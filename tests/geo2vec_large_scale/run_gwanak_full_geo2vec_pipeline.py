#!/usr/bin/env python3
"""Run the bounded Gwanak full Geo2Vec [location, shape] pipeline."""

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

import pandas as pd
import pyarrow.parquet as pq
import pyogrio

from geo2vec_large_scale_common import (
    BASE_SEED,
    EMBEDDING_DIR,
    ID_MAP_DIR,
    LOG_DIR,
    METADATA_DIR,
    PROTOTYPE_DIR,
    ROOT,
    SAMPLE_CACHE_DIR,
    TRAINING_RUN_DIR,
    dataframe_checksum,
    path_size_mb,
    read_json,
    suffix_for_limit,
    write_json_atomic,
    write_parquet_atomic,
)


GWANAK_GEOMETRY = Path("/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
GWANAK_LAYER = "gwanak_buildings"
REPORTS_DIR = ROOT / "reports"
STUDY_NAME = "gwanak_full_geo2vec_paper_faithful_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, default=GWANAK_GEOMETRY)
    parser.add_argument("--layer", default=GWANAK_LAYER)
    parser.add_argument("--geo-dim", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--buildings-per-shard", type=int, default=5000)
    parser.add_argument("--samples-per-unit", type=float, default=28.0)
    parser.add_argument("--point-sample", type=int, default=7)
    parser.add_argument("--uniform-grid", type=int, default=8)
    parser.add_argument("--sample-band-width", type=float, default=0.08)
    parser.add_argument("--sample-config-version", default="sdf_gwanak_full_geo2vec_0200_v1")
    parser.add_argument("--hidden-size", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=4)
    parser.add_argument("--num-freqs", type=int, default=4)
    parser.add_argument("--checkpoint-every-steps", type=int, default=250)
    parser.add_argument("--keep-checkpoints", type=int, default=2)
    parser.add_argument("--seed", type=int, default=BASE_SEED)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_nvidia_smi_once() -> dict[str, Any]:
    cmd = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10)
        rows = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            rows.append({"index": int(parts[0]), "name": parts[1], "total_vram_mb": int(parts[2])})
        return {"gpu_static_info_available": True, "gpus": rows}
    except Exception as exc:
        return {"gpu_static_info_available": False, "error": f"{type(exc).__name__}: {exc}"}


def torch_static_info() -> dict[str, Any]:
    try:
        import torch

        info: dict[str, Any] = {
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        }
        if torch.cuda.is_available():
            idx = torch.cuda.current_device()
            props = torch.cuda.get_device_properties(idx)
            info.update(
                {
                    "current_device": int(idx),
                    "gpu_name": props.name,
                    "total_vram_mb": int(props.total_memory / (1024**2)),
                    "peak_gpu_allocated_mb": float(torch.cuda.max_memory_allocated() / (1024**2)),
                    "peak_gpu_reserved_mb": float(torch.cuda.max_memory_reserved() / (1024**2)),
                }
            )
        return info
    except Exception as exc:
        return {"cuda_available": False, "error": f"{type(exc).__name__}: {exc}", "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES")}


def usage_snapshot(kind: int) -> dict[str, float]:
    usage = resource.getrusage(kind)
    return {
        "user_seconds": float(usage.ru_utime),
        "system_seconds": float(usage.ru_stime),
        "maxrss_mb": float(usage.ru_maxrss / 1024.0),
    }


def subtract_usage(end: dict[str, float], start: dict[str, float]) -> dict[str, float]:
    return {
        "user_seconds": end["user_seconds"] - start["user_seconds"],
        "system_seconds": end["system_seconds"] - start["system_seconds"],
        "maxrss_mb": end["maxrss_mb"],
    }


