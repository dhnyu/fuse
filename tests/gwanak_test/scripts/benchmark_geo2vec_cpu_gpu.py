#!/usr/bin/env python3
"""Benchmark CPU vs GPU Geo2Vec shape embeddings for Gwanak-gu buildings.

The script wraps the external GeoNeuralRepresentation repository in place and
does not modify it. It intentionally runs only controlled samples, never the
full Gwanak building set unless a user changes the sample sizes explicitly.
"""

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
RESULTS_PARQUET = OUTPUT_DIR / "geo2vec_cpu_gpu_benchmark_results.parquet"
REPORT_PATH = Path.home() / "fuse" / "tests" / "gwanak_test" / "docs" / "geo2vec_cpu_gpu_benchmark_report.md"


@dataclass(frozen=True)
class Geo2VecBenchmarkConfig:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_GPKG)
    parser.add_argument("--external-repo", type=Path, default=EXTERNAL_REPO)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--results-parquet", type=Path, default=RESULTS_PARQUET)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--sample-sizes", type=int, nargs="+", default=[1000, 5000])
    parser.add_argument("--include-10000", action="store_true", help="Append sample size 10000.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing benchmark outputs.")
    parser.add_argument("--num-process", type=int, default=Geo2VecBenchmarkConfig.num_process)
    parser.add_argument("--batch-size", type=int, default=Geo2VecBenchmarkConfig.batch_size)
    parser.add_argument("--samples-per-unit-shape", type=int, default=Geo2VecBenchmarkConfig.samples_perUnit_shape)
    parser.add_argument("--point-sample-shape", type=int, default=Geo2VecBenchmarkConfig.point_sample_shape)
    parser.add_argument("--uniformed-sample-per-unit-shape", type=int, default=Geo2VecBenchmarkConfig.uniformed_sample_perUnit_shape)
    parser.add_argument("--sample-band-width-shape", type=float, default=Geo2VecBenchmarkConfig.sample_band_width_shape)
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> Geo2VecBenchmarkConfig:
    return Geo2VecBenchmarkConfig(
        num_process=args.num_process,
        batch_size=args.batch_size,
        samples_perUnit_shape=args.samples_per_unit_shape,
        point_sample_shape=args.point_sample_shape,
        uniformed_sample_perUnit_shape=args.uniformed_sample_per_unit_shape,
        sample_band_width_shape=args.sample_band_width_shape,
    )


def make_geo2vec_args(config: Geo2VecBenchmarkConfig, device: str) -> SimpleNamespace:
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


def embedding_path(output_dir: Path, device: str, sample_size: int) -> Path:
    label = "gpu" if device == "cuda" else "cpu"
    return output_dir / f"geo2vec_benchmark_{label}_sample_{sample_size}.parquet"


def prepare_outputs(paths: list[Path], overwrite: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise RuntimeError(
            "Benchmark output file(s) already exist. Re-run with --overwrite to replace them:\n"
            + "\n".join(str(path) for path in existing)
        )
    if overwrite:
        for path in existing:
            path.unlink()


def seed_everything(seed: int, torch_module: Any | None = None) -> None:
    random.seed(seed)
    np.random.seed(seed)
    if torch_module is not None:
        torch_module.manual_seed(seed)
        if torch_module.cuda.is_available():
            torch_module.cuda.manual_seed_all(seed)


def maxrss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def parse_average_training_samples(log_text: str) -> float | None:
    match = re.search(r"In average training samples per entity:\s*([0-9.]+)", log_text)
    return float(match.group(1)) if match else None


def validate_embeddings(embeddings: np.ndarray, n_rows: int, n_dim: int) -> None:
    require(embeddings.shape == (n_rows, n_dim), f"Embedding shape {embeddings.shape} != {(n_rows, n_dim)}.")
    require(np.isfinite(embeddings).all(), "Embeddings contain NaN or infinite values.")


def embeddings_to_frame(sample: gpd.GeoDataFrame, embeddings: np.ndarray, config: Geo2VecBenchmarkConfig) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "building_id": sample["building_id"].astype(str).to_numpy(),
            "geo2vec_internal_id": sample["geo2vec_internal_id"].to_numpy(dtype=np.int64),
        }
    )
    embedding_cols = {
        f"geo2vec_{i:03d}": embeddings[:, i].astype(np.float32)
        for i in range(config.Geo_dim)
    }
    return pd.concat([out, pd.DataFrame(embedding_cols)], axis=1)


