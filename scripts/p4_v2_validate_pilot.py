#!/usr/bin/env python3
"""Independently validate and quantify an existing P4 v2 pilot."""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import shapely

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from canonical_config import canonical_json_bytes, load_strict_yaml
from p4_fixed_augmentation import read_scene_tables, scene_data, sha256_file


def read_member(path: Path, member: str) -> list[dict[str, Any]]:
    with tarfile.open(path) as archive:
        handle = archive.extractfile(f"{member}.parquet")
        if handle is None:
            raise ValueError(f"missing member {member} in {path.name}")
        return pq.read_table(io.BytesIO(handle.read())).to_pylist()


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "minimum": None, "p50": None, "p95": None, "maximum": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "minimum": float(array.min()),
        "p50": float(np.quantile(array, 0.5)),
        "p95": float(np.quantile(array, 0.95)),
        "maximum": float(array.max()),
    }


def isolated_cells(flat_indices: set[int], width: int) -> int:
    isolated = 0
    for flat in flat_indices:
        row, column = divmod(flat, width)
        neighbors = {
            (row + dr) * width + column + dc
            for dr in (-1, 0, 1)
            for dc in (-1, 0, 1)
            if (dr or dc) and row + dr >= 0 and 0 <= column + dc < width
        }
        isolated += not bool(neighbors.intersection(flat_indices))
    return isolated


