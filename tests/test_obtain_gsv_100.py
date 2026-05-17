#!/usr/bin/env python3
"""Small-scale Google Street View panorama acquisition benchmark.

This benchmark consumes the metadata-only pilot output and downloads roughly
100 unique panoramas. It keeps the workflow panorama-first: each panorama is
downloaded once, then directional crops are generated locally.
"""

from __future__ import annotations

import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from PIL import Image, UnidentifiedImageError
import numpy as np
import py360convert


REPO_ROOT = Path(__file__).resolve().parents[1]
METADATA_PARQUET = REPO_ROOT / "data/streetview/metadata/gsv_metadata_pilot_1000.parquet"
STREETVIEW_ROOT = REPO_ROOT / "data/streetview"
RAW_PANO_DIR = STREETVIEW_ROOT / "panoramas/raw"
CROP_DIRS = {
    "front": STREETVIEW_ROOT / "crops/front",
    "right": STREETVIEW_ROOT / "crops/right",
    "rear": STREETVIEW_ROOT / "crops/rear",
    "left": STREETVIEW_ROOT / "crops/left",
}
MANIFEST_DIR = STREETVIEW_ROOT / "manifests"
LOG_DIR = STREETVIEW_ROOT / "logs"
DEBUG_DIR = STREETVIEW_ROOT / "debug"
MANIFEST_PARQUET = MANIFEST_DIR / "gsv_download_manifest_100.parquet"
LOG_PATH = LOG_DIR / "gsv_download_100.log"

N_PANOS = int(os.getenv("GSV_BENCHMARK_N_PANOS", "100"))
WORKERS = int(os.getenv("GSV_BENCHMARK_WORKERS", "6"))
EXISTING_PANOS_ONLY = os.getenv("GSV_EXISTING_PANOS_ONLY", "false").lower() == "true"
OVERWRITE_CROPS = os.getenv("GSV_OVERWRITE_CROPS", "false").lower() == "true"
MAX_RETRIES = int(os.getenv("GSV_BENCHMARK_MAX_RETRIES", "2"))
ZOOM_CANDIDATES = [
    int(value)
    for value in os.getenv("GSV_BENCHMARK_ZOOMS", "2,1").split(",")
    if value.strip()
]
REQUEST_TIMEOUT_SECONDS = float(os.getenv("GSV_TILE_TIMEOUT_SECONDS", "30"))
MIN_VALID_PANO_BYTES = int(os.getenv("GSV_MIN_VALID_PANO_BYTES", "50000"))

TILE_SIZE = 512
CROP_SIZE = 512
CROP_FOV = 90
CROP_PITCH_DEG = 15
TILE_ENDPOINT = "https://geo0.ggpht.com/cbk"
DIRECTION_SPECS = {
    "front": 0,
    "right": 90,
    "rear": 180,
    "left": 270,
}


@dataclass(frozen=True)
class PanoTask:
    pano_id: str
    source_lat: float
    source_lon: float
    pano_lat: float | None
    pano_lon: float | None


def ensure_dirs() -> None:
    RAW_PANO_DIR.mkdir(parents=True, exist_ok=True)
    for path in CROP_DIRS.values():
        path.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def read_pano_tasks() -> list[PanoTask]:
    if EXISTING_PANOS_ONLY:
        return [
            PanoTask(
                pano_id=path.stem,
                source_lat=math.nan,
                source_lon=math.nan,
                pano_lat=None,
                pano_lon=None,
            )
            for path in sorted(RAW_PANO_DIR.glob("*.jpg"))[:N_PANOS]
        ]

    if not METADATA_PARQUET.exists():
        raise FileNotFoundError(f"Metadata pilot parquet not found: {METADATA_PARQUET}")

    rows = pq.read_table(
        METADATA_PARQUET,
        columns=["status", "pano_id", "source_lat", "source_lon", "pano_lat", "pano_lon"],
    ).to_pylist()

    tasks: list[PanoTask] = []
    seen: set[str] = set()
    for row in rows:
        pano_id = row.get("pano_id")
        if row.get("status") == "OK" and pano_id and pano_id not in seen:
            tasks.append(
                PanoTask(
                    pano_id=str(pano_id),
                    source_lat=float(row["source_lat"]),
                    source_lon=float(row["source_lon"]),
                    pano_lat=float(row["pano_lat"]) if row.get("pano_lat") is not None else None,
                    pano_lon=float(row["pano_lon"]) if row.get("pano_lon") is not None else None,
                )
            )
            seen.add(str(pano_id))
        if len(tasks) >= N_PANOS:
            break

    return tasks


