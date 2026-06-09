# Gwanak Full Geo2Vec Full R Evaluation

Generated: 2026-06-10T05:05:42+09:00

## 1. Executive Summary

Full-data R evaluation completed for the existing Gwanak epoch-10 Geo2Vec outputs. This was evaluation-only: no SDF caches, model checkpoints, or embeddings were regenerated. The R evaluator used all `38,547` buildings (`--max-model-rows 0`) with `--nthreads-xgboost 32` and `--nthreads-umap 32`.

Main result: full Geo2Vec preserves location strongly and retains shape signal. Shape-only remains strongest for compactness and bbox aspect ratio; location-only is strongest or comparable for centroid recovery and also carries area/perimeter signal from spatial structure.

## 2. Inputs Used

- Shape epoch-10 embeddings: `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/gwanak_full_geo2vec_epoch_saturation_v1/gwanak_geo2vec_shape_32d_epoch010_shape_embeddings`
- Location epoch-10 embeddings: `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/gwanak_full_geo2vec_epoch_saturation_v1/gwanak_geo2vec_location_32d_epoch010_location_embeddings`
- Full epoch-10 embeddings: `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/gwanak_full_geo2vec_epoch_saturation_v1/gwanak_full_geo2vec_32d_epoch010_embeddings`
- Deterministic split: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/evaluation_splits/gwanak_building_evaluation_split.parquet`
- R output directory: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full`

Full export branch order: `['location', 'shape']`. Full dimension: `64`.

## 3. Confirmation: Evaluation Only

No Geo2Vec training commands were run. No sample cache generation commands were run. No embedding export commands were run. The evaluator read existing Parquet embedding outputs and computed geometry variables only as evaluation labels/proxies.

## 4. R Packages Used

```json
{
  "FNN": true,
  "glmnet": true,
  "ranger": true,
  "uwot": true,
  "xgboost": true
}
```

Evaluation settings:

```json
{
  "max_model_rows": 0,
  "nthreads_umap": 32,
  "nthreads_xgboost": 32,
  "xgb_rounds": 120
}
```

## 5. Evaluation Split

Random split counts: `{'test': 7727, 'train': 30820}`.
Spatial split counts: `{'test': 9447, 'train': 29100}`.

Random split method: SHA256(seed|building_id) mapped to deterministic 5 folds; fold 5 is test.

Spatial split method: Centroid x/y quantile bins in EPSG:5186 combined deterministically into 5 folds; fold 5 is test.

## 6. Shape-Only Results

Random split, R ranger R2:

| target            |   shape |
|:------------------|--------:|
| area              |  0.1641 |
| perimeter         |  0.2649 |
| compactness       |  0.8564 |
| bbox_aspect_ratio |  0.9145 |
| edge_count        |  0.2799 |
| vertex_count      |  0.2799 |
| centroid_x        |  0.0984 |
| centroid_y        |  0.0626 |

Random split, R xgboost R2:

| target            |   shape |
|:------------------|--------:|
| area              |  0.1721 |
| perimeter         |  0.2738 |
| compactness       |  0.8818 |
| bbox_aspect_ratio |  0.9015 |
| edge_count        |  0.2771 |
| vertex_count      |  0.2819 |
| centroid_x        |  0.0798 |
| centroid_y        |  0.0521 |

## 7. Location-Only Results

Random split, R ranger R2:

| target            |   location |
|:------------------|-----------:|
| area              |     0.4083 |
| perimeter         |     0.3502 |
| compactness       |     0.1361 |
| bbox_aspect_ratio |     0.0887 |
| edge_count        |     0.1187 |
| vertex_count      |     0.1187 |
| centroid_x        |     0.9975 |
| centroid_y        |     0.9963 |

Random split, R xgboost R2:

| target            |   location |
|:------------------|-----------:|
| area              |     0.3706 |
| perimeter         |     0.3455 |
| compactness       |     0.1195 |
| bbox_aspect_ratio |     0.0725 |
| edge_count        |     0.1162 |
| vertex_count      |     0.1116 |
| centroid_x        |     0.9959 |
| centroid_y        |     0.9937 |

