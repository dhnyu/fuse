#!/usr/bin/env python
"""Read-only accepted S10/FM parent validation for S11. No model loading."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
import numpy as np
import pyarrow.parquet as pq
from threadpoolctl import threadpool_info, threadpool_limits

from representation_analysis import (band_indices, band_positions, cosine_block,
    eligibility, file_sha256, load_frozen_contract)
from retrieval_artifacts import load as read_accepted_manifest


def require(condition, message):
    if not condition:
        raise ValueError("S11_PILOT_" + message)


def verify_inputs(contract, lock):
    parents = lock["parents"]
    for role, row in parents.items():
        require(file_sha256(row["path"]) == row["sha256"], "PARENT_HASH:" + role)
    require(file_sha256(ROOT / "python/retrieval_inference.py") == lock["inference_source_sha256"], "INFERENCE_SOURCE")
    require(file_sha256(ROOT / "python/retrieval_ranking.py") == lock["legacy_ranking_source_sha256"], "RANKING_SOURCE")
    require(file_sha256(ROOT / "python/model_data.py") == lock["category_alias_reference_sha256"], "CATEGORY_ALIAS_REFERENCE")
    accepted = read_accepted_manifest(parents["s10_acceptance"]["path"], "acceptance")
    gallery = read_accepted_manifest(parents["gallery"]["path"], "gallery")
    models = read_accepted_manifest(parents["models"]["path"], "models")
    embeddings = read_accepted_manifest(parents["fm_embedding_manifest"]["path"], "embeddings")
    # Bind provenance to the accepted S10 runtime, not just today's source bytes.
    for source in ["python/retrieval_inference.py", "python/retrieval_ranking.py", "python/model_data.py"]:
        require(models["body"]["runtime"]["sources"][source] == file_sha256(ROOT / source), "ACCEPTED_RUNTIME_SOURCE:" + source)
    require(parents["categories"]["path"] == models["body"]["roots"]["categories"], "CATEGORY_PARENT_PATH")
    require(models["body"]["config"]["source_pins"][parents["categories"]["path"]] == parents["categories"]["sha256"], "CATEGORY_PARENT_HASH")
    require(accepted["body"]["status"] == "PASS", "S10_ACCEPTANCE")
    require(accepted["body"]["gallery_manifest_id"] == gallery["artifact_id"] == embeddings["body"]["gallery_manifest_id"], "GALLERY_LINEAGE")
    require(accepted["body"]["model_manifest_id"] == models["artifact_id"] == embeddings["body"]["model_manifest_id"], "MODEL_LINEAGE")
    fm = next(x for x in models["body"]["models"] if x["configuration_id"] == "cmp_FM")
    require(fm == embeddings["body"]["model"], "FM_BINDING")
    checkpoint = json.loads(Path(parents["checkpoint_manifest"]["path"]).read_text())
    require(checkpoint["completed_epoch"] == 60 and checkpoint["checkpoint_id"] == fm["checkpoint_id"] == lock["checkpoint_id"], "CHECKPOINT")
    require(checkpoint["payload"]["sha256"] == parents["checkpoint"]["sha256"] == fm["payload_sha256"], "CHECKPOINT_BYTES")
    require(fm["acceptance_id"] == lock["training_acceptance_id"], "TRAINING_ACCEPTANCE")
    rows = gallery["body"]["rows"]
    ids = [r["scene_id"] for r in rows]
    require(len(ids) == len(set(ids)) == 9000 and ids == sorted(ids) == embeddings["body"]["scene_ids"], "EXACT_IDS_ORDER")
    require(all(r["split"] == "evaluation" and r["epsg"] == 5186 for r in rows), "EVALUATION_ONLY")
    index = pq.read_table(parents["scene_index"]["path"], columns=["scene_id", "split", "center_x", "center_y"]).to_pylist()
    index = sorted((r for r in index if r["split"] == "evaluation"), key=lambda r: r["scene_id"])
    require([r["scene_id"] for r in index] == ids, "P1_SPLIT")
    centers = np.array([[r["center_x"], r["center_y"]] for r in rows], dtype=np.float64)
    require(np.array_equal(centers, [[r["center_x"], r["center_y"]] for r in index]), "P1_CENTERS")
    vectors = np.load(parents["fm_vectors"]["path"], mmap_mode="r", allow_pickle=False)
    require(vectors.shape == (9000, 256) and vectors.dtype == np.float32 and np.isfinite(vectors).all(), "X_SHAPE_FINITE")
    require(np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=2e-6, rtol=0), "X_NORMALIZATION")
    require(embeddings["artifact_id"] == lock["embedding_manifest_id"], "EMBEDDING_ID")
    categories = json.loads(Path(parents["categories"]["path"]).read_text())
    l2 = [r for r in categories["entries"] if r["attribute"] == "CLASS_L2"]
    require(len(l2) == 17 and all("/" in r["category_key"] for r in l2), "OFFICIAL_POI_L2")
    return vectors, centers, ids