def environment_record(torch_module: Any, input_path: Path, external_repo: Path) -> dict[str, Any]:
    cuda_available = bool(torch_module.cuda.is_available())
    gpu_name = torch_module.cuda.get_device_name(0) if cuda_available else None
    gpu_total_memory_gb = (
        torch_module.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        if cuda_available
        else None
    )
    try:
        import psutil

        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        cpu_count_logical = os.cpu_count()
        cpu_count_physical = None
        ram_gb = None
    return {
        "python_version": sys.version.replace("\n", " "),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "torch_version": torch_module.__version__,
        "torch_cuda_version": torch_module.version.cuda,
        "cuda_available": cuda_available,
        "cuda_device_count": int(torch_module.cuda.device_count()),
        "gpu_name": gpu_name,
        "gpu_total_memory_gb": gpu_total_memory_gb,
        "cpu_count_logical": cpu_count_logical,
        "cpu_count_physical": cpu_count_physical,
        "ram_gb": ram_gb,
        "input_path": str(input_path),
        "external_repo": str(external_repo),
    }


def run_one(
    *,
    list2vec: Any,
    torch_module: Any,
    valid: gpd.GeoDataFrame,
    sample_size: int,
    device: str,
    config: Geo2VecBenchmarkConfig,
    output_dir: Path,
) -> dict[str, Any]:
    run_seed = config.seed + sample_size + (100000 if device == "cuda" else 0)
    seed_everything(run_seed, torch_module)
    if device == "cuda":
        torch_module.cuda.empty_cache()
        torch_module.cuda.reset_peak_memory_stats()

    sample = valid.head(sample_size).copy().reset_index(drop=True)
    sample["geo2vec_internal_id"] = np.arange(len(sample), dtype=np.int64)
    out_path = embedding_path(output_dir, device, sample_size)
    start_epoch = time.time()
    start_time = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    rss_before = maxrss_mb()
    stdout_buffer = io.StringIO()
    record: dict[str, Any] = {
        "device": device,
        "sample_size": int(sample_size),
        "actual_geometries_used": int(len(sample)),
        "Geo_dim": config.Geo_dim,
        "num_epoch": config.num_epoch,
        "shape_learning": True,
        "location_learning": False,
        "num_process": config.num_process,
        "batch_size": config.batch_size,
        "samples_perUnit_shape": config.samples_perUnit_shape,
        "point_sample_shape": config.point_sample_shape,
        "sample_band_width_shape": config.sample_band_width_shape,
        "uniformed_sample_perUnit_shape": config.uniformed_sample_perUnit_shape,
        "training_ratio_shape": config.training_ratio_shape,
        "hidden_size_shape": config.hidden_size_shape,
        "num_layers_shape": config.num_layers_shape,
        "num_freqs_shape": config.num_freqs_shape,
        "code_reg_weight_shape": config.code_reg_weight_shape,
        "weight_decay_shape": config.weight_decay_shape,
        "polar_fourier_shape": config.polar_fourier_shape,
        "log_sampling_shape": config.log_sampling_shape,
        "seed": run_seed,
        "start_time": start_time,
        "end_time": None,
        "elapsed_seconds": None,
        "succeeded": False,
        "error_message": None,
        "embedding_shape": None,
        "peak_cpu_memory_mb": None,
        "peak_gpu_memory_allocated_mb": None,
        "peak_gpu_memory_reserved_mb": None,
        "average_training_samples_per_entity": None,
        "output_embedding_path": None,
        "stdout_log_path": None,
    }

    try:
        geo2vec_args = make_geo2vec_args(config, device=device)
        geometries = list(sample.geometry)
        original_dataloader = list2vec.__globals__.get("DataLoader")
        if device == "cpu" and original_dataloader is not None:
            def cpu_dataloader(*dl_args: Any, **dl_kwargs: Any) -> Any:
                dl_kwargs["pin_memory"] = False
                return original_dataloader(*dl_args, **dl_kwargs)

            list2vec.__globals__["DataLoader"] = cpu_dataloader
        try:
            with contextlib.redirect_stdout(stdout_buffer):
                raw_embeddings = list2vec(
                    geometries,
                    Geo_dim=config.Geo_dim,
                    num_epoch=config.num_epoch,
                    location_learning=False,
                    shape_learning=True,
                    save_file_name=None,
                    save_model_path=None,
                    args=geo2vec_args,
                )
        finally:
            if device == "cpu" and original_dataloader is not None:
                list2vec.__globals__["DataLoader"] = original_dataloader
        raw_embeddings = np.asarray(raw_embeddings, dtype=np.float32)
        embeddings = raw_embeddings[: len(sample), :]
        validate_embeddings(embeddings, len(sample), config.Geo_dim)
        out = embeddings_to_frame(sample, embeddings, config)
        out.to_parquet(out_path, index=False)

        record["succeeded"] = True
        record["embedding_shape"] = f"{embeddings.shape[0]}x{embeddings.shape[1]}"
        record["output_embedding_path"] = str(out_path)
    except Exception as exc:
        record["error_message"] = f"{type(exc).__name__}: {exc}"
        if "out of memory" in str(exc).lower() or "cuda oom" in str(exc).lower():
            record["error_message"] = "CUDA OOM: " + record["error_message"]
        stdout_buffer.write("\n")
        stdout_buffer.write(traceback.format_exc())
    finally:
        log_text = stdout_buffer.getvalue()
        log_path = output_dir / f"geo2vec_benchmark_{'gpu' if device == 'cuda' else 'cpu'}_sample_{sample_size}.log"
        log_path.write_text(log_text, encoding="utf-8")
        end_epoch = time.time()
        record["end_time"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
        record["elapsed_seconds"] = end_epoch - start_epoch
        record["peak_cpu_memory_mb"] = max(0.0, maxrss_mb() - rss_before)
        record["average_training_samples_per_entity"] = parse_average_training_samples(log_text)
        record["stdout_log_path"] = str(log_path)
        if device == "cuda":
            record["peak_gpu_memory_allocated_mb"] = torch_module.cuda.max_memory_allocated() / (1024 ** 2)
            record["peak_gpu_memory_reserved_mb"] = torch_module.cuda.max_memory_reserved() / (1024 ** 2)
        del sample
        gc.collect()
        if torch_module.cuda.is_available():
            torch_module.cuda.empty_cache()
    return record


def markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "_No rows._"
    view = df.loc[:, columns].copy()
    for col in view.columns:
        if pd.api.types.is_float_dtype(view[col]):
            view[col] = view[col].map(lambda x: "" if pd.isna(x) else f"{x:.2f}")
    return view.to_markdown(index=False)


def write_report(
    *,
    report_path: Path,
    results: pd.DataFrame,
    env: dict[str, Any],
    config: Geo2VecBenchmarkConfig,
    controlled_notes: list[str],
    full_valid_count: int,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    timings = results[
        [
            "device",
            "sample_size",
            "actual_geometries_used",
            "succeeded",
            "elapsed_seconds",
            "average_training_samples_per_entity",
            "embedding_shape",
            "error_message",
        ]
    ].sort_values(["sample_size", "device"])
    gpu = results[results["device"] == "cuda"][
        [
            "sample_size",
            "succeeded",
            "peak_gpu_memory_allocated_mb",
            "peak_gpu_memory_reserved_mb",
            "error_message",
        ]
    ].sort_values("sample_size")
    failures = results.loc[~results["succeeded"], ["device", "sample_size", "error_message"]]
    cpu_success = results[(results["device"] == "cpu") & results["succeeded"]]
    gpu_success = results[(results["device"] == "cuda") & results["succeeded"]]
    cpu_5000 = cpu_success[cpu_success["sample_size"] == 5000]
    gpu_5000 = gpu_success[gpu_success["sample_size"] == 5000]

    if not cpu_5000.empty:
        cpu_feasible = (
            "CPU completed the 5,000-building benchmark, so it avoids the VRAM failure mode. "
            "A full single-model run may be possible, but runtime would scale materially beyond this test."
        )
    else:
        cpu_feasible = "CPU did not complete the 5,000-building benchmark in this run, so full single-model feasibility is not established."
    if not gpu_5000.empty:
        gpu_feasible = "GPU completed the 5,000-building benchmark with the lightweight settings."
    else:
        gpu_feasible = "GPU did not complete the 5,000-building benchmark, so lighter settings or chunking remain necessary."

    lines = [
        "# Geo2Vec CPU vs GPU Benchmark Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## Purpose",
        "",
        (
            "This benchmark compares CPU and GPU practicality for a single global "
            "GeoNeuralRepresentation / Geo2Vec shape-only model on Gwanak-gu building footprints. "
            f"The full prepared input contains {full_valid_count:,} valid geometries; this workflow deliberately "
            "uses controlled samples only."
        ),
        "",
        "## Environment",
        "",
        f"- Python: `{env['python_version']}`",
        f"- Python executable: `{env['python_executable']}`",
        f"- CUDA_VISIBLE_DEVICES: `{env['cuda_visible_devices'] or 'unset'}`",
        f"- torch: `{env['torch_version']}`",
        f"- CUDA available: `{env['cuda_available']}`",
        f"- torch CUDA version: `{env['torch_cuda_version']}`",
        f"- GPU: `{env['gpu_name'] or 'none'}`",
        f"- GPU total memory GB: `{env['gpu_total_memory_gb']:.2f}`" if env["gpu_total_memory_gb"] is not None else "- GPU total memory GB: `n/a`",
        f"- CPU logical / physical cores: `{env['cpu_count_logical']}` / `{env['cpu_count_physical']}`",
        f"- RAM GB: `{env['ram_gb']:.2f}`" if env["ram_gb"] is not None else "- RAM GB: `n/a`",
        f"- Input: `{env['input_path']}`",
        f"- External repo: `{env['external_repo']}`",
        "",
        "## Controlled Settings",
        "",
        f"- Shape-only learning: `shape_learning=True`, `location_learning=False`",
        f"- Geo_dim: `{config.Geo_dim}`",
        f"- Epochs: `{config.num_epoch}`",
        f"- Batch size: `{config.batch_size}`",
        f"- Shape model: hidden size `{config.hidden_size_shape}`, layers `{config.num_layers_shape}`, frequencies `{config.num_freqs_shape}`",
        f"- Shape sampling: samples per unit `{config.samples_perUnit_shape}`, point samples `{config.point_sample_shape}`, uniform samples `{config.uniformed_sample_perUnit_shape}`, bandwidth `{config.sample_band_width_shape}`",
        "",
        "Controllability notes:",
        "",
        *[f"- {note}" for note in controlled_notes],
        "",
        "## Timing Results",
        "",
        markdown_table(
            timings,
            [
                "device",
                "sample_size",
                "actual_geometries_used",
                "succeeded",
                "elapsed_seconds",
                "average_training_samples_per_entity",
                "embedding_shape",
                "error_message",
            ],
        ),
        "",
        "## GPU Memory",
        "",
        markdown_table(
            gpu,
            [
                "sample_size",
                "succeeded",
                "peak_gpu_memory_allocated_mb",
                "peak_gpu_memory_reserved_mb",
                "error_message",
            ],
        ),
        "",
        "## Failures Or OOMs",
        "",
        markdown_table(failures, ["device", "sample_size", "error_message"]),
        "",
        "## Interpretation",
        "",
        f"- {cpu_feasible}",
        f"- {gpu_feasible}",
        "- The previous full GPU run failed at 38,547 buildings, so chunking remains the safer full-scale path unless a new single-model GPU run uses substantially lighter sampling/model settings.",
        "- CPU removes the VRAM ceiling but does not remove the sampling and training memory/time cost; extrapolate from the successful CPU sample before launching a full single-model run.",
        "",
        "## Recommendation",
        "",
        (
            "For the next full-scale experiment, keep the chunked production workflow as the reliable baseline. "
            "If a single global model is still needed, run a guarded CPU full experiment first with the same lightweight settings and a wall-time monitor, then try GPU only after further reducing sampling or batch/model size."
        ),
        "",
        "## Outputs",
        "",
        f"- Results parquet: `{RESULTS_PARQUET}`",
        "- Successful embedding parquet files are listed in the result table under `output_embedding_path`.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    config = build_config(args)
    sample_sizes = list(dict.fromkeys(args.sample_sizes + ([10000] if args.include_10000 else [])))
    require(all(size > 0 for size in sample_sizes), "All sample sizes must be positive.")
    require(args.input.exists(), f"Input GeoPackage not found: {args.input}")
    require(args.external_repo.exists(), f"External repository not found: {args.external_repo}")
    require((args.external_repo / "runners" / "list2embedding.py").exists(), "External list2embedding.py not found.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.results_parquet.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    planned_devices = ["cpu"]
    sys.path.insert(0, str(args.external_repo))
    import torch

    if torch.cuda.is_available():
        planned_devices.append("cuda")
    planned_outputs = [args.results_parquet, args.report]
    for size in sample_sizes:
        for device in planned_devices:
            planned_outputs.append(embedding_path(args.output_dir, device, size))
            planned_outputs.append(args.output_dir / f"geo2vec_benchmark_{'gpu' if device == 'cuda' else 'cpu'}_sample_{size}.log")
    prepare_outputs(planned_outputs, args.overwrite)

    seed_everything(config.seed, torch)
    from runners.list2embedding import list2vec

    print(f"Python executable: {sys.executable}")
    print(f"torch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"Reading input: {args.input}")
    gdf = gpd.read_file(args.input)
    require("building_id" in gdf.columns, "Input GeoPackage is missing building_id.")
    require(gdf.crs is not None, "Input GeoPackage has missing CRS.")
    valid_mask = gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid
    valid = gdf.loc[valid_mask, ["building_id", "geometry"]].copy().reset_index(drop=True)
    require(len(valid) >= max(sample_sizes), f"Only {len(valid)} valid geometries available for requested samples.")

    env = environment_record(torch, args.input, args.external_repo)
    controlled_notes = [
        "`list2vec` exposes `Geo_dim` and `num_epoch` directly.",
        "Sampling, batch size, and shape model settings are controllable through an argparse-like `args` namespace.",
        "The external shape branch reads `args.device` when constructing the PyTorch device; `args.device_shape` exists but is not used for device selection in `list2vec`.",
        "DataLoader workers are hard-coded to `0` inside `list2vec`; `num_workers` can be supplied but is not used there.",
        "For CPU runs with CUDA-visible PyTorch, the wrapper temporarily forces the external `DataLoader` calls to `pin_memory=False` so CPU execution does not allocate CUDA pinned memory.",
    ]

    records: list[dict[str, Any]] = []
    for sample_size in sample_sizes:
        for device in planned_devices:
            print(f"Starting Geo2Vec benchmark: device={device}, sample_size={sample_size}", flush=True)
            record = run_one(
                list2vec=list2vec,
                torch_module=torch,
                valid=valid,
                sample_size=sample_size,
                device=device,
                config=config,
                output_dir=args.output_dir,
            )
            records.append(record)
            print(
                f"Finished device={device}, sample_size={sample_size}, "
                f"succeeded={record['succeeded']}, elapsed={record['elapsed_seconds']:.2f}s",
                flush=True,
            )

    results = pd.DataFrame(records)
    results.to_parquet(args.results_parquet, index=False)
    (args.output_dir / "geo2vec_cpu_gpu_benchmark_environment.json").write_text(
        json.dumps({"environment": env, "config": asdict(config), "sample_sizes": sample_sizes}, indent=2),
        encoding="utf-8",
    )
    write_report(
        report_path=args.report,
        results=results,
        env=env,
        config=config,
        controlled_notes=controlled_notes,
        full_valid_count=int(len(valid)),
    )

    successful = results[results["succeeded"]].copy()
    conclusion = "No successful benchmark runs completed."
    if not successful.empty:
        fastest = successful.sort_values("elapsed_seconds").iloc[0]
        conclusion = (
            f"Fastest successful run: {fastest['device']} sample {int(fastest['sample_size'])} "
            f"in {fastest['elapsed_seconds']:.2f}s."
        )
    print(f"Script path: {Path(__file__).resolve()}")
    print(f"Report path: {args.report}")
    print(f"Benchmark result parquet path: {args.results_parquet}")
    print(f"Concise conclusion: {conclusion}")


if __name__ == "__main__":
    main()
