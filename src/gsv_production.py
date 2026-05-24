"""Production Google Street View acceptance and image materialization helpers."""

from __future__ import annotations

import json
import logging
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import requests
from PIL import Image, UnidentifiedImageError

try:
    import py360convert
except ImportError:  # pragma: no cover - validated by CLI before crop generation.
    py360convert = None

from fuse_paths import data_dir, data_file, relative_to_repo_or_data


METADATA_ENDPOINT = "https://maps.googleapis.com/maps/api/streetview/metadata"
TILE_ENDPOINT = "https://geo0.ggpht.com/cbk"
GOOGLE_COPYRIGHT_TOKEN = "Google"
MIN_CAPTURE_YEAR = 2018
MAX_POINT_TO_PANO_DISTANCE_M = 20.0
FINAL_TARGET_COUNT = 40_000

TILE_SIZE = 512
DEFAULT_ZOOM_CANDIDATES = (2, 1)
MIN_VALID_PANO_BYTES = 50_000
CROP_SIZE = 512
CROP_FOV = 90
CROP_PITCH_DEG = 15
DIRECTION_SPECS = {"front": 0, "right": 90, "rear": 180, "left": 270}


@dataclass(frozen=True)
class MetadataConfig:
    api_key: str
    target_count: int = FINAL_TARGET_COUNT
    batch_size: int = 500
    workers: int = 8
    throttle_seconds: float = 0.02
    max_retries: int = 3
    timeout_seconds: float = 30.0
    checkpoint_every: int = 500
    max_candidates: int | None = None


@dataclass(frozen=True)
class PanoTask:
    pano_id: str
    source_lat: float
    source_lon: float
    pano_lat: float | None
    pano_lon: float | None


def ensure_gsv_dirs() -> None:
    for key in [
        "streetview_metadata",
        "streetview_logs",
        "streetview_manifests",
        "streetview_panoramas_raw",
        "streetview_crops_front",
        "streetview_crops_right",
        "streetview_crops_rear",
        "streetview_crops_left",
        "streetview_debug",
    ]:
        data_dir(key, create=True)


def read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return pq.read_table(path).to_pylist()


def write_records(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(records)
    pq.write_table(table, path, compression="zstd")


def append_safe_write(records: list[dict[str, Any]], path: Path, key: str) -> None:
    existing = read_records(path)
    merged: dict[Any, dict[str, Any]] = {row[key]: row for row in existing if row.get(key) is not None}
    for row in records:
        merged[row[key]] = row
    write_records(list(merged.values()), path)


def haversine_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius_m = 6_371_008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_m * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def parse_capture_year(capture_date: str | None) -> int | None:
    if not capture_date:
        return None
    try:
        return int(str(capture_date)[:4])
    except ValueError:
        return None


def is_google_imagery(copyright_text: str | None) -> bool:
    return bool(copyright_text and GOOGLE_COPYRIGHT_TOKEN.lower() in copyright_text.lower())


def metadata_url_without_key(lat: float, lon: float) -> str:
    request = requests.Request("GET", METADATA_ENDPOINT, params={"location": f"{lat},{lon}", "source": "outdoor"})
    return request.prepare().url or ""


def call_metadata_endpoint(
    session: requests.Session,
    config: MetadataConfig,
    lat: float,
    lon: float,
) -> tuple[dict[str, Any], int | None, str | None]:
    params = {"location": f"{lat},{lon}", "source": "outdoor", "key": config.api_key}
    last_error: str | None = None
    for attempt in range(1, config.max_retries + 1):
        try:
            response = session.get(METADATA_ENDPOINT, params=params, timeout=config.timeout_seconds)
            content_type = response.headers.get("content-type", "")
            if response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}: {response.text[:300]}")
            if "json" not in content_type.lower():
                return {"status": "NON_JSON_RESPONSE", "error_message": response.text[:500]}, response.status_code, content_type
            return response.json(), response.status_code, content_type
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError, ValueError) as exc:
            last_error = str(exc)
            if attempt >= config.max_retries:
                break
            time.sleep(min(4.0, 0.5 * 2 ** (attempt - 1)))
    return {"status": "REQUEST_FAILED", "error_message": last_error}, None, None


