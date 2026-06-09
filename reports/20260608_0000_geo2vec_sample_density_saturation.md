# Geo2Vec Sample-Density Saturation Study

Date: 2026-06-08  
Study: `gwanak_sample_density_saturation_v1`  
Dataset: exact recoverable Gwanak buildings from `/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg`, layer `gwanak_buildings`  
Buildings: 38,547  
Workers: 40 SDF workers  
Training: one epoch, `Geo_dim=32`, batch size 4096, one `Geo2Vec_Model(n_poly=38547)` and one global embedding table per density.

## Purpose

The previous density study showed that the low engineering setting around 26 samples/building was not quality-saturated. This saturation study extends the same exact Gwanak setup to approximately 200, 400, 800, 1,600, 3,200, and 5,000 SDF samples/building to identify where downstream shape-embedding quality begins to flatten.

## Comparison With Previous Study

| study | density_name | mean_samples_per_building | total_samples | r2_mean | rmse_mean | mae_mean |
| --- | --- | --- | --- | --- | --- | --- |
| previous sensitivity | low | 26.2809 | 1,013,048 | 0.1286 | 0.3955 | 0.2469 |
| previous sensitivity | medium | 56.7814 | 2,188,751 | 0.3317 | 0.3636 | 0.2239 |
| previous sensitivity | high | 113.9628 | 4,392,924 | 0.5024 | 0.3276 | 0.2062 |
| saturation | sat_0200 | 197.8847 | 7,627,862 | 0.5778 | 0.3076 | 0.1969 |
| saturation | sat_0400 | 403.9249 | 15,570,094 | 0.6212 | 0.2954 | 0.1890 |
| saturation | sat_0800 | 799.8122 | 30,830,359 | 0.6291 | 0.2924 | 0.1877 |
| saturation | sat_1600 | 1613.2257 | 62,185,010 | 0.6426 | 0.2882 | 0.1844 |
| saturation | sat_3200 | 3213.5638 | 123,873,244 | 0.6543 | 0.2847 | 0.1825 |
| saturation | sat_5000 | 5026.2705 | 193,747,650 | 0.6616 | 0.2813 | 0.1807 |

The previous high setting at about 114 samples/building reached mean R2 0.502. The first new saturation point at about 198 samples/building reached mean R2 0.578, so the earlier curve had not saturated.

## Calibration

A 1,000-building calibration pass was run before the full sweep. The chosen parameters were close to the requested target densities, so the same candidate settings were used for the full 38,547-building run.

## Density Parameters

| density_name | target_samples_per_building | samples_per_unit | point_sample | uniform_grid | calibration_mean_samples_per_building | total_samples | mean_samples_per_building | median_samples_per_building | quantiles |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sat_0200 | 200 | 28 | 7 | 8 | 199.0280 | 7,627,862 | 197.8847 | 192.0000 | p05=166, p25=178, p75=210, p95=248 |
| sat_0400 | 400 | 60 | 15 | 11 | 406.1620 | 15,570,094 | 403.9249 | 392.0000 | p05=336, p25=362, p75=429, p95=508 |
| sat_0800 | 800 | 116 | 29 | 16 | 804.0570 | 30,830,359 | 799.8122 | 777.0000 | p05=671, p25=719, p75=847, p95=998 |
| sat_1600 | 1,600 | 232 | 58 | 23 | 1621.6600 | 62,185,010 | 1613.2257 | 1569.0000 | p05=1356, p25=1453, p75=1707, p95=2007 |
| sat_3200 | 3,200 | 470 | 117 | 32 | 3230.4690 | 123,873,244 | 3213.5638 | 3124.0000 | p05=2696, p25=2891, p75=3403, p95=4005 |
| sat_5000 | 5,000 | 734 | 184 | 40 | 5052.8350 | 193,747,650 | 5026.2705 | 4886.0000 | p05=4215, p25=4521, p75=5322, p95=6267 |

## Efficiency

