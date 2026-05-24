#!/usr/bin/env python3
"""Prototype one-point Google Street View panorama acquisition workflow.

This script intentionally processes exactly one sampled point. It validates the
metadata-first, panorama-first workflow before any large-scale acquisition is
implemented.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from PIL import Image, UnidentifiedImageError


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
from fuse_paths import data_dir, data_file, relative_to_repo_or_data  # noqa: E402

SAMPLES_PARQUET = data_file("samples_global_parquet")
METADATA_PARQUET = data_file("streetview_metadata_test")

OUTPUT_DIRS = {
    "metadata": data_dir("streetview_metadata"),
    "panoramas_raw": data_dir("streetview_panoramas_raw"),
    "crops_front": data_dir("streetview_crops_front"),
    "crops_right": data_dir("streetview_crops_right"),
    "crops_rear": data_dir("streetview_crops_rear"),
    "crops_left": data_dir("streetview_crops_left"),
    "previews": data_dir("streetview_previews"),
    "logs": data_dir("streetview_logs"),
}

METADATA_ENDPOINT = "https://maps.googleapis.com/maps/api/streetview/metadata"
CROP_SIZE = 512
CROP_FOV = 90
PANORAMA_ZOOM = int(os.getenv("GSV_PANORAMA_ZOOM", "4"))
TILE_SIZE = 512
TILE_ENDPOINTS = {
    "geo_cpk": "https://geo0.ggpht.com/cbk",
    "streetviewpixels": "https://streetviewpixels-pa.googleapis.com/v1/tile",
    "cbk": "https://cbk0.google.com/cbk",
}


@dataclass(frozen=True)
class SamplePoint:
    point_id: int
    grid_id: int
    lon: float
    lat: float
    highway_class: str
    sampled_rank: int


def ensure_output_dirs() -> None:
    for path in OUTPUT_DIRS.values():
        path.mkdir(parents=True, exist_ok=True)


def configure_logging() -> Path:
    ensure_output_dirs()
    log_path = OUTPUT_DIRS["logs"] / "gsv_one_test.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="a", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return log_path


def read_first_sample_point(path: Path = SAMPLES_PARQUET) -> SamplePoint:
    if not path.exists():
        raise FileNotFoundError(f"Sample parquet not found: {path}")

    table = pq.read_table(
        path,
        columns=["point_id", "grid_id", "lon", "lat", "highway_class", "sampled_rank"],
    ).slice(0, 1)
    if table.num_rows != 1:
        raise ValueError(f"Expected at least one sampled point in {path}")

    row = table.to_pylist()[0]
    return SamplePoint(
        point_id=int(row["point_id"]),
        grid_id=int(row["grid_id"]),
        lon=float(row["lon"]),
        lat=float(row["lat"]),
        highway_class=str(row["highway_class"]),
        sampled_rank=int(row["sampled_rank"]),
    )


def fetch_streetview_metadata(point: SamplePoint, api_key: str) -> dict[str, Any]:
    params = {
        "location": f"{point.lat},{point.lon}",
        "source": "outdoor",
        "key": api_key,
    }
    response = requests.get(METADATA_ENDPOINT, params=params, timeout=30)
    response.raise_for_status()
    metadata = response.json()
    metadata["_metadata_url_without_key"] = requests.Request(
        "GET",
        METADATA_ENDPOINT,
        params={k: v for k, v in params.items() if k != "key"},
    ).prepare().url
    return metadata


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


def zoom_candidates(start_zoom: int) -> list[int]:
    candidates = [start_zoom, 2, 1]
    out: list[int] = []
    for zoom in candidates:
        if zoom >= 1 and zoom not in out:
            out.append(zoom)
    return out


def tile_grid_size(zoom: int) -> tuple[int, int]:
    return 2**zoom, 2 ** (zoom - 1)


def make_tile_url(endpoint_name: str, pano_id: str, zoom: int, x: int, y: int) -> str:
    if endpoint_name == "streetviewpixels":
        request = requests.Request(
            "GET",
            TILE_ENDPOINTS[endpoint_name],
            params={"panoid": pano_id, "x": x, "y": y, "zoom": zoom},
        )
    elif endpoint_name == "geo_cpk":
        request = requests.Request(
            "GET",
            TILE_ENDPOINTS[endpoint_name],
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
    elif endpoint_name == "cbk":
        request = requests.Request(
            "GET",
            TILE_ENDPOINTS[endpoint_name],
            params={"output": "tile", "panoid": pano_id, "zoom": zoom, "x": x, "y": y},
        )
    else:
        raise ValueError(f"Unknown tile endpoint: {endpoint_name}")
    return request.prepare().url


def sanitize_for_filename(value: str, max_len: int = 120) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:max_len]


def response_preview(content: bytes, max_bytes: int = 500) -> str:
    return content[:max_bytes].decode("utf-8", errors="replace")


def looks_like_image(content_type: str, content: bytes) -> bool:
    lowered = content_type.lower()
    if lowered.startswith("image/"):
        return True
    return content.startswith(b"\xff\xd8\xff") or content.startswith(b"\x89PNG\r\n\x1a\n")


def save_non_image_response(
    *,
    pano_id: str,
    endpoint_name: str,
    zoom: int,
    x: int,
    y: int,
    status_code: int | None,
    content_type: str,
    url: str,
    content: bytes,
) -> Path:
    stem = sanitize_for_filename(
        f"tile_non_image_{pano_id}_{endpoint_name}_z{zoom}_x{x}_y{y}_http{status_code}"
    )
    body_path = OUTPUT_DIRS["logs"] / f"{stem}.body"
    meta_path = OUTPUT_DIRS["logs"] / f"{stem}.json"
    body_path.write_bytes(content)
    meta_path.write_text(
        json.dumps(
            {
                "pano_id": pano_id,
                "endpoint": endpoint_name,
                "zoom": zoom,
                "x": x,
                "y": y,
                "url": url,
                "status_code": status_code,
                "content_type": content_type,
                "first_500_chars": response_preview(content),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    logging.error("Saved non-image tile response body to %s", body_path)
    return body_path


def fetch_tile_image(
    *,
    pano_id: str,
    endpoint_name: str,
    zoom: int,
    x: int,
    y: int,
) -> Image.Image:
    url = make_tile_url(endpoint_name, pano_id, zoom, x, y)
    logging.info("Fetching tile pano_id=%s endpoint=%s zoom=%s x=%s y=%s url=%s", pano_id, endpoint_name, zoom, x, y, url)
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 gsv-one-prototype/0.1"},
    )
    content_type = response.headers.get("content-type", "")
    preview = response_preview(response.content)
    logging.info(
        "Tile response pano_id=%s endpoint=%s zoom=%s x=%s y=%s status=%s content_type=%s first_bytes=%r first_500_chars=%r",
        pano_id,
        endpoint_name,
        zoom,
        x,
        y,
        response.status_code,
        content_type,
        response.content[:16],
        preview,
    )

    if response.status_code != 200 or not looks_like_image(content_type, response.content):
        save_non_image_response(
            pano_id=pano_id,
            endpoint_name=endpoint_name,
            zoom=zoom,
            x=x,
            y=y,
            status_code=response.status_code,
            content_type=content_type,
            url=url,
            content=response.content,
        )
        raise RuntimeError(
            "Tile endpoint returned non-image response "
            f"endpoint={endpoint_name} zoom={zoom} x={x} y={y} "
            f"status={response.status_code} content_type={content_type}"
        )

    try:
        return Image.open(BytesIO(response.content)).convert("RGB")
    except UnidentifiedImageError:
        save_non_image_response(
            pano_id=pano_id,
            endpoint_name=endpoint_name,
            zoom=zoom,
            x=x,
            y=y,
            status_code=response.status_code,
            content_type=content_type,
            url=url,
            content=response.content,
        )
        raise


def stitch_panorama_tiles(pano_id: str, endpoint_name: str, zoom: int) -> Image.Image:
    tiles_x, tiles_y = tile_grid_size(zoom)
    panorama = Image.new("RGB", (tiles_x * TILE_SIZE, tiles_y * TILE_SIZE))
    for y in range(tiles_y):
        for x in range(tiles_x):
            tile = fetch_tile_image(
                pano_id=pano_id,
                endpoint_name=endpoint_name,
                zoom=zoom,
                x=x,
                y=y,
            )
            panorama.paste(tile, (x * TILE_SIZE, y * TILE_SIZE))
    return panorama


def download_panorama(pano_id: str, out_path: Path) -> Path:
    failures: list[str] = []
    for zoom in zoom_candidates(PANORAMA_ZOOM):
        for endpoint_name in TILE_ENDPOINTS:
            logging.info("Trying panorama tile acquisition pano_id=%s endpoint=%s zoom=%s", pano_id, endpoint_name, zoom)
            try:
                image = stitch_panorama_tiles(pano_id=pano_id, endpoint_name=endpoint_name, zoom=zoom)
            except Exception as exc:
                message = f"endpoint={endpoint_name} zoom={zoom} failed: {exc}"
                failures.append(message)
                logging.exception("Panorama tile acquisition failed: %s", message)
                continue

            if image.mode != "RGB":
                image = image.convert("RGB")
            image.save(out_path, format="JPEG", quality=95)
            logging.info(
                "Panorama written pano_id=%s endpoint=%s zoom=%s path=%s size=%s bytes=%s",
                pano_id,
                endpoint_name,
                zoom,
                out_path,
                image.size,
                out_path.stat().st_size,
            )
            return out_path

    raise RuntimeError("All panorama tile acquisition attempts failed: " + " | ".join(failures))
    return out_path


def equirectangular_to_perspective_fallback(
    panorama: Image.Image,
    heading_deg: float,
    fov_deg: float = CROP_FOV,
    out_size: int = CROP_SIZE,
) -> Image.Image:
    import numpy as np

    pano = np.asarray(panorama.convert("RGB"))
    pano_h, pano_w = pano.shape[:2]

    coords = np.linspace(-1.0, 1.0, out_size, dtype=np.float64)
    xx, yy = np.meshgrid(coords, -coords)
    fov_rad = math.radians(fov_deg)
    z = np.full_like(xx, 1.0 / math.tan(fov_rad / 2.0))

    norm = np.sqrt(xx * xx + yy * yy + z * z)
    x = xx / norm
    y = yy / norm
    z = z / norm

    heading = math.radians(heading_deg)
    x_rot = x * math.cos(heading) + z * math.sin(heading)
    z_rot = -x * math.sin(heading) + z * math.cos(heading)

    lon = np.arctan2(x_rot, z_rot)
    lat = np.arcsin(y)

    src_x = (lon / (2 * math.pi) + 0.5) * pano_w
    src_y = (0.5 - lat / math.pi) * pano_h

    src_x = np.mod(src_x, pano_w)
    src_y = np.clip(src_y, 0, pano_h - 1)

    x0 = np.floor(src_x).astype(np.int64)
    x1 = (x0 + 1) % pano_w
    y0 = np.floor(src_y).astype(np.int64)
    y1 = np.clip(y0 + 1, 0, pano_h - 1)
    wx = src_x - x0
    wy = src_y - y0

    top = pano[y0, x0] * (1 - wx[..., None]) + pano[y0, x1] * wx[..., None]
    bottom = pano[y1, x0] * (1 - wx[..., None]) + pano[y1, x1] * wx[..., None]
    sampled = top * (1 - wy[..., None]) + bottom * wy[..., None]
    return Image.fromarray(np.clip(sampled, 0, 255).astype(np.uint8), mode="RGB")


def equirectangular_to_perspective(
    panorama: Image.Image,
    heading_deg: float,
    fov_deg: float = CROP_FOV,
    out_size: int = CROP_SIZE,
) -> Image.Image:
    try:
        import numpy as np
        import py360convert

        crop = py360convert.e2p(
            np.asarray(panorama.convert("RGB")),
            fov_deg=(fov_deg, fov_deg),
            u_deg=heading_deg,
            v_deg=0,
            out_hw=(out_size, out_size),
        )
        return Image.fromarray(crop).convert("RGB")
    except ModuleNotFoundError:
        logging.info("py360convert is not installed; using local perspective crop fallback.")
        return equirectangular_to_perspective_fallback(
            panorama,
            heading_deg=heading_deg,
            fov_deg=fov_deg,
            out_size=out_size,
        )


def generate_crops(pano_path: Path, pano_id: str) -> dict[str, Path]:
    panorama = Image.open(pano_path).convert("RGB")
    specs = {
        "front": (0, OUTPUT_DIRS["crops_front"] / f"{pano_id}_front.jpg"),
        "right": (90, OUTPUT_DIRS["crops_right"] / f"{pano_id}_right.jpg"),
        "rear": (180, OUTPUT_DIRS["crops_rear"] / f"{pano_id}_rear.jpg"),
        "left": (270, OUTPUT_DIRS["crops_left"] / f"{pano_id}_left.jpg"),
    }

    out_paths: dict[str, Path] = {}
    for label, (heading, path) in specs.items():
        crop = equirectangular_to_perspective(panorama, heading_deg=heading)
        crop.save(path, format="JPEG", quality=92)
        out_paths[label] = path
    return out_paths


def create_contact_sheet(crop_paths: dict[str, Path], pano_id: str) -> Path:
    sheet = Image.new("RGB", (CROP_SIZE * 2, CROP_SIZE * 2), "white")
    positions = {
        "front": (0, 0),
        "right": (CROP_SIZE, 0),
        "rear": (0, CROP_SIZE),
        "left": (CROP_SIZE, CROP_SIZE),
    }
    for label, position in positions.items():
        crop = Image.open(crop_paths[label]).convert("RGB").resize((CROP_SIZE, CROP_SIZE))
        sheet.paste(crop, position)

    out_path = OUTPUT_DIRS["previews"] / f"{pano_id}_contact_sheet.jpg"
    sheet.save(out_path, format="JPEG", quality=92)
    return out_path


def build_metadata_record(
    point: SamplePoint,
    metadata: dict[str, Any],
    image_path: Path | None = None,
) -> dict[str, Any]:
    location = metadata.get("location") or {}
    pano_lat = location.get("lat")
    pano_lon = location.get("lng")
    image_exists = bool(image_path and image_path.exists())
    image_size_bytes = image_path.stat().st_size if image_exists and image_path else None

    point_to_pano_distance_m = None
    if pano_lon is not None and pano_lat is not None:
        point_to_pano_distance_m = haversine_distance_m(
            point.lon,
            point.lat,
            float(pano_lon),
            float(pano_lat),
        )

    return {
        "point_id": point.point_id,
        "grid_id": point.grid_id,
        "source_lon": point.lon,
        "source_lat": point.lat,
        "highway_class": point.highway_class,
        "sampled_rank": point.sampled_rank,
        "pano_id": metadata.get("pano_id"),
        "pano_lat": float(pano_lat) if pano_lat is not None else None,
        "pano_lon": float(pano_lon) if pano_lon is not None else None,
        "capture_date": metadata.get("date"),
        "copyright": metadata.get("copyright"),
        "status": metadata.get("status"),
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "image_path": relative_to_repo_or_data(image_path) if image_path else None,
        "image_exists": image_exists,
        "image_size_bytes": image_size_bytes,
        "point_to_pano_distance_m": point_to_pano_distance_m,
        "metadata_url_without_key": metadata.get("_metadata_url_without_key"),
        "raw_metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    }


def write_metadata_parquet(record: dict[str, Any], path: Path = METADATA_PARQUET) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([record])
    pq.write_table(table, path, compression="zstd")


def validate_outputs(
    metadata: dict[str, Any],
    pano_path: Path,
    crop_paths: dict[str, Path],
    contact_sheet_path: Path,
) -> None:
    checks = {
        "metadata_status_ok": metadata.get("status") == "OK",
        "panorama_downloaded": pano_path.exists() and pano_path.stat().st_size > 0,
        "metadata_parquet_written": METADATA_PARQUET.exists() and METADATA_PARQUET.stat().st_size > 0,
        "contact_sheet_generated": contact_sheet_path.exists() and contact_sheet_path.stat().st_size > 0,
        "all_crops_generated": all(path.exists() and path.stat().st_size > 0 for path in crop_paths.values()),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError(f"Validation failed: {', '.join(failed)}")


def main() -> int:
    log_path = configure_logging()
    logging.info("Starting one-point GSV prototype validation.")

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    override_pano_id = os.getenv("GSV_PANO_ID")
    if not api_key and not override_pano_id:
        logging.error("GOOGLE_MAPS_API_KEY is not set; stopping before metadata request.")
        return 1

    point = read_first_sample_point()
    logging.info(
        "Loaded point_id=%s grid_id=%s lat=%.7f lon=%.7f class=%s",
        point.point_id,
        point.grid_id,
        point.lat,
        point.lon,
        point.highway_class,
    )

    if override_pano_id:
        logging.warning("Using GSV_PANO_ID override; metadata endpoint is bypassed for panorama-stage debugging.")
        metadata = {
            "status": "OK",
            "pano_id": override_pano_id,
            "location": {"lat": point.lat, "lng": point.lon},
            "date": None,
            "copyright": None,
            "_metadata_url_without_key": None,
            "metadata_bypassed_for_panorama_debug": True,
        }
    else:
        try:
            metadata = fetch_streetview_metadata(point, api_key=api_key)
        except Exception as exc:
            logging.exception("Street View metadata request failed; no panorama download attempted.")
            failure_record = build_metadata_record(point, {"status": "METADATA_REQUEST_FAILED", "error": str(exc)})
            write_metadata_parquet(failure_record)
            return 1

    if metadata.get("status") != "OK":
        logging.warning("Street View metadata status is %s; no panorama download attempted.", metadata.get("status"))
        write_metadata_parquet(build_metadata_record(point, metadata))
        return 0

    pano_id = metadata.get("pano_id")
    if not pano_id:
        logging.error("Metadata status OK but no pano_id was returned; no panorama download attempted.")
        write_metadata_parquet(build_metadata_record(point, metadata))
        return 1

    pano_path = OUTPUT_DIRS["panoramas_raw"] / f"{pano_id}.jpg"
    download_panorama(pano_id, pano_path)
    crop_paths = generate_crops(pano_path, pano_id)
    contact_sheet_path = create_contact_sheet(crop_paths, pano_id)

    record = build_metadata_record(point, metadata, image_path=pano_path)
    write_metadata_parquet(record)
    validate_outputs(metadata, pano_path, crop_paths, contact_sheet_path)

    print("GSV one-point prototype complete")
    print(f"point_id: {point.point_id}")
    print(f"pano_id: {pano_id}")
    print(f"capture_date: {metadata.get('date')}")
    print(f"metadata_parquet: {relative_to_repo_or_data(METADATA_PARQUET)}")
    print(f"panorama: {relative_to_repo_or_data(pano_path)}")
    print(f"contact_sheet: {relative_to_repo_or_data(contact_sheet_path)}")
    print("crops:")
    for label, path in crop_paths.items():
        print(f"  {label}: {relative_to_repo_or_data(path)}")
    print(f"log: {relative_to_repo_or_data(log_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
