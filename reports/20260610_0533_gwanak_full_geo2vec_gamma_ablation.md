# Gwanak Full Geo2Vec code_reg_weight / Gamma Ablation

## 1. Executive Summary

This bounded Gwanak-only ablation evaluated four latent regularization settings for the paper-faithful full Geo2Vec representation `z_E = [z_E^loc, z_E^shp]` with `Geo_dim=32` per branch and epoch 10. Existing Gwanak id maps and SDF sample caches were reused; no 100k, 1M, or nationwide runs were started.

Recommendation: use **B paper-like (shape `code_reg_weight=1.0`, location `code_reg_weight=0.0`)** for the next 100k experiment. It is closest to the external GeoNeuralRepresentation branch defaults and improved mean selected spatial full-embedding R2 over the current controlled setting from **0.6874 to 0.7013** with ranger and **0.7185 to 0.7281** with xgboost. The largest gains were on spatial-split area and perimeter, while compactness and centroid recovery remained essentially unchanged.

## 2. Why code_reg_weight / gamma matters

`code_reg_weight` controls the latent-code regularization term during branch training. It changes the pressure on learned entity codes without changing the Geo2Vec representation itself. In this study it is treated as a training hyperparameter only; geometry proxies such as area, perimeter, compactness, aspect ratio, vertices, and centroids were used only by the evaluator and were not added to embeddings.

## 3. External GeoNeuralRepresentation default comparison

The optimized FUSE trainer had been using a controlled setting of `0.1` for both shape and location branches. The external GeoNeuralRepresentation defaults appear branch-specific: location regularization `0.0`, shape regularization `1.0`. This ablation directly compared:

| Setting | Shape code_reg_weight | Location code_reg_weight | Notes |
|---|---:|---:|---|
| A current controlled | 0.1 | 0.1 | Existing epoch-10 checkpoint reused. |
| B paper-default-like | 1.0 | 0.0 | Closest branch-specific external default. |
| C no latent regularization | 0.0 | 0.0 | Removes latent regularization pressure. |
| D mixed | 0.1 | 0.0 | Keeps current shape value, removes location regularization. |

## 4. Experimental Design

Dataset: Gwanak buildings, 38,547 entities. Embeddings: shape-only 32d, location-only 32d, full Geo2Vec 64d with branch order `[location, shape]`. Epochs were fixed at 10. Evaluation used the deterministic Gwanak random and EPSG:5186 spatial split file.

The R evaluator ran with `--max-model-rows 0`, `--nthreads-xgboost 32`, and `--nthreads-umap 32`. Available R optional packages were: `ranger=true, xgboost=true, uwot=true, glmnet=true, FNN=true`.

## 5. Reused Inputs and Sample Caches