| density_name | sample_generation_seconds | sample_generation_samples_per_second | sample_cache_mb | training_elapsed_seconds | mean_training_samples_per_second | cpu_rss_mb | peak_maxrss_mb | peak_gpu_allocated_mb | peak_gpu_reserved_mb | embedding_output_mb |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sat_0200 | 18.3774 | 415066.6203 | 78.7862 | 3.7784 | 2077196.8528 | 1538.3672 | 1529.6875 | 78.6885 | 116.0000 | 6.9163 |
| sat_0400 | 28.3364 | 549473.9822 | 162.6964 | 7.4564 | 2104051.9069 | 1703.0352 | 1795.8008 | 78.6885 | 116.0000 | 6.9167 |
| sat_0800 | 47.6901 | 646472.8048 | 316.0189 | 14.8592 | 2125368.7776 | 2003.4141 | 2163.1406 | 78.6885 | 120.0000 | 6.9180 |
| sat_1600 | 88.0367 | 706352.9916 | 633.5461 | 30.9061 | 2138879.8867 | 2401.0859 | 2853.6367 | 78.6885 | 112.0000 | 6.9221 |
| sat_3200 | 163.5724 | 757299.1463 | 1278.8582 | 63.1284 | 2151819.0111 | 2801.3242 | 4222.5742 | 78.6885 | 116.0000 | 6.9262 |
| sat_5000 | 250.7334 | 772723.6080 | 1996.5185 | 100.8166 | 2150242.7227 | 3071.2539 | 5673.5469 | 78.6885 | 118.0000 | 6.9250 |

SDF generation scaled from 18.4 seconds at about 198 samples/building to 250.7 seconds at about 5,026 samples/building. The 5,000-density cache was 193.7M rows and about 2.00 GiB compressed. GPU memory was not a bottleneck; peak reserved memory stayed at or below 120 MiB in this prototype. CPU/RAM remained safe; peak RSS was about 7.0 GB during generation and 5.7 GB during the largest training run.

## Validation Summary

Average across all targets and validation schemes:

| density_name | mean_samples_per_building | r2_mean | rmse_mean | mae_mean |
| --- | --- | --- | --- | --- |
| sat_0200 | 197.8847 | 0.5778 | 0.3076 | 0.1969 |
| sat_0400 | 403.9249 | 0.6212 | 0.2954 | 0.1890 |
| sat_0800 | 799.8122 | 0.6291 | 0.2924 | 0.1877 |
| sat_1600 | 1613.2257 | 0.6426 | 0.2882 | 0.1844 |
| sat_3200 | 3213.5638 | 0.6543 | 0.2847 | 0.1825 |
| sat_5000 | 5026.2705 | 0.6616 | 0.2813 | 0.1807 |

Average by validation scheme:

| resampling | density_name | mean_samples_per_building | r2_mean | rmse_mean | mae_mean |
| --- | --- | --- | --- | --- | --- |
| dong_holdout | sat_0200 | 197.8847 | 0.5728 | 0.3073 | 0.1986 |
| dong_holdout | sat_0400 | 403.9249 | 0.6188 | 0.2939 | 0.1905 |
| dong_holdout | sat_0800 | 799.8122 | 0.6260 | 0.2913 | 0.1894 |
| dong_holdout | sat_1600 | 1613.2257 | 0.6394 | 0.2870 | 0.1863 |
| dong_holdout | sat_3200 | 3213.5638 | 0.6493 | 0.2844 | 0.1848 |
| dong_holdout | sat_5000 | 5026.2705 | 0.6590 | 0.2800 | 0.1823 |
| random_split | sat_0200 | 197.8847 | 0.5751 | 0.3115 | 0.1962 |
| random_split | sat_0400 | 403.9249 | 0.6161 | 0.3006 | 0.1884 |
| random_split | sat_0800 | 799.8122 | 0.6273 | 0.2962 | 0.1868 |
| random_split | sat_1600 | 1613.2257 | 0.6400 | 0.2927 | 0.1835 |
| random_split | sat_3200 | 3213.5638 | 0.6519 | 0.2885 | 0.1816 |
| random_split | sat_5000 | 5026.2705 | 0.6566 | 0.2865 | 0.1801 |
| spatial_block_cv | sat_0200 | 197.8847 | 0.5854 | 0.3041 | 0.1959 |
| spatial_block_cv | sat_0400 | 403.9249 | 0.6289 | 0.2918 | 0.1880 |
| spatial_block_cv | sat_0800 | 799.8122 | 0.6341 | 0.2897 | 0.1868 |
| spatial_block_cv | sat_1600 | 1613.2257 | 0.6484 | 0.2850 | 0.1836 |
| spatial_block_cv | sat_3200 | 3213.5638 | 0.6616 | 0.2810 | 0.1813 |
| spatial_block_cv | sat_5000 | 5026.2705 | 0.6691 | 0.2774 | 0.1796 |