def load_originals(p3_root: Path, scenes: set[str]) -> dict[str, dict[str, Any]]:
    index_path, = (p3_root / "index").glob("*/scene_to_shard.parquet")
    index = pq.read_table(index_path).to_pylist()
    rows = {row["scene_id"]: row for row in index if row["scene_id"] in scenes}
    if set(rows) != scenes:
        raise ValueError("pilot scene is missing from the accepted P3 index")
    by_tar: dict[Path, list[str]] = defaultdict(list)
    for scene, row in rows.items():
        by_tar[p3_root / "shards" / row["branch_id"] / row["payload_filename"]].append(scene)
    originals: dict[str, dict[str, Any]] = {}
    for path, member_scenes in sorted(by_tar.items()):
        if sha256_file(path) != rows[member_scenes[0]]["payload_sha256"]:
            raise ValueError(f"P3 checksum mismatch: {path.name}")
        with tempfile.TemporaryDirectory(prefix="p4-pilot-parent-") as temporary:
            with tarfile.open(path) as archive:
                archive.extractall(temporary)
            tables = read_scene_tables(Path(temporary))
            for scene in member_scenes:
                originals[scene] = scene_data(tables, scene)
    return originals


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-root", required=True)
    parser.add_argument("--p3-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    pilot_root = Path(args.pilot_root)
    p3_root = Path(args.p3_root)
    source_report = json.loads((pilot_root / "pilot_report.json").read_text())
    scenes = {row["scene_id"] for row in source_report["scenes"]}
    originals = load_originals(p3_root, scenes)
    config = load_strict_yaml(ROOT / "config/p4_deterministic_augmentation.yml")
    fractions = {row["profile_id"]: float(row["landcover_mask_fraction"]) for row in config["profiles"]}
    manifests = sorted((pilot_root / "branches").glob("*/branch_manifest.json"))
    records: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    invalid_geometry = 0
    payload_bytes = 0
    validation_failures = 0
    candidate_count = 0
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text())
        validation = json.loads((manifest_path.parent / "validation.json").read_text())
        validation_failures += validation["status"] != "PASS"
        payload = manifest_path.parent / manifest["payload"]["filename"]
        if sha256_file(payload) != manifest["payload"]["sha256"]:
            raise ValueError(f"pilot payload checksum mismatch: {manifest['branch_id']}")
        payload_bytes += payload.stat().st_size
        candidates = read_member(payload, "candidates")
        geometries = read_member(payload, "geometry")
        masks = read_member(payload, "landcover_mask_provenance")
        rasters = read_member(payload, "raster")
        candidate_count += len(candidates)
        for row in candidates:
            profile = row["profile_id"]
            records[profile]["fallbacks"].append(int(row["geometry_fallback_count"]))
            records[profile]["sn_changes"].append(int(row["sn_added_count"]) + int(row["sn_removed_count"]))
        for row in geometries:
            profile = row["profile_id"]
            original = originals[row["scene_id"]]
            local_id = int(row["local_entity_id"])
            original_geometry = original["geometries"].get(local_id)
            final_geometry = shapely.from_wkb(row["geometry_wkb"])
            invalid_geometry += not bool(shapely.is_valid(final_geometry))
            if original_geometry is None or original_geometry.is_empty:
                continue
            entity_type = original["entities"][local_id]["entity_type"]
            prefix = f"{entity_type}_"
            records[profile][prefix + "centroid_displacement_m"].append(float(original_geometry.centroid.distance(final_geometry.centroid)))
            if entity_type == "B" and original_geometry.area > 0:
                records[profile][prefix + "area_ratio"].append(float(final_geometry.area / original_geometry.area))
                records[profile][prefix + "perimeter_ratio"].append(float(final_geometry.length / original_geometry.length))
                union = original_geometry.union(final_geometry).area
                if union > 0:
                    records[profile][prefix + "iou"].append(float(original_geometry.intersection(final_geometry).area / union))
            elif entity_type == "R" and original_geometry.length > 0:
                records[profile][prefix + "length_ratio"].append(float(final_geometry.length / original_geometry.length))
        mask_by_candidate: dict[str, set[int]] = defaultdict(set)
        dem_by_candidate: dict[str, list[float]] = defaultdict(list)
        for row in rasters:
            if row["modality"] == "landcover":
                mask_by_candidate[row["candidate_id"]].add(int(row["flat_index"]))
            else:
                original = originals[row["scene_id"]]["dem"].reshape(-1)[int(row["flat_index"])]
                dem_by_candidate[row["candidate_id"]].append(float(row["value"]) - float(original))
        for row in masks:
            profile = row["profile_id"]
            selected = mask_by_candidate[row["candidate_id"]]
            width = int(originals[row["scene_id"]]["lc_valid"].shape[1])
            expected = round(fractions[profile] * int(row["valid_cell_count"]))
            records[profile]["mask_count_error"].append(len(selected) - expected)
            records[profile]["mask_realized_fraction"].append(len(selected) / max(1, int(row["valid_cell_count"])))
            records[profile]["mask_initial_seeds"].append(len(json.loads(row["initial_seeds_json"])))
            records[profile]["mask_reseeds"].append(len(json.loads(row["reseeds_json"])))
            records[profile]["mask_max_active_fronts"].append(int(row["maximum_concurrent_fronts"]))
            records[profile]["mask_components"].append(int(row["realized_component_count"]))
            records[profile]["mask_isolated_cells"].append(isolated_cells(selected, width))
            records[profile]["dem_noise"].extend(dem_by_candidate[row["candidate_id"]])
    summaries = {
        profile: {name: distribution(values) for name, values in sorted(metrics.items())}
        for profile, metrics in sorted(records.items())
    }
    primary = source_report["invariants"]
    checks = {
        "all_branch_validations_pass": validation_failures == 0,
        "candidate_count_exact": candidate_count == len(scenes) * 3 * 16,
        "invalid_geometries_zero": invalid_geometry == 0,
        "exact_landcover_mask_counts": all(
            item["mask_count_error"]["minimum"] == 0 and item["mask_count_error"]["maximum"] == 0
            for item in summaries.values()
        ),
        "maximum_active_fronts_at_most_four": all(
            item["mask_max_active_fronts"]["maximum"] <= 4 for item in summaries.values()
        ),
        "isolated_mask_cells_are_reseed_explained": all(
            item["mask_isolated_cells"]["count"] == item["mask_reseeds"]["count"]
            and sum(records[profile]["mask_isolated_cells"]) <= sum(records[profile]["mask_reseeds"])
            for profile, item in summaries.items()
        ),
        "byte_identical_replay": bool(primary["byte_identical_replay"]),
        "weak_main_strong_geometry_monotone": bool(primary["weak_main_strong_geometry_monotone"]),
        "main_strong_fallbacks_lower_than_v1": bool(primary["main_strong_fallbacks_lower_than_v1"]),
        "primary_report_consistent": source_report["status"] == "PASS" and all(
            bool(value) for value in primary.values()
        ),
    }
    report = {
        "schema_version": "1.0.0",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "supplement": "p4-augmentation-v2",
        "source_pilot_report_sha256": sha256_file(pilot_root / "pilot_report.json"),
        "scene_count": len(scenes),
        "branch_count": len(manifests),
        "candidate_count": candidate_count,
        "payload_bytes": payload_bytes,
        "checks": checks,
        "profile_statistics": summaries,
        "invalid_geometry_count": invalid_geometry,
        "validation_failure_count": validation_failures,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(report))
    print(json.dumps({"status": report["status"], "output": str(output)}, sort_keys=True))
    if report["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