def haversine_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius_m = 6_371_008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


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
    return request.prepare().url


def tile_grid_size(zoom: int) -> tuple[int, int]:
    return 2**zoom, 2 ** (zoom - 1)


def looks_like_image(content_type: str, content: bytes) -> bool:
    return (
        content_type.lower().startswith("image/")
        or content.startswith(b"\xff\xd8\xff")
        or content.startswith(b"\x89PNG\r\n\x1a\n")
    )


def fetch_tile(session: requests.Session, pano_id: str, zoom: int, x: int, y: int) -> Image.Image:
    url = tile_url(pano_id, zoom, x, y)
    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": "Mozilla/5.0 gsv-100-benchmark/0.1"},
    )
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or not looks_like_image(content_type, response.content):
        preview = response.content[:300].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"non-image tile pano_id={pano_id} zoom={zoom} x={x} y={y} "
            f"status={response.status_code} content_type={content_type} preview={preview!r}"
        )
    try:
        return Image.open(BytesIO(response.content)).convert("RGB")
    except UnidentifiedImageError as exc:
        raise RuntimeError(f"invalid image tile pano_id={pano_id} zoom={zoom} x={x} y={y}") from exc


def stitch_panorama(session: requests.Session, pano_id: str, zoom: int) -> Image.Image:
    tiles_x, tiles_y = tile_grid_size(zoom)
    panorama = Image.new("RGB", (tiles_x * TILE_SIZE, tiles_y * TILE_SIZE))
    for y in range(tiles_y):
        for x in range(tiles_x):
            panorama.paste(fetch_tile(session, pano_id, zoom, x, y), (x * TILE_SIZE, y * TILE_SIZE))
    return panorama


def is_valid_image(path: Path, min_bytes: int = 1) -> bool:
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def pano_path(pano_id: str) -> Path:
    return RAW_PANO_DIR / f"{pano_id}.jpg"


def crop_path(pano_id: str, label: str) -> Path:
    return CROP_DIRS[label] / f"{pano_id}_{label}.jpg"


def resolve_tile_compatible_pano_id(task: PanoTask) -> str | None:
    try:
        import streetview

        panos = streetview.search_panoramas(task.source_lat, task.source_lon)
    except Exception as exc:
        logging.warning("Alternate pano lookup failed pano_id=%s reason=%s", task.pano_id, exc)
        return None

    if not panos:
        return None

    target_lat = task.pano_lat if task.pano_lat is not None else task.source_lat
    target_lon = task.pano_lon if task.pano_lon is not None else task.source_lon
    ranked = sorted(
        panos,
        key=lambda pano: haversine_distance_m(target_lon, target_lat, float(pano.lon), float(pano.lat)),
    )
    alternate = ranked[0].pano_id
    if alternate == task.pano_id:
        return None

    logging.info(
        "Resolved alternate tile-compatible pano_id original=%s alternate=%s distance_to_metadata_pano_m=%.2f",
        task.pano_id,
        alternate,
        haversine_distance_m(target_lon, target_lat, float(ranked[0].lon), float(ranked[0].lat)),
    )
    return alternate


def equirectangular_to_perspective(
    panorama: Image.Image,
    heading_deg: float,
    fov_deg: float = CROP_FOV,
    out_size: int = CROP_SIZE,
) -> Image.Image:
    crop = py360convert.e2p(
        np.asarray(panorama.convert("RGB")),
        fov_deg=(fov_deg, fov_deg),
        u_deg=heading_deg,
        v_deg=CROP_PITCH_DEG,
        out_hw=(out_size, out_size),
    )
    return Image.fromarray(crop).convert("RGB")


