#!/usr/bin/env python3
"""Validate global completeness of I15 branches without declaring I16."""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import numpy as np
import yaml
from safetensors.numpy import load as load_safetensors

from serialize_prototype_shard import MEMBER_SUFFIXES, canonical_json_bytes, read_json, sha256_file


EXPECTED = {
    "branch_count": 51,
    "scene_count": 320,
    "split_counts": {"training": 256, "validation": 32, "evaluation": 32},
    "node_count": 237121,
    "ordered_edge_count": 2756444,
    "coordinate_count": 794540,
    "empty_edge_scene_count": 59,
}


def assert_dtype_shape(array: np.ndarray, dtype: str, shape: tuple[Any, ...], dimensions: dict[str, int], key: str) -> None:
    expected_shape = tuple(dimensions.get(value, value) for value in shape)
    if array.dtype != np.dtype(dtype) or array.shape != expected_shape:
        raise ValueError(f"tensor dtype/shape mismatch: {key}: {array.dtype}/{array.shape} != {dtype}/{expected_shape}")


def validate_scene_tensors(archive: tarfile.TarFile, scene_id: str, split: str, config: dict[str, Any]) -> dict[str, int]:
    meta = json.loads(archive.extractfile(f"{scene_id}.meta.json").read())
    tensors = {
        group: load_safetensors(archive.extractfile(f"{scene_id}.{group}.safetensors").read())
        for group in ("entities", "geometry", "edges", "rasters")
    }
    entities, geometry, edges, rasters = (tensors[name] for name in ("entities", "geometry", "edges", "rasters"))
    n = len(meta["local_entity_ids"])
    e = int(meta["counts"]["edges"])
    c = int(meta["counts"]["coordinates"])
    if meta["scene_id"] != scene_id or meta["split"] != split or meta["local_entity_ids"] != list(range(n)):
        raise ValueError(f"scene metadata/local entity order mismatch: {scene_id}")
    nb = int(np.count_nonzero(entities["entity_type"] == 0))
    nr = int(np.count_nonzero(entities["entity_type"] == 1))
    np_count = int(np.count_nonzero(entities["entity_type"] == 2))
    part_count = len(geometry["part_coordinate_offsets"]) - 1
    ring_count = len(geometry["ring_is_hole"])
    dimensions = {
        "N": n, "NB": nb, "NR": nr, "NP": np_count, "C": c, "E": e,
        "N_plus_1": n + 1, "PART_plus_1": part_count + 1, "COMPONENT_plus_1": part_count + 1,
        "RING": ring_count,
    }
    groups = config["tensor"]["safetensors"]
    for group_name, arrays in tensors.items():
        contract = groups[group_name]
        if set(arrays) != set(contract):
            raise ValueError(f"safetensors key mismatch: {scene_id}:{group_name}")
        for key, definition in contract.items():
            assert_dtype_shape(arrays[key], definition["dtype"], tuple(definition["shape"]), dimensions, f"{scene_id}:{group_name}:{key}")
            if np.issubdtype(arrays[key].dtype, np.floating) and not np.isfinite(arrays[key]).all():
                raise ValueError(f"non-finite tensor: {scene_id}:{group_name}:{key}")
    for key in ("entity_coordinate_offsets", "entity_part_offsets", "entity_component_offsets", "entity_ring_offsets"):
        if geometry[key][0] != 0 or np.any(np.diff(geometry[key]) < 0):
            raise ValueError(f"invalid entity geometry offsets: {scene_id}:{key}")
    if geometry["entity_coordinate_offsets"][-1] != c or geometry["part_coordinate_offsets"][-1] != c:
        raise ValueError(f"geometry terminal offset mismatch: {scene_id}")
    if not np.array_equal(geometry["entity_part_offsets"], geometry["entity_component_offsets"]) or not np.array_equal(geometry["part_coordinate_offsets"], geometry["component_coordinate_offsets"]):
        raise ValueError(f"part/component topology mismatch: {scene_id}")
    if np.any(edges["relation_mask"] < 1) or np.any(edges["relation_mask"] > 31):
        raise ValueError(f"relation mask range mismatch: {scene_id}")
    if bool(meta["empty_edge"]) != (edges["edge_index"].shape == (2, 0)):
        raise ValueError(f"empty edge tensor mismatch: {scene_id}")
    for key in ("building_category", "road_category", "poi_category"):
        if np.any(entities[key] < 0):
            raise ValueError(f"negative categorical index: {scene_id}:{key}")
    for key in ("object_dem_missing", "building_missing", "road_missing"):
        if np.any((entities[key] != 0) & (entities[key] != 1)):
            raise ValueError(f"invalid missing indicator: {scene_id}:{key}")
    return {"node_count": n, "ordered_edge_count": e, "coordinate_count": c, "empty_edge_scene_count": int(e == 0)}


