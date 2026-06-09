#!/usr/bin/env python3
"""Run a Gwanak Geo2Vec epoch-saturation study."""

from __future__ import annotations

import argparse
import json
import shutil
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
    REPORT_DIR,
    SAMPLE_CACHE_DIR,
    TRAINING_RUN_DIR,
    dataframe_checksum,
    suffix_for_limit,
    write_json_atomic,
    write_parquet_atomic,
)


GWANAK_GEOMETRY = Path("/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
GWANAK_LAYER = "gwanak_buildings"
STUDY_NAME = "gwanak_geo2vec_epoch_saturation_v1"
EXPECTED_BUILDINGS = 38_547

DENSITIES = [
    {
        "name": "sat_0800",
        "target_samples_per_building": 800,
        "sample_config_version": "sdf_epoch_saturation_0800_v1",
        "samples_per_unit": 116,
        "point_sample": 29,
        "uniform_grid": 16,
    },
    {
        "name": "sat_1600",
        "target_samples_per_building": 1600,
        "sample_config_version": "sdf_epoch_saturation_1600_v1",
        "samples_per_unit": 232,
        "point_sample": 58,
        "uniform_grid": 23,
    },
    {
        "name": "sat_3200",
        "target_samples_per_building": 3200,
        "sample_config_version": "sdf_epoch_saturation_3200_v1",
        "samples_per_unit": 470,
        "point_sample": 117,
        "uniform_grid": 32,
    },
]

EPOCHS = [1, 5, 10, 20, 50]


def run(cmd: list[str]) -> None:
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def study_dirs() -> list[Path]:
    return [
        SAMPLE_CACHE_DIR / STUDY_NAME,
        TRAINING_RUN_DIR / STUDY_NAME,
        EMBEDDING_DIR / STUDY_NAME,
        REPORT_DIR / STUDY_NAME,
        METADATA_DIR / STUDY_NAME,
    ]


def assert_under_study_dir(path: Path, root: Path) -> None:
    resolved = path.resolve()
    root_resolved = root.resolve()
    if root_resolved != resolved and root_resolved not in resolved.parents:
        raise RuntimeError(f"Refusing path outside study directory: {path}")


def build_gwanak_id_map(overwrite: bool) -> tuple[Path, Path, int]:
    id_dir = METADATA_DIR / STUDY_NAME
    id_dir.mkdir(parents=True, exist_ok=True)
    id_map = id_dir / "gwanak_buildings_geo2vec_epoch_saturation_id_map.parquet"
    id_meta = id_dir / "gwanak_buildings_geo2vec_epoch_saturation_id_map_metadata.json"
    if id_map.exists() and id_meta.exists() and not overwrite:
        meta = json.loads(id_meta.read_text())
        return id_map, id_meta, int(meta["row_count"])
    gdf = pyogrio.read_dataframe(GWANAK_GEOMETRY, layer=GWANAK_LAYER, columns=["building_id"])
    if len(gdf) != EXPECTED_BUILDINGS:
        raise RuntimeError(f"Expected {EXPECTED_BUILDINGS} Gwanak buildings, found {len(gdf)}.")
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
        "expected_row_count": EXPECTED_BUILDINGS,
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
    assert_under_study_dir(sample_root, SAMPLE_CACHE_DIR / STUDY_NAME)
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


def validate_cache(manifest: Path, id_map: Path) -> dict[str, Any]:
    run(
        [
            sys.executable,
            str(PROTOTYPE_DIR / "validate_sample_cache.py"),
            "--manifest-json",
            str(manifest),
            "--id-map",
            str(id_map),
            "--overwrite",
        ]
    )
    return json.loads((manifest.parent / "sample_cache_validation.json").read_text())


def completed_export(embedding_dir: Path, n: int) -> bool:
    manifest = embedding_dir / "embedding_export_manifest.json"
    if not manifest.exists():
        return False
    payload = json.loads(manifest.read_text())
    return payload.get("row_count_valid") is True and payload.get("finite_values") is True and int(payload.get("row_count", -1)) == n


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=40)
    parser.add_argument("--buildings-per-shard", type=int, default=5000)
    parser.add_argument("--checkpoint-every-steps", type=int, default=2000)
    parser.add_argument("--keep-checkpoints", type=int, default=2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--skip-report", action="store_true")
    parser.add_argument("--max-epoch", type=int, choices=EPOCHS)
    parser.add_argument("--densities", nargs="*", choices=[d["name"] for d in DENSITIES])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.workers > 40:
        raise SystemExit("--workers must not exceed 40.")
    for path in study_dirs():
        path.mkdir(parents=True, exist_ok=True)
    started = time.time()
    id_map, id_meta, n = build_gwanak_id_map(args.overwrite)
    if n != EXPECTED_BUILDINGS:
        raise RuntimeError(f"Expected {EXPECTED_BUILDINGS} buildings, found {n}.")
    selected_densities = [d for d in DENSITIES if not args.densities or d["name"] in args.densities]
    selected_epochs = [e for e in EPOCHS if args.max_epoch is None or e <= args.max_epoch]

    sample_manifests: dict[str, str] = {}
    sample_validations: dict[str, dict[str, Any]] = {}
    for density in selected_densities:
        sample_root = SAMPLE_CACHE_DIR / STUDY_NAME / density["name"]
        manifest = generate_cache(
            density=density,
            id_map=id_map,
            id_meta=id_meta,
            limit=n,
            buildings_per_shard=args.buildings_per_shard,
            workers=args.workers,
            sample_root=sample_root,
            overwrite=args.overwrite,
        )
        val = validate_cache(manifest, id_map)
        sample_manifests[density["name"]] = str(manifest)
        sample_validations[density["name"]] = val

    completed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for epoch_count in selected_epochs:
        for density in selected_densities:
            name = density["name"]
            run_name = f"geo2vec_density_{name}_epoch_{epoch_count:02d}_32d"
            run_dir = TRAINING_RUN_DIR / STUDY_NAME / run_name
            embedding_root = EMBEDDING_DIR / STUDY_NAME
            embedding_dir = embedding_root / f"{run_name}_embeddings"
            assert_under_study_dir(run_dir, TRAINING_RUN_DIR / STUDY_NAME)
            assert_under_study_dir(embedding_dir, EMBEDDING_DIR / STUDY_NAME)
            try:
                if (run_dir / "training_summary.json").exists() and completed_export(embedding_dir, n) and args.skip_existing:
                    status = "reused"
                else:
                    cmd = [
                        sys.executable,
                        str(PROTOTYPE_DIR / "train_global_geo2vec_from_sample_cache.py"),
                        "--id-map",
                        str(id_map),
                        "--manifest-json",
                        sample_manifests[name],
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
                        str(epoch_count),
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
                    status = "completed"
                completed.append(
                    {
                        **density,
                        "epochs": int(epoch_count),
                        "status": status,
                        "id_map": str(id_map),
                        "sample_manifest_json": sample_manifests[name],
                        "training_run_dir": str(run_dir),
                        "embedding_dir": str(embedding_dir),
                    }
                )
            except Exception as exc:
                failed.append(
                    {
                        **density,
                        "epochs": int(epoch_count),
                        "status": "failed",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "sample_manifest_json": sample_manifests.get(name),
                        "training_run_dir": str(run_dir),
                        "embedding_dir": str(embedding_dir),
                    }
                )
                write_json_atomic(
                    METADATA_DIR / STUDY_NAME / "epoch_saturation_failed_partial.json",
                    {"failed": failed, "completed": completed},
                )

    manifest = {
        "study_name": STUDY_NAME,
        "dataset": "gwanak_exact_single_model_geometry",
        "building_count": int(n),
        "expected_building_count": EXPECTED_BUILDINGS,
        "base_seed": BASE_SEED,
        "workers": int(args.workers),
        "densities_requested": selected_densities,
        "epochs_requested": selected_epochs,
        "sample_manifests": sample_manifests,
        "sample_validations": sample_validations,
        "densities": completed,
        "failed_combinations": failed,
        "elapsed_seconds": time.time() - started,
    }
    manifest_path = METADATA_DIR / STUDY_NAME / "epoch_saturation_manifest.json"
    write_json_atomic(manifest_path, manifest)
    write_json_atomic(METADATA_DIR / STUDY_NAME / "sample_density_sensitivity_manifest.json", manifest)

    if not args.skip_validation:
        run(["Rscript", str(PROTOTYPE_DIR / "validate_density_embeddings_xgboost.R"), "--study-name", STUDY_NAME])
    if not args.skip_report:
        run([sys.executable, str(PROTOTYPE_DIR / "summarize_epoch_saturation.py"), "--study-name", STUDY_NAME])
        report = REPORT_DIR / "geo2vec_epoch_saturation_report.md"
        test_copy = PROTOTYPE_DIR / "geo2vec_epoch_saturation_report.md"
        shutil.copy2(report, test_copy)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
