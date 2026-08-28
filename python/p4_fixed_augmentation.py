"""Deterministic P4 fixed augmentation bank kernel and delta-cache writer."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import tarfile
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
import yaml
import zarr
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.strtree import STRtree

from p4_deterministic_rng import (
    base_digest, removal_count, sample_without_replacement, standard_normal,
    uniform_binary64, uniform_integer,
)

RELATIONS = ("SN", "CNT", "WIT", "INT", "CON")
BITS = {"SN": 1, "CNT": 2, "WIT": 4, "INT": 8, "CON": 16}
THREAD_ENV = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GDAL_NUM_THREADS", "ARROW_NUM_THREADS",
)


def _fields(common: list[tuple[str, pa.DataType]], extra: list[tuple[str, pa.DataType]]) -> pa.Schema:
    return pa.schema(common + extra)


IDENTITY_FIELDS = [("candidate_id", pa.string()), ("scene_id", pa.string()),
                   ("profile_id", pa.string()), ("master_view_id", pa.int16())]
PARQUET_SCHEMAS = {
    "candidates": _fields([], [
        ("candidate_id", pa.string()), ("scene_id", pa.string()), ("profile_id", pa.string()), ("master_view_id", pa.int16()),
        ("sampled_removal_fraction", pa.float64()), ("primary_removal_count", pa.int64()), ("direct_removed_count", pa.int64()),
        ("cascade_removed_count", pa.int64()), ("absorbed_donor_count", pa.int64()), ("retained_entity_count", pa.int64()),
        ("geometry_entity_count", pa.int64()), ("geometry_override_count", pa.int64()), ("geometry_fallback_count", pa.int64()),
        ("attribute_override_count", pa.int64()), ("landcover_mask_count", pa.int64()), ("dem_noise_count", pa.int64()),
        ("landcover_mask_digest", pa.string()), ("landcover_component_count", pa.int64()),
        ("landcover_initial_seed_count", pa.int64()), ("landcover_reseed_count", pa.int64()),
        ("landcover_maximum_active_fronts", pa.int64()),
        ("sn_added_count", pa.int64()), ("sn_removed_count", pa.int64()), ("invariant_relation_hash", pa.string()),
        ("invariant_counts_json", pa.string()), ("relation_counts_json", pa.string()), ("attempt_histogram_json", pa.string()),
        ("operation_order_json", pa.string()), ("operation_seeds_json", pa.string()), ("status", pa.string()),
    ]),
    "removals": _fields(IDENTITY_FIELDS, [("local_entity_id", pa.int64()), ("removal_role", pa.string())]),
    "geometry": _fields(IDENTITY_FIELDS, [
        ("local_entity_id", pa.int64()), ("geometry_wkb", pa.binary()), ("geometry_dtype", pa.string()),
        ("center_x", pa.float64()), ("center_y", pa.float64()), ("relative_x", pa.float64()), ("relative_y", pa.float64()),
        ("xmin", pa.float64()), ("ymin", pa.float64()), ("xmax", pa.float64()), ("ymax", pa.float64()),
        ("area_m2", pa.float64()), ("length_m", pa.float64()), ("receiver_road_id", pa.string()),
        ("geometry_operation", pa.string()), ("accepted_attempt", pa.int16()), ("accepted_attempt_seed", pa.string()),
        ("sampled_simplification_tolerance_m", pa.float64()), ("jitter_selected_vertex_count", pa.int64()),
        ("maximum_vertex_displacement_m", pa.float64()),
        ("attempts_json", pa.string()), ("fallback", pa.bool_()), ("changed_from_post_absorption", pa.bool_()),
        ("observed_area_m2", pa.float64()), ("observed_gross_floor_area_m2", pa.float64()),
    ]),
    "fallbacks": _fields(IDENTITY_FIELDS, [("local_entity_id", pa.int64()), ("attempt_count", pa.int16()),
                                             ("attempts_json", pa.string()), ("fallback", pa.bool_())]),
    "attributes": _fields(IDENTITY_FIELDS, [("local_entity_id", pa.int64()), ("field", pa.string()),
                                              ("original", pa.string()), ("augmented", pa.string()), ("action", pa.string())]),
    "raster": _fields(IDENTITY_FIELDS, [("modality", pa.string()), ("flat_index", pa.int64()), ("value", pa.float64())]),
    "landcover_mask_provenance": _fields(IDENTITY_FIELDS, [
        ("algorithm", pa.string()), ("valid_cell_count", pa.int64()), ("target_mask_count", pa.int64()),
        ("initial_seeds_json", pa.string()), ("reseeds_json", pa.string()),
        ("selected_order_sha256", pa.string()), ("frontier_order_sha256", pa.string()),
        ("maximum_concurrent_fronts", pa.int64()), ("realized_component_count", pa.int64()),
    ]),
    "context": _fields(IDENTITY_FIELDS, [("local_entity_id", pa.int64()), ("support_measure_unit", pa.string()),
        ("lc_total_support", pa.float64()), ("lc_valid_support", pa.float64()), ("lc_valid_support_ratio", pa.float64()),
        ("dem_total_support", pa.float64()), ("dem_valid_support", pa.float64()), ("dem_valid_support_ratio", pa.float64()),
        ("dem_mean_m", pa.float64()), ("dem_sd_m", pa.float64())] + [(f"lc_fraction_{i:02d}", pa.float64()) for i in range(1, 23)]),
    "relation_delta": _fields(IDENTITY_FIELDS, [("relation_type", pa.string()), ("source", pa.int64()),
                                                  ("destination", pa.int64()), ("action", pa.string())]),
    "topology": _fields(IDENTITY_FIELDS, [
        ("receiver_local_entity_id", pa.int64()), ("receiver_source_road_id", pa.string()),
        ("component_source_local_entity_id", pa.int64()), ("component_source_road_id", pa.string()),
        ("component_source_role", pa.string()), ("component_index", pa.int64()), ("source_chain_index", pa.int64()),
        ("chain_position", pa.int64()), ("source_node_id", pa.string()), ("x", pa.float64()), ("y", pa.float64()),
        ("component_offset", pa.int64()), ("chain_offset_start", pa.int64()), ("chain_offset_end", pa.int64()),
        ("source_node_offset", pa.int64()),
    ]),
    "absorption": _fields(IDENTITY_FIELDS, [("donor", pa.int64()), ("receiver", pa.int64()), ("status", pa.string()),
                                              ("donor_source_road_id", pa.string()), ("receiver_source_road_id", pa.string())]),
}


def initialize_worker() -> None:
    for name in THREAD_ENV:
        os.environ[name] = "1"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        pa.set_cpu_count(1)
        pa.set_io_thread_count(1)
    except Exception:
        pass


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    return prefix + sha256_bytes(canonical_json(value))[:24]


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical_json(value))


def write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema | None = None) -> None:
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, path, compression="zstd", compression_level=7,
                   use_dictionary=False, write_statistics=True, data_page_version="1.0")


def deterministic_tar(source: Path, output: Path) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    files = sorted((p for p in source.rglob("*") if p.is_file()), key=lambda p: p.relative_to(source).as_posix())
    with tarfile.open(output, "w", format=tarfile.PAX_FORMAT) as archive:
        for path in files:
            relative = path.relative_to(source).as_posix()
            info = archive.gettarinfo(str(path), arcname=relative)
            info.mtime = 0; info.uid = 0; info.gid = 0; info.uname = ""; info.gname = ""; info.mode = 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)
            members.append({"path": relative, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return members


def _eight_neighbors(flat_index: int, shape: tuple[int, int]) -> list[int]:
    rows, columns = shape
    row, column = divmod(flat_index, columns)
    result = []
    for row_delta in (-1, 0, 1):
        for column_delta in (-1, 0, 1):
            if row_delta == 0 and column_delta == 0:
                continue
            next_row, next_column = row + row_delta, column + column_delta
            if 0 <= next_row < rows and 0 <= next_column < columns:
                result.append(next_row * columns + next_column)
    return result


def _component_count(selected: set[int], shape: tuple[int, int]) -> int:
    remaining = set(selected)
    count = 0
    while remaining:
        count += 1
        stack = [remaining.pop()]
        while stack:
            for neighbor in _eight_neighbors(stack.pop(), shape):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
    return count


def landcover_block_mask(valid_cells: list[int], fraction: float, digest: bytes,
                         shape: tuple[int, int] = (100, 100), maximum_fronts: int = 4) -> dict[str, Any]:
    """Select the exact revised round-robin eight-neighbor block mask."""
    valid = sorted(set(int(value) for value in valid_cells))
    if len(valid) != len(valid_cells):
        raise ValueError("land-cover valid-cell identities must be unique")
    if maximum_fronts <= 0:
        raise ValueError("maximum active fronts must be positive")
    target = min(len(valid), max(0, int(round(float(fraction) * len(valid)))))
    if target == 0:
        empty_digest = sha256_bytes(canonical_json([]))
        return {"selected": [], "initial_seeds": [], "reseeds": [],
                "selected_order_sha256": empty_digest, "frontier_order_sha256": empty_digest,
                "maximum_concurrent_fronts": 0, "realized_component_count": 0,
                "valid_cell_count": len(valid), "target_mask_count": 0}

    work = list(valid)
    seed_count = min(maximum_fronts, target, len(work))
    initial_seeds = []
    for index in range(seed_count):
        chosen = index + uniform_integer(digest, "landcover_seed", index, len(work) - index)
        work[index], work[chosen] = work[chosen], work[index]
        initial_seeds.append(work[index])

    selected_order = list(initial_seeds)
    masked = set(initial_seeds)
    fronts: dict[int, dict[str, set[int]]] = {}
    for slot, seed in enumerate(initial_seeds):
        fronts[slot] = {
            "region": {seed},
            "frontier": {value for value in _eight_neighbors(seed, shape) if value in valid and value not in masked},
        }
    frontier_order: list[int] = []
    reseeds: list[dict[str, int]] = []
    frontier_draw = 0
    reseed_draw = 0
    slot_cursor = 0
    maximum_observed = len(fronts)
    valid_set = set(valid)

    while len(masked) < target:
        slots = sorted(fronts)
        if not slots:
            raise ValueError("land-cover block growth exhausted before target")
        slot = slots[slot_cursor % len(slots)]
        slot_cursor += 1
        front = fronts[slot]
        front["frontier"].difference_update(masked)
        if not front["frontier"]:
            unmasked = sorted(valid_set - masked)
            if not unmasked:
                break
            seed = unmasked[uniform_integer(digest, "landcover_reseed", reseed_draw, len(unmasked))]
            reseed_draw += 1
            reseeds.append({"slot": slot, "cell": seed, "selection_position": len(selected_order)})
            masked.add(seed)
            selected_order.append(seed)
            front["region"] = {seed}
            front["frontier"] = {
                value for value in _eight_neighbors(seed, shape) if value in valid_set and value not in masked
            }
            maximum_observed = max(maximum_observed, len(fronts))
            continue

        candidates = sorted(front["frontier"])
        selected = candidates[uniform_integer(digest, "landcover_frontier", frontier_draw, len(candidates))]
        frontier_draw += 1
        frontier_order.append(slot)
        masked.add(selected)
        selected_order.append(selected)
        for other in fronts.values():
            other["frontier"].discard(selected)
        front["region"].add(selected)
        front["frontier"].update(
            value for value in _eight_neighbors(selected, shape) if value in valid_set and value not in masked
        )

    if len(masked) != target or len(selected_order) != target:
        raise ValueError("land-cover block mask did not reach exact target")
    return {
        "selected": selected_order,
        "initial_seeds": initial_seeds,
        "reseeds": reseeds,
        "selected_order_sha256": sha256_bytes(canonical_json(selected_order)),
        "frontier_order_sha256": sha256_bytes(canonical_json(frontier_order)),
        "maximum_concurrent_fronts": maximum_observed,
        "realized_component_count": _component_count(masked, shape),
        "valid_cell_count": len(valid),
        "target_mask_count": target,
    }


def _parts(geometry: Any) -> list[Any]:
    if geometry.geom_type in ("MultiLineString", "MultiPolygon", "GeometryCollection"):
        return list(geometry.geoms)
    return [geometry]


def canonical_road_key(value: Any) -> tuple[int, Any]:
    if isinstance(value, (int, np.integer)):
        return (0, int(value))
    text = str(value)
    return (1, text.encode("utf-8"))


def geometry_center(geometry: Any) -> tuple[float, float]:
    xmin, ymin, xmax, ymax = geometry.bounds
    return ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)


def coordinate_count(geometry: Any) -> int:
    return int(shapely.get_num_coordinates(geometry))


def structure_signature(geometry: Any) -> tuple[Any, ...]:
    if isinstance(geometry, Polygon):
        return ("Polygon", 1, len(geometry.interiors))
    if isinstance(geometry, MultiPolygon):
        return ("MultiPolygon", len(geometry.geoms), tuple(len(x.interiors) for x in geometry.geoms))
    if isinstance(geometry, LineString):
        return ("LineString", 1)
    if isinstance(geometry, MultiLineString):
        return ("MultiLineString", len(geometry.geoms))
    return (geometry.geom_type,)


def _jitter_ring(coords: list[tuple[float, float]], digest: bytes, profile: dict[str, Any],
                 start_index: int, protected: set[tuple[float, float]], closed: bool,
                 bounds: tuple[float, float, float, float]) -> tuple[list[tuple[float, float]], int]:
    result = list(coords)
    stop = len(result) - 1 if closed and len(result) > 1 else len(result)
    xmin, ymin, xmax, ymax = bounds
    for index in range(stop):
        x, y = result[index]
        ordinal = start_index + index
        boundary = min(abs(x - xmin), abs(x - xmax), abs(y - ymin), abs(y - ymax)) <= 1e-8
        if boundary or (float(x), float(y)) in protected:
            continue
        if uniform_binary64(digest, "geometry_jitter_gate", ordinal) >= float(profile["jitter_probability"]):
            continue
        angle = 2.0 * math.pi * uniform_binary64(digest, "geometry_jitter_value", 2 * ordinal)
        distance = float(profile["jitter_displacement_m"]) * uniform_binary64(
            digest, "geometry_jitter_value", 2 * ordinal + 1
        )
        result[index] = (x + distance * math.cos(angle), y + distance * math.sin(angle))
    if closed and result:
        result[-1] = result[0]
    return result, start_index + stop


def jitter_geometry(geometry: Any, digest: bytes, profile: dict[str, Any],
                    protected: set[tuple[float, float]], bounds: tuple[float, float, float, float]) -> Any:
    cursor = 0
    if isinstance(geometry, LineString):
        coords, _ = _jitter_ring(list(geometry.coords), digest, profile, cursor, protected, False, bounds)
        return LineString(coords)
    if isinstance(geometry, MultiLineString):
        parts = []
        for part in geometry.geoms:
            coords, cursor = _jitter_ring(list(part.coords), digest, profile, cursor, protected, False, bounds)
            parts.append(coords)
        return MultiLineString(parts)
    if isinstance(geometry, Polygon):
        shell, cursor = _jitter_ring(list(geometry.exterior.coords), digest, profile, cursor, protected, True, bounds)
        holes = []
        for ring in geometry.interiors:
            coords, cursor = _jitter_ring(list(ring.coords), digest, profile, cursor, protected, True, bounds)
            holes.append(coords)
        return Polygon(shell, holes)
    if isinstance(geometry, MultiPolygon):
        parts = []
        for polygon in geometry.geoms:
            shell, cursor = _jitter_ring(list(polygon.exterior.coords), digest, profile, cursor, protected, True, bounds)
            holes = []
            for ring in polygon.interiors:
                coords, cursor = _jitter_ring(list(ring.coords), digest, profile, cursor, protected, True, bounds)
                holes.append(coords)
            parts.append(Polygon(shell, holes))
        return MultiPolygon(parts)
    return geometry


def simplify_geometry(geometry: Any, tolerance: float,
                      protected: set[tuple[float, float]]) -> Any:
    candidate = geometry.simplify(tolerance, preserve_topology=True)
    if isinstance(geometry, (LineString, MultiLineString)):
        original_parts = _parts(geometry); candidate_parts = _parts(candidate)
        if len(original_parts) != len(candidate_parts):
            return geometry
        rebuilt = []
        for original, simplified in zip(original_parts, candidate_parts, strict=True):
            coords = list(simplified.coords)
            original_coords = list(original.coords)
            for protected_coord in protected:
                if protected_coord in original_coords and protected_coord not in coords:
                    position = original_coords.index(protected_coord)
                    insertion = min(range(len(coords)), key=lambda i: abs(i / max(1, len(coords)-1) - position / max(1, len(original_coords)-1)))
                    coords.insert(insertion, protected_coord)
            rebuilt.append(LineString(coords))
        return rebuilt[0] if isinstance(geometry, LineString) else MultiLineString(rebuilt)
    return candidate


def selected_hosts(entities: dict[int, dict[str, Any]], geometries: dict[int, Any], retained: set[int]) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    buildings = sorted(i for i in retained if entities[i]["entity_type"] == "B")
    pois = sorted(i for i in retained if entities[i]["entity_type"] == "P")
    if not buildings or not pois:
        return set(), set()
    bg = [geometries[i] for i in buildings]
    pairs = STRtree(bg).query(np.asarray([geometries[i] for i in pois], dtype=object), predicate="within")
    candidates: dict[int, list[int]] = defaultdict(list)
    for poi_offset, building_offset in pairs.T.tolist():
        candidates[pois[poi_offset]].append(buildings[building_offset])
    cnt: set[tuple[int, int]] = set()
    for poi, values in candidates.items():
        host = min(values, key=lambda b: (float(geometries[b].area), str(entities[b]["source_entity_id"]), b))
        cnt.add((host, poi))
    return cnt, {(p, b) for b, p in cnt}


def invariant_relations(entities: dict[int, dict[str, Any]], geometries: dict[int, Any], retained: set[int],
                        road_nodes: dict[int, list[list[tuple[str, float, float]]]]) -> dict[str, set[tuple[int, int]]]:
    cnt, wit = selected_hosts(entities, geometries, retained)
    spatial = sorted(i for i in retained if entities[i]["entity_type"] in ("B", "R"))
    intersections: set[tuple[int, int]] = set()
    if spatial:
        selected = [geometries[i] for i in spatial]
        pairs = STRtree(selected).query(np.asarray(selected, dtype=object), predicate="intersects")
        for a, b in pairs.T.tolist():
            if a != b:
                intersections.add((spatial[a], spatial[b]))
    incident: dict[str, set[int]] = defaultdict(set)
    for road in spatial:
        if entities[road]["entity_type"] != "R":
            continue
        for chain in road_nodes.get(road, []):
            for node_id, _, _ in chain:
                incident[str(node_id)].add(road)
    con: set[tuple[int, int]] = set()
    for roads in incident.values():
        for source in roads:
            for destination in roads:
                if source != destination:
                    con.add((source, destination))
    return {"CNT": cnt, "WIT": wit, "INT": intersections, "CON": con}


def sn_applicable(source: int, destination: int, entities: dict[int, dict[str, Any]], contained_pois: set[int]) -> bool:
    source_type = entities[source]["entity_type"]
    destination_type = entities[destination]["entity_type"]
    if source in contained_pois or destination in contained_pois:
        return False
    return source_type in ("B", "R", "P") and destination_type in ("B", "R", "P")


def sn_relations(entities: dict[int, dict[str, Any]], geometries: dict[int, Any], retained: set[int],
                 contained_pois: set[int], radius: float = 100.0, top_k: int = 16) -> set[tuple[int, int]]:
    rows = sorted(retained)
    if not rows:
        return set()
    selected = [geometries[i] for i in rows]
    tree = STRtree(selected)
    directed: set[tuple[int, int]] = set()
    for offset, source in enumerate(rows):
        indices = tree.query(selected[offset], predicate="dwithin", distance=radius)
        candidates = []
        for index in indices.tolist():
            destination = rows[index]
            if destination == source or not sn_applicable(source, destination, entities, contained_pois):
                continue
            distance = float(selected[offset].distance(selected[index]))
            if distance <= radius:
                candidates.append((distance, destination))
        for _, destination in sorted(candidates, key=lambda x: (x[0], x[1]))[:top_k]:
            directed.add((source, destination))
    return directed | {(b, a) for a, b in directed}


def relation_hash(relations: dict[str, set[tuple[int, int]]]) -> str:
    return sha256_bytes(canonical_json({name: sorted(map(list, relations[name])) for name in sorted(relations)}))


def original_relations(edges: Any) -> dict[str, set[tuple[int, int]]]:
    result = {name: set() for name in RELATIONS}
    for row in edges.itertuples():
        pair = (int(row.source_local_entity_id), int(row.destination_local_entity_id))
        for name in RELATIONS:
            if bool(getattr(row, f"has_{name.lower()}")):
                result[name].add(pair)
    return result


def components_connected(parts: list[Any]) -> bool:
    if not parts:
        return False
    reached = {0}
    while True:
        expanded = reached | {
            index for index, part in enumerate(parts)
            if any(part.intersects(parts[current]) for current in reached)
        }
        if expanded == reached:
            break
        reached = expanded
    return len(reached) == len(parts)


def _grid_window(bounds: tuple[float, float, float, float], shape: tuple[int, int], geometry: Any) -> tuple[range, range]:
    xmin, ymin, xmax, ymax = bounds; height, width = shape
    gxmin, gymin, gxmax, gymax = geometry.bounds
    col0 = max(0, min(width - 1, int(math.floor((gxmin - xmin) / ((xmax - xmin) / width)))))
    col1 = max(0, min(width - 1, int(math.floor((gxmax - xmin) / ((xmax - xmin) / width)))))
    row0 = max(0, min(height - 1, int(math.floor((ymax - gymax) / ((ymax - ymin) / height)))))
    row1 = max(0, min(height - 1, int(math.floor((ymax - gymin) / ((ymax - ymin) / height)))))
    return range(row0, row1 + 1), range(col0, col1 + 1)


def geometry_support(geometry: Any, bounds: tuple[float, float, float, float], shape: tuple[int, int]) -> list[tuple[int, int, float]]:
    xmin, ymin, xmax, ymax = bounds; height, width = shape
    dx = (xmax - xmin) / width; dy = (ymax - ymin) / height
    if isinstance(geometry, Point):
        col = min(width - 1, max(0, int(math.floor((geometry.x - xmin) / dx))))
        row = min(height - 1, max(0, int(math.floor((ymax - geometry.y) / dy))))
        return [(row, col, 1.0)]
    result = []
    rows, cols = _grid_window(bounds, shape, geometry)
    for row in rows:
        top = ymax - row * dy; bottom = top - dy
        for col in cols:
            left = xmin + col * dx; right = left + dx
            intersection = geometry.intersection(box(left, bottom, right, top))
            weight = float(intersection.area if geometry.geom_type in ("Polygon", "MultiPolygon") else intersection.length)
            if weight > 0:
                result.append((row, col, weight))
    return result


def entity_context(geometry: Any, entity_type: str, bounds: tuple[float, float, float, float],
                   lc: np.ndarray, lc_valid: np.ndarray, dem: np.ndarray, dem_valid: np.ndarray) -> dict[str, Any]:
    lc_support = geometry_support(geometry, bounds, (100, 100))
    dem_support = geometry_support(geometry, bounds, (17, 17))
    total = float(geometry.area if entity_type == "B" else geometry.length if entity_type == "R" else 1.0)
    lc_by_class = np.zeros(22, dtype=np.float64); lc_valid_total = 0.0
    for row, col, weight in lc_support:
        valid = float(lc_valid[row, col]); lc_valid_total += weight * valid
        lc_by_class += weight * valid * np.asarray(lc[:, row, col], dtype=np.float64)
    fractions = lc_by_class / lc_valid_total if lc_valid_total > 0 else lc_by_class
    dem_weights = []; dem_values = []
    for row, col, weight in dem_support:
        valid = float(dem_valid[row, col])
        if valid > 0:
            dem_weights.append(weight * valid); dem_values.append(float(dem[row, col]))
    if dem_weights and sum(dem_weights) > 0:
        weights = np.asarray(dem_weights); values = np.asarray(dem_values); mean = float(np.sum(weights * values) / np.sum(weights))
        sd = float(math.sqrt(np.sum(weights * (values - mean) ** 2) / np.sum(weights)))
        dem_valid_total = float(np.sum(weights))
    else:
        mean = float("nan"); sd = float("nan"); dem_valid_total = 0.0
    result = {
        "support_measure_unit": "m2" if entity_type == "B" else "m" if entity_type == "R" else "point",
        "lc_total_support": total, "lc_valid_support": lc_valid_total,
        "lc_valid_support_ratio": lc_valid_total / total if total > 0 else 0.0,
        "dem_total_support": total, "dem_valid_support": dem_valid_total,
        "dem_valid_support_ratio": dem_valid_total / total if total > 0 else 0.0,
        "dem_mean_m": mean, "dem_sd_m": sd,
    }
    result.update({f"lc_fraction_{i+1:02d}": float(value) for i, value in enumerate(fractions)})
    return result


def extract_parent(parent_tar: Path, destination: Path) -> None:
    with tarfile.open(parent_tar) as archive:
        for member in archive.getmembers():
            resolved = (destination / member.name).resolve()
            if destination.resolve() not in resolved.parents and resolved != destination.resolve():
                raise ValueError("P3 tar path escape")
        archive.extractall(destination, filter="data")


def read_scene_tables(root: Path) -> dict[str, Any]:
    return {
        "B": pq.read_table(root / "vector/building_observed.parquet").to_pandas(),
        "R": pq.read_table(root / "vector/road_observed.parquet").to_pandas(),
        "P": pq.read_table(root / "vector/poi_observed.parquet").to_pandas(),
        "edges": pq.read_table(root / "relations/relation_edges.parquet").to_pandas(),
        "topology": pq.read_table(root / "topology/source_topology.parquet").to_pandas(),
        "raster_index": pq.read_table(root / "raster/scene_raster_index.parquet").to_pandas(),
        "lc": zarr.open_group(str(root / "raster/scene_landcover.zarr"), mode="r"),
        "dem": zarr.open_group(str(root / "raster/scene_dem.zarr"), mode="r"),
    }


def scene_data(tables: dict[str, Any], scene_id: str) -> dict[str, Any]:
    entities: dict[int, dict[str, Any]] = {}
    geometries: dict[int, Any] = {}
    for entity_type in ("B", "R", "P"):
        rows = tables[entity_type][tables[entity_type].scene_id == scene_id]
        for record in rows.to_dict("records"):
            local = int(record["local_entity_id"]); record["entity_type"] = entity_type
            entities[local] = record
            geometries[local] = shapely.from_wkb(bytes(record["observed_geometry_wkb"] if "observed_geometry_wkb" in record else record["observed_geometry"]))
    if sorted(entities) != list(range(len(entities))):
        raise ValueError(f"noncanonical P3 local IDs: {scene_id}")
    topology_rows = tables["topology"][tables["topology"].scene_id == scene_id]
    road_nodes: dict[int, list[list[tuple[str, float, float]]]] = defaultdict(list)
    for road, group in topology_rows.groupby("road_local_entity_id", sort=True):
        ordered = group.sort_values(["source_node_position", "source_node_offset_start"], kind="mergesort")
        chain = [(str(row.source_node_id), float(row.source_node_x_5186), float(row.source_node_y_5186)) for row in ordered.itertuples()]
        road_nodes[int(road)].append(chain)
    edges = tables["edges"][tables["edges"].scene_id == scene_id]
    raster_row = tables["raster_index"][tables["raster_index"].scene_id == scene_id].iloc[0]
    zindex = int(raster_row.zarr_index)
    return {
        "scene_id": scene_id, "entities": entities, "geometries": geometries,
        "road_nodes": dict(road_nodes), "edges": edges,
        "bounds": (float(raster_row.xmin), float(raster_row.ymin), float(raster_row.xmax), float(raster_row.ymax)),
        "center": ((float(raster_row.xmin) + float(raster_row.xmax)) / 2, (float(raster_row.ymin) + float(raster_row.ymax)) / 2),
        "lc": np.asarray(tables["lc"]["class_fraction"][zindex], dtype=np.float32),
        "lc_valid": np.asarray(tables["lc"]["valid_support_ratio"][zindex], dtype=np.float32),
        "lc_mask": np.asarray(tables["lc"]["valid_mask"][zindex], dtype=np.uint8),
        "dem": np.asarray(tables["dem"]["raw_mean_m"][zindex], dtype=np.float32),
        "dem_valid": np.asarray(tables["dem"]["valid_support_ratio"][zindex], dtype=np.float32),
        "dem_mask": np.asarray(tables["dem"]["valid_mask"][zindex], dtype=np.uint8),
    }


def original_sn(edges: Any) -> set[tuple[int, int]]:
    return {(int(row.source_local_entity_id), int(row.destination_local_entity_id)) for row in edges.itertuples() if bool(row.has_sn)}


def compose_absorption(scene: dict[str, Any], selected: set[int], profile_id: str, view: int) -> tuple[set[int], dict[int, int], list[dict[str, Any]], dict[int, Any], dict[int, list[list[tuple[str, float, float]]]]]:
    entities = scene["entities"]; geometries = dict(scene["geometries"]); road_nodes = {k: [list(chain) for chain in v] for k, v in scene["road_nodes"].items()}
    donors = sorted((i for i in selected if entities[i]["entity_type"] == "R"), key=lambda i: canonical_road_key(entities[i]["source_entity_id"]))
    donor_set = set(donors); assignment: dict[int, int] = {}; provenance = []
    for donor in donors:
        donor_nodes = {node for chain in road_nodes.get(donor, []) for node, _, _ in chain}
        candidates = []
        for receiver in sorted((i for i, e in entities.items() if e["entity_type"] == "R" and i not in donor_set), key=lambda i: canonical_road_key(entities[i]["source_entity_id"])):
            receiver_nodes = {node for chain in road_nodes.get(receiver, []) for node, _, _ in chain}
            if donor_nodes & receiver_nodes and str(entities[donor].get("ROAD_TYPE")) == str(entities[receiver].get("ROAD_TYPE")) and str(entities[donor].get("ROAD_RANK")) == str(entities[receiver].get("ROAD_RANK")):
                candidates.append(receiver)
        if not candidates:
            provenance.append({"donor": donor, "receiver": None, "status": "NO_VALID_RECEIVER"}); continue
        digest = base_digest(profile_id, scene["scene_id"], view, "road_absorption", entities[donor]["source_entity_id"], None)
        receiver = candidates[uniform_integer(digest, "receiver_selection", 0, len(candidates))]
        assignment[donor] = receiver
    groups: dict[int, list[int]] = defaultdict(list)
    for donor, receiver in assignment.items(): groups[receiver].append(donor)
    accepted: dict[int, int] = {}
    for receiver in sorted(groups, key=lambda i: canonical_road_key(entities[i]["source_entity_id"])):
        receiver_parts = _parts(geometries[receiver]); chains = list(road_nodes.get(receiver, [])); accepted_donors = []
        for donor in sorted(groups[receiver], key=lambda i: canonical_road_key(entities[i]["source_entity_id"])):
            candidate_parts = receiver_parts + _parts(geometries[donor])
            candidate = MultiLineString([list(part.coords) for part in candidate_parts])
            if candidate.is_empty or not candidate.is_valid or not components_connected(candidate_parts):
                provenance.append({"donor": donor, "receiver": receiver, "status": "INVALID_CONNECTED_GEOMETRY"}); continue
            receiver_parts = candidate_parts; chains.extend(road_nodes.get(donor, [])); accepted_donors.append(donor); accepted[donor] = receiver
        if accepted_donors:
            geometries[receiver] = MultiLineString([list(part.coords) for part in receiver_parts])
            road_nodes[receiver] = chains
            provenance.extend({"donor": donor, "receiver": receiver, "status": "ABSORBED"} for donor in accepted_donors)
    return set(accepted), accepted, provenance, geometries, road_nodes


def augment_scene(scene: dict[str, Any], profile: dict[str, Any], resources: dict[str, Any], view: int) -> dict[str, list[dict[str, Any]]]:
    scene_id = scene["scene_id"]; profile_id = profile["profile_id"]; entities = scene["entities"]
    all_ids = sorted(entities); digest = base_digest(profile_id, scene_id, view, "entity_removal", None, None)
    sampled_fraction = uniform_binary64(digest, "removal_fraction", 0) * float(profile["removal_fraction"])
    primary_count = removal_count(sampled_fraction, len(all_ids))
    selected_tokens = sample_without_replacement([f"{i:020d}" for i in all_ids], primary_count, digest, "entity_selection")
    selected_ids = {int(x) for x in selected_tokens}
    absorbed, donor_map, absorption, geometries, road_nodes = compose_absorption(scene, selected_ids, profile_id, view)
    direct_removed = {i for i in selected_ids if entities[i]["entity_type"] in ("B", "P")} | absorbed
    cascade = set()
    for row in scene["edges"].itertuples():
        source = int(row.source_local_entity_id); destination = int(row.destination_local_entity_id)
        if bool(row.has_cnt) and source in direct_removed and entities[source]["entity_type"] == "B":
            cascade.add(destination)
    removed = direct_removed | cascade; retained = set(all_ids) - removed
    reference = invariant_relations(entities, geometries, retained, road_nodes)
    threshold = resources["complexity_thresholds"]
    geometry_rows = []; fallback_rows = []; attempts_hist = defaultdict(int)
    pre_perturb = dict(geometries)
    for local in sorted(i for i in retained if entities[i]["entity_type"] in ("B", "R")):
        original = geometries[local]; protected = set()
        if entities[local]["entity_type"] == "R":
            protected = {(x, y) for chain in road_nodes.get(local, []) for _, x, y in chain}
        simplify = coordinate_count(original) > float(threshold[entities[local]["entity_type"]])
        accepted = None; accepted_attempt = None; accepted_seed = None; accepted_tolerance = None; failures = []
        for attempt in range(1, 11):
            gdigest = base_digest(profile_id, scene_id, view, "geometry", entities[local]["source_entity_id"], attempt)
            if simplify:
                tolerance = float(profile["simplification_tolerance_m"]) * uniform_binary64(gdigest, "geometry_simplification", 0)
                candidate = simplify_geometry(original, tolerance, protected)
            else:
                candidate = jitter_geometry(original, gdigest, profile, protected, scene["bounds"])
            valid = not candidate.is_empty and candidate.is_valid and box(*scene["bounds"]).covers(candidate) and structure_signature(candidate) == structure_signature(original)
            reason = "GEOMETRY_INVALID"
            if valid:
                geometries[local] = candidate
                relations = invariant_relations(entities, geometries, retained, road_nodes)
                valid = relations == reference
                reason = "RELATION_SET_CHANGED"
            if valid:
                accepted = candidate; accepted_attempt = attempt; accepted_seed = gdigest.hex()
                accepted_tolerance = tolerance if simplify else None
                attempts_hist[attempt] += 1; break
            geometries[local] = original; failures.append({"attempt": attempt, "seed": gdigest.hex(), "reason": reason})
        if accepted is None:
            geometries[local] = original; attempts_hist[10] += 1
            fallback_rows.append({"scene_id": scene_id, "profile_id": profile_id, "master_view_id": view, "local_entity_id": local,
                                  "attempt_count": 10, "attempts_json": json.dumps(failures, sort_keys=True, separators=(",", ":")), "fallback": True})
        geom = geometries[local]; center = geometry_center(geom); source = entities[local]
        jitter_selected = 0; maximum_displacement = 0.0
        if not simplify and structure_signature(geom) == structure_signature(original):
            original_xy = shapely.get_coordinates(original); final_xy = shapely.get_coordinates(geom)
            if len(original_xy) == len(final_xy):
                displacements = np.linalg.norm(final_xy - original_xy, axis=1)
                jitter_selected = int(np.count_nonzero(displacements > 0))
                maximum_displacement = float(displacements.max()) if len(displacements) else 0.0
        row = {"scene_id": scene_id, "profile_id": profile_id, "master_view_id": view, "local_entity_id": local,
               "geometry_wkb": geom.wkb, "geometry_dtype": "float64_wkb", "center_x": center[0], "center_y": center[1],
               "relative_x": center[0]-scene["center"][0], "relative_y": center[1]-scene["center"][1],
               "xmin": geom.bounds[0], "ymin": geom.bounds[1], "xmax": geom.bounds[2], "ymax": geom.bounds[3],
               "area_m2": float(geom.area), "length_m": float(geom.length),
               "receiver_road_id": str(source["source_entity_id"]) if local in donor_map.values() else None,
               "geometry_operation": "SIMPLIFY" if simplify else "JITTER", "accepted_attempt": accepted_attempt,
               "accepted_attempt_seed": accepted_seed, "sampled_simplification_tolerance_m": accepted_tolerance,
               "jitter_selected_vertex_count": jitter_selected, "maximum_vertex_displacement_m": maximum_displacement,
               "attempts_json": json.dumps(
                   failures + ([] if accepted_attempt is None else [{"attempt": accepted_attempt, "seed": accepted_seed, "reason": "ACCEPTED"}]),
                   sort_keys=True, separators=(",", ":")),
               "fallback": accepted is None, "changed_from_post_absorption": geom.wkb != pre_perturb[local].wkb}
        if source["entity_type"] == "B":
            old_area = float(source.get("observed_area_m2", geom.area)); old_gfa = source.get("observed_gross_floor_area_m2")
            row["observed_area_m2"] = float(geom.area)
            row["observed_gross_floor_area_m2"] = None if old_gfa is None or (isinstance(old_gfa,float) and math.isnan(old_gfa)) else float(old_gfa) * float(geom.area) / old_area if old_area > 0 else 0.0
        geometry_rows.append(row)
    final_invariant = invariant_relations(entities, geometries, retained, road_nodes)
    if final_invariant != reference:
        raise ValueError(f"final invariant relation mismatch: {scene_id}/{profile_id}/{view}")
    contained_pois = {poi for _, poi in final_invariant["CNT"]}
    final_relations = {**final_invariant, "SN": sn_relations(entities, geometries, retained, contained_pois)}
    parent_relations = original_relations(scene["edges"])
    relation_rows = []
    relation_counts = {}
    for relation_type in RELATIONS:
        original = parent_relations[relation_type]
        final = final_relations[relation_type]
        additions = final - original
        removals_for_type = original - final
        relation_counts[relation_type] = {
            "original": len(original), "added": len(additions),
            "removed": len(removals_for_type), "final": len(final),
        }
        relation_rows.extend(
            {"scene_id": scene_id, "profile_id": profile_id, "master_view_id": view,
             "relation_type": relation_type, "source": source, "destination": destination, "action": action}
            for action, pairs in (("ADD", additions), ("REMOVE", removals_for_type))
            for source, destination in sorted(pairs)
        )
    # Attribute perturbation stores only deltas and explicit no-op/selection provenance.
    attribute_rows = []
    for local in sorted(retained):
        entity = entities[local]; entity_type = entity["entity_type"]
        fields = ["A9","A11"] if entity_type == "B" else ["ROAD_RANK","ROAD_TYPE"] if entity_type == "R" else []
        for field in fields:
            value = entity.get(field)
            if value is None or (isinstance(value,float) and math.isnan(value)): continue
            adigest = base_digest(profile_id, scene_id, view, "categorical", f"{entity['source_entity_id']}:{field}", None)
            u = uniform_binary64(adigest, "categorical_mask", 0)
            action = "RETAIN"; augmented = str(value)
            if u < float(profile["categorical_mask_probability"]): action="MASK"; augmented="MASK"
            if action != "RETAIN": attribute_rows.append({"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"local_entity_id":local,"field":field,"original":str(value),"augmented":augmented,"action":action})
        if entity_type == "P":
            codes = tuple(
                "MISSING" if entity.get(f"CLASS_L{i}_CODE") is None or (isinstance(entity.get(f"CLASS_L{i}_CODE"),float) and math.isnan(entity.get(f"CLASS_L{i}_CODE"))) else str(entity.get(f"CLASS_L{i}_CODE"))
                for i in range(1, 7)
            )
            adigest = base_digest(profile_id, scene_id, view, "poi_hierarchy", entity["source_entity_id"], None)
            u = uniform_binary64(adigest, "categorical_mask", 0)
            if u < float(profile["categorical_mask_probability"]):
                for level, value in enumerate(codes, start=1):
                    if value != "MISSING":
                        attribute_rows.append({"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"local_entity_id":local,
                                               "field":f"CLASS_L{level}_CODE","original":value,"augmented":"MASK","action":"MASK"})
            elif u < float(profile["categorical_mask_probability"]) + float(profile["categorical_replacement_probability"]):
                eligible = []
                for level in range(4, 7):
                    if codes[level - 1] == "MISSING":
                        continue
                    key = f"{level}|{'|'.join(codes[:level - 1])}"
                    alternatives = [tuple(x) for x in resources["poi_hierarchy_branches"].get(key, []) if tuple(x)[level - 1] != codes[level - 1]]
                    if alternatives:
                        eligible.append((level, key, sorted(alternatives)))
                if eligible:
                    level, _, alternatives = eligible[uniform_integer(adigest, "categorical_replacement", 0, len(eligible))]
                    replacement = alternatives[uniform_integer(adigest, "categorical_replacement", 1, len(alternatives))]
                    for index in range(level - 1, 6):
                        if codes[index] != "MISSING" and replacement[index] != codes[index]:
                            attribute_rows.append({"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"local_entity_id":local,
                                                   "field":f"CLASS_L{index + 1}_CODE","original":codes[index],"augmented":replacement[index],"action":"REPLACE"})
        if entity_type == "R" and entity.get("LANES") is not None and not (isinstance(entity.get("LANES"),float) and math.isnan(entity.get("LANES"))):
            ldigest=base_digest(profile_id,scene_id,view,"lane",entity["source_entity_id"],None)
            if uniform_binary64(ldigest,"lane_perturbation",0)<float(profile["lane_probability"]):
                delta=(-1,1)[uniform_integer(ldigest,"lane_perturbation",1,2)]; original=int(round(float(entity["LANES"]))); augmented=max(1,original+delta)
                attribute_rows.append({"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"local_entity_id":local,"field":"LANES","original":str(original),"augmented":str(augmented),"action":"PERTURB"})
    # Raster perturbation and exact geometry support context.
    lc = scene["lc"].copy(); lc_valid = scene["lc_valid"].copy(); dem = scene["dem"].copy(); dem_valid = scene["dem_valid"].copy()
    valid_lc = [int(x) for x in np.flatnonzero(scene["lc_mask"] > 0)]
    ldigest=base_digest(profile_id,scene_id,view,"landcover",None,None)
    lc_mask = landcover_block_mask(valid_lc, float(profile["landcover_mask_fraction"]), ldigest)
    selected_lc = lc_mask["selected"]
    raster_rows=[]
    for flat in selected_lc:
        row,col=divmod(flat,100); lc[:,row,col]=0; lc_valid[row,col]=0
        raster_rows.append({"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"modality":"landcover","flat_index":flat,"value":None})
    landcover_provenance_rows = [{
        "scene_id": scene_id, "profile_id": profile_id, "master_view_id": view,
        "algorithm": "eight_neighbor_round_robin_block_growth_v1",
        "valid_cell_count": lc_mask["valid_cell_count"],
        "target_mask_count": lc_mask["target_mask_count"],
        "initial_seeds_json": json.dumps(lc_mask["initial_seeds"], separators=(",", ":")),
        "reseeds_json": json.dumps(lc_mask["reseeds"], sort_keys=True, separators=(",", ":")),
        "selected_order_sha256": lc_mask["selected_order_sha256"],
        "frontier_order_sha256": lc_mask["frontier_order_sha256"],
        "maximum_concurrent_fronts": lc_mask["maximum_concurrent_fronts"],
        "realized_component_count": lc_mask["realized_component_count"],
    }]
    valid_dem=[int(x) for x in np.flatnonzero(scene["dem_mask"]>0)]; ddigest=base_digest(profile_id,scene_id,view,"dem",None,None)
    for draw,flat in enumerate(valid_dem):
        noise=float(profile["dem_noise_sd_m"])*standard_normal(ddigest,"dem_gaussian",draw); row,col=divmod(flat,17)
        dem[row,col]=np.float32(float(dem[row,col])+noise)
        raster_rows.append({"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"modality":"dem","flat_index":flat,"value":float(dem[row,col])})
    context_rows=[]
    for local in sorted(retained):
        context=entity_context(geometries[local],entities[local]["entity_type"],scene["bounds"],lc,lc_valid,dem,dem_valid)
        context_rows.append({"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"local_entity_id":local,**context})
    removals=[{"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"local_entity_id":i,"removal_role":"CASCADE_POI" if i in cascade else "ABSORBED_ROAD" if i in absorbed else "DIRECT"} for i in sorted(removed)]
    topology_rows=[]
    for receiver in sorted(set(donor_map.values())):
        component_offset=0
        source_roads = [receiver] + sorted((donor for donor, target in donor_map.items() if target == receiver),
                                           key=lambda i: canonical_road_key(entities[i]["source_entity_id"]))
        component = 0
        for source_road in source_roads:
            for chain_index, chain in enumerate(scene["road_nodes"].get(source_road, [])):
                chain_start = component_offset; chain_end = chain_start + len(chain)
                for position,(node,x,y) in enumerate(chain):
                    topology_rows.append({"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"receiver_local_entity_id":receiver,
                                          "receiver_source_road_id":str(entities[receiver]["source_entity_id"]),
                                          "component_source_local_entity_id":source_road,
                                          "component_source_road_id":str(entities[source_road]["source_entity_id"]),
                                          "component_source_role":"RECEIVER" if source_road == receiver else "DONOR",
                                          "component_index":component,"source_chain_index":chain_index,"chain_position":position,
                                          "source_node_id":node,"x":x,"y":y,"component_offset":component_offset,
                                          "chain_offset_start":chain_start,"chain_offset_end":chain_end,"source_node_offset":chain_start + position})
                component_offset = chain_end; component += 1
    candidate_id=stable_id("augv_",{"cache":resources["cache_id"],"scene":scene_id,"profile":profile_id,"view":view,"implementation":resources["implementation_hash"]})
    operation_seeds = {
        operation: base_digest(profile_id, scene_id, view, operation, None, None).hex()
        for operation in ("entity_removal", "landcover", "dem")
    }
    candidate={"candidate_id":candidate_id,"scene_id":scene_id,"profile_id":profile_id,"master_view_id":view,"sampled_removal_fraction":sampled_fraction,
               "primary_removal_count":primary_count,"direct_removed_count":len(direct_removed),"cascade_removed_count":len(cascade),"absorbed_donor_count":len(absorbed),
               "retained_entity_count":len(retained),"geometry_entity_count":len(geometry_rows),
               "geometry_override_count":sum(bool(row["changed_from_post_absorption"]) for row in geometry_rows),"geometry_fallback_count":len(fallback_rows),
               "attribute_override_count":len(attribute_rows),"landcover_mask_count":len(selected_lc),"dem_noise_count":len(valid_dem),
               "landcover_mask_digest":lc_mask["selected_order_sha256"],"landcover_component_count":lc_mask["realized_component_count"],
               "landcover_initial_seed_count":len(lc_mask["initial_seeds"]),"landcover_reseed_count":len(lc_mask["reseeds"]),
               "landcover_maximum_active_fronts":lc_mask["maximum_concurrent_fronts"],
               "sn_added_count":relation_counts["SN"]["added"],"sn_removed_count":relation_counts["SN"]["removed"],"invariant_relation_hash":relation_hash(final_invariant),
               "invariant_counts_json":json.dumps({k:len(v) for k,v in final_invariant.items()},sort_keys=True,separators=(",",":")),
               "relation_counts_json":json.dumps(relation_counts,sort_keys=True,separators=(",",":")),
               "attempt_histogram_json":json.dumps({str(k):v for k,v in sorted(attempts_hist.items())},separators=(",",":")),
               "operation_order_json":json.dumps(["entity_removal_and_road_link_absorption","geometry_perturbation","attribute_perturbation_and_geometry_dependent_updates","raster_perturbation","reconstruct_all_derived_observations"],separators=(",",":")),
               "operation_seeds_json":json.dumps(operation_seeds,sort_keys=True,separators=(",",":")),"status":"PASS"}
    for row in absorption:
        row.update(scene_id=scene_id, profile_id=profile_id, master_view_id=view,
                   donor_source_road_id=str(entities[row["donor"]]["source_entity_id"]),
                   receiver_source_road_id=None if row["receiver"] is None else str(entities[row["receiver"]]["source_entity_id"]))
    for values in (removals,geometry_rows,fallback_rows,attribute_rows,raster_rows,landcover_provenance_rows,context_rows,relation_rows,topology_rows,absorption):
        for row in values: row["candidate_id"]=candidate_id
    return {"candidates":[candidate],"removals":removals,"geometry":geometry_rows,"fallbacks":fallback_rows,"attributes":attribute_rows,
            "raster":raster_rows,"landcover_mask_provenance":landcover_provenance_rows,"context":context_rows,
            "relation_delta":relation_rows,"topology":topology_rows,"absorption":absorption}


def scan_resources(parent_tars: list[Path], output: Path, cache_id: str, implementation_hash: str) -> dict[str, Any]:
    counts={"B":[],"R":[]}; hierarchy_branches: dict[str,set[tuple[str, ...]]]=defaultdict(set); training_scenes=[]; branch_training_scenes={}
    for tar_path in parent_tars:
        with tarfile.open(tar_path) as archive:
            raster_index=pq.read_table(io.BytesIO(archive.extractfile("raster/scene_raster_index.parquet").read()),columns=["scene_id","split"])
            raster_frame=raster_index.to_pandas(); branch_scenes=sorted(raster_frame.loc[raster_frame.split=="training","scene_id"].tolist())
            branch_training_scenes[tar_path.parent.name]=branch_scenes; training_scenes.extend(branch_scenes)
            for entity_type,name in (("B","vector/building_observed.parquet"),("R","vector/road_observed.parquet")):
                table=pq.read_table(io.BytesIO(archive.extractfile(name).read()),columns=["split","observed_coordinate_count"])
                frame=table.to_pandas(); counts[entity_type].extend(frame.loc[frame.split=="training","observed_coordinate_count"].astype(int).tolist())
            poi=pq.read_table(io.BytesIO(archive.extractfile("vector/poi_observed.parquet").read())).to_pandas(); poi=poi[poi.split=="training"]
            for row in poi.to_dict("records"):
                codes=tuple("MISSING" if row.get(f"CLASS_L{i}_CODE") is None or (isinstance(row.get(f"CLASS_L{i}_CODE"),float) and math.isnan(row.get(f"CLASS_L{i}_CODE"))) else str(row.get(f"CLASS_L{i}_CODE")) for i in range(1,7))
                for index in range(3,6):
                    if codes[index] != "MISSING":
                        hierarchy_branches[f"{index + 1}|{'|'.join(codes[:index])}"].add(codes)
    value={"cache_id":cache_id,"implementation_hash":implementation_hash,"complexity_thresholds":{k:float(np.quantile(v,0.9,method="linear")) for k,v in counts.items()},
           "poi_hierarchy_branches":{k:[list(x) for x in sorted(v)] for k,v in sorted(hierarchy_branches.items())},"training_scene_count":len(set(training_scenes)),
           "branch_training_scenes":branch_training_scenes}
    write_json(output,value); return value


def build_branch(spec: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    initialize_worker(); started=time.time(); output_dir.mkdir(parents=True,exist_ok=False)
    payload_dir=output_dir/"payload"; payload_dir.mkdir()
    writers = {
        key: pq.ParquetWriter(
            payload_dir / f"{key}.parquet",
            schema,
            compression="zstd",
            compression_level=7,
            use_dictionary=False,
            write_statistics=True,
            data_page_version="1.0",
        )
        for key, schema in PARQUET_SCHEMAS.items()
    }
    candidate_count = 0
    try:
        with tempfile.TemporaryDirectory(prefix="p4-parent-") as temporary:
            parent=Path(temporary); extract_parent(Path(spec["parent_tar"]),parent); tables=read_scene_tables(parent)
            resources=json.loads(Path(spec["resources_path"]).read_text()); resources["cache_id"]=spec["cache_id"]; resources["implementation_hash"]=spec["implementation_hash"]
            for scene_id in spec["scene_ids"]:
                scene=scene_data(tables,scene_id)
                for view in range(16):
                    result=augment_scene(scene,spec["profile"],resources,view)
                    candidate_count += len(result["candidates"])
                    for key, writer in writers.items():
                        rows = result[key]
                        if rows:
                            writer.write_table(pa.Table.from_pylist(rows, schema=PARQUET_SCHEMAS[key]))
    finally:
        for writer in writers.values():
            writer.close()
    payload=output_dir/f"{spec['branch_id']}.tar"; members=deterministic_tar(payload_dir,payload); shutil.rmtree(payload_dir)
    manifest={"schema_version":"1.0.0","status":"PASS","supplement_version":"p4-augmentation-v2",
              "bank_id":spec["bank_id"],"branch_id":spec["branch_id"],"profile_id":spec["profile"]["profile_id"],"profile":spec["profile"],
              "parent_cache_id":spec["cache_id"],"parent_acceptance_id":spec["cache_acceptance_id"],
              "parent_tar_sha256":spec["parent_tar_sha256"],"scene_ids":spec["scene_ids"],"scene_count":len(spec["scene_ids"]),
              "candidate_count":candidate_count,"payload":{"filename":payload.name,"size_bytes":payload.stat().st_size,"sha256":sha256_file(payload)},
              "members":members,"logical_content_sha256":sha256_bytes(canonical_json(members)),
              "implementation_hash":spec["implementation_hash"],
              "payload_contract":{"physical_k":16,"geometry_dtype":"float64_wkb","relation_representation":"parent_plus_complete_typed_delta",
                                  "raster_representation":"parent_plus_cell_delta","source_topology":"ordered_nested_component_chain_offsets"},
              "validation":{"writer":"PASS","schema":"PASS","global_invariants":"PASS"}}
    write_json(output_dir/"branch_manifest.json",manifest)
    write_json(output_dir/"execution.json",{"pass":os.environ.get("FUSE_P4_EXECUTION_PASS",spec.get("execution_pass","A")),
               "requested_workers":int(os.environ.get("FUSE_P4_REQUESTED_WORKERS",spec.get("requested_workers",40))),
               "threads":1,"wall_seconds":time.time()-started,"pid":os.getpid()})
    return manifest
