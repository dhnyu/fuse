# Gwanak Geo2Vec Scalability and Validation Report

Generated: 2026-06-08 02:55:05 KST

## Summary

The full Gwanak single-model lightweight run is methodologically preferable to the previous chunked output because all 38,547 buildings share one latent space. The observed GPU memory was tiny relative to the available RTX A6000 capacity, but CPU RAM and sample materialization still scale with entity count and sampled points.

## GPU Memory Capacity

|   gpu_id | name             |   total_memory_mb |   used_memory_mb |   free_memory_mb |
|---------:|:-----------------|------------------:|-----------------:|-----------------:|
|        0 | NVIDIA RTX A6000 |             49140 |            40911 |             7632 |
|        1 | NVIDIA RTX A6000 |             49140 |                3 |            48539 |

The single-model metadata records `torch.cuda.max_memory_allocated()` and `torch.cuda.max_memory_reserved()`. Those are peak PyTorch allocator measurements for this process, not the physical capacity of the GPU. Total and currently free GPU memory come from `nvidia-smi`, which is system-level state and can change as other processes start or stop.

## Parameter Sensitivity

- `Geo_dim`: increases embedding table size, optimizer state, output file size, and usually model input width. CPU/GPU memory and storage increase roughly linearly with dimension.
- `batch_size`: primarily affects GPU activation memory per step and may affect speed. It does not change output size or total sampled points.
- `hidden_size_shape`: increases neural network parameter and activation memory, and can increase runtime.
- `num_layers_shape`: increases model depth, activation memory, and runtime.
- `num_freqs_shape`: increases positional encoding width, which increases model input width, memory, and runtime.
- `samples_perUnit_shape`: increases edge-based SDF samples; raises CPU RAM, sampling time, training time, and DataLoader tensor size.
- `point_sample_shape`: increases vertex-neighborhood samples; raises CPU RAM and runtime.
- `uniformed_sample_perUnit_shape`: contributes a square grid per entity, so impact is approximately quadratic in this value.
- `num_epoch`: increases training runtime roughly linearly, with little effect on peak memory.
- `num_process`: can speed sampling but raises multiprocessing overhead and transient CPU memory pressure.

### 5,000-Building Parameter Sweep

| name            |   sample_size |   Geo_dim |   batch_size |   hidden_size_shape |   num_layers_shape |   num_freqs_shape |   samples_perUnit_shape |   point_sample_shape |   uniformed_sample_perUnit_shape |   num_epoch | succeeded   |   elapsed_seconds |   average_training_samples_per_entity |   peak_gpu_memory_allocated_mb |   peak_gpu_memory_reserved_mb |   peak_process_maxrss_mb | embedding_shape   |
|:----------------|--------------:|----------:|-------------:|--------------------:|-------------------:|------------------:|------------------------:|---------------------:|---------------------------------:|------------:|:------------|------------------:|--------------------------------------:|-------------------------------:|------------------------------:|-------------------------:|:------------------|
| baseline_32d    |          5000 |        32 |         4096 |                 128 |                  4 |                 4 |                       8 |                    2 |                                4 |           1 | True        |             4.325 |                                53.115 |                         61.809 |                            70 |                  1382.86 | 5000x32           |
| geo_dim_64      |          5000 |        64 |         4096 |                 128 |                  4 |                 4 |                       8 |                    2 |                                4 |           1 | True        |             4.309 |                                53.115 |                         67.506 |                            90 |                  1384.94 | 5000x64           |
| batch_8192      |          5000 |        32 |         8192 |                 128 |                  4 |                 4 |                       8 |                    2 |                                4 |           1 | True        |             4.291 |                                53.115 |                        102.746 |                           132 |                  1379.52 | 5000x32           |
| hidden_256      |          5000 |        32 |         4096 |                 256 |                  4 |                 4 |                       8 |                    2 |                                4 |           1 | True        |             4.305 |                                53.115 |                        103.004 |                           138 |                  1382.77 | 5000x32           |
| layers_8        |          5000 |        32 |         4096 |                 128 |                  8 |                 4 |                       8 |                    2 |                                4 |           1 | True        |             4.391 |                                53.115 |                         91.051 |                           112 |                  1383.56 | 5000x32           |
| freqs_8         |          5000 |        32 |         4096 |                 128 |                  4 |                 8 |                       8 |                    2 |                                4 |           1 | True        |             4.342 |                                53.115 |                         62.742 |                            90 |                  1385.44 | 5000x32           |
| sampling_medium |          5000 |        32 |         4096 |                 128 |                  4 |                 4 |                      16 |                    4 |                                5 |           1 | True        |             5.427 |                                95.376 |                         61.809 |                            78 |                  1412.5  | 5000x32           |
| epoch_2         |          5000 |        32 |         4096 |                 128 |                  4 |                 4 |                       8 |                    2 |                                4 |           2 | True        |             4.604 |                                53.115 |                         61.809 |                            70 |                  1387.42 | 5000x32           |

