#!/usr/bin/env python3
"""Run shape-only Geo2Vec embeddings for Gwanak-gu VWorld buildings.

This script wraps the external GeoNeuralRepresentation repository without
modifying it. By default it requires CUDA-enabled PyTorch; pass --allow-cpu
only for small intermediate tests.
"""

from __future__ import annotations

import argparse
import gc
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


DEFAULT_INPUT = Path.home() / "fusedatalarge" / "processed" / "gwanak_buildings_vworld.gpkg"
DEFAULT_EXTERNAL_REPO = Path.home() / "fuse_external" / "GeoNeuralRepresentation"
DEFAULT_OUTPUT_DIR = Path.home() / "fusedata" / "embeddings"
DEFAULT_OUTPUT = DEFAULT_OUTPUT_DIR / "gwanak_buildings_geo2vec_shape_full.parquet"
DEFAULT_METADATA = DEFAULT_OUTPUT_DIR / "gwanak_buildings_geo2vec_shape_full_metadata.json"
PART_PREFIX = "gwanak_buildings_geo2vec_shape_full_part"


@dataclass(frozen=True)
class Geo2VecConfig:
    Geo_dim: int = 64
    num_epoch: int = 1
    seed: int = 20260608
    num_process: int = 8
    batch_size: int = 8192
    hidden_size_shape: int = 128
    num_layers_shape: int = 4
    num_freqs_shape: int = 6
    samples_perUnit_shape: int = 16
    point_sample_shape: int = 4
    sample_band_width_shape: float = 0.08
    uniformed_sample_perUnit_shape: int = 5
    training_ratio_shape: float = 0.95
    code_reg_weight_shape: float = 0.1
    weight_decay_shape: float = 0.01
    polar_fourier_shape: bool = False
    log_sampling_shape: bool = True


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--external-repo", type=Path, default=DEFAULT_EXTERNAL_REPO)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--metadata", type=Path, default=None)
    parser.add_argument("--sample-size", type=int, default=None, help="Use only the first N valid geometries.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output files.")
    parser.add_argument("--allow-cpu", action="store_true", help="Permit CPU-only execution.")
    parser.add_argument("--chunk-size", type=int, default=5000, help="Number of valid geometries per Geo2Vec chunk.")
    parser.add_argument("--num-process", type=int, default=Geo2VecConfig.num_process)
    parser.add_argument("--batch-size", type=int, default=Geo2VecConfig.batch_size)
    parser.add_argument("--samples-per-unit-shape", type=int, default=Geo2VecConfig.samples_perUnit_shape)
    parser.add_argument("--point-sample-shape", type=int, default=Geo2VecConfig.point_sample_shape)
    parser.add_argument("--uniformed-sample-per-unit-shape", type=int, default=Geo2VecConfig.uniformed_sample_perUnit_shape)
    parser.add_argument("--sample-band-width-shape", type=float, default=Geo2VecConfig.sample_band_width_shape)
    return parser.parse_args()


def default_paths_for_sample(sample_size: int | None) -> tuple[Path, Path]:
    if sample_size is None:
        return DEFAULT_OUTPUT, DEFAULT_METADATA
    stem = f"gwanak_buildings_geo2vec_shape_sample_{sample_size}"
    return DEFAULT_OUTPUT_DIR / f"{stem}.parquet", DEFAULT_OUTPUT_DIR / f"{stem}_metadata.json"


def build_config(args: argparse.Namespace) -> Geo2VecConfig:
    return Geo2VecConfig(
        num_process=args.num_process,
        batch_size=args.batch_size,
        samples_perUnit_shape=args.samples_per_unit_shape,
        point_sample_shape=args.point_sample_shape,
        sample_band_width_shape=args.sample_band_width_shape,
        uniformed_sample_perUnit_shape=args.uniformed_sample_per_unit_shape,
    )


def make_geo2vec_args(config: Geo2VecConfig, device: str) -> SimpleNamespace:
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
        num_layers_shape=config.num_layers_shape,
        z_size_shape=config.Geo_dim,
        hidden_size_shape=config.hidden_size_shape,
        num_freqs_shape=config.num_freqs_shape,
        device_shape=device,
        code_reg_weight_shape=config.code_reg_weight_shape,
        weight_decay_shape=config.weight_decay_shape,
        polar_fourier_shape=config.polar_fourier_shape,
        log_sampling_shape=config.log_sampling_shape,
        training_ratio_shape=config.training_ratio_shape,
        test_representation_location=False,
        visualSDF_location=False,
        test_representation_shape=False,
        visualSDF_shape=False,
    )


