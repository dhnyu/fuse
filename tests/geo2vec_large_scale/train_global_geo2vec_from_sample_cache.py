#!/usr/bin/env python3
"""Train one global Geo2Vec model from disk-backed SDF sample shards."""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import torch
import torch.nn.functional as F

from geo2vec_large_scale_common import (
    BASE_SEED,
    EXTERNAL_REPO,
    TRAINING_RUN_DIR,
    append_jsonl,
    current_rss_mb,
    gpu_memory_mb,
    latest_checkpoint,
    maxrss_mb,
    read_json,
    seed_everything,
    sha256_file,
    write_json_atomic,
)

sys.path.insert(0, str(EXTERNAL_REPO))
from models.Geo2Vec import Geo2Vec_Model, SDFLoss  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id-map", type=Path, required=True)
    parser.add_argument("--manifest-json", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--geo-dim", type=int, default=32)
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=4)
    parser.add_argument("--num-freqs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--code-reg-weight", type=float, default=0.1)
    parser.add_argument("--weight-decay-init", type=float, default=0.01)
    parser.add_argument("--checkpoint-every-steps", type=int, default=250)
    parser.add_argument("--keep-checkpoints", type=int, default=0, help="Keep only the latest K checkpoints; 0 disables retention.")
    parser.add_argument("--stop-after-steps", type=int)
    parser.add_argument("--base-seed", type=int, default=BASE_SEED)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite-run-dir", action="store_true")
    return parser.parse_args()


def validate_sample_manifest_for_training(manifest: dict[str, Any]) -> None:
    required = ["complete", "manifest_parquet", "sample_dir", "total_samples", "shard_count"]
    missing = [key for key in required if key not in manifest]
    if missing:
        raise RuntimeError(f"Sample manifest missing required keys: {missing}")
    if not manifest.get("complete"):
        raise RuntimeError("Sample manifest is not marked complete.")
    manifest_path = Path(manifest["manifest_parquet"])
    if not manifest_path.exists():
        raise RuntimeError(f"Sample manifest parquet does not exist: {manifest_path}")
    sample_dir = Path(manifest["sample_dir"])
    if not sample_dir.exists():
        raise RuntimeError(f"Sample directory does not exist: {sample_dir}")
    shard_manifest = pd.read_parquet(manifest_path)
    required_cols = {"path", "status", "row_count", "building_count", "checksum_sha256"}
    missing_cols = required_cols.difference(shard_manifest.columns)
    if missing_cols:
        raise RuntimeError(f"Sample shard manifest missing columns: {sorted(missing_cols)}")
    bad_status = shard_manifest.loc[shard_manifest["status"] != "complete"]
    if len(bad_status):
        raise RuntimeError(f"Sample manifest has {len(bad_status)} non-complete shards.")
    missing_paths = [p for p in shard_manifest["path"].map(Path) if not p.exists()]
    if missing_paths:
        raise RuntimeError(f"Sample manifest has missing shard files, first: {missing_paths[0]}")
    failed_count = int(shard_manifest.get("failed_building_count", pd.Series([0])).fillna(0).sum())
    invalid_count = int(shard_manifest.get("invalid_building_count", pd.Series([0])).fillna(0).sum())
    if failed_count or invalid_count:
        raise RuntimeError(f"Sample manifest has failed_building_count={failed_count}, invalid_building_count={invalid_count}.")
    row_count = int(shard_manifest["row_count"].sum())
    if row_count != int(manifest["total_samples"]):
        raise RuntimeError(f"Manifest total_samples {manifest['total_samples']} != shard row sum {row_count}.")


def rng_state() -> dict[str, Any]:
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
        "torch_cuda_all": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
    }


def restore_rng_state(state: dict[str, Any]) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch_state = state["torch"]
    if isinstance(torch_state, torch.Tensor):
        torch_state = torch_state.detach().cpu().to(torch.uint8)
    torch.set_rng_state(torch_state)
    if torch.cuda.is_available() and state.get("torch_cuda_all") is not None:
        cuda_states = [
            x.detach().cpu().to(torch.uint8) if isinstance(x, torch.Tensor) else x
            for x in state["torch_cuda_all"]
        ]
        torch.cuda.set_rng_state_all(cuda_states)


def checkpoint_path(run_dir: Path, global_step: int) -> Path:
    return run_dir / f"checkpoint_step_{global_step:08d}.pt"


def apply_checkpoint_retention(run_dir: Path, keep_checkpoints: int) -> None:
    if keep_checkpoints <= 0:
        return
    checkpoints = sorted(run_dir.glob("checkpoint_step_*.pt"))
    stale = checkpoints[: max(0, len(checkpoints) - keep_checkpoints)]
    for path in stale:
        complete = path.with_suffix(".complete.json")
        path.unlink(missing_ok=True)
        complete.unlink(missing_ok=True)