def crop_paths_for_pano(pano_id: str) -> dict[str, Path]:
    return {label: crop_path(pano_id, label) for label in DIRECTION_SPECS}


def crop_distinctness_score(paths: dict[str, Path]) -> float:
    arrays = {
        label: np.asarray(Image.open(path).convert("RGB").resize((128, 128)), dtype=np.float32)
        for label, path in paths.items()
    }
    labels = list(arrays)
    scores = []
    for i, left in enumerate(labels):
        for right in labels[i + 1:]:
            scores.append(float(np.mean(np.abs(arrays[left] - arrays[right]))))
    return min(scores) if scores else 0.0


def rear_edge_discontinuity_score(path: Path) -> float:
    arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    return float(np.mean(np.abs(arr[:, 0, :] - arr[:, -1, :])))


def create_debug_contact_sheet(pano_id: str, source_path: Path, paths: dict[str, Path]) -> Path:
    panorama = Image.open(source_path).convert("RGB")
    pano_preview = panorama.resize((CROP_SIZE * 2, CROP_SIZE), Image.Resampling.LANCZOS)
    sheet = Image.new("RGB", (CROP_SIZE * 2, CROP_SIZE * 3), "white")
    sheet.paste(pano_preview, (0, 0))
    positions = {
        "front": (0, CROP_SIZE),
        "right": (CROP_SIZE, CROP_SIZE),
        "rear": (0, CROP_SIZE * 2),
        "left": (CROP_SIZE, CROP_SIZE * 2),
    }
    for label, position in positions.items():
        sheet.paste(Image.open(paths[label]).convert("RGB").resize((CROP_SIZE, CROP_SIZE)), position)
    out_path = DEBUG_DIR / f"{pano_id}_projection_validation.jpg"
    sheet.save(out_path, format="JPEG", quality=92)
    return out_path


def generate_crops_for_panorama(
    pano_id: str,
    source_path: Path,
    overwrite: bool = OVERWRITE_CROPS,
    write_debug_sheet: bool = EXISTING_PANOS_ONLY,
) -> tuple[bool, dict[str, Any]]:
    paths = crop_paths_for_pano(pano_id)
    if not overwrite and all(is_valid_image(path, min_bytes=1000) for path in paths.values()):
        metrics = {
            "crops_regenerated": False,
            "debug_contact_sheet": None,
            "crop_distinctness_score": crop_distinctness_score(paths),
            "rear_edge_discontinuity_score": rear_edge_discontinuity_score(paths["rear"]),
        }
        if write_debug_sheet:
            metrics["debug_contact_sheet"] = str(create_debug_contact_sheet(pano_id, source_path, paths).relative_to(REPO_ROOT))
        return True, metrics

    panorama = Image.open(source_path).convert("RGB")
    for label, heading in DIRECTION_SPECS.items():
        out_path = paths[label]
        crop = equirectangular_to_perspective(panorama, heading_deg=heading)
        crop.save(out_path, format="JPEG", quality=92)
    success = all(is_valid_image(path, min_bytes=1000) for path in paths.values())
    metrics = {
        "crops_regenerated": True,
        "debug_contact_sheet": None,
        "crop_distinctness_score": crop_distinctness_score(paths) if success else None,
        "rear_edge_discontinuity_score": rear_edge_discontinuity_score(paths["rear"]) if success else None,
    }
    if success and write_debug_sheet:
        metrics["debug_contact_sheet"] = str(create_debug_contact_sheet(pano_id, source_path, paths).relative_to(REPO_ROOT))
    return success, metrics


def generate_missing_crops(pano_id: str, source_path: Path) -> bool:
    success, _ = generate_crops_for_panorama(pano_id, source_path, overwrite=False, write_debug_sheet=False)
    return success


