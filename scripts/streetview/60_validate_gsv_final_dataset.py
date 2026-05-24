#!/usr/bin/env python3
"""Validate final GSV metadata and optional image manifests."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "fuse_paths.py").exists():
            return candidate
    raise RuntimeError(f"Could not locate repository root from {start}")


REPO_ROOT = find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(REPO_ROOT / "src"))

from fuse_paths import data_file  # noqa: E402
from gsv_production import FINAL_TARGET_COUNT, MAX_POINT_TO_PANO_DISTANCE_M, MIN_CAPTURE_YEAR, is_google_imagery, read_records  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-path", type=Path, default=data_file("gsv_final_manifest"))
    parser.add_argument("--image-manifest", type=Path, default=data_file("gsv_image_manifest"))
    parser.add_argument("--target-count", type=int, default=FINAL_TARGET_COUNT)
    parser.add_argument("--require-images", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    accepted = read_records(args.accepted_path)
    if len(accepted) != args.target_count:
        errors.append(f"accepted row count is {len(accepted)}, expected {args.target_count}")
    pano_ids = [row.get("pano_id") for row in accepted]
    if len(set(pano_ids)) != len(pano_ids):
        errors.append("accepted metadata contains duplicate pano_id values")
    for row in accepted:
        if row.get("status") != "OK":
            errors.append(f"candidate {row.get('candidate_id')} status is not OK")
        if not is_google_imagery(row.get("copyright")):
            errors.append(f"candidate {row.get('candidate_id')} is not Google imagery")
        if row.get("capture_year") is None or int(row["capture_year"]) < MIN_CAPTURE_YEAR:
            errors.append(f"candidate {row.get('candidate_id')} has invalid capture year")
        if row.get("point_to_pano_distance_m") is None or float(row["point_to_pano_distance_m"]) > MAX_POINT_TO_PANO_DISTANCE_M:
            errors.append(f"candidate {row.get('candidate_id')} exceeds pano distance limit")

    if args.require_images:
        images = read_records(args.image_manifest)
        image_success = {row.get("pano_id") for row in images if row.get("download_success") and row.get("crops_generated")}
        missing = sorted(set(pano_ids) - image_success)
        if missing:
            errors.append(f"{len(missing)} accepted pano_ids are missing valid downloaded panorama/crops")

    if errors:
        print("GSV final validation failed")
        for error in errors[:50]:
            print(f"- {error}")
        if len(errors) > 50:
            print(f"- ... {len(errors) - 50} more errors")
        return 1
    print("GSV final validation passed")
    print(f"accepted_count: {len(accepted)}")
    print(f"unique_pano_ids: {len(set(pano_ids))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