def save_checkpoint(
    run_dir: Path,
    model: Geo2Vec_Model,
    optimizer: torch.optim.Optimizer,
    state: dict[str, Any],
    keep_checkpoints: int = 0,
) -> Path:
    path = checkpoint_path(run_dir, state["global_step"])
    tmp = path.with_suffix(".pt.tmp")
    payload = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        **state,
        "rng_states": rng_state(),
    }
    torch.save(payload, tmp)
    os.replace(tmp, path)
    write_json_atomic(path.with_suffix(".complete.json"), {"checkpoint": str(path), "bytes": path.stat().st_size})
    apply_checkpoint_retention(run_dir, keep_checkpoints)
    return path


def make_model(args: argparse.Namespace, n_poly: int, device: torch.device) -> Geo2Vec_Model:
    model = Geo2Vec_Model(
        n_poly=n_poly,
        z_size=args.geo_dim,
        hidden_size=args.hidden_size,
        num_freqs=args.num_freqs,
        weight_decay=args.weight_decay_init,
        log_sampling=True,
        polar_fourier=False,
        num_layers=args.num_layers,
    )
    return model.to(device)


def train_batch(
    model: Geo2Vec_Model,
    optimizer: torch.optim.Optimizer,
    loss_fn: SDFLoss,
    device: torch.device,
    batch: pd.DataFrame,
) -> float:
    ids = torch.as_tensor(batch["geo2vec_internal_id"].to_numpy(dtype=np.int64), dtype=torch.long, device=device)
    xy = torch.as_tensor(batch[["x", "y"]].to_numpy(dtype=np.float32), dtype=torch.float32, device=device)
    sdf = torch.as_tensor(batch["sdf"].to_numpy(dtype=np.float32).reshape(-1, 1), dtype=torch.float32, device=device)
    optimizer.zero_grad(set_to_none=True)
    pred = model(ids, xy)
    latent = model.poly_embedding_layer(ids)
    loss = loss_fn(pred, sdf, latent)
    loss.backward()
    optimizer.step()
    return float(loss.item())


def eval_validation(model: Geo2Vec_Model, device: torch.device, df: pd.DataFrame, batch_size: int) -> float | None:
    val = df.loc[df["split"] == 1]
    if val.empty:
        return None
    losses = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(val), batch_size):
            batch = val.iloc[start : start + batch_size]
            ids = torch.as_tensor(batch["geo2vec_internal_id"].to_numpy(dtype=np.int64), dtype=torch.long, device=device)
            xy = torch.as_tensor(batch[["x", "y"]].to_numpy(dtype=np.float32), dtype=torch.float32, device=device)
            sdf = torch.as_tensor(batch["sdf"].to_numpy(dtype=np.float32).reshape(-1, 1), dtype=torch.float32, device=device)
            pred = model(ids, xy)
            losses.append(float(F.l1_loss(pred, sdf, reduction="mean").item()))
    model.train()
    return float(np.mean(losses)) if losses else None


