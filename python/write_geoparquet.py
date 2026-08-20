#!/usr/bin/env python3
"""Write and inspect the fixed GeoParquet 1.1.0 observation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import geopandas as gpd
import pyarrow.parquet as pq


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metadata(path: Path) -> dict:
    parquet = pq.read_metadata(path)
    raw = parquet.metadata or {}
    geo = json.loads(raw[b"geo"])
    primary = geo["primary_column"]
    column = geo["columns"][primary]
    frame = gpd.read_parquet(path)
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "rows": len(frame),
        "columns": list(frame.columns),
        "version": geo["version"],
        "creator": geo.get("creator"),
        "primary_column": primary,
        "encoding": column["encoding"],
        "crs": column.get("crs"),
        "crs_epsg": frame.crs.to_epsg() if frame.crs is not None else None,
        "geometry_types": column.get("geometry_types", []),
        "bbox": column.get("bbox"),
        "covering": column.get("covering"),
        "row_groups": parquet.num_row_groups,
        "compression": sorted({
            parquet.row_group(i).column(j).compression
            for i in range(parquet.num_row_groups)
            for j in range(parquet.row_group(i).num_columns)
        }),
    }


def write(args: argparse.Namespace) -> None:
    table = pq.read_table(args.input)
    frame = table.to_pandas()
    if args.geometry_column not in frame:
        raise ValueError(f"missing WKB geometry column: {args.geometry_column}")
    geometry = gpd.GeoSeries.from_wkb(frame.pop(args.geometry_column), crs=f"EPSG:{args.epsg}")
    result = gpd.GeoDataFrame(frame, geometry=geometry).rename_geometry(args.geometry_column)
    result.to_parquet(
        args.output,
        index=False,
        compression=args.compression,
        geometry_encoding="WKB",
        write_covering_bbox=True,
        schema_version="1.1.0",
        row_group_size=args.row_group_size,
    )
    info = metadata(Path(args.output))
    if info["version"] != "1.1.0" or info["encoding"] != "WKB":
        raise RuntimeError("GeoParquet metadata contract failed")
    if info["crs_epsg"] != args.epsg or info["primary_column"] != args.geometry_column:
        raise RuntimeError("GeoParquet CRS or primary geometry contract failed")
    print(json.dumps(info, sort_keys=True, separators=(",", ":")))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    writer = sub.add_parser("write")
    writer.add_argument("--input", required=True)
    writer.add_argument("--output", required=True)
    writer.add_argument("--geometry-column", default="observed_geometry")
    writer.add_argument("--epsg", type=int, default=5186)
    writer.add_argument("--compression", default="zstd")
    writer.add_argument("--row-group-size", type=int, default=65536)
    inspector = sub.add_parser("inspect")
    inspector.add_argument("--input", required=True)
    args = parser.parse_args()
    if args.command == "write":
        write(args)
    else:
        print(json.dumps(metadata(Path(args.input)), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
