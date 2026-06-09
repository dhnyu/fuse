#!/usr/bin/env python3
"""Generate deterministic disk-backed SDF sample shards for Geo2Vec."""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from geo2vec_large_scale_common import (
    BASE_SEED,
    GEOMETRY_LAYER,
    GEOMETRY_PATH,
    SAMPLE_CACHE_DIR,
    current_rss_mb,
    maxrss_mb,
    read_json,
    refuse_unsafe_limit,
    sha256_file,
    stable_hash_int,
    suffix_for_limit,
    timer,
    write_json_atomic,
    write_parquet_atomic,
)


DEFAULT_SAMPLE_CONFIG_VERSION = "sdf_proto_v1"
VALID_BRANCHES = {"shape", "location"}
SAMPLE_SCHEMA = pa.schema(
    [
        ("geo2vec_internal_id", pa.int64()),
        ("x", pa.float32()),
        ("y", pa.float32()),
        ("sdf", pa.float32()),
        ("split", pa.uint8()),
        ("sample_kind", pa.uint8()),
        ("sample_index", pa.int32()),
    ]
)


def cpu_times_snapshot() -> Any | None:
    try:
        import psutil

        return psutil.cpu_times()
    except Exception:
        return None


def iowait_percent(start: Any | None, end: Any | None) -> float | None:
    if start is None or end is None:
        return None
    try:
        fields = start._fields
        total_delta = sum(float(getattr(end, f)) - float(getattr(start, f)) for f in fields)
        if total_delta <= 0:
            return None
        wait_delta = float(getattr(end, "iowait", 0.0)) - float(getattr(start, "iowait", 0.0))
        return 100.0 * wait_delta / total_delta
    except Exception:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id-map", type=Path, required=True)
    parser.add_argument("--id-map-metadata", type=Path)
    parser.add_argument("--geometry", type=Path, default=GEOMETRY_PATH)
    parser.add_argument("--layer", default=GEOMETRY_LAYER)
    parser.add_argument("--output-dir", type=Path, default=SAMPLE_CACHE_DIR)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--branch", choices=sorted(VALID_BRANCHES), default="shape")
    parser.add_argument("--buildings-per-shard", type=int, default=5000)
    parser.add_argument("--base-seed", type=int, default=BASE_SEED)
    parser.add_argument("--sample-config-version", default=DEFAULT_SAMPLE_CONFIG_VERSION)
    parser.add_argument("--samples-per-unit", type=float, default=4.0)
    parser.add_argument("--point-sample", type=int, default=1)
    parser.add_argument("--sample-band-width", type=float, default=0.08)
    parser.add_argument("--uniform-grid", type=int, default=2)
    parser.add_argument("--validation-ratio", type=float, default=0.10)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--force-large", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def signed_distance(pt: tuple[float, float], polygon: BaseGeometry) -> float:
    point = Point(pt)
    if polygon.geom_type == "Polygon":
        distance = polygon.exterior.distance(point)
        for interior in polygon.interiors:
            distance = min(distance, interior.distance(point))
        return -distance if polygon.contains(point) else distance
    if polygon.geom_type == "MultiPolygon":
        best = float("inf")
        for poly in polygon.geoms:
            d = signed_distance(pt, poly)
            if abs(d) < abs(best):
                best = d
        return best
    return polygon.distance(point)


def polygonal_part(geom: BaseGeometry) -> BaseGeometry | None:
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.geom_type in {"Polygon", "MultiPolygon"}:
        return geom
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type == "Polygon"]
        multipolys = [p for g in geom.geoms if g.geom_type == "MultiPolygon" for p in g.geoms]
        all_polys = polys + multipolys
        if not all_polys:
            return None
        return MultiPolygon(all_polys) if len(all_polys) > 1 else all_polys[0]
    return None


def normalize_for_shape(geom: BaseGeometry, total_bounds: tuple[float, float, float, float]) -> BaseGeometry | None:
    geom = polygonal_part(geom)
    if geom is None:
        return None
    minx, miny, maxx, maxy = total_bounds
    width = max(maxx - minx, 1e-9)
    height = max(maxy - miny, 1e-9)
    geom = affinity.translate(geom, xoff=-minx, yoff=-miny)
    geom = affinity.scale(geom, xfact=1.0 / width, yfact=1.0 / height, origin=(0, 0))
    bx0, by0, bx1, by1 = geom.bounds
    cx = (bx0 + bx1) / 2.0
    cy = (by0 + by1) / 2.0
    scale = max(bx1 - bx0, by1 - by0, 1e-9)
    geom = affinity.translate(geom, xoff=-cx, yoff=-cy)
    geom = affinity.scale(geom, xfact=1.0 / scale, yfact=1.0 / scale, origin=(0, 0))
    return geom


