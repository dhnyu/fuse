#!/usr/bin/env python3
"""Create the exact-size final manifest from accepted metadata and successful images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "fuse_paths.py").exists():
            return candidate
    raise RuntimeError(f"Could not locate repository root from {start}")


REPO_ROOT = find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(REPO_ROOT / "src"))

from fuse_paths import data_file, relative_to_repo_or_data  # noqa: E402
from gsv_production import FINAL_TARGET_COUNT, read_records  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-path", type=Path, default=data_file("gsv_accepted_metadata"))
    parser.add_argument("--image-manifest", type=Path, default=data_file("gsv_image_manifest"))
    parser.add_argument("--target-count", type=int, default=FINAL_TARGET_COUNT)
    parser.add_argument("--out", type=Path, default=data_file("gsv_final_manifest", create_parent=True))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    accepted = read_records(args.accepted_path)
    images = read_records(args.image_manifest)
    image_by_pano = {
        row["pano_id"]: row
        for row in images
        if row.get("pano_id") and row.get("download_success") and row.get("crops_generated")
    }
    final = []
    for row in sorted(accepted, key=lambda item: int(item.get("accepted_rank") or item["candidate_id"])):
        image = image_by_pano.get(row.get("pano_id"))
        if not image:
            continue
        merged = dict(row)
        for key, value in image.items():
            merged[f"image_{key}" if key in merged else key] = value
        merged["final_rank"] = len(final) + 1
        final.append(merged)
        if len(final) >= args.target_count:
            break

    pq.write_table(pa.Table.from_pylist(final), args.out, compression="zstd")
    print("GSV final manifest built")
    print(f"final_count: {len(final)}")
    print(f"target_count: {args.target_count}")
    print(f"manifest: {relative_to_repo_or_data(args.out)}")
    if len(final) != args.target_count:
        print("More accepted metadata and successful image materialization are required before the final dataset is complete.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
