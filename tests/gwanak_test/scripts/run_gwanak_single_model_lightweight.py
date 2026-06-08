#!/usr/bin/env python3
"""Run a full single-model lightweight Geo2Vec shape embedding for Gwanak."""

from __future__ import annotations

import argparse
import contextlib
import gc
import io
import json
import os
import platform
import random
import re
import resource
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd


INPUT_GPKG = Path.home() / "fusedatalarge" / "processed" / "gwanak_buildings_vworld.gpkg"
EXTERNAL_REPO = Path.home() / "fuse_external" / "GeoNeuralRepresentation"
OUTPUT_DIR = Path.home() / "fusedata" / "gwanak_test" / "validation"
OUTPUT_PARQUET = OUTPUT_DIR / "gwanak_buildings_geo2vec_shape_single_model_lightweight.parquet"
METADATA_JSON = OUTPUT_DIR / "gwanak_buildings_geo2vec_shape_single_model_lightweight_metadata.json"
REPORT_PATH = Path.home() / "fuse" / "tests" / "gwanak_test" / "docs" / "gwanak_single_model_lightweight_experiment.md"
STDOUT_LOG = OUTPUT_DIR / "gwanak_buildings_geo2vec_shape_single_model_lightweight.log"
UMAP_PARQUET = OUTPUT_DIR / "gwanak_single_model_umap.parquet"
UMAP_PNG = OUTPUT_DIR / "gwanak_single_model_umap.png"
CHUNKED_PARQUET = Path.home() / "fusedata" / "embeddings" / "gwanak_buildings_geo2vec_shape_full.parquet"


@dataclass(frozen=True)
class Geo2VecConfig:
    Geo_dim: int = 32
    num_epoch: int = 1
    seed: int = 20260608
    num_process: int = 8
    batch_size: int = 4096
    hidden_size_shape: int = 128
    num_layers_shape: int = 4
    num_freqs_shape: int = 4
    samples_perUnit_shape: int = 8
    point_sample_shape: int = 2
    sample_band_width_shape: float = 0.08
    uniformed_sample_perUnit_shape: int = 4
    training_ratio_shape: float = 0.9
    code_reg_weight_shape: float = 0.1
    weight_decay_shape: float = 0.01
    polar_fourier_shape: bool = False
    log_sampling_shape: bool = True


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def maybe_select_free_gpu() -> str | None:
    if os.environ.get("CUDA_VISIBLE_DEVICES"):
        return os.environ["CUDA_VISIBLE_DEVICES"]
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    gpus: list[tuple[int, int, int]] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            gpus.append((int(parts[0]), int(parts[1]), int(parts[2])))
    if not gpus:
        return None
    best_index, used_mb, free_mb = max(gpus, key=lambda row: row[2])
    if best_index != 0 and free_mb > 1024:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(best_index)
        return str(best_index)
    if used_mb > 1024:
        free_candidates = [row for row in gpus if row[2] > 1024]
        if free_candidates:
            selected = max(free_candidates, key=lambda row: row[2])[0]
            os.environ["CUDA_VISIBLE_DEVICES"] = str(selected)
            return str(selected)
    return None


SELECTED_CUDA_VISIBLE_DEVICES = maybe_select_free_gpu()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_GPKG)
    parser.add_argument("--external-repo", type=Path, default=EXTERNAL_REPO)
    parser.add_argument("--output", type=Path, default=OUTPUT_PARQUET)
    parser.add_argument("--metadata", type=Path, default=METADATA_JSON)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--umap-parquet", type=Path, default=UMAP_PARQUET)
    parser.add_argument("--umap-png", type=Path, default=UMAP_PNG)
    parser.add_argument("--chunked-parquet", type=Path, default=CHUNKED_PARQUET)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


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


def seed_everything(seed: int, torch_module: Any | None = None) -> None:
    random.seed(seed)
    np.random.seed(seed)
    if torch_module is not None:
        torch_module.manual_seed(seed)
        if torch_module.cuda.is_available():
            torch_module.cuda.manual_seed_all(seed)


def maxrss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def current_rss_mb() -> float | None:
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / (1024 ** 2)
    except Exception:
        return None


def parse_average_training_samples(log_text: str) -> float | None:
    match = re.search(r"In average training samples per entity:\s*([0-9.]+)", log_text)
    return float(match.group(1)) if match else None


