#!/usr/bin/env python3
"""Summarize and report the Gwanak Geo2Vec epoch-saturation study."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import torch

from geo2vec_large_scale_common import EMBEDDING_DIR, METADATA_DIR, REPORT_DIR, TRAINING_RUN_DIR, write_json_atomic


STUDY_NAME = "gwanak_geo2vec_epoch_saturation_v1"
EXPECTED_BUILDINGS = 38_547
OUTPUT_ROOT = Path("/members/dhnyu/fusedata/geo2vec_large_scale")
REPORT_PATH = REPORT_DIR / "geo2vec_epoch_saturation_report.md"
PREVIOUS_STUDY = "gwanak_sample_density_saturation_v1"
PREVIOUS_R2 = {
    "sat_0800": 0.6291,
    "sat_1600": 0.6426,
    "sat_3200": 0.6543,
    "sat_5000": 0.6616,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-name", default=STUDY_NAME)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):,.{digits}f}"
    return str(value)


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int | None = None) -> list[str]:
    if df.empty:
        return ["No completed rows available."]
    use = df.loc[:, columns].copy()
    if max_rows is not None:
        use = use.head(max_rows)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in use.iterrows():
        lines.append("| " + " | ".join(fmt(row[col]) for col in columns) + " |")
    return lines


def path_is_under(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    root_resolved = root.resolve()
    return resolved == root_resolved or root_resolved in resolved.parents


def embedding_audit(embedding_dir: Path) -> dict[str, Any]:
    manifest = read_json(embedding_dir / "embedding_export_manifest.json")
    parts = sorted(embedding_dir.glob("embeddings_part_*.parquet"))
    rows = 0
    dims: set[int] = set()
    finite = True
    for part in parts:
        table = pq.read_table(part)
        cols = [c for c in table.column_names if c.startswith("geo2vec_")]
        dims.add(len(cols))
        df = table.select(cols).to_pandas()
        rows += table.num_rows
        finite = finite and bool(np.isfinite(df.to_numpy(dtype=np.float32)).all())
    return {
        "embedding_manifest_rows": int(manifest.get("row_count", -1)),
        "embedding_rows_scanned": int(rows),
        "embedding_dims": sorted(dims),
        "embedding_finite_scanned": finite,
        "embedding_manifest_finite": bool(manifest.get("finite_values")),
    }


def checkpoint_audit(checkpoint: Path) -> dict[str, Any]:
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    cfg = payload.get("model_config", {})
    return {
        "checkpoint": str(checkpoint),
        "n_poly": int(cfg.get("n_poly", -1)),
        "geo_dim": int(cfg.get("geo_dim", -1)),
        "global_step": int(payload.get("global_step", -1)),
        "epoch_state": int(payload.get("epoch", -1)),
    }


def collect_efficiency(manifest: dict[str, Any], study_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for d in manifest.get("densities", []):
        sample_manifest = read_json(Path(d["sample_manifest_json"]))
        cache_validation = read_json(Path(d["sample_manifest_json"]).parent / "sample_cache_validation.json")
        run_dir = Path(d["training_run_dir"])
        embedding_dir = Path(d["embedding_dir"])
        training_summary = read_json(run_dir / "training_summary.json")
        embedding_manifest = read_json(embedding_dir / "embedding_export_manifest.json")
        metrics_path = run_dir / "training_metrics.jsonl"
        metrics = pd.read_json(metrics_path, lines=True) if metrics_path.exists() and metrics_path.stat().st_size else pd.DataFrame()
        ckpt_audit = checkpoint_audit(Path(training_summary["final_checkpoint"]))
        emb_audit = embedding_audit(embedding_dir)
        total_samples = int(sample_manifest["total_samples"])
        building_count = int(sample_manifest["building_count"])
        rows.append(
            {
                "density_name": d["name"],
                "target_samples_per_building": int(d["target_samples_per_building"]),
                "actual_samples_per_building": total_samples / building_count,
                "samples_per_unit": int(d["samples_per_unit"]),
                "point_sample": int(d["point_sample"]),
                "uniform_grid": int(d["uniform_grid"]),
                "epochs": int(d["epochs"]),
                "total_samples": total_samples,
                "training_steps": int(training_summary["global_step"]),
                "sdf_generation_time": float(sample_manifest["elapsed_seconds"]),
                "cache_size_mb": float(sample_manifest["total_bytes"] / (1024**2)),
                "training_time": float(training_summary["elapsed_seconds"]),
                "training_samples_sec": float(metrics["training_samples_per_second"].mean()) if not metrics.empty else np.nan,
                "cpu_rss": training_summary.get("cpu_rss_mb"),
                "peak_rss": training_summary.get("peak_maxrss_mb"),
                "gpu_allocated_mb": training_summary.get("peak_gpu_allocated_mb"),
                "gpu_reserved_mb": training_summary.get("peak_gpu_reserved_mb"),
                "embedding_output_size_mb": float(embedding_manifest["output_size_mb"]),
                "embedding_rows": int(embedding_manifest["row_count"]),
                "embedding_dim": int(embedding_manifest["geo_dim"]),
                "sample_count_median": cache_validation.get("sample_count_median"),
                "status": d.get("status", "completed"),
            }
        )
        audit_rows.append(
            {
                "density_name": d["name"],
                "epochs": int(d["epochs"]),
                "training_run_under_study": path_is_under(run_dir, TRAINING_RUN_DIR / study_name),
                "embedding_under_study": path_is_under(embedding_dir, EMBEDDING_DIR / study_name),
                "sample_cache_under_study": path_is_under(Path(d["sample_manifest_json"]), OUTPUT_ROOT / "sample_caches" / study_name),
                "n_poly_is_expected": ckpt_audit["n_poly"] == EXPECTED_BUILDINGS,
                "geo_dim_is_32": ckpt_audit["geo_dim"] == 32,
                "embedding_rows_expected": emb_audit["embedding_rows_scanned"] == EXPECTED_BUILDINGS,
                "embedding_dim_32": emb_audit["embedding_dims"] == [32],
                "embedding_finite": emb_audit["embedding_finite_scanned"] is True,
                "final_checkpoint": ckpt_audit["checkpoint"],
                "global_step": ckpt_audit["global_step"],
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(audit_rows)


def load_validation(study_name: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    out_dir = REPORT_DIR / study_name
    results_path = out_dir / "density_xgboost_validation_results.parquet"
    summary_path = out_dir / "density_xgboost_validation_summary.parquet"
    if not results_path.exists() or not summary_path.exists():
        return pd.DataFrame(), pd.DataFrame()
    return pd.read_parquet(results_path), pd.read_parquet(summary_path)


def validation_rollups(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if results.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    by_combo = (
        results.groupby(["density_name", "epochs"], dropna=False)
        .agg(r2_mean=("r2", "mean"), rmse_mean=("rmse", "mean"), mae_mean=("mae", "mean"))
        .reset_index()
        .sort_values(["density_name", "epochs"])
    )
    by_scheme = (
        results.groupby(["resampling", "density_name", "epochs"], dropna=False)
        .agg(r2_mean=("r2", "mean"), rmse_mean=("rmse", "mean"), mae_mean=("mae", "mean"))
        .reset_index()
        .sort_values(["resampling", "density_name", "epochs"])
    )
    by_target = (
        results.groupby(["target", "resampling", "density_name", "epochs"], dropna=False)
        .agg(r2_mean=("r2", "mean"))
        .reset_index()
        .sort_values(["target", "resampling", "density_name", "epochs"])
    )
    return by_combo, by_scheme, by_target


def marginal_gains(by_combo: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for density, group in by_combo.groupby("density_name"):
        g = group.set_index("epochs").sort_index()
        for lo, hi in [(1, 5), (5, 10), (10, 20), (20, 50)]:
            if lo in g.index and hi in g.index:
                rows.append(
                    {
                        "density_name": density,
                        "epoch_interval": f"{lo}->{hi}",
                        "r2_gain": float(g.loc[hi, "r2_mean"] - g.loc[lo, "r2_mean"]),
                    }
                )
    return pd.DataFrame(rows)


def threshold_table(by_combo: pd.DataFrame, efficiency: pd.DataFrame) -> pd.DataFrame:
    if by_combo.empty:
        return pd.DataFrame()
    merged = by_combo.merge(efficiency[["density_name", "epochs", "training_time", "cache_size_mb"]], on=["density_name", "epochs"], how="left")
    best = float(merged["r2_mean"].max())
    rows = []
    for pct in [0.95, 0.99]:
        eligible = merged.loc[merged["r2_mean"] >= best * pct].copy()
        if eligible.empty:
            continue
        eligible["cost"] = eligible["training_time"].fillna(np.inf)
        row = eligible.sort_values(["cost", "cache_size_mb", "density_name", "epochs"]).iloc[0]
        rows.append(
            {
                "threshold": f"{int(pct * 100)}% best R2",
                "density_name": row["density_name"],
                "epochs": int(row["epochs"]),
                "r2_mean": float(row["r2_mean"]),
                "training_time": float(row["training_time"]) if pd.notna(row["training_time"]) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def write_outputs(study_name: str, efficiency: pd.DataFrame, audit: pd.DataFrame, results: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out_dir = REPORT_DIR / study_name
    out_dir.mkdir(parents=True, exist_ok=True)
    efficiency.to_parquet(out_dir / "epoch_efficiency_summary.parquet", index=False)
    efficiency.to_csv(out_dir / "epoch_efficiency_summary.csv", index=False)
    audit.to_parquet(out_dir / "epoch_safety_audit.parquet", index=False)
    by_combo, by_scheme, by_target = validation_rollups(results)
    by_combo.to_parquet(out_dir / "epoch_validation_by_density_epoch.parquet", index=False)
    by_scheme.to_parquet(out_dir / "epoch_validation_by_scheme.parquet", index=False)
    by_target.to_parquet(out_dir / "epoch_validation_by_target_scheme.parquet", index=False)
    gains = marginal_gains(by_combo)
    gains.to_parquet(out_dir / "epoch_marginal_r2_gains.parquet", index=False)
    thresholds = threshold_table(by_combo, efficiency)
    thresholds.to_parquet(out_dir / "epoch_r2_threshold_configs.parquet", index=False)
    write_json_atomic(METADATA_DIR / study_name / "epoch_efficiency_summary.json", {"rows": efficiency.to_dict(orient="records")})
    return {
        "by_combo": by_combo,
        "by_scheme": by_scheme,
        "by_target": by_target,
        "gains": gains,
        "thresholds": thresholds,
    }


def recommendation(by_combo: pd.DataFrame, thresholds: pd.DataFrame) -> tuple[str, str, str]:
    if by_combo.empty:
        return ("Incomplete", "Incomplete", "Validation is not available yet.")
    best = by_combo.sort_values("r2_mean", ascending=False).iloc[0]
    stress = thresholds.iloc[0] if not thresholds.empty else by_combo.sort_values(["epochs", "r2_mean"], ascending=[True, False]).iloc[0]
    production = best
    cost_effective = "Compare the marginal R2 gains table against SDF cache size and training time; the best current answer is based on completed combinations only."
    return (
        f"{stress['density_name']} at {int(stress['epochs'])} epochs",
        f"{production['density_name']} at {int(production['epochs'])} epochs",
        cost_effective,
    )


def make_report(
    manifest: dict[str, Any],
    efficiency: pd.DataFrame,
    audit: pd.DataFrame,
    results: pd.DataFrame,
    rollups: dict[str, pd.DataFrame],
) -> str:
    by_combo = rollups["by_combo"]
    by_scheme = rollups["by_scheme"]
    by_target = rollups["by_target"]
    gains = rollups["gains"]
    thresholds = rollups["thresholds"]
    stress_rec, prod_rec, cost_rec = recommendation(by_combo, thresholds)
    failed = pd.DataFrame(manifest.get("failed_combinations", []))
    best_r2 = None if by_combo.empty else float(by_combo["r2_mean"].max())
    saturated = []
    if not gains.empty:
        for density, group in gains.groupby("density_name"):
            last = group.loc[group["epoch_interval"] == "20->50", "r2_gain"]
            saturated.append(
                {
                    "density_name": density,
                    "saturated_by_50_epochs": bool(len(last) and abs(float(last.iloc[0])) < 0.005),
                    "last_marginal_r2_gain": float(last.iloc[0]) if len(last) else np.nan,
                }
            )
    saturation_df = pd.DataFrame(saturated)

    lines: list[str] = [
        "# Geo2Vec Epoch Saturation Report",
        "",
        "## Purpose",
        "",
        "This study tests whether downstream Gwanak building-shape embedding quality is currently limited more by SDF sample density or by Geo2Vec training epochs. It uses the exact recoverable Gwanak building set from `/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg`, layer `gwanak_buildings`, with 38,547 buildings.",
        "",
        "## Comparison To Previous One-Epoch Density Saturation",
        "",
        "Previous one-epoch mean R2 values were: `sat_0800=0.629`, `sat_1600=0.643`, `sat_3200=0.654`, and `sat_5000=0.662`. The new study repeats `sat_0800`, `sat_1600`, and `sat_3200` with 1, 5, 10, 20, and 50 epochs in a separate study directory.",
        "",
    ]
    if best_r2 is not None:
        lines.append(f"Best observed completed mean R2 in this epoch study: `{best_r2:.4f}`.")
        lines.append("")

    lines.extend(["## Experimental Configuration", ""])
    lines.extend(
        markdown_table(
            efficiency,
            [
                "density_name",
                "target_samples_per_building",
                "actual_samples_per_building",
                "samples_per_unit",
                "point_sample",
                "uniform_grid",
                "epochs",
                "total_samples",
                "training_steps",
            ],
        )
    )
    lines.extend(["", "## Efficiency", ""])
    lines.extend(
        markdown_table(
            efficiency,
            [
                "density_name",
                "epochs",
                "sdf_generation_time",
                "cache_size_mb",
                "training_time",
                "training_samples_sec",
                "cpu_rss",
                "peak_rss",
                "gpu_allocated_mb",
                "gpu_reserved_mb",
                "embedding_output_size_mb",
            ],
        )
    )
    lines.extend(["", "## Validation Summary", "", "Mean R2/RMSE/MAE by density and epoch:", ""])
    lines.extend(markdown_table(by_combo, ["density_name", "epochs", "r2_mean", "rmse_mean", "mae_mean"]))
    lines.extend(["", "Mean R2/RMSE/MAE by validation scheme:", ""])
    lines.extend(markdown_table(by_scheme, ["resampling", "density_name", "epochs", "r2_mean", "rmse_mean", "mae_mean"]))
    lines.extend(["", "R2 by target, density, epoch, and validation scheme:", ""])
    lines.extend(markdown_table(by_target, ["target", "resampling", "density_name", "epochs", "r2_mean"]))
    lines.extend(["", "## Epoch Saturation Analysis", "", "Mean R2 vs epoch for each density:", ""])
    lines.extend(markdown_table(by_combo, ["density_name", "epochs", "r2_mean"]))
    lines.extend(["", "Marginal R2 gains:", ""])
    lines.extend(markdown_table(gains, ["density_name", "epoch_interval", "r2_gain"]))
    lines.extend(["", "Saturation by 50 epochs:", ""])
    lines.extend(markdown_table(saturation_df, ["density_name", "saturated_by_50_epochs", "last_marginal_r2_gain"]))
    lines.extend(["", "## Density Vs Epoch Tradeoff", ""])
    lines.append("The completed epoch grid should be read against the previous one-epoch sample-density curve. Key reference points: `sat_0800` one epoch previously reached 0.629 mean R2, `sat_1600` reached 0.643, `sat_3200` reached 0.654, and `sat_5000` reached 0.662.")
    lines.append("")
    lines.extend(["Most efficient configurations reaching fractions of the best observed R2:", ""])
    lines.extend(markdown_table(thresholds, ["threshold", "density_name", "epochs", "r2_mean", "training_time"]))
    lines.extend(["", "## Recommendation", ""])
    lines.append(f"- Best engineering stress-test configuration: `{stress_rec}`.")
    lines.append(f"- Best quality-oriented production configuration among completed runs: `{prod_rec}`.")
    lines.append(f"- Cost-effectiveness: {cost_rec}")
    lines.extend(["", "## Validation And Safety Checks", ""])
    lines.extend(markdown_table(audit, ["density_name", "epochs", "n_poly_is_expected", "geo_dim_is_32", "embedding_rows_expected", "embedding_dim_32", "embedding_finite", "sample_cache_under_study", "training_run_under_study", "embedding_under_study"]))
    if not failed.empty:
        lines.extend(["", "Failed or incomplete combinations:", ""])
        lines.extend(markdown_table(failed, ["name", "epochs", "status", "error_type", "error"]))
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- This is Gwanak-only and may not capture national-scale geometry diversity.",
            "- `Geo_dim` is fixed at 32.",
            "- This is not a full hyperparameter-tuning study.",
            "- Shape-normalized SDF embeddings are expected to be less direct for `log_area` and `log_perimeter` than for shape ratios such as compactness, elongation, and bbox area ratio.",
            "",
            "## Output Paths",
            "",
            f"- Study manifest: `{METADATA_DIR / manifest['study_name'] / 'epoch_saturation_manifest.json'}`",
            f"- Efficiency summary: `{REPORT_DIR / manifest['study_name'] / 'epoch_efficiency_summary.parquet'}`",
            f"- Validation details: `{REPORT_DIR / manifest['study_name'] / 'density_xgboost_validation_results.parquet'}`",
            f"- Sample caches: `{OUTPUT_ROOT / 'sample_caches' / manifest['study_name']}`",
            f"- Training runs: `{OUTPUT_ROOT / 'training_runs' / manifest['study_name']}`",
            f"- Embeddings: `{OUTPUT_ROOT / 'embeddings' / manifest['study_name']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    manifest_path = METADATA_DIR / args.study_name / "epoch_saturation_manifest.json"
    manifest = read_json(manifest_path)
    efficiency, audit = collect_efficiency(manifest, args.study_name)
    results, _summary = load_validation(args.study_name)
    rollups = write_outputs(args.study_name, efficiency, audit, results)
    report = make_report(manifest, efficiency, audit, results, rollups)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(REPORT_PATH)


if __name__ == "__main__":
    main()
