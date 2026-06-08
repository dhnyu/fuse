#!/usr/bin/env python3
"""Build a deterministic national building_id -> Geo2Vec internal id map."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from geo2vec_large_scale_common import (
    ATTRIBUTES_PATH,
    ID_MAP_DIR,
    dataframe_checksum,
    ensure_output_dir,
    refuse_unsafe_limit,
    suffix_for_limit,
    write_json_atomic,
    write_parquet_atomic,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attributes", type=Path, default=ATTRIBUTES_PATH)
    parser.add_argument("--output-dir", type=Path, default=ID_MAP_DIR)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--force-large", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def build_id_map(attributes: Path, limit: int) -> pd.DataFrame:
    table = pq.read_table(attributes, columns=["building_id"])
    df = table.to_pandas()
    total_rows = len(df)
    missing = int(df["building_id"].isna().sum())
    if missing:
        raise RuntimeError(f"Found {missing} missing building_id values in attributes.")
    if not df["building_id"].is_unique:
        dupes = int(df["building_id"].duplicated().sum())
        raise RuntimeError(f"Found {dupes} duplicate building_id values in attributes.")
    df = df.sort_values("building_id", kind="mergesort").head(limit).reset_index(drop=True)
    df.insert(0, "geo2vec_internal_id", range(len(df)))
    df["geo2vec_internal_id"] = df["geo2vec_internal_id"].astype("int64")
    if not (df["geo2vec_internal_id"].to_numpy() == range(len(df))).all():
        raise RuntimeError("Internal ids are not contiguous.")
    df.attrs["source_total_rows"] = total_rows
    return df[["building_id", "geo2vec_internal_id"]]


def main() -> None:
    args = parse_args()
    refuse_unsafe_limit(args.limit, args.force_large)
    ensure_output_dir(args.output_dir)
    suffix = suffix_for_limit(args.limit)
    out_parquet = args.output_dir / f"korea_buildings_geo2vec_global_id_map_{suffix}.parquet"
    out_json = args.output_dir / f"korea_buildings_geo2vec_global_id_map_{suffix}_metadata.json"
    if (out_parquet.exists() or out_json.exists()) and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite existing id map outputs for {suffix}.")

    start = time.time()
    df = build_id_map(args.attributes, args.limit)
    elapsed = time.time() - start
    checksum = dataframe_checksum(df, ["building_id", "geo2vec_internal_id"])
    write_parquet_atomic(df, out_parquet)
    metadata = {
        "script": Path(__file__).name,
        "attributes": str(args.attributes),
        "output_parquet": str(out_parquet),
        "limit": args.limit,
        "row_count": int(len(df)),
        "missing_building_id": int(df["building_id"].isna().sum()),
        "duplicate_building_id": int(df["building_id"].duplicated().sum()),
        "min_internal_id": int(df["geo2vec_internal_id"].min()),
        "max_internal_id": int(df["geo2vec_internal_id"].max()),
        "ids_contiguous": bool((df["geo2vec_internal_id"].to_numpy() == range(len(df))).all()),
        "ordering": "building_id ascending, stable mergesort",
        "checksum_records_sha256": checksum,
        "elapsed_seconds": elapsed,
    }
    write_json_atomic(out_json, metadata)
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