def normalize_for_location(geom: BaseGeometry, total_bounds: tuple[float, float, float, float]) -> BaseGeometry | None:
    geom = polygonal_part(geom)
    if geom is None:
        return None
    minx, miny, maxx, maxy = total_bounds
    width = max(maxx - minx, 1e-9)
    height = max(maxy - miny, 1e-9)
    geom = affinity.translate(geom, xoff=-minx, yoff=-miny)
    geom = affinity.scale(geom, xfact=1.0 / width, yfact=1.0 / height, origin=(0, 0))
    return geom


def normalize_geometry(geom: BaseGeometry, total_bounds: tuple[float, float, float, float], branch: str) -> BaseGeometry | None:
    if branch == "shape":
        return normalize_for_shape(geom, total_bounds)
    if branch == "location":
        return normalize_for_location(geom, total_bounds)
    raise ValueError(f"Unsupported Geo2Vec branch: {branch}")


def normalization_metadata(total_bounds: tuple[float, float, float, float], branch: str) -> dict[str, Any]:
    minx, miny, maxx, maxy = total_bounds
    width = max(maxx - minx, 1e-9)
    height = max(maxy - miny, 1e-9)
    if branch == "shape":
        formula = (
            "First apply original GeoNeuralRepresentation dataset normalization: "
            "x1=(x-minx)/(maxx-minx), y1=(y-miny)/(maxy-miny). "
            "Then per entity apply shape normalization: subtract entity bbox center "
            "and divide both axes by max(entity_width, entity_height)."
        )
    elif branch == "location":
        formula = (
            "Apply original GeoNeuralRepresentation dataset/global normalization only: "
            "x1=(x-minx)/(maxx-minx), y1=(y-miny)/(maxy-miny). "
            "No per-entity centering or per-entity scaling is applied."
        )
    else:
        raise ValueError(f"Unsupported Geo2Vec branch: {branch}")
    return {
        "branch": branch,
        "source_total_bounds": [float(minx), float(miny), float(maxx), float(maxy)],
        "source_width": float(width),
        "source_height": float(height),
        "normalized_bounds_without_buffer": [0.0, 0.0, 1.0, 1.0] if branch == "location" else None,
        "formula": formula,
    }


def uniform_sample_bounds(branch: str, buffer: float = 0.1) -> tuple[float, float, float, float]:
    if branch == "shape":
        return (-0.6, 0.6, -0.6, 0.6)
    if branch == "location":
        return (0.0 - buffer, 1.0 + buffer, 0.0 - buffer, 1.0 + buffer)
    raise ValueError(f"Unsupported Geo2Vec branch: {branch}")


def iter_polygon_rings(geom: BaseGeometry) -> list[list[tuple[float, float]]]:
    parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    rings: list[list[tuple[float, float]]] = []
    for poly in parts:
        if not isinstance(poly, Polygon):
            continue
        rings.append([(float(x), float(y)) for x, y in poly.exterior.coords])
        for interior in poly.interiors:
            rings.append([(float(x), float(y)) for x, y in interior.coords])
    return rings


def split_for_sample(base_seed: int, gid: int, sample_index: int, validation_ratio: float) -> int:
    h = stable_hash_int(base_seed, gid, sample_index, "split")
    return 1 if (h / float(2**64 - 1)) < validation_ratio else 0


def sample_geometry(
    building_id: str,
    gid: int,
    geom: BaseGeometry,
    total_bounds: tuple[float, float, float, float],
    config: dict[str, Any],
) -> pd.DataFrame:
    branch = str(config["branch"])
    normalized = normalize_geometry(geom, total_bounds, branch)
    if normalized is None or normalized.is_empty:
        return pd.DataFrame(columns=[field.name for field in SAMPLE_SCHEMA])
    seed = stable_hash_int(config["base_seed"], building_id, gid, config["sample_config_version"])
    rng = random.Random(seed)
    rows: list[tuple[int, np.float32, np.float32, np.float32, int, int, int]] = []
    sample_index = 0

    def add(x: float, y: float, kind: int) -> None:
        nonlocal sample_index
        sdf = signed_distance((x, y), normalized)
        split = split_for_sample(config["base_seed"], gid, sample_index, config["validation_ratio"])
        rows.append((gid, np.float32(x), np.float32(y), np.float32(sdf), split, kind, sample_index))
        sample_index += 1

    for ring in iter_polygon_rings(normalized):
        for i, p1 in enumerate(ring[:-1]):
            p2 = ring[i + 1]
            add(p1[0], p1[1], 0)
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            length = math.hypot(dx, dy)
            for _ in range(config["point_sample"]):
                add(
                    p1[0] + rng.gauss(0, config["sample_band_width"]),
                    p1[1] + rng.gauss(0, config["sample_band_width"]),
                    1,
                )
            n_len = int(length * config["samples_per_unit"])
            if n_len > 0 and length > 0:
                inv_len = 1.0 / length
                perp_x = -dy * inv_len
                perp_y = dx * inv_len
                for _ in range(n_len):
                    f = rng.random()
                    dist = rng.gauss(0, config["sample_band_width"])
                    sign = -1.0 if rng.random() < 0.5 else 1.0
                    add(p1[0] + f * dx + sign * dist * perp_x, p1[1] + f * dy + sign * dist * perp_y, 2)

    grid = int(config["uniform_grid"])
    if grid > 0:
        minx, maxx, miny, maxy = config["uniform_sample_bounds"]
        for x in np.linspace(minx, maxx, grid, dtype=np.float32):
            for y in np.linspace(miny, maxy, grid, dtype=np.float32):
                add(float(x), float(y), 3)

    return pd.DataFrame.from_records(rows, columns=[field.name for field in SAMPLE_SCHEMA])