def run_stage(
    name: str,
    cmd: list[str],
    log_dir: Path,
    workload: dict[str, Any],
    extra_summary_paths: list[Path] | None = None,
) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{name}.stdout.log"
    stderr_path = log_dir / f"{name}.stderr.log"
    start_wall = time.time()
    start_ts = now_iso()
    self_start = usage_snapshot(resource.RUSAGE_SELF)
    child_start = usage_snapshot(resource.RUSAGE_CHILDREN)
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, text=True)
    end_wall = time.time()
    row: dict[str, Any] = {
        "stage": name,
        "command": cmd,
        "start_timestamp": start_ts,
        "end_timestamp": now_iso(),
        "elapsed_seconds": float(end_wall - start_wall),
        "returncode": int(proc.returncode),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "process_cpu": subtract_usage(usage_snapshot(resource.RUSAGE_SELF), self_start),
        "child_process_cpu": subtract_usage(usage_snapshot(resource.RUSAGE_CHILDREN), child_start),
        "memory_start": self_start,
        "memory_end": usage_snapshot(resource.RUSAGE_SELF),
        "gpu": torch_static_info(),
        "workload": workload,
    }
    if extra_summary_paths:
        summaries = {}
        for path in extra_summary_paths:
            if path.exists():
                try:
                    summaries[str(path)] = read_json(path)
                except Exception as exc:
                    summaries[str(path)] = {"error": f"{type(exc).__name__}: {exc}"}
        row["summaries"] = summaries
    write_json_atomic(log_dir / f"{name}_resource_log.json", row)
    if proc.returncode != 0:
        raise RuntimeError(f"Stage failed: {name}. See {stderr_path}")
    return row


def load_existing_resource_rows(log_dir: Path) -> list[dict[str, Any]]:
    preferred = [
        "shape_sample_cache_generation",
        "shape_sample_cache_validation",
        "location_sample_cache_generation",
        "location_sample_cache_validation",
        "shape_model_training",
        "location_model_training",
        "shape_embedding_export",
        "location_embedding_export",
        "full_geo2vec_export",
        "embedding_evaluation",
    ]
    rows = []
    for stage in preferred:
        path = log_dir / f"{stage}_resource_log.json"
        if path.exists():
            rows.append(read_json(path))
    return rows


def build_gwanak_id_map(geometry: Path, layer: str, overwrite: bool) -> tuple[Path, Path, int]:
    out_dir = ID_MAP_DIR / STUDY_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    id_map = out_dir / "gwanak_buildings_geo2vec_global_id_map.parquet"
    id_meta = out_dir / "gwanak_buildings_geo2vec_global_id_map_metadata.json"
    if id_map.exists() and id_meta.exists() and not overwrite:
        meta = read_json(id_meta)
        return id_map, id_meta, int(meta["row_count"])
    gdf = pyogrio.read_dataframe(geometry, layer=layer, columns=["building_id"])
    if gdf["building_id"].isna().any():
        raise RuntimeError("Gwanak id map has missing building_id values.")
    if not gdf["building_id"].is_unique:
        raise RuntimeError("Gwanak id map has duplicate building_id values.")
    df = pd.DataFrame({"building_id": gdf["building_id"].astype(str)})
    df = df.sort_values("building_id", kind="mergesort").reset_index(drop=True)
    df.insert(0, "geo2vec_internal_id", range(len(df)))
    df["geo2vec_internal_id"] = df["geo2vec_internal_id"].astype("int64")
    write_parquet_atomic(df[["building_id", "geo2vec_internal_id"]], id_map)
    meta = {
        "study_name": STUDY_NAME,
        "geometry": str(geometry),
        "layer": layer,
        "output_parquet": str(id_map),
        "row_count": int(len(df)),
        "missing_building_id": 0,
        "duplicate_building_id": 0,
        "min_internal_id": int(df["geo2vec_internal_id"].min()),
        "max_internal_id": int(df["geo2vec_internal_id"].max()),
        "ids_contiguous": bool((df["geo2vec_internal_id"].to_numpy() == range(len(df))).all()),
        "ordering": "building_id ascending, stable mergesort",
        "checksum_records_sha256": dataframe_checksum(df, ["building_id", "geo2vec_internal_id"]),
    }
    write_json_atomic(id_meta, meta)
    return id_map, id_meta, int(len(df))


