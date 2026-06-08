#!/usr/bin/env python3
"""Validate disk-backed SDF sample cache shards."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from geo2vec_large_scale_common import REPORT_DIR, read_json, sha256_file, write_json_atomic, write_parquet_atomic


REQUIRED_DTYPES = {
    "geo2vec_internal_id": "int64",
    "x": "float32",
    "y": "float32",
    "sdf": "float32",
    "split": "uint8",
    "sample_kind": "uint8",
    "sample_index": "int32",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-json", type=Path, required=True)
    parser.add_argument("--id-map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=REPORT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = read_json(args.manifest_json)
    sample_dir = Path(manifest["sample_dir"])
    out_json = sample_dir / "sample_cache_validation.json"
    out_parquet = sample_dir / "sample_cache_validation_by_shard.parquet"
    if out_json.exists() and not args.overwrite:
        print(out_json.read_text())
        return
    id_map = pd.read_parquet(args.id_map, columns=["geo2vec_internal_id"])
    expected_ids = set(id_map["geo2vec_internal_id"].astype("int64").tolist())
    shard_manifest = pd.read_parquet(manifest["manifest_parquet"])
    shard_rows = []
    total_rows = 0
    train_rows = 0
    val_rows = 0
    invalid_messages: list[str] = []
    sample_counts: dict[int, int] = {}
    for shard in shard_manifest.itertuples(index=False):
        path = Path(shard.path)
        checksum = sha256_file(path)
        checksum_ok = checksum == shard.checksum_sha256
        table = pq.read_table(path)
        df = table.to_pandas()
        dtype_ok = True
        for col, dtype in REQUIRED_DTYPES.items():
            if col not in df.columns:
                dtype_ok = False
                invalid_messages.append(f"{path.name} missing {col}")
            elif str(df[col].dtype) != dtype:
                dtype_ok = False
                invalid_messages.append(f"{path.name} dtype {col}={df[col].dtype}, expected {dtype}")
        finite_ok = bool(np.isfinite(df[["x", "y", "sdf"]].to_numpy(dtype=np.float32)).all())
        ids = set(df["geo2vec_internal_id"].astype("int64").unique().tolist())
        unknown_ids = ids.difference(expected_ids)
        split_counts = df["split"].value_counts().to_dict()
        for gid, count in df.groupby("geo2vec_internal_id").size().items():
            sample_counts[int(gid)] = sample_counts.get(int(gid), 0) + int(count)
        total_rows += len(df)
        train_rows += int(split_counts.get(0, 0))
        val_rows += int(split_counts.get(1, 0))
        shard_rows.append(
            {
                "shard_index": int(shard.shard_index),
                "path": str(path),
                "row_count": int(len(df)),
                "building_count": int(df["geo2vec_internal_id"].nunique()),
                "checksum_ok": checksum_ok,
                "dtype_ok": dtype_ok,
                "finite_ok": finite_ok,
                "unknown_id_count": int(len(unknown_ids)),
                "train_rows": int(split_counts.get(0, 0)),
                "validation_rows": int(split_counts.get(1, 0)),
            }
        )
    counts = np.array(list(sample_counts.values()), dtype=np.int64)
    missing_ids = expected_ids.difference(sample_counts.keys())
    validation = {
        "manifest_json": str(args.manifest_json),
        "id_map": str(args.id_map),
        "valid": not invalid_messages
        and all(r["checksum_ok"] and r["dtype_ok"] and r["finite_ok"] and r["unknown_id_count"] == 0 for r in shard_rows)
        and len(missing_ids) == 0,
        "messages": invalid_messages[:50],
        "shard_count": int(len(shard_rows)),
        "total_rows": int(total_rows),
        "train_rows": int(train_rows),
        "validation_rows": int(val_rows),
        "validation_ratio_observed": float(val_rows / total_rows) if total_rows else None,
        "building_count_with_samples": int(len(sample_counts)),
        "missing_building_count": int(len(missing_ids)),
        "sample_count_min": int(counts.min()) if len(counts) else None,
        "sample_count_median": float(np.median(counts)) if len(counts) else None,
        "sample_count_max": int(counts.max()) if len(counts) else None,
    }
    write_parquet_atomic(pd.DataFrame(shard_rows), out_parquet)
    write_json_atomic(out_json, validation)
    print(json.dumps(validation, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
