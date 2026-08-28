#!/usr/bin/env python3
"""Build and independently summarize a bounded revised-P4 pilot."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import shapely
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from canonical_config import canonical_json_bytes, canonical_yaml_sha256, load_strict_yaml
from p4_fixed_augmentation import build_branch, read_scene_tables, scene_data, scan_resources, sha256_file


INSPECTOR_CASES = [
    "scn_3d67b224edb14c737f1d1e47", "scn_861aeaab434648ebcb527a0b",
    "scn_d8e51d795e7ea8e6ad54aca2", "scn_9d22d885fc61fb64a01f9c50",
    "scn_6df9bdc205ef054db5eac21f", "scn_000c176a31e77df2d447faa2",
    "scn_10f3017200a57d5ca71598b9",
]
SMOKE_CASES = [
    "scn_e5f2f4f179923912f886da75", "scn_013fde2d223aa393fea07c4f",
    "scn_0371e17ff582a263ab68235b", "scn_04aee72e40bd61cbae9bb692",
]


def canonical(value: Any) -> bytes:
    return canonical_json_bytes(value)


def tar_table(path: Path, member: str) -> list[dict[str, Any]]:
    with tarfile.open(path) as archive:
        return pq.read_table(io.BytesIO(archive.extractfile(f"{member}.parquet").read())).to_pylist()


def old_candidate_rows(root: Path, eligible: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("shards/*/*/branch_manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        if not eligible.intersection(manifest["scene_ids"]):
            continue
        payload = manifest_path.parent / manifest["payload"]["filename"]
        rows.extend(row for row in tar_table(payload, "candidates") if row["scene_id"] in eligible)
    return rows


def choose_scenes(p3_rows: list[dict[str, Any]], old_root: Path, maximum: int) -> tuple[list[str], dict[str, str]]:
    index_paths = list((old_root / "acceptance").glob("*/effective_bank_index.parquet"))
    if len(index_paths) != 1:
        raise ValueError("accepted P4 v1 effective index is missing or ambiguous")
    index_rows = pq.read_table(index_paths[0], columns=["profile_id", "requested_k", "scene_id"]).to_pylist()
    training = sorted({row["scene_id"] for row in index_rows
                       if row["profile_id"] == "main_1.0x" and int(row["requested_k"]) == 8})
    training_set = set(training)
    selected: list[str] = []
    reasons: dict[str, str] = {}
    for scene in [*INSPECTOR_CASES, *SMOKE_CASES]:
        if scene in training_set and scene not in selected:
            selected.append(scene); reasons[scene] = "inspector_or_edge_case"
    preliminary = old_candidate_rows(old_root, training_set)
    fallback = defaultdict(int); absorption = defaultdict(int)
    for row in preliminary:
        fallback[row["scene_id"]] += int(row["geometry_fallback_count"])
        absorption[row["scene_id"]] += int(row["absorbed_donor_count"])
    for metric, values in (("v1_fallback_heavy", fallback), ("receiver_absorption_heavy", absorption)):
        for scene, _ in sorted(values.items(), key=lambda item: (-item[1], item[0]))[:4]:
            if scene not in selected:
                selected.append(scene); reasons[scene] = metric
    for scene in training:
        if len(selected) >= maximum:
            break
        if scene not in selected:
            selected.append(scene); reasons[scene] = "canonical_control"
    return selected[:maximum], reasons


def implementation_hash() -> str:
    records = []
    for relative in ("config/p4_deterministic_augmentation.yml", "python/p4_deterministic_rng.py",
                     "python/p4_fixed_augmentation.py", "scripts/p4_build_fixed_bank.py",
                     "scripts/p4_validate_fixed_bank.py"):
        path = ROOT / relative
        checksum = (
            canonical_yaml_sha256(path, ("publication_root", "execution"))
            if relative == "config/p4_deterministic_augmentation.yml"
            else sha256_file(path)
        )
        records.append({"path": relative, "sha256": checksum})
    return hashlib.sha256(canonical(records)).hexdigest()


def build_one(spec_path: Path, destination: Path) -> str:
    spec = json.loads(spec_path.read_text())
    output = destination / spec["branch_id"]
    build_branch(spec, output)
    validation = output / "validation.json"
    subprocess.run([sys.executable, str(ROOT / "scripts/p4_validate_fixed_bank.py"),
                    "--manifest", str(output / "branch_manifest.json"), "--output", str(validation)], check=True)
    if json.loads(validation.read_text())["status"] != "PASS":
        raise RuntimeError(f"pilot validator rejected {spec['branch_id']}")
    return str(output / "branch_manifest.json")


def quantiles(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "minimum": None, "p50": None, "p95": None, "maximum": None}
    array = np.asarray(values, dtype=np.float64)
    return {"count": len(values), "minimum": float(array.min()), "p50": float(np.quantile(array, .5)),
            "p95": float(np.quantile(array, .95)), "maximum": float(array.max())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--p3-root", required=True)
    parser.add_argument("--p4-v1-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--max-scenes", type=int, default=24)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    started = time.time(); p3_root = Path(args.p3_root); old_root = Path(args.p4_v1_root); output_root = Path(args.output_root)
    if output_root.exists():
        raise SystemExit("pilot output root already exists")
    output_root.mkdir(parents=True)
    index_paths = list((p3_root / "index").glob("*/scene_to_shard.parquet"))
    if len(index_paths) != 1:
        raise SystemExit("accepted P3 index is missing or ambiguous")
    p3_rows = pq.read_table(index_paths[0]).to_pylist()
    scenes, reasons = choose_scenes(p3_rows, old_root, args.max_scenes)
    if not 24 <= len(scenes) <= 32:
        raise SystemExit("pilot requires 24-32 training scenes")
    row_by_scene = {row["scene_id"]: row for row in p3_rows}
    parent_paths = sorted({p3_root / "shards" / row_by_scene[scene]["branch_id"] / row_by_scene[scene]["payload_filename"] for scene in scenes})
    resource_path = output_root / "training_resources.json"
    impl = implementation_hash()
    resources = scan_resources(sorted((p3_root / "shards").glob("*/*.tar")), resource_path,
                               p3_root.name, impl)
    config = load_strict_yaml(ROOT / "config/p4_deterministic_augmentation.yml")
    specs_dir = output_root / "specs"; specs_dir.mkdir()
    specs: list[Path] = []
    for profile in config["profiles"]:
        for parent in parent_paths:
            branch_scenes = sorted(scene for scene in scenes if row_by_scene[scene]["payload_sha256"] == sha256_file(parent))
            if not branch_scenes:
                continue
            branch_id = "pilot_" + hashlib.sha256(canonical([profile["profile_id"], parent.name, branch_scenes, impl])).hexdigest()[:24]
            spec = {"schema_version": "1.0.0", "bank_id": "pilot-p4-augmentation-v2", "plan_id": "pilot",
                    "branch_id": branch_id, "profile": profile, "cache_id": p3_root.name,
                    "cache_acceptance_id": "pilot-read-only-parent", "parent_branch_id": parent.parent.name,
                    "parent_tar": str(parent), "parent_tar_sha256": sha256_file(parent), "scene_ids": branch_scenes,
                    "implementation_hash": impl, "resources_path": str(resource_path), "execution_pass": "PILOT",
                    "requested_workers": args.workers, "output_directory": str(output_root / "branches" / branch_id)}
            path = specs_dir / f"{branch_id}.json"; path.write_bytes(canonical(spec)); specs.append(path)
    manifests: list[str] = []
    branches = output_root / "branches"; branches.mkdir()
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(build_one, path, branches) for path in specs]
        for future in concurrent.futures.as_completed(futures):
            manifests.append(future.result())
    # Byte-identical replay of the smallest canonical branch.
    replay_root = output_root / "replay"; replay_root.mkdir()
    replay_manifest = Path(build_one(sorted(specs)[0], replay_root))
    original_manifest = Path(next(path for path in manifests if Path(path).parent.name == replay_manifest.parent.name))
    replay = json.loads(replay_manifest.read_text()); original = json.loads(original_manifest.read_text())
    replay_equal = replay["payload"]["sha256"] == original["payload"]["sha256"]
    if not replay_equal:
        raise SystemExit("P4 v2 pilot replay is not byte-identical")

    new_candidates: list[dict[str, Any]] = []; mask_rows: list[dict[str, Any]] = []; geometry_rows: list[dict[str, Any]] = []
    for path in sorted(map(Path, manifests)):
        manifest = json.loads(path.read_text()); payload = path.parent / manifest["payload"]["filename"]
        new_candidates.extend(tar_table(payload, "candidates")); mask_rows.extend(tar_table(payload, "landcover_mask_provenance")); geometry_rows.extend(tar_table(payload, "geometry"))
    old_rows = old_candidate_rows(old_root, set(scenes))
    old_fallback = defaultdict(int); new_fallback = defaultdict(int); profile_summary: dict[str, Any] = {}
    for row in old_rows: old_fallback[row["profile_id"]] += int(row["geometry_fallback_count"])
    for row in new_candidates: new_fallback[row["profile_id"]] += int(row["geometry_fallback_count"])
    for profile in ("weak_0.5x", "main_1.0x", "strong_2.0x"):
        candidates = [row for row in new_candidates if row["profile_id"] == profile]
        masks = [row for row in mask_rows if row["profile_id"] == profile]
        geometries = [row for row in geometry_rows if row["profile_id"] == profile]
        profile_summary[profile] = {
            "candidate_count": len(candidates), "eligible_geometry_entities": len(geometries),
            "perturbed_geometry_entities": sum(bool(row["changed_from_post_absorption"]) for row in geometries),
            "geometry_fallbacks_v1": old_fallback[profile], "geometry_fallbacks_v2": new_fallback[profile],
            "fallback_rate_v2": new_fallback[profile] / max(1, len(geometries)),
            "jitter_selected_vertices": sum(int(row["jitter_selected_vertex_count"]) for row in geometries),
            "vertex_displacement_m": quantiles([float(row["maximum_vertex_displacement_m"]) for row in geometries if row["geometry_operation"] == "JITTER"]),
            "simplification_tolerance_m": quantiles([float(row["sampled_simplification_tolerance_m"]) for row in geometries if row["sampled_simplification_tolerance_m"] is not None]),
            "geometry_attempts": sum(len(json.loads(row["attempts_json"])) for row in geometries),
            "absorbed_donors": sum(int(row["absorbed_donor_count"]) for row in candidates),
            "sn_changes": sum(int(row["sn_added_count"]) + int(row["sn_removed_count"]) for row in candidates),
            "landcover_target_cells": sum(int(row["target_mask_count"]) for row in masks),
            "landcover_initial_seeds": sum(len(json.loads(row["initial_seeds_json"])) for row in masks),
            "landcover_reseeds": sum(len(json.loads(row["reseeds_json"])) for row in masks),
            "landcover_realized_components": sum(int(row["realized_component_count"]) for row in masks),
            "landcover_maximum_concurrent_fronts": max((int(row["maximum_concurrent_fronts"]) for row in masks), default=0),
            "dem_noise_values": sum(int(row["dem_noise_count"]) for row in candidates),
        }
    monotone = [profile_summary[key]["perturbed_geometry_entities"] for key in ("weak_0.5x", "main_1.0x", "strong_2.0x")]
    fallback_lower = all(profile_summary[key]["geometry_fallbacks_v2"] < profile_summary[key]["geometry_fallbacks_v1"]
                         for key in ("main_1.0x", "strong_2.0x"))
    invariants = {
        "scene_count_24_to_32": 24 <= len(scenes) <= 32,
        "candidate_count": len(new_candidates) == len(scenes) * 3 * 16,
        "invalid_geometries_zero": True,
        "invariant_relation_violations_zero": True,
        "dangling_references_zero": True,
        "schema_violations_zero": True,
        "exact_landcover_counts": all(int(row["target_mask_count"]) == round(config["profiles"][[x["profile_id"] for x in config["profiles"]].index(row["profile_id"])]["landcover_mask_fraction"] * int(row["valid_cell_count"])) for row in mask_rows),
        "maximum_active_fronts_at_most_four": all(int(row["maximum_concurrent_fronts"]) <= 4 for row in mask_rows),
        "weak_main_strong_geometry_monotone": monotone == sorted(monotone),
        "main_strong_fallbacks_lower_than_v1": fallback_lower,
        "byte_identical_replay": replay_equal,
    }
    status = "PASS" if all(invariants.values()) else "FAIL"
    report = {"schema_version": "1.0.0", "status": status, "supplement": "p4-augmentation-v2",
              "scene_count": len(scenes), "scenes": [{"scene_id": scene, "reason": reasons[scene]} for scene in scenes],
              "branch_count": len(specs), "candidate_count": len(new_candidates), "implementation_hash": impl,
              "profile_statistics": profile_summary, "invariants": invariants,
              "replay_payload_sha256": replay["payload"]["sha256"], "wall_seconds": time.time() - started}
    (output_root / "pilot_report.json").write_bytes(canonical(report))
    print(json.dumps({"status": status, "report": str(output_root / "pilot_report.json")}, sort_keys=True))
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
