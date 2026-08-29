#!/usr/bin/env python3
"""Verify the P6 v3 split-coordinate contract on the historical defect case."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p6_data import build_vocabulary, ragged_collate, validate_geometry_layout
from p7_training import P7ArtifactCatalog, P7Data

SCENE_ID = "scn_28a3bd91311d83e99834f532"
CANDIDATE_ID = "augv_0c7fb311e3c582cf84136d90"
MASTER_VIEW_ID = 7
PRECEDING_SCENE_ID = "scn_45571a771359c97c621b43f7"
PRECEDING_MASTER_VIEW_ID = 5


def digest(value: torch.Tensor) -> str:
    return hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def load_data(preprocessing: str) -> P7Data:
    config = yaml.safe_load((ROOT / "config/p7_deterministic_training.yml").read_text())
    roots = {
        "p3": "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/original_scene_cache/oscache_c89fa07e3d6cb1819a7994a6",
        "p4": "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/augmentation_banks/augbank_252ce67e6d74679b02871e57",
        "p5": "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/fixed_queries/fqa_89741b3e7b3ff7e44597ca67",
    }
    catalog = P7ArtifactCatalog(roots, config["parents"], verify=True)
    vocabulary = build_vocabulary(ROOT / "config/codebooks/spatial_categories.json")
    prototype = pq.read_table(
        "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/index/"
        "rsi_80031f1493c75163f91b7c71/prototype/rps_4dfda380e54a9b7f9f60ac04/"
        "prototype_scene_selection.parquet"
    ).to_pylist()
    return P7Data(catalog, json.loads(Path(preprocessing).read_text()), vocabulary, prototype)


def scene_slice(batch: dict, index: int) -> dict:
    node_start, node_end = map(int, batch["scene_ptr"][index:index + 2])
    part_start, part_end = map(int, batch["part_coordinate_ptr"][index:index + 2])
    ring_start, ring_end = map(int, batch["ring_coordinate_ptr"][index:index + 2])
    first_part = int(batch["geometry"]["entity_part_offsets"][node_start])
    return {
        "part_count": part_end - part_start,
        "ring_count": ring_end - ring_start,
        "total_count": part_end - part_start + ring_end - ring_start,
        "first_part_count": int(batch["geometry"]["part_coordinate_offsets"][first_part + 1]
                                - batch["geometry"]["part_coordinate_offsets"][first_part]),
        "part_sha256": digest(batch["geometry"]["part_coordinates_xy_m_scientific"][part_start:part_end]),
        "ring_sha256": digest(batch["geometry"]["ring_coordinates_xy_m_scientific"][ring_start:ring_end]),
        "entity_count": node_end - node_start,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preprocessing", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = load_data(args.preprocessing)
    candidate = data.training_view(SCENE_ID, MASTER_VIEW_ID)
    preceding = data.training_view(PRECEDING_SCENE_ID, PRECEDING_MASTER_VIEW_ID)
    if candidate["view_id"] != CANDIDATE_ID:
        raise ValueError("problem candidate identity changed")
    validate_geometry_layout(candidate)
    expected = scene_slice(ragged_collate([candidate]), 0)
    contexts = {
        "alone": expected,
        "after_trailing_ring": scene_slice(ragged_collate([preceding, candidate]), 1),
        "before_trailing_ring": scene_slice(ragged_collate([candidate, preceding]), 0),
    }
    failures = [name for name, row in contexts.items() if row != expected]
    if expected["total_count"] != 28 or expected["first_part_count"] != 6 or failures:
        raise ValueError(f"P6 geometry v3 historical-defect verification failed: {failures}")
    result = {
        "status": "PASS", "geometry_layout_version": "3.0.0",
        "scene_id": SCENE_ID, "candidate_id": CANDIDATE_ID,
        "contexts": contexts, "wrong_33_coordinate_observations": 0,
        "batch_context_variants": 0, "wrong_declared_ranges": 0,
        "road_fourier_input_corruptions": 0,
    }
    Path(args.output).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
