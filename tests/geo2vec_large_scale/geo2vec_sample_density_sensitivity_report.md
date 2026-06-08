# Geo2Vec Sample-Density Sensitivity Study

Date: 2026-06-08  
Study: `gwanak_sample_density_sensitivity_v1`  
Dataset: exact Gwanak building geometry from `/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg`, layer `gwanak_buildings`  
Buildings: 38,547  
Training: one `Geo2Vec_Model(n_poly=38547)` and one global entity embedding table per density setting. No shard-specific models were trained.

## Why This Study Was Run

The nationwide engineering runs used `sdf_proto_v1`, which is intentionally sparse and optimized for scalability. The Geo2Vec paper and the external implementation both emphasize adaptive SDF samples around vertices, edges, and uniform space; the paper's sample-count analysis shows downstream performance improving as sampled points increase. Therefore the low-density nationwide setting should be treated as an engineering setting, not as a final quality setting.

I used the recoverable Gwanak building set rather than a national 100k subset because it ties directly to the earlier successful single-global-model experiment and supports random, spatial-block, and dong-holdout validation on the same geometries.

## Density Settings

| density_name | sample_config_version | samples_per_unit | point_sample | uniform_grid | total_samples | samples/building mean | samples/building median | sample range | quantiles |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low | sdf_density_low_v1 | 4 | 1 | 2 | 1013048 | 26.2809 | 25.0000 | 18-232 | p05=20, p25=22, p75=28, p95=37 |
| medium | sdf_density_medium_v1 | 8 | 2 | 4 | 2188751 | 56.7814 | 55.0000 | 41-359 | p05=46, p25=50, p75=60, p95=73 |
| high | sdf_density_high_v1 | 16 | 4 | 6 | 4392924 | 113.9628 | 110.0000 | 85-608 | p05=95, p25=102, p75=121, p95=144 |

The optional very-high setting was skipped for this pass. The high setting already reached a median of 110 samples/building and showed a clear quality trend without stressing storage, CPU memory, or GPU memory.

## Efficiency

| density_name | SDF sec | SDF samples/sec | cache MiB | train sec | train samples/sec | valid L1 | GPU reserved MiB | cpu_rss_mb | peak_maxrss_mb | embedding_output_mb |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low | 10.1496 | 99811.7445 | 14.2362 | 0.7406 | 1899595.3594 | 0.0400 | 108.0000 | 1314.8164 | 1312.8008 | 6.9142 |
| medium | 14.4981 | 150967.9278 | 29.3626 | 1.2988 | 1971075.3464 | 0.0369 | 118.0000 | 1358.9102 | 1349.3125 | 6.9262 |
| high | 23.0579 | 190517.2082 | 51.5609 | 2.3016 | 2038541.1009 | 0.0224 | 112.0000 | 1465.1445 | 1454.1406 | 6.9224 |

SDF generation remained the dominant cost relative to the very small one-epoch training runs. GPU VRAM was not a bottleneck: peak reserved memory stayed around 108-118 MiB for this Gwanak-scale comparison.

## Downstream Validation Summary

Average across all targets and validation schemes:

| density_name | r2_mean | rmse_mean | mae_mean |
| --- | --- | --- | --- |
| high | 0.5024 | 0.3276 | 0.2062 |
| low | 0.1286 | 0.3955 | 0.2469 |
| medium | 0.3317 | 0.3636 | 0.2239 |

Average by validation scheme:

| resampling | density_name | r2_mean | rmse_mean | mae_mean |
| --- | --- | --- | --- | --- |
| dong_holdout | high | 0.4994 | 0.3262 | 0.2078 |
| dong_holdout | low | 0.1222 | 0.3947 | 0.2479 |
| dong_holdout | medium | 0.3314 | 0.3617 | 0.2248 |
| random_split | high | 0.4965 | 0.3328 | 0.2056 |
| random_split | low | 0.1327 | 0.3984 | 0.2465 |
| random_split | medium | 0.3235 | 0.3689 | 0.2244 |
| spatial_block_cv | high | 0.5113 | 0.3238 | 0.2051 |
| spatial_block_cv | low | 0.1310 | 0.3935 | 0.2463 |
| spatial_block_cv | medium | 0.3402 | 0.3603 | 0.2226 |

Spatial block CV R2 by target:

