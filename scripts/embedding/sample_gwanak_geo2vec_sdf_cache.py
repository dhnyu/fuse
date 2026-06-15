#!/usr/bin/env python3
"""Generate Gwanak building Geo2Vec SDF caches for object-geometry variants."""

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

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid


DEFAULT_OUTPUT_ROOT = Path.home() / "fusedata" / "embeddings" / "gwanak_building_geo2vec"
DEFAULT_PREPARED = DEFAULT_OUTPUT_ROOT / "phase0_current" / "prepared" / "gwanak_buildings_geo2vec_valid.gpkg"
DEFAULT_PREPARED_LAYER = "gwanak_buildings_geo2vec_valid"
DEFAULT_ID_MAP = DEFAULT_OUTPUT_ROOT / "phase0_current" / "id_maps" / "gwanak_buildings_geo2vec_id_map.parquet"
DEFAULT_NONOVERLAP_GRID = Path.home() / "fusedatalarge" / "working_data" / "gwanak" / "gwanak_scene_grid_500m_nonoverlap.gpkg"
DEFAULT_OVERLAP_GRID = Path.home() / "fusedatalarge" / "working_data" / "gwanak" / "gwanak_scene_grid_500m_overlap_stride250m.gpkg"
BASE_SEED = 20260615
VALID_VARIANTS = ("shape_only", "shape_absolute_location", "shape_scene_relative_location")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-geometry", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--prepared-layer", default=DEFAULT_PREPARED_LAYER)
    parser.add_argument("--id-map", type=Path, default=DEFAULT_ID_MAP)
    parser.add_argument("--nonoverlap-grid", type=Path, default=DEFAULT_NONOVERLAP_GRID)
    parser.add_argument("--overlap-grid", type=Path, default=DEFAULT_OVERLAP_GRID)
    parser.add_argument("--grid-type", choices=["nonoverlap", "overlap"], default="nonoverlap")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="phase1_smoke")
    parser.add_argument("--variant", choices=[*VALID_VARIANTS, "all"], default="all")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--smoke-size", type=int, default=32)
    parser.add_argument("--buildings-per-shard", type=int, default=64)
    parser.add_argument("--samples-per-unit", type=float, default=1.0)
    parser.add_argument("--point-sample", type=int, default=1)
    parser.add_argument("--sample-band-width", type=float, default=0.05)
    parser.add_argument("--uniform-grid", type=int, default=2)
    parser.add_argument("--validation-ratio", type=float, default=0.2)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--base-seed", type=int, default=BASE_SEED)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


