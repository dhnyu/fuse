#!/usr/bin/env python3
"""Mandatory 320-scene float64 scientific-geometry no-op gate for I19."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import jsonschema
import numpy as np
import shapely

from prototype_augmentation import canonical_json_bytes, no_op_round_trip_scene
from prototype_dataloader import AcceptedPrototypeDataset
from run_prototype_augmentation_benchmark import load_resources, read_json, sha256_file


REGRESSION_SCENES = [
    "scn_3e1fb01511497ec3fd8e984b",
    "scn_6db492fed1b26a915e27759a",
    "scn_aa160d43b2f2411038ace102",
    "scn_3943062e027f61a18ae5cda2",
    "scn_62344300076ce1f87edff43f",
    "scn_1f40aa20639e2b32c602b8f6",
]


def compare_directories(left: Path, right: Path) -> None:
    left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
    if left_files != right_files:
        raise FileExistsError("same no-op gate ID has a different file set")
    for relative in left_files:
        if sha256_file(left / relative) != sha256_file(right / relative):
            raise FileExistsError(f"same no-op gate ID has different content: {relative}")


def publish(stage: Path, final: Path) -> None:
    if final.exists():
        compare_directories(stage, final)
        shutil.rmtree(stage)
    else:
        final.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(final)


def output_record(path: Path) -> dict[str, Any]:
    return {"relative_path": path.name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-manifest", required=True)
    parser.add_argument("--dataloader-result", required=True)
    parser.add_argument("--tensor-contract", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--implementation", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    accepted_path = Path(args.accepted_manifest).resolve()
    loader_path = Path(args.dataloader_result).resolve()
    tensor_contract = Path(args.tensor_contract).resolve()
    schema_path = Path(args.schema).resolve()
    accepted, loader = read_json(accepted_path), read_json(loader_path)
    if accepted.get("status") != "READY" or loader.get("status") != "READY":
        raise RuntimeError("no-op gate requires READY I16 and I17")
    if loader.get("accepted_dataset_id") != accepted.get("training_dataset_id"):
        raise RuntimeError("no-op gate I16/I17 identity mismatch")
    dataset = AcceptedPrototypeDataset(accepted_path, tensor_contract, split=None)
    resources = load_resources(accepted)
    rows = [no_op_round_trip_scene(dataset[position], resources) for position in range(len(dataset))]
    if len(rows) != 320 or len({row["scene_id"] for row in rows}) != 320:
        raise RuntimeError("no-op gate scene coverage mismatch")
    regression = {scene: next((row for row in rows if row["scene_id"] == scene), None)
                  for scene in REGRESSION_SCENES}
    if any(value is None for value in regression.values()):
        raise RuntimeError("no-op regression scene missing")
    count_fields = [key for key in rows[0] if key.startswith(("missing_", "extra_"))] + [
        "dangling_relation", "self_relation", "duplicate_relation", "invalid_geometry",
        "coordinate_offset_mismatch", "building_area_non_bit_exact", "reference_center_mismatch",
        "reference_area_alignment_mismatch",
    ]
    totals = {key: sum(int(row[key]) for row in rows) for key in count_fields}
    area_qc = {
        "bit_exact_count": sum(int(row["building_area_bit_exact"]) for row in rows),
        "non_bit_exact_count": totals["building_area_non_bit_exact"],
        "maximum_ulp_distance": max(int(row["building_area_maximum_ulp"]) for row in rows),
        "maximum_absolute_standardized_difference": max(
            float(row["building_area_maximum_absolute_standardized_difference"]) for row in rows
        ),
        "affected": [
            {"scene_id": row["scene_id"], "entities": json.loads(row["building_area_affected_json"])}
            for row in rows if json.loads(row["building_area_affected_json"])
        ],
    }
    cross_runtime = [item for row in rows for item in json.loads(row["building_area_cross_runtime_json"])]
    absolute = np.asarray([item["absolute_difference"] for item in cross_runtime], dtype=np.float64)
    relative = np.asarray([item["relative_difference"] for item in cross_runtime], dtype=np.float64)
    cross_runtime_qc = {
        "runtime": {"shapely": shapely.__version__, "geos": shapely.geos_version_string},
        "exact_equal_count": sum(int(item["exact_equal"]) for item in cross_runtime),
        "absolute_difference": {name: float(value) for name, value in zip(
            ("min", "median", "p95", "p99", "max"), np.quantile(absolute, [0, .5, .95, .99, 1]))},
        "relative_difference": {name: float(value) for name, value in zip(
            ("min", "median", "p95", "p99", "max"), np.quantile(relative, [0, .5, .95, .99, 1]))},
        "selected_host_affected_poi_count": sum(int(row["selected_host_area_affected_count"]) for row in rows),
    }
    host_scene = next(row for row in rows if row["scene_id"] == "scn_62344300076ce1f87edff43f")
    hosts = {int(poi): int(host) for host, poi in json.loads(host_scene["selected_hosts_json"])}
    expected_pois = (948, 979, 985, 988, 1014)
    if any(hosts.get(poi) != 439 for poi in expected_pois) or any(hosts.get(poi) == 415 for poi in expected_pois):
        raise RuntimeError("authoritative-area selected-host regression failed")
    failed = [row for row in rows if row["status"] != "PASS"]
    if failed or any(totals.values()):
        raise RuntimeError("scientific geometry no-op round-trip failed: " + json.dumps(
            {"totals": totals, "failed_scenes": failed[:10]}, sort_keys=True, separators=(",", ":")
        ))

    scientific_identity = {
        "accepted_dataset_id": accepted["training_dataset_id"],
        "dataloader_smoke_id": loader["smoke_id"],
        "accepted_manifest_sha256": sha256_file(accepted_path),
        "dataloader_result_sha256": sha256_file(loader_path),
        "tensor_contract_sha256": sha256_file(tensor_contract),
        "schema_sha256": sha256_file(schema_path),
        "implementation_sha256": sha256_file(Path(args.implementation)),
        "runner_sha256": sha256_file(Path(__file__)),
        "requirements_sha256": sha256_file(Path(args.requirements)),
        "predicate": "exact_shapely_cnt_wit_int_con_v1",
    }
    logical_result = {
        "scene_count": 320, "totals": totals, "building_area_float32_qc": area_qc,
        "cross_runtime_geometry_area_qc": cross_runtime_qc,
        "regression_scenes": {scene: regression[scene]["status"] for scene in REGRESSION_SCENES},
        "scene_result_digest": hashlib.sha256(canonical_json_bytes(rows)).hexdigest(),
    }
    gate_id = "pgr_" + hashlib.sha256(canonical_json_bytes({
        "scientific_identity": scientific_identity, "logical_result": logical_result,
    })).hexdigest()[:24]
    output_root = Path(args.output_root).resolve()
    output_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{gate_id}.stage-", dir=output_root.parent))
    rows_path = stage / "scientific_geometry_roundtrip_scenes.parquet"
    pq.write_table(pa.Table.from_pylist(rows), rows_path, compression="zstd")
    manifest_path = stage / "scientific_geometry_roundtrip_manifest.json"
    manifest = {
        "schema_version": "1.0.0", "status": "PASS", "gate_id": gate_id,
        "accepted_dataset_id": accepted["training_dataset_id"], "dataloader_smoke_id": loader["smoke_id"],
        "scientific_identity": scientific_identity, "logical_result": logical_result,
        "outputs": [output_record(rows_path)],
    }
    jsonschema.validate(manifest, read_json(schema_path))
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    publish(stage, output_root / gate_id)
    print(str((output_root / gate_id / manifest_path.name).resolve()))
    print(str((output_root / gate_id / rows_path.name).resolve()))


if __name__ == "__main__":
    main()
