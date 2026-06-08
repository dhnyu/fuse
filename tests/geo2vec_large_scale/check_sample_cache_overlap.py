#!/usr/bin/env python3
"""Check deterministic overlap between two sample cache manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from geo2vec_large_scale_common import METADATA_DIR, read_json, write_json_atomic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest-json", type=Path, required=True)
    parser.add_argument("--candidate-manifest-json", type=Path, required=True)
    parser.add_argument("--overlap-shards", type=int, required=True)
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base = read_json(args.base_manifest_json)
    candidate = read_json(args.candidate_manifest_json)
    base_df = pd.read_parquet(base["manifest_parquet"]).sort_values("shard_index").head(args.overlap_shards)
    candidate_df = pd.read_parquet(candidate["manifest_parquet"]).sort_values("shard_index").head(args.overlap_shards)
    rows = []
    for i in range(args.overlap_shards):
        b = base_df.iloc[i]
        c = candidate_df.iloc[i]
        rows.append(
            {
                "shard_index": int(i),
                "base_checksum": str(b["checksum_sha256"]),
                "candidate_checksum": str(c["checksum_sha256"]),
                "checksum_match": bool(b["checksum_sha256"] == c["checksum_sha256"]),
                "base_row_count": int(b["row_count"]),
                "candidate_row_count": int(c["row_count"]),
                "row_count_match": bool(int(b["row_count"]) == int(c["row_count"])),
            }
        )
    report = {
        "base_manifest_json": str(args.base_manifest_json),
        "candidate_manifest_json": str(args.candidate_manifest_json),
        "overlap_shards": int(args.overlap_shards),
        "all_checksum_match": all(row["checksum_match"] for row in rows),
        "all_row_count_match": all(row["row_count_match"] for row in rows),
        "rows": rows,
    }
    out = args.output_json or (METADATA_DIR / f"sample_cache_overlap_{args.overlap_shards}_shards.json")
    write_json_atomic(out, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
