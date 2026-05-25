#!/usr/bin/env python3
"""Validate the large Street View panorama and semantic crop corpus."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from PIL import Image


DEFAULT_METADATA_PATH = Path("/members/dhnyu/fusedata/streetview/final/gsv_seoul_metadata_final_40000.parquet")
DEFAULT_LARGE_ROOT = Path("/members/dhnyu/fusedatalarge")
TARGET_COUNT = 40_000
VIEWS = ("front", "left", "right", "rear")
MIN_VALID_PANO_BYTES = 50_000
MIN_VALID_CROP_BYTES = 1_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--large-root", type=Path, default=DEFAULT_LARGE_ROOT)
    parser.add_argument("--target-count", type=int, default=TARGET_COUNT)
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_LARGE_ROOT / "streetview" / "qc" / "gsv_large_image_completion_validation.json",
    )
    return parser.parse_args()


def is_valid_image(path: Path, min_bytes: int) -> tuple[bool, str | None, tuple[int, int] | None]:
    if not path.exists():
        return False, "missing", None
    size = path.stat().st_size
    if size < min_bytes:
        return False, f"too_small:{size}", None
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            return True, None, image.size
    except Exception as exc:
        return False, f"{type(exc).__name__}:{str(exc)[:160]}", None


def read_checkpoint_latest(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            latest[str(row["pano_id"])] = row
    return latest


def main() -> int:
    args = parse_args()
    streetview_root = args.large_root / "streetview"
    raw_dir = streetview_root / "panoramas" / "raw"
    crop_dirs = {view: streetview_root / "crops" / view for view in VIEWS}
    manifest_path = streetview_root / "manifests" / "gsv_large_image_acquisition_manifest.parquet"
    crop_manifest_path = streetview_root / "manifests" / "gsv_large_semantic_crop_manifest.parquet"
    checkpoint_path = streetview_root / "manifests" / "gsv_large_image_checkpoint.jsonl"

    rows = pq.read_table(args.metadata_path, columns=["accepted_rank", "point_id", "pano_id"]).to_pylist()
    pano_ids = [str(row["pano_id"]) for row in rows]
    expected_ids = set(pano_ids)
    errors: list[str] = []

    if len(rows) != args.target_count:
        errors.append(f"metadata rows={len(rows)}, expected={args.target_count}")
    if len(expected_ids) != len(pano_ids):
        errors.append(f"metadata duplicate pano_ids={len(pano_ids) - len(expected_ids)}")

    raw_files = sorted(raw_dir.glob("*.jpg"))
    crop_files = {view: sorted(crop_dirs[view].glob("*.jpg")) for view in VIEWS}
    raw_ids = {path.stem for path in raw_files}
    crop_ids = {
        view: {path.name.rsplit(f"_{view}.jpg", 1)[0] for path in files}
        for view, files in crop_files.items()
    }

    if len(raw_files) != args.target_count:
        errors.append(f"raw panorama count={len(raw_files)}, expected={args.target_count}")
    for view in VIEWS:
        if len(crop_files[view]) != args.target_count:
            errors.append(f"{view} crop count={len(crop_files[view])}, expected={args.target_count}")
    if len(raw_ids) != len(raw_files):
        errors.append(f"duplicate raw pano filenames={len(raw_files) - len(raw_ids)}")
    for view in VIEWS:
        if len(crop_ids[view]) != len(crop_files[view]):
            errors.append(f"duplicate {view} crop filenames={len(crop_files[view]) - len(crop_ids[view])}")

    missing_raw = sorted(expected_ids - raw_ids)
    extra_raw = sorted(raw_ids - expected_ids)
    if missing_raw:
        errors.append(f"missing raw panoramas={len(missing_raw)}")
    if extra_raw:
        errors.append(f"extra raw panoramas={len(extra_raw)}")
    for view in VIEWS:
        missing = sorted(expected_ids - crop_ids[view])
        extra = sorted(crop_ids[view] - expected_ids)
        if missing:
            errors.append(f"missing {view} crops={len(missing)}")
        if extra:
            errors.append(f"extra {view} crops={len(extra)}")

    invalid_raw = []
    for path in raw_files:
        ok, reason, _ = is_valid_image(path, MIN_VALID_PANO_BYTES)
        if not ok:
            invalid_raw.append({"path": str(path), "reason": reason})
    invalid_crops: dict[str, list[dict[str, str | None]]] = {view: [] for view in VIEWS}
    for view in VIEWS:
        for path in crop_files[view]:
            ok, reason, _ = is_valid_image(path, MIN_VALID_CROP_BYTES)
            if not ok:
                invalid_crops[view].append({"path": str(path), "reason": reason})
    if invalid_raw:
        errors.append(f"invalid raw panoramas={len(invalid_raw)}")
    for view in VIEWS:
        if invalid_crops[view]:
            errors.append(f"invalid {view} crops={len(invalid_crops[view])}")

    manifest_rows = pq.read_table(manifest_path).to_pylist() if manifest_path.exists() else []
    crop_manifest_rows = pq.read_table(crop_manifest_path).to_pylist() if crop_manifest_path.exists() else []
    manifest_success_ids = {str(row.get("pano_id")) for row in manifest_rows if row.get("success")}
    if len(manifest_rows) != args.target_count:
        errors.append(f"image manifest rows={len(manifest_rows)}, expected={args.target_count}")
    if manifest_success_ids != expected_ids:
        errors.append(f"image manifest success ids mismatch={len(expected_ids ^ manifest_success_ids)}")
    if len(crop_manifest_rows) != args.target_count * len(VIEWS):
        errors.append(f"crop manifest rows={len(crop_manifest_rows)}, expected={args.target_count * len(VIEWS)}")

    checkpoint_latest = read_checkpoint_latest(checkpoint_path)
    checkpoint_success_ids = {pid for pid, row in checkpoint_latest.items() if row.get("success")}
    if checkpoint_success_ids != expected_ids:
        errors.append(f"checkpoint success ids mismatch={len(expected_ids ^ checkpoint_success_ids)}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": not errors,
        "errors": errors,
        "metadata_rows": len(rows),
        "metadata_unique_pano_ids": len(expected_ids),
        "raw_panorama_count": len(raw_files),
        "crop_counts": {view: len(crop_files[view]) for view in VIEWS},
        "invalid_raw_examples": invalid_raw[:20],
        "invalid_crop_examples": {view: invalid_crops[view][:20] for view in VIEWS},
        "manifest_rows": len(manifest_rows),
        "crop_manifest_rows": len(crop_manifest_rows),
        "checkpoint_latest_successes": len(checkpoint_success_ids),
        "manifest_path": str(manifest_path),
        "crop_manifest_path": str(crop_manifest_path),
        "checkpoint_path": str(checkpoint_path),
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if errors:
        print("GSV large image completion validation failed")
        for error in errors[:50]:
            print(f"- {error}")
        print(f"report: {args.report_path}")
        return 1
    print("GSV large image completion validation passed")
    print(f"raw_panoramas: {len(raw_files)}")
    for view in VIEWS:
        print(f"{view}_crops: {len(crop_files[view])}")
    print(f"report: {args.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
