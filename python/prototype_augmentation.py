#!/usr/bin/env python3
"""Exact deterministic reference augmentation primitives for research target I19."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import torch
from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon, box
from shapely.strtree import STRtree


RELATION_BITS = {"SN": 1, "CNT": 2, "WIT": 4, "INT": 8, "CON": 16}
ENTITY_CODES = {"B": 0, "R": 1, "P": 2}


def geometry_bbox_center(geometry: Any) -> tuple[float, float]:
    xmin, ymin, xmax, ymax = geometry.bounds
    return (xmin + xmax) / 2.0, (ymin + ymax) / 2.0


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def logical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def keyed_rng(base_seed: int, epoch: int, scene_id: str, view_id: int, operation: str,
              local_entity_id: int = -1, attempt: int = -1) -> np.random.Generator:
    material = f"{base_seed}|{epoch}|{scene_id}|{view_id}|{operation}|{local_entity_id}|{attempt}".encode()
    seed = int.from_bytes(hashlib.sha256(material).digest()[:16], "big")
    return np.random.Generator(np.random.PCG64(seed))


def unstandardize(value: float, mean: float, scale: float, transform: str) -> float:
    raw = float(value) * float(scale) + float(mean)
    return math.expm1(raw) if transform == "log1p" else raw


def standardize(value: float, mean: float, scale: float, transform: str) -> float:
    transformed = math.log1p(max(0.0, float(value))) if transform == "log1p" else float(value)
    return (transformed - float(mean)) / float(scale)


def float32_ulp_distance(left: float | np.float32, right: float | np.float32) -> int:
    values = np.asarray([left, right], dtype=np.float32)
    if not np.isfinite(values).all():
        raise ValueError("ULP distance requires finite float32 values")
    bits = values.view(np.uint32)
    ordered = np.where(
        bits & np.uint32(0x80000000),
        np.bitwise_not(bits),
        bits | np.uint32(0x80000000),
    ).astype(np.uint64)
    return int(abs(int(ordered[0]) - int(ordered[1])))


def perturb_lane_value(original: int | None, missing: int, rng: np.random.Generator,
                       probability: float) -> tuple[int | None, int, bool, int]:
    if missing or original is None:
        return original, int(missing), False, 0
    if rng.random() >= probability:
        return int(original), 0, False, 0
    delta = -1 if rng.random() < 0.5 else 1
    return max(1, int(original) + delta), 0, True, delta


def road_removal_closure(primary_road_rows: Iterable[int], endpoint_nodes: np.ndarray,
                         node_degrees: np.ndarray) -> set[int]:
    """Propagate only through original degree-two nodes, with a visited set for cycles."""
    incident: dict[int, list[int]] = {}
    for road_row, endpoints in enumerate(endpoint_nodes.tolist()):
        for node in endpoints:
            incident.setdefault(int(node), []).append(road_row)
    removed = set(int(row) for row in primary_road_rows)
    queue = sorted(removed)
    cursor = 0
    while cursor < len(queue):
        road_row = queue[cursor]
        cursor += 1
        for node in endpoint_nodes[road_row].tolist():
            node = int(node)
            if int(node_degrees[node]) != 2:
                continue
            for neighbor in sorted(incident.get(node, [])):
                if neighbor not in removed:
                    removed.add(neighbor)
                    queue.append(neighbor)
    return removed


def _line_parts(geometry: Any) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    return []


def _polygon_parts(geometry: Any) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return []


def structure_signature(geometry: Any) -> tuple[str, int, tuple[int, ...]]:
    if isinstance(geometry, (Polygon, MultiPolygon)):
        parts = _polygon_parts(geometry)
        return "polygon", len(parts), tuple(len(part.interiors) for part in parts)
    if isinstance(geometry, (LineString, MultiLineString)):
        parts = _line_parts(geometry)
        return "line", len(parts), ()
    if isinstance(geometry, (Point, MultiPoint)):
        return "point", len(geometry.geoms) if isinstance(geometry, MultiPoint) else 1, ()
    return geometry.geom_type, 0, ()


def _jitter_coordinates(coords: list[tuple[float, float]], rng: np.random.Generator,
                        probability: float, maximum_m: float, boundary_tolerance: float,
                        preserve_ends: bool, closed: bool,
                        scene_center: tuple[float, float]) -> list[tuple[float, float]]:
    result = list(coords)
    unique_length = len(result) - 1 if closed and len(result) > 1 else len(result)
    for index in range(unique_length):
        x, y = result[index]
        cx, cy = scene_center
        boundary = min(abs(x - (cx - 250.0)), abs(x - (cx + 250.0)),
                       abs(y - (cy - 250.0)), abs(y - (cy + 250.0))) <= boundary_tolerance
        endpoint = preserve_ends and index in (0, unique_length - 1)
        if boundary or endpoint or rng.random() >= probability:
            continue
        angle = rng.uniform(0.0, 2.0 * math.pi)
        distance = rng.uniform(0.0, maximum_m)
        result[index] = (x + distance * math.cos(angle), y + distance * math.sin(angle))
    if closed and result:
        result[-1] = result[0]
    return result


def jitter_geometry(geometry: Any, rng: np.random.Generator, probability: float,
                    maximum_m: float, boundary_tolerance: float, road: bool,
                    scene_center: tuple[float, float] = (0.0, 0.0)) -> Any:
    if isinstance(geometry, LineString):
        return LineString(_jitter_coordinates(list(geometry.coords), rng, probability, maximum_m,
                                              boundary_tolerance, road, False, scene_center))
    if isinstance(geometry, MultiLineString):
        return MultiLineString([
            _jitter_coordinates(list(part.coords), rng, probability, maximum_m,
                                boundary_tolerance, road, False, scene_center) for part in geometry.geoms
        ])
    if isinstance(geometry, Polygon):
        exterior = _jitter_coordinates(list(geometry.exterior.coords), rng, probability, maximum_m,
                                       boundary_tolerance, False, True, scene_center)
        holes = [_jitter_coordinates(list(ring.coords), rng, probability, maximum_m,
                                     boundary_tolerance, False, True, scene_center) for ring in geometry.interiors]
        return Polygon(exterior, holes)
    if isinstance(geometry, MultiPolygon):
        return MultiPolygon([jitter_geometry(part, rng, probability, maximum_m, boundary_tolerance, False, scene_center)
                             for part in geometry.geoms])
    return geometry


def simplify_geometry(geometry: Any, tolerance: float, road: bool) -> Any:
    candidate = geometry.simplify(tolerance, preserve_topology=True)
    if road:
        originals = _line_parts(geometry)
        candidates = _line_parts(candidate)
        if len(originals) != len(candidates):
            return candidate
        rebuilt = []
        for original, simplified in zip(originals, candidates):
            coords = list(simplified.coords)
            if len(coords) >= 2:
                coords[0], coords[-1] = original.coords[0], original.coords[-1]
            rebuilt.append(LineString(coords))
        return rebuilt[0] if isinstance(geometry, LineString) else MultiLineString(rebuilt)
    return candidate


def unpack_geometries(sample: dict[str, Any]) -> list[Any]:
    reference = sample["scientific_reference"]
    coordinates = reference["coordinates_absolute_xy_5186"].cpu().numpy()
    if coordinates.dtype != np.float64:
        raise ValueError("scientific geometry coordinates must be absolute float64")
    types = reference["geometry_type"].cpu().numpy()
    entity_parts = reference["entity_part_offsets"].cpu().numpy()
    part_coords = reference["part_coordinate_offsets"].cpu().numpy()
    entity_rings = reference["entity_ring_offsets"].cpu().numpy()
    ring_components = reference["ring_component_index"].cpu().numpy()
    ring_starts = reference["ring_coordinate_start"].cpu().numpy()
    ring_ends = reference["ring_coordinate_end"].cpu().numpy()
    ring_holes = reference["ring_is_hole"].cpu().numpy()
    result: list[Any] = []
    for row in range(len(types)):
        part_start, part_end = int(entity_parts[row]), int(entity_parts[row + 1])
        parts = [coordinates[int(part_coords[p]):int(part_coords[p + 1])] for p in range(part_start, part_end)]
        code = int(types[row])
        if code in (0, 1):
            points = [Point(part[0]) for part in parts if len(part)]
            value = points[0] if code == 0 and points else MultiPoint(points)
        elif code in (2, 3):
            lines = [LineString(part) for part in parts if len(part) >= 2]
            value = lines[0] if code == 2 and lines else MultiLineString(lines)
        elif code in (4, 5):
            ring_start, ring_end = int(entity_rings[row]), int(entity_rings[row + 1])
            by_part: dict[int, list[tuple[np.ndarray, bool]]] = {}
            for ring in range(ring_start, ring_end):
                coords = coordinates[int(ring_starts[ring]):int(ring_ends[ring])]
                by_part.setdefault(int(ring_components[ring]), []).append((coords, bool(ring_holes[ring])))
            polygons = []
            for part in range(part_start, part_end):
                rings = by_part.get(part, [])
                shells = [coords for coords, hole in rings if not hole]
                holes = [coords for coords, hole in rings if hole]
                if len(shells) == 1:
                    polygons.append(Polygon(shells[0], holes))
            value = polygons[0] if code == 4 and polygons else MultiPolygon(polygons)
        else:
            raise ValueError(f"unsupported geometry type code: {code}")
        result.append(value)
    return result


def selected_host_relations(geometries: list[Any], entity_types: np.ndarray, retained: set[int],
                            source_entity_ids: list[Any],
                            local_entity_ids: list[int] | np.ndarray | None = None,
                            building_areas: np.ndarray | None = None) -> dict[str, set[tuple[int, int]]]:
    local_ids = list(range(len(geometries))) if local_entity_ids is None else [int(value) for value in local_entity_ids]
    buildings = [row for row in sorted(retained) if entity_types[row] == ENTITY_CODES["B"]]
    pois = [row for row in sorted(retained) if entity_types[row] == ENTITY_CODES["P"]]
    result = {"CNT": set(), "WIT": set()}
    if not buildings or not pois:
        return result
    building_geometries = [geometries[row] for row in buildings]
    tree = STRtree(building_geometries)
    for poi in pois:
        candidates = [
            buildings[int(index)] for index in tree.query(geometries[poi])
            if geometries[poi].within(building_geometries[int(index)])
        ]
        if not candidates:
            continue
        host = min(candidates, key=lambda building: (
            float(geometries[building].area if building_areas is None else building_areas[building]),
            source_entity_ids[building] is None,
            "" if source_entity_ids[building] is None else str(source_entity_ids[building]),
            local_ids[building],
        ))
        result["CNT"].add((host, poi))
        result["WIT"].add((poi, host))
    return result


def relation_sets(geometries: list[Any], entity_types: np.ndarray, retained: set[int],
                  endpoint_nodes: np.ndarray, endpoint_retained: np.ndarray,
                  road_entity_rows: np.ndarray, source_entity_ids: list[Any],
                  local_entity_ids: list[int] | np.ndarray | None = None,
                  building_areas: np.ndarray | None = None) -> dict[str, set[tuple[int, int]]]:
    buildings = [row for row in sorted(retained) if entity_types[row] == ENTITY_CODES["B"]]
    roads = [row for row in sorted(retained) if entity_types[row] == ENTITY_CODES["R"]]
    result = {name: set() for name in ("CNT", "WIT", "INT", "CON")}
    result.update(selected_host_relations(
        geometries, entity_types, retained, source_entity_ids, local_entity_ids, building_areas
    ))
    spatial_rows = buildings + roads
    if spatial_rows:
        spatial_geometries = [geometries[row] for row in spatial_rows]
        tree = STRtree(spatial_geometries)
        for source in spatial_rows:
            for index in tree.query(geometries[source], predicate="intersects"):
                destination = spatial_rows[int(index)]
                if source != destination:
                    result["INT"].add((source, destination))
    entity_to_road = {int(entity): road for road, entity in enumerate(road_entity_rows.tolist())}
    incident: dict[int, list[int]] = {}
    for entity in roads:
        road = entity_to_road[entity]
        for endpoint_order, node in enumerate(endpoint_nodes[road].tolist()):
            if int(endpoint_retained[road, endpoint_order]) == 1:
                incident.setdefault(int(node), []).append(entity)
    for connected in incident.values():
        for source in connected:
            for destination in connected:
                if source != destination:
                    result["CON"].add((source, destination))
    return result


def fixed_relation_sets(sample: dict[str, Any], retained: set[int]) -> dict[str, set[tuple[int, int]]]:
    result = {name: set() for name in ("CNT", "WIT", "INT", "CON")}
    edge_index = sample["edges"]["edge_index"].cpu().numpy()
    masks = sample["edges"]["relation_mask"].cpu().numpy()
    for edge, mask in zip(edge_index.T.tolist(), masks.tolist()):
        source, destination = map(int, edge)
        if source not in retained or destination not in retained:
            continue
        for name in result:
            if int(mask) & RELATION_BITS[name]:
                result[name].add((source, destination))
    return result


def no_op_round_trip_scene(sample: dict[str, Any], resources: AugmentationResources) -> dict[str, Any]:
    entities = sample["entities"]
    entity_types = entities["entity_type"].cpu().numpy()
    local_ids = entities["local_entity_id"].cpu().numpy()
    entity_count = len(local_ids)
    if not np.array_equal(local_ids, np.arange(entity_count, dtype=np.int64)):
        raise ValueError(f"entity order mismatch: {sample['scene_id']}")
    geometries = unpack_geometries(sample)
    retained = set(range(entity_count))
    invalid_geometry = sum(int(geometry.is_empty or not geometry.is_valid) for geometry in geometries)
    reference = sample["scientific_reference"]
    centers = reference["reference_center_absolute_xy_5186"].cpu().numpy()
    center_errors = [math.hypot(geometry_bbox_center(geometry)[0] - centers[row, 0],
                                geometry_bbox_center(geometry)[1] - centers[row, 1])
                     for row, geometry in enumerate(geometries)]
    absolute = reference["coordinates_absolute_xy_5186"].cpu().numpy()
    model = sample["geometry"]["coordinates_xy_m"].cpu().numpy()
    offsets = reference["entity_coordinate_offsets"].cpu().numpy()
    reconstructed_model = np.empty_like(model)
    for row in range(entity_count):
        start, end = int(offsets[row]), int(offsets[row + 1])
        reconstructed_model[start:end] = np.asarray(
            (absolute[start:end] - centers[row]) / 500.0, dtype=np.float32
        ) * np.float32(500.0)
    coordinate_mismatch = int(not np.array_equal(reconstructed_model, model))

    area_stat = resources.normalizations["building_observed_area_m2"]
    building_values = entities["building_numerical"].cpu().numpy()
    building_missing = entities["building_missing"].cpu().numpy()
    area_bit_exact = area_non_bit_exact = 0
    area_max_ulp = 0
    area_max_absolute_difference = 0.0
    area_affected = []
    area_differences = []
    area_references = reference["building_observed_area_m2_reference"].cpu().numpy()
    reference_area_alignment_mismatch = int(len(area_references) != len(entities["building_row_index"]))
    building_areas = np.full(entity_count, np.nan, dtype=np.float64)
    for offset, row in enumerate(entities["building_row_index"].tolist()):
        if int(building_missing[offset, 0]):
            continue
        area_reference = float(area_references[offset])
        area_geometry = float(geometries[row].area)
        building_areas[row] = area_reference
        expected = np.float32(standardize(area_reference, area_stat["mean"],
                                          area_stat["applied_scale"], area_stat["transform"]))
        stored = np.float32(building_values[offset, 0])
        distance = float32_ulp_distance(expected, stored)
        difference = abs(float(expected) - float(stored))
        area_bit_exact += int(distance == 0)
        area_non_bit_exact += int(distance != 0)
        area_max_ulp = max(area_max_ulp, distance)
        area_max_absolute_difference = max(area_max_absolute_difference, difference)
        if distance:
            area_affected.append({
                "local_entity_id": int(row), "source_entity_id": sample["meta"]["source_entity_ids"][row],
                "area_reference_float64": area_reference, "area_geometry_float64": area_geometry,
                "expected_float32": float(expected),
                "stored_float32": float(stored), "ulp_distance": distance,
                "absolute_standardized_difference": difference,
            })
        absolute_difference = abs(area_reference - area_geometry)
        area_differences.append({
            "local_entity_id": int(row), "source_entity_id": sample["meta"]["source_entity_ids"][row],
            "area_reference_float64": area_reference, "area_geometry_float64": area_geometry,
            "absolute_difference": absolute_difference,
            "relative_difference": absolute_difference / area_reference,
            "exact_equal": area_reference == area_geometry,
        })

    endpoint_nodes = sample["topology"]["road_endpoint_node_index"].cpu().numpy()
    endpoint_retained = sample["topology"]["road_endpoint_retained"].cpu().numpy()
    road_rows = entities["road_row_index"].cpu().numpy()
    expected_relations = fixed_relation_sets(sample, retained)
    observed_relations = relation_sets(geometries, entity_types, retained, endpoint_nodes,
                                       endpoint_retained, road_rows, sample["meta"]["source_entity_ids"], local_ids,
                                       building_areas)
    geometry_area_relations = relation_sets(
        geometries, entity_types, retained, endpoint_nodes, endpoint_retained, road_rows,
        sample["meta"]["source_entity_ids"], local_ids,
    )
    selected_host_area_affected = len(observed_relations["CNT"] ^ geometry_area_relations["CNT"]) // 2
    relation_counts = {}
    for name in expected_relations:
        relation_counts[f"missing_{name}"] = len(expected_relations[name] - observed_relations[name])
        relation_counts[f"extra_{name}"] = len(observed_relations[name] - expected_relations[name])

    edge_pairs = [tuple(map(int, edge)) for edge in sample["edges"]["edge_index"].T.tolist()]
    dangling = sum(int(source < 0 or destination < 0 or source >= entity_count or destination >= entity_count)
                   for source, destination in edge_pairs)
    self_relations = sum(int(source == destination) for source, destination in edge_pairs)
    duplicate_relations = len(edge_pairs) - len(set(edge_pairs))
    failures = (sum(relation_counts.values()) + dangling + self_relations + duplicate_relations +
                invalid_geometry + coordinate_mismatch + area_non_bit_exact +
                sum(int(error > 1e-8) for error in center_errors))
    return {
        "scene_id": sample["scene_id"], **relation_counts,
        "dangling_relation": dangling, "self_relation": self_relations,
        "duplicate_relation": duplicate_relations, "invalid_geometry": invalid_geometry,
        "coordinate_offset_mismatch": coordinate_mismatch,
        "reference_area_alignment_mismatch": reference_area_alignment_mismatch,
        "building_area_bit_exact": area_bit_exact,
        "building_area_non_bit_exact": area_non_bit_exact,
        "building_area_maximum_ulp": area_max_ulp,
        "building_area_maximum_absolute_standardized_difference": area_max_absolute_difference,
        "building_area_affected_json": json.dumps(area_affected, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "building_area_cross_runtime_json": json.dumps(area_differences, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "selected_host_area_affected_count": selected_host_area_affected,
        "selected_hosts_json": json.dumps(sorted([list(pair) for pair in observed_relations["CNT"]]), separators=(",", ":")),
        "reference_center_mismatch": sum(int(error > 1e-8) for error in center_errors),
        "maximum_center_error_m": max(center_errors, default=0.0),
        "status": "PASS" if failures == 0 else "FAIL",
    }


def candidate_relations_match(row: int, geometries: list[Any], entity_types: np.ndarray,
                              retained: set[int], fixed: dict[str, set[tuple[int, int]]],
                              source_entity_ids: list[Any], local_entity_ids: list[int] | np.ndarray,
                              building_areas: np.ndarray) -> bool:
    """Compare every invariant relation involving one candidate entity."""
    if entity_types[row] == ENTITY_CODES["B"]:
        spatial = [other for other in retained if other != row and entity_types[other] in (ENTITY_CODES["B"], ENTITY_CODES["R"])]
        containment = selected_host_relations(
            geometries, entity_types, retained, source_entity_ids, local_entity_ids, building_areas
        )
        cnt = {pair for pair in containment["CNT"] if row in pair}
        wit = {pair for pair in containment["WIT"] if row in pair}
        intersections = {(row, other) for other in spatial if geometries[row].intersects(geometries[other])}
        intersections |= {(destination, source) for source, destination in intersections}
        expected_int = {pair for pair in fixed["INT"] if row in pair}
        return cnt == {pair for pair in fixed["CNT"] if row in pair} and \
            wit == {pair for pair in fixed["WIT"] if row in pair} and intersections == expected_int
    if entity_types[row] == ENTITY_CODES["R"]:
        spatial = [other for other in retained if other != row and entity_types[other] in (ENTITY_CODES["B"], ENTITY_CODES["R"])]
        intersections = {(other, row) for other in spatial if geometries[other].intersects(geometries[row])}
        intersections |= {(destination, source) for source, destination in intersections}
        return intersections == {pair for pair in fixed["INT"] if row in pair}
    return True


def regenerate_sn(geometries: list[Any], retained: set[int], distance_m: float = 100.0,
                  top_k: int = 16) -> set[tuple[int, int]]:
    rows = sorted(retained)
    if not rows:
        return set()
    tree = STRtree([geometries[row] for row in rows])
    directed: set[tuple[int, int]] = set()
    for position, source in enumerate(rows):
        candidates = []
        for index in tree.query(geometries[source], predicate="dwithin", distance=distance_m):
            destination = rows[int(index)]
            if destination == source:
                continue
            distance = float(geometries[source].distance(geometries[destination]))
            if distance <= distance_m:
                candidates.append((distance, destination))
        for _, destination in sorted(candidates, key=lambda item: (item[0], item[1]))[:top_k]:
            directed.add((source, destination))
    return directed | {(destination, source) for source, destination in directed}


def recompute_object_context(geometries: list[Any], retained: set[int], landcover: np.ndarray,
                             lc_support: np.ndarray, dem: np.ndarray, dem_support: np.ndarray,
                             scene_center: tuple[float, float]) -> np.ndarray:
    """Reference cell-center zonal recomputation in the closed scene footprint."""
    output = np.zeros((len(geometries), 26), dtype=np.float32)
    for row in sorted(retained):
        geometry = geometries[row]
        absolute_center = geometry_bbox_center(geometry)
        cx = absolute_center[0] - scene_center[0]
        cy = absolute_center[1] - scene_center[1]
        lc_col = int(np.clip(math.floor((cx + 250.0) / 5.0), 0, 99))
        lc_row = int(np.clip(math.floor((250.0 - cy) / 5.0), 0, 99))
        support = float(lc_support[lc_row, lc_col])
        if support > 0:
            values = landcover[:, lc_row, lc_col]
            total = float(values.sum())
            if total > 0:
                output[row, :22] = values / total
        output[row, 22] = support
        dem_col = int(np.clip(math.floor((cx + 250.0) / (500.0 / 17.0)), 0, 16))
        dem_row = int(np.clip(math.floor((250.0 - cy) / (500.0 / 17.0)), 0, 16))
        dem_value = float(dem[dem_row, dem_col])
        output[row, 23] = dem_value if dem_support[dem_row, dem_col] > 0 else 0.0
        output[row, 24] = 0.0
        output[row, 25] = float(dem_support[dem_row, dem_col])
    return output


@dataclass
class AugmentationResources:
    normalizations: dict[str, dict[str, Any]]
    mask_indices: dict[str, int]
    missing_indices: dict[str, int]


def augment_scene(sample: dict[str, Any], config: dict[str, Any], resources: AugmentationResources,
                  thresholds: dict[int, float], epoch: int, view_id: int,
                  intensity: float = 1.0) -> dict[str, Any]:
    scene_id = sample["scene_id"]
    base_seed = int(config["rng"]["base_seed"])
    entities = sample["entities"]
    entity_types = entities["entity_type"].cpu().numpy()
    n = len(entity_types)
    geometries = unpack_geometries(sample)
    original_geometries = list(geometries)
    all_rows = set(range(n))
    road_entity_rows = entities["road_row_index"].cpu().numpy()
    endpoint_nodes = sample["topology"]["road_endpoint_node_index"].cpu().numpy()
    endpoint_retained = sample["topology"]["road_endpoint_retained"].cpu().numpy()
    node_degrees = sample["topology"]["node_incident_road_count"].cpu().numpy()
    scene_center = tuple(float(value) for value in sample["meta"]["center_xy_5186"])
    building_area_references = sample["scientific_reference"]["building_observed_area_m2_reference"].cpu().numpy()
    building_areas = np.full(n, np.nan, dtype=np.float64)
    for offset, row in enumerate(entities["building_row_index"].tolist()):
        if not int(entities["building_missing"][offset, 0]):
            building_areas[row] = float(building_area_references[offset])

    removal_rng = keyed_rng(base_seed, epoch, scene_id, view_id, "entity_removal")
    fraction = removal_rng.uniform(0.0, min(1.0, intensity * float(config["entity_removal"]["maximum_fraction"])))
    primary_count = min(n, int(math.floor(fraction * n)))
    primary = set(removal_rng.choice(np.arange(n), size=primary_count, replace=False).tolist()) if primary_count else set()
    removed = set(primary)
    original_edge_index = sample["edges"]["edge_index"].cpu().numpy()
    original_masks = sample["edges"]["relation_mask"].cpu().numpy()
    for edge, mask in zip(original_edge_index.T.tolist(), original_masks.tolist()):
        source, destination = map(int, edge)
        if source in removed and entity_types[source] == ENTITY_CODES["B"] and int(mask) & RELATION_BITS["CNT"]:
            removed.add(destination)
    entity_to_road = {int(entity): road for road, entity in enumerate(road_entity_rows.tolist())}
    primary_road_offsets = [entity_to_road[row] for row in primary if row in entity_to_road]
    road_closure = road_removal_closure(primary_road_offsets, endpoint_nodes, node_degrees)
    removed.update(int(road_entity_rows[row]) for row in road_closure)
    retained = all_rows - removed

    fixed_relations = {name: set() for name in ("CNT", "WIT", "INT", "CON")}
    for edge, mask in zip(original_edge_index.T.tolist(), original_masks.tolist()):
        source, destination = map(int, edge)
        if source not in retained or destination not in retained:
            continue
        for name in fixed_relations:
            if int(mask) & RELATION_BITS[name]:
                fixed_relations[name].add((source, destination))
    retries = rejections = fallbacks = accepted_geometry = 0
    geometry_changed_rows: set[int] = set()
    boundary = box(scene_center[0] - 250.0, scene_center[1] - 250.0,
                   scene_center[0] + 250.0, scene_center[1] + 250.0)
    for row in sorted(retained):
        if entity_types[row] not in (ENTITY_CODES["B"], ENTITY_CODES["R"]):
            continue
        original = geometries[row]
        vertex_count = len(original_geometries[row].wkb)  # stable fallback complexity proxy
        coordinate_count = int(sample["geometry"]["entity_coordinate_offsets"][row + 1] - sample["geometry"]["entity_coordinate_offsets"][row])
        simplify = coordinate_count > thresholds[int(entity_types[row])]
        accepted = False
        for attempt in range(int(config["geometry"]["maximum_attempts"])):
            retries += 1
            rng = keyed_rng(base_seed, epoch, scene_id, view_id, "geometry", row, attempt)
            if simplify:
                maximum = intensity * float(config["geometry"]["simplification_tolerance_m"]["maximum"])
                candidate = simplify_geometry(original, rng.uniform(0.0, maximum), entity_types[row] == ENTITY_CODES["R"])
            else:
                probability = min(1.0, intensity * float(config["geometry"]["vertex_jitter"]["probability"]))
                maximum = intensity * float(config["geometry"]["vertex_jitter"]["displacement_m"]["maximum"])
                candidate = jitter_geometry(original, rng, probability, maximum,
                                            float(config["geometry"]["scene_boundary_tolerance_m"]),
                                            entity_types[row] == ENTITY_CODES["R"], scene_center)
            valid = (not candidate.is_empty and candidate.is_valid and boundary.covers(candidate)
                     and structure_signature(candidate) == structure_signature(original))
            if valid:
                geometries[row] = candidate
                if entity_types[row] == ENTITY_CODES["B"]:
                    building_areas[row] = float(candidate.area) if candidate.wkb != original.wkb else float(
                        building_area_references[entities["building_row_index"].tolist().index(row)]
                    )
                valid = candidate_relations_match(
                    row, geometries, entity_types, retained, fixed_relations,
                    sample["meta"]["source_entity_ids"], entities["local_entity_id"].tolist(), building_areas,
                )
            if valid:
                accepted = True; accepted_geometry += 1
                if candidate.wkb != original.wkb:
                    geometry_changed_rows.add(row)
                break
            geometries[row] = original
            if entity_types[row] == ENTITY_CODES["B"]:
                building_areas[row] = float(building_area_references[entities["building_row_index"].tolist().index(row)])
            rejections += 1
        if not accepted:
            geometries[row] = original
            if entity_types[row] == ENTITY_CODES["B"]:
                building_areas[row] = float(building_area_references[entities["building_row_index"].tolist().index(row)])
            fallbacks += 1

    # Geometry-derived Building values retain original missingness and source allocation ratio.
    building_values = entities["building_numerical"].cpu().numpy().copy()
    building_missing = entities["building_missing"].cpu().numpy().copy()
    area_stat = resources.normalizations["building_observed_area_m2"]
    gfa_stat = resources.normalizations["building_observed_gross_floor_area_m2"]
    building_qc = []
    building_reference_preserved = building_geometry_updated = 0
    for offset, row in enumerate(entities["building_row_index"].tolist()):
        if row not in retained:
            continue
        original_area = float(building_area_references[offset])
        new_area = float(building_areas[row])
        building_values[offset, 0] = standardize(new_area, area_stat["mean"], area_stat["applied_scale"], area_stat["transform"])
        if not int(building_missing[offset, 1]):
            original_gfa = unstandardize(building_values[offset, 1], gfa_stat["mean"], gfa_stat["applied_scale"], gfa_stat["transform"])
            ratio = original_gfa / original_area if original_area > 0 else 0.0
            new_gfa = new_area * ratio
            building_values[offset, 1] = standardize(new_gfa, gfa_stat["mean"], gfa_stat["applied_scale"], gfa_stat["transform"])
        geometry_changed = geometries[row].wkb != original_geometries[row].wkb
        building_geometry_updated += int(geometry_changed)
        building_reference_preserved += int(not geometry_changed and new_area == float(building_area_references[offset]))
        building_qc.append(0.0 if not geometry_changed else abs(new_area - geometries[row].area))

    lane_values = entities["road_numerical"].cpu().numpy().copy()
    lane_missing = entities["road_missing"].cpu().numpy().copy()
    lane_stat = resources.normalizations["road_lanes"]
    lane_events = []
    p_lane = min(1.0, intensity * float(config["attributes"]["road_lanes"]["probability"]))
    for road_offset, row in enumerate(road_entity_rows.tolist()):
        if row not in retained:
            continue
        missing = int(lane_missing[road_offset, 0])
        original = None if missing else int(round(unstandardize(lane_values[road_offset, 0], lane_stat["mean"], lane_stat["applied_scale"], lane_stat["transform"])))
        rng = keyed_rng(base_seed, epoch, scene_id, view_id, "road_lane", int(row))
        augmented, _, selected, delta = perturb_lane_value(original, missing, rng, p_lane)
        if augmented is not None:
            lane_values[road_offset, 0] = standardize(augmented, lane_stat["mean"], lane_stat["applied_scale"], lane_stat["transform"])
        lane_events.append({"row": int(row), "original": original, "augmented": augmented,
                            "selected": selected, "delta": delta, "missing": bool(missing)})

    categories = {name: entities[name].cpu().numpy().copy() for name in ("building_category", "road_category", "poi_category")}
    attributes = {"building_category": ["A9", "A11"], "road_category": ["ROAD_RANK", "ROAD_TYPE"],
                  "poi_category": [f"CLASS_L{i}" for i in range(1, 7)]}
    type_rows = {"building_category": entities["building_row_index"].tolist(),
                 "road_category": entities["road_row_index"].tolist(), "poi_category": entities["poi_row_index"].tolist()}
    mask_probability = min(1.0, intensity * float(config["categorical"]["mask_probability"]))
    for group, values in categories.items():
        for offset, row in enumerate(type_rows[group]):
            if row not in retained:
                continue
            for column, attribute in enumerate(attributes[group]):
                if int(values[offset, column]) == resources.missing_indices[attribute]:
                    continue
                rng = keyed_rng(base_seed, epoch, scene_id, view_id, f"categorical_{attribute}", int(row))
                if rng.random() < mask_probability:
                    values[offset, column] = resources.mask_indices[attribute]
    # POI replacement uses another observed hierarchy with the same retained prefix.
    replacement_probability = min(1.0, intensity * float(config["categorical"]["poi"]["replacement_probability"]))
    original_poi = entities["poi_category"].cpu().numpy()
    for offset, row in enumerate(type_rows["poi_category"]):
        if row not in retained:
            continue
        rng = keyed_rng(base_seed, epoch, scene_id, view_id, "poi_replacement", int(row))
        if rng.random() >= replacement_probability:
            continue
        level = int(config["categorical"]["poi"]["earliest_replacement_level"]) - 1
        candidates = [candidate for candidate in range(len(original_poi))
                      if candidate != offset and np.array_equal(original_poi[candidate, :level], original_poi[offset, :level])]
        if candidates:
            replacement = original_poi[int(candidates[int(rng.integers(len(candidates)))])]
            for column in range(level, 6):
                if original_poi[offset, column] != resources.missing_indices[f"CLASS_L{column + 1}"]:
                    categories["poi_category"][offset, column] = replacement[column]

    rasters = {key: value.cpu().numpy().copy() for key, value in sample["rasters"].items()}
    valid_lc = np.argwhere(rasters["landcover_valid_mask"] == 1)
    lc_count = int(math.floor(min(1.0, intensity * float(config["raster"]["landcover"]["valid_cell_mask_fraction"])) * len(valid_lc)))
    if lc_count:
        rng = keyed_rng(base_seed, epoch, scene_id, view_id, "landcover")
        selected = valid_lc[rng.choice(len(valid_lc), size=lc_count, replace=False)]
        for row, column in selected:
            rasters["landcover_class_fraction"][:, row, column] = 0.0
            rasters["landcover_valid_support"][row, column] = 0.0
    dem_stat = resources.normalizations["scene_dem_mean_m"]
    valid_dem = rasters["dem_valid_mask"] == 1
    rng = keyed_rng(base_seed, epoch, scene_id, view_id, "dem")
    sigma_standardized = intensity * float(config["raster"]["dem"]["valid_cell_gaussian_sd_m"]) / float(dem_stat["applied_scale"])
    rasters["dem_standardized_mean"][valid_dem] += rng.normal(0.0, sigma_standardized, int(valid_dem.sum())).astype(np.float32)
    object_context = recompute_object_context(geometries, retained, rasters["landcover_class_fraction"],
                                              rasters["landcover_valid_support"], rasters["dem_standardized_mean"],
                                              rasters["dem_valid_support"], scene_center)
    final_relations = relation_sets(
        geometries, entity_types, retained, endpoint_nodes, endpoint_retained,
        road_entity_rows, sample["meta"]["source_entity_ids"], entities["local_entity_id"].tolist(), building_areas,
    )
    sn = regenerate_sn(geometries, retained,
                       float(config["relations"]["SN"]["distance_m"]),
                       int(config["relations"]["SN"]["per_source_top_k"]))
    relative = entities["relative_position_m"].cpu().numpy().copy()
    for row in retained:
        center = geometry_bbox_center(geometries[row])
        relative[row] = [center[0] - scene_center[0], center[1] - scene_center[1]]

    result = {
        "scene_id": scene_id, "view_id": int(view_id), "retained": sorted(retained), "removed": sorted(removed),
        "primary_removed": sorted(primary), "road_propagated": sorted(int(road_entity_rows[row]) for row in road_closure),
        "geometry_wkb": {str(row): geometries[row].wkb_hex for row in sorted(retained)},
        "relative_position": relative.round(6).tolist(), "building_numerical": building_values.round(7).tolist(),
        "building_missing": building_missing.tolist(), "road_numerical": lane_values.round(7).tolist(),
        "road_missing": lane_missing.tolist(), "lane_events": lane_events,
        "categories": {key: value.tolist() for key, value in categories.items()},
        "relations": {key: sorted([list(pair) for pair in value]) for key, value in {**final_relations, "SN": sn}.items()},
        "object_context_digest": hashlib.sha256(object_context.tobytes()).hexdigest(),
        "raster_digest": logical_digest({key: hashlib.sha256(value.tobytes()).hexdigest() for key, value in rasters.items()}),
        "statistics": {"retries": retries, "rejections": rejections, "fallbacks": fallbacks,
                       "accepted_geometry": accepted_geometry, "geometry_changed": len(geometry_changed_rows),
                       "building_reference_preserved": building_reference_preserved,
                       "building_geometry_updated": building_geometry_updated,
                       "building_area_max_error": max(building_qc, default=0.0)},
        "invariants": {"CNT_WIT_INT_CON": final_relations == fixed_relations,
                       "landcover_nodata_unchanged": bool(np.array_equal(sample["rasters"]["landcover_valid_mask"].cpu().numpy(), rasters["landcover_valid_mask"])),
                       "dem_nodata_unchanged": bool(np.array_equal(sample["rasters"]["dem_valid_mask"].cpu().numpy(), rasters["dem_valid_mask"]))},
    }
    result["content_digests"] = {
        "geometry_wkb": logical_digest(result["geometry_wkb"]),
        "relative_position_float32": hashlib.sha256(relative.tobytes()).hexdigest(),
        "building_numerical_float32": hashlib.sha256(building_values.tobytes()).hexdigest(),
        "building_missing_uint8": hashlib.sha256(building_missing.tobytes()).hexdigest(),
        "road_numerical_float32": hashlib.sha256(lane_values.tobytes()).hexdigest(),
        "road_missing_uint8": hashlib.sha256(lane_missing.tobytes()).hexdigest(),
        "categories": logical_digest({key: hashlib.sha256(value.tobytes()).hexdigest() for key, value in categories.items()}),
        "relations": logical_digest(result["relations"]),
        "object_context_float32": hashlib.sha256(object_context.tobytes()).hexdigest(),
        "rasters": result["raster_digest"],
    }
    result["logical_digest"] = logical_digest(result)
    return result


def cuda_reference_check() -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("I19 requires a single CUDA GPU correctness check")
    torch.cuda.reset_peak_memory_stats()
    cpu = torch.tensor([1.0, 2.0, 3.0], dtype=torch.float32)
    gpu = cpu.cuda()
    transformed = torch.clamp(torch.round(gpu + torch.tensor([-1.0, 1.0, -1.0], device=gpu.device)), min=1)
    expected = torch.tensor([1.0, 3.0, 2.0])
    if not torch.equal(transformed.cpu(), expected):
        raise RuntimeError("CPU/CUDA discrete lane reference mismatch")
    noise = torch.zeros((17, 17), dtype=torch.float32, device=gpu.device)
    support = torch.ones_like(noise, dtype=torch.bool)
    output = torch.where(support, noise + 1.0, noise)
    if not torch.isfinite(output).all():
        raise RuntimeError("CUDA raster reference is non-finite")
    torch.cuda.synchronize()
    return {"status": "PASS", "device": torch.cuda.get_device_name(),
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
            "peak_reserved_bytes": int(torch.cuda.max_memory_reserved())}
