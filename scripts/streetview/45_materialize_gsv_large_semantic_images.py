#!/usr/bin/env python3
"""Materialize production Street View panoramas and semantic rectangular crops.

This large-storage image stage reads the validated 40k metadata parquet and
writes imagery under /members/dhnyu/fusedatalarge. Crop generation is a direct
rectangular extraction from the panorama image: no spherical reprojection,
perspective rendering, cubemap conversion, heading alignment, or wraparound.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from PIL import Image, UnidentifiedImageError


TILE_ENDPOINT = "https://geo0.ggpht.com/cbk"
TILE_SIZE = 512
DEFAULT_ZOOM_CANDIDATES = (2, 1)
MIN_VALID_PANO_BYTES = 50_000
MIN_VALID_CROP_BYTES = 1_000
JPEG_QUALITY_PANO = 95
JPEG_QUALITY_CROP = 92
DEFAULT_WORKERS = 6
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
USER_AGENT = "Mozilla/5.0 fuse-gsv-large-materialization/1.0"


@dataclass(frozen=True)
class CropWindow:
    label: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float


SEMANTIC_WINDOWS = (
    CropWindow("left", 0.05, 0.35, 0.30, 0.90),
    CropWindow("front", 0.25, 0.55, 0.30, 0.90),
    CropWindow("right", 0.45, 0.75, 0.30, 0.90),
    CropWindow("rear", 0.65, 0.95, 0.30, 0.90),
)
VIEW_ORDER = ("front", "left", "right", "rear")


@dataclass(frozen=True)
class ImageTask:
    accepted_rank: int
    point_id: int
    pano_id: str


def find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "src" / "fuse_paths.py").exists():
            return candidate
    raise RuntimeError(f"Could not locate repository root from {start}")


REPO_ROOT = find_repo_root(Path(__file__).resolve())
DEFAULT_METADATA_PATH = Path("/members/dhnyu/fusedata/streetview/final/gsv_seoul_metadata_final_40000.parquet")
DEFAULT_LARGE_ROOT = Path("/members/dhnyu/fusedatalarge")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--large-root", type=Path, default=DEFAULT_LARGE_ROOT)
    parser.add_argument("--limit", type=int, default=None, help="Debug limit; omit for full production.")
    parser.add_argument("--workers", type=int, default=int(os.getenv("GSV_LARGE_IMAGE_WORKERS", str(DEFAULT_WORKERS))))
    parser.add_argument("--zooms", default=os.getenv("GSV_LARGE_IMAGE_ZOOMS", "2,1"))
    parser.add_argument("--timeout-seconds", type=float, default=float(os.getenv("GSV_LARGE_TILE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))))
    parser.add_argument("--max-retries", type=int, default=int(os.getenv("GSV_LARGE_IMAGE_MAX_RETRIES", str(DEFAULT_MAX_RETRIES))))
    parser.add_argument("--overwrite-panoramas", action="store_true")
    parser.add_argument("--overwrite-crops", action="store_true")
    parser.add_argument("--recheck-completed", action="store_true", help="Validate checkpointed successes instead of trusting prior checkpoint rows.")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def streetview_dirs(large_root: Path) -> dict[str, Path]:
    root = large_root / "streetview"
    dirs = {
        "root": root,
        "panoramas_raw": root / "panoramas" / "raw",
        "crops_front": root / "crops" / "front",
        "crops_left": root / "crops" / "left",
        "crops_right": root / "crops" / "right",
        "crops_rear": root / "crops" / "rear",
        "manifests": root / "manifests",
        "logs": root / "logs",
        "qc": root / "qc",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def pano_path(dirs: dict[str, Path], pano_id: str) -> Path:
    return dirs["panoramas_raw"] / f"{pano_id}.jpg"


def crop_path(dirs: dict[str, Path], pano_id: str, label: str) -> Path:
    return dirs[f"crops_{label}"] / f"{pano_id}_{label}.jpg"


def is_valid_image(path: Path, min_bytes: int = 1) -> bool:
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def tile_url(pano_id: str, zoom: int, x: int, y: int) -> str:
    request = requests.Request(
        "GET",
        TILE_ENDPOINT,
        params={
            "cb_client": "maps_sv.tactile",
            "authuser": "0",
            "hl": "en",
            "panoid": pano_id,
            "output": "tile",
            "x": x,
            "y": y,
            "zoom": zoom,
            "nbt": "",
            "fover": "2",
        },
    )
    return request.prepare().url or ""


def tile_grid_size(zoom: int) -> tuple[int, int]:
    return 2**zoom, 2 ** (zoom - 1)


def looks_like_image(content_type: str, content: bytes) -> bool:
    return content_type.lower().startswith("image/") or content.startswith(b"\xff\xd8\xff") or content.startswith(b"\x89PNG\r\n\x1a\n")


def fetch_tile(session: requests.Session, pano_id: str, zoom: int, x: int, y: int, timeout_seconds: float) -> Image.Image:
    response = session.get(tile_url(pano_id, zoom, x, y), timeout=timeout_seconds, headers={"User-Agent": USER_AGENT})
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or not looks_like_image(content_type, response.content):
        body = response.text[:200] if response.content else ""
        raise RuntimeError(f"non-image tile zoom={zoom} x={x} y={y} status={response.status_code} content_type={content_type} body={body}")
    try:
        return Image.open(BytesIO(response.content)).convert("RGB")
    except UnidentifiedImageError as exc:
        raise RuntimeError(f"invalid image tile zoom={zoom} x={x} y={y}") from exc


def stitch_panorama(session: requests.Session, pano_id: str, zoom: int, timeout_seconds: float) -> Image.Image:
    tiles_x, tiles_y = tile_grid_size(zoom)
    panorama = Image.new("RGB", (tiles_x * TILE_SIZE, tiles_y * TILE_SIZE))
    for y in range(tiles_y):
        for x in range(tiles_x):
            panorama.paste(fetch_tile(session, pano_id, zoom, x, y, timeout_seconds), (x * TILE_SIZE, y * TILE_SIZE))
    return panorama


def normalized_to_pixel_box(window: CropWindow, width: int, height: int) -> tuple[int, int, int, int]:
    left = round(window.x_min * width)
    right = round(window.x_max * width)
    top = round((1.0 - window.y_max) * height)
    bottom = round((1.0 - window.y_min) * height)
    return left, top, right, bottom


def generate_semantic_crops(dirs: dict[str, Path], pano_id: str, source_path: Path, overwrite: bool) -> dict[str, Any]:
    crop_paths = {window.label: crop_path(dirs, pano_id, window.label) for window in SEMANTIC_WINDOWS}
    if not overwrite and all(is_valid_image(path, MIN_VALID_CROP_BYTES) for path in crop_paths.values()):
        sizes = {label: image_size(path) for label, path in crop_paths.items()}
        return {"success": True, "skipped": True, "crop_sizes": sizes, "failure_reason": None}

    try:
        panorama = Image.open(source_path).convert("RGB")
        for window in SEMANTIC_WINDOWS:
            crop = panorama.crop(normalized_to_pixel_box(window, *panorama.size))
            crop.save(crop_paths[window.label], format="JPEG", quality=JPEG_QUALITY_CROP)
    except Exception as exc:
        return {"success": False, "skipped": False, "crop_sizes": {}, "failure_reason": str(exc)}

    valid = {label: is_valid_image(path, MIN_VALID_CROP_BYTES) for label, path in crop_paths.items()}
    sizes = {label: image_size(path) for label, path in crop_paths.items()}
    if not all(valid.values()):
        failed = [label for label, ok in valid.items() if not ok]
        return {"success": False, "skipped": False, "crop_sizes": sizes, "failure_reason": "invalid crop(s): " + ",".join(failed)}
    return {"success": True, "skipped": False, "crop_sizes": sizes, "failure_reason": None}


def download_panorama(
    dirs: dict[str, Path],
    task: ImageTask,
    zoom_candidates: tuple[int, ...],
    timeout_seconds: float,
    max_retries: int,
    overwrite: bool,
) -> dict[str, Any]:
    path = pano_path(dirs, task.pano_id)
    if not overwrite and is_valid_image(path, MIN_VALID_PANO_BYTES):
        return {
            "success": True,
            "skipped": True,
            "zoom_used": None,
            "retry_count": 0,
            "failure_reason": None,
            "panorama_size": image_size(path),
        }

    failure_reason = None
    zoom_used = None
    retry_count = 0
    with requests.Session() as session:
        for attempt in range(max_retries + 1):
            retry_count = attempt
            for zoom in zoom_candidates:
                try:
                    image = stitch_panorama(session, task.pano_id, zoom, timeout_seconds)
                    tmp_path = path.with_suffix(path.suffix + ".tmp")
                    image.save(tmp_path, format="JPEG", quality=JPEG_QUALITY_PANO)
                    if not is_valid_image(tmp_path, MIN_VALID_PANO_BYTES):
                        raise RuntimeError(f"stitched panorama failed validation at zoom={zoom}")
                    tmp_path.replace(path)
                    zoom_used = zoom
                    return {
                        "success": True,
                        "skipped": False,
                        "zoom_used": zoom_used,
                        "retry_count": retry_count,
                        "failure_reason": None,
                        "panorama_size": image.size,
                    }
                except Exception as exc:
                    failure_reason = str(exc)
                    tmp_path = path.with_suffix(path.suffix + ".tmp")
                    if tmp_path.exists():
                        tmp_path.unlink()
            if attempt < max_retries:
                time.sleep(min(4.0, 0.75 * 2**attempt))
    return {
        "success": False,
        "skipped": False,
        "zoom_used": zoom_used,
        "retry_count": retry_count,
        "failure_reason": failure_reason,
        "panorama_size": None,
    }


def process_one(
    dirs: dict[str, Path],
    task: ImageTask,
    zoom_candidates: tuple[int, ...],
    timeout_seconds: float,
    max_retries: int,
    overwrite_panoramas: bool,
    overwrite_crops: bool,
) -> dict[str, Any]:
    started = utc_now()
    pano = download_panorama(dirs, task, zoom_candidates, timeout_seconds, max_retries, overwrite_panoramas)
    crops = {"success": False, "skipped": False, "crop_sizes": {}, "failure_reason": None}
    if pano["success"]:
        crops = generate_semantic_crops(dirs, task.pano_id, pano_path(dirs, task.pano_id), overwrite=overwrite_crops)

    panorama_file = pano_path(dirs, task.pano_id)
    crop_files = {label: crop_path(dirs, task.pano_id, label) for label in VIEW_ORDER}
    success = bool(pano["success"] and crops["success"])
    failure_reason = None if success else (crops["failure_reason"] or pano["failure_reason"])
    crop_sizes = crops.get("crop_sizes") or {}
    return {
        "accepted_rank": task.accepted_rank,
        "point_id": task.point_id,
        "pano_id": task.pano_id,
        "success": success,
        "download_success": bool(pano["success"]),
        "download_skipped": bool(pano["skipped"]),
        "crops_generated": bool(crops["success"]),
        "crops_skipped": bool(crops["skipped"]),
        "zoom_used": pano["zoom_used"],
        "retry_count": pano["retry_count"],
        "panorama_path": str(panorama_file) if panorama_file.exists() else None,
        "panorama_size": list(pano["panorama_size"]) if pano["panorama_size"] else None,
        "panorama_bytes": panorama_file.stat().st_size if panorama_file.exists() else None,
        "crop_paths": {label: str(path) for label, path in crop_files.items()},
        "crop_sizes": {label: list(size) if size else None for label, size in crop_sizes.items()},
        "crop_bytes": {label: path.stat().st_size if path.exists() else None for label, path in crop_files.items()},
        "failure_reason": failure_reason,
        "started_at": started,
        "finished_at": utc_now(),
    }


def read_tasks(metadata_path: Path, limit: int | None) -> list[ImageTask]:
    table = pq.read_table(metadata_path, columns=["accepted_rank", "point_id", "pano_id"])
    rows = sorted(table.to_pylist(), key=lambda row: int(row["accepted_rank"]))
    if limit is not None:
        rows = rows[:limit]
    pano_ids = [row["pano_id"] for row in rows]
    if len(pano_ids) != len(set(pano_ids)):
        raise RuntimeError("Input metadata contains duplicated pano_id values.")
    return [ImageTask(accepted_rank=int(row["accepted_rank"]), point_id=int(row["point_id"]), pano_id=str(row["pano_id"])) for row in rows]


def load_latest_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return latest
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            latest[str(row["pano_id"])] = row
    return latest


def checkpoint_success_is_usable(row: dict[str, Any], dirs: dict[str, Path]) -> bool:
    if not row.get("success"):
        return False
    pano_id = str(row["pano_id"])
    if not is_valid_image(pano_path(dirs, pano_id), MIN_VALID_PANO_BYTES):
        return False
    return all(is_valid_image(crop_path(dirs, pano_id, label), MIN_VALID_CROP_BYTES) for label in VIEW_ORDER)


def write_jsonl(path: Path, row: dict[str, Any], lock: threading.Lock) -> None:
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_manifests(dirs: dict[str, Path], records: list[dict[str, Any]]) -> dict[str, Path]:
    manifest_path = dirs["manifests"] / "gsv_large_image_acquisition_manifest.parquet"
    crop_manifest_path = dirs["manifests"] / "gsv_large_semantic_crop_manifest.parquet"
    failure_path = dirs["logs"] / "gsv_large_image_failures.jsonl"
    qc_path = dirs["qc"] / "gsv_large_image_qc_summary.json"

    ordered = sorted(records, key=lambda row: int(row["accepted_rank"]))
    if ordered:
        pq.write_table(pa.Table.from_pylist(ordered), manifest_path, compression="zstd")
    crop_rows = []
    for row in ordered:
        for window in SEMANTIC_WINDOWS:
            crop_rows.append(
                {
                    "accepted_rank": row["accepted_rank"],
                    "point_id": row["point_id"],
                    "pano_id": row["pano_id"],
                    "view": window.label,
                    "x_min": window.x_min,
                    "x_max": window.x_max,
                    "y_min": window.y_min,
                    "y_max": window.y_max,
                    "crop_path": row["crop_paths"].get(window.label),
                    "crop_size": row["crop_sizes"].get(window.label),
                    "crop_bytes": row["crop_bytes"].get(window.label),
                    "crop_valid": bool(row.get("crops_generated")),
                }
            )
    if crop_rows:
        pq.write_table(pa.Table.from_pylist(crop_rows), crop_manifest_path, compression="zstd")

    failures = [row for row in ordered if not row.get("success")]
    with failure_path.open("w", encoding="utf-8") as handle:
        for row in failures:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    pano_count = sum(1 for row in ordered if row.get("download_success"))
    crop_counts = {
        label: sum(1 for row in ordered if is_valid_image(Path(row["crop_paths"][label]), MIN_VALID_CROP_BYTES))
        for label in VIEW_ORDER
    }
    crop_size_counts = Counter(tuple(row["crop_sizes"].get("front") or []) for row in ordered if row.get("crop_sizes", {}).get("front"))
    qc = {
        "generated_at": utc_now(),
        "records": len(ordered),
        "successes": sum(1 for row in ordered if row.get("success")),
        "failures": len(failures),
        "panorama_success_count": pano_count,
        "crop_counts": crop_counts,
        "unique_pano_ids": len({row["pano_id"] for row in ordered}),
        "duplicate_pano_ids": len(ordered) - len({row["pano_id"] for row in ordered}),
        "front_crop_size_distribution": {str(key): value for key, value in crop_size_counts.items()},
        "semantic_windows": [asdict(window) for window in SEMANTIC_WINDOWS],
        "manifest_path": str(manifest_path),
        "crop_manifest_path": str(crop_manifest_path),
        "failure_log_path": str(failure_path),
    }
    qc_path.write_text(json.dumps(qc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest": manifest_path, "crop_manifest": crop_manifest_path, "failure_log": failure_path, "qc": qc_path}


def directory_size_bytes(path: Path) -> int:
    total = 0
    for file in path.rglob("*"):
        if file.is_file():
            total += file.stat().st_size
    return total


def main() -> int:
    args = parse_args()
    dirs = streetview_dirs(args.large_root.expanduser())
    log_path = dirs["logs"] / "gsv_large_image_materialization.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
    )

    if not args.metadata_path.exists():
        logging.error("Metadata parquet does not exist: %s", args.metadata_path)
        return 2

    zoom_candidates = tuple(int(value) for value in str(args.zooms).split(",") if value.strip())
    tasks = read_tasks(args.metadata_path.expanduser(), args.limit)
    checkpoint_path = dirs["manifests"] / "gsv_large_image_checkpoint.jsonl"
    latest = load_latest_checkpoint(checkpoint_path)
    completed = {
        pano_id
        for pano_id, row in latest.items()
        if checkpoint_success_is_usable(row, dirs) or (row.get("success") and not args.recheck_completed)
    }
    pending = [task for task in tasks if task.pano_id not in completed]
    records = [latest[task.pano_id] for task in tasks if task.pano_id in latest and task.pano_id in completed]

    layout_path = dirs["manifests"] / "gsv_large_semantic_crop_layout.json"
    layout_path.write_text(
        json.dumps(
            {
                "description": "Direct rectangular semantic panorama crops. No projection, heading alignment, or wraparound.",
                "coordinate_system": {"x_axis": "left edge = 0, right edge = 1", "y_axis": "bottom edge = 0, top edge = 1"},
                "windows": [asdict(window) for window in SEMANTIC_WINDOWS],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    logging.info("Large image materialization root: %s", dirs["root"])
    logging.info("Tasks=%s completed_from_checkpoint=%s pending=%s workers=%s zooms=%s", len(tasks), len(completed), len(pending), args.workers, zoom_candidates)
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_one,
                dirs,
                task,
                zoom_candidates,
                args.timeout_seconds,
                args.max_retries,
                args.overwrite_panoramas,
                args.overwrite_crops,
            ): task
            for task in pending
        }
        for i, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "accepted_rank": task.accepted_rank,
                    "point_id": task.point_id,
                    "pano_id": task.pano_id,
                    "success": False,
                    "download_success": False,
                    "crops_generated": False,
                    "failure_reason": str(exc),
                    "started_at": None,
                    "finished_at": utc_now(),
                }
            records.append(row)
            write_jsonl(checkpoint_path, row, lock)
            if i == 1 or i % 100 == 0 or i == len(pending):
                successes = sum(1 for record in records if record.get("success"))
                logging.info("Processed pending %s/%s total_records=%s successes=%s latest=%s success=%s", i, len(pending), len(records), successes, task.pano_id, row.get("success"))

    paths = write_manifests(dirs, records)
    total_success = sum(1 for row in records if row.get("success"))
    total_failure = len(records) - total_success
    storage = {name: directory_size_bytes(path) for name, path in dirs.items() if name in {"panoramas_raw", "crops_front", "crops_left", "crops_right", "crops_rear", "manifests", "logs", "qc"}}

    print("GSV large semantic image materialization complete")
    print(f"tasks: {len(tasks)}")
    print(f"successes: {total_success}")
    print(f"failures: {total_failure}")
    print(f"checkpoint: {checkpoint_path}")
    print(f"manifest: {paths['manifest']}")
    print(f"crop_manifest: {paths['crop_manifest']}")
    print(f"failure_log: {paths['failure_log']}")
    print(f"qc_summary: {paths['qc']}")
    print("storage_bytes:")
    for key, value in sorted(storage.items()):
        print(f"  {key}: {value}")
    return 0 if total_failure == 0 and total_success == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