def stable_hash_int(*parts: Any, bits: int = 64) -> int:
    import hashlib

    text = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[: bits // 8], "little", signed=False)


def sha256_file(path: Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def path_size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / (1024**2)
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / (1024**2)


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


def polygonal_part(geom: BaseGeometry | None) -> BaseGeometry | None:
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = make_valid(geom)
    if geom.geom_type in {"Polygon", "MultiPolygon"}:
        return geom
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type == "Polygon"]
        polys.extend(p for g in geom.geoms if g.geom_type == "MultiPolygon" for p in g.geoms)
        if not polys:
            return None
        return MultiPolygon(polys) if len(polys) > 1 else polys[0]
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
    return affinity.scale(geom, xfact=1.0 / scale, yfact=1.0 / scale, origin=(0, 0))


def normalize_for_location(geom: BaseGeometry, bounds: tuple[float, float, float, float]) -> BaseGeometry | None:
    geom = polygonal_part(geom)
    if geom is None:
        return None
    minx, miny, maxx, maxy = bounds
    width = max(maxx - minx, 1e-9)
    height = max(maxy - miny, 1e-9)
    geom = affinity.translate(geom, xoff=-minx, yoff=-miny)
    return affinity.scale(geom, xfact=1.0 / width, yfact=1.0 / height, origin=(0, 0))


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


def uniform_bounds(branch: str) -> tuple[float, float, float, float]:
    if branch == "shape":
        return (-0.6, 0.6, -0.6, 0.6)
    return (-0.1, 1.1, -0.1, 1.1)


def sample_geometry(entity: dict[str, Any], config: dict[str, Any]) -> pd.DataFrame:
    branch = str(config["branch"])
    geom = entity["geometry"]
    if branch == "shape":
        normalized = normalize_for_shape(geom, tuple(config["shape_total_bounds"]))
    else:
        normalized = normalize_for_location(geom, tuple(entity["location_bounds"]))
    if normalized is None or normalized.is_empty:
        return pd.DataFrame(columns=[field.name for field in SAMPLE_SCHEMA])

    gid = int(entity["geo2vec_internal_id"])
    seed_key = entity.get("entity_key", entity.get("building_id", gid))
    rng = random.Random(stable_hash_int(config["base_seed"], seed_key, gid, config["variant"], branch))
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
            for _ in range(int(config["point_sample"])):
                add(p1[0] + rng.gauss(0, config["sample_band_width"]), p1[1] + rng.gauss(0, config["sample_band_width"]), 1)
            n_len = int(length * float(config["samples_per_unit"]))
            if n_len > 0 and length > 0:
                inv_len = 1.0 / length
                perp_x = -dy * inv_len
                perp_y = dx * inv_len
                for _ in range(n_len):
                    f = rng.random()
                    dist = rng.gauss(0, config["sample_band_width"])
                    sign = -1.0 if rng.random() < 0.5 else 1.0
                    add(p1[0] + f * dx + sign * dist * perp_x, p1[1] + f * dy + sign * dist * perp_y, 2)

    minx, maxx, miny, maxy = uniform_bounds(branch)
    grid = int(config["uniform_grid"])
    for x in np.linspace(minx, maxx, grid, dtype=np.float32):
        for y in np.linspace(miny, maxy, grid, dtype=np.float32):
            add(float(x), float(y), 3)
    return pd.DataFrame.from_records(rows, columns=[field.name for field in SAMPLE_SCHEMA])


def worker(payload: tuple[dict[str, Any], dict[str, Any]]) -> tuple[int, str | None, pd.DataFrame]:
    entity, config = payload
    try:
        df = sample_geometry(entity, config)
        if df.empty:
            return int(entity["geo2vec_internal_id"]), "empty_or_invalid_geometry", df
        return int(entity["geo2vec_internal_id"]), None, df
    except Exception as exc:
        return int(entity["geo2vec_internal_id"]), f"{type(exc).__name__}: {exc}", pd.DataFrame(columns=[f.name for f in SAMPLE_SCHEMA])


def read_prepared(path: Path, layer: str, id_map_path: Path, smoke_size: int | None) -> gpd.GeoDataFrame:
    id_map = pd.read_parquet(id_map_path).sort_values("geo2vec_internal_id")
    if smoke_size is not None:
        id_map = id_map.head(smoke_size)
    gdf = pyogrio.read_dataframe(path, layer=layer)
    gdf["building_id"] = gdf["building_id"].astype(str)
    merged = id_map.merge(gdf, on=["building_id", "geo2vec_internal_id"], how="left", validate="one_to_one")
    if merged["geometry"].isna().any():
        raise RuntimeError("Prepared geometry missing for some ID-map rows.")
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=gdf.crs)


def scene_membership(buildings: gpd.GeoDataFrame, grid_path: Path, grid_type: str) -> gpd.GeoDataFrame:
    grids = pyogrio.read_dataframe(grid_path)
    grids = gpd.GeoDataFrame(grids, geometry="geometry", crs=buildings.crs)
    if "scene_id" not in grids.columns:
        grids["scene_id"] = [f"{grid_type}_{i:06d}" for i in range(len(grids))]
    grids["scene_id"] = grids["scene_id"].astype(str)
    keep_cols = ["scene_id", "geometry"]
    if "coverage_ratio" in grids.columns:
        keep_cols.insert(1, "coverage_ratio")
    grids = grids[keep_cols]
    if grid_type == "nonoverlap":
        points = buildings.copy()
        points["geometry"] = points.geometry.representative_point()
        joined = gpd.sjoin(points, grids, how="left", predicate="within")
        if joined["scene_id"].isna().any():
            joined2 = gpd.sjoin(points.loc[joined["scene_id"].isna(), buildings.columns], grids, how="left", predicate="intersects")
            joined.loc[joined["scene_id"].isna(), "scene_id"] = joined2["scene_id"].to_numpy()
        out = buildings.merge(joined[["building_id", "scene_id"]], on="building_id", how="inner")
    else:
        joined = gpd.sjoin(buildings, grids, how="inner", predicate="intersects")
        out = joined.drop(columns=[c for c in ["index_right"] if c in joined.columns])
    scene_bounds = grids.set_index("scene_id").geometry.bounds
    scene_bounds.columns = ["scene_minx", "scene_miny", "scene_maxx", "scene_maxy"]
    out = out.merge(scene_bounds, left_on="scene_id", right_index=True, how="left")
    out["grid_type"] = grid_type
    out = out.dropna(subset=["scene_id"]).copy()
    out = out.sort_values(["building_id", "scene_id"]).reset_index(drop=True)
    out["geo2vec_internal_id"] = np.arange(len(out), dtype=np.int64)
    out["entity_key"] = out["building_id"].astype(str) + "__" + out["scene_id"].astype(str)
    return out