def prepare_outputs(args: argparse.Namespace) -> tuple[Path, Path]:
    default_output, default_metadata = default_paths_for_sample(args.sample_size)
    output = args.output or default_output
    metadata = args.metadata or default_metadata
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata.parent.mkdir(parents=True, exist_ok=True)

    part_paths = list(output.parent.glob(f"{PART_PREFIX}_*.parquet"))
    part_metadata_paths = list(output.parent.glob(f"{PART_PREFIX}_*_metadata.json"))
    existing = [path for path in (output, metadata, *part_paths, *part_metadata_paths) if path.exists()]
    if existing and not args.overwrite:
        raise RuntimeError(
            "Output file(s) already exist. Re-run with --overwrite to replace them:\n"
            + "\n".join(str(path) for path in existing)
        )
    if args.overwrite:
        for path in existing:
            path.unlink()
    return output, metadata


def chunk_paths(output_dir: Path, chunk_index: int) -> tuple[Path, Path]:
    stem = f"{PART_PREFIX}_{chunk_index:03d}"
    return output_dir / f"{stem}.parquet", output_dir / f"{stem}_metadata.json"


def validate_embeddings(embeddings: np.ndarray, expected_rows: int, expected_dim: int, label: str) -> None:
    require(
        embeddings.shape[0] == expected_rows,
        f"{label}: embedding row count {embeddings.shape[0]} does not match expected {expected_rows}.",
    )
    require(
        embeddings.shape[1] == expected_dim,
        f"{label}: embedding dimension {embeddings.shape[1]} != {expected_dim}.",
    )
    require(np.isfinite(embeddings).all(), f"{label}: embeddings contain NaN or Inf values.")


def embeddings_to_frame(chunk: gpd.GeoDataFrame, embeddings: np.ndarray, config: Geo2VecConfig) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "building_id": chunk["building_id"].astype(str).to_numpy(),
            "geo2vec_internal_id": chunk["geo2vec_internal_id"].to_numpy(dtype=np.int64),
        }
    )
    embedding_cols = {
        f"geo2vec_{i:03d}": embeddings[:, i].astype(np.float32)
        for i in range(config.Geo_dim)
    }
    return pd.concat([out, pd.DataFrame(embedding_cols)], axis=1)