## 8. Full Geo2Vec Results

Random split, R ranger R2:

| target            |   full_geo2vec |
|:------------------|---------------:|
| area              |         0.3553 |
| perimeter         |         0.3554 |
| compactness       |         0.8399 |
| bbox_aspect_ratio |         0.9017 |
| edge_count        |         0.2663 |
| vertex_count      |         0.2663 |
| centroid_x        |         0.9976 |
| centroid_y        |         0.9964 |

Random split, R xgboost R2:

| target            |   full_geo2vec |
|:------------------|---------------:|
| area              |         0.3929 |
| perimeter         |         0.4163 |
| compactness       |         0.88   |
| bbox_aspect_ratio |         0.9114 |
| edge_count        |         0.2954 |
| vertex_count      |         0.2904 |
| centroid_x        |         0.9962 |
| centroid_y        |         0.9943 |

Spatial split, R ranger R2:

| target            |   full_geo2vec |   location |   shape |
|:------------------|---------------:|-----------:|--------:|
| area              |         0.1079 |     0.05   |  0.0785 |
| perimeter         |         0.2536 |     0.1117 |  0.2287 |
| compactness       |         0.8515 |     0.0469 |  0.8663 |
| bbox_aspect_ratio |         0.9263 |    -0.0128 |  0.9377 |
| edge_count        |         0.2085 |     0.0279 |  0.2414 |
| vertex_count      |         0.2085 |     0.0279 |  0.2414 |
| centroid_x        |         0.9926 |     0.9928 | -0.0273 |
| centroid_y        |         0.9926 |     0.993  |  0.0144 |

Spatial split, R xgboost R2:

| target            |   full_geo2vec |   location |   shape |
|:------------------|---------------:|-----------:|--------:|
| area              |         0.2094 |     0.091  |  0.0605 |
| perimeter         |         0.3014 |     0.082  |  0.1999 |
| compactness       |         0.8882 |     0.0298 |  0.8887 |
| bbox_aspect_ratio |         0.925  |     0.014  |  0.9265 |
| edge_count        |         0.2399 |     0.0371 |  0.2354 |
| vertex_count      |         0.2385 |     0.0393 |  0.2438 |
| centroid_x        |         0.9943 |     0.994  | -0.0423 |
| centroid_y        |         0.9929 |     0.9924 |  0.0091 |

## 9. Comparison with Previous Python Evaluation

Previous Python epoch-10 evaluation used random forest on its deterministic split. The closest comparison is R ranger on the random split. Differences are expected because the split implementation and RF implementation are not identical, but broad behavior is consistent.

R ranger minus Python random forest R2:

| target            | embedding    |   r2_r_ranger |   r2_python_rf |   delta_r_minus_python |
|:------------------|:-------------|--------------:|---------------:|-----------------------:|
| area              | full_geo2vec |        0.3553 |         0.349  |                 0.0063 |
| bbox_aspect_ratio | full_geo2vec |        0.9017 |         0.9221 |                -0.0204 |
| centroid_x        | full_geo2vec |        0.9976 |         0.9968 |                 0.0008 |
| centroid_y        | full_geo2vec |        0.9964 |         0.9953 |                 0.0011 |
| compactness       | full_geo2vec |        0.8399 |         0.8674 |                -0.0275 |
| edge_count        | full_geo2vec |        0.2663 |         0.2963 |                -0.0301 |
| perimeter         | full_geo2vec |        0.3554 |         0.3737 |                -0.0183 |
| vertex_count      | full_geo2vec |        0.2663 |         0.2963 |                -0.0301 |
| area              | location     |        0.4083 |         0.4384 |                -0.0301 |
| bbox_aspect_ratio | location     |        0.0887 |         0.0557 |                 0.033  |
| centroid_x        | location     |        0.9975 |         0.9968 |                 0.0007 |
| centroid_y        | location     |        0.9963 |         0.9954 |                 0.0009 |
| compactness       | location     |        0.1361 |         0.1614 |                -0.0253 |
| edge_count        | location     |        0.1187 |         0.1646 |                -0.0459 |
| perimeter         | location     |        0.3502 |         0.4081 |                -0.0579 |
| vertex_count      | location     |        0.1187 |         0.1646 |                -0.0459 |
| area              | shape        |        0.1641 |         0.1483 |                 0.0158 |
| bbox_aspect_ratio | shape        |        0.9145 |         0.9281 |                -0.0136 |
| centroid_x        | shape        |        0.0984 |         0.0867 |                 0.0118 |
| centroid_y        | shape        |        0.0626 |         0.0547 |                 0.0079 |
| compactness       | shape        |        0.8564 |         0.8699 |                -0.0135 |
| edge_count        | shape        |        0.2799 |         0.2903 |                -0.0104 |
| perimeter         | shape        |        0.2649 |         0.2648 |                 0.0002 |
| vertex_count      | shape        |        0.2799 |         0.2903 |                -0.0104 |

