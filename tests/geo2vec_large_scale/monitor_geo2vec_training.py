#!/usr/bin/env python3
"""Summarize Geo2Vec prototype training outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from geo2vec_large_scale_common import path_size_mb, write_json_atomic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--sample-manifest-json", type=Path)
    parser.add_argument("--embedding-manifest-json", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_json = args.run_dir / "monitor_status.json"
    out_md = args.run_dir / "monitor_status.md"
    if out_json.exists() and not args.overwrite:
        print(out_json.read_text())
        return
    metrics_path = args.run_dir / "training_metrics.jsonl"
    training_summary_path = args.run_dir / "training_summary.json"
    training_summary = json.loads(training_summary_path.read_text()) if training_summary_path.exists() else {}
    metrics = pd.read_json(metrics_path, lines=True) if metrics_path.exists() and metrics_path.stat().st_size else pd.DataFrame()
    checkpoints = sorted(args.run_dir.glob("checkpoint_step_*.pt"))
    status = {
        "run_dir": str(args.run_dir),
        "metrics_rows": int(len(metrics)),
        "checkpoint_count": int(len(checkpoints)),
        "latest_checkpoint": str(checkpoints[-1]) if checkpoints else None,
        "latest_checkpoint_size_mb": checkpoints[-1].stat().st_size / (1024**2) if checkpoints else None,
        "run_dir_size_mb": path_size_mb(args.run_dir),
        "mean_training_samples_per_second": float(metrics["training_samples_per_second"].mean()) if "training_samples_per_second" in metrics else None,
        "max_cpu_rss_mb": float(metrics["cpu_rss_mb"].max()) if "cpu_rss_mb" in metrics else None,
        "max_gpu_allocated_mb": float(metrics["gpu_allocated_mb"].max()) if "gpu_allocated_mb" in metrics and metrics["gpu_allocated_mb"].notna().any() else None,
        "max_gpu_reserved_mb": float(metrics["gpu_reserved_mb"].max()) if "gpu_reserved_mb" in metrics and metrics["gpu_reserved_mb"].notna().any() else None,
        "last_validation_l1": float(metrics["validation_l1"].dropna().iloc[-1]) if "validation_l1" in metrics and metrics["validation_l1"].notna().any() else None,
        "checkpoint_retention_keep": training_summary.get("checkpoint_retention_keep"),
        "training_summary_path": str(training_summary_path) if training_summary_path.exists() else None,
    }
    if args.sample_manifest_json and args.sample_manifest_json.exists():
        sample = json.loads(args.sample_manifest_json.read_text())
        status["sample_cache_total_samples"] = sample.get("total_samples")
        status["sample_cache_size_mb"] = sample.get("total_bytes", 0) / (1024**2)
        status["sample_generation_samples_per_second"] = sample.get("samples_per_second")
    if args.embedding_manifest_json and args.embedding_manifest_json.exists():
        emb = json.loads(args.embedding_manifest_json.read_text())
        status["embedding_row_count"] = emb.get("row_count")
        status["embedding_output_size_mb"] = emb.get("output_size_mb")
    write_json_atomic(out_json, status)
    lines = [
        "# Geo2Vec Prototype Monitor",
        "",
        f"- Run directory: `{args.run_dir}`",
        f"- Metrics rows: `{status['metrics_rows']}`",
        f"- Checkpoints: `{status['checkpoint_count']}`",
        f"- Latest checkpoint size MB: `{status['latest_checkpoint_size_mb']}`",
        f"- Mean training samples/sec: `{status['mean_training_samples_per_second']}`",
        f"- Max CPU RSS MB: `{status['max_cpu_rss_mb']}`",
        f"- Max GPU allocated MB: `{status['max_gpu_allocated_mb']}`",
        f"- Max GPU reserved MB: `{status['max_gpu_reserved_mb']}`",
        f"- Last validation L1: `{status['last_validation_l1']}`",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