## Scalability Estimates

| stage      |   buildings |   sampled_points_est |   runtime_min_linear_est |   rss_gb_linear_est |   parquet_gb_32d_est |
|:-----------|------------:|---------------------:|-------------------------:|--------------------:|---------------------:|
| 50,000     |       50000 |              2600166 |                    0.805 |               2.066 |                0.01  |
| 100,000    |      100000 |              5200332 |                    1.61  |               4.132 |                0.02  |
| 300,000    |      300000 |             15600996 |                    4.829 |              12.395 |                0.061 |
| 1,000,000  |     1000000 |             52003320 |                   16.095 |              41.317 |                0.203 |
| 14,388,938 |    14388938 |            748272556 |                  231.593 |             594.505 |                2.921 |

Gwanak succeeded at 38,547 buildings. No prepared Seoul building subset was found, but the nationwide VWorld building file exists with about 14.39M features. Korea-scale single-model training should not be attempted directly from the Gwanak result; staged samples are required.

Recommended stages: 50k and 100k with conservative lightweight settings; 300k only if RSS and sampling time remain linear; 1M only as a controlled overnight/global-memory test; Seoul full after Seoul boundaries are materialized; Korea sampled before any Korea full attempt; Korea full only if a 1M run shows comfortable RAM/GPU margins and runtime.

Safe starting settings for all stages: `Geo_dim=32`, `hidden_size=128`, `num_layers=4`, `num_freqs=4`, `batch_size=4096`, `samples_perUnit_shape=8`, `point_sample_shape=2`, `uniformed_sample_perUnit_shape=4`, `num_epoch=1`. For 300k+ consider `batch_size=2048` and fewer `num_process` workers if CPU RAM spikes.

## File Integrity vs Downstream Validation

File integrity checks prove only that the parquet has the expected rows, IDs, dimensions, and finite values. They do not prove that embeddings encode meaningful geometry. Downstream validation should test whether embeddings predict shape metrics, form interpretable clusters, and show reasonable spatial or administrative coherence.

### Downstream Geometry Prediction

| embedding        | target          | model   |    r2 |   mae |
|:-----------------|:----------------|:--------|------:|------:|
| chunked_64d      | bbox_area_ratio | rf_100  | 0.292 | 0.093 |
| chunked_64d      | compactness     | rf_100  | 0.198 | 0.059 |
| chunked_64d      | elongation      | rf_100  | 0.335 | 0.171 |
| chunked_64d      | log_area        | rf_100  | 0.013 | 0.59  |
| chunked_64d      | log_perimeter   | rf_100  | 0.024 | 0.31  |
| single_model_32d | bbox_area_ratio | rf_100  | 0.723 | 0.052 |
| single_model_32d | compactness     | rf_100  | 0.604 | 0.042 |
| single_model_32d | elongation      | rf_100  | 0.774 | 0.097 |
| single_model_32d | log_area        | rf_100  | 0.121 | 0.58  |
| single_model_32d | log_perimeter   | rf_100  | 0.19  | 0.305 |

