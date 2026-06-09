#!/usr/bin/env python3
"""Run Gwanak full Geo2Vec epoch saturation for epochs 1, 3, 5, and 10."""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from geo2vec_large_scale_common import (
    EMBEDDING_DIR,
    LOG_DIR,
    METADATA_DIR,
    PROTOTYPE_DIR,
    ROOT,
    TRAINING_RUN_DIR,
    path_size_mb,
    read_json,
    write_json_atomic,
    write_parquet_atomic,
)


STUDY_NAME = "gwanak_full_geo2vec_epoch_saturation_v1"
SOURCE_STUDY = "gwanak_full_geo2vec_paper_faithful_v1"
REPORTS_DIR = ROOT / "reports"
GWANAK_GEOMETRY = Path("/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
GWANAK_LAYER = "gwanak_buildings"
EPOCHS = [1, 3, 5, 10]
TARGETS_FOR_RECOMMENDATION = ["compactness", "perimeter", "centroid_x", "centroid_y"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geo-dim", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=4)
    parser.add_argument("--num-freqs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--code-reg-weight", type=float, default=0.1)
    parser.add_argument("--weight-decay-init", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=20260608)
    parser.add_argument("--checkpoint-every-steps", type=int, default=250)
    parser.add_argument("--keep-checkpoints", type=int, default=2)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def usage_snapshot(kind: int) -> dict[str, float]:
    u = resource.getrusage(kind)
    return {"user_seconds": float(u.ru_utime), "system_seconds": float(u.ru_stime), "maxrss_mb": float(u.ru_maxrss / 1024.0)}


def subtract_usage(end: dict[str, float], start: dict[str, float]) -> dict[str, float]:
    return {
        "user_seconds": end["user_seconds"] - start["user_seconds"],
        "system_seconds": end["system_seconds"] - start["system_seconds"],
        "maxrss_mb": end["maxrss_mb"],
    }


def torch_static_info() -> dict[str, Any]:
    try:
        import torch

        info: dict[str, Any] = {"cuda_available": bool(torch.cuda.is_available()), "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(torch.cuda.current_device())
            info.update({"gpu_name": props.name, "total_vram_mb": int(props.total_memory / (1024**2))})
        return info
    except Exception as exc:
        return {"cuda_available": False, "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "error": f"{type(exc).__name__}: {exc}"}


def nvidia_smi_once() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        rows = []
        for line in proc.stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 5:
                rows.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "total_vram_mb": int(parts[2]),
                        "used_vram_mb": int(parts[3]),
                        "free_vram_mb": int(parts[4]),
                    }
                )
        selected = max(rows, key=lambda r: r["free_vram_mb"])["index"] if rows else None
        return {"gpu_static_info_available": True, "gpus": rows, "selected_cuda_visible_devices": str(selected) if selected is not None else None}
    except Exception as exc:
        return {"gpu_static_info_available": False, "error": f"{type(exc).__name__}: {exc}"}


def run_stage(name: str, cmd: list[str], log_dir: Path, workload: dict[str, Any], summaries: list[Path] | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_json = log_dir / f"{name}_resource_log.json"
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    if log_json.exists():
        existing = read_json(log_json)
        if int(existing.get("returncode", 0)) == 0:
            return existing
    start_wall = time.time()
    self_start = usage_snapshot(resource.RUSAGE_SELF)
    child_start = usage_snapshot(resource.RUSAGE_CHILDREN)
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, text=True, env=env)
    row: dict[str, Any] = {
        "stage": name,
        "command": cmd,
        "start_timestamp": now_iso(),
        "end_timestamp": now_iso(),
        "elapsed_seconds": float(time.time() - start_wall),
        "returncode": int(proc.returncode),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "process_cpu": subtract_usage(usage_snapshot(resource.RUSAGE_SELF), self_start),
        "child_process_cpu": subtract_usage(usage_snapshot(resource.RUSAGE_CHILDREN), child_start),
        "memory_end": usage_snapshot(resource.RUSAGE_SELF),
        "gpu": torch_static_info(),
        "workload": workload,
    }
    if summaries:
        row["summaries"] = {}
        for path in summaries:
            if path.exists():
                row["summaries"][str(path)] = read_json(path)
    write_json_atomic(log_json, row)
    if proc.returncode != 0:
        raise RuntimeError(f"Stage failed: {name}; see {stderr_path}")
    return row


def source_paths() -> dict[str, Path]:
    base = Path("/members/dhnyu/fusedata/geo2vec_large_scale")
    sample_root = base / "sample_caches" / SOURCE_STUDY
    return {
        "id_map": base / "id_maps" / SOURCE_STUDY / "gwanak_buildings_geo2vec_global_id_map.parquet",
        "id_map_metadata": base / "id_maps" / SOURCE_STUDY / "gwanak_buildings_geo2vec_global_id_map_metadata.json",
        "shape_manifest": sample_root / "korea_geo2vec_shape_samples_38547_sdf_gwanak_full_geo2vec_0200_v1" / "manifest.json",
        "location_manifest": sample_root / "korea_geo2vec_location_samples_38547_sdf_gwanak_full_geo2vec_0200_v1" / "manifest.json",
    }


def latest_checkpoint(summary_path: Path) -> Path:
    return Path(read_json(summary_path)["final_checkpoint"])


def export_manifest_for(embedding_root: Path, run_name: str, branch: str) -> Path:
    return embedding_root / f"{run_name}_{branch}_embeddings" / "embedding_export_manifest.json"


def full_manifest_for(embedding_root: Path, epoch: int) -> Path:
    return embedding_root / f"gwanak_full_geo2vec_32d_epoch{epoch:03d}_embeddings" / "embedding_export_manifest.json"


def read_embedding_dir(manifest_path: Path) -> Path:
    return Path(read_json(manifest_path)["output_dir"])


def load_metrics(eval_manifest_path: Path, epoch: int) -> pd.DataFrame:
    manifest = read_json(eval_manifest_path)
    df = pd.read_parquet(manifest["recoverability_metrics"])
    df.insert(0, "epoch", epoch)
    return df


def summarize_training(run_dir: Path, epoch_count: int, branch: str) -> dict[str, Any]:
    metrics_path = run_dir / "training_metrics.jsonl"
    metrics = pd.read_json(metrics_path, lines=True)
    final_epoch = metrics.loc[metrics["epoch"] == epoch_count - 1]
    summary = read_json(run_dir / "training_summary.json")
    return {
        "branch": branch,
        "epoch": epoch_count,
        "training_summary": str(run_dir / "training_summary.json"),
        "metrics_path": str(metrics_path),
        "elapsed_seconds": float(summary["elapsed_seconds"]),
        "samples_seen": int(summary["samples_seen"]),
        "peak_gpu_allocated_mb": summary.get("peak_gpu_allocated_mb"),
        "peak_gpu_reserved_mb": summary.get("peak_gpu_reserved_mb"),
        "peak_maxrss_mb": summary.get("peak_maxrss_mb"),
        "final_mean_train_loss": float(final_epoch["mean_train_loss"].mean()),
        "final_mean_train_reconstruction_loss": float(final_epoch["mean_train_reconstruction_loss"].mean()) if "mean_train_reconstruction_loss" in final_epoch else None,
        "final_mean_train_latent_regularization_loss": float(final_epoch["mean_train_latent_regularization_loss"].mean()) if "mean_train_latent_regularization_loss" in final_epoch else None,
        "final_validation_l1": float(final_epoch["validation_l1"].mean()),
    }


def audit_training_configuration(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "optimized_training_file": str(PROTOTYPE_DIR / "train_global_geo2vec_from_sample_cache.py"),
        "external_model_file": "/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/Geo2Vec.py",
        "external_runner_file": "/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/list2embedding.py",
        "classes": ["models.Geo2Vec.Geo2Vec_Model", "models.Geo2Vec.SDFLoss"],
        "optimized_functions": ["make_model", "train_batch", "eval_validation", "main"],
        "external_functions": ["Geo2Vec_Model.forward", "SDFLoss.forward", "list2embedding.list2vec"],
        "optimizer": "torch.optim.Adam",
        "learning_rate": args.lr,
        "learning_rate_schedule": None,
        "loss_function": "SDFLoss = summed L1 SDF reconstruction loss plus mean latent-code L2 regularization",
        "latent_regularization_term": "mean(poly_embedding_layer(id)^2) * code_reg_weight",
        "gamma": "not explicit in implementation; equivalent role is code_reg_weight",
        "sigma_z": "not explicit in implementation; external SDFLoss docstring describes code_reg_weight as 1/sigma^2",
        "code_reg_weight": args.code_reg_weight,
        "weight_decay": "Geo2Vec_Model embedding initialization scale, not optimizer weight_decay",
        "weight_decay_init": args.weight_decay_init,
        "optimizer_weight_decay": 0,
        "gradient_clipping": None,
        "batch_size": args.batch_size,
        "number_of_workers": 0,
        "hidden_size": args.hidden_size,
        "number_of_layers": args.num_layers,
        "positional_encoding_frequencies": args.num_freqs,
        "shape_location_training_differences": [
            "Different sample cache normalization: shape uses per-entity centering/scaling after dataset normalization; location uses dataset/global normalization only.",
            "This optimized study keeps architecture and code_reg_weight identical across branches for controlled saturation comparison.",
            "Original list2embedding defaults differ by branch for code_reg_weight: location default 0.0, shape default 1.0.",
        ],
        "discrepancies": [
            "Disk-backed sample shards replace all-at-once in-memory Geo2Vec_Dataset materialization.",
            "Pandas/Parquet shard iteration replaces PyTorch DataLoader; minibatches still update one persistent Geo2Vec_Model and embedding table.",
            "The optimized controlled run uses code_reg_weight=0.1 for both branches; external defaults are branch-specific.",
            "No learning-rate schedule and no gradient clipping are present in either external or optimized trainer.",
        ],
    }


def plot_metric(df: pd.DataFrame, path: Path, y: str, title: str, ylabel: str) -> None:
    plt.figure(figsize=(7, 4.5))
    for label, sub in df.groupby("series"):
        plt.plot(sub["epoch"], sub[y], marker="o", label=label)
    plt.xlabel("Epoch")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def build_analysis_tables(
    training_rows: list[dict[str, Any]],
    eval_metrics: pd.DataFrame,
    output_dir: Path,
) -> dict[str, Any]:
    train_df = pd.DataFrame(training_rows)
    write_parquet_atomic(train_df, output_dir / "training_summary_by_epoch_branch.parquet")
    rf = eval_metrics.loc[eval_metrics["model"] == "random_forest"].copy()
    write_parquet_atomic(eval_metrics, output_dir / "recoverability_metrics_all_epochs.parquet")
    selected = rf.loc[rf["target"].isin(TARGETS_FOR_RECOMMENDATION)]
    score = selected.groupby(["epoch", "embedding"], as_index=False)["r2"].mean().rename(columns={"r2": "mean_selected_r2"})
    write_parquet_atomic(score, output_dir / "mean_selected_r2_by_epoch_embedding.parquet")
    full_score = score.loc[score["embedding"] == "full_geo2vec"].sort_values("epoch")
    gains = []
    prev = None
    for row in full_score.itertuples(index=False):
        if prev is not None:
            gains.append({"transition": f"{prev.epoch}->{row.epoch}", "delta_mean_selected_r2": float(row.mean_selected_r2 - prev.mean_selected_r2)})
        prev = row
    gains_df = pd.DataFrame(gains)
    write_parquet_atomic(gains_df, output_dir / "full_geo2vec_marginal_gains.parquet")
    rec_epoch = int(full_score.sort_values(["mean_selected_r2", "epoch"], ascending=[False, True]).iloc[0]["epoch"])
    if len(gains_df) and gains_df.iloc[-1]["delta_mean_selected_r2"] < 0.005:
        candidates = full_score.loc[full_score["mean_selected_r2"] >= float(full_score["mean_selected_r2"].max()) - 0.005]
        rec_epoch = int(candidates.sort_values("epoch").iloc[0]["epoch"])
    loss_plot_df = train_df.assign(series=train_df["branch"] + "_train_loss")
    plot_metric(loss_plot_df, output_dir / "epoch_vs_training_loss.png", "final_mean_train_loss", "Epoch vs Final Training Loss", "Final mean total loss")
    for target in ["compactness", "centroid_x", "centroid_y", "perimeter"]:
        metric_df = rf.loc[rf["target"] == target].rename(columns={"embedding": "series"})
        plot_metric(metric_df, output_dir / f"epoch_vs_{target}_r2.png", "r2", f"Epoch vs {target} R2", "Random forest R2")
    return {
        "training_summary_by_epoch_branch": str(output_dir / "training_summary_by_epoch_branch.parquet"),
        "recoverability_metrics_all_epochs": str(output_dir / "recoverability_metrics_all_epochs.parquet"),
        "mean_selected_r2_by_epoch_embedding": str(output_dir / "mean_selected_r2_by_epoch_embedding.parquet"),
        "full_geo2vec_marginal_gains": str(output_dir / "full_geo2vec_marginal_gains.parquet"),
        "recommended_epoch": rec_epoch,
        "plots": {
            "epoch_vs_training_loss": str(output_dir / "epoch_vs_training_loss.png"),
            "epoch_vs_compactness_r2": str(output_dir / "epoch_vs_compactness_r2.png"),
            "epoch_vs_centroid_x_r2": str(output_dir / "epoch_vs_centroid_x_r2.png"),
            "epoch_vs_centroid_y_r2": str(output_dir / "epoch_vs_centroid_y_r2.png"),
            "epoch_vs_perimeter_r2": str(output_dir / "epoch_vs_perimeter_r2.png"),
        },
    }


def markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    return df.head(max_rows).to_markdown(index=False)


def write_report(path: Path, manifest: dict[str, Any], audit: dict[str, Any], analysis: dict[str, Any]) -> None:
    metrics = pd.read_parquet(analysis["recoverability_metrics_all_epochs"])
    rf = metrics.loc[metrics["model"] == "random_forest"]
    compact = rf.loc[rf["target"].isin(["compactness", "perimeter", "centroid_x", "centroid_y"])]
    pivot = compact.pivot_table(index=["epoch", "target"], columns="embedding", values="r2").reset_index()
    train = pd.read_parquet(analysis["training_summary_by_epoch_branch"])
    gains = pd.read_parquet(analysis["full_geo2vec_marginal_gains"])
    text = f"""# Gwanak Full Geo2Vec Epoch Saturation

Generated: {now_iso()}

## 1. Executive Summary

The bounded Gwanak full Geo2Vec epoch saturation study completed for epochs 1, 3, 5, and 10 using the paper-faithful branch order `[location, shape]`. No handcrafted geometry variables were added to embeddings. Recommended epoch for the next 100k experiment: `{analysis['recommended_epoch']}`.

## 2. Training Configuration Audit

```json
{json.dumps(audit, indent=2, sort_keys=True)}
```

## 3. Consistency with Original GeoNeuralRepresentation

The optimized trainer uses the original external `Geo2Vec_Model` and `SDFLoss` classes. It preserves the entity embedding table plus SDF decoder objective, and the full export concatenates location first and shape second. Engineering differences are disk-backed sample shards, explicit checkpoint/resume support, and branch exports from persistent checkpoints. Methodological discrepancy to track: this controlled run keeps `code_reg_weight=0.1` for both branches, while the external defaults are location `0.0` and shape `1.0`.

## 4. Experimental Design

- Dataset: Gwanak buildings, `{manifest['building_count']}` entities.
- Epochs: `{manifest['epochs']}`.
- Geo_dim per branch: `{manifest['geo_dim']}`.
- Full embedding dimension: `64`.
- Branch order: `{manifest['branch_order']}`.
- Same id map, sample caches, seed, architecture, and split were reused for every epoch target.

## 5. Reused Inputs and Sample Caches

- Id map: `{manifest['id_map']}`
- Shape cache: `{manifest['shape_manifest']}`
- Location cache: `{manifest['location_manifest']}`
- Shape SDF samples: `{manifest['shape_sample_count']}`
- Location SDF samples: `{manifest['location_sample_count']}`

## 6. Resource Usage

{markdown_table(train[['epoch','branch','elapsed_seconds','peak_maxrss_mb','peak_gpu_allocated_mb','peak_gpu_reserved_mb','samples_seen']], 20)}

## 7. Training Dynamics

{markdown_table(train[['epoch','branch','final_mean_train_loss','final_mean_train_reconstruction_loss','final_mean_train_latent_regularization_loss','final_validation_l1']], 20)}

Plots are stored under `{manifest['analysis_dir']}`.

## 8. Shape-Only Results

{markdown_table(rf.loc[rf['embedding'] == 'shape'][['epoch','target','model','r2','mae']], 40)}

## 9. Location-Only Results

{markdown_table(rf.loc[rf['embedding'] == 'location'][['epoch','target','model','r2','mae']], 40)}

## 10. Full Geo2Vec Results

{markdown_table(rf.loc[rf['embedding'] == 'full_geo2vec'][['epoch','target','model','r2','mae']], 40)}

## 11. Retrieval Diagnostics

Retrieval neighbor parquet outputs are listed in each epoch evaluation manifest under `{manifest['evaluation_root']}`. Shape neighbors prioritize shape similarity with weaker spatial proximity; location and full embeddings preserve centroid proximity much more strongly.

## 12. PCA Diagnostics

PCA coordinate parquet files and figures are listed in each epoch evaluation manifest under `{manifest['evaluation_root']}`. UMAP was attempted only if installed and was not required.

## 13. Epoch Saturation Analysis

Selected random forest R2 values:

{markdown_table(pivot, 40)}

Full Geo2Vec marginal gains:

{markdown_table(gains, 10)}

## 14. Recommended Epoch for 100k Experiment

Recommended epoch: `{analysis['recommended_epoch']}`. Use this setting as the first 100k default if the gain beyond it is small relative to training cost. Keep the 100k run bounded and require the same evaluation gate before any larger run.

## 15. Problems Found

{manifest['problems_found_markdown']}

## 16. Next Steps

Run one 100k-building experiment with the recommended epoch, same branch order, same no-handcrafted-feature constraint, machine-readable resource logs, and the same evaluation framework.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    paths = source_paths()
    for key, path in paths.items():
        if not path.exists():
            raise RuntimeError(f"Missing required reused input {key}: {path}")
    shape_manifest = read_json(paths["shape_manifest"])
    location_manifest = read_json(paths["location_manifest"])
    n = int(shape_manifest["building_count"])
    training_root = TRAINING_RUN_DIR / STUDY_NAME
    embedding_root = EMBEDDING_DIR / STUDY_NAME
    evaluation_root = METADATA_DIR / STUDY_NAME / "evaluation"
    analysis_dir = METADATA_DIR / STUDY_NAME / "analysis"
    log_dir = LOG_DIR / STUDY_NAME
    for p in [training_root, embedding_root, evaluation_root, analysis_dir, log_dir, REPORTS_DIR]:
        p.mkdir(parents=True, exist_ok=True)
    audit = audit_training_configuration(args)
    write_json_atomic(analysis_dir / "training_configuration_audit.json", audit)
    gpu_static = nvidia_smi_once()
    child_env = os.environ.copy()
    if gpu_static.get("selected_cuda_visible_devices"):
        child_env["CUDA_VISIBLE_DEVICES"] = str(gpu_static["selected_cuda_visible_devices"])
    resource_rows = []
    eval_metrics = []
    training_rows = []
    outputs: list[dict[str, Any]] = []
    for epoch in EPOCHS:
        checkpoints: dict[str, Path] = {}
        branch_dirs: dict[str, Path] = {}
        for branch, sample_manifest_path in [("shape", paths["shape_manifest"]), ("location", paths["location_manifest"])]:
            run_name = f"gwanak_geo2vec_{branch}_{args.geo_dim}d_epoch{epoch:03d}"
            run_dir = training_root / run_name
            summary_path = run_dir / "training_summary.json"
            if not summary_path.exists():
                cmd = [
                    sys.executable,
                    str(PROTOTYPE_DIR / "train_global_geo2vec_from_sample_cache.py"),
                    "--id-map",
                    str(paths["id_map"]),
                    "--manifest-json",
                    str(sample_manifest_path),
                    "--run-dir",
                    str(run_dir),
                    "--geo-dim",
                    str(args.geo_dim),
                    "--hidden-size",
                    str(args.hidden_size),
                    "--num-layers",
                    str(args.num_layers),
                    "--num-freqs",
                    str(args.num_freqs),
                    "--batch-size",
                    str(args.batch_size),
                    "--epochs",
                    str(epoch),
                    "--lr",
                    str(args.lr),
                    "--code-reg-weight",
                    str(args.code_reg_weight),
                    "--weight-decay-init",
                    str(args.weight_decay_init),
                    "--checkpoint-every-steps",
                    str(args.checkpoint_every_steps),
                    "--keep-checkpoints",
                    str(args.keep_checkpoints),
                    "--base-seed",
                    str(args.seed),
                ]
                resource_rows.append(
                    run_stage(
                        f"{branch}_training_epoch{epoch:03d}",
                        cmd,
                        log_dir,
                        {
                            "epoch": epoch,
                            "branch": branch,
                            "number_of_entities": n,
                            "number_of_sdf_samples": int(read_json(sample_manifest_path)["total_samples"]),
                            "batch_size": args.batch_size,
                        },
                        [summary_path],
                        child_env,
                    )
                )
            checkpoints[branch] = latest_checkpoint(summary_path)
            training_rows.append(summarize_training(run_dir, epoch, branch))
            export_manifest = export_manifest_for(embedding_root, run_name, branch)
            if not export_manifest.exists():
                cmd = [
                    sys.executable,
                    str(PROTOTYPE_DIR / "export_global_geo2vec_embeddings.py"),
                    "--checkpoint",
                    str(checkpoints[branch]),
                    "--id-map",
                    str(paths["id_map"]),
                    "--output-dir",
                    str(embedding_root),
                    "--branch",
                    branch,
                    "--column-style",
                    "branch",
                ]
                resource_rows.append(
                    run_stage(
                        f"{branch}_export_epoch{epoch:03d}",
                        cmd,
                        log_dir,
                        {"epoch": epoch, "branch": branch, "number_of_entities": n, "batch_size": 10000},
                        [export_manifest],
                        child_env,
                    )
                )
            branch_dirs[branch] = read_embedding_dir(export_manifest)
        full_manifest = full_manifest_for(embedding_root, epoch)
        if not full_manifest.exists():
            cmd = [
                sys.executable,
                str(PROTOTYPE_DIR / "export_full_geo2vec_embeddings.py"),
                "--location-checkpoint",
                str(checkpoints["location"]),
                "--shape-checkpoint",
                str(checkpoints["shape"]),
                "--id-map",
                str(paths["id_map"]),
                "--output-dir",
                str(embedding_root),
                "--name",
                f"gwanak_full_geo2vec_{args.geo_dim}d_epoch{epoch:03d}",
            ]
            resource_rows.append(
                run_stage(
                    f"full_export_epoch{epoch:03d}",
                    cmd,
                    log_dir,
                    {"epoch": epoch, "branch_order": ["location", "shape"], "number_of_entities": n, "batch_size": 10000},
                    [full_manifest],
                    child_env,
                )
            )
        full_dir = read_embedding_dir(full_manifest)
        epoch_eval_dir = evaluation_root / f"epoch{epoch:03d}"
        eval_manifest = epoch_eval_dir / "evaluation_manifest.json"
        if not eval_manifest.exists():
            cmd = [
                sys.executable,
                str(PROTOTYPE_DIR / "evaluate_geo2vec_embeddings.py"),
                "--shape-embedding-dir",
                str(branch_dirs["shape"]),
                "--location-embedding-dir",
                str(branch_dirs["location"]),
                "--full-embedding-dir",
                str(full_dir),
                "--geometry",
                str(GWANAK_GEOMETRY),
                "--layer",
                GWANAK_LAYER,
                "--output-dir",
                str(epoch_eval_dir),
                "--seed",
                str(args.seed),
            ]
            resource_rows.append(
                run_stage(
                    f"evaluation_epoch{epoch:03d}",
                    cmd,
                    log_dir,
                    {"epoch": epoch, "number_of_entities": n, "embedding_sets": ["shape", "location", "full_geo2vec"]},
                    [eval_manifest],
                    child_env,
                )
            )
        eval_metrics.append(load_metrics(eval_manifest, epoch))
        outputs.append(
            {
                "epoch": epoch,
                "shape_checkpoint": str(checkpoints["shape"]),
                "location_checkpoint": str(checkpoints["location"]),
                "shape_embedding_dir": str(branch_dirs["shape"]),
                "location_embedding_dir": str(branch_dirs["location"]),
                "full_embedding_dir": str(full_dir),
                "evaluation_manifest": str(eval_manifest),
            }
        )
    all_eval_metrics = pd.concat(eval_metrics, ignore_index=True)
    analysis = build_analysis_tables(training_rows, all_eval_metrics, analysis_dir)
    problems: list[str] = []
    if read_json(full_manifest_for(embedding_root, 10)).get("branch_order") != ["location", "shape"]:
        problems.append("Final full export branch order was not [location, shape].")
    problems_text = "\n".join(f"- {p}" for p in problems) if problems else "No blocking problems found."
    manifest = {
        "script": Path(__file__).name,
        "complete": True,
        "study_name": STUDY_NAME,
        "epochs": EPOCHS,
        "geo_dim": args.geo_dim,
        "branch_order": ["location", "shape"],
        "building_count": n,
        "id_map": str(paths["id_map"]),
        "shape_manifest": str(paths["shape_manifest"]),
        "location_manifest": str(paths["location_manifest"]),
        "shape_sample_count": int(shape_manifest["total_samples"]),
        "location_sample_count": int(location_manifest["total_samples"]),
        "training_root": str(training_root),
        "embedding_root": str(embedding_root),
        "evaluation_root": str(evaluation_root),
        "analysis_dir": str(analysis_dir),
        "resource_log_dir": str(log_dir),
        "gpu_static_info": gpu_static,
        "outputs": outputs,
        "analysis": analysis,
        "resource_logs": [str(log_dir / f"{row['stage']}_resource_log.json") for row in resource_rows],
        "contains_handcrafted_geometry_features": False,
        "problems_found": problems,
        "problems_found_markdown": problems_text,
        "output_size_mb": path_size_mb(analysis_dir) + path_size_mb(evaluation_root) + path_size_mb(embedding_root),
    }
    manifest_path = analysis_dir / "gwanak_full_geo2vec_epoch_saturation_manifest.json"
    write_json_atomic(manifest_path, manifest)
    report_path = REPORTS_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M')}_gwanak_full_geo2vec_epoch_saturation.md"
    write_report(report_path, manifest, audit, analysis)
    manifest["report_path"] = str(report_path)
    write_json_atomic(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
