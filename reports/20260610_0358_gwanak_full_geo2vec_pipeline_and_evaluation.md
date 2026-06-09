# Gwanak Full Geo2Vec Pipeline and Evaluation

Generated: 2026-06-10T03:58:48+09:00

## 1. Executive Summary

The bounded Gwanak-scale full Geo2Vec workflow completed with separate paper-faithful location and shape branches and exported the final embedding as `z_E = [z_E^loc, z_E^shp]`. No handcrafted geometry variables were added to the embeddings.

Recommendation: ready for a 100k-building experiment with the same bounded logging and evaluation gates.

## 2. Current Pipeline Status

- Study: `gwanak_full_geo2vec_paper_faithful_v1`
- Buildings: `38547`
- Geo_dim per branch: `32`
- Epochs per branch: `1`
- Shape cache: `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/gwanak_full_geo2vec_paper_faithful_v1/korea_geo2vec_shape_samples_38547_sdf_gwanak_full_geo2vec_0200_v1/manifest.json`
- Location cache: `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/gwanak_full_geo2vec_paper_faithful_v1/korea_geo2vec_location_samples_38547_sdf_gwanak_full_geo2vec_0200_v1/manifest.json`
- Shape checkpoint: `/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/gwanak_full_geo2vec_paper_faithful_v1/gwanak_geo2vec_shape_32d/checkpoint_step_00001682.pt`
- Location checkpoint: `/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/gwanak_full_geo2vec_paper_faithful_v1/gwanak_geo2vec_location_32d/checkpoint_step_00001007.pt`

## 3. Confirmation of Paper-Faithful Geo2Vec

- Shape branch uses per-entity shape normalization after dataset normalization.
- Location branch uses dataset/global normalization only.
- Full export branch order: `['location', 'shape']`
- Handcrafted geometry features in embedding: `false`
- Evaluation proxy variables are computed only after export for diagnostics.

## 4. Scripts Added or Modified

- Added `tests/geo2vec_large_scale/run_gwanak_full_geo2vec_pipeline.py`
- Added `tests/geo2vec_large_scale/evaluate_geo2vec_embeddings.py`
- Reused existing cache, training, branch export, and full export scripts.

## 5. Experiment Configuration

```json
{
  "batch_size": 4096,
  "buildings_per_shard": 5000,
  "checkpoint_every_steps": 250,
  "epochs": 1,
  "geo_dim": 32,
  "geometry": "/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg",
  "hidden_size": 128,
  "keep_checkpoints": 2,
  "layer": "gwanak_buildings",
  "num_freqs": 4,
  "num_layers": 4,
  "overwrite": false,
  "point_sample": 7,
  "sample_band_width": 0.08,
  "sample_config_version": "sdf_gwanak_full_geo2vec_0200_v1",
  "samples_per_unit": 28.0,
  "seed": 20260608,
  "skip_existing": true,
  "uniform_grid": 8,
  "workers": 8
}
```

## 6. Resource Usage Summary

```json
[]
```

Detailed machine-readable logs are under `/members/dhnyu/fusedata/geo2vec_large_scale/logs/gwanak_full_geo2vec_paper_faithful_v1`.

## 7. Output Embedding Schema

- Shape-only dimension: `32`
- Location-only dimension: `32`
- Full dimension: `64`
- Full column order valid: `true`
- Full schema starts with `building_id`, `geo2vec_internal_id`, `geo2vec_loc_000 ... geo2vec_loc_031`, then `geo2vec_shp_000 ... geo2vec_shp_031`.

## 8. Evaluation Framework

The evaluator compares shape-only, location-only, and full Geo2Vec embeddings using linear regression, ridge regression, and random forest recoverability. Geometry proxies are labels only. Retrieval diagnostics use nearest neighbors in each embedding space. PCA figures and coordinates are exported. UMAP was attempted only if the package was already available.

Evaluation output directory: `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation`

## 9. Shape-Only Results

Random forest R2:

```json
{
  "area": 0.06645647398781673,
  "centroid_x": 0.04953572001039286,
  "centroid_y": 0.03659357775512817,
  "compactness": 0.7635472927487472,
  "perimeter": 0.16634349775567947
}
```

## 10. Location-Only Results

Random forest R2:

```json
{
  "area": 0.03728931094511845,
  "centroid_x": 0.968961685234646,
  "centroid_y": 0.9566177690706626,
  "compactness": 0.0525406213191264,
  "perimeter": 0.05766536950910306
}
```

## 11. Full Geo2Vec Results

Random forest R2:

```json
{
  "area": 0.08551332179972804,
  "centroid_x": 0.9795155289046596,
  "centroid_y": 0.9730447383408123,
  "compactness": 0.771917085844206,
  "perimeter": 0.19888382933472393
}
```

## 12. Retrieval Diagnostics

```json
{
  "full_geo2vec": {
    "neighbors": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/full_geo2vec_retrieval_neighbors.parquet",
    "summary": {
      "embedding": "full_geo2vec",
      "mean_abs_log_area_delta": 0.6666288584574556,
      "mean_centroid_distance": 349.43139852280854
    }
  },
  "location": {
    "neighbors": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/location_retrieval_neighbors.parquet",
    "summary": {
      "embedding": "location",
      "mean_abs_log_area_delta": 0.7323505963142722,
      "mean_centroid_distance": 354.7513033886957
    }
  },
  "shape": {
    "neighbors": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/shape_retrieval_neighbors.parquet",
    "summary": {
      "embedding": "shape",
      "mean_abs_log_area_delta": 0.5798943562062294,
      "mean_centroid_distance": 2112.9956210351975
    }
  }
}
```

## 13. PCA/UMAP Diagnostics

PCA:

```json
{
  "full_geo2vec": {
    "coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/full_geo2vec_pca_coordinates.parquet",
    "explained_variance_ratio": [
      0.2481851875782013,
      0.20237848162651062
    ],
    "figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/full_geo2vec_pca_area.png"
  },
  "location": {
    "coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/location_pca_coordinates.parquet",
    "explained_variance_ratio": [
      0.5016056299209595,
      0.40398338437080383
    ],
    "figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/location_pca_area.png"
  },
  "shape": {
    "coordinates": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/shape_pca_coordinates.parquet",
    "explained_variance_ratio": [
      0.33422693610191345,
      0.16684600710868835
    ],
    "figure": "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_paper_faithful_v1/evaluation/shape_pca_area.png"
  }
}
```

UMAP:

```json
{
  "full_geo2vec": {
    "available": false,
    "error": "ModuleNotFoundError: No module named 'umap'"
  },
  "location": {
    "available": false,
    "error": "ModuleNotFoundError: No module named 'umap'"
  },
  "shape": {
    "available": false,
    "error": "ModuleNotFoundError: No module named 'umap'"
  }
}
```

## 14. Problems Found

No blocking problems found in the bounded Gwanak run.

## 15. Recommended Next Step

Proceed to a 100k-building experiment only if the 100k run uses the same paper-faithful two-branch workflow, exports `[location, shape]`, keeps geometry proxies out of embeddings, and runs this evaluation framework before any 1M or nationwide attempt.
