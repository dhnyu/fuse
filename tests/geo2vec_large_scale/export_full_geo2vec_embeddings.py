#!/usr/bin/env python3
"""Export full Geo2Vec embeddings as [location, shape] from two branch checkpoints."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import torch

from geo2vec_large_scale_common import EMBEDDING_DIR, EXTERNAL_REPO, path_size_mb, write_json_atomic

sys.path.insert(0, str(EXTERNAL_REPO))
from models.Geo2Vec import Geo2Vec_Model  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--location-checkpoint", type=Path, required=True)
    parser.add_argument("--shape-checkpoint", type=Path, required=True)
    parser.add_argument("--id-map", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=EMBEDDING_DIR)
    parser.add_argument("--name", default=None)
    parser.add_argument("--batch-size", type=int, default=10000)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def load_weight(checkpoint: Path, expected_branch: str) -> tuple[np.ndarray, dict]:
    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False)
    cfg = ckpt["model_config"]
    branch = cfg.get("branch")
    if branch is not None and branch != expected_branch:
        raise RuntimeError(f"{checkpoint} has branch={branch!r}; expected {expected_branch!r}.")
    model = Geo2Vec_Model(
        n_poly=int(cfg["n_poly"]),
        z_size=int(cfg["geo_dim"]),
        hidden_size=int(cfg["hidden_size"]),
        num_freqs=int(cfg["num_freqs"]),
        log_sampling=True,
        polar_fourier=False,
        num_layers=int(cfg["num_layers"]),
    )
    model.load_state_dict(ckpt["model_state_dict"])
    weight = model.poly_embedding_layer.weight.detach().cpu().numpy().astype(np.float32)
    if not np.isfinite(weight).all():
        raise RuntimeError(f"Non-finite values found in {expected_branch} checkpoint.")
    return weight, cfg


def main() -> None:
    args = parse_args()
    loc_weight, loc_cfg = load_weight(args.location_checkpoint, "location")
    shp_weight, shp_cfg = load_weight(args.shape_checkpoint, "shape")
    if loc_weight.shape[0] != shp_weight.shape[0]:
        raise RuntimeError(f"Location rows {loc_weight.shape[0]} != shape rows {shp_weight.shape[0]}.")
    if loc_weight.shape[1] != shp_weight.shape[1]:
        raise RuntimeError(f"Location dim {loc_weight.shape[1]} != shape dim {shp_weight.shape[1]}.")

    name = args.name or f"{args.location_checkpoint.parent.name}__{args.shape_checkpoint.parent.name}__full_geo2vec"
    out_dir = args.output_dir / f"{name}_embeddings"
    manifest_path = out_dir / "embedding_export_manifest.json"
    if manifest_path.exists() and not args.overwrite:
        print(manifest_path.read_text())
        return
    out_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    pf = pq.ParquetFile(args.id_map)
    part_rows = []
    total_rows = 0
    part_index = 0
    geo_dim = int(loc_weight.shape[1])
    for batch in pf.iter_batches(batch_size=args.batch_size, columns=["building_id", "geo2vec_internal_id"]):
        df = batch.to_pandas()
        ids = df["geo2vec_internal_id"].to_numpy(dtype=np.int64)
        loc = loc_weight[ids]
        shp = shp_weight[ids]
        if not np.isfinite(loc).all() or not np.isfinite(shp).all():
            raise RuntimeError("Non-finite embedding value detected during export.")
        loc_df = pd.DataFrame({f"geo2vec_loc_{i:03d}": loc[:, i] for i in range(geo_dim)})
        shp_df = pd.DataFrame({f"geo2vec_shp_{i:03d}": shp[:, i] for i in range(geo_dim)})
        out = pd.concat([df.reset_index(drop=True), loc_df, shp_df], axis=1)
        part_path = out_dir / f"embeddings_part_{part_index:06d}.parquet"
        tmp = part_path.with_suffix(".parquet.tmp")
        pq.write_table(pa.Table.from_pandas(out, preserve_index=False), tmp, compression="zstd")
        tmp.replace(part_path)
        part_rows.append({"part_index": part_index, "path": str(part_path), "row_count": int(len(out)), "bytes": part_path.stat().st_size})
        total_rows += len(out)
        part_index += 1

    pq.write_table(pa.Table.from_pandas(pd.DataFrame(part_rows), preserve_index=False), out_dir / "embedding_export_parts.parquet", compression="zstd")
    manifest = {
        "location_checkpoint": str(args.location_checkpoint),
        "shape_checkpoint": str(args.shape_checkpoint),
        "id_map": str(args.id_map),
        "output_dir": str(out_dir),
        "row_count": int(total_rows),
        "expected_rows": int(loc_weight.shape[0]),
        "geo_dim_per_branch": geo_dim,
        "full_geo2vec_dim": int(geo_dim * 2),
        "embedding_kind": "full_geo2vec_location_shape",
        "branch_order": ["location", "shape"],
        "location_column_prefix": "geo2vec_loc",
        "shape_column_prefix": "geo2vec_shp",
        "location_model_config": loc_cfg,
        "shape_model_config": shp_cfg,
        "part_count": int(part_index),
        "finite_values": True,
        "elapsed_seconds": time.time() - start,
        "output_size_mb": path_size_mb(out_dir),
        "row_count_valid": int(total_rows) == int(loc_weight.shape[0]),
        "contains_handcrafted_geometry_features": False,
    }
    write_json_atomic(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