def validate_embeddings(out: pd.DataFrame, expected_n: int, expected_dim: int) -> None:
    require(len(out) == expected_n, f"Output rows {len(out)} != expected {expected_n}.")
    require(out["building_id"].notna().all(), "Missing building_id values.")
    require(out["building_id"].is_unique, "building_id values are not unique.")
    expected_ids = np.arange(expected_n, dtype=np.int64)
    actual_ids = out["geo2vec_internal_id"].to_numpy(dtype=np.int64)
    require(np.array_equal(actual_ids, expected_ids), "geo2vec_internal_id is not 0..n-1.")
    embedding_cols = [col for col in out.columns if re.fullmatch(r"geo2vec_\d{3}", col)]
    require(len(embedding_cols) == expected_dim, f"Embedding column count {len(embedding_cols)} != {expected_dim}.")
    values = out[embedding_cols].to_numpy(dtype=np.float32)
    require(not np.isnan(values).any(), "Embeddings contain NaN.")
    require(not np.isinf(values).any(), "Embeddings contain Inf.")


def embeddings_to_frame(gdf: gpd.GeoDataFrame, embeddings: np.ndarray, config: Geo2VecConfig) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "building_id": gdf["building_id"].astype(str).to_numpy(),
            "geo2vec_internal_id": gdf["geo2vec_internal_id"].to_numpy(dtype=np.int64),
        }
    )
    embedding_cols = {
        f"geo2vec_{i:03d}": embeddings[:, i].astype(np.float32)
        for i in range(config.Geo_dim)
    }
    return pd.concat([out, pd.DataFrame(embedding_cols)], axis=1)


def compare_with_chunked(single: pd.DataFrame, chunked_path: Path) -> dict[str, Any]:
    if not chunked_path.exists():
        return {"chunked_path": str(chunked_path), "exists": False}
    chunked = pd.read_parquet(chunked_path)
    single_cols = [col for col in single.columns if re.fullmatch(r"geo2vec_\d{3}", col)]
    chunked_cols = [col for col in chunked.columns if re.fullmatch(r"geo2vec_\d{3}", col)]
    joined_ids = set(single["building_id"].astype(str)).intersection(set(chunked["building_id"].astype(str)))
    return {
        "chunked_path": str(chunked_path),
        "exists": True,
        "single_rows": int(len(single)),
        "chunked_rows": int(len(chunked)),
        "matched_building_ids": int(len(joined_ids)),
        "single_embedding_dim": int(len(single_cols)),
        "chunked_embedding_dim": int(len(chunked_cols)),
        "comparison_note": (
            "Direct vector comparison is not meaningful because the previous output was trained "
            "chunk-by-chunk in separate latent spaces and has a different embedding dimension."
        ),
    }


