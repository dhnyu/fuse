#!/usr/bin/env python3
"""Metadata-only Google Street View pilot for sampled Seoul road points.

This script intentionally does not download panoramas or generate crops. It
queries the official Street View metadata endpoint for the first 1000 sampled
points and writes pilot diagnostics as parquet.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
from fuse_paths import data_dir, data_file, relative_to_repo_or_data  # noqa: E402

SAMPLES_PARQUET = data_file("samples_global_parquet")
METADATA_DIR = data_dir("streetview_metadata")
LOG_DIR = data_dir("streetview_logs")

PILOT_SIZE = int(os.getenv("GSV_METADATA_PILOT_SIZE", "1000"))
REQUEST_THROTTLE_SECONDS = float(os.getenv("GSV_METADATA_THROTTLE_SECONDS", "0.05"))
MAX_RETRIES = int(os.getenv("GSV_METADATA_MAX_RETRIES", "3"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("GSV_METADATA_TIMEOUT_SECONDS", "30"))

METADATA_ENDPOINT = "https://maps.googleapis.com/maps/api/streetview/metadata"
METADATA_PARQUET = METADATA_DIR / "gsv_metadata_pilot_1000.parquet"
SUMMARY_PARQUET = METADATA_DIR / "gsv_metadata_pilot_summary.parquet"
DUPLICATION_PARQUET = METADATA_DIR / "gsv_pano_duplication_counts.parquet"
YEAR_DISTRIBUTION_PARQUET = METADATA_DIR / "gsv_capture_year_distribution.parquet"


def ensure_dirs() -> None:
    data_dir("streetview_metadata", create=True)
    data_dir("streetview_logs", create=True)


def configure_logging() -> Path:
    ensure_dirs()
    log_path = LOG_DIR / "gsv_metadata_pilot.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, mode="a", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return log_path


def read_sample_points(path: Path = SAMPLES_PARQUET, n: int = PILOT_SIZE) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Sample parquet not found: {path}")

    table = pq.read_table(
        path,
        columns=["point_id", "grid_id", "lon", "lat", "highway_class", "sampled_rank"],
    ).slice(0, n)
    rows = table.to_pylist()
    if len(rows) != n:
        raise ValueError(f"Expected {n} sampled points, found {len(rows)} in {path}")
    return rows


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


def parse_capture_year(capture_date: str | None) -> int | None:
    if not capture_date:
        return None
    try:
        return int(str(capture_date)[:4])
    except ValueError:
        return None


def metadata_url_without_key(lat: float, lon: float) -> str:
    request = requests.Request(
        "GET",
        METADATA_ENDPOINT,
        params={"location": f"{lat},{lon}", "source": "outdoor"},
    )
    return request.prepare().url


def call_metadata_endpoint(
    *,
    session: requests.Session,
    api_key: str,
    lat: float,
    lon: float,
) -> tuple[dict[str, Any], int | None, str | None]:
    params = {
        "location": f"{lat},{lon}",
        "source": "outdoor",
        "key": api_key,
    }
    last_error: str | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(METADATA_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            status_code = response.status_code
            content_type = response.headers.get("content-type", "")

            if status_code >= 500:
                last_error = f"HTTP {status_code}: {response.text[:300]}"
                raise requests.HTTPError(last_error)

            if "json" not in content_type.lower():
                return (
                    {
                        "status": "NON_JSON_RESPONSE",
                        "error_message": response.text[:500],
                    },
                    status_code,
                    content_type,
                )

            return response.json(), status_code, content_type
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            last_error = str(exc)
            if attempt >= MAX_RETRIES:
                break
            sleep_seconds = min(2.0, 0.5 * 2 ** (attempt - 1))
            logging.warning(
                "Metadata request failed at attempt %s/%s for lat=%.7f lon=%.7f: %s; retrying in %.1fs",
                attempt,
                MAX_RETRIES,
                lat,
                lon,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
        except ValueError as exc:
            return (
                {
                    "status": "INVALID_JSON",
                    "error_message": str(exc),
                },
                response.status_code if "response" in locals() else None,
                response.headers.get("content-type", "") if "response" in locals() else None,
            )

    return {"status": "REQUEST_FAILED", "error_message": last_error}, None, None


def build_record(
    *,
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

    point_to_pano_distance_m = None
    if pano_lat is not None and pano_lon is not None:
        point_to_pano_distance_m = haversine_distance_m(
            source_lon,
            source_lat,
            float(pano_lon),
            float(pano_lat),
        )

    return {
        "point_id": int(source["point_id"]),
        "grid_id": int(source["grid_id"]),
        "source_lon": source_lon,
        "source_lat": source_lat,
        "highway_class": str(source["highway_class"]),
        "sampled_rank": int(source["sampled_rank"]),
        "status": metadata.get("status"),
        "pano_id": metadata.get("pano_id"),
        "pano_lat": float(pano_lat) if pano_lat is not None else None,
        "pano_lon": float(pano_lon) if pano_lon is not None else None,
        "capture_date": capture_date,
        "capture_year": capture_year,
        "copyright": metadata.get("copyright"),
        "point_to_pano_distance_m": point_to_pano_distance_m,
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "http_status_code": http_status_code,
        "content_type": content_type,
        "metadata_url_without_key": metadata_url_without_key(source_lat, source_lon),
        "error_message": metadata.get("error_message") or metadata.get("error_message".upper()),
        "raw_metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    }


def write_table(records: list[dict[str, Any]], path: Path) -> pa.Table:
    table = pa.Table.from_pylist(records)
    pq.write_table(table, path, compression="zstd")
    return table


def numeric_values(records: list[dict[str, Any]], key: str) -> list[float]:
    return [float(record[key]) for record in records if record.get(key) is not None]


def median(values: list[float]) -> float | None:
    if not values:
        return None
    values = sorted(values)
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    total_points = len(records)
    successes = [record for record in records if record.get("status") == "OK"]
    failures = total_points - len(successes)
    pano_ids = [record["pano_id"] for record in successes if record.get("pano_id")]
    unique_pano_ids = len(set(pano_ids))
    distances = numeric_values(successes, "point_to_pano_distance_m")
    capture_years = [int(record["capture_year"]) for record in successes if record.get("capture_year") is not None]

    return {
        "total_points": total_points,
        "metadata_successes": len(successes),
        "metadata_failures": failures,
        "unique_pano_ids": unique_pano_ids,
        "pano_reuse_ratio": (1 - unique_pano_ids / len(pano_ids)) if pano_ids else None,
        "missing_pano_fraction": 1 - len(pano_ids) / total_points if total_points else None,
        "mean_point_to_pano_distance_m": (sum(distances) / len(distances)) if distances else None,
        "median_point_to_pano_distance_m": median(distances),
        "min_capture_year": min(capture_years) if capture_years else None,
        "median_capture_year": median([float(year) for year in capture_years]),
        "max_capture_year": max(capture_years) if capture_years else None,
    }


def write_analysis_outputs(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    summary = build_summary(records)
    write_table([summary], SUMMARY_PARQUET)

    pano_counts = Counter(record["pano_id"] for record in records if record.get("pano_id"))
    pano_count_records = [
        {"pano_id": pano_id, "n_points_using_this_pano": n}
        for pano_id, n in sorted(pano_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    write_table(pano_count_records, DUPLICATION_PARQUET)

    year_counts = Counter(record["capture_year"] for record in records if record.get("capture_year") is not None)
    year_records = [
        {"capture_year": int(year), "n": n}
        for year, n in sorted(year_counts.items())
    ]
    write_table(year_records, YEAR_DISTRIBUTION_PARQUET)
    return summary, pano_count_records, year_records


def validate_outputs() -> None:
    for path in [METADATA_PARQUET, SUMMARY_PARQUET, DUPLICATION_PARQUET, YEAR_DISTRIBUTION_PARQUET]:
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError(f"Expected non-empty parquet output was not written: {path}")

    metadata_rows = pq.read_table(METADATA_PARQUET).num_rows
    summary_rows = pq.read_table(SUMMARY_PARQUET).num_rows
    duplication_rows = pq.read_table(DUPLICATION_PARQUET).num_rows
    year_rows = pq.read_table(YEAR_DISTRIBUTION_PARQUET).num_rows

    if metadata_rows != PILOT_SIZE:
        raise RuntimeError(f"Expected {PILOT_SIZE} metadata rows, found {metadata_rows}")
    if summary_rows != 1:
        raise RuntimeError(f"Expected 1 summary row, found {summary_rows}")
    if duplication_rows < 1:
        raise RuntimeError("Pano duplication output is empty.")
    if year_rows < 1:
        raise RuntimeError("Capture-year distribution output is empty.")


def run_pilot() -> int:
    log_path = configure_logging()
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        logging.error("GOOGLE_MAPS_API_KEY is not set; metadata pilot cannot run.")
        return 1

    points = read_sample_points()
    logging.info("Starting metadata-only GSV pilot for %s sampled points.", len(points))
    records: list[dict[str, Any]] = []

    with requests.Session() as session:
        for i, point in enumerate(points, start=1):
            metadata, http_status_code, content_type = call_metadata_endpoint(
                session=session,
                api_key=api_key,
                lat=float(point["lat"]),
                lon=float(point["lon"]),
            )
            record = build_record(
                source=point,
                metadata=metadata,
                http_status_code=http_status_code,
                content_type=content_type,
            )
            records.append(record)

            if i == 1 or i % 50 == 0 or i == len(points):
                successes = sum(1 for item in records if item.get("status") == "OK")
                logging.info(
                    "Processed %s/%s metadata requests; successes=%s failures=%s latest_status=%s",
                    i,
                    len(points),
                    successes,
                    len(records) - successes,
                    record.get("status"),
                )
            time.sleep(REQUEST_THROTTLE_SECONDS)

    metadata_table = write_table(records, METADATA_PARQUET)
    summary, pano_counts, year_records = write_analysis_outputs(records)
    validate_outputs()

    print("GSV metadata pilot complete")
    print(f"metadata_rows: {metadata_table.num_rows}")
    print(f"metadata_successes: {summary['metadata_successes']}")
    print(f"metadata_failures: {summary['metadata_failures']}")
    print(f"unique_pano_ids: {summary['unique_pano_ids']}")
    print(f"pano_reuse_ratio: {summary['pano_reuse_ratio']}")
    print(f"missing_pano_fraction: {summary['missing_pano_fraction']}")
    print(f"median_point_to_pano_distance_m: {summary['median_point_to_pano_distance_m']}")
    print(
        "capture_year_range: "
        f"{summary['min_capture_year']} / {summary['median_capture_year']} / {summary['max_capture_year']}"
    )
    print(f"top_duplicate_panos: {pano_counts[:5]}")
    print(f"capture_year_bins: {len(year_records)}")
    print(f"metadata_parquet: {relative_to_repo_or_data(METADATA_PARQUET)}")
    print(f"summary_parquet: {relative_to_repo_or_data(SUMMARY_PARQUET)}")
    print(f"duplication_parquet: {relative_to_repo_or_data(DUPLICATION_PARQUET)}")
    print(f"capture_year_distribution_parquet: {relative_to_repo_or_data(YEAR_DISTRIBUTION_PARQUET)}")
    print(f"log: {relative_to_repo_or_data(log_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_pilot())