- Id map: `/members/dhnyu/fusedata/geo2vec_large_scale/id_maps/gwanak_full_geo2vec_paper_faithful_v1/gwanak_buildings_geo2vec_global_id_map.parquet`
- Shape sample cache manifest: `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/gwanak_full_geo2vec_paper_faithful_v1/korea_geo2vec_shape_samples_38547_sdf_gwanak_full_geo2vec_0200_v1/manifest.json`
- Location sample cache manifest: `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/gwanak_full_geo2vec_paper_faithful_v1/korea_geo2vec_location_samples_38547_sdf_gwanak_full_geo2vec_0200_v1/manifest.json`
- Evaluation split: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/evaluation_splits/gwanak_building_evaluation_split.parquet`
- Sample caches regenerated: `False`
- Larger-scale runs started: `False`

## 6. Training Configuration

All settings used the same Gwanak buildings, id map, SDF sample caches, seed, architecture, batch configuration, epoch count, and deterministic evaluation split. GPU assignment snapshot selected shape on GPU `1` and location on GPU `0` when parallel branch training was available.

Training/resource and final loss summary:

| Setting | Branch | code_reg_weight | elapsed_s | peak_RSS_MB | peak_GPU_alloc_MB | peak_GPU_reserved_MB | final_recon_loss | final_latent_reg_loss | final_val_L1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A current (0.1, 0.1) | shape | 0.1000 | 36.5153 | 1,585.8 | 78.7051 | 116.0000 | 22.3831 | 0.0015 | 0.0055 |
| A current (0.1, 0.1) | location | 0.1000 | 22.0691 | 1,507.7 | 78.7051 | 114.0000 | 18.0270 | 0.0008 | 0.0041 |
| B paper-like (1.0, 0.0) | shape | 1.0000 | 36.7960 | 1,592.2 | 78.7051 | 116.0000 | 22.4144 | 0.0146 | 0.0055 |
| B paper-like (1.0, 0.0) | location | 0.0000 | 20.6502 | 1,448.5 | 73.0225 | 94.0000 | 18.0260 | 0.0000 | 0.0043 |
| C none (0.0, 0.0) | shape | 0.0000 | 34.0761 | 1,534.5 | 73.0225 | 96.0000 | 22.2509 | 0.0000 | 0.0054 |
| C none (0.0, 0.0) | location | 0.0000 | 20.8085 | 1,446.6 | 73.0225 | 94.0000 | 18.0260 | 0.0000 | 0.0043 |
| D mixed (0.1, 0.0) | shape | 0.1000 | 36.8949 | 1,591.1 | 78.7051 | 116.0000 | 22.3831 | 0.0015 | 0.0055 |
| D mixed (0.1, 0.0) | location | 0.0000 | 20.6384 | 1,455.9 | 73.0225 | 94.0000 | 18.0260 | 0.0000 | 0.0043 |

## 7. Resource Usage

The new B/C/D runs completed at Gwanak scale with peak process RSS around 1.45-1.59 GB per branch. Peak PyTorch GPU allocation stayed below 80 MB and reserved memory stayed below 116 MB in the recorded branch logs. Setting A reused valid prior epoch-10 checkpoints rather than retraining.

GPU snapshot at run start reported two NVIDIA RTX A6000 devices with about 49 GB total VRAM each. No continuous GPU polling or background monitoring was used.

## 8. Loss Dynamics

Shape reconstruction losses were close across settings: B ended at 22.4144 with latent regularization loss 0.0146, A ended at 22.3831 with latent regularization loss 0.0015, and C ended at 22.2509 with no latent penalty. Location with `code_reg_weight=0.0` ended at 18.0260 reconstruction loss with zero latent penalty, while A location with `0.1` ended at 18.0270 reconstruction loss and 0.0008 latent penalty.

Validation L1 stayed tightly grouped: shape 0.00540-0.00546 and location 0.00408-0.00429. No instability was observed from the paper-like setting.

## 9. Random Split Evaluation Results

Full Geo2Vec random split R2, ranger:

| Target | A current (0.1, 0.1) | B paper-like (1.0, 0.0) | C none (0.0, 0.0) | D mixed (0.1, 0.0) |
| --- | --- | --- | --- | --- |
| compactness | 0.8399 | 0.8416 | 0.8394 | 0.8401 |
| bbox_aspect_ratio | 0.9017 | 0.9041 | 0.9056 | 0.8983 |
| perimeter | 0.3554 | 0.3625 | 0.3474 | 0.3583 |
| area | 0.3553 | 0.3617 | 0.3478 | 0.3737 |
| centroid_x | 0.9976 | 0.9976 | 0.9976 | 0.9976 |
| centroid_y | 0.9964 | 0.9964 | 0.9964 | 0.9964 |

Full Geo2Vec random split R2, xgboost:

| Target | A current (0.1, 0.1) | B paper-like (1.0, 0.0) | C none (0.0, 0.0) | D mixed (0.1, 0.0) |
| --- | --- | --- | --- | --- |
| compactness | 0.8800 | 0.8756 | 0.8776 | 0.8793 |
| bbox_aspect_ratio | 0.9114 | 0.9030 | 0.9122 | 0.9081 |
| perimeter | 0.4163 | 0.4424 | 0.4340 | 0.4398 |
| area | 0.3929 | 0.4583 | 0.4584 | 0.4511 |
| centroid_x | 0.9962 | 0.9961 | 0.9961 | 0.9961 |
| centroid_y | 0.9943 | 0.9943 | 0.9943 | 0.9943 |

## 10. Spatial Split Evaluation Results

Full Geo2Vec spatial split R2, ranger:

| Target | A current (0.1, 0.1) | B paper-like (1.0, 0.0) | C none (0.0, 0.0) | D mixed (0.1, 0.0) |
| --- | --- | --- | --- | --- |
| compactness | 0.8515 | 0.8525 | 0.8510 | 0.8504 |
| bbox_aspect_ratio | 0.9263 | 0.9253 | 0.9234 | 0.9237 |
| perimeter | 0.2536 | 0.2870 | 0.2856 | 0.2835 |
| area | 0.1079 | 0.1578 | 0.1447 | 0.1461 |
| centroid_x | 0.9926 | 0.9925 | 0.9926 | 0.9925 |
| centroid_y | 0.9926 | 0.9928 | 0.9928 | 0.9928 |

Full Geo2Vec spatial split R2, xgboost:

| Target | A current (0.1, 0.1) | B paper-like (1.0, 0.0) | C none (0.0, 0.0) | D mixed (0.1, 0.0) |
| --- | --- | --- | --- | --- |
| compactness | 0.8882 | 0.8875 | 0.8895 | 0.8890 |
| bbox_aspect_ratio | 0.9250 | 0.9228 | 0.9187 | 0.9248 |
| perimeter | 0.3014 | 0.3162 | 0.3194 | 0.3053 |
| area | 0.2094 | 0.2555 | 0.2343 | 0.2524 |
| centroid_x | 0.9943 | 0.9938 | 0.9938 | 0.9938 |
| centroid_y | 0.9929 | 0.9930 | 0.9930 | 0.9930 |

Current-vs-paper-like spatial full Geo2Vec deltas:

| Model | Target | A current | B paper-like | Delta B-A |
| --- | --- | --- | --- | --- |
| ranger | compactness | 0.8515 | 0.8525 | 0.0011 |
| ranger | bbox_aspect_ratio | 0.9263 | 0.9253 | -0.0010 |
| ranger | perimeter | 0.2536 | 0.2870 | 0.0335 |
| ranger | area | 0.1079 | 0.1578 | 0.0499 |
| ranger | centroid_x | 0.9926 | 0.9925 | -0.0000 |
| ranger | centroid_y | 0.9926 | 0.9928 | 0.0002 |
| xgboost | compactness | 0.8882 | 0.8875 | -0.0006 |
| xgboost | bbox_aspect_ratio | 0.9250 | 0.9228 | -0.0022 |
| xgboost | perimeter | 0.3014 | 0.3162 | 0.0148 |
| xgboost | area | 0.2094 | 0.2555 | 0.0461 |
| xgboost | centroid_x | 0.9943 | 0.9938 | -0.0005 |
| xgboost | centroid_y | 0.9929 | 0.9930 | 0.0001 |

## 11. PCA/UMAP Diagnostics

PCA and UMAP coordinates and area-colored figures were produced for shape-only, location-only, and full Geo2Vec embeddings for every ablation setting. Outputs are under:

`/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_gamma_ablation_v1/r_evaluation/<setting>/`

Each setting includes `shape_pca_coordinates.parquet`, `location_pca_coordinates.parquet`, `full_geo2vec_pca_coordinates.parquet`, matching UMAP coordinate parquet files, and PNG figures for area-colored PCA/UMAP diagnostics. UMAP used R `uwot` with 32 threads.

## 12. Retrieval Diagnostics

Nearest-neighbor retrieval tables were exported for every setting and embedding type: `shape_retrieval_neighbors.parquet`, `location_retrieval_neighbors.parquet`, and `full_geo2vec_retrieval_neighbors.parquet`. Retrieval diagnostics are evaluation outputs only and did not feed geometry proxies back into embeddings.

## 13. Comparison of Gamma Settings

Mean selected spatial full Geo2Vec R2:

| Setting | Spatial full mean R2 ranger | Spatial full mean R2 xgboost |
| --- | --- | --- |
| A current (0.1, 0.1) | 0.6874 | 0.7185 |
| B paper-like (1.0, 0.0) | 0.7013 | 0.7281 |
| C none (0.0, 0.0) | 0.6983 | 0.7248 |
| D mixed (0.1, 0.0) | 0.6982 | 0.7264 |

Mean spatial R2 by embedding type with xgboost:

| Embedding | A current (0.1, 0.1) | B paper-like (1.0, 0.0) | C none (0.0, 0.0) | D mixed (0.1, 0.0) |
| --- | --- | --- | --- | --- |
| shape | 0.3404 | 0.3417 | 0.3419 | 0.3404 |
| location | 0.3672 | 0.3997 | 0.3997 | 0.3997 |
| full_geo2vec | 0.7185 | 0.7281 | 0.7248 | 0.7264 |

Mean spatial R2 by embedding type with ranger:

| Embedding | A current (0.1, 0.1) | B paper-like (1.0, 0.0) | C none (0.0, 0.0) | D mixed (0.1, 0.0) |
| --- | --- | --- | --- | --- |
| shape | 0.3497 | 0.3477 | 0.3470 | 0.3497 |
| location | 0.3636 | 0.3845 | 0.3845 | 0.3845 |
| full_geo2vec | 0.6874 | 0.7013 | 0.6983 | 0.6982 |

The paper-like setting B produced the best mean selected spatial full-embedding score for both ranger and xgboost. Compared with A, B improved spatial full Geo2Vec area R2 from 0.1079 to 0.1578 with ranger and from 0.2094 to 0.2555 with xgboost. B also improved spatial perimeter R2 from 0.2536 to 0.2870 with ranger and from 0.3014 to 0.3162 with xgboost. Compactness and centroid scores were effectively stable.

C and D were competitive, especially for xgboost area/perimeter, but B has the strongest combined argument because it improves spatial full performance while restoring branch-specific paper-faithful regularization.

## 14. Recommended Setting for 100k

Use **shape `code_reg_weight=1.0`, location `code_reg_weight=0.0`** for the next 100k-building experiment.

Justification:

- It matches the external GeoNeuralRepresentation branch-default pattern better than the current controlled `0.1/0.1` setting.
- It improved spatial-split full Geo2Vec performance on area and perimeter, the two targets most sensitive to morphology and scale.
- It did not materially reduce centroid recoverability, indicating that removing location latent regularization did not harm position encoding in this bounded test.
- It was stable at epoch 10 with similar reconstruction and validation losses to the current setting.
- Resource usage stayed within the same small Gwanak-scale envelope.

## 15. Problems Found

- The previous controlled `0.1/0.1` setting is a methodological discrepancy relative to the apparent external branch defaults.
- Differences are not huge, so the 100k experiment should preserve the full manifest and compare against this Gwanak baseline rather than treating the result as final proof.
- Setting C showed that removing all regularization can be competitive on some nonlinear metrics, but it is less paper-faithful and does not outperform B on the consolidated spatial score.

## 16. Next Steps

Proceed to a bounded 100k experiment using branch order `[location, shape]`, `Geo_dim=32` per branch, epoch 10, and code regularization `(shape=1.0, location=0.0)`. Reuse the R evaluation path with deterministic splits and keep geometry proxies evaluation-only.

## Output Manifests

- Ablation manifest: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_gamma_ablation_v1/analysis/gwanak_full_geo2vec_gamma_ablation_manifest.json`
- Training summary parquet: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_gamma_ablation_v1/analysis/training_summary_by_setting_branch.parquet`
- Recoverability metrics parquet: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_gamma_ablation_v1/analysis/r_recoverability_metrics_by_setting.parquet`
- Spatial score summary parquet: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_gamma_ablation_v1/analysis/spatial_full_score_summary.parquet`