def run_umap(output_path: Path, umap_parquet: Path, umap_png: Path) -> dict[str, Any]:
    r_code = f"""
options(warn = 1)
suppressPackageStartupMessages({{
  library(arrow)
  library(data.table)
  library(uwot)
  library(ggplot2)
}})
input_path <- {json.dumps(str(output_path))}
out_parquet <- {json.dumps(str(umap_parquet))}
out_png <- {json.dumps(str(umap_png))}
dt <- as.data.table(arrow::read_parquet(input_path))
embedding_cols <- grep('^geo2vec_[0-9]{{3}}$', names(dt), value = TRUE)
stopifnot(length(embedding_cols) == 32L)
x <- as.matrix(dt[, ..embedding_cols])
set.seed(20260608L)
um <- uwot::umap(
  x,
  n_neighbors = 30,
  min_dist = 0.05,
  metric = 'cosine',
  n_threads = max(1L, parallel::detectCores() - 2L),
  verbose = FALSE
)
out <- data.table(
  building_id = dt$building_id,
  geo2vec_internal_id = dt$geo2vec_internal_id,
  umap_1 = as.numeric(um[, 1]),
  umap_2 = as.numeric(um[, 2])
)
arrow::write_parquet(out, out_parquet)
p <- ggplot(out, aes(umap_1, umap_2)) +
  geom_point(size = 0.25, alpha = 0.45, color = '#2f5d7c') +
  coord_equal() +
  theme_minimal(base_size = 11) +
  labs(title = 'Gwanak Single-Model Geo2Vec UMAP', x = 'UMAP 1', y = 'UMAP 2')
ggsave(out_png, p, width = 8, height = 7, dpi = 220)
"""
    result = subprocess.run(["Rscript", "-e", r_code], capture_output=True, text=True)
    return {
        "succeeded": result.returncode == 0,
        "returncode": result.returncode,
        "umap_parquet": str(umap_parquet) if result.returncode == 0 else None,
        "umap_png": str(umap_png) if result.returncode == 0 else None,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def write_report(path: Path, metadata: dict[str, Any]) -> None:
    status = "succeeded" if metadata.get("succeeded") else "failed"
    comparison = metadata.get("chunked_comparison") or {}
    umap = metadata.get("umap") or {}
    lines = [
        "# Gwanak Single-Model Lightweight Geo2Vec Experiment",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## Summary",
        "",
        f"- Single-model training status: `{status}`",
        f"- Rows used: `{metadata.get('number_of_geometries_used')}`",
        f"- Runtime seconds: `{metadata.get('elapsed_seconds')}`",
        f"- Average training samples per entity: `{metadata.get('average_training_samples_per_entity')}`",
        f"- Device: `{metadata.get('device')}`",
        f"- CUDA_VISIBLE_DEVICES: `{metadata.get('cuda_visible_devices') or 'unset'}`",
        f"- Peak GPU allocated MB: `{metadata.get('peak_gpu_memory_allocated_mb')}`",
        f"- Peak GPU reserved MB: `{metadata.get('peak_gpu_memory_reserved_mb')}`",
        f"- Peak process max RSS MB: `{metadata.get('peak_process_maxrss_mb')}`",
        "",
        "## Configuration",
        "",
        "Shape-only learning was used: `shape_learning=True`, `location_learning=False`.",
        "",
        "```json",
        json.dumps(metadata.get("geo2vec_config", {}), indent=2),
        "```",
        "",
        "## Validation",
        "",
        f"- Output parquet: `{metadata.get('output_path')}`",
        f"- Metadata JSON: `{metadata.get('metadata_path')}`",
        f"- Validation succeeded: `{metadata.get('validation_succeeded')}`",
        f"- Embedding shape: `{metadata.get('embedding_shape')}`",
        f"- Error message: `{metadata.get('error_message')}`",
        "",
        "## UMAP",
        "",
        f"- UMAP succeeded: `{umap.get('succeeded')}`",
        f"- UMAP parquet: `{umap.get('umap_parquet')}`",
        f"- UMAP PNG: `{umap.get('umap_png')}`",
        "",
        "## Comparison With Chunked Embedding",
        "",
        f"- Chunked path: `{comparison.get('chunked_path')}`",
        f"- Chunked exists: `{comparison.get('exists')}`",
        f"- Single rows: `{comparison.get('single_rows')}`",
        f"- Chunked rows: `{comparison.get('chunked_rows')}`",
        f"- Matched building IDs: `{comparison.get('matched_building_ids')}`",
        f"- Single dimension: `{comparison.get('single_embedding_dim')}`",
        f"- Chunked dimension: `{comparison.get('chunked_embedding_dim')}`",
        f"- Note: {comparison.get('comparison_note')}",
        "",
        "The important methodological difference is that this run learns one global latent space for all Gwanak buildings. The earlier full Gwanak output was generated chunk-by-chunk, so its vectors are not guaranteed to be mutually aligned across chunks.",
        "",
        "## Scaling Implications",
        "",
        "For Seoul, success here would justify a staged single-model feasibility study at larger deterministic samples before a full Seoul run. Monitor GPU reserved memory and sampled points per entity, not only final parquet size.",
        "",
        "For nationwide Korea, even a successful Gwanak single-model run does not prove that a naive nationwide single model is practical. The nationwide strategy should still evaluate anchor-aligned chunks or a redesigned out-of-sample geometry encoder.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = Geo2VecConfig()
    for path in [args.output, args.metadata, args.report, args.umap_parquet, args.umap_png, STDOUT_LOG]:
        if path.exists() and not args.overwrite:
            raise RuntimeError(f"Output exists; rerun with --overwrite: {path}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    require(args.input.exists(), f"Input not found: {args.input}")
    require(args.external_repo.exists(), f"External repo not found: {args.external_repo}")
    sys.path.insert(0, str(args.external_repo))

    import torch

    seed_everything(config.seed, torch)
    cuda_available = bool(torch.cuda.is_available())
    device = "cuda" if cuda_available else "cpu"
    if cuda_available:
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    from runners.list2embedding import list2vec

    start = time.time()
    stdout_buffer = io.StringIO()
    metadata: dict[str, Any] = {
        "input_path": str(args.input),
        "external_repo": str(args.external_repo),
        "output_path": str(args.output),
        "metadata_path": str(args.metadata),
        "report_path": str(args.report),
        "stdout_log_path": str(STDOUT_LOG),
        "chunked_comparison_path": str(args.chunked_parquet),
        "python_version": sys.version.replace("\n", " "),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": cuda_available,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "selected_cuda_visible_devices": SELECTED_CUDA_VISIBLE_DEVICES,
        "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
        "device": device,
        "geo2vec_config": asdict(config),
        "shape_learning": True,
        "location_learning": False,
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "succeeded": False,
        "validation_succeeded": False,
        "error_message": None,
    }
    try:
        gdf = gpd.read_file(args.input)
        require("building_id" in gdf.columns, "Input is missing building_id.")
        valid_mask = gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid
        valid = gdf.loc[valid_mask, ["building_id", "geometry"]].copy().reset_index(drop=True)
        valid["geo2vec_internal_id"] = np.arange(len(valid), dtype=np.int64)
        require(len(valid) == 38547, f"Expected 38,547 valid buildings, found {len(valid)}.")
        metadata["number_of_input_rows"] = int(len(gdf))
        metadata["number_of_geometries_used"] = int(len(valid))
        metadata["crs"] = str(gdf.crs)

        geo2vec_args = make_geo2vec_args(config, device=device)
        if device == "cpu":
            original_dataloader = list2vec.__globals__.get("DataLoader")

            def cpu_dataloader(*dl_args: Any, **dl_kwargs: Any) -> Any:
                dl_kwargs["pin_memory"] = False
                return original_dataloader(*dl_args, **dl_kwargs)

            if original_dataloader is not None:
                list2vec.__globals__["DataLoader"] = cpu_dataloader
        else:
            original_dataloader = None

        try:
            with contextlib.redirect_stdout(stdout_buffer):
                raw_embeddings = list2vec(
                    list(valid.geometry),
                    Geo_dim=config.Geo_dim,
                    num_epoch=config.num_epoch,
                    location_learning=False,
                    shape_learning=True,
                    save_file_name=None,
                    save_model_path=None,
                    args=geo2vec_args,
                )
        finally:
            if original_dataloader is not None:
                list2vec.__globals__["DataLoader"] = original_dataloader

        raw_embeddings = np.asarray(raw_embeddings, dtype=np.float32)
        embeddings = raw_embeddings[: len(valid), :]
        require(embeddings.shape == (len(valid), config.Geo_dim), f"Unexpected embedding shape: {embeddings.shape}")
        out = embeddings_to_frame(valid, embeddings, config)
        validate_embeddings(out, len(valid), config.Geo_dim)
        out.to_parquet(args.output, index=False)
        metadata["succeeded"] = True
        metadata["validation_succeeded"] = True
        metadata["embedding_shape"] = f"{embeddings.shape[0]}x{embeddings.shape[1]}"
        metadata["raw_embedding_shape"] = f"{raw_embeddings.shape[0]}x{raw_embeddings.shape[1]}"
        metadata["extra_rows_returned"] = int(max(0, raw_embeddings.shape[0] - len(valid)))
        metadata["chunked_comparison"] = compare_with_chunked(out, args.chunked_parquet)
        metadata["umap"] = run_umap(args.output, args.umap_parquet, args.umap_png)
    except Exception as exc:
        metadata["error_message"] = f"{type(exc).__name__}: {exc}"
        stdout_buffer.write("\n")
        stdout_buffer.write(traceback.format_exc())
    finally:
        elapsed = time.time() - start
        log_text = stdout_buffer.getvalue()
        STDOUT_LOG.write_text(log_text, encoding="utf-8")
        metadata["average_training_samples_per_entity"] = parse_average_training_samples(log_text)
        metadata["elapsed_seconds"] = elapsed
        metadata["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
        metadata["peak_process_maxrss_mb"] = maxrss_mb()
        metadata["current_process_rss_mb"] = current_rss_mb()
        if cuda_available:
            metadata["peak_gpu_memory_allocated_mb"] = torch.cuda.max_memory_allocated() / (1024 ** 2)
            metadata["peak_gpu_memory_reserved_mb"] = torch.cuda.max_memory_reserved() / (1024 ** 2)
            try:
                metadata["cuda_memory_summary"] = torch.cuda.memory_summary(abbreviated=True)
            except Exception:
                metadata["cuda_memory_summary"] = None
        else:
            metadata["peak_gpu_memory_allocated_mb"] = None
            metadata["peak_gpu_memory_reserved_mb"] = None
        args.metadata.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        write_report(args.report, metadata)
        gc.collect()
        if cuda_available:
            torch.cuda.empty_cache()

    print(f"Script path: {Path(__file__).resolve()}")
    print(f"Output parquet: {args.output}")
    print(f"Metadata JSON: {args.metadata}")
    print(f"Report path: {args.report}")
    print(f"Succeeded: {metadata['succeeded']}")
    print(f"Elapsed seconds: {metadata['elapsed_seconds']:.2f}")
    if metadata.get("error_message"):
        print(f"Error: {metadata['error_message']}")
    if not metadata["succeeded"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