| target | high | low | medium |
| --- | --- | --- | --- |
| bbox_area_ratio | 0.8018 | 0.4197 | 0.6117 |
| compactness | 0.6696 | 0.1189 | 0.4174 |
| elongation | 0.7735 | 0.0308 | 0.5359 |
| log_area | 0.1197 | 0.0321 | 0.0481 |
| log_perimeter | 0.1918 | 0.0535 | 0.0881 |

Dong holdout R2 by target:

| target | high | low | medium |
| --- | --- | --- | --- |
| bbox_area_ratio | 0.7986 | 0.4163 | 0.6092 |
| compactness | 0.6674 | 0.1187 | 0.4151 |
| elongation | 0.7670 | 0.0315 | 0.5393 |
| log_area | 0.0922 | 0.0103 | 0.0229 |
| log_perimeter | 0.1720 | 0.0340 | 0.0706 |

Random split R2 by target:

| target | high | low | medium |
| --- | --- | --- | --- |
| bbox_area_ratio | 0.8063 | 0.4223 | 0.6160 |
| compactness | 0.6627 | 0.1111 | 0.3950 |
| elongation | 0.7181 | 0.0291 | 0.4926 |
| log_area | 0.1112 | 0.0437 | 0.0417 |
| log_perimeter | 0.1843 | 0.0576 | 0.0720 |

## Interpretation

The low engineering density produced about 26 samples/building and performed poorly on shape-sensitive targets. Mean R2 across all downstream validation summaries was 0.129.

The medium density produced about 57 samples/building and improved mean R2 to 0.332. This is close to the previous lightweight Gwanak-style setting and is a much better quality/scalability compromise than the low setting.

The high density produced about 114 samples/building and improved mean R2 to 0.502. The gains from medium to high are large on compactness, elongation, and bbox area ratio, including spatial block CV and dong holdout. The area and perimeter targets improved only modestly, which is plausible because the current Geo2Vec SDF normalization emphasizes shape more than absolute size.

Performance did not saturate at about 24 or 52 samples/building in this study. The measured trend supports the paper's Figure 2 and Figure 3 message: denser adaptive SDF sampling gives the decoder more shape information and improves downstream geometry reconstruction/validation. This study should not be read as proving saturation at 114 samples/building; it only shows that 114 was still better than 57 on this dataset.

## Recommendations

For the 5M engineering stress test, use the medium setting first: `samples_per_unit=8`, `point_sample=2`, `uniform_grid=4`, `sample_config_version=sdf_density_medium_v1`, 8 SDF workers, `Geo_dim=32`, batch size 4096, checkpoint retention keep latest 3. It roughly doubles cache/training volume relative to low while giving a large validation improvement.

For final Korea-scale production embeddings, do not use the low engineering setting unless resource constraints dominate quality. The high setting, `samples_per_unit=16`, `point_sample=4`, `uniform_grid=6`, is the current quality-oriented recommendation, subject to a 300k or 1M high-density confirmation before full nationwide production.

Before full Korea, run one bounded high-density engineering check at 300k or 1M to confirm SDF throughput, checkpoint size, and downstream validation behavior at a larger national subset. A very-high setting around 150-200 samples/building should only be tested if high-density quality appears unsaturated and storage/time budgets remain acceptable.

## Outputs

- Study manifest: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_sample_density_sensitivity_v1/sample_density_sensitivity_manifest.json`
- Efficiency summary: `/members/dhnyu/fusedata/geo2vec_large_scale/reports/gwanak_sample_density_sensitivity_v1/density_efficiency_summary.parquet`
- Downstream validation summary: `/members/dhnyu/fusedata/geo2vec_large_scale/reports/gwanak_sample_density_sensitivity_v1/density_xgboost_validation_summary.parquet`
- Downstream validation details: `/members/dhnyu/fusedata/geo2vec_large_scale/reports/gwanak_sample_density_sensitivity_v1/density_xgboost_validation_results.parquet`
- Embeddings: `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/gwanak_sample_density_sensitivity_v1`
- Sample caches: `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/gwanak_sample_density_sensitivity_v1`
- Training runs: `/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/gwanak_sample_density_sensitivity_v1`

## Caveats

This is a one-epoch comparison intended to isolate sample-density effects under the current prototype training budget. Absolute downstream scores may change with more epochs or tuned decoder settings, but the low < medium < high ordering is consistent across the strict validation schemes used here.
