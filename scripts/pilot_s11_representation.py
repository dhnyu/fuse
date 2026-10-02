#!/usr/bin/env python
"""Bounded, CPU-only S11 parity pilot. Never an entrypoint for full analysis.

Runs at most 32 predefined original queries against the accepted 9000 candidates.
Only diagnostic counts/hashes are published under the external pilot root.
"""
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
sys.path.insert(0, str(ROOT / "python"))
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


def run_pilot():
    contract, lock = load_frozen_contract()
    require(contract["scope"]["full_analysis_authorized"] is False, "PILOT_SCOPE")
    x, centers, ids = verify_inputs(contract, lock)
    seed = contract["pilot"]["selection_seed"]
    selected = sorted(range(len(ids)), key=lambda i: (hashlib.sha256((str(seed) + ids[i]).encode()).digest(), ids[i]))[:32]
    positions = np.array(sorted(selected), dtype=np.int64)
    require(len(positions) == 32 < len(x), "QUERY_CAP")
    timing = {}
    # Independent reference only: the pilot may use a Python loop for validation.
    # The actual numerical implementation above has no Python per-query scoring.
    with threadpool_limits(limits=1):
        start = time.perf_counter()
        reference = np.stack([x @ x[q] for q in positions])
        timing["reference_gemv_seconds"] = time.perf_counter() - start
        start = time.perf_counter()
        gemm = x[positions] @ x.T
        timing["diagnostic_gemm_seconds"] = time.perf_counter() - start
    outputs = {}
    for size in contract["pilot"]["query_block_sizes"]:
        start = time.perf_counter()
        actual = np.concatenate([cosine_block(x, positions[start:start+size]) for start in range(0, len(positions), size)])
        timing[f"native_batched_block_{size}_seconds"] = time.perf_counter() - start
        outputs[str(size)] = bool(np.array_equal(actual, reference))
        require(outputs[str(size)], "BATCHED_SCORE_PARITY")
    distances, modes = eligibility(centers, positions)
    require(np.all(modes["standard"].sum(axis=1) == 8999), "STANDARD_COUNT")
    legacy_bands = json.loads(Path(lock["parents"]["band_manifest"]["path"]).read_text())
    require(legacy_bands["checkpoint"] == lock["checkpoint_id"] and legacy_bands["embedding_manifest"] == lock["embedding_manifest_id"], "BAND_LINEAGE")
    stored = pq.read_table(lock["parents"]["bands"]["path"], filters=[("query_scene_id", "in", [ids[i] for i in positions])]).to_pylist()
    require(len(stored) == 32 * 2 * 31, "PARENT_BAND_RECORD_COUNT")
    rows_by_key = {(r["query_scene_id"], r["mode"], r["rank"]): r for r in stored}
    require(len(rows_by_key) == len(stored), "PARENT_BAND_UNIQUE")
    comparison = {}
    legacy_ids = np.array(ids)
    for mode, mask in modes.items():
        bands = band_indices(actual, mask)
        positions_by_band = band_positions(mask.sum(axis=1))
        candidate_order_mismatches = 0
        gemm_order_mismatches = 0
        gemm_band_mismatches = 0
        gemm_bands = band_indices(gemm, mask)
        # Deliberately independent lexical reference on only the 32 pilot rows.
        for qi, position in enumerate(positions):
            eligible = np.flatnonzero(mask[qi])
            reference_order = eligible[np.lexsort((legacy_ids[eligible], -reference[qi, eligible]))]
            actual_order = eligible[np.argsort(-actual[qi, eligible], kind="stable")]
            gm_order = eligible[np.argsort(-gemm[qi, eligible], kind="stable")]
            candidate_order_mismatches += int(np.count_nonzero(reference_order != actual_order))
            gemm_order_mismatches += int(np.count_nonzero(reference_order != gm_order))
            for name, ranks in positions_by_band.items():
                require(np.array_equal(bands[name][qi], reference_order[ranks[qi]-1]), "INDEPENDENT_BAND_PARITY")
                gemm_band_mismatches += int(np.count_nonzero(bands[name][qi] != gemm_bands[name][qi]))
                for rank, candidate in zip(ranks[qi], bands[name][qi], strict=True):
                    old = rows_by_key[(ids[position], mode, int(rank))]
                    require(old["candidate_scene_id"] == ids[candidate] and old["cosine"] == float(actual[qi, candidate]) and old["distance_m"] == float(distances[qi, candidate]), "ACCEPTED_BAND_EXACT_READBACK")
        require(candidate_order_mismatches == 0, "FULL_ELIGIBLE_ORDER_PARITY")
        comparison[mode] = {"candidate_count_min": int(mask.sum(1).min()), "candidate_count_max": int(mask.sum(1).max()),
                            "native_order_mismatches": candidate_order_mismatches,
                            "diagnostic_gemm_order_mismatches": gemm_order_mismatches,
                            "diagnostic_gemm_band_slot_mismatches": gemm_band_mismatches}
    # Re-read parent hashes after computation; nothing is re-inferred or rewritten.
    for role, record in lock["parents"].items():
        require(file_sha256(record["path"]) == record["sha256"], "SOURCE_CHANGED:" + role)
    result = {"status": "PASS", "scope": "bounded_numerical_parity_pilot_only", "full_analysis_ready": False,
              "contract_sha256": lock["contract_sha256"], "checkpoint_id": lock["checkpoint_id"],
              "embedding_manifest_id": lock["embedding_manifest_id"], "query_count": 32, "candidate_count": 9000,
              "query_scene_ids": [ids[i] for i in positions], "selection_seed": seed,
              "block_exact_score_parity": outputs, "eligible_ranking_checks": comparison,
              "accepted_band_records_exact": len(stored),
              "diagnostic_gemm": {"bitwise_equal": bool(np.array_equal(reference, gemm)),
                                  "unequal_scores": int(np.count_nonzero(reference != gemm)),
                                  "max_absolute_difference": float(np.max(np.abs(reference-gemm)))},
              "reference_score_sha256": hashlib.sha256(reference.tobytes()).hexdigest(),
              "timing": timing, "parent_hashes_unchanged": True,
              "versions": {p: importlib.metadata.version(p) for p in ["numpy", "scipy", "pyarrow", "threadpoolctl"]},
              "python": platform.python_version(), "blas": threadpool_info(),
              "execution": {"workers": 1, "blas_threads_during_scoring": 1, "gpu": 0,
                            "inference": 0, "training": 0, "full_s11": False},
              "unexecuted": ["full 9000-query alignment", "production descriptor extraction", "UMAP fitting", "targets graph implementation"],
              "source_hashes": {p: file_sha256(ROOT / p) for p in ["python/representation_analysis.py", "scripts/pilot_s11_representation.py"]}}
    return contract, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()  # No full mode, query-count override, inference or GPU options.
    contract, result = run_pilot()
    parent = Path(contract["pilot"]["output_root"])
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=datetime.datetime.now().strftime("%Y%m%d_%H%M%S_") , dir=parent))
    raw = json.dumps(result, indent=2, allow_nan=False, sort_keys=True).encode() + b"\n"
    staged = root / "parity_result.json.staging"
    with staged.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(json.loads(staged.read_bytes()) == result, "DIAGNOSTIC_READBACK")
    os.link(staged, root / "parity_result.json")
    staged.unlink()
    print(str(root / "parity_result.json"))


if __name__ == "__main__":
    main()
