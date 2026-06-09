#!/usr/bin/env python3
"""Run Gwanak full Geo2Vec with safe branch-level GPU parallelism."""

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

from geo2vec_large_scale_common import EMBEDDING_DIR, LOG_DIR, METADATA_DIR, PROTOTYPE_DIR, ROOT, TRAINING_RUN_DIR, path_size_mb, read_json, write_json_atomic


STUDY_NAME = "gwanak_full_geo2vec_parallel_branch_v1"
SOURCE_STUDY = "gwanak_full_geo2vec_paper_faithful_v1"
BASE = Path("/members/dhnyu/fusedata/geo2vec_large_scale")
GWANAK_GEOMETRY = Path("/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
GWANAK_LAYER = "gwanak_buildings"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--geo-dim", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=4)
    parser.add_argument("--num-freqs", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--code-reg-weight", type=float, default=0.1)
    parser.add_argument("--weight-decay-init", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=20260608)
    parser.add_argument("--keep-checkpoints", type=int, default=2)
    parser.add_argument("--checkpoint-every-steps", type=int, default=250)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--overwrite-run-dir", action="store_true")
    parser.add_argument("--allow-cpu-small-test", action="store_true")
    parser.add_argument("--max-gpus", type=int, help="Validation aid: cap usable GPUs from the initial nvidia-smi snapshot.")
    parser.add_argument(
        "--resume-smoke-existing",
        action="store_true",
        help="Validate branch-level concurrency by concurrently loading existing completed Gwanak branch checkpoints with --resume.",
    )
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
                gpus.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1],
                        "total_vram_mb": int(parts[2]),
                        "used_vram_mb": int(parts[3]),
                        "free_vram_mb": int(parts[4]),
                    }
                )
        return {"available": True, "gpus": sorted(gpus, key=lambda x: x["free_vram_mb"], reverse=True)}
    except Exception as exc:
        return {"available": False, "error": f"{type(exc).__name__}: {exc}", "gpus": []}