def main() -> None:
    args = parse_args()
    config = build_config(args)
    output_path, metadata_path = prepare_outputs(args)
    start = time.time()
    start_time = time.strftime("%Y-%m-%d %H:%M:%S %Z")

    require(args.input.exists(), f"Input GeoPackage not found: {args.input}")
    require(args.external_repo.exists(), f"External repository not found: {args.external_repo}")
    require(
        (args.external_repo / "runners" / "list2embedding.py").exists(),
        f"list2embedding.py not found under external repository: {args.external_repo}",
    )

    random.seed(config.seed)
    np.random.seed(config.seed)
    sys.path.insert(0, str(args.external_repo))

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is not installed in the active Python environment.") from exc

    cuda_available = bool(torch.cuda.is_available())
    cuda_device_count = int(torch.cuda.device_count())
    gpu_name = torch.cuda.get_device_name(0) if cuda_available else None
    if not cuda_available and not args.allow_cpu:
        raise RuntimeError(
            "CUDA-enabled PyTorch is not available. This script refuses the full run on CPU. "
            "Pass --allow-cpu only for a small --sample-size test."
        )

    device = "cuda" if cuda_available else "cpu"
    torch.manual_seed(config.seed)
    if cuda_available:
        torch.cuda.manual_seed_all(config.seed)

    from runners.list2embedding import list2vec

    print(f"Python version: {sys.version}")
    print(f"torch version: {torch.__version__}")
    print(f"CUDA available: {cuda_available}")
    print(f"CUDA device count: {cuda_device_count}")
    print(f"GPU name: {gpu_name or 'none'}")
    print(f"Device used by Geo2Vec: {device}")
    print(f"Reading input: {args.input}")

    gdf = gpd.read_file(args.input)
    require("building_id" in gdf.columns, "Input GeoPackage is missing building_id.")
    require(gdf.crs is not None, "Input GeoPackage has missing CRS.")
    input_rows = int(len(gdf))
    crs_text = str(gdf.crs)

    valid_mask = gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid
    valid = gdf.loc[valid_mask, ["building_id", "geometry"]].copy()
    if args.sample_size is not None:
        require(args.sample_size > 0, "--sample-size must be positive.")
        valid = valid.head(args.sample_size).copy()
    require(len(valid) > 0, "No valid non-empty geometries found.")

    valid = valid.reset_index(drop=True)
    valid["geo2vec_internal_id"] = np.arange(len(valid), dtype=np.int64)
    n = int(len(valid))
    print(f"Input rows: {input_rows}")
    print(f"Valid geometries used: {n}")
    print(f"CRS: {crs_text}")

    geo2vec_args = make_geo2vec_args(config, device=device)
    chunk_size = int(args.chunk_size)
    require(chunk_size > 0, "--chunk-size must be positive.")
    chunk_starts = list(range(0, n, chunk_size))
    total_chunks = len(chunk_starts)
    chunk_records: list[dict[str, object]] = []
    part_paths: list[Path] = []

    for chunk_index, start_idx in enumerate(chunk_starts):
        chunk_start_time = time.time()
        end_idx = min(start_idx + chunk_size, n)
        chunk = valid.iloc[start_idx:end_idx].copy()
        chunk_n = int(len(chunk))
        part_path, part_metadata_path = chunk_paths(output_path.parent, chunk_index)
        print(
            f"[chunk {chunk_index + 1}/{total_chunks}] "
            f"rows {start_idx}:{end_idx} n={chunk_n} -> {part_path}",
            flush=True,
        )

        chunk_geometries = list(chunk.geometry)
        embeddings_raw = list2vec(
            chunk_geometries,
            Geo_dim=config.Geo_dim,
            num_epoch=config.num_epoch,
            location_learning=False,
            shape_learning=True,
            save_file_name=None,
            save_model_path=None,
            args=geo2vec_args,
        )

        embeddings_raw = np.asarray(embeddings_raw, dtype=np.float32)
        raw_rows = int(embeddings_raw.shape[0])
        extra_rows = int(max(0, raw_rows - chunk_n))
        embeddings = embeddings_raw[:chunk_n, :]
        validate_embeddings(embeddings, chunk_n, config.Geo_dim, f"chunk {chunk_index}")

        part_df = embeddings_to_frame(chunk, embeddings, config)
        part_df.to_parquet(part_path, index=False)
        part_paths.append(part_path)

        chunk_elapsed = time.time() - chunk_start_time
        chunk_metadata = {
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "part_path": str(part_path),
            "part_metadata_path": str(part_metadata_path),
            "row_start_inclusive": start_idx,
            "row_end_exclusive": end_idx,
            "number_of_geometries": chunk_n,
            "number_of_embeddings": int(embeddings.shape[0]),
            "raw_embedding_rows_returned": raw_rows,
            "extra_rows_returned": extra_rows,
            "Geo_dim": config.Geo_dim,
            "num_epoch": config.num_epoch,
            "device_used": device,
            "torch version": torch.__version__,
            "CUDA availability": cuda_available,
            "GPU name if available": gpu_name,
            "elapsed seconds": chunk_elapsed,
            "notes": (
                f"Returned {extra_rows} extra row(s); part output sliced to exactly {chunk_n} rows."
                if extra_rows
                else "No extra rows observed."
            ),
        }
        part_metadata_path.write_text(
            json.dumps(chunk_metadata, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        chunk_records.append(chunk_metadata)

        del embeddings_raw, embeddings, part_df, chunk_geometries, chunk
        gc.collect()
        if hasattr(torch, "cuda"):
            torch.cuda.empty_cache()
        print(f"[chunk {chunk_index + 1}/{total_chunks}] complete in {chunk_elapsed:.2f}s", flush=True)

    print("Combining chunk parquet files.", flush=True)
    parts = [pd.read_parquet(path) for path in part_paths]
    combined = pd.concat(parts, ignore_index=True)
    require(int(len(combined)) == n, f"Final row count {len(combined)} does not match valid input count {n}.")
    require(combined["geo2vec_internal_id"].is_unique, "Final geo2vec_internal_id values are not unique.")
    combined = combined.sort_values("geo2vec_internal_id").reset_index(drop=True)
    require(
        np.array_equal(combined["geo2vec_internal_id"].to_numpy(), np.arange(n, dtype=np.int64)),
        "Final geo2vec_internal_id sequence is not 0..n-1.",
    )
    embedding_col_names = [f"geo2vec_{i:03d}" for i in range(config.Geo_dim)]
    require(all(col in combined.columns for col in embedding_col_names), "Missing expected embedding columns.")
    final_embeddings = combined[embedding_col_names].to_numpy(dtype=np.float32)
    validate_embeddings(final_embeddings, n, config.Geo_dim, "final combined output")
    combined.to_parquet(output_path, index=False)

    end = time.time()
    metadata = {
        "input_path": str(args.input),
        "output_path": str(output_path),
        "metadata_path": str(metadata_path),
        "external_repo_path": str(args.external_repo),
        "number_of_input_buildings": input_rows,
        "number_of_valid_geometries_used": n,
        "number_of_embeddings": int(len(combined)),
        "Geo_dim": config.Geo_dim,
        "num_epoch": config.num_epoch,
        "embedding_kind": "shape",
        "CRS": crs_text,
        "Python version": sys.version,
        "torch version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "CUDA availability": cuda_available,
        "CUDA device count": cuda_device_count,
        "GPU name if available": gpu_name,
        "device_used": device,
        "start time": start_time,
        "end time": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "elapsed seconds": end - start,
        "notes about extra rows returned by GeoNeuralRepresentation": "See per-chunk metadata.",
        "sample_size_argument": args.sample_size,
        "chunk_size": chunk_size,
        "number_of_chunks": total_chunks,
        "chunk_parts": [str(path) for path in part_paths],
        "chunk_metadata": chunk_records,
        "allow_cpu": bool(args.allow_cpu),
        "geo2vec_config": asdict(config),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Embedding parquet written: {output_path}")
    print(f"Metadata JSON written: {metadata_path}")
    print(f"Embedding shape: {final_embeddings.shape}")


if __name__ == "__main__":
    main()