def acquire_panorama(task: PanoTask) -> tuple[bool, str, Path, int | None, int, str | None, bool]:
    acquisition_pano_id = task.pano_id
    path = pano_path(acquisition_pano_id)
    retry_count = 0
    zoom_used: int | None = None
    failure_reason: str | None = None
    download_success = False
    download_skipped = False

    candidate_pano_ids = [task.pano_id]
    with requests.Session() as session:
        candidate_index = 0
        while candidate_index < len(candidate_pano_ids) and not download_success:
            acquisition_pano_id = candidate_pano_ids[candidate_index]
            path = pano_path(acquisition_pano_id)

            if is_valid_image(path, min_bytes=MIN_VALID_PANO_BYTES):
                download_success = True
                download_skipped = True
                logging.info("Reusing cached panorama pano_id=%s path=%s", acquisition_pano_id, path)
                break

            if EXISTING_PANOS_ONLY:
                failure_reason = f"missing or invalid cached panorama: {path}"
                break

            if path.exists():
                logging.warning("Existing panorama appears invalid; redownloading pano_id=%s path=%s", acquisition_pano_id, path)

            for attempt in range(MAX_RETRIES + 1):
                retry_count = max(retry_count, attempt)
                for zoom in ZOOM_CANDIDATES:
                    try:
                        image = stitch_panorama(session, acquisition_pano_id, zoom)
                        image.save(path, format="JPEG", quality=95)
                        if not is_valid_image(path, min_bytes=MIN_VALID_PANO_BYTES):
                            raise RuntimeError(f"stitched panorama failed validation at zoom={zoom}")
                        zoom_used = zoom
                        download_success = True
                        break
                    except Exception as exc:
                        failure_reason = str(exc)
                        logging.warning(
                            "Panorama attempt failed original_pano_id=%s acquisition_pano_id=%s attempt=%s zoom=%s reason=%s",
                            task.pano_id,
                            acquisition_pano_id,
                            attempt,
                            zoom,
                            failure_reason,
                        )
                if download_success:
                    break
                time.sleep(min(2.0, 0.5 * 2**attempt))

            if not download_success and candidate_index == 0:
                alternate = resolve_tile_compatible_pano_id(task)
                if alternate and alternate not in candidate_pano_ids:
                    candidate_pano_ids.append(alternate)
            candidate_index += 1

    return download_success, acquisition_pano_id, path, zoom_used, retry_count, failure_reason, download_skipped


def download_or_reuse_panorama(task: PanoTask) -> dict[str, Any]:
    started = time.perf_counter()
    acquisition_pano_id = task.pano_id
    path = pano_path(acquisition_pano_id)
    retry_count = 0
    zoom_used: int | None = None
    failure_reason: str | None = None
    download_success = False
    download_skipped = False
    crop_metrics: dict[str, Any] = {
        "crops_regenerated": False,
        "debug_contact_sheet": None,
        "crop_distinctness_score": None,
        "rear_edge_discontinuity_score": None,
    }

    try:
        download_success, acquisition_pano_id, path, zoom_used, retry_count, failure_reason, download_skipped = acquire_panorama(task)
        crops_generated, crop_metrics = generate_crops_for_panorama(
            acquisition_pano_id,
            path,
            overwrite=OVERWRITE_CROPS,
            write_debug_sheet=EXISTING_PANOS_ONLY,
        ) if download_success else (False, crop_metrics)
    except Exception as exc:
        failure_reason = str(exc)
        crops_generated = False
        logging.exception("Panorama task failed pano_id=%s", task.pano_id)

    elapsed_seconds = time.perf_counter() - started
    return {
        "pano_id": task.pano_id,
        "acquisition_pano_id": acquisition_pano_id,
        "download_success": bool(download_success),
        "crops_generated": bool(crops_generated),
        "retry_count": int(retry_count),
        "zoom_used": zoom_used,
        "panorama_path": str(path.relative_to(REPO_ROOT)) if path.exists() else None,
        "image_size_bytes": path.stat().st_size if path.exists() else None,
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "failure_reason": None if download_success and crops_generated else failure_reason,
        "elapsed_seconds": elapsed_seconds,
        "download_skipped": bool(download_skipped),
        **crop_metrics,
    }


def write_manifest(records: list[dict[str, Any]]) -> None:
    table = pa.Table.from_pylist(records)
    pq.write_table(table, MANIFEST_PARQUET, compression="zstd")


