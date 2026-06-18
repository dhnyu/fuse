#!/usr/bin/env python3
"""Run independent regional replication of the validated Geo2Vec Model C setup."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import Polygon
from shapely.ops import unary_union


ROOT = Path.home() / "fuse"
WORKING_ROOT = Path.home() / "fusedatalarge" / "working_data"
OUTPUT_ROOT = Path.home() / "fusedata" / "embeddings" / "regional_replication_model_c"
REPORT_DIR = ROOT / "reports" / "experiments"
SIDO_BOUNDARY = Path.home() / "fusedatalarge" / "geodata" / "koreanadm" / "bnd_sido_00_2024_2Q.shp"
SIGUNGU_BOUNDARY = Path.home() / "fusedatalarge" / "geodata" / "koreanadm" / "bnd_sigungu_00_2024_2Q.shp"
TARGET_EPSG = 5186
THREADS = 48
REGIONS = [
    "changwon",
    "daejeon",
    "ganghwa",
    "jeju",
    "seongnam",
    "sejong",
    "daegu",
    "danyang",
    "gangneung",
    "incheon",
    "suwon",
]


@dataclass(frozen=True)
class RegionBoundary:
    source: str
    field: str
    match_type: str
    value: str
    name_ko: str


BOUNDARIES = {
    "changwon": RegionBoundary("sigungu", "SIGUNGU_NM", "prefix", "창원시", "창원시"),
    "daejeon": RegionBoundary("sido", "SIDO_NM", "exact", "대전광역시", "대전광역시"),
    "ganghwa": RegionBoundary("sigungu", "SIGUNGU_NM", "exact", "강화군", "강화군"),
    "jeju": RegionBoundary("sido", "SIDO_NM", "exact", "제주특별자치도", "제주특별자치도"),
    "seongnam": RegionBoundary("sigungu", "SIGUNGU_NM", "prefix", "성남시", "성남시"),
    "sejong": RegionBoundary("sido", "SIDO_NM", "exact", "세종특별자치시", "세종특별자치시"),
    "daegu": RegionBoundary("sido", "SIDO_NM", "exact", "대구광역시", "대구광역시"),
    "danyang": RegionBoundary("sigungu", "SIGUNGU_NM", "exact", "단양군", "단양군"),
    "gangneung": RegionBoundary("sigungu", "SIGUNGU_NM", "exact", "강릉시", "강릉시"),
    "incheon": RegionBoundary("sigungu", "SIGUNGU_CD", "prefix", "23", "인천광역시"),
    "suwon": RegionBoundary("sigungu", "SIGUNGU_NM", "prefix", "수원시", "수원시"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--regions", default=",".join(REGIONS))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--stop-after", choices=["grids", "prepare", "cache", "train", "evaluate", "report"])
    return parser.parse_args()


def kst_now() -> datetime:
    return datetime.now().astimezone()


def stamp() -> str:
    return kst_now().strftime("%Y%m%d_%H%M")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def env48() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "OMP_NUM_THREADS": str(THREADS),
            "MKL_NUM_THREADS": str(THREADS),
            "OPENBLAS_NUM_THREADS": str(THREADS),
            "VECLIB_MAXIMUM_THREADS": str(THREADS),
            "NUMEXPR_NUM_THREADS": str(THREADS),
            "FUSE_EVAL_THREADS": str(THREADS),
            "CUDA_VISIBLE_DEVICES": env.get("CUDA_VISIBLE_DEVICES", "0"),
            "TZ": "Asia/Seoul",
        }
    )
    return env


def run_logged(cmd: list[str], log_path: Path, cwd: Path = ROOT, overwrite: bool = False) -> float:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.exists() and overwrite:
        log_path.unlink()
    started = time.time()
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n\n")
        log.write(f"## started {kst_now().strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
        log.write(" ".join(cmd) + "\n\n")
        log.flush()
        proc = subprocess.run(cmd, cwd=cwd, env=env48(), stdout=log, stderr=subprocess.STDOUT, text=True)
        elapsed = time.time() - started
        log.write(f"\n## finished rc={proc.returncode} elapsed_seconds={elapsed:.3f}\n")
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with rc={proc.returncode}. See log: {log_path}")
    return elapsed


def layer_name(path: Path) -> str:
    return path.stem


def select_boundary(region: str) -> gpd.GeoDataFrame:
    cfg = BOUNDARIES[region]
    path = SIDO_BOUNDARY if cfg.source == "sido" else SIGUNGU_BOUNDARY
    gdf = gpd.read_file(path)
    values = gdf[cfg.field].astype(str)
    if cfg.match_type == "exact":
        sel = gdf.loc[values == cfg.value].copy()
    elif cfg.match_type == "prefix":
        sel = gdf.loc[values.str.startswith(cfg.value)].copy()
    else:
        raise ValueError(f"Unknown match type: {cfg.match_type}")
    if sel.empty:
        raise RuntimeError(f"No boundary matched region={region}")
    sel = sel.to_crs(epsg=TARGET_EPSG)
    geom = unary_union([g for g in sel.geometry if g is not None and not g.is_empty])
    return gpd.GeoDataFrame(
        {
            "region": [region],
            "region_name_ko": [cfg.name_ko],
            "source": [cfg.source],
            "field": [cfg.field],
            "match_type": [cfg.match_type],
            "match_value": [cfg.value],
            "source_feature_count": [int(len(sel))],
        },
        geometry=[geom],
        crs=f"EPSG:{TARGET_EPSG}",
    )


def make_grid(region: str, output_root: Path, overwrite: bool = False) -> dict[str, Any]:
    grid_dir = output_root / "grids" / region
    grid_dir.mkdir(parents=True, exist_ok=True)
    grid_path = grid_dir / f"{region}_scene_grid_500m_nonoverlap.gpkg"
    summary_path = grid_dir / "grid_summary.json"
    if grid_path.exists() and summary_path.exists() and not overwrite:
        return read_json(summary_path)

    boundary = select_boundary(region)
    geom = boundary.geometry.iloc[0]
    minx, miny, maxx, maxy = geom.bounds
    stride = 500.0
    cell = 500.0
    x0 = math.floor(minx / stride) * stride
    x1 = math.ceil(maxx / stride) * stride
    y0 = math.floor(miny / stride) * stride
    y1 = math.ceil(maxy / stride) * stride
    rows: list[dict[str, Any]] = []
    polys: list[Polygon] = []
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            polys.append(Polygon([(x, y), (x + cell, y), (x + cell, y + cell), (x, y + cell), (x, y)]))
            x += stride
        y += stride
    candidates = gpd.GeoDataFrame(geometry=polys, crs=f"EPSG:{TARGET_EPSG}")
    if candidates.empty:
        raise RuntimeError(f"Grid generation produced zero cells for {region}")
    centroids = candidates.geometry.centroid
    for idx, (row_idx, poly) in enumerate(candidates.geometry.items(), start=1):
        rows.append(
            {
                "scene_id": f"{region}_nonoverlap_500m_{idx:06d}",
                "region": region,
                "grid_type": "nonoverlap",
                "cell_size_m": cell,
                "stride_m": stride,
                "area_m2": float(poly.area),
                "centroid_x": float(centroids.loc[row_idx].x),
                "centroid_y": float(centroids.loc[row_idx].y),
                "intersects_boundary": False,
                "within_boundary": False,
                "coverage_ratio": 1.0,
            }
        )
    grid = gpd.GeoDataFrame(rows, geometry=list(candidates.geometry), crs=f"EPSG:{TARGET_EPSG}")
    if grid.empty:
        raise RuntimeError(f"Grid generation produced zero cells for {region}")
    if grid_path.exists():
        grid_path.unlink()
    grid.to_file(grid_path, layer=layer_name(grid_path), driver="GPKG")
    summary = {
        "region": region,
        "grid_path": str(grid_path),
        "grid_layer": layer_name(grid_path),
        "cell_size_m": 500,
        "stride_m": 500,
        "grid_type": "nonoverlap",
        "n_cells": int(len(grid)),
        "coverage_ratio_min": None,
        "coverage_ratio_mean": None,
        "coverage_ratio_max": None,
        "coverage_note": "Full boundary-bbox grid. Coverage ratios are not computed because Model C only uses 500 m scene bounding boxes for scene-relative normalization.",
        "boundary": boundary.drop(columns="geometry").iloc[0].to_dict(),
    }
    write_json_atomic(summary_path, summary)
    return summary


def phase_paths(output_root: Path, region: str) -> dict[str, Path]:
    prep_run = f"{region}_phase0"
    cache_run = f"{region}_model_c_cache"
    train_run = f"{region}_model_c_epoch05"
    return {
        "prep_run": Path(prep_run),
        "cache_run": Path(cache_run),
        "train_run": Path(train_run),
        "building_gpkg": WORKING_ROOT / region / "1_Building_vworld.gpkg",
        "prepared_gpkg": output_root / prep_run / "prepared" / "gwanak_buildings_geo2vec_valid.gpkg",
        "id_map": output_root / prep_run / "id_maps" / "gwanak_buildings_geo2vec_id_map.parquet",
        "targets": output_root / prep_run / "targets" / "gwanak_building_geometry_targets.parquet",
        "cache_summary": output_root / "sample_caches" / cache_run / "sample_cache_summary.json",
        "training_summary": output_root / "embeddings" / train_run / "training_embedding_summary.json",
        "metrics": output_root / "evaluations" / train_run / "spatial_block_cv_ranger_metrics.parquet",
        "eval_summary": output_root / "evaluations" / train_run / "spatial_block_cv_ranger_summary.json",
    }


def run_region(region: str, output_root: Path, overwrite: bool, skip_existing: bool) -> dict[str, Any]:
    paths = phase_paths(output_root, region)
    logs = output_root / "logs" / region
    region_started = time.time()
    grid = make_grid(region, output_root, overwrite=overwrite)

    if not paths["targets"].exists() or overwrite:
        print(f"[{region}] preparing buildings")
        prepare_elapsed = run_logged(
            [
                "Rscript",
                "scripts/embedding/prepare_gwanak_building_geo2vec_inputs.R",
                "--input",
                str(paths["building_gpkg"]),
                "--output-root",
                str(output_root),
                "--run-id",
                str(paths["prep_run"]),
                "--overwrite",
            ],
            logs / "prepare.log",
            overwrite=overwrite,
        )
    elif skip_existing:
        prepare_elapsed = 0.0
    else:
        prepare_elapsed = 0.0

    if not paths["cache_summary"].exists() or overwrite:
        print(f"[{region}] generating SDF caches with 48 workers")
        cache_elapsed = run_logged(
            [
                sys.executable,
                "scripts/embedding/sample_gwanak_geo2vec_sdf_cache.py",
                "--prepared-geometry",
                str(paths["prepared_gpkg"]),
                "--prepared-layer",
                "gwanak_buildings_geo2vec_valid",
                "--id-map",
                str(paths["id_map"]),
                "--nonoverlap-grid",
                grid["grid_path"],
                "--output-root",
                str(output_root),
                "--run-id",
                str(paths["cache_run"]),
                "--variant",
                "shape_scene_relative_location",
                "--samples-per-unit",
                "232",
                "--point-sample",
                "58",
                "--uniform-grid",
                "23",
                "--workers",
                str(THREADS),
                "--buildings-per-shard",
                "5000",
                "--overwrite",
            ],
            logs / "sample_cache.log",
            overwrite=overwrite,
        )
    elif skip_existing:
        cache_elapsed = 0.0
    else:
        cache_elapsed = 0.0

    if not paths["training_summary"].exists() or overwrite:
        print(f"[{region}] training Model C on cuda:0")
        train_elapsed = run_logged(
            [
                sys.executable,
                "scripts/embedding/train_gwanak_geo2vec_embeddings.py",
                "--output-root",
                str(output_root),
                "--run-id",
                str(paths["train_run"]),
                "--cache-run-id",
                str(paths["cache_run"]),
                "--variant",
                "shape_scene_relative_location",
                "--geo-dim",
                "32",
                "--epochs",
                "5",
                "--hidden-size",
                "128",
                "--num-layers",
                "4",
                "--num-freqs",
                "4",
                "--batch-size",
                "4096",
                "--lr",
                "0.001",
                "--shape-code-reg-weight",
                "1.0",
                "--location-code-reg-weight",
                "0.0",
                "--device",
                "cuda:0",
                "--overwrite",
            ],
            logs / "train.log",
            overwrite=overwrite,
        )
    elif skip_existing:
        train_elapsed = 0.0
    else:
        train_elapsed = 0.0

    if not paths["metrics"].exists() or overwrite:
        print(f"[{region}] evaluating Ranger spatial block CV with 48 threads")
        eval_elapsed = run_logged(
            [
                "Rscript",
                "scripts/embedding/evaluate_geo2vec_model_c_spatial_cv_ranger.R",
                "--output-root",
                str(output_root),
                "--run-id",
                str(paths["train_run"]),
                "--targets",
                str(paths["targets"]),
                "--threads",
                str(THREADS),
                "--overwrite",
            ],
            logs / "evaluate.log",
            overwrite=overwrite,
        )
    elif skip_existing:
        eval_elapsed = 0.0
    else:
        eval_elapsed = 0.0

    total_elapsed = time.time() - region_started
    run_summary = {
        "region": region,
        "run_namespace": "regional_replication_model_c",
        "prep_run": str(paths["prep_run"]),
        "cache_run": str(paths["cache_run"]),
        "train_run": str(paths["train_run"]),
        "grid_summary": grid,
        "paths": {k: str(v) for k, v in paths.items()},
        "step_elapsed_seconds": {
            "prepare": prepare_elapsed,
            "cache": cache_elapsed,
            "train": train_elapsed,
            "evaluate": eval_elapsed,
            "total_wall": total_elapsed,
        },
        "logs": str(logs),
    }
    write_json_atomic(output_root / "summaries" / f"{region}_run_summary.json", run_summary)
    return run_summary


def markdown_table(df: pd.DataFrame, float_digits: int = 4) -> str:
    if df.empty:
        return ""
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].map(lambda x: "" if pd.isna(x) else f"{x:.{float_digits}f}")
        elif pd.api.types.is_integer_dtype(out[col]):
            out[col] = out[col].map(lambda x: f"{int(x):,}" if pd.notna(x) else "")
    widths = [max(len(str(col)), *(len(str(x)) for x in out[col])) for col in out.columns]
    header = "| " + " | ".join(str(col).ljust(widths[i]) for i, col in enumerate(out.columns)) + " |"
    sep = "| " + " | ".join("-" * widths[i] for i in range(len(widths))) + " |"
    rows = ["| " + " | ".join(str(row[col]).rjust(widths[i]) for i, col in enumerate(out.columns)) + " |" for _, row in out.iterrows()]
    return "\n".join([header, sep, *rows])


def seconds_fmt(x: float | None) -> str:
    if x is None or pd.isna(x):
        return ""
    x = float(x)
    if x < 60:
        return f"{x:.1f}s"
    if x < 3600:
        return f"{x / 60:.1f}m"
    return f"{x / 3600:.2f}h"


def collect_report_data(output_root: Path, regions: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dataset_rows = []
    runtime_rows = []
    metric_rows = []
    leakage_rows = []
    for region in regions:
        paths = phase_paths(output_root, region)
        prep_audit = read_json(output_root / str(paths["prep_run"]) / "audit" / "gwanak_building_geo2vec_phase0_audit.json")
        cache = read_json(paths["cache_summary"])
        train = read_json(paths["training_summary"])
        eval_summary = read_json(paths["eval_summary"])
        metrics = pd.read_parquet(paths["metrics"])
        full_manifest = read_json(output_root / "embeddings" / str(paths["train_run"]) / "shape_scene_relative_location" / "full_embeddings" / "embedding_export_manifest.json")
        dataset_rows.append({"Region": region, "Buildings": int(prep_audit["valid_rows"])})
        cache_runtime = sum(read_json(Path(p))["elapsed_seconds"] for p in cache["manifests"])
        branch_train_runtime = 0.0
        for branch in ["shape", "location"]:
            manifest = train["variants"]["shape_scene_relative_location"]["branches"][branch]
            branch_train_runtime += read_json(Path(manifest["training_summary"]))["elapsed_seconds"]
        runtime_rows.append(
            {
                "Region": region,
                "Cache Runtime": cache_runtime,
                "Train Runtime": branch_train_runtime,
                "Evaluation Runtime": float(eval_summary["elapsed_seconds"]),
                "Total Runtime": cache_runtime + branch_train_runtime + float(eval_summary["elapsed_seconds"]),
            }
        )
        wide = metrics.pivot_table(index=[], columns="target", values="r2", aggfunc="first").reset_index(drop=True)
        metric_rows.append(
            {
                "Region": region,
                "Area": float(wide.get("area", pd.Series([float("nan")])).iloc[0]),
                "Perimeter": float(wide.get("perimeter", pd.Series([float("nan")])).iloc[0]),
                "Compactness": float(wide.get("compactness", pd.Series([float("nan")])).iloc[0]),
                "Aspect Ratio": float(wide.get("aspect_ratio", pd.Series([float("nan")])).iloc[0]),
                "BBox Ratio": float(wide.get("bbox_area_ratio", pd.Series([float("nan")])).iloc[0]),
            }
        )
        leakage_rows.append(
            {
                "Region": region,
                "centroid_x": float(wide.get("centroid_x", pd.Series([float("nan")])).iloc[0]),
                "centroid_y": float(wide.get("centroid_y", pd.Series([float("nan")])).iloc[0]),
            }
        )
        (output_root / "summaries" / f"{region}_artifacts.json").write_text(
            json.dumps(
                {
                    "cache_summary": str(paths["cache_summary"]),
                    "training_summary": str(paths["training_summary"]),
                    "full_embedding": full_manifest["embedding_path"],
                    "metrics": str(paths["metrics"]),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    return pd.DataFrame(dataset_rows), pd.DataFrame(runtime_rows), pd.DataFrame(metric_rows), pd.DataFrame(leakage_rows)


def write_report(output_root: Path, regions: list[str]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    dataset, runtime, metrics, leakage = collect_report_data(output_root, regions)
    consistency = metrics.drop(columns=["Region"]).agg(["mean", "std", "min", "max"]).T.reset_index()
    consistency.columns = ["Metric", "Mean", "Std Dev", "Minimum", "Maximum"]
    leakage_consistency = leakage.drop(columns=["Region"]).agg(["mean", "std", "min", "max"]).T.reset_index()
    leakage_consistency.columns = ["Metric", "Mean", "Std Dev", "Minimum", "Maximum"]
    runtime_fmt = runtime.copy()
    for col in ["Cache Runtime", "Train Runtime", "Evaluation Runtime", "Total Runtime"]:
        runtime_fmt[col] = runtime_fmt[col].map(seconds_fmt)

    metric_values = metrics.drop(columns=["Region"])
    primary_mean = metric_values[["Area", "Perimeter"]].mean(axis=1)
    secondary_mean = metric_values[["Compactness", "Aspect Ratio", "BBox Ratio"]].mean(axis=1)
    leakage_abs = leakage[["centroid_x", "centroid_y"]].abs().max(axis=1)
    metrics_interpret = pd.DataFrame(
        {
            "Region": metrics["Region"],
            "Primary Mean": primary_mean,
            "Secondary Mean": secondary_mean,
            "Max Abs Centroid R2": leakage_abs,
        }
    )
    outlier_lines = []
    for col in ["Area", "Perimeter", "Compactness", "Aspect Ratio", "BBox Ratio"]:
        mu = metrics[col].mean()
        sd = metrics[col].std()
        if sd > 0:
            low = metrics.loc[metrics[col] < mu - 2 * sd, ["Region", col]]
            high = metrics.loc[metrics[col] > mu + 2 * sd, ["Region", col]]
            for _, row in pd.concat([low, high]).iterrows():
                outlier_lines.append(f"- `{row['Region']}` is an outlier for `{col}` with R2={row[col]:.4f}.")
    if not outlier_lines:
        outlier_lines.append("- No region exceeds a two-standard-deviation outlier rule on the reported Ranger targets.")

    gwanak_reference = {
        "Area": 0.7169,
        "Perimeter": 0.8578,
        "Compactness": 0.8719,
        "Aspect Ratio": 0.9516,
        "BBox Ratio": 0.9531,
        "centroid_x": -0.0436,
        "centroid_y": 0.0338,
    }
    gwanak_vs = []
    for metric, value in gwanak_reference.items():
        source = leakage if metric.startswith("centroid") else metrics
        col = metric
        regional_mean = float(source[col].mean())
        regional_sd = float(source[col].std())
        z = (value - regional_mean) / regional_sd if regional_sd > 0 else float("nan")
        gwanak_vs.append({"Metric": metric, "Gwanak Reference": value, "Regional Mean": regional_mean, "Z vs Regions": z})
    gwanak_df = pd.DataFrame(gwanak_vs)

    primary_ok = float(primary_mean.mean()) >= 0.60
    primary_partial = float(primary_mean.mean()) >= 0.50
    secondary_ok = float(secondary_mean.mean()) >= 0.80
    leakage_ok = bool((leakage_abs < 0.15).all())
    leakage_partial = int((leakage_abs >= 0.15).sum()) <= 2 and float(leakage_abs.max()) < 0.25
    if primary_ok and secondary_ok and leakage_ok:
        recommendation = "Strongly replicated"
    elif secondary_ok and primary_partial and leakage_partial:
        recommendation = "Partially replicated"
    else:
        recommendation = "Not replicated"

    report_path = REPORT_DIR / f"{stamp()}_geo2vec_regional_replication_study.md"
    lines = [
        "# Geo2Vec Regional Replication Study",
        "",
        f"Generated: {kst_now().strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## 1. Experimental Design",
        "",
        "This study independently trained the validated Geo2Vec Model C configuration within each listed Korean region and evaluated the resulting embeddings within the same region using spatial block cross-validation. It does not perform geographic transfer or generalization.",
        "",
        "Configuration:",
        "",
        "- Variant: `shape_scene_relative_location`",
        "- Embedding order: `[scene-relative location, shape]`",
        "- Dimensions: 32D location + 32D shape = 64D full embedding",
        "- Training: epochs 5, `geo_dim=32`, `hidden_size=128`, `num_layers=4`, `num_freqs=4`, `batch_size=4096`",
        "- Optimizer: Adam, learning rate 0.001",
        "- Regularization: shape `code_reg_weight=1.0`, location `code_reg_weight=0.0`",
        "- SDF cache: `samples_per_unit=232`, `point_sample=58`, `uniform_grid=23`, `buildings_per_shard=5000`",
        "- Scene grids: experiment-local 500 m non-overlap grids under the output namespace; large-region grids use the full regional boundary bounding box because Model C only uses cell bounds for scene-relative normalization.",
        "- Resources: cache workers 48, evaluation threads 48, `data.table` threads 48, Ranger threads 48, BLAS/OpenMP thread env vars 48, training device `cuda:0`",
        "- Evaluation model: Ranger only, 100 trees",
        "",
        f"Output namespace: `{output_root}`",
        "",
        "## 2. Regional Dataset Summary",
        "",
        markdown_table(dataset),
        "",
        "## 3. Runtime Summary",
        "",
        markdown_table(runtime_fmt),
        "",
        "## 4. Spatial CV Ranger Results",
        "",
        markdown_table(metrics),
        "",
        "## 5. Leakage Diagnostics",
        "",
        markdown_table(leakage),
        "",
        "## 6. Cross-Region Consistency",
        "",
        markdown_table(consistency),
        "",
        "Centroid leakage consistency:",
        "",
        markdown_table(leakage_consistency),
        "",
        "Gwanak reference comparison uses the prior completed Gwanak Model C epoch-5 Ranger spatial-block results from `reports/experiments/20260616_0121_gwanak_geo2vec_phase4_model_c_epoch_saturation.md`; Gwanak was not retrained in this replication study.",
        "",
        markdown_table(gwanak_df),
        "",
        "## 7. Interpretation",
        "",
        f"- Mean primary R2 across regions is {primary_mean.mean():.4f}; mean secondary R2 across regions is {secondary_mean.mean():.4f}.",
        f"- Maximum absolute centroid diagnostic across all region-target pairs is {leakage_abs.max():.4f}.",
        *outlier_lines,
        "- Model C behaves consistently if high morphology/scale recovery is paired with low centroid recovery across regions. The tables above should be interpreted with that joint criterion rather than by one target alone.",
        "- Centroid leakage remains near zero everywhere under the threshold used here if all absolute centroid R2 values remain below 0.15.",
        "- Gwanak is considered unusually strong only if its reference scores sit far above the regional mean, approximately |z| >= 2; otherwise it is representative of the replicated regional behavior.",
        "- Multi-region validation supports using Model C as a canonical Geo2Vec object-geometry configuration only for within-region object embedding validation. It is still not geographic transfer validation.",
        "",
        "## 8. Recommendation",
        "",
        f"Classification: **{recommendation}**.",
        "",
        "Recommendation: keep Model C as the canonical Geo2Vec configuration for the next scene-aware object-embedding phase if the reported primary and secondary targets are stable and centroid leakage remains low. Geographic transfer/generalization should remain a separate future experiment.",
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> None:
    args = parse_args()
    selected = [r.strip() for r in args.regions.split(",") if r.strip()]
    bad = sorted(set(selected) - set(REGIONS))
    if bad:
        raise SystemExit(f"Unsupported or excluded region(s): {', '.join(bad)}")
    args.output_root.mkdir(parents=True, exist_ok=True)
    print(f"Output namespace: {args.output_root}")
    print(f"Regions: {', '.join(selected)}")
    summaries = []
    for region in selected:
        print(f"=== {region} ===")
        summaries.append(run_region(region, args.output_root, overwrite=args.overwrite, skip_existing=args.skip_existing))
        if args.stop_after in {"grids", "prepare", "cache", "train", "evaluate"}:
            break
    if args.stop_after == "report":
        report_path = write_report(args.output_root, selected)
        print(f"Report written: {report_path}")
    elif args.stop_after is None:
        report_path = write_report(args.output_root, selected)
        print(f"Report written: {report_path}")
    write_json_atomic(args.output_root / "summaries" / "regional_replication_latest_run.json", {"regions": selected, "summaries": summaries})


if __name__ == "__main__":
    main()