def parse_time_v(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    out: dict[str, Any] = {}
    patterns = {
        "user_seconds": r"User time \(seconds\):\s+([0-9.]+)",
        "system_seconds": r"System time \(seconds\):\s+([0-9.]+)",
        "maxrss_kb": r"Maximum resident set size \(kbytes\):\s+([0-9]+)",
    }
    text = path.read_text(errors="replace")
    for key, pattern in patterns.items():
        m = re.search(pattern, text)
        if m:
            out[key] = float(m.group(1))
    if "maxrss_kb" in out:
        out["maxrss_mb"] = out["maxrss_kb"] / 1024.0
    return out


def train_command(args: argparse.Namespace, branch: str, run_dir: Path, manifest: Path, resume: bool) -> list[str]:
    cmd = [
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
    if resume:
        cmd.append("--resume")
    if args.overwrite_run_dir:
        cmd.append("--overwrite-run-dir")
    return cmd


def launch_timed(name: str, cmd: list[str], log_dir: Path, cuda_device: str | None, workload: dict[str, Any]) -> tuple[subprocess.Popen, dict[str, Any]]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    time_path = log_dir / f"{name}.time.txt"
    wrapped = ["/usr/bin/time", "-v", "-o", str(time_path), *cmd]
    env = os.environ.copy()
    if cuda_device is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(cuda_device)
    started = now_iso()
    start_wall = time.time()
    stdout = stdout_path.open("w", encoding="utf-8")
    stderr = stderr_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(wrapped, cwd=ROOT, stdout=stdout, stderr=stderr, text=True, env=env)
    meta = {
        "stage": name,
        "command": cmd,
        "assigned_gpu_id": cuda_device,
        "cuda_visible_devices": env.get("CUDA_VISIBLE_DEVICES"),
        "start_timestamp": started,
        "start_wall": start_wall,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "time_path": time_path,
        "stdout_handle": stdout,
        "stderr_handle": stderr,
        "workload": workload,
    }
    return proc, meta


def finish_timed(proc: subprocess.Popen, meta: dict[str, Any], log_dir: Path, summary_path: Path | None, gpu_info: dict[str, Any]) -> dict[str, Any]:
    returncode = proc.wait()
    meta["stdout_handle"].close()
    meta["stderr_handle"].close()
    summary = read_json(summary_path) if summary_path and summary_path.exists() else {}
    row = {
        "stage": meta["stage"],
        "command": meta["command"],
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
        "cuda_available": summary.get("cuda_available"),
        "gpu_model": gpu_info.get("name") if gpu_info else None,
        "total_vram_mb": gpu_info.get("total_vram_mb") if gpu_info else None,
        "peak_gpu_allocated_mb": summary.get("peak_gpu_allocated_mb"),
        "peak_gpu_reserved_mb": summary.get("peak_gpu_reserved_mb"),
        "number_of_entities": meta["workload"].get("number_of_entities"),
        "number_of_sdf_samples": meta["workload"].get("number_of_sdf_samples"),
        "batch_size": meta["workload"].get("batch_size"),
        "epochs": meta["workload"].get("epochs"),
        "checkpoint_path": summary.get("final_checkpoint"),
        "output_file_size_mb": path_size_mb(Path(summary["final_checkpoint"])) if summary.get("final_checkpoint") else None,
        "summary": summary,
    }
    write_json_atomic(log_dir / f"{meta['stage']}_resource_log.json", row)
    if returncode != 0:
        raise RuntimeError(f"Stage failed: {meta['stage']}; see {meta['stderr_path']}")
    return row


def run_simple_stage(name: str, cmd: list[str], log_dir: Path, summary_path: Path | None = None) -> dict[str, Any]:
    proc, meta = launch_timed(name, cmd, log_dir, None, {})
    return finish_timed(proc, meta, log_dir, summary_path, {})


def latest_checkpoint(summary: Path) -> Path:
    return Path(read_json(summary)["final_checkpoint"])


def main() -> None:
    args = parse_args()
    paths = source_paths()
    for p in paths.values():
        if not p.exists():
            raise RuntimeError(f"Missing required input: {p}")
    id_map = pd.read_parquet(paths["id_map"], columns=["geo2vec_internal_id"])
    n = int(len(id_map))
    shape_samples = int(read_json(paths["shape_manifest"])["total_samples"])
    loc_samples = int(read_json(paths["location_manifest"])["total_samples"])
    log_dir = LOG_DIR / STUDY_NAME
    train_root = TRAINING_RUN_DIR / STUDY_NAME
    embed_root = EMBEDDING_DIR / STUDY_NAME
    eval_root = METADATA_DIR / STUDY_NAME / "r_evaluation"
    for p in [log_dir, train_root, embed_root, eval_root]:
        p.mkdir(parents=True, exist_ok=True)

    gpu = gpu_snapshot()
    usable = gpu.get("gpus", [])
    if args.max_gpus is not None:
        usable = usable[: max(0, int(args.max_gpus))]
        gpu["gpus_after_max_gpus_cap"] = usable
        gpu["max_gpus_cap"] = int(args.max_gpus)
    two_gpu = len(usable) >= 2
    if not usable and not args.allow_cpu_small_test:
        raise RuntimeError("CUDA/GPU unavailable; CPU fallback requires --allow-cpu-small-test.")
    mode = "parallel_two_gpu" if two_gpu else "sequential_single_gpu_or_cpu"
    assignments = {
        "shape": str(usable[0]["index"]) if usable else None,
        "location": str(usable[1]["index"]) if len(usable) > 1 else (str(usable[0]["index"]) if usable else None),
    }

    if args.resume_smoke_existing:
        source_train = TRAINING_RUN_DIR / SOURCE_STUDY
        run_dirs = {"shape": source_train / "gwanak_geo2vec_shape_32d", "location": source_train / "gwanak_geo2vec_location_32d"}
        resume = True
    else:
        run_dirs = {
            "shape": train_root / f"gwanak_geo2vec_shape_{args.geo_dim}d_epoch{args.epochs:03d}",
            "location": train_root / f"gwanak_geo2vec_location_{args.geo_dim}d_epoch{args.epochs:03d}",
        }
        resume = False

    branch_meta = {
        "shape": {"manifest": paths["shape_manifest"], "samples": shape_samples},
        "location": {"manifest": paths["location_manifest"], "samples": loc_samples},
    }
    branch_logs = []
    to_run = []
    for branch in ["shape", "location"]:
        summary = run_dirs[branch] / "training_summary.json"
        if summary.exists() and args.skip_existing and not args.resume_smoke_existing:
            continue
        cmd = train_command(args, branch, run_dirs[branch], branch_meta[branch]["manifest"], resume)
        workload = {"branch": branch, "number_of_entities": n, "number_of_sdf_samples": branch_meta[branch]["samples"], "batch_size": args.batch_size, "epochs": args.epochs}
        to_run.append((branch, cmd, summary, workload))

    if two_gpu and len(to_run) == 2:
        launched = []
        for branch, cmd, summary, workload in to_run:
            proc, meta = launch_timed(f"{branch}_training", cmd, log_dir, assignments[branch], workload)
            launched.append((proc, meta, summary, next((g for g in usable if str(g["index"]) == assignments[branch]), {})))
        for proc, meta, summary, ginfo in launched:
            branch_logs.append(finish_timed(proc, meta, log_dir, summary, ginfo))
    else:
        for branch, cmd, summary, workload in to_run:
            proc, meta = launch_timed(f"{branch}_training", cmd, log_dir, assignments[branch], workload)
            ginfo = next((g for g in usable if str(g["index"]) == assignments[branch]), {})
            branch_logs.append(finish_timed(proc, meta, log_dir, summary, ginfo))

    summaries = {b: run_dirs[b] / ("resume_smoke_summary.json" if args.resume_smoke_existing and (run_dirs[b] / "resume_smoke_summary.json").exists() else "training_summary.json") for b in ["shape", "location"]}
    checkpoints = {b: latest_checkpoint(summaries[b]) for b in ["shape", "location"]}

    export_manifests: dict[str, Path] = {}
    for branch in ["shape", "location"]:
        run_name = run_dirs[branch].name
        export_manifest = embed_root / f"{run_name}_{branch}_embeddings" / "embedding_export_manifest.json"
        export_manifests[branch] = export_manifest
        if not export_manifest.exists():
            cmd = [
                sys.executable,
                str(PROTOTYPE_DIR / "export_global_geo2vec_embeddings.py"),
                "--checkpoint",
                str(checkpoints[branch]),
                "--id-map",
                str(paths["id_map"]),
                "--output-dir",
                str(embed_root),
                "--branch",
                branch,
                "--column-style",
                "branch",
            ]
            run_simple_stage(f"{branch}_export", cmd, log_dir, export_manifest)
    full_manifest = embed_root / f"gwanak_full_geo2vec_{args.geo_dim}d_parallel_embeddings" / "embedding_export_manifest.json"
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
            str(embed_root),
            "--name",
            f"gwanak_full_geo2vec_{args.geo_dim}d_parallel",
        ]
        run_simple_stage("full_export", cmd, log_dir, full_manifest)

    manifest = {
        "script": Path(__file__).name,
        "complete": True,
        "mode": mode,
        "resume_smoke_existing": bool(args.resume_smoke_existing),
        "gpu_snapshot": gpu,
        "assignments": assignments,
        "branch_level_parallelism": bool(two_gpu),
        "sequential_fallback_available": True,
        "contains_handcrafted_geometry_features": False,
        "branch_order": ["location", "shape"],
        "id_map": str(paths["id_map"]),
        "shape_manifest": str(paths["shape_manifest"]),
        "location_manifest": str(paths["location_manifest"]),
        "shape_checkpoint": str(checkpoints["shape"]),
        "location_checkpoint": str(checkpoints["location"]),
        "shape_embedding_manifest": str(export_manifests["shape"]),
        "location_embedding_manifest": str(export_manifests["location"]),
        "full_embedding_manifest": str(full_manifest),
        "branch_resource_logs": [str(log_dir / f"{b}_training_resource_log.json") for b in ["shape", "location"]],
        "log_dir": str(log_dir),
    }
    out = METADATA_DIR / STUDY_NAME / "parallel_runner_validation_manifest.json"
    write_json_atomic(out, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