def rejection_reason(record: dict[str, Any], used_pano_ids: set[str]) -> str | None:
    if record.get("status") != "OK":
        return "metadata_not_ok"
    if not record.get("pano_id"):
        return "missing_pano_id"
    if not is_google_imagery(record.get("copyright")):
        return "non_google_imagery"
    if record.get("capture_year") is None:
        return "missing_capture_year"
    if int(record["capture_year"]) < MIN_CAPTURE_YEAR:
        return "capture_year_before_2018"
    distance = record.get("point_to_pano_distance_m")
    if distance is None:
        return "missing_pano_location"
    if float(distance) > MAX_POINT_TO_PANO_DISTANCE_M:
        return "pano_distance_gt_20m"
    if record["pano_id"] in used_pano_ids:
        return "duplicate_pano_id"
    return None


def build_metadata_record(
    source: dict[str, Any],
    metadata: dict[str, Any],
    http_status_code: int | None,
    content_type: str | None,
) -> dict[str, Any]:
    source_lon = float(source["lon"])
    source_lat = float(source["lat"])
    location = metadata.get("location") or {}
    pano_lat = location.get("lat")
    pano_lon = location.get("lng")
    capture_date = metadata.get("date")
    capture_year = parse_capture_year(capture_date)
    distance = None
    if pano_lat is not None and pano_lon is not None:
        distance = haversine_distance_m(source_lon, source_lat, float(pano_lon), float(pano_lat))
    return {
        "candidate_id": int(source["candidate_id"]),
        "candidate_rank": int(source.get("candidate_rank", source["candidate_id"])),
        "grid_id": int(source["grid_id"]) if source.get("grid_id") is not None else None,
        "source_lon": source_lon,
        "source_lat": source_lat,
        "highway_class": str(source["highway_class"]),
        "sampled_rank": int(source["sampled_rank"]),
        "source_road_id": int(source["source_road_id"]),
        "status": metadata.get("status"),
        "pano_id": metadata.get("pano_id"),
        "pano_lat": float(pano_lat) if pano_lat is not None else None,
        "pano_lon": float(pano_lon) if pano_lon is not None else None,
        "capture_date": capture_date,
        "capture_year": capture_year,
        "copyright": metadata.get("copyright"),
        "point_to_pano_distance_m": distance,
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "http_status_code": http_status_code,
        "content_type": content_type,
        "metadata_url_without_key": metadata_url_without_key(source_lat, source_lon),
        "error_message": metadata.get("error_message") or metadata.get("Error_message"),
        "raw_metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    }


def query_one_metadata(source: dict[str, Any], config: MetadataConfig) -> dict[str, Any]:
    with requests.Session() as session:
        metadata, http_status_code, content_type = call_metadata_endpoint(
            session=session,
            config=config,
            lat=float(source["lat"]),
            lon=float(source["lon"]),
        )
    if config.throttle_seconds > 0:
        time.sleep(config.throttle_seconds)
    return build_metadata_record(source, metadata, http_status_code, content_type)


def iter_unprocessed_candidates(candidate_path: Path, checkpoint_path: Path, max_candidates: int | None) -> list[dict[str, Any]]:
    candidates = pq.read_table(candidate_path).to_pylist()
    if max_candidates is not None:
        candidates = candidates[:max_candidates]
    processed_ids = {int(row["candidate_id"]) for row in read_records(checkpoint_path) if row.get("candidate_id") is not None}
    return [row for row in candidates if int(row["candidate_id"]) not in processed_ids]


def accept_metadata_records(records: Iterable[dict[str, Any]], target_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    used_panos: set[str] = set()
    for raw in sorted(records, key=lambda row: int(row.get("candidate_rank") or row["candidate_id"])):
        record = dict(raw)
        reason = rejection_reason(record, used_panos)
        if reason is None and len(accepted) < target_count:
            record["accepted_rank"] = len(accepted) + 1
            record["accepted"] = True
            accepted.append(record)
            used_panos.add(str(record["pano_id"]))
        else:
            record["accepted"] = False
            record["rejection_reason"] = reason or "target_already_met"
            rejected.append(record)
    return accepted, rejected


def run_metadata_acceptance(candidate_path: Path, config: MetadataConfig) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ensure_gsv_dirs()
    checkpoint_path = data_file("gsv_metadata_checkpoint", create_parent=True)
    pending = iter_unprocessed_candidates(candidate_path, checkpoint_path, config.max_candidates)
    logging.info("Pending metadata candidates: %s", len(pending))
    for start in range(0, len(pending), config.batch_size):
        batch = pending[start : start + config.batch_size]
        if not batch:
            continue
        processed_batch: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            future_to_candidate = {executor.submit(query_one_metadata, candidate, config): candidate for candidate in batch}
            for future in as_completed(future_to_candidate):
                processed_batch.append(future.result())
        append_safe_write(processed_batch, checkpoint_path, key="candidate_id")
        all_records = read_records(checkpoint_path)
        accepted, _ = accept_metadata_records(all_records, config.target_count)
        logging.info(
            "Metadata checkpoint rows=%s accepted=%s target=%s",
            len(all_records),
            len(accepted),
            config.target_count,
        )
        if len(accepted) >= config.target_count:
            break

    all_records = read_records(checkpoint_path)
    accepted, rejected = accept_metadata_records(all_records, config.target_count)
    write_records(accepted, data_file("gsv_accepted_metadata", create_parent=True))
    write_records(rejected, data_file("gsv_rejected_metadata", create_parent=True))
    write_diagnostics(accepted, rejected)
    return accepted, rejected


def quantiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "p05": None, "median": None, "mean": None, "p95": None, "max": None}
    arr = np.asarray(values, dtype=float)
    return {
        "min": float(np.min(arr)),
        "p05": float(np.quantile(arr, 0.05)),
        "median": float(np.quantile(arr, 0.5)),
        "mean": float(np.mean(arr)),
        "p95": float(np.quantile(arr, 0.95)),
        "max": float(np.max(arr)),
    }


def write_diagnostics(accepted: list[dict[str, Any]], rejected: list[dict[str, Any]]) -> None:
    rejection_counts = Counter(row.get("rejection_reason", "accepted") for row in rejected)
    write_records(
        [{"rejection_reason": reason, "n": n} for reason, n in sorted(rejection_counts.items())],
        data_file("gsv_metadata_rejection_summary", create_parent=True),
    )
    pano_ids = [row["pano_id"] for row in accepted if row.get("pano_id")]
    duplicate_count = len(pano_ids) - len(set(pano_ids))
    distances = [float(row["point_to_pano_distance_m"]) for row in accepted if row.get("point_to_pano_distance_m") is not None]
    years = Counter(row["capture_year"] for row in accepted if row.get("capture_year") is not None)
    classes = Counter(row["highway_class"] for row in accepted if row.get("highway_class") is not None)
    summary = {
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "unique_pano_ids": len(set(pano_ids)),
        "duplicate_accepted_pano_ids": duplicate_count,
        "metadata_success_rate": len([r for r in accepted + rejected if r.get("status") == "OK"]) / max(1, len(accepted) + len(rejected)),
        **{f"distance_{k}_m": v for k, v in quantiles(distances).items()},
    }
    report_path = data_file("gsv_diagnostics_report", create_parent=True)
    lines = [
        "# Google Street View Metadata Diagnostics",
        "",
        f"- accepted_count: {len(accepted):,}",
        f"- rejected_count: {len(rejected):,}",
        f"- unique_pano_ids: {len(set(pano_ids)):,}",
        f"- duplicate_accepted_pano_ids: {duplicate_count:,}",
        "",
        "## Rejection Reasons",
        *[f"- {reason}: {n:,}" for reason, n in sorted(rejection_counts.items())],
        "",
        "## Capture Years",
        *[f"- {year}: {n:,}" for year, n in sorted(years.items())],
        "",
        "## Road Classes",
        *[f"- {klass}: {n:,}" for klass, n in sorted(classes.items())],
        "",
        "## Pano Distance Summary",
        *[f"- {key}: {value}" for key, value in quantiles(distances).items()],
        "",
        "## Summary",
        *[f"- {key}: {value}" for key, value in summary.items()],
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pano_path(pano_id: str) -> Path:
    return data_dir("streetview_panoramas_raw", create=True) / f"{pano_id}.jpg"


def crop_path(pano_id: str, label: str) -> Path:
    return data_dir(f"streetview_crops_{label}", create=True) / f"{pano_id}_{label}.jpg"


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
    response = session.get(tile_url(pano_id, zoom, x, y), timeout=timeout_seconds, headers={"User-Agent": "Mozilla/5.0 fuse-gsv-production/1.0"})
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or not looks_like_image(content_type, response.content):
        raise RuntimeError(f"non-image tile pano_id={pano_id} zoom={zoom} x={x} y={y} status={response.status_code}")
    try:
        return Image.open(BytesIO(response.content)).convert("RGB")
    except UnidentifiedImageError as exc:
        raise RuntimeError(f"invalid image tile pano_id={pano_id} zoom={zoom} x={x} y={y}") from exc


def stitch_panorama(session: requests.Session, pano_id: str, zoom: int, timeout_seconds: float) -> Image.Image:
    tiles_x, tiles_y = tile_grid_size(zoom)
    panorama = Image.new("RGB", (tiles_x * TILE_SIZE, tiles_y * TILE_SIZE))
    for y in range(tiles_y):
        for x in range(tiles_x):
            panorama.paste(fetch_tile(session, pano_id, zoom, x, y, timeout_seconds), (x * TILE_SIZE, y * TILE_SIZE))
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


def equirectangular_to_perspective(panorama: Image.Image, heading_deg: float) -> Image.Image:
    if py360convert is None:
        raise RuntimeError("py360convert is required for crop generation.")
    crop = py360convert.e2p(
        np.asarray(panorama.convert("RGB")),
        fov_deg=(CROP_FOV, CROP_FOV),
        u_deg=heading_deg,
        v_deg=CROP_PITCH_DEG,
        out_hw=(CROP_SIZE, CROP_SIZE),
    )
    return Image.fromarray(crop).convert("RGB")


def generate_crops_for_panorama(pano_id: str, source_path: Path, overwrite: bool = False) -> bool:
    paths = {label: crop_path(pano_id, label) for label in DIRECTION_SPECS}
    if not overwrite and all(is_valid_image(path, min_bytes=1000) for path in paths.values()):
        return True
    panorama = Image.open(source_path).convert("RGB")
    for label, heading in DIRECTION_SPECS.items():
        equirectangular_to_perspective(panorama, heading).save(paths[label], format="JPEG", quality=92)
    return all(is_valid_image(path, min_bytes=1000) for path in paths.values())


def materialize_one_panorama(
    task: PanoTask,
    zoom_candidates: tuple[int, ...] = DEFAULT_ZOOM_CANDIDATES,
    timeout_seconds: float = 30.0,
    max_retries: int = 2,
    overwrite_crops: bool = False,
) -> dict[str, Any]:
    path = pano_path(task.pano_id)
    download_success = is_valid_image(path, min_bytes=MIN_VALID_PANO_BYTES)
    download_skipped = download_success
    zoom_used = None
    failure_reason = None
    retry_count = 0
    with requests.Session() as session:
        for attempt in range(max_retries + 1):
            if download_success:
                break
            retry_count = attempt
            for zoom in zoom_candidates:
                try:
                    image = stitch_panorama(session, task.pano_id, zoom, timeout_seconds)
                    image.save(path, format="JPEG", quality=95)
                    if not is_valid_image(path, min_bytes=MIN_VALID_PANO_BYTES):
                        raise RuntimeError(f"stitched panorama failed validation at zoom={zoom}")
                    download_success = True
                    zoom_used = zoom
                    break
                except Exception as exc:
                    failure_reason = str(exc)
            if not download_success:
                time.sleep(min(4.0, 0.5 * 2**attempt))
    crops_generated = False
    if download_success:
        try:
            crops_generated = generate_crops_for_panorama(task.pano_id, path, overwrite=overwrite_crops)
        except Exception as exc:
            failure_reason = str(exc)
    return {
        "pano_id": task.pano_id,
        "download_success": bool(download_success),
        "download_skipped": bool(download_skipped),
        "crops_generated": bool(crops_generated),
        "zoom_used": zoom_used,
        "retry_count": retry_count,
        "panorama_path": relative_to_repo_or_data(path) if path.exists() else None,
        "image_size_bytes": path.stat().st_size if path.exists() else None,
        "failure_reason": None if download_success and crops_generated else failure_reason,
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def accepted_to_tasks(records: list[dict[str, Any]], limit: int | None = None) -> list[PanoTask]:
    rows = records[:limit] if limit is not None else records
    return [
        PanoTask(
            pano_id=str(row["pano_id"]),
            source_lat=float(row["source_lat"]),
            source_lon=float(row["source_lon"]),
            pano_lat=float(row["pano_lat"]) if row.get("pano_lat") is not None else None,
            pano_lon=float(row["pano_lon"]) if row.get("pano_lon") is not None else None,
        )
        for row in rows
    ]
