#!/usr/bin/env python3
"""Download and crop panoramas only after production metadata acceptance."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from gsv_production import accepted_to_tasks, materialize_one_panorama, read_records  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-path", type=Path, default=data_file("gsv_accepted_metadata"))
    parser.add_argument("--limit", type=int, default=None, help="Pilot/debug limit; omit for full accepted set.")
    parser.add_argument("--workers", type=int, default=int(os.getenv("GSV_IMAGE_WORKERS", "6")))
    parser.add_argument("--zooms", default=os.getenv("GSV_IMAGE_ZOOMS", "2,1"))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.getenv("GSV_TILE_TIMEOUT_SECONDS", "30")))
    parser.add_argument("--max-retries", type=int, default=int(os.getenv("GSV_IMAGE_MAX_RETRIES", "2")))
    parser.add_argument("--overwrite-crops", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.accepted_path.exists():
        logging.error("Accepted metadata parquet does not exist: %s", args.accepted_path)
        return 2

    records = read_records(args.accepted_path)
    tasks = accepted_to_tasks(records, limit=args.limit)
    zooms = tuple(int(value) for value in args.zooms.split(",") if value.strip())
    manifest_path = data_file("gsv_image_manifest", create_parent=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                materialize_one_panorama,
                task,
                zoom_candidates=zooms,
                timeout_seconds=args.timeout_seconds,
                max_retries=args.max_retries,
                overwrite_crops=args.overwrite_crops,
            ): task
            for task in tasks
        }
        for i, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            results.append(record)
            if i == 1 or i % 25 == 0 or i == len(tasks):
                logging.info("Materialized %s/%s panoramas; latest=%s success=%s", i, len(tasks), record["pano_id"], record["download_success"])

    results.sort(key=lambda row: row["pano_id"])
    pq.write_table(pa.Table.from_pylist(results), manifest_path, compression="zstd")
    successes = [row for row in results if row["download_success"] and row["crops_generated"]]
    failures = [row for row in results if not (row["download_success"] and row["crops_generated"])]
    print("GSV image materialization complete")
    print(f"requested: {len(tasks)}")
    print(f"successful_panorama_and_crops: {len(successes)}")
    print(f"failures: {len(failures)}")
    print(f"manifest: {relative_to_repo_or_data(manifest_path)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
