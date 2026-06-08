# Geo2Vec CPU vs GPU Benchmark Report

Generated: 2026-06-08 02:24:59 KST

## Purpose

This benchmark compares CPU and GPU practicality for a single global GeoNeuralRepresentation / Geo2Vec shape-only model on Gwanak-gu building footprints. The full prepared input contains 38,547 valid geometries; this workflow deliberately uses controlled samples only.

## Environment

- Python: `3.14.0 | packaged by conda-forge | (main, Oct 22 2025, 23:24:08) [GCC 14.3.0]`
- Python executable: `/members/dhnyu/.conda/envs/rgeo/bin/python`
- CUDA_VISIBLE_DEVICES: `1`
- torch: `2.12.0+cu130`
- CUDA available: `True`
- torch CUDA version: `13.0`
- GPU: `NVIDIA RTX A6000`
- GPU total memory GB: `47.40`
- CPU logical / physical cores: `48` / `24`
- RAM GB: `755.00`
- Input: `/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg`
- External repo: `/members/dhnyu/fuse_external/GeoNeuralRepresentation`

## Controlled Settings

- Shape-only learning: `shape_learning=True`, `location_learning=False`
- Geo_dim: `32`
- Epochs: `1`
- Batch size: `4096`
- Shape model: hidden size `128`, layers `4`, frequencies `4`
- Shape sampling: samples per unit `8`, point samples `2`, uniform samples `4`, bandwidth `0.08`

Controllability notes:

- `list2vec` exposes `Geo_dim` and `num_epoch` directly.
- Sampling, batch size, and shape model settings are controllable through an argparse-like `args` namespace.
- The external shape branch reads `args.device` when constructing the PyTorch device; `args.device_shape` exists but is not used for device selection in `list2vec`.
- DataLoader workers are hard-coded to `0` inside `list2vec`; `num_workers` can be supplied but is not used there.
- For CPU runs with CUDA-visible PyTorch, the wrapper temporarily forces the external `DataLoader` calls to `pin_memory=False` so CPU execution does not allocate CUDA pinned memory.

## Timing Results

| device   |   sample_size |   actual_geometries_used | succeeded   |   elapsed_seconds |   average_training_samples_per_entity | embedding_shape   | error_message   |
|:---------|--------------:|-------------------------:|:------------|------------------:|--------------------------------------:|:------------------|:----------------|
| cpu      |          1000 |                     1000 | True        |              2.55 |                                 51.28 | 1000x32           |                 |
| cuda     |          1000 |                     1000 | True        |              2.24 |                                 51.28 | 1000x32           |                 |
| cpu      |          5000 |                     5000 | True        |              4.65 |                                 53.12 | 5000x32           |                 |
| cuda     |          5000 |                     5000 | True        |              3.56 |                                 53.12 | 5000x32           |                 |
| cpu      |         10000 |                    10000 | True        |              7.69 |                                 52.69 | 10000x32          |                 |
| cuda     |         10000 |                    10000 | True        |              5.53 |                                 52.69 | 10000x32          |                 |

## GPU Memory

|   sample_size | succeeded   |   peak_gpu_memory_allocated_mb |   peak_gpu_memory_reserved_mb | error_message   |
|--------------:|:------------|-------------------------------:|------------------------------:|:----------------|
|          1000 | True        |                          59.82 |                            68 |                 |
|          5000 | True        |                          61.81 |                            70 |                 |
|         10000 | True        |                          65.15 |                            88 |                 |

## Failures Or OOMs

_No rows._

## Interpretation

- CPU completed the 5,000-building benchmark, so it avoids the VRAM failure mode. A full single-model run may be possible, but runtime would scale materially beyond this test.
- GPU completed the 5,000-building benchmark with the lightweight settings.
- The previous full GPU run failed at 38,547 buildings, so chunking remains the safer full-scale path unless a new single-model GPU run uses substantially lighter sampling/model settings.
- CPU removes the VRAM ceiling but does not remove the sampling and training memory/time cost; extrapolate from the successful CPU sample before launching a full single-model run.

## Recommendation

For the next full-scale experiment, keep the chunked production workflow as the reliable baseline. If a single global model is still needed, run a guarded CPU full experiment first with the same lightweight settings and a wall-time monitor, then try GPU only after further reducing sampling or batch/model size.

## Outputs

- Results parquet: `/members/dhnyu/fusedata/gwanak_test/validation/geo2vec_cpu_gpu_benchmark_results.parquet`
- Successful embedding parquet files are listed in the result table under `output_embedding_path`.
