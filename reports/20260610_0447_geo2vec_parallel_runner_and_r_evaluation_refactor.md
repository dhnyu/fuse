# Geo2Vec Parallel Runner and R Evaluation Refactor

Generated: 2026-06-10 04:47 KST

## 1. Executive Summary

Implemented branch-level two-GPU parallelism for the full Gwanak Geo2Vec workflow and moved the preferred embedding evaluation path to R. The validation used existing Gwanak sample caches and checkpoints; no 100k, 1M, or nationwide runs were started.

Validation status: completed.

## 2. Motivation

The full Geo2Vec representation is paper-faithful only when exported as:

```text
z_E = [z_E^loc, z_E^shp]
```

Shape and location branches are independent training jobs before concatenation, so they can safely run in parallel on separate GPUs without changing the shared-latent-space design inside either branch.

## 3. Branch-Level Parallelism Design

Added `tests/geo2vec_large_scale/run_gwanak_full_geo2vec_parallel.py`.

The runner:

- uses the existing shape and location sample caches;
- trains one persistent model per branch;
- assigns at most one GPU per branch;
- never trains shard-specific independent models;
- exports shape-only, location-only, and full `[location, shape]` embeddings after both branches complete.

## 4. GPU Selection and Fallback Behavior

GPU selection uses one `nvidia-smi` snapshot at startup. The two GPUs with most free VRAM are selected when available.

Validation results:

- Two-GPU branch mode: `parallel_two_gpu`
- Shape assigned GPU: `1`
- Location assigned GPU: `0`
- Single-GPU fallback mode: `sequential_single_gpu_or_cpu`
- Fallback validation assigned both branches to GPU `1`

Manifests:

- `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_parallel_branch_v1/parallel_runner_validation_manifest.json`
- `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_parallel_branch_v1/sequential_fallback_validation_manifest.json`

## 5. Scripts Added or Modified

Added:

- `tests/geo2vec_large_scale/run_gwanak_full_geo2vec_parallel.py`
- `tests/geo2vec_large_scale/build_gwanak_evaluation_split.py`
- `tests/geo2vec_large_scale/evaluate_geo2vec_embeddings.R`

Modified:

- `tests/geo2vec_large_scale/train_global_geo2vec_from_sample_cache.py`
- `tests/geo2vec_large_scale/evaluate_geo2vec_embeddings.py`

## 6. Deterministic Evaluation Split Design

Created:

`/members/dhnyu/fusedata/geo2vec_large_scale/metadata/evaluation_splits/gwanak_building_evaluation_split.parquet`

Columns:

- `building_id`
- `geo2vec_internal_id`
- `split_random`
- `fold_random`
- `split_spatial`
- `fold_spatial`
- `centroid_x`
- `centroid_y`

Metadata:

`/members/dhnyu/fusedata/geo2vec_large_scale/metadata/evaluation_splits/gwanak_building_evaluation_split_metadata.json`

Random split uses `SHA256(seed|building_id)`. Spatial folds use EPSG:5186 centroid quantile bins combined deterministically into five folds.

## 7. R Evaluation Pipeline

Added `tests/geo2vec_large_scale/evaluate_geo2vec_embeddings.R`.

The R evaluator:

- reads embeddings with `arrow`;
- computes geometry proxy labels with `sf`;
- joins deterministic splits;
- evaluates random and spatial splits;
- supports linear regression, ridge via `glmnet`, random forest via `ranger`, and R `xgboost`;
- exports PCA and UMAP coordinates and figures;
- exports nearest-neighbor retrieval tables.

Validated R package availability:

```json
{
  "FNN": true,
  "glmnet": true,
  "ranger": true,
  "uwot": true,
  "xgboost": true
}
```

R evaluation manifest:

`/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_parallel_branch_v1/r_evaluation/r_evaluation_manifest.json`

## 8. Python Evaluation Changes

Python evaluation now records:

- Python xgboost/umap are not required;
- R evaluation is the preferred evaluation path;
- skipped optional Python packages are not pipeline problems.

No Python packages were installed.

## 9. Gwanak Validation Results

Validation used existing Gwanak branch checkpoints and sample caches. The parallel runner concurrently resumed branch checkpoints to validate branch-level process orchestration and GPU assignment without retraining.

Full export remained:

```json
{
  "branch_order": ["location", "shape"],
  "full_geo2vec_dim": 64
}
```

R random-split validation, bounded to `max_model_rows=5000`, produced the expected branch behavior:

| target | model | full_geo2vec | location | shape |
|---|---|---:|---:|---:|
| centroid_x | ranger | 0.9701 | 0.9652 | 0.0500 |
| centroid_y | ranger | 0.9618 | 0.9553 | 0.0228 |
| compactness | ranger | 0.7006 | 0.0322 | 0.7043 |
| perimeter | ranger | 0.0946 | 0.0997 | 0.1415 |
| centroid_x | xgboost | 0.9388 | 0.9362 | 0.0341 |
| centroid_y | xgboost | 0.9303 | 0.9129 | 0.0224 |
| compactness | xgboost | 0.6364 | 0.0418 | 0.6367 |
| perimeter | xgboost | 0.0675 | 0.0848 | 0.1214 |

## 10. Resource Logging Schema

Branch training logs are JSON files under:

`/members/dhnyu/fusedata/geo2vec_large_scale/logs/gwanak_full_geo2vec_parallel_branch_v1`

Each branch log includes:

- branch;
- assigned GPU id;
- `CUDA_VISIBLE_DEVICES`;
- start/end timestamps;
- elapsed seconds;
- process CPU user/system time from `/usr/bin/time -v`;
- max RSS;
- CUDA availability;
- GPU model and total VRAM;
- PyTorch peak allocated/reserved memory from training summary;
- entity count;
- SDF sample count;
- batch size;
- epochs;
- checkpoint path;
- checkpoint file size.

No continuous monitoring or repeated GPU polling is used.

## 11. Remaining Limitations

- This is branch-level parallelism only.
- No shard-level streaming training was added.
- No model is split across shards.
- The R validation run used a bounded model subset for speed; full-data R evaluation is available by omitting `--max-model-rows`.
- CPU fallback is guarded and intended only for small tests.

## 12. Recommended Next Step

Use `run_gwanak_full_geo2vec_parallel.py` as the basis for the next bounded 100k experiment, with the recommended epoch setting from the saturation study, deterministic evaluation splits, and the R evaluator as the required evaluation gate before any 1M or nationwide run.