def sample_manifest_path(sample_root: Path, branch: str, n: int, sample_config_version: str) -> Path:
    suffix = suffix_for_limit(n)
    return sample_root / f"korea_geo2vec_{branch}_samples_{suffix}_{sample_config_version}" / "manifest.json"


def embedding_manifest_dir(manifest_path: Path) -> Path:
    manifest = read_json(manifest_path)
    return Path(manifest["output_dir"])


def latest_checkpoint_from_summary(summary_path: Path) -> Path:
    summary = read_json(summary_path)
    return Path(summary["final_checkpoint"])


def validate_embedding_schema(shape_dir: Path, location_dir: Path, full_dir: Path, geo_dim: int) -> dict[str, Any]:
    def first_part(out_dir: Path) -> pd.DataFrame:
        parts = pd.read_parquet(out_dir / "embedding_export_parts.parquet").sort_values("part_index")
        return pd.read_parquet(parts.iloc[0]["path"])

    shape = first_part(shape_dir)
    location = first_part(location_dir)
    full = first_part(full_dir)
    shape_cols = sorted(c for c in shape.columns if c.startswith("geo2vec_shp_"))
    loc_cols = sorted(c for c in location.columns if c.startswith("geo2vec_loc_"))
    full_loc_cols = sorted(c for c in full.columns if c.startswith("geo2vec_loc_"))
    full_shp_cols = sorted(c for c in full.columns if c.startswith("geo2vec_shp_"))
    expected_full_prefix = ["building_id", "geo2vec_internal_id"] + [f"geo2vec_loc_{i:03d}" for i in range(geo_dim)] + [
        f"geo2vec_shp_{i:03d}" for i in range(geo_dim)
    ]
    result = {
        "shape_dim": len(shape_cols),
        "location_dim": len(loc_cols),
        "full_location_dim": len(full_loc_cols),
        "full_shape_dim": len(full_shp_cols),
        "full_dim": len(full_loc_cols) + len(full_shp_cols),
        "full_column_order_valid": list(full.columns[: len(expected_full_prefix)]) == expected_full_prefix,
        "expected_schema": expected_full_prefix,
        "observed_full_schema_prefix": list(full.columns[: len(expected_full_prefix)]),
    }
    result["valid"] = (
        result["shape_dim"] == geo_dim
        and result["location_dim"] == geo_dim
        and result["full_location_dim"] == geo_dim
        and result["full_shape_dim"] == geo_dim
        and result["full_dim"] == 2 * geo_dim
        and result["full_column_order_valid"]
    )
    if not result["valid"]:
        raise RuntimeError(f"Embedding schema validation failed: {json.dumps(result, indent=2)}")
    return result


def summarize_recoverability(evaluation_manifest: dict[str, Any]) -> dict[str, Any]:
    metrics = pd.read_parquet(evaluation_manifest["recoverability_metrics"])
    rows = {}
    for embedding in ["shape", "location", "full_geo2vec"]:
        sub = metrics.loc[(metrics["embedding"] == embedding) & (metrics["model"] == "random_forest")]
        rows[embedding] = {
            target: float(sub.loc[sub["target"] == target, "r2"].iloc[0])
            for target in ["area", "perimeter", "compactness", "centroid_x", "centroid_y"]
        }
    return rows


