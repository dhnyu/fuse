#!/usr/bin/env python3
"""Run a bounded Geo2Vec SDF sample-density sensitivity study."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

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
STUDY_NAME = "gwanak_sample_density_sensitivity_v1"


DENSITIES = [
    {"name": "low", "sample_config_version": "sdf_density_low_v1", "samples_per_unit": 4, "point_sample": 1, "uniform_grid": 2},
    {"name": "medium", "sample_config_version": "sdf_density_medium_v1", "samples_per_unit": 8, "point_sample": 2, "uniform_grid": 4},
    {"name": "high", "sample_config_version": "sdf_density_high_v1", "samples_per_unit": 16, "point_sample": 4, "uniform_grid": 6},
]


def run(cmd: list[str]) -> None:
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


def build_gwanak_id_map(overwrite: bool) -> tuple[Path, Path, int]:
    id_dir = METADATA_DIR / STUDY_NAME
    id_dir.mkdir(parents=True, exist_ok=True)
    id_map = id_dir / "gwanak_buildings_geo2vec_density_study_id_map.parquet"
    id_meta = id_dir / "gwanak_buildings_geo2vec_density_study_id_map_metadata.json"
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--checkpoint-every-steps", type=int, default=500)
    parser.add_argument("--keep-checkpoints", type=int, default=2)
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = time.time()
    id_map, id_meta, n = build_gwanak_id_map(args.overwrite)
    study_meta_dir = METADATA_DIR / STUDY_NAME
    study_meta_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for density in DENSITIES:
        name = density["name"]
        sample_root = SAMPLE_CACHE_DIR / STUDY_NAME / name
        sample_manifest = sample_root / f"korea_geo2vec_shape_samples_{suffix_for_limit(n)}_{density['sample_config_version']}" / "manifest.json"
        if not (sample_manifest.exists() and args.skip_existing):
            run(
                [
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
                    str(n),
                    "--branch",
                    "shape",
                    "--buildings-per-shard",
                    "5000",
                    "--workers",
                    str(args.workers),
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
                    "--overwrite",
                ]
            )
        run(
            [
                sys.executable,
                str(PROTOTYPE_DIR / "validate_sample_cache.py"),
                "--manifest-json",
                str(sample_manifest),
                "--id-map",
                str(id_map),
                "--overwrite",
            ]
        )
        run_dir = TRAINING_RUN_DIR / STUDY_NAME / f"geo2vec_density_{name}_32d"
        if not ((run_dir / "training_summary.json").exists() and args.skip_existing):
            run(
                [
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
                    "--overwrite-run-dir",
                ]
            )
        summary = json.loads((run_dir / "training_summary.json").read_text())
        embedding_root = EMBEDDING_DIR / STUDY_NAME
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
        records.append(
            {
                **density,
                "id_map": str(id_map),
                "sample_manifest_json": str(sample_manifest),
                "training_run_dir": str(run_dir),
                "embedding_dir": str(embedding_root / f"{run_dir.name}_embeddings"),
            }
        )
    manifest = {
        "study_name": STUDY_NAME,
        "dataset": "gwanak_exact_single_model_geometry",
        "building_count": n,
        "base_seed": BASE_SEED,
        "workers": args.workers,
        "densities": records,
        "elapsed_seconds": time.time() - start,
    }
    write_json_atomic(study_meta_dir / "sample_density_sensitivity_manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