def sample_geometry_worker(payload: tuple[str, int, BaseGeometry, tuple[float, float, float, float], dict[str, Any]]) -> tuple[int, str | None, pd.DataFrame]:
    building_id, gid, geom, total_bounds, config = payload
    try:
        df = sample_geometry(building_id, gid, geom, total_bounds, config)
        if df.empty:
            return gid, "empty_or_invalid_geometry", df
        return gid, None, df
    except Exception as exc:
        empty = pd.DataFrame(columns=[field.name for field in SAMPLE_SCHEMA])
        return gid, f"{type(exc).__name__}: {exc}", empty


def load_geometry_subset(path: Path, layer: str, limit: int) -> tuple[pd.DataFrame, tuple[float, float, float, float], str | None]:
    info = pyogrio.read_info(path, layer=layer)
    total_bounds = tuple(float(x) for x in info["total_bounds"])
    crs = info.get("crs")
    sql = f"SELECT building_id, geom FROM {layer} ORDER BY building_id LIMIT {int(limit)}"
    gdf = pyogrio.read_dataframe(path, sql=sql)
    return gdf, total_bounds, str(crs) if crs is not None else None


def main() -> None:
    args = parse_args()
    refuse_unsafe_limit(args.limit, args.force_large)
    branch = str(args.branch)
    id_map = pd.read_parquet(args.id_map).head(args.limit)
    if len(id_map) != args.limit:
        raise RuntimeError(f"Id map has {len(id_map):,} rows, expected {args.limit:,}.")
    suffix = suffix_for_limit(args.limit)
    sample_config_version = str(args.sample_config_version)
    sample_dir = args.output_dir / f"korea_geo2vec_{branch}_samples_{suffix}_{sample_config_version}"
    sample_dir.mkdir(parents=True, exist_ok=True)
    manifest_parquet = sample_dir / "manifest.parquet"
    manifest_json = sample_dir / "manifest.json"
    if manifest_json.exists() and not args.overwrite:
        existing = json.loads(manifest_json.read_text())
        if existing.get("complete"):
            print(json.dumps(existing, indent=2, sort_keys=True))
            return

    config = {
        "branch": branch,
        "sample_config_version": sample_config_version,
        "base_seed": int(args.base_seed),
        "samples_per_unit": float(args.samples_per_unit),
        "point_sample": int(args.point_sample),
        "sample_band_width": float(args.sample_band_width),
        "uniform_grid": int(args.uniform_grid),
        "uniform_sample_bounds": uniform_sample_bounds(branch),
        "validation_ratio": float(args.validation_ratio),
    }
    workers = max(1, int(args.workers))
    gdf, total_bounds, source_crs = load_geometry_subset(args.geometry, args.layer, args.limit)
    merged = id_map.merge(gdf, on="building_id", how="left", validate="one_to_one")
    if merged["geometry"].isna().any():
        raise RuntimeError("Some id-map buildings were not found in the geometry subset.")

    rows = []
    total_samples = 0
    overall_start = time.time()
    overall_cpu_start = cpu_times_snapshot()
    for shard_index, start_idx in enumerate(range(0, len(merged), args.buildings_per_shard)):
        end_idx = min(start_idx + args.buildings_per_shard, len(merged))
        shard_path = sample_dir / f"samples_shard_{shard_index:06d}.parquet"
        if shard_path.exists() and not args.overwrite:
            checksum = sha256_file(shard_path)
            shard_rows = pq.ParquetFile(shard_path).metadata.num_rows
            rows.append(
                {
                    "shard_index": shard_index,
                    "path": str(shard_path),
                    "status": "complete",
                    "row_count": int(shard_rows),
                    "building_count": int(end_idx - start_idx),
                    "elapsed_seconds": 0.0,
                    "samples_per_second": None,
                    "bytes": int(shard_path.stat().st_size),
                    "checksum_sha256": checksum,
                    "resumed": True,
                }
            )
            total_samples += int(shard_rows)
            continue
        shard_cpu_start = cpu_times_snapshot()
        with timer() as t:
            payloads = [
                (rec.building_id, int(rec.geo2vec_internal_id), rec.geometry, total_bounds, config)
                for rec in merged.iloc[start_idx:end_idx].itertuples(index=False)
            ]
            results: list[tuple[int, str | None, pd.DataFrame]] = []
            if workers == 1:
                results = [sample_geometry_worker(payload) for payload in payloads]
            else:
                with ProcessPoolExecutor(max_workers=workers) as executor:
                    futures = [executor.submit(sample_geometry_worker, payload) for payload in payloads]
                    for future in as_completed(futures):
                        results.append(future.result())
            results.sort(key=lambda row: row[0])
            invalid = [(gid, msg) for gid, msg, df in results if msg is not None]
            parts = [df for _, _, df in results if not df.empty]
            shard_df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=[f.name for f in SAMPLE_SCHEMA])
            table = pa.Table.from_pandas(shard_df, schema=SAMPLE_SCHEMA, preserve_index=False)
            tmp = shard_path.with_suffix(".parquet.tmp")
            pq.write_table(table, tmp, compression="zstd")
            os.replace(tmp, shard_path)
        shard_iowait_percent = iowait_percent(shard_cpu_start, cpu_times_snapshot())
        checksum = sha256_file(shard_path)
        shard_samples = len(shard_df)
        total_samples += shard_samples
        rows.append(
            {
                "shard_index": shard_index,
                "path": str(shard_path),
                "status": "complete",
                "row_count": int(shard_samples),
                "building_count": int(end_idx - start_idx),
                "elapsed_seconds": t["elapsed_seconds"],
                "samples_per_second": float(shard_samples / t["elapsed_seconds"]) if t["elapsed_seconds"] > 0 else None,
                "buildings_per_second": float((end_idx - start_idx) / t["elapsed_seconds"]) if t["elapsed_seconds"] > 0 else None,
                "worker_count": int(workers),
                "cpu_rss_mb": current_rss_mb(),
                "peak_maxrss_mb": maxrss_mb(),
                "iowait_percent": shard_iowait_percent,
                "bytes": int(shard_path.stat().st_size),
                "checksum_sha256": checksum,
                "failed_building_count": int(sum(1 for _, msg in invalid if msg and not msg.startswith("empty"))),
                "invalid_building_count": int(len(invalid)),
                "resumed": False,
            }
        )
        print(f"shard {shard_index} buildings={end_idx-start_idx} samples={shard_samples} seconds={t['elapsed_seconds']:.2f}")

    manifest_df = pd.DataFrame(rows)
    write_parquet_atomic(manifest_df, manifest_parquet)
    manifest_checksum = sha256_file(manifest_parquet)
    total_elapsed = time.time() - overall_start
    manifest = {
        "script": Path(__file__).name,
        "complete": True,
        "branch": branch,
        "sample_dir": str(sample_dir),
        "manifest_parquet": str(manifest_parquet),
        "manifest_checksum_sha256": manifest_checksum,
        "id_map": str(args.id_map),
        "id_map_metadata": str(args.id_map_metadata) if args.id_map_metadata else None,
        "geometry": str(args.geometry),
        "layer": args.layer,
        "source_crs": source_crs,
        "total_bounds": [float(x) for x in total_bounds],
        "normalization": normalization_metadata(total_bounds, branch),
        "limit": int(args.limit),
        "building_count": int(len(merged)),
        "total_samples": int(total_samples),
        "total_bytes": int(manifest_df["bytes"].sum()),
        "elapsed_seconds": float(total_elapsed),
        "samples_per_second": float(total_samples / total_elapsed),
        "sample_schema": [f"{field.name}:{field.type}" for field in SAMPLE_SCHEMA],
        "sample_config": config,
        "worker_count": int(workers),
        "cpu_rss_mb": current_rss_mb(),
        "peak_maxrss_mb": maxrss_mb(),
        "iowait_percent": iowait_percent(overall_cpu_start, cpu_times_snapshot()),
        "shard_count": int(len(manifest_df)),
    }
    write_json_atomic(manifest_json, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
