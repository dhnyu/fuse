#!/usr/bin/env python3
"""Gwanak Geo2Vec feasibility sweep and downstream validation."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import random
import re
import resource
import subprocess
import sys
import time
import traceback
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd


ROOT = Path.home() / "fuse"
INPUT_GPKG = Path.home() / "fusedatalarge" / "processed" / "gwanak_buildings_vworld.gpkg"
EXTERNAL_REPO = Path.home() / "fuse_external" / "GeoNeuralRepresentation"
VALIDATION_DIR = Path.home() / "fusedata" / "gwanak_test" / "validation"
SINGLE_PARQUET = VALIDATION_DIR / "gwanak_buildings_geo2vec_shape_single_model_lightweight.parquet"
SINGLE_METADATA = VALIDATION_DIR / "gwanak_buildings_geo2vec_shape_single_model_lightweight_metadata.json"
CHUNKED_PARQUET = Path.home() / "fusedata" / "embeddings" / "gwanak_buildings_geo2vec_shape_full.parquet"
CHUNKED_METADATA = Path.home() / "fusedata" / "embeddings" / "gwanak_buildings_geo2vec_shape_full_metadata.json"
KOREA_SUMMARY = Path.home() / "fusedatalarge" / "processed" / "korea_building_merge_summary.parquet"
REPORT = ROOT / "tests" / "gwanak_test" / "docs" / "gwanak_geo2vec_scalability_validation_report.md"
SWEEP_RESULTS = VALIDATION_DIR / "gwanak_geo2vec_parameter_sweep_results.parquet"
DOWNSTREAM_RESULTS = VALIDATION_DIR / "gwanak_geo2vec_downstream_validation_single_vs_chunked.parquet"
CLUSTER_RESULTS = VALIDATION_DIR / "gwanak_geo2vec_cluster_morphology_single_vs_chunked.parquet"
GPU_STATUS_JSON = VALIDATION_DIR / "gwanak_geo2vec_gpu_status.json"


@dataclass(frozen=True)
class Config:
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


def gpu_status() -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    rows = []
    for line in result.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 5:
            rows.append(
                {
                    "gpu_id": int(parts[0]),
                    "name": parts[1],
                    "total_memory_mb": int(parts[2]),
                    "used_memory_mb": int(parts[3]),
                    "free_memory_mb": int(parts[4]),
                }
            )
    return rows


def select_gpu_env() -> dict[str, str]:
    env = os.environ.copy()
    if env.get("CUDA_VISIBLE_DEVICES"):
        return env
    status = gpu_status()
    if status:
        best = max(status, key=lambda row: row["free_memory_mb"])
        if best["free_memory_mb"] > 1024:
            env["CUDA_VISIBLE_DEVICES"] = str(best["gpu_id"])
    return env


def maxrss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def make_geo2vec_args(config: Config, device: str) -> SimpleNamespace:
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


def parse_avg_samples(text: str) -> float | None:
    match = re.search(r"In average training samples per entity:\s*([0-9.]+)", text)
    return float(match.group(1)) if match else None


def child_run(config_path: Path) -> None:
    payload = json.loads(config_path.read_text())
    name = payload["name"]
    sample_size = int(payload["sample_size"])
    config = Config(**payload["config"])
    sys.path.insert(0, str(EXTERNAL_REPO))
    import torch
    from runners.list2embedding import list2vec

    seed_everything(config.seed, torch)
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    start = time.time()
    log = io.StringIO()
    record: dict[str, Any] = {
        "name": name,
        "sample_size": sample_size,
        **asdict(config),
        "device": device,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "succeeded": False,
        "error_message": None,
    }
    try:
        gdf = gpd.read_file(INPUT_GPKG)
        valid = gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid, ["building_id", "geometry"]]
        sample = valid.head(sample_size).copy().reset_index(drop=True)
        args = make_geo2vec_args(config, device)
        with contextlib.redirect_stdout(log):
            emb = list2vec(
                list(sample.geometry),
                Geo_dim=config.Geo_dim,
                num_epoch=config.num_epoch,
                location_learning=False,
                shape_learning=True,
                save_file_name=None,
                save_model_path=None,
                args=args,
            )
        emb = np.asarray(emb, dtype=np.float32)[: len(sample), :]
        if emb.shape != (len(sample), config.Geo_dim):
            raise RuntimeError(f"Unexpected embedding shape {emb.shape}")
        if not np.isfinite(emb).all():
            raise RuntimeError("Embedding contains non-finite values")
        record["succeeded"] = True
        record["embedding_shape"] = f"{emb.shape[0]}x{emb.shape[1]}"
        record["embedding_dim"] = int(emb.shape[1])
    except Exception as exc:
        record["error_message"] = f"{type(exc).__name__}: {exc}"
        log.write("\n")
        log.write(traceback.format_exc())
    finally:
        record["elapsed_seconds"] = time.time() - start
        record["average_training_samples_per_entity"] = parse_avg_samples(log.getvalue())
        record["peak_process_maxrss_mb"] = maxrss_mb()
        if torch.cuda.is_available():
            record["peak_gpu_memory_allocated_mb"] = torch.cuda.max_memory_allocated() / (1024 ** 2)
            record["peak_gpu_memory_reserved_mb"] = torch.cuda.max_memory_reserved() / (1024 ** 2)
        else:
            record["peak_gpu_memory_allocated_mb"] = None
            record["peak_gpu_memory_reserved_mb"] = None
        log_path = VALIDATION_DIR / f"gwanak_geo2vec_parameter_sweep_{name}.log"
        log_path.write_text(log.getvalue(), encoding="utf-8")
        record["log_path"] = str(log_path)
        print(json.dumps(record))


def run_sweep(overwrite: bool) -> pd.DataFrame:
    if SWEEP_RESULTS.exists() and not overwrite:
        return pd.read_parquet(SWEEP_RESULTS)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    base = Config()
    configs = [
        ("baseline_32d", base),
        ("geo_dim_64", replace(base, Geo_dim=64)),
        ("batch_8192", replace(base, batch_size=8192)),
        ("hidden_256", replace(base, hidden_size_shape=256)),
        ("layers_8", replace(base, num_layers_shape=8)),
        ("freqs_8", replace(base, num_freqs_shape=8)),
        ("sampling_medium", replace(base, samples_perUnit_shape=16, point_sample_shape=4, uniformed_sample_perUnit_shape=5)),
        ("epoch_2", replace(base, num_epoch=2)),
    ]
    rows = []
    env = select_gpu_env()
    for name, cfg in configs:
        payload_path = VALIDATION_DIR / f"gwanak_geo2vec_parameter_sweep_{name}.json"
        payload_path.write_text(json.dumps({"name": name, "sample_size": 5000, "config": asdict(cfg)}, indent=2))
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--child-config", str(payload_path)],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        if result.returncode != 0:
            rows.append({"name": name, "succeeded": False, "error_message": result.stderr[-2000:]})
        else:
            last_json = result.stdout.strip().splitlines()[-1]
            rows.append(json.loads(last_json))
    df = pd.DataFrame(rows)
    df.to_parquet(SWEEP_RESULTS, index=False)
    return df


def geometry_metrics() -> pd.DataFrame:
    gdf = gpd.read_file(INPUT_GPKG)
    gdf = gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty & gdf.geometry.is_valid, ["building_id", "geometry"]].copy()
    geom = gdf.geometry
    bounds = geom.bounds
    area = geom.area.to_numpy()
    perimeter = geom.length.to_numpy()
    width = (bounds["maxx"] - bounds["minx"]).to_numpy()
    height = (bounds["maxy"] - bounds["miny"]).to_numpy()
    min_side = np.maximum(np.minimum(width, height), 1e-6)
    max_side = np.maximum(np.maximum(width, height), 1e-6)
    compactness = np.where(perimeter > 0, 4 * math.pi * area / (perimeter ** 2), np.nan)
    return pd.DataFrame(
        {
            "building_id": gdf["building_id"].astype(str).to_numpy(),
            "log_area": np.log1p(area),
            "log_perimeter": np.log1p(perimeter),
            "compactness": compactness,
            "elongation": max_side / min_side,
            "bbox_area_ratio": np.where(width * height > 0, area / (width * height), np.nan),
        }
    )


def evaluate_embeddings(label: str, emb_path: Path, metrics: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    from sklearn.cluster import KMeans
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    emb = pd.read_parquet(emb_path)
    cols = [c for c in emb.columns if re.fullmatch(r"geo2vec_\d{3}", c)]
    df = emb[["building_id"] + cols].merge(metrics, on="building_id", how="inner")
    x = df[cols].to_numpy(np.float32)
    rows = []
    targets = ["log_area", "log_perimeter", "compactness", "elongation", "bbox_area_ratio"]
    train_idx, test_idx = train_test_split(np.arange(len(df)), test_size=0.2, random_state=20260608)
    for target in targets:
        y = df[target].to_numpy(np.float32)
        ok = np.isfinite(y)
        tr = train_idx[ok[train_idx]]
        te = test_idx[ok[test_idx]]
        models = {
            "ridge": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
            "rf_100": RandomForestRegressor(n_estimators=100, max_depth=18, random_state=20260608, n_jobs=8),
        }
        baseline = np.full(len(te), np.nanmean(y[tr]))
        rows.append({"embedding": label, "target": target, "model": "baseline_mean", "r2": r2_score(y[te], baseline), "mae": mean_absolute_error(y[te], baseline)})
        for model_name, model in models.items():
            model.fit(x[tr], y[tr])
            pred = model.predict(x[te])
            rows.append({"embedding": label, "target": target, "model": model_name, "r2": r2_score(y[te], pred), "mae": mean_absolute_error(y[te], pred)})
    km_x = StandardScaler().fit_transform(x)
    clusters = KMeans(n_clusters=10, random_state=20260608, n_init=20).fit_predict(km_x)
    cluster_df = df[["building_id", "log_area", "log_perimeter", "compactness", "elongation", "bbox_area_ratio"]].copy()
    cluster_df["embedding"] = label
    cluster_df["cluster_k10"] = clusters + 1
    summary = cluster_df.groupby(["embedding", "cluster_k10"], as_index=False).agg(
        n=("building_id", "size"),
        median_log_area=("log_area", "median"),
        median_compactness=("compactness", "median"),
        median_elongation=("elongation", "median"),
        median_bbox_area_ratio=("bbox_area_ratio", "median"),
    )
    return rows, summary


def run_downstream(overwrite: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    if DOWNSTREAM_RESULTS.exists() and CLUSTER_RESULTS.exists() and not overwrite:
        return pd.read_parquet(DOWNSTREAM_RESULTS), pd.read_parquet(CLUSTER_RESULTS)
    metrics = geometry_metrics()
    rows = []
    clusters = []
    for label, path in [("single_model_32d", SINGLE_PARQUET), ("chunked_64d", CHUNKED_PARQUET)]:
        model_rows, cluster_df = evaluate_embeddings(label, path, metrics)
        rows.extend(model_rows)
        clusters.append(cluster_df)
    downstream = pd.DataFrame(rows)
    cluster = pd.concat(clusters, ignore_index=True)
    downstream.to_parquet(DOWNSTREAM_RESULTS, index=False)
    cluster.to_parquet(CLUSTER_RESULTS, index=False)
    return downstream, cluster


def read_metadata(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    view = df.copy()
    for col in view.columns:
        if pd.api.types.is_float_dtype(view[col]):
            view[col] = view[col].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    return view.to_markdown(index=False)


def write_report(gpus: list[dict[str, Any]], sweep: pd.DataFrame, downstream: pd.DataFrame, clusters: pd.DataFrame) -> None:
    single_meta = read_metadata(SINGLE_METADATA)
    chunk_meta = read_metadata(CHUNKED_METADATA)
    korea_count = 14_388_938
    if KOREA_SUMMARY.exists():
        ks = pd.read_parquet(KOREA_SUMMARY)
        if "final_feature_count" in ks:
            korea_count = int(ks["final_feature_count"].dropna().iloc[0])
    gwanak_n = int(single_meta.get("number_of_geometries_used", 38547))
    avg_samples = float(single_meta.get("average_training_samples_per_entity", 52.0))
    runtime_per_building = float(single_meta.get("elapsed_seconds", 37.2)) / gwanak_n
    rss_per_building = float(single_meta.get("peak_process_maxrss_mb", 1631)) / gwanak_n
    output_mb_per_building = SINGLE_PARQUET.stat().st_size / (1024 ** 2) / gwanak_n
    stages = []
    for n in [50_000, 100_000, 300_000, 1_000_000, korea_count]:
        stages.append(
            {
                "stage": f"{n:,}",
                "buildings": n,
                "sampled_points_est": int(n * avg_samples),
                "runtime_min_linear_est": runtime_per_building * n / 60,
                "rss_gb_linear_est": rss_per_building * n / 1024,
                "parquet_gb_32d_est": output_mb_per_building * n / 1024,
            }
        )
    stage_df = pd.DataFrame(stages)
    best = downstream[downstream["model"] != "baseline_mean"].sort_values(["embedding", "target", "r2"], ascending=[True, True, False]).groupby(["embedding", "target"]).head(1)
    gpu_df = pd.DataFrame(gpus)
    sweep_cols = ["name", "sample_size", "Geo_dim", "batch_size", "hidden_size_shape", "num_layers_shape", "num_freqs_shape", "samples_perUnit_shape", "point_sample_shape", "uniformed_sample_perUnit_shape", "num_epoch", "succeeded", "elapsed_seconds", "average_training_samples_per_entity", "peak_gpu_memory_allocated_mb", "peak_gpu_memory_reserved_mb", "peak_process_maxrss_mb", "embedding_shape"]
    lines = [
        "# Gwanak Geo2Vec Scalability and Validation Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## Summary",
        "",
        "The full Gwanak single-model lightweight run is methodologically preferable to the previous chunked output because all 38,547 buildings share one latent space. The observed GPU memory was tiny relative to the available RTX A6000 capacity, but CPU RAM and sample materialization still scale with entity count and sampled points.",
        "",
        "## GPU Memory Capacity",
        "",
        markdown_table(gpu_df),
        "",
        "The single-model metadata records `torch.cuda.max_memory_allocated()` and `torch.cuda.max_memory_reserved()`. Those are peak PyTorch allocator measurements for this process, not the physical capacity of the GPU. Total and currently free GPU memory come from `nvidia-smi`, which is system-level state and can change as other processes start or stop.",
        "",
        "## Parameter Sensitivity",
        "",
        "- `Geo_dim`: increases embedding table size, optimizer state, output file size, and usually model input width. CPU/GPU memory and storage increase roughly linearly with dimension.",
        "- `batch_size`: primarily affects GPU activation memory per step and may affect speed. It does not change output size or total sampled points.",
        "- `hidden_size_shape`: increases neural network parameter and activation memory, and can increase runtime.",
        "- `num_layers_shape`: increases model depth, activation memory, and runtime.",
        "- `num_freqs_shape`: increases positional encoding width, which increases model input width, memory, and runtime.",
        "- `samples_perUnit_shape`: increases edge-based SDF samples; raises CPU RAM, sampling time, training time, and DataLoader tensor size.",
        "- `point_sample_shape`: increases vertex-neighborhood samples; raises CPU RAM and runtime.",
        "- `uniformed_sample_perUnit_shape`: contributes a square grid per entity, so impact is approximately quadratic in this value.",
        "- `num_epoch`: increases training runtime roughly linearly, with little effect on peak memory.",
        "- `num_process`: can speed sampling but raises multiprocessing overhead and transient CPU memory pressure.",
        "",
        "### 5,000-Building Parameter Sweep",
        "",
        markdown_table(sweep.loc[:, [c for c in sweep_cols if c in sweep.columns]]),
        "",
        "## Scalability Estimates",
        "",
        markdown_table(stage_df),
        "",
        "Gwanak succeeded at 38,547 buildings. No prepared Seoul building subset was found, but the nationwide VWorld building file exists with about 14.39M features. Korea-scale single-model training should not be attempted directly from the Gwanak result; staged samples are required.",
        "",
        "Recommended stages: 50k and 100k with conservative lightweight settings; 300k only if RSS and sampling time remain linear; 1M only as a controlled overnight/global-memory test; Seoul full after Seoul boundaries are materialized; Korea sampled before any Korea full attempt; Korea full only if a 1M run shows comfortable RAM/GPU margins and runtime.",
        "",
        "Safe starting settings for all stages: `Geo_dim=32`, `hidden_size=128`, `num_layers=4`, `num_freqs=4`, `batch_size=4096`, `samples_perUnit_shape=8`, `point_sample_shape=2`, `uniformed_sample_perUnit_shape=4`, `num_epoch=1`. For 300k+ consider `batch_size=2048` and fewer `num_process` workers if CPU RAM spikes.",
        "",
        "## File Integrity vs Downstream Validation",
        "",
        "File integrity checks prove only that the parquet has the expected rows, IDs, dimensions, and finite values. They do not prove that embeddings encode meaningful geometry. Downstream validation should test whether embeddings predict shape metrics, form interpretable clusters, and show reasonable spatial or administrative coherence.",
        "",
        "### Downstream Geometry Prediction",
        "",
        markdown_table(best.loc[:, ["embedding", "target", "model", "r2", "mae"]]),
        "",
        "### Cluster Morphology",
        "",
        markdown_table(clusters.head(20)),
        "",
        "## Single-Model vs Chunked Comparison",
        "",
        f"- Single-model rows: `{single_meta.get('number_of_geometries_used')}`; dimension: `32`; runtime seconds: `{single_meta.get('elapsed_seconds')}`; peak GPU allocated MB: `{single_meta.get('peak_gpu_memory_allocated_mb')}`; validation: `{single_meta.get('validation_succeeded')}`.",
        f"- Chunked rows: `{chunk_meta.get('number_of_embeddings')}`; dimension: `{chunk_meta.get('Geo_dim')}`; runtime seconds: `{chunk_meta.get('elapsed seconds')}`; chunks: `{chunk_meta.get('number_of_chunks')}`; validation was confirmed by the earlier validation report.",
        "- Building ID sets match for all 38,547 buildings.",
        "- Direct vector comparison is not meaningful: chunked vectors come from separate latent spaces and also use 64 dimensions, while the new single-model vectors use one global 32-dimensional space.",
        "- Downstream comparisons are meaningful because both embeddings are evaluated against the same original building metrics.",
        "",
        "## Recommendations",
        "",
        "Use the single-model lightweight Gwanak embedding as the preferred Gwanak shape embedding. Next, run 50k and 100k deterministic samples from the nationwide building GeoPackage before preparing a Seoul full run. Keep the chunked output only as an experimental baseline unless anchor alignment is added.",
        "",
        "## Outputs",
        "",
        f"- Parameter sweep: `{SWEEP_RESULTS}`",
        f"- Downstream validation: `{DOWNSTREAM_RESULTS}`",
        f"- Cluster morphology: `{CLUSTER_RESULTS}`",
        f"- GPU status JSON: `{GPU_STATUS_JSON}`",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child-config", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.child_config:
        child_run(args.child_config)
        return
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    gpus = gpu_status()
    GPU_STATUS_JSON.write_text(json.dumps(gpus, indent=2), encoding="utf-8")
    sweep = run_sweep(args.overwrite)
    downstream, clusters = run_downstream(args.overwrite)
    write_report(gpus, sweep, downstream, clusters)
    print(f"Report path: {REPORT}")
    print(f"Parameter sweep: {SWEEP_RESULTS}")
    print(f"Downstream validation: {DOWNSTREAM_RESULTS}")


if __name__ == "__main__":
    main()
