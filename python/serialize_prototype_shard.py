#!/usr/bin/env python3
"""Serialize one approved I14 branch into deterministic WebDataset members.

The implementation follows dissertation Section 2 object-modal geometry and
relation graph contracts. It consumes accepted I13 paths only through an I14
specification and never mutates upstream artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import resource
import shutil
import sys
import tarfile
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
import zarr
import jsonschema
from safetensors.numpy import load as load_safetensors
from safetensors.numpy import save as save_safetensors
from shapely import from_wkb


MEMBER_SUFFIXES = (
    "meta.json",
    "entities.safetensors",
    "geometry.safetensors",
    "edges.safetensors",
    "topology.safetensors",
    "rasters.safetensors",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: str | Path, root: str | Path | None = None) -> dict[str, Any]:
    path = Path(path).resolve()
    record = {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
    if root is not None:
        relative = path.relative_to(Path(root).resolve()).as_posix()
        record["path"] = relative
        record["relative_path"] = relative
    return record


def verify_record(record: dict[str, Any], label: str) -> None:
    path = Path(record["path"])
    if not path.is_file() or path.stat().st_size != int(record["size_bytes"]) or sha256_file(path) != record["sha256"]:
        raise ValueError(f"checksum or size mismatch: {label}: {path}")


def read_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def read_filtered(path: str | Path, scene_ids: list[str]) -> list[dict[str, Any]]:
    table = pq.read_table(path, filters=[("scene_id", "in", scene_ids)])
    return table.to_pylist()


def output_path(manifest: dict[str, Any], basename: str) -> str:
    matches = [item["path"] for item in manifest["outputs"] if Path(item["path"]).name == basename]
    if len(matches) != 1:
        raise ValueError(f"accepted manifest has {len(matches)} outputs named {basename}")
    return matches[0]


def verify_source_contract(spec: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    for name, record in spec["accepted_artifacts"].items():
        verify_record(record, f"I13 {name}")
    accepted = read_json(spec["accepted_artifacts"]["manifest"]["path"])
    if accepted.get("status") != "PASS" or accepted.get("spatial_dataset_id") != spec["spatial_dataset_id"]:
        raise ValueError("I13 accepted manifest identity/status mismatch")

    result: dict[str, dict[str, dict[str, Any]]] = {}
    for stage in ("vector", "raster", "relation"):
        result[stage] = {}
        for record in spec["upstream_datasets"]["branch_manifests"][stage]:
            path = Path(record["path"])
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                raise ValueError(f"I13 {stage} branch manifest checksum mismatch: {path}")
            manifest = read_json(path)
            if manifest.get("status") != "PASS" or manifest.get("branch_id") != record["branch_id"]:
                raise ValueError(f"I13 {stage} branch manifest identity/status mismatch: {path}")
            result[stage][record["branch_id"]] = manifest
    return result


def vocabulary_maps(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
    mapping: dict[str, dict[str, int]] = {}
    missing: dict[str, int] = {}
    for row in rows:
        attribute = row["attribute"]
        key = row["category_key"]
        index = int(row["index"])
        mapping.setdefault(attribute, {})[key] = index
        if row["entry_type"] == "MISSING":
            missing[attribute] = index
    if any("MASK" not in values for values in mapping.values()):
        raise ValueError("I13 vocabulary lacks reserved MASK entry")
    return mapping, missing


def normalization_maps(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["attribute"]: row for row in rows}


def category_index(attribute: str, raw_key: Any, vocab: dict[str, dict[str, int]], missing: dict[str, int]) -> int:
    if raw_key is None or str(raw_key).strip() == "":
        return missing[attribute]
    key = str(raw_key)
    if key == "MASK":
        raise ValueError(f"raw MASK is forbidden for {attribute}")
    if key not in vocab[attribute]:
        raise ValueError(f"invalid category without OOV fallback: {attribute}={key}")
    return vocab[attribute][key]


def standardized(value: Any, attribute: str, stats: dict[str, dict[str, Any]]) -> tuple[np.float32, np.uint8]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return np.float32(0), np.uint8(1)
    number = float(value)
    row = stats[attribute]
    if row["transform"] == "log1p":
        if number < 0:
            raise ValueError(f"negative log1p input for {attribute}")
        number = math.log1p(number)
    elif row["transform"] != "identity":
        raise ValueError(f"unsupported numerical transform: {row['transform']}")
    scale = float(row["applied_scale"])
    if not math.isfinite(number) or not math.isfinite(scale) or scale <= 0:
        raise ValueError(f"invalid numerical value/statistic for {attribute}")
    return np.float32((number - float(row["mean"])) / scale), np.uint8(0)


def poi_key(row: dict[str, Any], level: int) -> Any:
    if row[f"CLASS_L{level}_STATE"] != "VALUE":
        return None
    codes = [row[f"CLASS_L{i}_CODE"] for i in range(1, level + 1)]
    if any(value is None or str(value).strip() == "" for value in codes):
        raise ValueError(f"POI level {level} VALUE has incomplete ancestry")
    return "/".join(str(value) for value in codes)


def geometry_parts(geometry: Any) -> tuple[list[np.ndarray], list[tuple[np.ndarray, bool]], list[int]]:
    kind = geometry.geom_type
    if kind == "Point":
        return [np.asarray(geometry.coords, dtype=np.float64)], [], []
    if kind == "MultiPoint":
        return [np.asarray(item.coords, dtype=np.float64) for item in geometry.geoms], [], []
    if kind == "LineString":
        return [np.asarray(geometry.coords, dtype=np.float64)], [], []
    if kind == "MultiLineString":
        return [np.asarray(item.coords, dtype=np.float64) for item in geometry.geoms], [], []
    if kind == "Polygon":
        rings = [(np.asarray(geometry.exterior.coords, dtype=np.float64), False)]
        rings.extend((np.asarray(item.coords, dtype=np.float64), True) for item in geometry.interiors)
        return [np.concatenate([item[0] for item in rings], axis=0)], rings, [0] * len(rings)
    if kind == "MultiPolygon":
        parts: list[np.ndarray] = []
        rings: list[tuple[np.ndarray, bool]] = []
        ring_parts: list[int] = []
        for part_index, polygon in enumerate(geometry.geoms):
            current = [(np.asarray(polygon.exterior.coords, dtype=np.float64), False)]
            current.extend((np.asarray(item.coords, dtype=np.float64), True) for item in polygon.interiors)
            parts.append(np.concatenate([item[0] for item in current], axis=0))
            rings.extend(current)
            ring_parts.extend([part_index] * len(current))
        return parts, rings, ring_parts
    raise ValueError(f"unsupported observed geometry type: {kind}")


def ordered_tensors(tensors: dict[str, np.ndarray]) -> OrderedDict[str, np.ndarray]:
    return OrderedDict((key, np.ascontiguousarray(tensors[key])) for key in sorted(tensors))


def tensor_bytes(tensors: dict[str, np.ndarray]) -> bytes:
    return save_safetensors(ordered_tensors(tensors))


def validate_tensor_roundtrip(payload: bytes, expected: dict[str, np.ndarray], tolerance: float) -> None:
    actual = load_safetensors(payload)
    if set(actual) != set(expected):
        raise ValueError("safetensors key mismatch")
    for key, reference in expected.items():
        observed = actual[key]
        if observed.dtype != reference.dtype or observed.shape != reference.shape:
            raise ValueError(f"safetensors dtype/shape mismatch: {key}")
        if np.issubdtype(reference.dtype, np.floating):
            if not np.allclose(observed, reference, rtol=tolerance, atol=tolerance, equal_nan=False):
                raise ValueError(f"safetensors float round-trip mismatch: {key}")
        elif not np.array_equal(observed, reference):
            raise ValueError(f"safetensors exact round-trip mismatch: {key}")


def build_edge_tensors(relation_rows: list[dict[str, Any]], id_to_row: dict[int, int], scene_id: str) -> dict[str, np.ndarray]:
    relation_rows = sorted(
        relation_rows,
        key=lambda row: (int(row["source_local_entity_id"]), int(row["destination_local_entity_id"]), int(row["relation_mask"])),
    )
    edge_index = np.empty((2, len(relation_rows)), dtype=np.int64)
    relation_mask = np.empty((len(relation_rows),), dtype=np.uint8)
    for edge_row, relation in enumerate(relation_rows):
        source = int(relation["source_local_entity_id"])
        destination = int(relation["destination_local_entity_id"])
        if source not in id_to_row or destination not in id_to_row:
            raise ValueError(f"dangling/cross-scene edge for {scene_id}")
        edge_index[:, edge_row] = [id_to_row[source], id_to_row[destination]]
        mask = int(relation["relation_mask"])
        expected_mask = sum((1 << bit) for bit, name in enumerate(("has_sn", "has_cnt", "has_wit", "has_int", "has_con")) if relation[name])
        if mask != expected_mask or mask <= 0 or mask > 31:
            raise ValueError(f"relation mask mismatch for {scene_id}")
        relation_mask[edge_row] = mask
    return {"edge_index": edge_index, "relation_mask": relation_mask}


def validate_tar_member_names(names: list[str], scene_ids: list[str]) -> None:
    expected = [f"{scene_id}.{suffix}" for scene_id in scene_ids for suffix in MEMBER_SUFFIXES]
    if names != expected or len(names) != len(set(names)):
        raise ValueError("tar member order/duplicate/missing mismatch")


def create_scene(
    scene_id: str,
    split: str,
    stats_row: dict[str, Any],
    dictionary_rows: list[dict[str, Any]],
    vector_rows: dict[str, list[dict[str, Any]]],
    object_rows: list[dict[str, Any]],
    relation_rows: list[dict[str, Any]],
    topology_rows: list[dict[str, Any]],
    topology_source: dict[str, Any],
    raster_row: dict[str, Any],
    raster_arrays: dict[str, np.ndarray],
    vocab: dict[str, dict[str, int]],
    missing: dict[str, int],
    norm: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    dictionary_rows = sorted(dictionary_rows, key=lambda row: int(row["local_entity_id"]))
    expected_nodes = int(stats_row["i.node_count"])
    if len(dictionary_rows) != expected_nodes:
        raise ValueError(f"dictionary node count mismatch for {scene_id}")
    local_ids = [int(row["local_entity_id"]) for row in dictionary_rows]
    if local_ids != list(range(expected_nodes)):
        raise ValueError(f"local entity order is not contiguous for {scene_id}")
    if any(row["scene_id"] != scene_id or row["split"] != split for row in dictionary_rows):
        raise ValueError(f"dictionary scene/split mismatch for {scene_id}")

    source_by_id: dict[int, dict[str, Any]] = {}
    vector_type_codes = {"building": "B", "road": "R", "poi": "P"}
    for entity_type, rows in vector_rows.items():
        for row in rows:
            key = int(row["local_entity_id"])
            if key in source_by_id or row["entity_type"] != vector_type_codes[entity_type]:
                raise ValueError(f"duplicate/type-mismatched vector entity for {scene_id}:{key}")
            source_by_id[key] = row
    if set(source_by_id) != set(local_ids):
        raise ValueError(f"vector/dictionary entity mismatch for {scene_id}")
    object_by_id = {int(row["local_entity_id"]): row for row in object_rows}
    if len(object_by_id) != len(object_rows) or set(object_by_id) != set(local_ids):
        raise ValueError(f"object raster/dictionary entity mismatch for {scene_id}")

    entity_type_codes = config["tensor"]["entity_type_codes"]
    entity_type = np.asarray([entity_type_codes[row["entity_type"]] for row in dictionary_rows], dtype=np.uint8)
    relative = np.empty((expected_nodes, 2), dtype=np.float32)
    object_raster = np.empty((expected_nodes, 26), dtype=np.float32)
    object_dem_missing = np.empty((expected_nodes, 2), dtype=np.uint8)
    building_index: list[int] = []
    building_category: list[list[int]] = []
    building_numerical: list[list[np.float32]] = []
    building_missing: list[list[np.uint8]] = []
    building_area_reference: list[np.float64] = []
    road_index: list[int] = []
    road_category: list[list[int]] = []
    road_numerical: list[list[np.float32]] = []
    road_missing: list[list[np.uint8]] = []
    poi_index: list[int] = []
    poi_category: list[list[int]] = []

    coordinates: list[np.ndarray] = []
    absolute_reference_coordinates: list[np.ndarray] = []
    absolute_reference_centers = np.empty((expected_nodes, 2), dtype=np.float64)
    geometry_type: list[int] = []
    geometry_available: list[int] = []
    entity_coordinate_offsets = [0]
    entity_part_offsets = [0]
    part_coordinate_offsets = [0]
    entity_ring_offsets = [0]
    ring_component_index: list[int] = []
    ring_coordinate_start: list[int] = []
    ring_coordinate_end: list[int] = []
    ring_is_hole: list[int] = []
    geometry_codes = config["tensor"]["geometry_type_codes"]
    length = float(config["tensor"]["geometry_normalization_length_m"])

    for tensor_row, dictionary_row in enumerate(dictionary_rows):
        local_id = int(dictionary_row["local_entity_id"])
        entity = source_by_id[local_id]
        context = object_by_id[local_id]
        if entity["source_entity_id"] != dictionary_row["source_entity_id"] or context["source_entity_id"] != dictionary_row["source_entity_id"]:
            raise ValueError(f"source entity mapping mismatch for {scene_id}:{local_id}")
        relative[tensor_row] = [entity["relative_center_x_m"], entity["relative_center_y_m"]]
        dem_mean, dem_mean_missing = standardized(context["dem_mean_m"], "object_dem_mean_m", norm)
        dem_sd, dem_sd_missing = standardized(context["dem_sd_m"], "object_dem_sd_m", norm)
        object_raster[tensor_row] = [
            *[context[f"lc_fraction_{i:02d}"] for i in range(1, 23)],
            context["lc_valid_support_ratio"], dem_mean, dem_sd, context["dem_valid_support_ratio"],
        ]
        object_dem_missing[tensor_row] = [dem_mean_missing, dem_sd_missing]
        if not np.isfinite(relative[tensor_row]).all() or not np.isfinite(object_raster[tensor_row]).all():
            raise ValueError(f"non-finite entity tensor for {scene_id}:{local_id}")

        entity_kind = dictionary_row["entity_type"]
        if entity_kind == "B":
            building_index.append(tensor_row)
            structure_key = dictionary_row["building_structure_category_key"]
            if entity["A11"] == "블록구조" and str(structure_key) != "12":
                raise ValueError("Building 블록구조 must map only to official A11 code 12")
            building_category.append([
                category_index("A9", entity["A9"], vocab, missing),
                category_index("A11", structure_key, vocab, missing),
            ])
            area, area_missing = standardized(entity["observed_area_m2"], "building_observed_area_m2", norm)
            gross, gross_missing = standardized(entity["observed_gross_floor_area_m2"], "building_observed_gross_floor_area_m2", norm)
            building_numerical.append([area, gross])
            building_missing.append([area_missing, gross_missing])
            area_reference = entity["observed_area_m2"]
            if area_missing:
                building_area_reference.append(np.float64(0.0))
            else:
                area_reference = np.float64(area_reference)
                if not np.isfinite(area_reference) or area_reference <= 0:
                    raise ValueError(f"invalid Building reference area for {scene_id}:{local_id}")
                building_area_reference.append(area_reference)
        elif entity_kind == "R":
            road_index.append(tensor_row)
            road_category.append([
                category_index("ROAD_RANK", entity["ROAD_RANK"], vocab, missing),
                category_index("ROAD_TYPE", entity["ROAD_TYPE"], vocab, missing),
            ])
            lanes, lanes_missing = standardized(entity["LANES"], "road_lanes", norm)
            road_numerical.append([lanes])
            road_missing.append([lanes_missing])
        elif entity_kind == "P":
            poi_index.append(tensor_row)
            poi_category.append([
                category_index(f"CLASS_L{i}", poi_key(entity, i), vocab, missing) for i in range(1, 7)
            ])
        else:
            raise ValueError(f"unsupported entity type: {entity_kind}")

        geometry = from_wkb(entity["observed_geometry"])
        parts, rings, ring_parts = geometry_parts(geometry)
        center = np.asarray([entity["observed_center_x_5186"], entity["observed_center_y_5186"]], dtype=np.float64)
        if not np.isfinite(center).all():
            raise ValueError(f"non-finite scientific reference center for {scene_id}:{local_id}")
        xmin, ymin, xmax, ymax = geometry.bounds
        geometry_center = np.asarray([(xmin + xmax) / 2.0, (ymin + ymax) / 2.0], dtype=np.float64)
        if not np.allclose(geometry_center, center, rtol=0.0, atol=1e-8):
            raise ValueError(f"scientific reference center/geometry mismatch for {scene_id}:{local_id}")
        absolute_reference_centers[tensor_row] = center
        normalized_parts = [np.asarray((part[:, :2] - center) / length, dtype=np.float32) for part in parts]
        reference_parts = [np.asarray(part[:, :2], dtype=np.float64) for part in parts]
        normalized_rings = [np.asarray((ring[:, :2] - center) / length, dtype=np.float32) for ring, _ in rings]
        for part in normalized_parts:
            coordinates.append(part)
            part_coordinate_offsets.append(part_coordinate_offsets[-1] + len(part))
        absolute_reference_coordinates.extend(reference_parts)
        entity_coordinate_start = entity_coordinate_offsets[-1]
        part_base = entity_part_offsets[-1]
        ring_cursor = entity_coordinate_start
        for ring, (_, is_hole), local_part in zip(normalized_rings, rings, ring_parts):
            ring_component_index.append(part_base + local_part)
            ring_coordinate_start.append(ring_cursor)
            ring_cursor += len(ring)
            ring_coordinate_end.append(ring_cursor)
            ring_is_hole.append(int(is_hole))
        entity_coordinate_offsets.append(entity_coordinate_offsets[-1] + sum(len(part) for part in normalized_parts))
        entity_part_offsets.append(entity_part_offsets[-1] + len(parts))
        entity_ring_offsets.append(entity_ring_offsets[-1] + len(rings))
        geometry_type.append(geometry_codes[geometry.geom_type.upper()])
        geometry_available.append(int(config["tensor"]["geometry_available"][entity_kind]))

    coordinate_array = np.concatenate(coordinates, axis=0) if coordinates else np.empty((0, 2), dtype=np.float32)
    reference_coordinate_array = np.concatenate(absolute_reference_coordinates, axis=0) if absolute_reference_coordinates else np.empty((0, 2), dtype=np.float64)
    if len(coordinate_array) != int(sum(int(source_by_id[key]["observed_coordinate_count"]) for key in local_ids)):
        raise ValueError(f"geometry coordinate count mismatch for {scene_id}")
    if entity_coordinate_offsets[-1] != len(coordinate_array) or part_coordinate_offsets[-1] != len(coordinate_array):
        raise ValueError(f"geometry offset terminal mismatch for {scene_id}")

    entity_tensors = {
        "local_entity_id": np.asarray(local_ids, dtype=np.int64),
        "entity_type": entity_type,
        "relative_position_m": relative,
        "object_raster": object_raster,
        "object_dem_missing": object_dem_missing,
        "building_row_index": np.asarray(building_index, dtype=np.int64),
        "building_category": np.asarray(building_category, dtype=np.int32).reshape((-1, 2)),
        "building_numerical": np.asarray(building_numerical, dtype=np.float32).reshape((-1, 2)),
        "building_missing": np.asarray(building_missing, dtype=np.uint8).reshape((-1, 2)),
        "road_row_index": np.asarray(road_index, dtype=np.int64),
        "road_category": np.asarray(road_category, dtype=np.int32).reshape((-1, 2)),
        "road_numerical": np.asarray(road_numerical, dtype=np.float32).reshape((-1, 1)),
        "road_missing": np.asarray(road_missing, dtype=np.uint8).reshape((-1, 1)),
        "poi_row_index": np.asarray(poi_index, dtype=np.int64),
        "poi_category": np.asarray(poi_category, dtype=np.int32).reshape((-1, 6)),
    }
    geometry_tensors = {
        "coordinates_xy": coordinate_array,
        "coordinates_absolute_xy_5186": reference_coordinate_array,
        "reference_center_absolute_xy_5186": absolute_reference_centers,
        "building_observed_area_m2_reference": np.asarray(building_area_reference, dtype=np.float64),
        "geometry_type": np.asarray(geometry_type, dtype=np.uint8),
        "geometry_available": np.asarray(geometry_available, dtype=np.uint8),
        "entity_coordinate_offsets": np.asarray(entity_coordinate_offsets, dtype=np.int64),
        "entity_component_offsets": np.asarray(entity_part_offsets, dtype=np.int64),
        "component_coordinate_offsets": np.asarray(part_coordinate_offsets, dtype=np.int64),
        "entity_part_offsets": np.asarray(entity_part_offsets, dtype=np.int64),
        "part_coordinate_offsets": np.asarray(part_coordinate_offsets, dtype=np.int64),
        "entity_ring_offsets": np.asarray(entity_ring_offsets, dtype=np.int64),
        "ring_component_index": np.asarray(ring_component_index, dtype=np.int64),
        "ring_coordinate_start": np.asarray(ring_coordinate_start, dtype=np.int64),
        "ring_coordinate_end": np.asarray(ring_coordinate_end, dtype=np.int64),
        "ring_is_hole": np.asarray(ring_is_hole, dtype=np.uint8),
    }

    id_to_row = {local_id: row for row, local_id in enumerate(local_ids)}
    expected_edges = int(stats_row["ordered_pair_count"])
    if len(relation_rows) != expected_edges:
        raise ValueError(f"ordered edge count mismatch for {scene_id}")
    edge_tensors = build_edge_tensors(relation_rows, id_to_row, scene_id)

    road_rows = sorted((source_by_id[key] for key in local_ids if source_by_id[key]["entity_type"] == "R"),
                       key=lambda row: int(row["local_entity_id"]))
    topology_rows = sorted(topology_rows, key=lambda row: (int(row["road_local_entity_id"]), int(row["endpoint_order"])))
    if len(topology_rows) != 2 * len(road_rows):
        raise ValueError(f"road topology endpoint count mismatch for {scene_id}")
    by_endpoint = {(int(row["road_local_entity_id"]), int(row["endpoint_order"])): row for row in topology_rows}
    endpoint_node_index = np.empty((len(road_rows), 2), dtype=np.int64)
    endpoint_retained = np.empty((len(road_rows), 2), dtype=np.uint8)
    for road_offset, road in enumerate(road_rows):
        for endpoint_order, source_field in ((0, "F_NODE"), (1, "T_NODE")):
            row = by_endpoint.get((int(road["local_entity_id"]), endpoint_order))
            if row is None or str(row["road_source_entity_id"]) != str(road["source_entity_id"]) or str(row["original_node_id"]) != str(road[source_field]):
                raise ValueError(f"road topology exact join mismatch for {scene_id}:{road['local_entity_id']}")
            endpoint_node_index[road_offset, endpoint_order] = int(row["scene_node_index"])
            endpoint_retained[road_offset, endpoint_order] = int(bool(row["original_endpoint_retained"]))
    node_rows: dict[int, dict[str, Any]] = {}
    for row in topology_rows:
        index = int(row["scene_node_index"])
        signature = (str(row["original_node_id"]), int(row["scene_incident_road_count"]), int(row["node_state_code"]),
                     float(row["original_node_x_5186"]), float(row["original_node_y_5186"]))
        if index in node_rows:
            previous = node_rows[index]
            previous_signature = (str(previous["original_node_id"]), int(previous["scene_incident_road_count"]), int(previous["node_state_code"]),
                                  float(previous["original_node_x_5186"]), float(previous["original_node_y_5186"]))
            if signature != previous_signature:
                raise ValueError(f"inconsistent original road node dictionary for {scene_id}:{index}")
        else:
            node_rows[index] = row
    if sorted(node_rows) != list(range(len(node_rows))):
        raise ValueError(f"road topology node index is not dense for {scene_id}")
    ordered_nodes = [node_rows[index] for index in range(len(node_rows))]
    topology_tensors = {
        "road_endpoint_node_index": endpoint_node_index,
        "road_endpoint_retained": endpoint_retained,
        "node_incident_road_count": np.asarray([row["scene_incident_road_count"] for row in ordered_nodes], dtype=np.int32),
        "node_state": np.asarray([row["node_state_code"] for row in ordered_nodes], dtype=np.uint8),
        "node_xy_5186": np.asarray([[row["original_node_x_5186"], row["original_node_y_5186"]] for row in ordered_nodes], dtype=np.float64).reshape((-1, 2)),
    }
    if len(ordered_nodes) and (endpoint_node_index.min() < 0 or endpoint_node_index.max() >= len(ordered_nodes)):
        raise ValueError(f"road topology endpoint index out of range for {scene_id}")

    lc = np.asarray(raster_arrays["landcover_class_fraction"], dtype=np.float32)
    lc_support = np.asarray(raster_arrays["landcover_valid_support"], dtype=np.float32)
    lc_mask = np.asarray(raster_arrays["landcover_valid_mask"], dtype=np.uint8)
    dem_raw = np.asarray(raster_arrays["dem_raw_mean"], dtype=np.float32)
    dem_support = np.asarray(raster_arrays["dem_valid_support"], dtype=np.float32)
    dem_mask = np.asarray(raster_arrays["dem_valid_mask"], dtype=np.uint8)
    if lc.shape != (22, 100, 100) or lc_support.shape != (100, 100) or lc_mask.shape != (100, 100):
        raise ValueError(f"landcover raster shape mismatch for {scene_id}")
    if dem_raw.shape != (17, 17) or dem_support.shape != (17, 17) or dem_mask.shape != (17, 17):
        raise ValueError(f"DEM raster shape mismatch for {scene_id}")
    if not np.array_equal((lc_support > 0).astype(np.uint8), lc_mask) or not np.array_equal((dem_support > 0).astype(np.uint8), dem_mask):
        raise ValueError(f"raster support/mask mismatch for {scene_id}")
    dem_stat = norm["scene_dem_mean_m"]
    dem = np.zeros_like(dem_raw, dtype=np.float32)
    valid = dem_mask.astype(bool)
    dem[valid] = (dem_raw[valid] - np.float32(dem_stat["mean"])) / np.float32(dem_stat["applied_scale"])
    if not np.isfinite(lc).all() or not np.isfinite(lc_support).all() or not np.isfinite(dem).all() or not np.isfinite(dem_support).all():
        raise ValueError(f"non-finite raster tensor for {scene_id}")
    raster_tensors = {
        "landcover_class_fraction": lc,
        "landcover_valid_support": lc_support,
        "landcover_valid_mask": lc_mask,
        "dem_standardized_mean": dem,
        "dem_valid_support": dem_support,
        "dem_valid_mask": dem_mask,
    }

    center = [(float(raster_row["xmin"]) + float(raster_row["xmax"])) / 2, (float(raster_row["ymin"]) + float(raster_row["ymax"])) / 2]
    meta = {
        "meta_schema_version": "1.0.0",
        "scene_id": scene_id,
        "scene_footprint_id": stats_row["scene_footprint_id"],
        "split": split,
        "center_xy_5186": center,
        "crs": "EPSG:5186",
        "local_entity_ids": local_ids,
        "source_entity_ids": [row["source_entity_id"] for row in dictionary_rows],
        "entity_types": [row["entity_type"] for row in dictionary_rows],
        "empty_edge": expected_edges == 0,
        "counts": {"nodes": expected_nodes, "edges": expected_edges, "coordinates": len(coordinate_array)},
        "road_topology": {
            "road_local_entity_ids": [int(row["local_entity_id"]) for row in road_rows],
            "original_node_ids": [str(row["original_node_id"]) for row in ordered_nodes],
            "source_artifact": topology_source,
            "endpoint_order": ["F", "T"],
            "node_state_codes": {"INTERIOR": 0, "BOUNDARY": 1, "OUTSIDE": 2},
        },
        "building_observed_area_reference": {
            "source_column": "observed_area_m2",
            "dtype": "float64",
            "unit": "square_meter",
            "crs": "EPSG:5186",
            "building_local_entity_ids": [int(row["local_entity_id"]) for row in dictionary_rows if row["entity_type"] == "B"],
        },
    }
    tensors_by_member = {
        "entities.safetensors": entity_tensors,
        "geometry.safetensors": geometry_tensors,
        "edges.safetensors": edge_tensors,
        "topology.safetensors": topology_tensors,
        "rasters.safetensors": raster_tensors,
    }
    tolerance = float(config["tensor"]["float_tolerance"])
    payloads = {"meta.json": canonical_json_bytes(meta)}
    for name, tensors in tensors_by_member.items():
        payload = tensor_bytes(tensors)
        validate_tensor_roundtrip(payload, tensors, tolerance)
        payloads[name] = payload
    metrics = {
        "scene_id": scene_id,
        "split": split,
        "node_count": expected_nodes,
        "edge_count": expected_edges,
        "coordinate_count": len(coordinate_array),
        "empty_edge": expected_edges == 0,
        "member_bytes": sum(len(value) for value in payloads.values()),
    }
    return payloads, metrics


def add_tar_member(archive: tarfile.TarFile, name: str, payload: bytes, metadata: dict[str, Any]) -> tuple[int, int]:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mtime = int(metadata["mtime"])
    info.uid = int(metadata["uid"])
    info.gid = int(metadata["gid"])
    info.uname = metadata["uname"]
    info.gname = metadata["gname"]
    info.mode = int(metadata["mode"])
    header_offset = archive.fileobj.tell()
    archive.addfile(info, io.BytesIO(payload))
    return header_offset, archive.fileobj.tell() - header_offset


def write_parquet(rows: list[dict[str, Any]], path: Path, config: dict[str, Any]) -> None:
    table = pa.Table.from_pylist(rows)
    pq.write_table(
        table,
        path,
        compression=config["archive"]["parquet_compression"],
        row_group_size=int(config["archive"]["parquet_row_group_size"]),
        use_dictionary=False,
        write_statistics=True,
        data_page_version="1.0",
    )


def compare_directories(left: Path, right: Path) -> None:
    left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
    if left_files != right_files:
        raise FileExistsError("immutable output file set differs")
    for relative in left_files:
        if sha256_file(left / relative) != sha256_file(right / relative):
            raise FileExistsError(f"same branch ID has different immutable content: {relative}")


def build_branch(spec_path: Path, config_path: Path, schema_path: Path, output_dir: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    spec = read_json(spec_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if spec["plan_id"] != config["identity"]["serialization_plan_id"] or spec["serialization_dataset_id"] != config["identity"]["serialization_dataset_id"]:
        raise ValueError("I14/I15 scientific identity mismatch")
    if spec["spatial_dataset_id"] != config["identity"]["spatial_dataset_id"]:
        raise ValueError("I13/I15 spatial dataset mismatch")
    manifests = verify_source_contract(spec)
    scene_ids = list(spec["scene_ids"])
    split = spec["split"]
    branch_id = spec["branch_id"]

    dictionary = read_filtered(spec["accepted_artifacts"]["dictionary"]["path"], scene_ids)
    scene_stats = read_filtered(spec["accepted_artifacts"]["scene_statistics"]["path"], scene_ids)
    stats_by_scene = {row["scene_id"]: row for row in scene_stats}
    if set(stats_by_scene) != set(scene_ids) or len(stats_by_scene) != len(scene_stats):
        raise ValueError("scene statistics duplicate/missing scene")
    vocab_rows = pq.read_table(spec["accepted_artifacts"]["vocabulary"]["path"]).to_pylist()
    norm_rows = pq.read_table(spec["accepted_artifacts"]["normalization"]["path"]).to_pylist()
    vocab, missing = vocabulary_maps(vocab_rows)
    norm = normalization_maps(norm_rows)

    data: dict[str, dict[str, Any]] = {}
    used_source_records: list[dict[str, Any]] = []
    for observation_branch in sorted({stats_by_scene[scene_id]["branch_id"] for scene_id in scene_ids}):
        branch_scenes = [scene_id for scene_id in scene_ids if stats_by_scene[scene_id]["branch_id"] == observation_branch]
        stage_manifests = {stage: manifests[stage][observation_branch] for stage in manifests}
        paths = {
            "building": output_path(stage_manifests["vector"], "building_observed.parquet"),
            "road": output_path(stage_manifests["vector"], "road_observed.parquet"),
            "poi": output_path(stage_manifests["vector"], "poi_observed.parquet"),
            "object": output_path(stage_manifests["raster"], "object_raster_context.parquet"),
            "raster_index": output_path(stage_manifests["raster"], "scene_raster_index.parquet"),
            "relation": output_path(stage_manifests["relation"], "relation_edges.parquet"),
            "topology": output_path(stage_manifests["relation"], "road_topology.parquet"),
            "landcover": output_path(stage_manifests["raster"], "scene_landcover.zarr"),
            "dem": output_path(stage_manifests["raster"], "scene_dem.zarr"),
        }
        for stage_manifest in stage_manifests.values():
            for output in stage_manifest["outputs"]:
                if output["path"] in paths.values() and "sha256" in output:
                    verify_record(output, f"accepted source {Path(output['path']).name}")
                    used_source_records.append(output)
        rows = {name: read_filtered(path, branch_scenes) for name, path in paths.items() if name not in ("landcover", "dem")}
        raster_index = {row["scene_id"]: row for row in rows["raster_index"]}
        lc_group = zarr.open_group(paths["landcover"], mode="r")
        dem_group = zarr.open_group(paths["dem"], mode="r")
        for scene_id in branch_scenes:
            index = raster_index[scene_id]
            zarr_index = int(index["zarr_index"])
            data[scene_id] = {
                "vectors": {entity: [row for row in rows[entity] if row["scene_id"] == scene_id] for entity in ("building", "road", "poi")},
                "objects": [row for row in rows["object"] if row["scene_id"] == scene_id],
                "relations": [row for row in rows["relation"] if row["scene_id"] == scene_id],
                "topology": [row for row in rows["topology"] if row["scene_id"] == scene_id],
                "topology_source": stage_manifests["relation"]["inputs"]["road_topology"],
                "raster_index": index,
                "rasters": {
                    "landcover_class_fraction": lc_group["class_fraction"][zarr_index],
                    "landcover_valid_support": lc_group["valid_support_ratio"][zarr_index],
                    "landcover_valid_mask": lc_group["valid_mask"][zarr_index],
                    "dem_raw_mean": dem_group["raw_mean_m"][zarr_index],
                    "dem_valid_support": dem_group["valid_support_ratio"][zarr_index],
                    "dem_valid_mask": dem_group["valid_mask"][zarr_index],
                },
            }

    dictionary_by_scene = {scene_id: [row for row in dictionary if row["scene_id"] == scene_id] for scene_id in scene_ids}
    final_dir = output_dir.resolve() if output_dir else Path(spec["output"]["directory"]).resolve()
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=f".{branch_id}.staging-", dir=final_dir.parent))
    archive_path = stage_dir / f"scenes-{branch_id}.tar"
    index_path = stage_dir / f"scenes-{branch_id}.idx"
    scene_index_path = stage_dir / "scene_index.parquet"
    qc_path = stage_dir / "branch_qc.json"
    log_path = stage_dir / "branch_log.jsonl"
    manifest_path = stage_dir / "branch_manifest.json"
    scene_metrics: list[dict[str, Any]] = []
    archive_index: list[dict[str, Any]] = []
    actual_uncompressed = 0
    try:
        with tarfile.open(archive_path, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for scene_id in scene_ids:
                scene = data[scene_id]
                payloads, metrics = create_scene(
                    scene_id, split, stats_by_scene[scene_id], dictionary_by_scene[scene_id], scene["vectors"],
                    scene["objects"], scene["relations"], scene["topology"], scene["topology_source"],
                    scene["raster_index"], scene["rasters"],
                    vocab, missing, norm, config,
                )
                start = archive.fileobj.tell()
                members = []
                for suffix in MEMBER_SUFFIXES:
                    payload = payloads[suffix]
                    offset, length = add_tar_member(archive, f"{scene_id}.{suffix}", payload, config["archive"]["metadata"])
                    members.append({"name": f"{scene_id}.{suffix}", "offset": offset, "length": length, "payload_bytes": len(payload), "sha256": sha256_bytes(payload)})
                    actual_uncompressed += len(payload)
                archive_index.append({"scene_id": scene_id, "offset": start, "length": archive.fileobj.tell() - start, "members": members})
                scene_metrics.append(metrics)

        index_path.write_bytes(canonical_json_bytes({"index_schema_version": "1.0.0", "branch_id": branch_id, "scenes": archive_index}))
        index_rows = []
        for order, (scene_id, item, metrics) in enumerate(zip(scene_ids, archive_index, scene_metrics)):
            index_rows.append({
                "scene_order": order, "scene_id": scene_id, "split": split, "branch_id": branch_id,
                "sample_offset": item["offset"], "sample_length": item["length"],
                "node_count": metrics["node_count"], "edge_count": metrics["edge_count"],
                "coordinate_count": metrics["coordinate_count"], "empty_edge": metrics["empty_edge"],
            })
        write_parquet(index_rows, scene_index_path, config)

        expected = spec["totals"]
        totals = {
            "scene_count": len(scene_metrics),
            "node_count": sum(item["node_count"] for item in scene_metrics),
            "ordered_edge_count": sum(item["edge_count"] for item in scene_metrics),
            "coordinate_count": sum(item["coordinate_count"] for item in scene_metrics),
            "empty_edge_scene_count": sum(item["empty_edge"] for item in scene_metrics),
            "estimated_uncompressed_bytes": int(expected["estimated_uncompressed_bytes"]),
            "actual_uncompressed_bytes": actual_uncompressed,
            "archive_bytes": archive_path.stat().st_size,
        }
        for name in ("scene_count", "node_count", "ordered_edge_count", "coordinate_count"):
            if totals[name] != int(expected[name]):
                raise ValueError(f"branch total mismatch: {name}")

        with tarfile.open(archive_path, mode="r:") as archive:
            names = archive.getnames()
            validate_tar_member_names(names, scene_ids)
            for item in archive_index:
                for member in item["members"]:
                    payload = archive.extractfile(member["name"]).read()
                    if sha256_bytes(payload) != member["sha256"] or len(payload) != member["payload_bytes"]:
                        raise ValueError(f"tar round-trip checksum mismatch: {member['name']}")

        tensor_schema_hash = sha256_bytes(canonical_json_bytes(config["tensor"]))
        source_spec_record = file_record(spec_path)
        qc = {
            "qc_schema_version": "1.0.0", "status": "PASS", "branch_id": branch_id,
            "round_trip_scene_count": len(scene_ids), "error_count": 0,
            "missing_scene_count": 0, "extra_scene_count": 0, "duplicate_scene_count": 0,
            "split_mismatch_count": 0, "dangling_edge_count": 0, "category_error_count": 0,
            "normalization_error_count": 0, "raster_error_count": 0,
            "tensor_schema_hash": tensor_schema_hash, "totals": totals,
        }
        qc_path.write_bytes(canonical_json_bytes(qc))
        deterministic_log = {
            "event": "prototype_serialization_shard_complete", "status": "PASS", "branch_id": branch_id,
            "scene_count": len(scene_ids), "workers": 1, "threads": 1, "gpu": 0,
        }
        log_path.write_bytes(canonical_json_bytes(deterministic_log))
        outputs = [file_record(path, stage_dir) for path in (archive_path, index_path, scene_index_path, qc_path, log_path)]
        manifest = {
            "manifest_schema_version": "1.0.0", "status": "PASS", "plan_id": spec["plan_id"],
            "serialization_dataset_id": spec["serialization_dataset_id"], "spatial_dataset_id": spec["spatial_dataset_id"],
            "branch_id": branch_id, "split": split, "scene_ids": scene_ids, "totals": totals,
            "tensor_schema_hash": tensor_schema_hash, "tensor_contract_sha256": sha256_file(config_path),
            "tensor_manifest_schema_sha256": sha256_file(schema_path), "source_spec": source_spec_record,
            "scientific_identity": {
                "spatial_dataset_id": spec["spatial_dataset_id"],
                "serialization_plan_id": spec["plan_id"],
                "serialization_dataset_id": spec["serialization_dataset_id"],
                "i14_spec_sha256": source_spec_record["sha256"],
                "i14_scientific_identity": spec["scientific_identity"],
                "tensor_contract_sha256": sha256_file(config_path),
                "manifest_schema_sha256": sha256_file(schema_path),
                "implementation_sha256": sha256_file(Path(__file__).resolve()),
                "requirements_sha256": sha256_file(Path(__file__).resolve().parent / "requirements-serialization.txt"),
                "serialization_algorithm": config["serialization"],
            },
            "accepted_artifacts": spec["accepted_artifacts"], "upstream_datasets": spec["upstream_datasets"],
            "building_observed_area_reference_provenance": {
                "source_column": "observed_area_m2", "dtype": "float64", "unit": "square_meter", "crs": "EPSG:5186",
                "extraction_algorithm": "verified_building_observed_parquet_local_entity_join",
                "source_artifacts": sorted(
                    [record for record in used_source_records if Path(record["path"]).name == "building_observed.parquet"],
                    key=lambda record: record["path"],
                ),
            },
            "outputs": outputs, "qc": qc, "execution": {"controller": "controller_10", "workers": 1, "threads": 1, "gpu": 0},
        }
        jsonschema.validate(instance=manifest, schema=read_json(schema_path))
        manifest_path.write_bytes(canonical_json_bytes(manifest))

        runtime = {
            "event": "prototype_serialization_shard_runtime", "status": "PASS", "branch_id": branch_id,
            "scene_count": len(scene_ids), "elapsed_seconds": time.perf_counter() - started,
            "maximum_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            "read_bytes": None, "write_bytes": sum(path.stat().st_size for path in stage_dir.iterdir() if path.is_file()),
        }

        if final_dir.exists():
            compare_directories(stage_dir, final_dir)
            shutil.rmtree(stage_dir)
            reuse = True
        else:
            os.replace(stage_dir, final_dir)
            reuse = False
        final_files = sorted(str(path.resolve()) for path in final_dir.iterdir() if path.is_file())
        return {"status": "PASS", "branch_id": branch_id, "output_files": final_files, "immutable_reuse": reuse, "runtime": runtime}
    except Exception:
        shutil.rmtree(stage_dir, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build_branch(args.spec.resolve(), args.config.resolve(), args.schema.resolve(), args.output_dir)
    sys.stdout.buffer.write(canonical_json_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
