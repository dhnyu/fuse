#!/usr/bin/env python3
"""Build deterministic reusable Gwanak Geo2Vec evaluation splits."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyogrio

from geo2vec_large_scale_common import METADATA_DIR, write_json_atomic, write_parquet_atomic


DEFAULT_GEOMETRY = Path("/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
DEFAULT_LAYER = "gwanak_buildings"
DEFAULT_ID_MAP = Path(
    "/members/dhnyu/fusedata/geo2vec_large_scale/id_maps/gwanak_full_geo2vec_paper_faithful_v1/"
    "gwanak_buildings_geo2vec_global_id_map.parquet"
)
DEFAULT_OUTPUT_DIR = METADATA_DIR / "evaluation_splits"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, default=DEFAULT_GEOMETRY)
    parser.add_argument("--layer", default=DEFAULT_LAYER)
    parser.add_argument("--id-map", type=Path, default=DEFAULT_ID_MAP)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--test-fold", type=int, default=5)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def stable_unit_interval(seed: int, building_id: str) -> float:
    h = hashlib.sha256(f"{seed}|{building_id}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "little", signed=False) / float(2**64 - 1)


def quantile_bin(values: pd.Series, bins: int) -> pd.Series:
    ranks = values.rank(method="first")
    return np.floor((ranks - 1) * bins / len(values)).astype(int)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_parquet = args.output_dir / "gwanak_building_evaluation_split.parquet"
    out_json = args.output_dir / "gwanak_building_evaluation_split_metadata.json"
    if out_parquet.exists() and out_json.exists() and not args.overwrite:
        print(out_json.read_text())
        return

    id_map = pd.read_parquet(args.id_map)
    gdf = pyogrio.read_dataframe(args.geometry, layer=args.layer, columns=["building_id"])
    gdf["building_id"] = gdf["building_id"].astype(str)
    centroids = gdf.geometry.centroid
    geom_df = pd.DataFrame(
        {
            "building_id": gdf["building_id"],
            "centroid_x": centroids.x.astype(float),
            "centroid_y": centroids.y.astype(float),
        }
    )
    df = id_map.merge(geom_df, on="building_id", how="left", validate="one_to_one")
    if df[["centroid_x", "centroid_y"]].isna().any().any():
        raise RuntimeError("Some id-map buildings were missing from the Gwanak geometry layer.")

    random_u = df["building_id"].map(lambda x: stable_unit_interval(args.seed, str(x)))
    df["fold_random"] = np.floor(random_u * args.folds).astype(int) + 1
    df.loc[df["fold_random"] > args.folds, "fold_random"] = args.folds
    df["split_random"] = np.where(df["fold_random"] == args.test_fold, "test", "train")

    x_bin = quantile_bin(df["centroid_x"], args.folds)
    y_bin = quantile_bin(df["centroid_y"], args.folds)
    df["fold_spatial"] = ((x_bin * 2 + y_bin * 3) % args.folds).astype(int) + 1
    df["split_spatial"] = np.where(df["fold_spatial"] == args.test_fold, "test", "train")
    df = df[
        [
            "building_id",
            "geo2vec_internal_id",
            "split_random",
            "fold_random",
            "split_spatial",
            "fold_spatial",
            "centroid_x",
            "centroid_y",
        ]
    ].sort_values("geo2vec_internal_id")
    write_parquet_atomic(df, out_parquet)
    meta: dict[str, Any] = {
        "script": Path(__file__).name,
        "output_parquet": str(out_parquet),
        "geometry": str(args.geometry),
        "layer": args.layer,
        "id_map": str(args.id_map),
        "seed": int(args.seed),
        "folds": int(args.folds),
        "test_fold": int(args.test_fold),
        "row_count": int(len(df)),
        "crs_required": "EPSG:5186",
        "random_split_method": "SHA256(seed|building_id) mapped to deterministic 5 folds; fold 5 is test.",
        "spatial_split_method": "Centroid x/y quantile bins in EPSG:5186 combined deterministically into 5 folds; fold 5 is test.",
        "split_counts": {
            "random": df["split_random"].value_counts().to_dict(),
            "spatial": df["split_spatial"].value_counts().to_dict(),
        },
    }
    write_json_atomic(out_json, meta)
    print(json.dumps(meta, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