def main() -> int:
    configure_logging()
    tasks = read_pano_tasks()
    if not tasks:
        raise RuntimeError("No valid pano_id values found in metadata pilot output.")

    started = time.perf_counter()
    logging.info(
        "Starting GSV panorama benchmark for %s unique panoramas with %s workers, zoom candidates=%s, existing_only=%s, overwrite_crops=%s",
        len(tasks),
        WORKERS,
        ZOOM_CANDIDATES,
        EXISTING_PANOS_ONLY,
        OVERWRITE_CROPS,
    )

    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        future_to_task = {executor.submit(download_or_reuse_panorama, task): task for task in tasks}
        for i, future in enumerate(as_completed(future_to_task), start=1):
            record = future.result()
            records.append(record)
            if i == 1 or i % 10 == 0 or i == len(tasks):
                successes = sum(1 for item in records if item["download_success"])
                crop_successes = sum(1 for item in records if item["crops_generated"])
                logging.info(
                    "Completed %s/%s panorama tasks; downloads=%s crops=%s latest=%s success=%s",
                    i,
                    len(tasks),
                    successes,
                    crop_successes,
                    record["pano_id"],
                    record["download_success"],
                )

    records.sort(key=lambda item: item["pano_id"])
    write_manifest(records)

    total_elapsed = time.perf_counter() - started
    successes = [record for record in records if record["download_success"]]
    failures = [record for record in records if not record["download_success"]]
    crop_successes = [record for record in records if record["crops_generated"]]
    crop_regenerated = [record for record in records if record.get("crops_regenerated")]
    skipped_downloads = [record for record in records if record.get("download_skipped")]
    sizes = [record["image_size_bytes"] for record in successes if record.get("image_size_bytes")]
    retry_counts = [record["retry_count"] for record in records]
    distinctness_scores = [record["crop_distinctness_score"] for record in records if record.get("crop_distinctness_score") is not None]
    rear_edge_scores = [record["rear_edge_discontinuity_score"] for record in records if record.get("rear_edge_discontinuity_score") is not None]
    mean_size = sum(sizes) / len(sizes) if sizes else 0
    throughput = len(successes) / total_elapsed if total_elapsed > 0 else 0

    if not MANIFEST_PARQUET.exists() or MANIFEST_PARQUET.stat().st_size <= 0:
        raise RuntimeError(f"Manifest was not written: {MANIFEST_PARQUET}")

    print("GSV 100-panorama benchmark complete")
    print(f"requested_panoramas: {len(tasks)}")
    print(f"successful_panorama_downloads: {len(successes)}")
    print(f"failed_downloads: {len(failures)}")
    print(f"mean_panorama_file_size_bytes: {mean_size:.1f}")
    print(f"approx_throughput_panos_per_second: {throughput:.4f}")
    print(f"crop_generation_success_rate: {len(crop_successes) / len(records):.4f}")
    print(f"crops_regenerated: {len(crop_regenerated)}")
    print(f"panorama_downloads_skipped: {len(skipped_downloads)}")
    print(f"retry_count_min_mean_max: {min(retry_counts)} / {sum(retry_counts) / len(retry_counts):.2f} / {max(retry_counts)}")
    if distinctness_scores:
        print(f"crop_distinctness_min_mean: {min(distinctness_scores):.2f} / {sum(distinctness_scores) / len(distinctness_scores):.2f}")
    if rear_edge_scores:
        print(f"rear_edge_discontinuity_min_mean_max: {min(rear_edge_scores):.2f} / {sum(rear_edge_scores) / len(rear_edge_scores):.2f} / {max(rear_edge_scores):.2f}")
    print(f"manifest: {MANIFEST_PARQUET.relative_to(REPO_ROOT)}")
    print(f"log: {LOG_PATH.relative_to(REPO_ROOT)}")
    if EXISTING_PANOS_ONLY:
        debug_sheets = [record.get("debug_contact_sheet") for record in records if record.get("debug_contact_sheet")]
        print(f"debug_contact_sheets: {len(debug_sheets)}")
        print(f"debug_dir: {DEBUG_DIR.relative_to(REPO_ROOT)}")
    if failures:
        print("failures:")
        for record in failures[:10]:
            print(f"  {record['pano_id']}: {record['failure_reason']}")
    return 0 if len(successes) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
