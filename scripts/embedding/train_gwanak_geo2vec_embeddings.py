#!/usr/bin/env python3
"""Train Gwanak Geo2Vec branch embeddings from staged SDF caches."""

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
import pyarrow as pa
import pyarrow.parquet as pq
import torch


DEFAULT_OUTPUT_ROOT = Path.home() / "fusedata" / "embeddings" / "gwanak_building_geo2vec"
EXTERNAL_REPO = Path.home() / "fuse_external" / "GeoNeuralRepresentation"
VALID_VARIANTS = ("shape_only", "shape_absolute_location", "shape_scene_relative_location")
sys.path.insert(0, str(EXTERNAL_REPO))
from models.Geo2Vec import Geo2Vec_Model, SDFLoss  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="phase1_smoke")
    parser.add_argument("--cache-run-id", default=None, help="Existing sample-cache run id to train from; defaults to --run-id.")
    parser.add_argument("--variant", choices=[*VALID_VARIANTS, "all"], default="all")
    parser.add_argument("--geo-dim", type=int, default=4)
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--num-layers", type=int, default=1)
    parser.add_argument("--num-freqs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--shape-code-reg-weight", type=float, default=1.0)
    parser.add_argument("--location-code-reg-weight", type=float, default=0.0)
    parser.add_argument("--weight-decay-init", type=float, default=0.01)
    parser.add_argument("--base-seed", type=int, default=20260615)
    parser.add_argument("--device", default=None)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


def path_size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / (1024**2)
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / (1024**2)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def branches_for_variant(variant: str) -> list[str]:
    return ["shape"] if variant == "shape_only" else ["shape", "location"]


def device_from_args(args: argparse.Namespace) -> torch.device:
    if args.device:
        return torch.device(args.device)
    return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


def cuda_index(device: torch.device) -> int:
    if device.type != "cuda":
        return 0
    return torch.cuda.current_device() if device.index is None else int(device.index)


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


def train_branch(args: argparse.Namespace, variant: str, branch: str, device: torch.device) -> dict[str, Any]:
    cache_run_id = args.cache_run_id or args.run_id
    manifest_path = args.output_root / "sample_caches" / cache_run_id / variant / branch / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Sample manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entity_map = pd.read_parquet(manifest["entity_map"])
    n_poly = int(entity_map["geo2vec_internal_id"].max()) + 1
    run_dir = args.output_root / "training_runs" / args.run_id / variant / branch
    export_dir = args.output_root / "embeddings" / args.run_id / variant / f"{branch}_embeddings"
    summary_path = run_dir / "training_summary.json"
    export_manifest_path = export_dir / "embedding_export_manifest.json"
    if summary_path.exists() and export_manifest_path.exists() and not args.overwrite:
        return json.loads(export_manifest_path.read_text(encoding="utf-8"))
    run_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    gpu_idx = cuda_index(device)
    if torch.cuda.is_available() and device.type == "cuda":
        torch.cuda.set_device(gpu_idx)
        torch.cuda.reset_peak_memory_stats(gpu_idx)
    seed_everything(args.base_seed + (17 if branch == "location" else 0) + len(variant))
    model = make_model(args, n_poly, device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    code_reg = args.shape_code_reg_weight if branch == "shape" else args.location_code_reg_weight
    loss_fn = SDFLoss(code_reg_weight=code_reg, sum=True)
    shard_manifest = pd.read_parquet(manifest["manifest_parquet"]).sort_values("shard_index")
    metrics = []
    start = time.time()
    global_step = 0
    samples_seen = 0
    for epoch in range(args.epochs):
        for shard in shard_manifest.itertuples(index=False):
            df = pq.read_table(shard.path).to_pandas()
            train = df.loc[df["split"] == 0].reset_index(drop=True)
            if train.empty:
                continue
            order = np.random.default_rng(args.base_seed + epoch * 1009 + int(shard.shard_index)).permutation(len(train))
            train = train.iloc[order].reset_index(drop=True)
            shard_loss = 0.0
            shard_steps = 0
            shard_start = time.time()
            for offset in range(0, len(train), args.batch_size):
                batch = train.iloc[offset : offset + args.batch_size]
                ids = torch.as_tensor(batch["geo2vec_internal_id"].to_numpy(np.int64), dtype=torch.long, device=device)
                xy = torch.as_tensor(batch[["x", "y"]].to_numpy(np.float32), dtype=torch.float32, device=device)
                sdf = torch.as_tensor(batch["sdf"].to_numpy(np.float32).reshape(-1, 1), dtype=torch.float32, device=device)
                optimizer.zero_grad(set_to_none=True)
                pred = model(ids, xy)
                latent = model.poly_embedding_layer(ids)
                loss = loss_fn(pred, sdf, latent)
                loss.backward()
                optimizer.step()
                shard_loss += float(loss.item())
                shard_steps += 1
                global_step += 1
                samples_seen += len(batch)
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            elapsed = time.time() - shard_start
            metrics.append(
                {
                    "epoch": epoch,
                    "shard_index": int(shard.shard_index),
                    "train_rows": int(len(train)),
                    "mean_train_loss": float(shard_loss / shard_steps),
                    "elapsed_seconds": elapsed,
                    "samples_per_second": float(len(train) / elapsed) if elapsed > 0 else None,
                }
            )
    checkpoint_path = run_dir / "checkpoint_final.pt"
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "model_config": {
                "n_poly": n_poly,
                "geo_dim": args.geo_dim,
                "hidden_size": args.hidden_size,
                "num_layers": args.num_layers,
                "num_freqs": args.num_freqs,
                "branch": branch,
                "variant": variant,
            },
            "training_config": vars(args),
            "cache_run_id": cache_run_id,
            "sample_manifest": manifest,
        },
        checkpoint_path,
    )
    weight = model.poly_embedding_layer.weight.detach().cpu().numpy().astype(np.float32)
    if not np.isfinite(weight).all():
        raise RuntimeError(f"Non-finite embeddings for {variant}/{branch}")
    key_cols = [c for c in entity_map.columns if c != "geo2vec_internal_id"]
    out = entity_map.copy()
    prefix = "geo2vec_shp" if branch == "shape" else "geo2vec_loc"
    for i in range(weight.shape[1]):
        out[f"{prefix}_{i:03d}"] = weight[out["geo2vec_internal_id"].to_numpy(np.int64), i]
    embedding_path = export_dir / "embeddings.parquet"
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), embedding_path, compression="zstd")
    summary = {
        "run_dir": str(run_dir),
        "checkpoint": str(checkpoint_path),
        "variant": variant,
        "branch": branch,
        "cache_run_id": cache_run_id,
        "entity_count": int(n_poly),
        "geo_dim": int(args.geo_dim),
        "epochs": int(args.epochs),
        "global_step": int(global_step),
        "samples_seen": int(samples_seen),
        "device": str(device),
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(gpu_idx) if device.type == "cuda" else None,
        "peak_gpu_allocated_mb": torch.cuda.max_memory_allocated(gpu_idx) / (1024**2) if device.type == "cuda" else None,
        "peak_gpu_reserved_mb": torch.cuda.max_memory_reserved(gpu_idx) / (1024**2) if device.type == "cuda" else None,
        "elapsed_seconds": time.time() - start,
        "metrics": metrics,
    }
    write_json_atomic(summary_path, summary)
    export_manifest = {
        "variant": variant,
        "branch": branch,
        "cache_run_id": cache_run_id,
        "embedding_kind": f"{variant}_{branch}",
        "embedding_path": str(embedding_path),
        "export_dir": str(export_dir),
        "entity_map": manifest["entity_map"],
        "key_columns": key_cols,
        "row_count": int(len(out)),
        "geo_dim": int(args.geo_dim),
        "columns": list(out.columns),
        "finite_values": True,
        "training_summary": str(summary_path),
        "checkpoint": str(checkpoint_path),
        "output_size_mb": path_size_mb(export_dir),
        "device": str(device),
        "gpu_name": summary["gpu_name"],
    }
    write_json_atomic(export_manifest_path, export_manifest)
    return export_manifest


