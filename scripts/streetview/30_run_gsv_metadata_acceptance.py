#!/usr/bin/env python3
"""Run resumable production GSV metadata acceptance for oversampled candidates."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "fuse_paths.py").exists():
            return candidate
    raise RuntimeError(f"Could not locate repository root from {start}")


REPO_ROOT = find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(REPO_ROOT / "src"))

from fuse_paths import data_file, relative_to_repo_or_data  # noqa: E402
from gsv_production import FINAL_TARGET_COUNT, MetadataConfig, run_metadata_acceptance  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-path", type=Path, default=data_file("gsv_candidate_pool_parquet"))
    parser.add_argument("--target-count", type=int, default=FINAL_TARGET_COUNT)
    parser.add_argument("--max-candidates", type=int, default=None, help="Pilot/debug limit; omit for production.")
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("GSV_METADATA_BATCH_SIZE", "500")))
    parser.add_argument("--workers", type=int, default=int(os.getenv("GSV_METADATA_WORKERS", "8")))
    parser.add_argument("--throttle-seconds", type=float, default=float(os.getenv("GSV_METADATA_THROTTLE_SECONDS", "0.02")))
    parser.add_argument("--max-retries", type=int, default=int(os.getenv("GSV_METADATA_MAX_RETRIES", "3")))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.getenv("GSV_METADATA_TIMEOUT_SECONDS", "30")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logging.error("GOOGLE_MAPS_API_KEY is not set; refusing to query metadata.")
        return 2
    if not args.candidate_path.exists():
        logging.error("Candidate parquet does not exist: %s", args.candidate_path)
        return 2

    config = MetadataConfig(
        api_key=api_key,
        target_count=args.target_count,
        batch_size=args.batch_size,
        workers=args.workers,
        throttle_seconds=args.throttle_seconds,
        max_retries=args.max_retries,
        timeout_seconds=args.timeout_seconds,
        max_candidates=args.max_candidates,
    )
    accepted, rejected = run_metadata_acceptance(args.candidate_path, config)
    print("GSV metadata acceptance complete")
    print(f"accepted: {len(accepted)}")
    print(f"rejected: {len(rejected)}")
    print(f"accepted_metadata: {relative_to_repo_or_data(data_file('gsv_accepted_metadata'))}")
    print(f"rejected_metadata: {relative_to_repo_or_data(data_file('gsv_rejected_metadata'))}")
    print(f"diagnostics_report: {relative_to_repo_or_data(data_file('gsv_diagnostics_report'))}")
    return 0 if len(accepted) == args.target_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
