#!/usr/bin/env python3
"""I16 aggregate acceptance for the immutable prototype serialization cache."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from safetensors.numpy import load as load_safetensors

from serialize_prototype_shard import canonical_json_bytes, normalization_maps, sha256_file, standardized
from validate_prototype_serialization_shards import validate_scene_tensors


BRANCH_FILES = {
    "manifest": "branch_manifest.json",
    "scene_index": "scene_index.parquet",
    "qc": "branch_qc.json",
    "log": "branch_log.jsonl",
}
I13_FILES = {
    "manifest": "prototype_spatial_manifest.json",
    "dictionary": "prototype_entity_dictionary.parquet",
    "qc": "prototype_spatial_qc.json",
    "vocabulary": "prototype_categorical_vocabulary.parquet",
    "normalization": "prototype_normalization_statistics.parquet",
    "missing_mapping": "prototype_missing_mapping.json",
    "scene_statistics": "prototype_scene_spatial_statistics.parquet",
    "alias": "prototype_categorical_aliases.parquet",
    "road_topology": "prototype_road_topology.parquet",
    "log": "prototype_spatial_log.jsonl",
}


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_record(path: Path, root: Path | None = None) -> dict[str, Any]:
    relative = str(path.relative_to(root)) if root else str(path.resolve())
    return {"path": relative, "relative_path": relative, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def write_parquet(rows: list[dict[str, Any]], path: Path, config: dict[str, Any]) -> None:
    table = pa.Table.from_pylist(rows)
    pq.write_table(
        table, path, compression=config["output"]["parquet_compression"],
        row_group_size=int(config["output"]["parquet_row_group_size"]),
        use_dictionary=False, write_statistics=True, data_page_version="1.0",
    )


def compare_directories(left: Path, right: Path) -> None:
    left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
    if left_files != right_files:
        raise FileExistsError("immutable accepted dataset file set differs")
    for relative in left_files:
        if sha256_file(left / relative) != sha256_file(right / relative):
            raise FileExistsError(f"same accepted dataset ID has different immutable content: {relative}")


def require_unique_paths(paths: list[str], expected_names: set[str], scope: str) -> dict[str, Path]:
    values = [Path(path).resolve() for path in paths]
    names = [path.name for path in values]
    if len(values) != len(set(values)) or len(names) != len(set(names)):
        raise ValueError(f"duplicate {scope} path or basename")
    missing, extra = expected_names - set(names), set(names) - expected_names
    if missing or extra:
        raise ValueError(f"{scope} file set mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
    return {path.name: path for path in values}


def group_branch_files(paths: list[str]) -> dict[str, dict[str, Path]]:
    grouped: dict[Path, list[Path]] = {}
    for value in paths:
        path = Path(value).resolve()
        grouped.setdefault(path.parent, []).append(path)
    result: dict[str, dict[str, Path]] = {}
    for directory, values in grouped.items():
        manifests = [path for path in values if path.name == "branch_manifest.json"]
        if len(manifests) != 1:
            raise ValueError(f"branch bundle lacks exactly one manifest: {directory}")
        manifest = read_json(manifests[0])
        branch_id = manifest.get("branch_id")
        expected = set(BRANCH_FILES.values()) | {f"scenes-{branch_id}.tar", f"scenes-{branch_id}.idx"}
        by_name = require_unique_paths([str(path) for path in values], expected, f"branch {branch_id}")
        if branch_id in result:
            raise ValueError(f"duplicate branch ID: {branch_id}")
        result[branch_id] = by_name
    return result


def validate_branch_sets(expected: list[str], observed: list[str]) -> None:
    if len(expected) != len(set(expected)):
        raise ValueError("duplicate I14 branch ID")
    if len(observed) != len(set(observed)):
        raise ValueError("duplicate I15 branch ID")
    missing, extra = set(expected) - set(observed), set(observed) - set(expected)
    if missing or extra:
        raise ValueError(f"I14/I15 branch set mismatch: missing={sorted(missing)}, extra={sorted(extra)}")


def validate_scene_assignments(rows: list[dict[str, Any]], expected: dict[str, str]) -> None:
    ids = [row["scene_id"] for row in rows]
    duplicate = sorted({scene for scene in ids if ids.count(scene) > 1})
    missing, extra = set(expected) - set(ids), set(ids) - set(expected)
    cross = sorted(row["scene_id"] for row in rows if expected.get(row["scene_id"]) != row["split"])
    if duplicate or missing or extra or cross:
        raise ValueError(
            f"scene assignment mismatch: duplicate={duplicate[:3]}, missing={sorted(missing)[:3]}, "
            f"extra={sorted(extra)[:3]}, cross_split={cross[:3]}"
        )


def verify_record(record: dict[str, Any], path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size != int(record["size_bytes"]) or sha256_file(path) != record["sha256"]:
        raise ValueError(f"size/checksum mismatch: {label}: {path}")


def read_indexed_member(stream: io.BufferedReader, record: dict[str, Any], expected_name: str) -> bytes:
    offset = int(record["offset"])
    stream.seek(offset)
    header = stream.read(512)
    if len(header) != 512:
        raise ValueError(f"truncated tar header: {expected_name}")
    try:
        info = tarfile.TarInfo.frombuf(header, encoding="utf-8", errors="surrogateescape")
    except tarfile.HeaderError as error:
        raise ValueError(f"corrupted tar header: {expected_name}") from error
    payload_size = int(record["payload_bytes"])
    expected_length = 512 + math.ceil(payload_size / 512) * 512
    if info.name != expected_name or info.size != payload_size or int(record["length"]) != expected_length:
        raise ValueError(f".idx offset/size or tar member mismatch: {expected_name}")
    payload = stream.read(payload_size)
    if len(payload) != payload_size or sha256_bytes(payload) != record["sha256"]:
        raise ValueError(f"indexed tar payload checksum mismatch: {expected_name}")
    return payload


class MemoryArchive:
    def __init__(self, payloads: dict[str, bytes]):
        self.payloads = payloads

    def extractfile(self, name: str) -> io.BytesIO:
        if name not in self.payloads:
            raise KeyError(name)
        return io.BytesIO(self.payloads[name])


def vocabulary_limits(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    rows = pq.read_table(path).to_pylist()
    limits: dict[str, int] = {}
    mask: dict[str, int] = {}
    for row in rows:
        attribute, index = str(row["attribute"]), int(row["index"])
        limits[attribute] = max(limits.get(attribute, -1), index)
        if row["category_key"] == "MASK":
            mask[attribute] = index
    return limits, mask


def validate_category_arrays(entities: dict[str, np.ndarray], config: dict[str, Any], limits: dict[str, int], masks: dict[str, int]) -> None:
    groups = (("B", "building_category"), ("R", "road_category"), ("P", "poi_category"))
    for entity_type, key in groups:
        values = entities[key]
        attributes = config["tensor"]["categorical_attributes"][entity_type]
        for column, attribute in enumerate(attributes):
            if attribute not in limits or np.any(values[:, column] < 0) or np.any(values[:, column] > limits[attribute]):
                raise ValueError(f"categorical index range mismatch: {attribute}")
            if attribute in masks and np.any(values[:, column] == masks[attribute]):
                raise ValueError(f"raw MASK category is forbidden: {attribute}")


def validate_direct_scene(
    stream: io.BufferedReader, scene_entry: dict[str, Any], scene_id: str, split: str,
    config: dict[str, Any], limits: dict[str, int], masks: dict[str, int], norm: dict[str, dict[str, Any]], expected_offset: int,
) -> tuple[dict[str, int], dict[str, Any]]:
    suffixes = list(config["archive"]["member_order"])
    members = scene_entry.get("members", [])
    names = [member.get("name") for member in members]
    expected_names = [f"{scene_id}.{suffix}" for suffix in suffixes]
    if names != expected_names or len(names) != len(set(names)):
        raise ValueError(f"missing/duplicate/unexpected member group: {scene_id}")
    if int(scene_entry["offset"]) != expected_offset or int(members[0]["offset"]) != expected_offset:
        raise ValueError(f"non-contiguous sample offset: {scene_id}")
    payloads: dict[str, bytes] = {}
    next_offset = expected_offset
    for member, name in zip(members, expected_names):
        if int(member["offset"]) != next_offset:
            raise ValueError(f"non-contiguous member offset: {name}")
        payloads[name] = read_indexed_member(stream, member, name)
        next_offset += int(member["length"])
    if int(scene_entry["length"]) != next_offset - expected_offset:
        raise ValueError(f"sample length mismatch: {scene_id}")
    metrics = validate_scene_tensors(MemoryArchive(payloads), scene_id, split, config)
    entities = load_safetensors(payloads[f"{scene_id}.entities.safetensors"])
    edges = load_safetensors(payloads[f"{scene_id}.edges.safetensors"])
    topology = load_safetensors(payloads[f"{scene_id}.topology.safetensors"])
    geometry = load_safetensors(payloads[f"{scene_id}.geometry.safetensors"])
    n = metrics["node_count"]
    if edges["edge_index"].size and (np.any(edges["edge_index"] < 0) or np.any(edges["edge_index"] >= n)):
        raise ValueError(f"dangling relation endpoint: {scene_id}")
    if np.any(np.bitwise_and(edges["relation_mask"], np.uint8(224)) != 0):
        raise ValueError(f"unknown relation mask bit: {scene_id}")
    topology_node_count = len(topology["node_incident_road_count"])
    if topology["road_endpoint_node_index"].size and (
        np.any(topology["road_endpoint_node_index"] < 0) or
        np.any(topology["road_endpoint_node_index"] >= topology_node_count)
    ):
        raise ValueError(f"road topology endpoint index out of range: {scene_id}")
    if np.any(topology["road_endpoint_retained"] > 1):
        raise ValueError(f"road topology endpoint-retained range mismatch: {scene_id}")
    validate_category_arrays(entities, config, limits, masks)
    references = geometry["building_observed_area_m2_reference"]
    expected_area = np.asarray([
        standardized(None if bool(missing) else float(reference), "building_observed_area_m2", norm)[0]
        for reference, missing in zip(references, entities["building_missing"][:, 0])
    ], dtype=np.float32)
    stored_area = entities["building_numerical"][:, 0]
    if not np.array_equal(expected_area.view(np.uint32), stored_area.view(np.uint32)):
        mismatch = np.flatnonzero(expected_area.view(np.uint32) != stored_area.view(np.uint32))[0]
        raise ValueError(f"Building reference-area/model bit mismatch: {scene_id}:{int(mismatch)}")
    return metrics, {
        "sample_offset": expected_offset,
        "sample_length": int(scene_entry["length"]),
        "actual_payload_bytes": sum(int(member["payload_bytes"]) for member in members),
        **{
            f"{suffix.replace('.', '_')}_{field}": int(member[field])
            for suffix, member in zip(suffixes, members)
            for field in ("offset", "payload_bytes")
        },
    }


def aggregate_row(scope: str, scope_id: str, branch_rows: list[dict[str, Any]]) -> dict[str, Any]:
    estimate = sum(int(row["estimated_uncompressed_bytes"]) for row in branch_rows)
    payload = sum(int(row["actual_payload_bytes"]) for row in branch_rows)
    archive = sum(int(row["tar_bytes"]) for row in branch_rows)
    return {
        "scope": scope, "scope_id": scope_id, "branch_count": len(branch_rows),
        "scene_count": sum(int(row["scene_count"]) for row in branch_rows),
        "node_count": sum(int(row["node_count"]) for row in branch_rows),
        "ordered_edge_count": sum(int(row["ordered_edge_count"]) for row in branch_rows),
        "coordinate_count": sum(int(row["coordinate_count"]) for row in branch_rows),
        "empty_edge_scene_count": sum(int(row["empty_edge_scene_count"]) for row in branch_rows),
        "estimated_uncompressed_bytes": estimate, "actual_payload_bytes": payload, "tar_bytes": archive,
        "estimate_error_bytes": payload - estimate,
        "estimate_error_ratio": payload / estimate - 1.0,
        "tar_overhead_bytes": archive - payload,
        "tar_overhead_ratio": archive / payload - 1.0,
    }


def build_acceptance(
    invocation_path: Path, config_path: Path, schema_path: Path, i15_config_path: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    invocation = read_json(invocation_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    i15_config = yaml.safe_load(i15_config_path.read_text(encoding="utf-8"))
    schema = read_json(schema_path)
    specs = [read_json(path) for path in invocation["spec_paths"]]
    if len(invocation["spec_paths"]) != len(set(invocation["spec_paths"])):
        raise ValueError("duplicate I14 spec path")
    split_rank = {value: index for index, value in enumerate(config["ordering"]["splits"])}
    specs.sort(key=lambda value: (split_rank.get(value["split"], 999), value["branch_id"]))
    expected = config["expected"]
    if len(specs) != int(expected["branch_count"]):
        raise ValueError(f"expected {expected['branch_count']} specs, found {len(specs)}")
    if any(spec["plan_id"] != config["identity"]["serialization_plan_id"] for spec in specs):
        raise ValueError("I14 plan identity mismatch")
    branch_files = group_branch_files(invocation["branch_files"])
    validate_branch_sets([spec["branch_id"] for spec in specs], list(branch_files))
    i13 = require_unique_paths(invocation["i13_files"], set(I13_FILES.values()), "I13 acceptance")
    i13_manifest = read_json(i13[I13_FILES["manifest"]])
    if i13_manifest.get("spatial_dataset_id") != config["identity"]["spatial_dataset_id"] or i13_manifest.get("status") != "PASS":
        raise ValueError("I13 scientific identity or status mismatch")

    accepted_artifacts = specs[0]["accepted_artifacts"]
    for key, record in accepted_artifacts.items():
        path = i13[I13_FILES[key]]
        if Path(record["path"]).resolve() != path or record["sha256"] != sha256_file(path) or int(record["size_bytes"]) != path.stat().st_size:
            raise ValueError(f"I13 accepted artifact forwarding/checksum mismatch: {key}")
    for spec in specs:
        if spec["accepted_artifacts"] != accepted_artifacts:
            raise ValueError(f"I13 artifact identity differs across specs: {spec['branch_id']}")

    limits, masks = vocabulary_limits(i13[I13_FILES["vocabulary"]])
    norm = normalization_maps(pq.read_table(i13[I13_FILES["normalization"]]).to_pylist())
    branch_rows: list[dict[str, Any]] = []
    global_rows: list[dict[str, Any]] = []
    expected_scene_splits = {scene: spec["split"] for spec in specs for scene in spec["scene_ids"]}
    if len(expected_scene_splits) != sum(len(spec["scene_ids"]) for spec in specs):
        raise ValueError("duplicate I14 scene")
    split_positions = {split: 0 for split in split_rank}
    global_position = 0
    tensor_schema_hash: str | None = None
    tensor_contract_hash: str | None = None
    branch_manifest_hashes: list[dict[str, str]] = []

    for shard_order, spec in enumerate(specs):
        branch_id, files = spec["branch_id"], branch_files[spec["branch_id"]]
        manifest_path = files[BRANCH_FILES["manifest"]]
        manifest = read_json(manifest_path)
        if manifest.get("status") != "PASS" or manifest.get("branch_id") != branch_id:
            raise ValueError(f"branch manifest status/ID mismatch: {branch_id}")
        if manifest.get("scene_ids") != spec["scene_ids"] or manifest.get("split") != spec["split"]:
            raise ValueError(f"I14/I15 scene order or split mismatch: {branch_id}")
        if manifest.get("accepted_artifacts") != accepted_artifacts:
            raise ValueError(f"I13 forwarding mismatch: {branch_id}")
        source_spec = manifest["source_spec"]
        spec_path = Path(invocation["spec_paths"][[Path(path).resolve() for path in invocation["spec_paths"]].index(Path(source_spec["path"]).resolve())]).resolve()
        verify_record(source_spec, spec_path, f"I14 spec {branch_id}")
        if manifest["qc"].get("status") != "PASS" or int(manifest["qc"].get("error_count", -1)) != 0:
            raise ValueError(f"branch QC failed: {branch_id}")
        output_records = {record["relative_path"]: record for record in manifest["outputs"]}
        expected_output_names = set(files) - {"branch_manifest.json"}
        if set(output_records) != expected_output_names:
            raise ValueError(f"branch manifest output set mismatch: {branch_id}")
        for name, record in output_records.items():
            verify_record(record, files[name], f"I15 {branch_id}/{name}")
        manifest_hash = sha256_file(manifest_path)
        branch_manifest_hashes.append({"branch_id": branch_id, "sha256": manifest_hash})
        if tensor_schema_hash is None:
            tensor_schema_hash = manifest["tensor_schema_hash"]
            tensor_contract_hash = manifest["tensor_contract_sha256"]
        if manifest["tensor_schema_hash"] != tensor_schema_hash or manifest["tensor_contract_sha256"] != tensor_contract_hash:
            raise ValueError(f"tensor scientific identity mismatch: {branch_id}")
        area_provenance = manifest.get("building_observed_area_reference_provenance", {})
        source_records = area_provenance.get("source_artifacts", [])
        if (area_provenance.get("source_column") != "observed_area_m2" or
                area_provenance.get("dtype") != "float64" or not source_records):
            raise ValueError(f"Building reference-area provenance missing: {branch_id}")
        for record in source_records:
            verify_record(record, Path(record["path"]), f"Building reference area source {branch_id}")

        tar_name, idx_name = f"scenes-{branch_id}.tar", f"scenes-{branch_id}.idx"
        tar_path, idx_path = files[tar_name], files[idx_name]
        json_index = read_json(idx_path)
        sidecar = pq.read_table(files[BRANCH_FILES["scene_index"]]).to_pylist()
        if json_index.get("branch_id") != branch_id or [row["scene_id"] for row in json_index.get("scenes", [])] != spec["scene_ids"]:
            raise ValueError(f".idx scene order mismatch: {branch_id}")
        if [row["scene_id"] for row in sidecar] != spec["scene_ids"] or [row["scene_order"] for row in sidecar] != list(range(len(sidecar))):
            raise ValueError(f"sidecar scene order mismatch: {branch_id}")
        expected_names = [f"{scene}.{suffix}" for scene in spec["scene_ids"] for suffix in config["archive"]["member_order"]]
        with tarfile.open(tar_path, "r:") as archive:
            names = archive.getnames()
        if names != expected_names or len(names) != len(set(names)):
            raise ValueError(f"tar member order/completeness mismatch: {branch_id}")

        observed_totals = {key: 0 for key in ("node_count", "ordered_edge_count", "coordinate_count", "empty_edge_scene_count")}
        with tar_path.open("rb") as stream:
            next_offset = 0
            for scene_order, (scene_id, index_entry, sidecar_row) in enumerate(zip(spec["scene_ids"], json_index["scenes"], sidecar)):
                metrics, access = validate_direct_scene(
                    stream, index_entry, scene_id, spec["split"], i15_config, limits, masks, norm, next_offset
                )
                next_offset += access["sample_length"]
                if (
                    int(sidecar_row["sample_offset"]) != access["sample_offset"]
                    or int(sidecar_row["sample_length"]) != access["sample_length"]
                    or int(sidecar_row["node_count"]) != metrics["node_count"]
                    or int(sidecar_row["edge_count"]) != metrics["ordered_edge_count"]
                    or int(sidecar_row["coordinate_count"]) != metrics["coordinate_count"]
                    or bool(sidecar_row["empty_edge"]) != bool(metrics["empty_edge_scene_count"])
                ):
                    raise ValueError(f".idx/sidecar/tensor mismatch: {scene_id}")
                for key in observed_totals:
                    observed_totals[key] += metrics[key]
                global_rows.append({
                    "training_dataset_id": "__PENDING__", "serialization_dataset_id": manifest["serialization_dataset_id"],
                    "serialization_plan_id": manifest["plan_id"], "spatial_dataset_id": manifest["spatial_dataset_id"],
                    "shard_id": f"pts_{sha256_bytes(canonical_json_bytes({'branch_id': branch_id, 'manifest_sha256': manifest_hash}))[:24]}",
                    "branch_id": branch_id, "scene_id": scene_id, "split": spec["split"],
                    "global_order": global_position, "split_local_order": split_positions[spec["split"]],
                    "shard_order": shard_order, "shard_scene_order": scene_order,
                    "tar_path": str(tar_path), "tar_sha256": output_records[tar_name]["sha256"],
                    "idx_path": str(idx_path), "idx_sha256": output_records[idx_name]["sha256"],
                    "sample_key": scene_id, "member_prefix": f"{scene_id}.",
                    **access, "node_count": metrics["node_count"],
                    "ordered_edge_count": metrics["ordered_edge_count"],
                    "coordinate_count": metrics["coordinate_count"],
                    "empty_edge": bool(metrics["empty_edge_scene_count"]),
                })
                global_position += 1
                split_positions[spec["split"]] += 1
        manifest_totals = manifest["totals"]
        if any(observed_totals[key] != int(manifest_totals[key]) for key in observed_totals):
            raise ValueError(f"tensor/manifest resource total mismatch: {branch_id}")
        branch_rows.append({
            "training_dataset_id": "__PENDING__", "shard_id": global_rows[-1]["shard_id"],
            "shard_order": shard_order, "branch_id": branch_id, "split": spec["split"],
            "spec_path": str(spec_path), "spec_sha256": source_spec["sha256"],
            "branch_manifest_path": str(manifest_path), "branch_manifest_sha256": manifest_hash,
            "tar_path": str(tar_path), "tar_sha256": output_records[tar_name]["sha256"], "tar_bytes": tar_path.stat().st_size,
            "idx_path": str(idx_path), "idx_sha256": output_records[idx_name]["sha256"], "idx_bytes": idx_path.stat().st_size,
            "scene_index_path": str(files[BRANCH_FILES["scene_index"]]), "scene_index_sha256": output_records[BRANCH_FILES["scene_index"]]["sha256"],
            "qc_path": str(files[BRANCH_FILES["qc"]]), "qc_sha256": output_records[BRANCH_FILES["qc"]]["sha256"],
            "log_path": str(files[BRANCH_FILES["log"]]), "log_sha256": output_records[BRANCH_FILES["log"]]["sha256"],
            "scene_count": int(manifest_totals["scene_count"]), "node_count": int(manifest_totals["node_count"]),
            "ordered_edge_count": int(manifest_totals["ordered_edge_count"]), "coordinate_count": int(manifest_totals["coordinate_count"]),
            "empty_edge_scene_count": int(manifest_totals["empty_edge_scene_count"]),
            "estimated_uncompressed_bytes": int(manifest_totals["estimated_uncompressed_bytes"]),
            "actual_payload_bytes": int(manifest_totals["actual_uncompressed_bytes"]),
        })

    validate_scene_assignments(global_rows, expected_scene_splits)
    diagnostics = [aggregate_row("branch", row["branch_id"], [row]) for row in branch_rows]
    diagnostics += [aggregate_row("split", split, [row for row in branch_rows if row["split"] == split]) for split in split_rank]
    aggregate = aggregate_row("dataset", config["identity"]["serialization_dataset_id"], branch_rows)
    diagnostics.append(aggregate)
    observed = {
        "branch_count": aggregate["branch_count"], "scene_count": aggregate["scene_count"],
        "split_counts": {split: sum(row["scene_count"] for row in branch_rows if row["split"] == split) for split in split_rank},
        "node_count": aggregate["node_count"], "ordered_edge_count": aggregate["ordered_edge_count"],
        "coordinate_count": aggregate["coordinate_count"], "empty_edge_scene_count": aggregate["empty_edge_scene_count"],
        "estimated_uncompressed_bytes": aggregate["estimated_uncompressed_bytes"],
        "actual_payload_bytes": aggregate["actual_payload_bytes"], "tar_bytes": aggregate["tar_bytes"],
    }
    expected_values = {key: expected[key] for key in observed}
    if observed != expected_values:
        raise ValueError(f"authoritative aggregate total mismatch: observed={observed}, expected={expected_values}")

    identity = {
        "acceptance_algorithm": "deterministic_i14_i15_indexed_aggregate_acceptance_v1",
        "spatial_dataset_id": config["identity"]["spatial_dataset_id"],
        "serialization_plan_id": config["identity"]["serialization_plan_id"],
        "serialization_dataset_id": config["identity"]["serialization_dataset_id"],
        "i13_manifest_sha256": accepted_artifacts["manifest"]["sha256"],
        "i13_accepted_artifacts": accepted_artifacts,
        "i14_specs": [{"branch_id": spec["branch_id"], "sha256": sha256_file(Path(spec[".path"])) if ".path" in spec else sha256_file(Path(next(path for path in invocation["spec_paths"] if Path(path).name == f"spec-{spec['branch_id']}.json")))} for spec in specs],
        "i15_branch_manifests": branch_manifest_hashes,
        "tensor_schema_hash": tensor_schema_hash, "tensor_contract_sha256": tensor_contract_hash,
        "acceptance_config_sha256": sha256_file(config_path), "acceptance_schema_sha256": sha256_file(schema_path),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "ordering": config["ordering"], "archive": config["archive"],
    }
    training_dataset_id = f"{config['identity']['accepted_dataset_prefix']}_{sha256_bytes(canonical_json_bytes(identity))[:24]}"
    for row in branch_rows + global_rows:
        row["training_dataset_id"] = training_dataset_id
    aggregate["scope_id"] = training_dataset_id

    serialization_root = Path(specs[0]["output"]["root"]).resolve()
    final_dir = output_dir.resolve() if output_dir else serialization_root / config["output"]["directory"] / training_dataset_id
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=f".{training_dataset_id}.staging-", dir=final_dir.parent))
    names = config["output"]
    try:
        shard_catalog_path = stage_dir / names["shard_catalog"]
        global_index_path = stage_dir / names["global_scene_index"]
        dataset_index_path = stage_dir / names["dataset_index"]
        qc_path = stage_dir / names["qc"]
        diagnostics_path = stage_dir / names["diagnostics"]
        log_path = stage_dir / names["log"]
        manifest_path = stage_dir / names["manifest"]
        write_parquet(branch_rows, shard_catalog_path, config)
        write_parquet(global_rows, global_index_path, config)
        write_parquet(diagnostics, diagnostics_path, config)
        splits = {}
        for split in split_rank:
            rows = [row for row in global_rows if row["split"] == split]
            shards = [row for row in branch_rows if row["split"] == split]
            splits[split] = {
                "scene_count": len(rows), "global_order_start": rows[0]["global_order"],
                "global_order_end_exclusive": rows[-1]["global_order"] + 1,
                "branch_ids": [row["branch_id"] for row in shards], "shard_ids": [row["shard_id"] for row in shards],
            }
        dataset_index = {
            "index_schema_version": "1.0.0", "training_dataset_id": training_dataset_id,
            "serialization_dataset_id": config["identity"]["serialization_dataset_id"],
            "shard_catalog": names["shard_catalog"], "global_scene_index": names["global_scene_index"],
            "sequential_order": config["ordering"]["scenes"], "random_access": "tar_idx_direct_seek",
            "splits": splits,
        }
        dataset_index_path.write_bytes(canonical_json_bytes(dataset_index))
        qc = {
            "qc_schema_version": "1.0.0", "status": "PASS", "training_dataset_id": training_dataset_id,
            **observed, "error_count": 0, "missing_branch_count": 0, "extra_branch_count": 0,
            "duplicate_branch_count": 0, "missing_scene_count": 0, "extra_scene_count": 0,
            "duplicate_scene_count": 0, "cross_split_shard_count": 0, "checksum_mismatch_count": 0,
            "tar_member_mismatch_count": 0, "index_mismatch_count": 0, "tensor_mismatch_count": 0,
            "dangling_edge_count": 0, "unknown_relation_mask_count": 0, "category_error_count": 0,
            "nonfinite_float_count": 0, "invalid_offset_count": 0, "raster_error_count": 0,
            "i13_forwarding_error_count": 0, "direct_seek_scene_count": len(global_rows),
        }
        qc_path.write_bytes(canonical_json_bytes(qc))
        log_path.write_bytes(canonical_json_bytes({
            "event": "prototype_training_dataset_acceptance_complete", "status": "READY",
            "training_dataset_id": training_dataset_id, "branch_count": len(branch_rows), "scene_count": len(global_rows),
            "workers": 1, "threads": 1, "gpu": 0,
        }))
        output_paths = [shard_catalog_path, global_index_path, dataset_index_path, qc_path, diagnostics_path, log_path]
        manifest = {
            "manifest_schema_version": "1.0.0", "status": "READY", "training_dataset_id": training_dataset_id,
            "spatial_dataset_id": config["identity"]["spatial_dataset_id"],
            "serialization_plan_id": config["identity"]["serialization_plan_id"],
            "serialization_dataset_id": config["identity"]["serialization_dataset_id"],
            "totals": observed, "scientific_identity": identity, "accepted_artifacts": accepted_artifacts,
            "i13_outputs": {key: file_record(path) for key, filename in I13_FILES.items() for path in [i13[filename]]},
            "outputs": [file_record(path, stage_dir) for path in output_paths], "qc": qc,
            "execution": {"controller": "controller_05", "workers": 1, "threads": 1, "gpu": 0},
        }
        jsonschema.validate(instance=manifest, schema=schema)
        manifest_path.write_bytes(canonical_json_bytes(manifest))
        if final_dir.exists():
            compare_directories(stage_dir, final_dir)
            shutil.rmtree(stage_dir)
            reuse = True
        else:
            os.replace(stage_dir, final_dir)
            reuse = False
        return {
            "status": "READY", "training_dataset_id": training_dataset_id,
            "output_files": sorted(str(path.resolve()) for path in final_dir.iterdir() if path.is_file()),
            "immutable_reuse": reuse,
        }
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--invocation", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--i15-config", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build_acceptance(
        args.invocation.resolve(), args.config.resolve(), args.schema.resolve(),
        args.i15_config.resolve(), args.output_dir.resolve() if args.output_dir else None,
    )
    print(canonical_json_bytes(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