def entity_map_for_variant(variant: str, branch: str, buildings: gpd.GeoDataFrame, args: argparse.Namespace) -> tuple[pd.DataFrame, list[dict[str, Any]], tuple[float, float, float, float]]:
    full_info = pyogrio.read_info(args.prepared_geometry, layer=args.prepared_layer)
    shape_total_bounds = tuple(float(x) for x in full_info["total_bounds"])
    if variant in {"shape_only", "shape_absolute_location"}:
        df = buildings[["building_id", "geo2vec_internal_id", "geometry"]].copy()
        if branch == "location":
            bounds = shape_total_bounds
            df["location_minx"], df["location_miny"], df["location_maxx"], df["location_maxy"] = bounds
        df["entity_key"] = df["building_id"].astype(str)
        map_cols = ["building_id", "geo2vec_internal_id"]
    else:
        grid_path = args.nonoverlap_grid if args.grid_type == "nonoverlap" else args.overlap_grid
        df = scene_membership(buildings, grid_path, args.grid_type)
        df["location_minx"] = df["scene_minx"]
        df["location_miny"] = df["scene_miny"]
        df["location_maxx"] = df["scene_maxx"]
        df["location_maxy"] = df["scene_maxy"]
        map_cols = ["building_id", "scene_id", "grid_type", "geo2vec_internal_id"]
    entity_map = pd.DataFrame(df[map_cols]).copy()
    entities = []
    for rec in df.itertuples(index=False):
        location_bounds = (
            float(getattr(rec, "location_minx", shape_total_bounds[0])),
            float(getattr(rec, "location_miny", shape_total_bounds[1])),
            float(getattr(rec, "location_maxx", shape_total_bounds[2])),
            float(getattr(rec, "location_maxy", shape_total_bounds[3])),
        )
        entities.append(
            {
                "building_id": str(rec.building_id),
                "scene_id": str(getattr(rec, "scene_id", "")),
                "entity_key": str(rec.entity_key),
                "geo2vec_internal_id": int(rec.geo2vec_internal_id),
                "geometry": rec.geometry,
                "location_bounds": location_bounds,
            }
        )
    return entity_map, entities, shape_total_bounds


def branches_for_variant(variant: str) -> list[str]:
    if variant == "shape_only":
        return ["shape"]
    return ["shape", "location"]