## R2 By Target And Scheme

### random_split

| target | sat_0200 | sat_0400 | sat_0800 | sat_1600 | sat_3200 | sat_5000 |
| --- | --- | --- | --- | --- | --- | --- |
| bbox_area_ratio | 0.8822 | 0.9193 | 0.9292 | 0.9311 | 0.9340 | 0.9401 |
| compactness | 0.7633 | 0.8314 | 0.8368 | 0.8554 | 0.8740 | 0.8716 |
| elongation | 0.8058 | 0.8134 | 0.8414 | 0.8177 | 0.8255 | 0.8380 |
| log_area | 0.1611 | 0.1999 | 0.2066 | 0.2306 | 0.2519 | 0.2516 |
| log_perimeter | 0.2628 | 0.3164 | 0.3223 | 0.3654 | 0.3741 | 0.3817 |

### spatial_block_cv

| target | sat_0200 | sat_0400 | sat_0800 | sat_1600 | sat_3200 | sat_5000 |
| --- | --- | --- | --- | --- | --- | --- |
| bbox_area_ratio | 0.8803 | 0.9183 | 0.9253 | 0.9294 | 0.9364 | 0.9392 |
| compactness | 0.7729 | 0.8380 | 0.8390 | 0.8522 | 0.8774 | 0.8736 |
| elongation | 0.8522 | 0.8614 | 0.8691 | 0.8549 | 0.8639 | 0.8777 |
| log_area | 0.1611 | 0.2052 | 0.2113 | 0.2403 | 0.2518 | 0.2627 |
| log_perimeter | 0.2605 | 0.3213 | 0.3260 | 0.3653 | 0.3785 | 0.3922 |

### dong_holdout

| target | sat_0200 | sat_0400 | sat_0800 | sat_1600 | sat_3200 | sat_5000 |
| --- | --- | --- | --- | --- | --- | --- |
| bbox_area_ratio | 0.8789 | 0.9166 | 0.9240 | 0.9287 | 0.9350 | 0.9376 |
| compactness | 0.7726 | 0.8361 | 0.8385 | 0.8519 | 0.8755 | 0.8736 |
| elongation | 0.8475 | 0.8614 | 0.8705 | 0.8576 | 0.8618 | 0.8737 |
| log_area | 0.1325 | 0.1811 | 0.1859 | 0.2138 | 0.2177 | 0.2365 |
| log_perimeter | 0.2327 | 0.2989 | 0.3112 | 0.3447 | 0.3566 | 0.3735 |

## Saturation Analysis

Mean R2 versus actual samples/building:

| mean_samples_per_building | density_name | r2_mean |
| --- | --- | --- |
| 197.8847 | sat_0200 | 0.5778 |
| 403.9249 | sat_0400 | 0.6212 |
| 799.8122 | sat_0800 | 0.6291 |
| 1613.2257 | sat_1600 | 0.6426 |
| 3213.5638 | sat_3200 | 0.6543 |
| 5026.2705 | sat_5000 | 0.6616 |

Marginal gain:

| density_name | mean_samples_per_building | r2_mean | marginal_r2_gain | r2_gain_per_1000_samples |
| --- | --- | --- | --- | --- |
| sat_0200 | 197.8847 | 0.5778 |  |  |
| sat_0400 | 403.9249 | 0.6212 | 0.0435 | 0.2110 |
| sat_0800 | 799.8122 | 0.6291 | 0.0079 | 0.0199 |
| sat_1600 | 1613.2257 | 0.6426 | 0.0135 | 0.0166 |
| sat_3200 | 3213.5638 | 0.6543 | 0.0117 | 0.0073 |
| sat_5000 | 5026.2705 | 0.6616 | 0.0073 | 0.0040 |

