#!/usr/bin/env python3
"""Inspect national building geometry inventory without loading all geometry."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pyogrio

from geo2vec_large_scale_common import GEOMETRY_LAYER, GEOMETRY_PATH, METADATA_DIR, write_json_atomic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, default=GEOMETRY_PATH)
    parser.add_argument("--layer", default=GEOMETRY_LAYER)
    parser.add_argument("--output-dir", type=Path, default=METADATA_DIR)
    parser.add_argument("--validity-sample", type=int, default=10000)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_json = args.output_dir / "korea_buildings_geometry_inventory.json"
    if out_json.exists() and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite existing report: {out_json}")
    start = time.time()
    info = pyogrio.read_info(args.geometry, layer=args.layer)
    report = {
        "script": Path(__file__).name,
        "geometry": str(args.geometry),
        "layer": args.layer,
        "driver": info.get("driver"),
        "crs": str(info.get("crs")),
        "encoding": info.get("encoding"),
        "feature_count": int(info.get("features")) if info.get("features") is not None else None,
        "geometry_type": info.get("geometry_type"),
        "fid_column": info.get("fid_column"),
        "geometry_name": info.get("geometry_name"),
        "fields": list(info.get("fields") or []),
        "dtypes": [str(x) for x in info.get("dtypes") or []],
        "extent": [float(x) for x in info.get("total_bounds")] if info.get("total_bounds") is not None else None,
    }
    if args.validity_sample > 0:
        sql = f"SELECT building_id, geom FROM {args.layer} ORDER BY building_id LIMIT {int(args.validity_sample)}"
        gdf = pyogrio.read_dataframe(args.geometry, sql=sql)
        report["validity_sample"] = {
            "requested": int(args.validity_sample),
            "rows": int(len(gdf)),
            "missing_building_id": int(gdf["building_id"].isna().sum()),
            "duplicate_building_id": int(gdf["building_id"].duplicated().sum()),
            "null_geometry": int(gdf.geometry.isna().sum()),
            "empty_geometry": int(gdf.geometry.is_empty.sum()),
            "valid_geometry": int(gdf.geometry.is_valid.sum()),
            "invalid_geometry": int((~gdf.geometry.is_valid).sum()),
            "geometry_types": {str(k): int(v) for k, v in gdf.geometry.geom_type.value_counts(dropna=False).items()},
        }
    report["elapsed_seconds"] = time.time() - start
    write_json_atomic(out_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