Python random forest R2:

| target            |   full_geo2vec |   location |   shape |
|:------------------|---------------:|-----------:|--------:|
| area              |         0.349  |     0.4384 |  0.1483 |
| perimeter         |         0.3737 |     0.4081 |  0.2648 |
| compactness       |         0.8674 |     0.1614 |  0.8699 |
| bbox_aspect_ratio |         0.9221 |     0.0557 |  0.9281 |
| edge_count        |         0.2963 |     0.1646 |  0.2903 |
| vertex_count      |         0.2963 |     0.1646 |  0.2903 |
| centroid_x        |         0.9968 |     0.9968 |  0.0867 |
| centroid_y        |         0.9953 |     0.9954 |  0.0547 |

## 10. PCA/UMAP Diagnostics

PCA and UMAP completed for all three embedding sets.

```json
{
  "full_geo2vec": {
    "pca_area_figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/full_geo2vec_pca_area.png",
    "pca_coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/full_geo2vec_pca_coordinates.parquet",
    "umap_area_figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/full_geo2vec_umap_area.png",
    "umap_available": true,
    "umap_coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/full_geo2vec_umap_coordinates.parquet"
  },
  "location": {
    "pca_area_figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/location_pca_area.png",
    "pca_coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/location_pca_coordinates.parquet",
    "umap_area_figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/location_umap_area.png",
    "umap_available": true,
    "umap_coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/location_umap_coordinates.parquet"
  },
  "shape": {
    "pca_area_figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/shape_pca_area.png",
    "pca_coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/shape_pca_coordinates.parquet",
    "umap_area_figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/shape_umap_area.png",
    "umap_available": true,
    "umap_coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/shape_umap_coordinates.parquet"
  }
}
```

## 11. Retrieval Diagnostics

Nearest-neighbor retrieval diagnostics completed for shape, location, and full Geo2Vec.

| embedding    | neighbors                                                                                                                                                        |   mean_abs_log_area_delta |   mean_centroid_distance |
|:-------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------:|-------------------------:|
| shape        | /members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/shape_retrieval_neighbors.parquet        |                    0.5608 |                  1756.45 |
| location     | /members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/location_retrieval_neighbors.parquet     |                    0.6109 |                   127.56 |
| full_geo2vec | /members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/r_evaluation_epoch010_full/full_geo2vec_retrieval_neighbors.parquet |                    0.5172 |                   211.81 |

## 12. Problems Found

No blocking problems found. The full R evaluation completed successfully with R `ranger`, `xgboost`, `glmnet`, `uwot`, and `FNN` available. Geometry proxy variables were used only for evaluation labels.

## 13. Recommendation for 100k Experiment

Proceed with the 100k experiment using the full paper-faithful `[location, shape]` export, the deterministic split/evaluation framework, and R evaluation as the primary evaluation gate. Keep the current no-handcrafted-feature constraint. For 100k, use the R evaluator with explicit thread settings and consider running both random and spatial splits before any 1M or nationwide attempt.
