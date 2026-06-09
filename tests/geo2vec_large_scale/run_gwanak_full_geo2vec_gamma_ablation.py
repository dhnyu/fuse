#!/usr/bin/env python3
"""Run bounded Gwanak full Geo2Vec code_reg_weight/gamma ablation."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from geo2vec_large_scale_common import EMBEDDING_DIR, LOG_DIR, METADATA_DIR, PROTOTYPE_DIR, ROOT, TRAINING_RUN_DIR, path_size_mb, read_json, write_json_atomic, write_parquet_atomic


STUDY_NAME = "gwanak_full_geo2vec_gamma_ablation_v1"
SOURCE_STUDY = "gwanak_full_geo2vec_paper_faithful_v1"
EPOCH_STUDY = "gwanak_full_geo2vec_epoch_saturation_v1"
BASE = Path("/members/dhnyu/fusedata/geo2vec_large_scale")
REPORTS_DIR = ROOT / "reports"
GWANAK_GEOMETRY = Path("/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
GWANAK_LAYER = "gwanak_buildings"
SPLIT_PATH = BASE / "metadata" / "evaluation_splits" / "gwanak_building_evaluation_split.parquet"

SETTINGS = {
    "A_current_0p1_0p1": {"shape": 0.1, "location": 0.1, "reuse_existing": True, "label": "A current controlled"},
    "B_paper_default_like_1p0_0p0": {"shape": 1.0, "location": 0.0, "reuse_existing": False, "label": "B paper-default-like"},
    "C_no_regularization_0p0_0p0": {"shape": 0.0, "location": 0.0, "reuse_existing": False, "label": "C no latent regularization"},
    "D_mixed_0p1_0p0": {"shape": 0.1, "location": 0.0, "reuse_existing": False, "label": "D mixed"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geo-dim", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=4)
    parser.add_argument("--num-freqs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--weight-decay-init", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=20260608)
    parser.add_argument("--checkpoint-every-steps", type=int, default=250)
    parser.add_argument("--keep-checkpoints", type=int, default=2)
    parser.add_argument("--skip-existing", action="store_true", default=True)
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def source_paths() -> dict[str, Path]:
    sample_root = BASE / "sample_caches" / SOURCE_STUDY
    return {
        "id_map": BASE / "id_maps" / SOURCE_STUDY / "gwanak_buildings_geo2vec_global_id_map.parquet",
        "shape_manifest": sample_root / "korea_geo2vec_shape_samples_38547_sdf_gwanak_full_geo2vec_0200_v1" / "manifest.json",
        "location_manifest": sample_root / "korea_geo2vec_location_samples_38547_sdf_gwanak_full_geo2vec_0200_v1" / "manifest.json",
    }


def gpu_snapshot() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free", "--format=csv,noheader,nounits"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        gpus = []
        for line in proc.stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) == 5:
                gpus.append({"index": int(parts[0]), "name": parts[1], "total_vram_mb": int(parts[2]), "used_vram_mb": int(parts[3]), "free_vram_mb": int(parts[4])})
        return {"available": True, "gpus": sorted(gpus, key=lambda x: x["free_vram_mb"], reverse=True)}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "gpus": []}


def parse_time_v(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(errors="replace")
    out: dict[str, Any] = {}
    patterns = {
        "user_seconds": r"User time \(seconds\):\s+([0-9.]+)",
        "system_seconds": r"System time \(seconds\):\s+([0-9.]+)",
        "maxrss_kb": r"Maximum resident set size \(kbytes\):\s+([0-9]+)",
    }
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            out[key] = float(m.group(1))
    if "maxrss_kb" in out:
        out["maxrss_mb"] = out["maxrss_kb"] / 1024.0
    return out


def launch(name: str, cmd: list[str], log_dir: Path, cuda_device: str | None, workload: dict[str, Any]) -> tuple[subprocess.Popen, dict[str, Any]]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    time_path = log_dir / f"{name}.time.txt"
    env = os.environ.copy()
    if cuda_device is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(cuda_device)
    stdout = stdout_path.open("w", encoding="utf-8")
    stderr = stderr_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(["/usr/bin/time", "-v", "-o", str(time_path), *cmd], cwd=ROOT, stdout=stdout, stderr=stderr, text=True, env=env)
    return proc, {
        "stage": name,
        "command": cmd,
        "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES"),
        "assigned_gpu_id": cuda_device,
        "start_timestamp": now_iso(),
        "start_wall": time.time(),
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "time_path": time_path,
        "stdout_handle": stdout,
        "stderr_handle": stderr,
        "workload": workload,
    }


def finish(proc: subprocess.Popen, meta: dict[str, Any], log_dir: Path, summary_path: Path | None, gpu_info: dict[str, Any] | None) -> dict[str, Any]:
    returncode = proc.wait()
    meta["stdout_handle"].close()
    meta["stderr_handle"].close()
    summary = read_json(summary_path) if summary_path and summary_path.exists() else {}
    row = {
        "stage": meta["stage"],
        "command": meta["command"],
        "setting": meta["workload"].get("setting"),
        "branch": meta["workload"].get("branch"),
        "assigned_gpu_id": meta["assigned_gpu_id"],
        "cuda_visible_devices": meta["cuda_visible_devices"],
        "start_timestamp": meta["start_timestamp"],
        "end_timestamp": now_iso(),
        "elapsed_seconds": float(time.time() - meta["start_wall"]),
        "returncode": int(returncode),
        "stdout_log": str(meta["stdout_path"]),
        "stderr_log": str(meta["stderr_path"]),
        "process_cpu": parse_time_v(meta["time_path"]),
        "gpu_model": gpu_info.get("name") if gpu_info else None,
        "total_vram_mb": gpu_info.get("total_vram_mb") if gpu_info else None,
        "summary": summary,
        "checkpoint_path": summary.get("final_checkpoint"),
        "output_file_size_mb": path_size_mb(Path(summary["final_checkpoint"])) if summary.get("final_checkpoint") else None,
        **meta["workload"],
    }
    write_json_atomic(log_dir / f"{meta['stage']}_resource_log.json", row)
    if returncode != 0:
        raise RuntimeError(f"Stage failed: {meta['stage']}; see {meta['stderr_path']}")
    return row


def run_simple(name: str, cmd: list[str], log_dir: Path, summary_path: Path | None = None) -> dict[str, Any]:
    proc, meta = launch(name, cmd, log_dir, None, {})
    return finish(proc, meta, log_dir, summary_path, None)


def train_cmd(args: argparse.Namespace, branch: str, setting: str, code_reg: float, run_dir: Path, manifest: Path) -> list[str]:
    return [
        sys.executable,
        str(PROTOTYPE_DIR / "train_global_geo2vec_from_sample_cache.py"),
        "--id-map",
        str(source_paths()["id_map"]),
        "--manifest-json",
        str(manifest),
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
        str(args.epochs),
        "--lr",
        str(args.lr),
        "--code-reg-weight",
        str(code_reg),
        "--weight-decay-init",
        str(args.weight_decay_init),
        "--checkpoint-every-steps",
        str(args.checkpoint_every_steps),
        "--keep-checkpoints",
        str(args.keep_checkpoints),
        "--base-seed",
        str(args.seed),
    ]


def latest_checkpoint(summary_path: Path) -> Path:
    return Path(read_json(summary_path)["final_checkpoint"])


def setting_paths(setting: str, args: argparse.Namespace) -> dict[str, Any]:
    if SETTINGS[setting]["reuse_existing"]:
        train_root = TRAINING_RUN_DIR / EPOCH_STUDY
        embed_root = EMBEDDING_DIR / EPOCH_STUDY
        eval_dir = METADATA_DIR / EPOCH_STUDY / "r_evaluation_epoch010_full"
        return {
            "training_root": train_root,
            "embedding_root": embed_root,
            "eval_dir": eval_dir,
            "shape_run_dir": train_root / "gwanak_geo2vec_shape_32d_epoch010",
            "location_run_dir": train_root / "gwanak_geo2vec_location_32d_epoch010",
            "shape_embedding_dir": embed_root / "gwanak_geo2vec_shape_32d_epoch010_shape_embeddings",
            "location_embedding_dir": embed_root / "gwanak_geo2vec_location_32d_epoch010_location_embeddings",
            "full_embedding_dir": embed_root / "gwanak_full_geo2vec_32d_epoch010_embeddings",
        }
    train_root = TRAINING_RUN_DIR / STUDY_NAME / setting
    embed_root = EMBEDDING_DIR / STUDY_NAME / setting
    eval_dir = METADATA_DIR / STUDY_NAME / "r_evaluation" / setting
    return {
        "training_root": train_root,
        "embedding_root": embed_root,
        "eval_dir": eval_dir,
        "shape_run_dir": train_root / f"gwanak_geo2vec_shape_32d_epoch010_{setting}",
        "location_run_dir": train_root / f"gwanak_geo2vec_location_32d_epoch010_{setting}",
    }


def ensure_exports(args: argparse.Namespace, setting: str, paths: dict[str, Any], checkpoints: dict[str, Path], log_dir: Path) -> dict[str, Path]:
    embed_root = paths["embedding_root"]
    embed_root.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for branch in ["shape", "location"]:
        if SETTINGS[setting]["reuse_existing"]:
            out[branch] = paths[f"{branch}_embedding_dir"]
            continue
        run_name = paths[f"{branch}_run_dir"].name
        manifest = embed_root / f"{run_name}_{branch}_embeddings" / "embedding_export_manifest.json"
        if not manifest.exists():
            run_simple(
                f"{setting}_{branch}_export",
                [
                    sys.executable,
                    str(PROTOTYPE_DIR / "export_global_geo2vec_embeddings.py"),
                    "--checkpoint",
                    str(checkpoints[branch]),
                    "--id-map",
                    str(source_paths()["id_map"]),
                    "--output-dir",
                    str(embed_root),
                    "--branch",
                    branch,
                    "--column-style",
                    "branch",
                ],
                log_dir,
                manifest,
            )
        out[branch] = Path(read_json(manifest)["output_dir"])
    if SETTINGS[setting]["reuse_existing"]:
        out["full"] = paths["full_embedding_dir"]
    else:
        full_manifest = embed_root / f"gwanak_full_geo2vec_32d_epoch010_{setting}_embeddings" / "embedding_export_manifest.json"
        if not full_manifest.exists():
            run_simple(
                f"{setting}_full_export",
                [
                    sys.executable,
                    str(PROTOTYPE_DIR / "export_full_geo2vec_embeddings.py"),
                    "--location-checkpoint",
                    str(checkpoints["location"]),
                    "--shape-checkpoint",
                    str(checkpoints["shape"]),
                    "--id-map",
                    str(source_paths()["id_map"]),
                    "--output-dir",
                    str(embed_root),
                    "--name",
                    f"gwanak_full_geo2vec_32d_epoch010_{setting}",
                ],
                log_dir,
                full_manifest,
            )
        out["full"] = Path(read_json(full_manifest)["output_dir"])
    return out


def ensure_r_eval(setting: str, embed_dirs: dict[str, Path], eval_dir: Path, log_dir: Path) -> Path:
    manifest = eval_dir / "r_evaluation_manifest.json"
    if manifest.exists():
        return manifest
    cmd = [
        "Rscript",
        str(PROTOTYPE_DIR / "evaluate_geo2vec_embeddings.R"),
        "--shape-embedding-dir",
        str(embed_dirs["shape"]),
        "--location-embedding-dir",
        str(embed_dirs["location"]),
        "--full-embedding-dir",
        str(embed_dirs["full"]),
        "--split-path",
        str(SPLIT_PATH),
        "--output-dir",
        str(eval_dir),
        "--max-model-rows",
        "0",
        "--nthreads-xgboost",
        "32",
        "--nthreads-umap",
        "32",
        "--overwrite",
    ]
    run_simple(f"{setting}_r_evaluation", cmd, log_dir, manifest)
    return manifest


def summarize_training(setting: str, branch: str, run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "training_summary.json"
    metrics_path = run_dir / "training_metrics.jsonl"
    summary = read_json(summary_path)
    metrics = pd.read_json(metrics_path, lines=True)
    final = metrics.loc[metrics["epoch"] == metrics["epoch"].max()]
    return {
        "setting": setting,
        "branch": branch,
        "training_summary": str(summary_path),
        "metrics_path": str(metrics_path),
        "elapsed_seconds": float(summary.get("elapsed_seconds", 0.0)),
        "peak_maxrss_mb": summary.get("peak_maxrss_mb"),
        "peak_gpu_allocated_mb": summary.get("peak_gpu_allocated_mb"),
        "peak_gpu_reserved_mb": summary.get("peak_gpu_reserved_mb"),
        "final_reconstruction_loss": float(final["mean_train_reconstruction_loss"].mean()) if "mean_train_reconstruction_loss" in final else None,
        "final_latent_regularization_loss": float(final["mean_train_latent_regularization_loss"].mean()) if "mean_train_latent_regularization_loss" in final else None,
        "final_total_loss": float(final["mean_train_loss"].mean()),
        "final_validation_l1": float(final["validation_l1"].mean()),
        "code_reg_weight": SETTINGS[setting][branch],
    }


def main() -> None:
    args = parse_args()
    paths0 = source_paths()
    for p in [*paths0.values(), SPLIT_PATH]:
        if not p.exists():
            raise RuntimeError(f"Missing required reused input: {p}")
    n = len(pd.read_parquet(paths0["id_map"], columns=["geo2vec_internal_id"]))
    sample_counts = {"shape": int(read_json(paths0["shape_manifest"])["total_samples"]), "location": int(read_json(paths0["location_manifest"])["total_samples"])}
    gpu = gpu_snapshot()
    usable = gpu.get("gpus", [])
    assignments = {"shape": str(usable[0]["index"]) if usable else None, "location": str(usable[1]["index"]) if len(usable) > 1 else (str(usable[0]["index"]) if usable else None)}
    log_dir = LOG_DIR / STUDY_NAME
    analysis_dir = METADATA_DIR / STUDY_NAME / "analysis"
    log_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    training_rows = []
    all_eval = []
    for setting, cfg in SETTINGS.items():
        paths = setting_paths(setting, args)
        for p in [paths["training_root"], paths["embedding_root"], paths["eval_dir"]]:
            p.mkdir(parents=True, exist_ok=True)
        checkpoints: dict[str, Path] = {}
        if cfg["reuse_existing"]:
            checkpoints = {
                "shape": latest_checkpoint(paths["shape_run_dir"] / "training_summary.json"),
                "location": latest_checkpoint(paths["location_run_dir"] / "training_summary.json"),
            }
        else:
            launched = []
            for branch, manifest in [("shape", paths0["shape_manifest"]), ("location", paths0["location_manifest"])]:
                run_dir = paths[f"{branch}_run_dir"]
                summary_path = run_dir / "training_summary.json"
                if not summary_path.exists():
                    cmd = train_cmd(args, branch, setting, cfg[branch], run_dir, manifest)
                    workload = {"setting": setting, "branch": branch, "number_of_entities": n, "number_of_sdf_samples": sample_counts[branch], "batch_size": args.batch_size, "epochs": args.epochs, "code_reg_weight": cfg[branch]}
                    if len(usable) >= 2:
                        proc, meta = launch(f"{setting}_{branch}_training", cmd, log_dir, assignments[branch], workload)
                        ginfo = next((g for g in usable if str(g["index"]) == assignments[branch]), None)
                        launched.append((proc, meta, summary_path, ginfo))
                    else:
                        proc, meta = launch(f"{setting}_{branch}_training", cmd, log_dir, assignments[branch], workload)
                        ginfo = next((g for g in usable if str(g["index"]) == assignments[branch]), None)
                        finish(proc, meta, log_dir, summary_path, ginfo)
            for proc, meta, summary_path, ginfo in launched:
                finish(proc, meta, log_dir, summary_path, ginfo)
            for branch in ["shape", "location"]:
                checkpoints[branch] = latest_checkpoint(paths[f"{branch}_run_dir"] / "training_summary.json")
        embed_dirs = ensure_exports(args, setting, paths, checkpoints, log_dir)
        eval_manifest = ensure_r_eval(setting, embed_dirs, paths["eval_dir"], log_dir)
        for branch in ["shape", "location"]:
            training_rows.append(summarize_training(setting, branch, paths[f"{branch}_run_dir"]))
        ev = pd.read_parquet(read_json(eval_manifest)["recoverability_metrics"])
        ev.insert(0, "setting", setting)
        all_eval.append(ev)
        outputs.append({"setting": setting, "label": cfg["label"], "shape_code_reg_weight": cfg["shape"], "location_code_reg_weight": cfg["location"], "shape_embedding_dir": str(embed_dirs["shape"]), "location_embedding_dir": str(embed_dirs["location"]), "full_embedding_dir": str(embed_dirs["full"]), "r_evaluation_manifest": str(eval_manifest)})
    training_df = pd.DataFrame(training_rows)
    eval_df = pd.concat(all_eval, ignore_index=True)
    write_parquet_atomic(training_df, analysis_dir / "training_summary_by_setting_branch.parquet")
    write_parquet_atomic(eval_df, analysis_dir / "r_recoverability_metrics_by_setting.parquet")
    selected = ["compactness", "bbox_aspect_ratio", "perimeter", "area", "centroid_x", "centroid_y"]
    score = eval_df.loc[(eval_df["split"] == "spatial") & (eval_df["model"].isin(["ranger_random_forest", "xgboost"])) & (eval_df["embedding"] == "full_geo2vec") & (eval_df["target"].isin(selected))]
    score_summary = score.groupby(["setting", "model"], as_index=False)["r2"].mean().rename(columns={"r2": "mean_selected_spatial_full_r2"})
    write_parquet_atomic(score_summary, analysis_dir / "spatial_full_score_summary.parquet")
    best = score_summary.groupby("setting")["mean_selected_spatial_full_r2"].mean().sort_values(ascending=False)
    recommended = str(best.index[0])
    manifest = {
        "script": Path(__file__).name,
        "complete": True,
        "study_name": STUDY_NAME,
        "settings": SETTINGS,
        "recommended_setting": recommended,
        "gpu_snapshot": gpu,
        "assignments": assignments,
        "id_map": str(paths0["id_map"]),
        "shape_manifest": str(paths0["shape_manifest"]),
        "location_manifest": str(paths0["location_manifest"]),
        "split_path": str(SPLIT_PATH),
        "analysis_dir": str(analysis_dir),
        "training_summary": str(analysis_dir / "training_summary_by_setting_branch.parquet"),
        "recoverability_metrics": str(analysis_dir / "r_recoverability_metrics_by_setting.parquet"),
        "score_summary": str(analysis_dir / "spatial_full_score_summary.parquet"),
        "outputs": outputs,
        "contains_handcrafted_geometry_features": False,
        "sample_caches_regenerated": False,
        "large_scale_runs_started": False,
    }
    manifest_path = analysis_dir / "gwanak_full_geo2vec_gamma_ablation_manifest.json"
    write_json_atomic(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
