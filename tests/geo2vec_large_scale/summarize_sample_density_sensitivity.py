#!/usr/bin/env python3
"""Summarize sample-density sensitivity outputs."""

from __future__ import annotations

import json
import argparse
from pathlib import Path

import pandas as pd

from geo2vec_large_scale_common import METADATA_DIR, REPORT_DIR, write_json_atomic


STUDY_NAME = "gwanak_sample_density_sensitivity_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-name", default=STUDY_NAME)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    study_name = args.study_name
    manifest_path = METADATA_DIR / study_name / "sample_density_sensitivity_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    rows = []
    for d in manifest["densities"]:
        sm = json.loads(Path(d["sample_manifest_json"]).read_text())
        val = json.loads((Path(d["sample_manifest_json"]).parent / "sample_cache_validation.json").read_text())
        tr = json.loads((Path(d["training_run_dir"]) / "training_summary.json").read_text())
        exp = json.loads((Path(d["embedding_dir"]) / "embedding_export_manifest.json").read_text())
        metrics = pd.read_json(Path(d["training_run_dir"]) / "training_metrics.jsonl", lines=True)
        rows.append(
            {
                "density_name": d["name"],
                "sample_config_version": d["sample_config_version"],
                "samples_per_unit": d["samples_per_unit"],
                "point_sample": d["point_sample"],
                "uniform_grid": d["uniform_grid"],
                "building_count": sm["building_count"],
                "total_samples": sm["total_samples"],
                "mean_samples_per_building": sm["total_samples"] / sm["building_count"],
                "median_samples_per_building": val["sample_count_median"],
                "min_samples_per_building": val["sample_count_min"],
                "max_samples_per_building": val["sample_count_max"],
                "train_rows": val["train_rows"],
                "validation_rows": val["validation_rows"],
                "validation_ratio_observed": val["validation_ratio_observed"],
                "sample_generation_seconds": sm["elapsed_seconds"],
                "sample_generation_samples_per_second": sm["samples_per_second"],
                "sample_cache_mb": sm["total_bytes"] / (1024**2),
                "training_elapsed_seconds": tr["elapsed_seconds"],
                "training_steps": tr["global_step"],
                "training_samples_seen": tr["samples_seen"],
                "mean_training_samples_per_second": float(metrics["training_samples_per_second"].mean()),
                "last_validation_l1": float(metrics["validation_l1"].iloc[-1]),
                "peak_gpu_allocated_mb": tr["peak_gpu_allocated_mb"],
                "peak_gpu_reserved_mb": tr["peak_gpu_reserved_mb"],
                "cpu_rss_mb": tr["cpu_rss_mb"],
                "peak_maxrss_mb": tr["peak_maxrss_mb"],
                "embedding_output_mb": exp["output_size_mb"],
                "embedding_rows": exp["row_count"],
                "embedding_finite_values": exp["finite_values"],
            }
        )
    summary = pd.DataFrame(rows)
    out_dir = REPORT_DIR / study_name
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "density_efficiency_summary.parquet"
    csv_path = out_dir / "density_efficiency_summary.csv"
    summary.to_parquet(summary_path, index=False)
    summary.to_csv(csv_path, index=False)
    write_json_atomic(METADATA_DIR / study_name / "density_efficiency_summary.json", {"rows": rows})
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
