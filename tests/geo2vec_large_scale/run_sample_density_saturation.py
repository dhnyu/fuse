#!/usr/bin/env python3
"""Run a Gwanak Geo2Vec SDF sample-density saturation study."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pyogrio

from geo2vec_large_scale_common import (
    BASE_SEED,
    EMBEDDING_DIR,
    METADATA_DIR,
    PROTOTYPE_DIR,
    SAMPLE_CACHE_DIR,
    TRAINING_RUN_DIR,
    dataframe_checksum,
    suffix_for_limit,
    write_json_atomic,
    write_parquet_atomic,
)


GWANAK_GEOMETRY = Path("/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
GWANAK_LAYER = "gwanak_buildings"
STUDY_NAME = "gwanak_sample_density_saturation_v1"


CANDIDATE_DENSITIES = [
    {
        "name": "sat_0200",
        "target_samples_per_building": 200,
        "sample_config_version": "sdf_saturation_0200_v1",
        "samples_per_unit": 28,
        "point_sample": 7,
        "uniform_grid": 8,
    },
    {
        "name": "sat_0400",
        "target_samples_per_building": 400,
        "sample_config_version": "sdf_saturation_0400_v1",
        "samples_per_unit": 60,
        "point_sample": 15,
        "uniform_grid": 11,
    },
    {
        "name": "sat_0800",
        "target_samples_per_building": 800,
        "sample_config_version": "sdf_saturation_0800_v1",
        "samples_per_unit": 116,
        "point_sample": 29,
        "uniform_grid": 16,
    },
    {
        "name": "sat_1600",
        "target_samples_per_building": 1600,
        "sample_config_version": "sdf_saturation_1600_v1",
        "samples_per_unit": 232,
        "point_sample": 58,
        "uniform_grid": 23,
    },
    {
        "name": "sat_3200",
        "target_samples_per_building": 3200,
        "sample_config_version": "sdf_saturation_3200_v1",
        "samples_per_unit": 470,
        "point_sample": 117,
        "uniform_grid": 32,
    },
    {
        "name": "sat_5000",
        "target_samples_per_building": 5000,
        "sample_config_version": "sdf_saturation_5000_v1",
        "samples_per_unit": 734,
        "point_sample": 184,
        "uniform_grid": 40,
    },
]


def run(cmd: list[str]) -> None:
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def build_gwanak_id_map(overwrite: bool) -> tuple[Path, Path, int]:
    id_dir = METADATA_DIR / STUDY_NAME
    id_dir.mkdir(parents=True, exist_ok=True)
    id_map = id_dir / "gwanak_buildings_geo2vec_saturation_study_id_map.parquet"
    id_meta = id_dir / "gwanak_buildings_geo2vec_saturation_study_id_map_metadata.json"
    if id_map.exists() and id_meta.exists() and not overwrite:
        meta = json.loads(id_meta.read_text())
        return id_map, id_meta, int(meta["row_count"])
    gdf = pyogrio.read_dataframe(GWANAK_GEOMETRY, layer=GWANAK_LAYER, columns=["building_id"])
    if gdf["building_id"].isna().any():
        raise RuntimeError("Gwanak id map has missing building_id.")
    if not gdf["building_id"].is_unique:
        raise RuntimeError("Gwanak id map has duplicate building_id.")
    df = pd.DataFrame({"building_id": gdf["building_id"].astype(str)})
    df = df.sort_values("building_id", kind="mergesort").reset_index(drop=True)
    df.insert(0, "geo2vec_internal_id", range(len(df)))
    df["geo2vec_internal_id"] = df["geo2vec_internal_id"].astype("int64")
    write_parquet_atomic(df[["building_id", "geo2vec_internal_id"]], id_map)
    meta = {
        "study_name": STUDY_NAME,
        "geometry": str(GWANAK_GEOMETRY),
        "layer": GWANAK_LAYER,
        "row_count": int(len(df)),
        "missing_building_id": 0,
        "duplicate_building_id": 0,
        "ids_contiguous": True,
        "ordering": "building_id ascending, stable mergesort",
        "checksum_records_sha256": dataframe_checksum(df, ["building_id", "geo2vec_internal_id"]),
    }
    write_json_atomic(id_meta, meta)
    return id_map, id_meta, len(df)


def sample_manifest_path(sample_root: Path, limit: int, version: str) -> Path:
    return sample_root / f"korea_geo2vec_shape_samples_{suffix_for_limit(limit)}_{version}" / "manifest.json"


def generate_cache(
    *,
    density: dict[str, Any],
    id_map: Path,
    id_meta: Path,
    limit: int,
    buildings_per_shard: int,
    workers: int,
    sample_root: Path,
    overwrite: bool,
) -> Path:
    manifest = sample_manifest_path(sample_root, limit, density["sample_config_version"])
    if manifest.exists() and not overwrite:
        existing = json.loads(manifest.read_text())
        if existing.get("complete"):
            print(json.dumps(existing, indent=2, sort_keys=True))
            return manifest
    cmd = [
        sys.executable,
        str(PROTOTYPE_DIR / "generate_disk_backed_sdf_samples.py"),
        "--id-map",
        str(id_map),
        "--id-map-metadata",
        str(id_meta),
        "--geometry",
        str(GWANAK_GEOMETRY),
        "--layer",
        GWANAK_LAYER,
        "--limit",
        str(limit),
        "--branch",
        "shape",
        "--buildings-per-shard",
        str(buildings_per_shard),
        "--workers",
        str(workers),
        "--samples-per-unit",
        str(density["samples_per_unit"]),
        "--point-sample",
        str(density["point_sample"]),
        "--uniform-grid",
        str(density["uniform_grid"]),
        "--validation-ratio",
        "0.1",
        "--base-seed",
        str(BASE_SEED),
        "--sample-config-version",
        density["sample_config_version"],
        "--output-dir",
        str(sample_root),
    ]
    if overwrite:
        cmd.append("--overwrite")
    run(cmd)
    return manifest


def validate_cache(manifest: Path, id_map: Path, overwrite: bool = True) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(PROTOTYPE_DIR / "validate_sample_cache.py"),
        "--manifest-json",
        str(manifest),
        "--id-map",
        str(id_map),
    ]
    if overwrite:
        cmd.append("--overwrite")
    run(cmd)
    return json.loads((manifest.parent / "sample_cache_validation.json").read_text())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=40)
    parser.add_argument("--calibration-limit", type=int, default=1000)
    parser.add_argument("--buildings-per-shard", type=int, default=5000)
    parser.add_argument("--checkpoint-every-steps", type=int, default=2000)
    parser.add_argument("--keep-checkpoints", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--calibration-only", action="store_true")
    parser.add_argument("--max-target", type=int, help="Optional safety cap for target samples/building.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.workers > 40:
        raise SystemExit("--workers must not exceed 40.")
    start = time.time()
    id_map, id_meta, n = build_gwanak_id_map(args.overwrite)
    study_meta_dir = METADATA_DIR / STUDY_NAME
    study_meta_dir.mkdir(parents=True, exist_ok=True)
    selected = [
        dict(d)
        for d in CANDIDATE_DENSITIES
        if args.max_target is None or int(d["target_samples_per_building"]) <= args.max_target
    ]

    calibration_records = []
    for density in selected:
        calib_density = dict(density)
        calib_density["sample_config_version"] = f"{density['sample_config_version']}_calibration"
        sample_root = SAMPLE_CACHE_DIR / STUDY_NAME / "calibration" / density["name"]
        manifest = generate_cache(
            density=calib_density,
            id_map=id_map,
            id_meta=id_meta,
            limit=args.calibration_limit,
            buildings_per_shard=args.calibration_limit,
            workers=args.workers,
            sample_root=sample_root,
            overwrite=args.overwrite,
        )
        val = validate_cache(manifest, id_map, overwrite=True)
        sm = json.loads(manifest.read_text())
        calibration_records.append(
            {
                **density,
                "calibration_manifest_json": str(manifest),
                "calibration_total_samples": int(sm["total_samples"]),
                "calibration_building_count": int(sm["building_count"]),
                "calibration_mean_samples_per_building": float(sm["total_samples"] / sm["building_count"]),
                "calibration_median_samples_per_building": float(val["sample_count_median"]),
                "calibration_min_samples_per_building": int(val["sample_count_min"]),
                "calibration_max_samples_per_building": int(val["sample_count_max"]),
            }
        )

    write_json_atomic(
        study_meta_dir / "sample_density_saturation_calibration.json",
        {
            "study_name": STUDY_NAME,
            "calibration_limit": int(args.calibration_limit),
            "workers": int(args.workers),
            "densities": calibration_records,
        },
    )
    if args.calibration_only:
        print(json.dumps({"calibration": calibration_records}, indent=2, sort_keys=True))
        return

    completed = []
    failed = []
    for density in selected:
        name = density["name"]
        sample_root = SAMPLE_CACHE_DIR / STUDY_NAME / name
        run_dir = TRAINING_RUN_DIR / STUDY_NAME / f"geo2vec_density_{name}_32d"
        embedding_root = EMBEDDING_DIR / STUDY_NAME
        try:
            sample_manifest = sample_manifest_path(sample_root, n, density["sample_config_version"])
            if not (sample_manifest.exists() and args.skip_existing):
                sample_manifest = generate_cache(
                    density=density,
                    id_map=id_map,
                    id_meta=id_meta,
                    limit=n,
                    buildings_per_shard=args.buildings_per_shard,
                    workers=args.workers,
                    sample_root=sample_root,
                    overwrite=args.overwrite,
                )
            validate_cache(sample_manifest, id_map, overwrite=True)
            if not ((run_dir / "training_summary.json").exists() and args.skip_existing):
                cmd = [
                    sys.executable,
                    str(PROTOTYPE_DIR / "train_global_geo2vec_from_sample_cache.py"),
                    "--id-map",
                    str(id_map),
                    "--manifest-json",
                    str(sample_manifest),
                    "--run-dir",
                    str(run_dir),
                    "--geo-dim",
                    "32",
                    "--hidden-size",
                    "128",
                    "--num-layers",
                    "4",
                    "--num-freqs",
                    "4",
                    "--epochs",
                    "1",
                    "--batch-size",
                    "4096",
                    "--checkpoint-every-steps",
                    str(args.checkpoint_every_steps),
                    "--keep-checkpoints",
                    str(args.keep_checkpoints),
                ]
                if args.overwrite or not run_dir.exists():
                    cmd.append("--overwrite-run-dir")
                run(cmd)
            summary = json.loads((run_dir / "training_summary.json").read_text())
            run(
                [
                    sys.executable,
                    str(PROTOTYPE_DIR / "export_global_geo2vec_embeddings.py"),
                    "--checkpoint",
                    summary["final_checkpoint"],
                    "--id-map",
                    str(id_map),
                    "--output-dir",
                    str(embedding_root),
                    "--batch-size",
                    "10000",
                    "--overwrite",
                ]
            )
            completed.append(
                {
                    **density,
                    "id_map": str(id_map),
                    "sample_manifest_json": str(sample_manifest),
                    "training_run_dir": str(run_dir),
                    "embedding_dir": str(embedding_root / f"{run_dir.name}_embeddings"),
                }
            )
        except Exception as exc:
            failed.append(
                {
                    **density,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "sample_root": str(sample_root),
                    "training_run_dir": str(run_dir),
                }
            )
            write_json_atomic(study_meta_dir / "sample_density_saturation_failed_partial.json", {"failed": failed, "completed": completed})

    manifest = {
        "study_name": STUDY_NAME,
        "dataset": "gwanak_exact_single_model_geometry",
        "building_count": int(n),
        "base_seed": BASE_SEED,
        "workers": int(args.workers),
        "calibration_limit": int(args.calibration_limit),
        "calibration": calibration_records,
        "densities": completed,
        "failed_densities": failed,
        "elapsed_seconds": time.time() - start,
    }
    write_json_atomic(study_meta_dir / "sample_density_sensitivity_manifest.json", manifest)
    write_json_atomic(study_meta_dir / "sample_density_saturation_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