def generate_branch(variant: str, branch: str, buildings: gpd.GeoDataFrame, args: argparse.Namespace) -> dict[str, Any]:
    branch_dir = args.output_root / "sample_caches" / args.run_id / variant / branch
    manifest_json = branch_dir / "manifest.json"
    if manifest_json.exists() and not args.overwrite:
        existing = json.loads(manifest_json.read_text(encoding="utf-8"))
        if existing.get("complete"):
            return existing
    branch_dir.mkdir(parents=True, exist_ok=True)
    entity_map, entities, shape_total_bounds = entity_map_for_variant(variant, branch, buildings, args)
    entity_map_path = branch_dir / "entity_map.parquet"
    pq.write_table(pa.Table.from_pandas(entity_map, preserve_index=False), entity_map_path, compression="zstd")
    config = {
        "variant": variant,
        "branch": branch,
        "base_seed": int(args.base_seed),
        "samples_per_unit": float(args.samples_per_unit),
        "point_sample": int(args.point_sample),
        "sample_band_width": float(args.sample_band_width),
        "uniform_grid": int(args.uniform_grid),
        "validation_ratio": float(args.validation_ratio),
        "shape_total_bounds": [float(x) for x in shape_total_bounds],
    }
    rows = []
    total_samples = 0
    start = time.time()
    workers = max(1, int(args.workers))
    for shard_index, start_idx in enumerate(range(0, len(entities), args.buildings_per_shard)):
        end_idx = min(start_idx + args.buildings_per_shard, len(entities))
        shard_path = branch_dir / f"samples_shard_{shard_index:06d}.parquet"
        if shard_path.exists() and not args.overwrite:
            shard_rows = pq.ParquetFile(shard_path).metadata.num_rows
            total_samples += shard_rows
            rows.append({"shard_index": shard_index, "path": str(shard_path), "status": "complete", "row_count": int(shard_rows), "entity_count": int(end_idx - start_idx), "bytes": shard_path.stat().st_size, "checksum_sha256": sha256_file(shard_path), "resumed": True})
            continue
        payloads = [(entity, config) for entity in entities[start_idx:end_idx]]
        shard_start = time.time()
        if workers == 1:
            results = [worker(payload) for payload in payloads]
        else:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                results = [future.result() for future in as_completed([executor.submit(worker, payload) for payload in payloads])]
        results.sort(key=lambda row: row[0])
        invalid = [(gid, msg) for gid, msg, df in results if msg is not None]
        parts = [df for _, _, df in results if not df.empty]
        shard_df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=[f.name for f in SAMPLE_SCHEMA])
        tmp = shard_path.with_suffix(".parquet.tmp")
        pq.write_table(pa.Table.from_pandas(shard_df, schema=SAMPLE_SCHEMA, preserve_index=False), tmp, compression="zstd")
        os.replace(tmp, shard_path)
        elapsed = time.time() - shard_start
        total_samples += len(shard_df)
        rows.append(
            {
                "shard_index": shard_index,
                "path": str(shard_path),
                "status": "complete",
                "row_count": int(len(shard_df)),
                "entity_count": int(end_idx - start_idx),
                "elapsed_seconds": elapsed,
                "samples_per_second": float(len(shard_df) / elapsed) if elapsed > 0 else None,
                "bytes": shard_path.stat().st_size,
                "checksum_sha256": sha256_file(shard_path),
                "invalid_entity_count": int(len(invalid)),
                "resumed": False,
            }
        )
        print(f"{variant}/{branch} shard={shard_index} entities={end_idx - start_idx} samples={len(shard_df)}")
    shard_manifest = pd.DataFrame(rows)
    manifest_parquet = branch_dir / "manifest.parquet"
    pq.write_table(pa.Table.from_pandas(shard_manifest, preserve_index=False), manifest_parquet, compression="zstd")
    manifest = {
        "script": Path(__file__).name,
        "complete": True,
        "run_id": args.run_id,
        "variant": variant,
        "branch": branch,
        "grid_type": args.grid_type if variant == "shape_scene_relative_location" else None,
        "sample_dir": str(branch_dir),
        "manifest_json": str(manifest_json),
        "manifest_parquet": str(manifest_parquet),
        "entity_map": str(entity_map_path),
        "entity_count": int(len(entity_map)),
        "total_samples": int(total_samples),
        "shard_count": int(len(shard_manifest)),
        "total_bytes": int(shard_manifest["bytes"].sum()) if len(shard_manifest) else 0,
        "cache_size_mb": path_size_mb(branch_dir),
        "prepared_geometry": str(args.prepared_geometry),
        "prepared_layer": args.prepared_layer,
        "shape_total_bounds": [float(x) for x in shape_total_bounds],
        "location_normalization": "gwanak_bbox" if variant == "shape_absolute_location" and branch == "location" else ("scene_bbox" if variant == "shape_scene_relative_location" and branch == "location" else None),
        "sample_config": config,
        "worker_count": workers,
        "smoke_test": bool(args.smoke_test),
        "smoke_size": int(args.smoke_size) if args.smoke_test else None,
        "elapsed_seconds": time.time() - start,
    }
    write_json_atomic(manifest_json, manifest)
    return manifest


def main() -> None:
    args = parse_args()
    if not args.prepared_geometry.exists():
        raise SystemExit(f"Prepared geometry not found: {args.prepared_geometry}")
    if not args.id_map.exists():
        raise SystemExit(f"ID map not found: {args.id_map}")
    variants = list(VALID_VARIANTS) if args.variant == "all" else [args.variant]
    buildings = read_prepared(args.prepared_geometry, args.prepared_layer, args.id_map, args.smoke_size if args.smoke_test else None)
    manifests = []
    for variant in variants:
        for branch in branches_for_variant(variant):
            manifests.append(generate_branch(variant, branch, buildings, args))
    summary = {
        "run_id": args.run_id,
        "variants": variants,
        "manifest_count": len(manifests),
        "manifests": [m["manifest_json"] for m in manifests],
        "total_cache_size_mb": sum(float(m["cache_size_mb"]) for m in manifests),
    }
    summary_path = args.output_root / "sample_caches" / args.run_id / "sample_cache_summary.json"
    write_json_atomic(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