def synchronize_if_cuda(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def main() -> None:
    args = parse_args()
    manifest = read_json(args.manifest_json)
    validate_sample_manifest_for_training(manifest)
    suffix = Path(manifest["sample_dir"]).name.replace("korea_geo2vec_sdf_samples_", "")
    run_dir = args.run_dir or (TRAINING_RUN_DIR / f"korea_geo2vec_global_train_{suffix}_{args.geo_dim}d")
    if run_dir.exists() and any(run_dir.iterdir()) and not (args.resume or args.overwrite_run_dir):
        raise SystemExit(f"Run directory exists. Use --resume or --overwrite-run-dir: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = run_dir / "training_metrics.jsonl"
    id_map_checksum = sha256_file(args.id_map)
    manifest_checksum = manifest.get("manifest_checksum_sha256") or sha256_file(Path(manifest["manifest_parquet"]))
    id_map = pd.read_parquet(args.id_map, columns=["geo2vec_internal_id"])
    n_poly = int(id_map["geo2vec_internal_id"].max()) + 1
    seed_everything(args.base_seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    model = make_model(args, n_poly, device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = SDFLoss(code_reg_weight=args.code_reg_weight, sum=True)
    shard_manifest = pd.read_parquet(manifest["manifest_parquet"]).sort_values("shard_index").reset_index(drop=True)
    state: dict[str, Any] = {
        "epoch": 0,
        "global_step": 0,
        "current_shard_index": 0,
        "current_sample_offset": 0,
        "samples_seen": 0,
        "training_config": vars(args),
        "model_config": {
            "n_poly": n_poly,
            "geo_dim": args.geo_dim,
            "hidden_size": args.hidden_size,
            "num_layers": args.num_layers,
            "num_freqs": args.num_freqs,
        },
        "id_map_checksum": id_map_checksum,
        "sample_manifest_checksum": manifest_checksum,
        "device": str(device),
    }
    if args.resume:
        ckpt = latest_checkpoint(run_dir)
        if ckpt is not None:
            payload = torch.load(ckpt, map_location=device, weights_only=False)
            if payload.get("id_map_checksum") != id_map_checksum:
                raise RuntimeError("Checkpoint id-map checksum does not match.")
            if payload.get("sample_manifest_checksum") != manifest_checksum:
                raise RuntimeError("Checkpoint sample manifest checksum does not match.")
            model.load_state_dict(payload["model_state_dict"])
            optimizer.load_state_dict(payload["optimizer_state_dict"])
            restore_rng_state(payload["rng_states"])
            state.update({k: payload[k] for k in state.keys() if k in payload})
            print(f"resumed {ckpt}")

    start_global_step = int(state["global_step"])
    start_samples_seen = int(state["samples_seen"])
    start_time = time.time()
    for epoch in range(int(state["epoch"]), args.epochs):
        for shard_pos, shard in shard_manifest.iterrows():
            shard_index = int(shard["shard_index"])
            if epoch == state["epoch"] and shard_index < int(state["current_shard_index"]):
                continue
            df = pq.read_table(shard["path"]).to_pandas()
            train = df.loc[df["split"] == 0].reset_index(drop=True)
            order = np.random.default_rng(args.base_seed + epoch * 1_000_003 + shard_index).permutation(len(train))
            train = train.iloc[order].reset_index(drop=True)
            start_offset = int(state["current_sample_offset"]) if (epoch == state["epoch"] and shard_index == state["current_shard_index"]) else 0
            shard_loss = 0.0
            shard_steps = 0
            synchronize_if_cuda(device)
            shard_start = time.time()
            model.train()
            for offset in range(start_offset, len(train), args.batch_size):
                batch = train.iloc[offset : offset + args.batch_size]
                loss = train_batch(model, optimizer, loss_fn, device, batch)
                shard_loss += loss
                shard_steps += 1
                state["global_step"] += 1
                state["samples_seen"] += int(len(batch))
                state["epoch"] = epoch
                state["current_shard_index"] = shard_index
                state["current_sample_offset"] = int(offset + len(batch))
                if state["global_step"] % args.checkpoint_every_steps == 0:
                    save_checkpoint(run_dir, model, optimizer, state, args.keep_checkpoints)
                if args.stop_after_steps is not None and state["global_step"] >= args.stop_after_steps:
                    stopped_path = save_checkpoint(run_dir, model, optimizer, state, args.keep_checkpoints)
                    audit = {
                        "status": "controlled_stop",
                        "checkpoint": str(stopped_path),
                        "global_step": int(state["global_step"]),
                        "epoch": int(state["epoch"]),
                        "current_shard_index": int(state["current_shard_index"]),
                        "current_sample_offset": int(state["current_sample_offset"]),
                        "samples_seen": int(state["samples_seen"]),
                        "id_map_checksum": id_map_checksum,
                        "sample_manifest_checksum": manifest_checksum,
                    }
                    write_json_atomic(run_dir / "controlled_stop_audit.json", audit)
                    print(json.dumps(audit, indent=2, sort_keys=True))
                    return
            val_loss = eval_validation(model, device, df, args.batch_size)
            synchronize_if_cuda(device)
            elapsed = time.time() - shard_start
            row = {
                "epoch": epoch,
                "shard_index": shard_index,
                "global_step": int(state["global_step"]),
                "train_rows": int(len(train)),
                "validation_rows": int((df["split"] == 1).sum()),
                "mean_train_loss": float(shard_loss / shard_steps) if shard_steps else None,
                "validation_l1": val_loss,
                "elapsed_seconds": elapsed,
                "training_samples_per_second": float(len(train) / elapsed) if elapsed > 0 else None,
                "cpu_rss_mb": current_rss_mb(),
                "peak_maxrss_mb": maxrss_mb(),
                **gpu_memory_mb(),
            }
            append_jsonl(metrics_path, row)
            print(json.dumps(row, sort_keys=True))
            state["current_sample_offset"] = 0
        state["epoch"] = epoch + 1
        state["current_shard_index"] = 0
        state["current_sample_offset"] = 0
        save_checkpoint(run_dir, model, optimizer, state, args.keep_checkpoints)
    final_path = save_checkpoint(run_dir, model, optimizer, state, args.keep_checkpoints)
    summary = {
        "run_dir": str(run_dir),
        "final_checkpoint": str(final_path),
        "metrics_path": str(metrics_path),
        "elapsed_seconds": time.time() - start_time,
        "global_step": int(state["global_step"]),
        "samples_seen": int(state["samples_seen"]),
        "device": str(device),
        "cuda_available": bool(torch.cuda.is_available()),
        "peak_gpu_allocated_mb": torch.cuda.max_memory_allocated() / (1024**2) if torch.cuda.is_available() else None,
        "peak_gpu_reserved_mb": torch.cuda.max_memory_reserved() / (1024**2) if torch.cuda.is_available() else None,
        "cpu_rss_mb": current_rss_mb(),
        "peak_maxrss_mb": maxrss_mb(),
        "id_map_checksum": id_map_checksum,
        "sample_manifest_checksum": manifest_checksum,
        "checkpoint_retention_keep": int(args.keep_checkpoints),
        "resume_requested": bool(args.resume),
        "training_steps_this_invocation": int(state["global_step"]) - start_global_step,
        "samples_seen_this_invocation": int(state["samples_seen"]) - start_samples_seen,
    }
    summary_path = (
        run_dir / "resume_smoke_summary.json"
        if args.resume and summary["training_steps_this_invocation"] == 0
        else run_dir / "training_summary.json"
    )
    write_json_atomic(summary_path, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