### Cluster Morphology

| embedding        |   cluster_k10 |     n |   median_log_area |   median_compactness |   median_elongation |   median_bbox_area_ratio |
|:-----------------|--------------:|------:|------------------:|---------------------:|--------------------:|-------------------------:|
| single_model_32d |             1 |  2521 |             4.59  |                0.751 |               1.235 |                    0.829 |
| single_model_32d |             2 |  6189 |             4.57  |                0.732 |               1.073 |                    0.528 |
| single_model_32d |             3 |  3826 |             4.587 |                0.705 |               1.411 |                    0.709 |
| single_model_32d |             4 |  4949 |             4.496 |                0.748 |               1.063 |                    0.509 |
| single_model_32d |             5 |  5044 |             4.587 |                0.71  |               1.154 |                    0.563 |
| single_model_32d |             6 |  2479 |             4.636 |                0.592 |               1.72  |                    0.598 |
| single_model_32d |             7 |  3824 |             4.576 |                0.748 |               1.149 |                    0.717 |
| single_model_32d |             8 |  1858 |             4.613 |                0.605 |               1.747 |                    0.606 |
| single_model_32d |             9 |  3974 |             4.615 |                0.701 |               1.32  |                    0.643 |
| single_model_32d |            10 |  3883 |             4.578 |                0.753 |               1.08  |                    0.732 |
| chunked_64d      |             1 |  2205 |             4.529 |                0.717 |               1.146 |                    0.546 |
| chunked_64d      |             2 |  9968 |             4.572 |                0.719 |               1.175 |                    0.578 |
| chunked_64d      |             3 |  1122 |             4.587 |                0.716 |               1.357 |                    0.765 |
| chunked_64d      |             4 |  1001 |             4.551 |                0.696 |               1.435 |                    0.704 |
| chunked_64d      |             5 |  1727 |             4.628 |                0.725 |               1.271 |                    0.736 |
| chunked_64d      |             6 |   892 |             4.616 |                0.706 |               1.519 |                    0.784 |
| chunked_64d      |             7 | 16794 |             4.577 |                0.728 |               1.134 |                    0.619 |
| chunked_64d      |             8 |   822 |             4.442 |                0.697 |               1.48  |                    0.742 |
| chunked_64d      |             9 |  1802 |             4.646 |                0.71  |               1.139 |                    0.528 |
| chunked_64d      |            10 |  2214 |             4.567 |                0.719 |               1.107 |                    0.52  |

## Single-Model vs Chunked Comparison

- Single-model rows: `38547`; dimension: `32`; runtime seconds: `37.225385665893555`; peak GPU allocated MB: `78.98291015625`; validation: `True`.
- Chunked rows: `38547`; dimension: `64`; runtime seconds: `39.7507541179657`; chunks: `8`; validation was confirmed by the earlier validation report.
- Building ID sets match for all 38,547 buildings.
- Direct vector comparison is not meaningful: chunked vectors come from separate latent spaces and also use 64 dimensions, while the new single-model vectors use one global 32-dimensional space.
- Downstream comparisons are meaningful because both embeddings are evaluated against the same original building metrics.

## Recommendations

Use the single-model lightweight Gwanak embedding as the preferred Gwanak shape embedding. Next, run 50k and 100k deterministic samples from the nationwide building GeoPackage before preparing a Seoul full run. Keep the chunked output only as an experimental baseline unless anchor alignment is added.

## Outputs

- Parameter sweep: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_parameter_sweep_results.parquet`
- Downstream validation: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_downstream_validation_single_vs_chunked.parquet`
- Cluster morphology: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_cluster_morphology_single_vs_chunked.parquet`
- GPU status JSON: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_gpu_status.json`