def write_report(
    args: argparse.Namespace,
    report_path: Path,
    run_manifest: dict[str, Any],
    evaluation_manifest: dict[str, Any],
    schema: dict[str, Any],
    resource_rows: list[dict[str, Any]],
) -> None:
    recoverability = summarize_recoverability(evaluation_manifest)
    retrieval = evaluation_manifest["retrieval"]
    pca = evaluation_manifest["pca"]
    umap = evaluation_manifest["umap"]
    resource_summary = [
        {
            "stage": row["stage"],
            "elapsed_seconds": row["elapsed_seconds"],
            "child_cpu_user_seconds": row["child_process_cpu"]["user_seconds"],
            "child_cpu_system_seconds": row["child_process_cpu"]["system_seconds"],
            "child_maxrss_mb": row["child_process_cpu"]["maxrss_mb"],
        }
        for row in resource_rows
    ]
    text = f"""# Gwanak Full Geo2Vec Pipeline and Evaluation

Generated: {now_iso()}

## 1. Executive Summary

The bounded Gwanak-scale full Geo2Vec workflow completed with separate paper-faithful location and shape branches and exported the final embedding as `z_E = [z_E^loc, z_E^shp]`. No handcrafted geometry variables were added to the embeddings.

Recommendation: {'ready for a 100k-building experiment with the same bounded logging and evaluation gates' if run_manifest['ready_for_100k'] else 'not ready for a 100k-building experiment until the listed problems are addressed'}.

## 2. Current Pipeline Status

- Study: `{STUDY_NAME}`
- Buildings: `{run_manifest['building_count']}`
- Geo_dim per branch: `{args.geo_dim}`
- Epochs per branch: `{args.epochs}`
- Shape cache: `{run_manifest['shape_sample_manifest']}`
- Location cache: `{run_manifest['location_sample_manifest']}`
- Shape checkpoint: `{run_manifest['shape_checkpoint']}`
- Location checkpoint: `{run_manifest['location_checkpoint']}`

## 3. Confirmation of Paper-Faithful Geo2Vec

- Shape branch uses per-entity shape normalization after dataset normalization.
- Location branch uses dataset/global normalization only.
- Full export branch order: `{run_manifest['branch_order']}`
- Handcrafted geometry features in embedding: `false`
- Evaluation proxy variables are computed only after export for diagnostics.

## 4. Scripts Added or Modified

- Added `tests/geo2vec_large_scale/run_gwanak_full_geo2vec_pipeline.py`
- Added `tests/geo2vec_large_scale/evaluate_geo2vec_embeddings.py`
- Reused existing cache, training, branch export, and full export scripts.

## 5. Experiment Configuration

```json
{json.dumps(run_manifest['experiment_config'], indent=2, sort_keys=True, default=str)}
```

## 6. Resource Usage Summary

```json
{json.dumps(resource_summary, indent=2, sort_keys=True, default=str)}
```

Detailed machine-readable logs are under `{run_manifest['resource_log_dir']}`.

## 7. Output Embedding Schema

- Shape-only dimension: `{schema['shape_dim']}`
- Location-only dimension: `{schema['location_dim']}`
- Full dimension: `{schema['full_dim']}`
- Full column order valid: `{str(schema['full_column_order_valid']).lower()}`
- Full schema starts with `building_id`, `geo2vec_internal_id`, `geo2vec_loc_000 ... geo2vec_loc_031`, then `geo2vec_shp_000 ... geo2vec_shp_031`.

## 8. Evaluation Framework

The evaluator compares shape-only, location-only, and full Geo2Vec embeddings using linear regression, ridge regression, and random forest recoverability. Geometry proxies are labels only. Retrieval diagnostics use nearest neighbors in each embedding space. PCA figures and coordinates are exported. UMAP was attempted only if the package was already available.

Evaluation output directory: `{evaluation_manifest['output_dir']}`

## 9. Shape-Only Results

Random forest R2:

```json
{json.dumps(recoverability['shape'], indent=2, sort_keys=True, default=str)}
```

## 10. Location-Only Results

Random forest R2:

```json
{json.dumps(recoverability['location'], indent=2, sort_keys=True, default=str)}
```

## 11. Full Geo2Vec Results

Random forest R2:

```json
{json.dumps(recoverability['full_geo2vec'], indent=2, sort_keys=True, default=str)}
```

## 12. Retrieval Diagnostics

```json
{json.dumps(retrieval, indent=2, sort_keys=True, default=str)}
```

## 13. PCA/UMAP Diagnostics

PCA:

```json
{json.dumps(pca, indent=2, sort_keys=True, default=str)}
```

UMAP:

```json
{json.dumps(umap, indent=2, sort_keys=True, default=str)}
```

## 14. Problems Found

{run_manifest['problems_found_markdown']}

## 15. Recommended Next Step

Proceed to a 100k-building experiment only if the 100k run uses the same paper-faithful two-branch workflow, exports `[location, shape]`, keeps geometry proxies out of embeddings, and runs this evaluation framework before any 1M or nationwide attempt.
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    started = now_iso()
    report_timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    run_root = METADATA_DIR / STUDY_NAME
    log_dir = LOG_DIR / STUDY_NAME
    sample_root = SAMPLE_CACHE_DIR / STUDY_NAME
    training_root = TRAINING_RUN_DIR / STUDY_NAME
    embedding_root = EMBEDDING_DIR / STUDY_NAME
    evaluation_dir = METADATA_DIR / STUDY_NAME / "evaluation"
    for path in [run_root, log_dir, sample_root, training_root, embedding_root, evaluation_dir, REPORTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)

    gpu_static_info = run_nvidia_smi_once()
    id_map, id_meta, n = build_gwanak_id_map(args.geometry, args.layer, args.overwrite)
    resource_rows: list[dict[str, Any]] = []

    for branch in ["shape", "location"]:
        manifest = sample_manifest_path(sample_root, branch, n, args.sample_config_version)
        if manifest.exists() and args.skip_existing:
            continue
        cmd = [
            sys.executable,
            str(PROTOTYPE_DIR / "generate_disk_backed_sdf_samples.py"),
            "--id-map",
            str(id_map),
            "--id-map-metadata",
            str(id_meta),
            "--geometry",
            str(args.geometry),
            "--layer",
            args.layer,
            "--output-dir",
            str(sample_root),
            "--limit",
            str(n),
            "--branch",
            branch,
            "--buildings-per-shard",
            str(args.buildings_per_shard),
            "--sample-config-version",
            args.sample_config_version,
            "--samples-per-unit",
            str(args.samples_per_unit),
            "--point-sample",
            str(args.point_sample),
            "--sample-band-width",
            str(args.sample_band_width),
            "--uniform-grid",
            str(args.uniform_grid),
            "--workers",
            str(args.workers),
        ]
        if args.overwrite:
            cmd.append("--overwrite")
        resource_rows.append(
            run_stage(
                f"{branch}_sample_cache_generation",
                cmd,
                log_dir,
                {"branch": branch, "number_of_workers": args.workers, "number_of_entities": n},
                [manifest],
            )
        )
        val_cmd = [
            sys.executable,
            str(PROTOTYPE_DIR / "validate_sample_cache.py"),
            "--manifest-json",
            str(manifest),
            "--id-map",
            str(id_map),
            "--overwrite",
        ]
        resource_rows.append(
            run_stage(
                f"{branch}_sample_cache_validation",
                val_cmd,
                log_dir,
                {"branch": branch, "number_of_entities": n},
                [manifest.parent / "sample_cache_validation.json"],
            )
        )

    shape_manifest = sample_manifest_path(sample_root, "shape", n, args.sample_config_version)
    location_manifest = sample_manifest_path(sample_root, "location", n, args.sample_config_version)
    checkpoints: dict[str, Path] = {}
    for branch, manifest in [("shape", shape_manifest), ("location", location_manifest)]:
        run_dir = training_root / f"gwanak_geo2vec_{branch}_{args.geo_dim}d"
        summary = run_dir / "training_summary.json"
        if not (summary.exists() and args.skip_existing):
            cmd = [
                sys.executable,
                str(PROTOTYPE_DIR / "train_global_geo2vec_from_sample_cache.py"),
                "--id-map",
                str(id_map),
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
                "--checkpoint-every-steps",
                str(args.checkpoint_every_steps),
                "--keep-checkpoints",
                str(args.keep_checkpoints),
                "--base-seed",
                str(args.seed),
            ]
            if args.overwrite:
                cmd.append("--overwrite-run-dir")
            resource_rows.append(
                run_stage(
                    f"{branch}_model_training",
                    cmd,
                    log_dir,
                    {
                        "branch": branch,
                        "batch_size": args.batch_size,
                        "number_of_workers": 0,
                        "number_of_entities": n,
                        "number_of_sdf_samples": int(read_json(manifest)["total_samples"]),
                    },
                    [summary],
                )
            )
        checkpoints[branch] = latest_checkpoint_from_summary(summary)

    branch_embedding_dirs: dict[str, Path] = {}
    for branch in ["shape", "location"]:
        manifest_path = embedding_root / f"gwanak_geo2vec_{branch}_{args.geo_dim}d_{branch}_embeddings" / "embedding_export_manifest.json"
        if not (manifest_path.exists() and args.skip_existing):
            cmd = [
                sys.executable,
                str(PROTOTYPE_DIR / "export_global_geo2vec_embeddings.py"),
                "--checkpoint",
                str(checkpoints[branch]),
                "--id-map",
                str(id_map),
                "--output-dir",
                str(embedding_root),
                "--branch",
                branch,
                "--column-style",
                "branch",
                "--batch-size",
                "10000",
            ]
            if args.overwrite:
                cmd.append("--overwrite")
            resource_rows.append(
                run_stage(
                    f"{branch}_embedding_export",
                    cmd,
                    log_dir,
                    {"branch": branch, "batch_size": 10000, "number_of_entities": n},
                    [manifest_path],
                )
            )
        branch_embedding_dirs[branch] = embedding_manifest_dir(manifest_path)

    full_manifest_path = embedding_root / f"gwanak_full_geo2vec_{args.geo_dim}d_embeddings" / "embedding_export_manifest.json"
    if not (full_manifest_path.exists() and args.skip_existing):
        cmd = [
            sys.executable,
            str(PROTOTYPE_DIR / "export_full_geo2vec_embeddings.py"),
            "--location-checkpoint",
            str(checkpoints["location"]),
            "--shape-checkpoint",
            str(checkpoints["shape"]),
            "--id-map",
            str(id_map),
            "--output-dir",
            str(embedding_root),
            "--name",
            f"gwanak_full_geo2vec_{args.geo_dim}d",
            "--batch-size",
            "10000",
        ]
        if args.overwrite:
            cmd.append("--overwrite")
        resource_rows.append(
            run_stage(
                "full_geo2vec_export",
                cmd,
                log_dir,
                {"branch_order": ["location", "shape"], "batch_size": 10000, "number_of_entities": n},
                [full_manifest_path],
            )
        )
    full_embedding_dir = embedding_manifest_dir(full_manifest_path)
    schema = validate_embedding_schema(branch_embedding_dirs["shape"], branch_embedding_dirs["location"], full_embedding_dir, args.geo_dim)

    evaluation_manifest_path = evaluation_dir / "evaluation_manifest.json"
    if not (evaluation_manifest_path.exists() and args.skip_existing):
        cmd = [
            sys.executable,
            str(PROTOTYPE_DIR / "evaluate_geo2vec_embeddings.py"),
            "--shape-embedding-dir",
            str(branch_embedding_dirs["shape"]),
            "--location-embedding-dir",
            str(branch_embedding_dirs["location"]),
            "--full-embedding-dir",
            str(full_embedding_dir),
            "--geometry",
            str(args.geometry),
            "--layer",
            args.layer,
            "--output-dir",
            str(evaluation_dir),
            "--seed",
            str(args.seed),
        ]
        if args.overwrite:
            cmd.append("--overwrite")
        resource_rows.append(
            run_stage(
                "embedding_evaluation",
                cmd,
                log_dir,
                {"number_of_entities": n, "embedding_sets": ["shape", "location", "full_geo2vec"]},
                [evaluation_manifest_path],
            )
        )
    evaluation_manifest = read_json(evaluation_manifest_path)
    if not resource_rows:
        resource_rows = load_existing_resource_rows(log_dir)

    shape_sample = read_json(shape_manifest)
    location_sample = read_json(location_manifest)
    shape_export = read_json(branch_embedding_dirs["shape"] / "embedding_export_manifest.json")
    location_export = read_json(branch_embedding_dirs["location"] / "embedding_export_manifest.json")
    full_export = read_json(full_embedding_dir / "embedding_export_manifest.json")
    problems: list[str] = []
    if not schema["valid"]:
        problems.append("Embedding schema validation failed.")
    if full_export.get("branch_order") != ["location", "shape"]:
        problems.append("Full export branch order is not [location, shape].")
    if full_export.get("contains_handcrafted_geometry_features") is not False:
        problems.append("Full export manifest does not explicitly rule out handcrafted geometry features.")
    if not evaluation_manifest.get("complete"):
        problems.append("Evaluation manifest is not complete.")
    problems_markdown = "\n".join(f"- {p}" for p in problems) if problems else "No blocking problems found in the bounded Gwanak run."
    ready_for_100k = not problems

    run_manifest = {
        "script": Path(__file__).name,
        "complete": True,
        "study_name": STUDY_NAME,
        "start_timestamp": started,
        "end_timestamp": now_iso(),
        "geometry": str(args.geometry),
        "layer": args.layer,
        "building_count": int(n),
        "id_map": str(id_map),
        "shape_sample_manifest": str(shape_manifest),
        "location_sample_manifest": str(location_manifest),
        "shape_checkpoint": str(checkpoints["shape"]),
        "location_checkpoint": str(checkpoints["location"]),
        "shape_embedding_dir": str(branch_embedding_dirs["shape"]),
        "location_embedding_dir": str(branch_embedding_dirs["location"]),
        "full_embedding_dir": str(full_embedding_dir),
        "evaluation_dir": str(evaluation_dir),
        "resource_log_dir": str(log_dir),
        "gpu_static_info": gpu_static_info,
        "branch_order": ["location", "shape"],
        "paper_faithful_geo2vec": True,
        "contains_handcrafted_geometry_features": False,
        "shape_sample_count": int(shape_sample["total_samples"]),
        "location_sample_count": int(location_sample["total_samples"]),
        "shape_embedding_output_size_mb": path_size_mb(branch_embedding_dirs["shape"]),
        "location_embedding_output_size_mb": path_size_mb(branch_embedding_dirs["location"]),
        "full_embedding_output_size_mb": path_size_mb(full_embedding_dir),
        "evaluation_output_size_mb": path_size_mb(evaluation_dir),
        "schema_validation": schema,
        "shape_export": shape_export,
        "location_export": location_export,
        "full_export": full_export,
        "evaluation_manifest": str(evaluation_manifest_path),
        "resource_logs": [str(log_dir / f"{row['stage']}_resource_log.json") for row in resource_rows],
        "experiment_config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "problems_found": problems,
        "problems_found_markdown": problems_markdown,
        "ready_for_100k": bool(ready_for_100k),
    }
    run_manifest_path = run_root / "gwanak_full_geo2vec_pipeline_manifest.json"
    write_json_atomic(run_manifest_path, run_manifest)
    report_path = REPORTS_DIR / f"{report_timestamp}_gwanak_full_geo2vec_pipeline_and_evaluation.md"
    write_report(args, report_path, run_manifest, evaluation_manifest, schema, resource_rows)
    run_manifest["report_path"] = str(report_path)
    write_json_atomic(run_manifest_path, run_manifest)
    print(json.dumps(run_manifest, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
