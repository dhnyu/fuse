#!/usr/bin/env python3
"""Mandatory 320-scene float64 scientific-geometry no-op gate for I19."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
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


_WORKER_DATASET: AcceptedPrototypeDataset | None = None
_WORKER_RESOURCES: dict[str, Any] | None = None


def initialize_worker(accepted_path: str, tensor_contract: str) -> None:
    global _WORKER_DATASET, _WORKER_RESOURCES
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    import torch
    torch.set_num_threads(1)
    accepted = read_json(Path(accepted_path))
    _WORKER_DATASET = AcceptedPrototypeDataset(Path(accepted_path), Path(tensor_contract), split=None)
    _WORKER_RESOURCES = load_resources(accepted)


def process_scene(position: int) -> dict[str, Any]:
    if _WORKER_DATASET is None or _WORKER_RESOURCES is None:
        raise RuntimeError("no-op worker was not initialized")
    return no_op_round_trip_scene(_WORKER_DATASET[position], _WORKER_RESOURCES)


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
    workers = 40
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers,
        initializer=initialize_worker,
        initargs=(str(accepted_path), str(tensor_contract)),
    ) as executor:
        rows = list(executor.map(process_scene, range(len(dataset)), chunksize=1))
    rows.sort(key=lambda row: row["scene_id"])
    if len(rows) != 320 or len({row["scene_id"] for row in rows}) != 320:
        raise RuntimeError("no-op gate scene coverage mismatch")
    representative_ids = sorted({
        value["scene_id"] for value in loader["correctness"]["representatives"].values()
    })
    regression = {scene: next(row for row in rows if row["scene_id"] == scene)
                  for scene in representative_ids}
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
        "regression_scenes": {scene: regression[scene]["status"] for scene in representative_ids},
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
        "execution": {"process_workers": workers, "native_threads_per_worker": 1},
        "outputs": [output_record(rows_path)],
    }
    jsonschema.validate(manifest, read_json(schema_path))
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    publish(stage, output_root / gate_id)
    print(str((output_root / gate_id / manifest_path.name).resolve()))
    print(str((output_root / gate_id / rows_path.name).resolve()))


if __name__ == "__main__":
    main()
