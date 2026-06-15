#!/usr/bin/env python3
"""Validate FUSE repository/data path configuration without running pipelines."""

from __future__ import annotations

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

from fuse_paths import (  # noqa: E402
    DIRECTORIES,
    FILES,
    data_dir,
    data_file,
    data_root,
    ensure_core_dirs,
    environment_summary,
)


REQUIRED_DIRECTORY_KEYS = [
    "geodata",
    "osm",
    "osm_raw",
    "osm_canonical",
    "osm_sampling",
    "sampling_global",
    "streetview",
    "streetview_final",
    "streetview_metadata",
    "streetview_panoramas_raw",
    "streetview_crops_front",
    "streetview_crops_right",
    "streetview_crops_rear",
    "streetview_crops_left",
    "streetview_manifests",
]

EXPECTED_DISCOVERABLE_FILES = [
    "seoul_boundary",
    "osm_roads_canonical",
    "samples_global_parquet",
    "gsv_final_manifest",
    "gsv_image_manifest",
]


def can_write(directory: Path) -> bool:
    probe = directory / ".fuse_write_test"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def main() -> int:
    if os.getenv("FUSE_VALIDATE_CREATE_DIRS", "true").lower() == "true":
        ensure_core_dirs()

    print("FUSE path validation")
    for key, value in environment_summary().items():
        print(f"  {key}: {value}")

    root = data_root(create=True)
    print(f"  data_root_writable: {can_write(root)}")

    missing_required_dirs = [key for key in REQUIRED_DIRECTORY_KEYS if not data_dir(key).is_dir()]
    optional_missing_dirs = [
        key for key in DIRECTORIES if key not in REQUIRED_DIRECTORY_KEYS and not data_dir(key).is_dir()
    ]
    unwritable_dirs = [key for key in REQUIRED_DIRECTORY_KEYS if data_dir(key).is_dir() and not can_write(data_dir(key))]
    missing_files = [key for key in EXPECTED_DISCOVERABLE_FILES if not data_file(key).exists()]

    print(f"  configured_directories: {len(DIRECTORIES)}")
    print(f"  configured_files: {len(FILES)}")
    print(f"  missing_required_directories: {', '.join(missing_required_dirs) if missing_required_dirs else 'none'}")
    print(f"  optional_missing_directories: {', '.join(optional_missing_dirs) if optional_missing_dirs else 'none'}")
    print(f"  unwritable_directories: {', '.join(unwritable_dirs) if unwritable_dirs else 'none'}")
    print(f"  missing_expected_files: {', '.join(missing_files) if missing_files else 'none'}")

    if missing_required_dirs or unwritable_dirs:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
