#!/usr/bin/env python3
"""Small Geo2Vec shape-only integration test on 100 Gwanak-gu buildings."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import numpy as np
import pandas as pd


INPUT_GPKG = Path.home() / "fusedatalarge" / "processed" / "gwanak_buildings_vworld.gpkg"
EXTERNAL_REPO = Path.home() / "fuse_external" / "GeoNeuralRepresentation"
OUTPUT_DIR = Path.home() / "fusedata" / "embeddings"
OUTPUT_PARQUET = OUTPUT_DIR / "gwanak_buildings_geo2vec_shape_test_100.parquet"
METADATA_JSON = OUTPUT_DIR / "gwanak_buildings_geo2vec_shape_test_100_metadata.json"


@dataclass(frozen=True)
class RunConfig:
    sample_size: int = 100
    Geo_dim: int = 32
    num_epoch: int = 1
    seed: int = 20260608
    num_process: int = 2
    samples_perUnit_shape: int = 8
    point_sample_shape: int = 2
    sample_band_width_shape: float = 0.08
    uniformed_sample_perUnit_shape: int = 4
    batch_size: int = 2048


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing test parquet/metadata outputs.",
    )
    return parser.parse_args()


def make_geo2vec_args(config: RunConfig, torch_module) -> SimpleNamespace:
    device = "cuda" if torch_module.cuda.is_available() else "cpu"
    return SimpleNamespace(
        num_process=config.num_process,
        samples_perUnit_location=8,
        point_sample_location=2,
        sample_band_width_location=0.08,
        uniformed_sample_perUnit_location=4,
        samples_perUnit_shape=config.samples_perUnit_shape,
        point_sample_shape=config.point_sample_shape,
        sample_band_width_shape=config.sample_band_width_shape,
        uniformed_sample_perUnit_shape=config.uniformed_sample_perUnit_shape,
        batch_size=config.batch_size,
        num_workers=0,
        epochs_location=config.num_epoch,
        num_layers_location=3,
        z_size_location=config.Geo_dim,
        hidden_size_location=64,
        num_freqs_location=4,
        device=device,
        code_reg_weight_location=0.0,
        weight_decay_location=0.01,
        polar_fourier_location=False,
        log_sampling_location=False,
        training_ratio_location=0.9,
        epochs_shape=config.num_epoch,
        num_layers_shape=3,
        z_size_shape=config.Geo_dim,
        hidden_size_shape=64,
        num_freqs_shape=4,
        device_shape=device,
        code_reg_weight_shape=0.1,
        weight_decay_shape=0.01,
        polar_fourier_shape=False,
        log_sampling_shape=True,
        training_ratio_shape=0.9,
        test_representation_location=False,
        visualSDF_location=False,
        test_representation_shape=False,
        visualSDF_shape=False,
    )


def main() -> None:
    cli = parse_args()
    config = RunConfig()
    start = time.time()
    start_time = time.strftime("%Y-%m-%d %H:%M:%S %Z")

    require(INPUT_GPKG.exists(), f"Input GeoPackage not found: {INPUT_GPKG}")
    require(EXTERNAL_REPO.exists(), f"External repository not found: {EXTERNAL_REPO}")
    require(
        (EXTERNAL_REPO / "runners" / "list2embedding.py").exists(),
        f"list2embedding.py not found under external repository: {EXTERNAL_REPO}",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = [p for p in (OUTPUT_PARQUET, METADATA_JSON) if p.exists()]
    if existing and not cli.overwrite:
        raise RuntimeError(
            "Output file(s) already exist. Re-run with --overwrite to replace them:\n"
            + "\n".join(str(p) for p in existing)
        )
    if cli.overwrite:
        for path in existing:
            path.unlink()

    random.seed(config.seed)
    np.random.seed(config.seed)

    sys.path.insert(0, str(EXTERNAL_REPO))
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "Required dependency missing: torch. Activate/install a PyTorch "
            "environment before running the Gwanak Geo2Vec integration test."
        ) from exc

    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)

    try:
        from runners.list2embedding import list2vec
    except ImportError as exc:
        raise RuntimeError(
            f"Failed to import list2vec from external repository: {EXTERNAL_REPO}"
        ) from exc

    print(f"Python version: {sys.version}")
    print(f"torch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"Reading input: {INPUT_GPKG}")

    gdf = gpd.read_file(INPUT_GPKG)
    require("building_id" in gdf.columns, "Input GeoPackage is missing building_id.")
    crs_text = str(gdf.crs)
    require(gdf.crs is not None, "Input GeoPackage has missing CRS.")
    print(f"Input CRS: {crs_text}")
    print(f"Input rows read: {len(gdf)}")

    valid_mask = gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid
    sample = gdf.loc[valid_mask, ["building_id", "geometry"]].head(config.sample_size).copy()
    require(
        len(sample) == config.sample_size,
        f"Only {len(sample)} valid non-empty geometries available; expected {config.sample_size}.",
    )
    sample["geo2vec_internal_id"] = np.arange(len(sample), dtype=np.int64)
    sample = sample.reset_index(drop=True)
    building_ids = sample["building_id"].astype(str).to_numpy()
    geometries = list(sample.geometry)

    geo2vec_args = make_geo2vec_args(config, torch)
    embeddings = list2vec(
        geometries,
        Geo_dim=config.Geo_dim,
        num_epoch=config.num_epoch,
        location_learning=False,
        shape_learning=True,
        save_file_name=None,
        save_model_path=None,
        args=geo2vec_args,
    )

    embeddings = np.asarray(embeddings, dtype=np.float32)
    extra_rows = int(max(0, embeddings.shape[0] - len(sample)))
    embeddings = embeddings[: len(sample), :]

    require(embeddings.shape[0] == len(sample), "Embedding row count does not match input sample size.")
    require(
        embeddings.shape[1] == config.Geo_dim,
        f"Unexpected embedding dimension {embeddings.shape[1]}; expected {config.Geo_dim}.",
    )
    require(np.isfinite(embeddings).all(), "Embeddings contain NaN or infinite values.")

    out = pd.DataFrame(
        {
            "building_id": building_ids,
            "geo2vec_internal_id": sample["geo2vec_internal_id"].to_numpy(dtype=np.int64),
        }
    )
    for i in range(config.Geo_dim):
        out[f"geo2vec_{i:03d}"] = embeddings[:, i]

    out.to_parquet(OUTPUT_PARQUET, index=False)

    end = time.time()
    metadata = {
        "input_path": str(INPUT_GPKG),
        "external_repo_path": str(EXTERNAL_REPO),
        "output_path": str(OUTPUT_PARQUET),
        "metadata_path": str(METADATA_JSON),
        "sample_size": config.sample_size,
        "embedding_kind": "shape",
        "Geo_dim": config.Geo_dim,
        "num_epoch": config.num_epoch,
        "CRS": crs_text,
        "Python version": sys.version,
        "torch version": torch.__version__,
        "CUDA availability": bool(torch.cuda.is_available()),
        "start time": start_time,
        "end time": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "elapsed seconds": end - start,
        "number of input rows read": int(len(gdf)),
        "number of geometries used": int(len(sample)),
        "notes about extra embedding rows if observed": (
            f"GeoNeuralRepresentation returned {extra_rows} extra embedding row(s); "
            "output was sliced to the input sample size."
            if extra_rows
            else "No extra embedding rows observed."
        ),
        "run_config": asdict(config),
    }
    METADATA_JSON.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Embedding parquet written: {OUTPUT_PARQUET}")
    print(f"Metadata JSON written: {METADATA_JSON}")
    print(f"Embedding shape: {embeddings.shape}")


if __name__ == "__main__":
    main()