def concatenate_variant(args: argparse.Namespace, variant: str, shape_manifest: dict[str, Any], loc_manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if loc_manifest is None:
        return None
    out_dir = args.output_root / "embeddings" / args.run_id / variant / "full_embeddings"
    manifest_path = out_dir / "embedding_export_manifest.json"
    if manifest_path.exists() and not args.overwrite:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    shape = pd.read_parquet(shape_manifest["embedding_path"])
    loc = pd.read_parquet(loc_manifest["embedding_path"])
    key_cols = loc_manifest["key_columns"]
    shape_cols = sorted([c for c in shape.columns if c.startswith("geo2vec_shp_")])
    loc_cols = sorted([c for c in loc.columns if c.startswith("geo2vec_loc_")])
    full = loc[key_cols + ["geo2vec_internal_id"] + loc_cols].merge(
        shape[key_cols + shape_cols],
        on=key_cols,
        how="left",
        validate="one_to_one",
    )
    if full[shape_cols].isna().any().any():
        raise RuntimeError(f"Shape join failed for full variant {variant}")
    if not np.isfinite(full[loc_cols + shape_cols].to_numpy(np.float32)).all():
        raise RuntimeError(f"Non-finite full embeddings for {variant}")
    embedding_path = out_dir / "embeddings.parquet"
    pq.write_table(pa.Table.from_pandas(full, preserve_index=False), embedding_path, compression="zstd")
    manifest = {
        "variant": variant,
        "embedding_kind": f"{variant}_full_location_shape",
        "branch_order": ["location", "shape"],
        "embedding_path": str(embedding_path),
        "export_dir": str(out_dir),
        "key_columns": key_cols,
        "row_count": int(len(full)),
        "location_dim": int(len(loc_cols)),
        "shape_dim": int(len(shape_cols)),
        "full_dim": int(len(loc_cols) + len(shape_cols)),
        "finite_values": True,
        "output_size_mb": path_size_mb(out_dir),
    }
    write_json_atomic(manifest_path, manifest)
    return manifest


def main() -> None:
    args = parse_args()
    if not EXTERNAL_REPO.exists():
        raise SystemExit(f"External GeoNeuralRepresentation repo not found: {EXTERNAL_REPO}")
    variants = list(VALID_VARIANTS) if args.variant == "all" else [args.variant]
    device = device_from_args(args)
    results: dict[str, Any] = {"run_id": args.run_id, "cache_run_id": args.cache_run_id or args.run_id, "device": str(device), "variants": {}}
    for variant in variants:
        branch_exports: dict[str, dict[str, Any]] = {}
        for branch in branches_for_variant(variant):
            branch_exports[branch] = train_branch(args, variant, branch, device)
        full = concatenate_variant(args, variant, branch_exports.get("shape"), branch_exports.get("location"))
        results["variants"][variant] = {"branches": branch_exports, "full": full}
    summary_path = args.output_root / "embeddings" / args.run_id / "training_embedding_summary.json"
    write_json_atomic(summary_path, results)
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