def validate(plan_directory: Path, output_root: Path, config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    spec_paths = sorted(plan_directory.glob("spec-psb_*.json"))
    if len(spec_paths) != EXPECTED["branch_count"]:
        raise ValueError(f"expected 51 I14 specs, found {len(spec_paths)}")
    specs = [read_json(path) for path in spec_paths]
    expected_scenes = [scene for spec in specs for scene in spec["scene_ids"]]
    if len(expected_scenes) != EXPECTED["scene_count"] or len(set(expected_scenes)) != len(expected_scenes):
        raise ValueError("I14 spec scenes are duplicate/incomplete")

    manifests = []
    all_scenes: list[str] = []
    split_counts = {key: 0 for key in EXPECTED["split_counts"]}
    totals = {key: 0 for key in ("node_count", "ordered_edge_count", "coordinate_count", "empty_edge_scene_count")}
    archive_bytes = 0
    actual_uncompressed_bytes = 0
    estimated_uncompressed_bytes = 0
    for spec in specs:
        branch_dir = output_root / "branches" / spec["branch_id"]
        manifest_path = branch_dir / "branch_manifest.json"
        manifest = read_json(manifest_path)
        if manifest["status"] != "PASS" or manifest["branch_id"] != spec["branch_id"] or manifest["scene_ids"] != spec["scene_ids"]:
            raise ValueError(f"branch manifest/spec identity or scene order mismatch: {spec['branch_id']}")
        if manifest["split"] != spec["split"] or manifest["plan_id"] != spec["plan_id"]:
            raise ValueError(f"branch split/plan mismatch: {spec['branch_id']}")
        if manifest["accepted_artifacts"] != spec["accepted_artifacts"] or manifest["upstream_datasets"] != spec["upstream_datasets"]:
            raise ValueError(f"I13 artifact/dataset forwarding mismatch: {spec['branch_id']}")
        if manifest["qc"]["status"] != "PASS" or manifest["qc"]["error_count"] != 0 or manifest["qc"]["round_trip_scene_count"] != len(spec["scene_ids"]):
            raise ValueError(f"branch QC mismatch: {spec['branch_id']}")
        for output in manifest["outputs"]:
            path = branch_dir / output["relative_path"]
            if not path.is_file() or path.stat().st_size != output["size_bytes"] or sha256_file(path) != output["sha256"]:
                raise ValueError(f"branch checksum mismatch: {path}")
        index = pq.read_table(branch_dir / "scene_index.parquet").to_pylist()
        if [row["scene_id"] for row in index] != spec["scene_ids"] or [row["scene_order"] for row in index] != list(range(len(index))):
            raise ValueError(f"scene index order mismatch: {spec['branch_id']}")
        archive_path = branch_dir / f"scenes-{spec['branch_id']}.tar"
        json_index = read_json(branch_dir / f"scenes-{spec['branch_id']}.idx")
        if [row["scene_id"] for row in json_index["scenes"]] != spec["scene_ids"]:
            raise ValueError(f"JSON index scene order mismatch: {spec['branch_id']}")
        with tarfile.open(archive_path, "r:") as archive:
            names = archive.getnames()
            expected_names = [f"{scene}.{suffix}" for scene in spec["scene_ids"] for suffix in MEMBER_SUFFIXES]
            if names != expected_names or len(names) != len(set(names)):
                raise ValueError(f"tar member mismatch: {spec['branch_id']}")
            tensor_totals = {key: 0 for key in totals}
            for scene_id in spec["scene_ids"]:
                for key, value in validate_scene_tensors(archive, scene_id, spec["split"], config).items():
                    tensor_totals[key] += value
        if tensor_totals != {key: int(manifest["totals"][key]) for key in totals}:
            raise ValueError(f"tensor/manifest totals mismatch: {spec['branch_id']}")
        manifests.append(manifest)
        all_scenes.extend(manifest["scene_ids"])
        split_counts[manifest["split"]] += manifest["totals"]["scene_count"]
        for key in totals:
            totals[key] += manifest["totals"][key]
        archive_bytes += manifest["totals"]["archive_bytes"]
        actual_uncompressed_bytes += manifest["totals"]["actual_uncompressed_bytes"]
        estimated_uncompressed_bytes += manifest["totals"]["estimated_uncompressed_bytes"]

    if set(all_scenes) != set(expected_scenes) or len(all_scenes) != len(set(all_scenes)):
        raise ValueError("I15 global duplicate/missing scene")
    observed = {"branch_count": len(manifests), "scene_count": len(all_scenes), "split_counts": split_counts, **totals}
    if observed != EXPECTED:
        raise ValueError(f"I15 global totals mismatch: {observed}")
    return {
        "status": "PASS",
        **observed,
        "duplicate_scene_count": 0,
        "missing_scene_count": 0,
        "tensor_schema_mismatch_count": 0,
        "dangling_edge_count": 0,
        "category_error_count": 0,
        "normalization_error_count": 0,
        "raster_error_count": 0,
        "checksum_mismatch_count": 0,
        "artifact_forwarding_error_count": 0,
        "archive_bytes": archive_bytes,
        "actual_uncompressed_bytes": actual_uncompressed_bytes,
        "estimated_uncompressed_bytes": estimated_uncompressed_bytes,
        "estimate_error_ratio": actual_uncompressed_bytes / estimated_uncompressed_bytes - 1,
        "compression_ratio": archive_bytes / actual_uncompressed_bytes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-directory", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(args.plan_directory.resolve(), args.output_root.resolve(), args.config.resolve())
    payload = canonical_json_bytes(result)
    if args.output:
        args.output.write_bytes(payload)
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