Best observed mean R2 was 0.6616 at `sat_5000` with 5026.3 samples/building. The smallest density reaching 95% of the best observed mean R2 (0.6285) was `sat_0800` at 799.8 samples/building. The smallest density reaching 99% of the best observed mean R2 (0.6549) was `sat_5000` at 5026.3 samples/building.

The curve is clearly flattening after about 800-1,600 samples/building, but it has not fully saturated by 5,000 samples/building under this one-epoch setup. Marginal gain from 3,214 to 5,026 samples/building was +0.0073 mean R2, which is real but small relative to the additional SDF generation and cache volume.

## Recommendation

For engineering stress testing at 5M buildings, use the 800-sample setting first: `samples_per_unit=116`, `point_sample=29`, `uniform_grid=16`, 8 or 40 workers depending on the goal of the run. It reaches 95% of the best observed mean R2 while keeping cache volume far below the 3,200 and 5,000 settings.

For quality-oriented production embeddings, use the 1,600-sample setting as the current practical default: `samples_per_unit=232`, `point_sample=58`, `uniform_grid=23`. It gives better quality than 800 with a manageable cache multiplier, and it is a stronger paper-inspired adaptive SDF setting than the earlier engineering densities.

The 5,000-sample setting is not the default recommendation. It is worthwhile only if the final objective explicitly prioritizes the last few R2 points and the nationwide storage/sampling budget can absorb roughly 5,000 samples/building. A lower density, especially 1,600 or 3,200, achieves nearly the same validation quality at materially lower cost.

## Validation And Safety Checks

| density_name | cache_valid | n_poly | global_steps | embedding_rows | embedding_finite | checkpoint_retention_keep |
| --- | --- | --- | --- | --- | --- | --- |
| sat_0200 | True |  | 1,682 | 38,547 | True | 2 |
| sat_0400 | True |  | 3,426 | 38,547 | True | 2 |
| sat_0800 | True |  | 6,779 | 38,547 | True | 2 |
| sat_1600 | True |  | 13,668 | 38,547 | True | 2 |
| sat_3200 | True |  | 27,224 | 38,547 | True | 2 |
| sat_5000 | True |  | 42,574 | 38,547 | True | 2 |

No shard-specific models were trained. Each density has one training run directory and one exported 32D embedding table with 38,547 finite rows.

## Caveats

This is a one-epoch comparison designed to isolate sample-density effects. Additional epochs could shift the absolute scores and may change where the curve appears to saturate.

The study is Gwanak-only. It is useful because it uses the exact recoverable Gwanak geometry from the earlier experiment, but nationwide morphology may have different complexity.

The current SDF normalization is shape-oriented. That helps compactness, elongation, and bbox-area-ratio validation more directly than absolute log area or log perimeter, so area/perimeter metrics should be interpreted with that limitation in mind.

## Outputs

- Study manifest: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_sample_density_saturation_v1/sample_density_saturation_manifest.json`
- Efficiency summary: `/members/dhnyu/fusedata/geo2vec_large_scale/reports/gwanak_sample_density_saturation_v1/density_efficiency_summary.parquet`
- Validation summary: `/members/dhnyu/fusedata/geo2vec_large_scale/reports/gwanak_sample_density_saturation_v1/density_xgboost_validation_summary.parquet`
- Validation details: `/members/dhnyu/fusedata/geo2vec_large_scale/reports/gwanak_sample_density_saturation_v1/density_xgboost_validation_results.parquet`
- Quantiles: `/members/dhnyu/fusedata/geo2vec_large_scale/reports/gwanak_sample_density_saturation_v1/sample_count_quantiles.parquet`
- Sample caches: `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/gwanak_sample_density_saturation_v1`
- Training runs: `/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/gwanak_sample_density_saturation_v1`
- Embeddings: `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/gwanak_sample_density_saturation_v1`
