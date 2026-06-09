# Full Geo2Vec Large-Scale Implementation Plan

Generated: 2026-06-09

## 1. Executive Summary

The large-scale FUSE Geo2Vec prototype now supports both original GeoNeuralRepresentation branches:

- `--branch shape`: current shape behavior, with dataset normalization followed by per-entity centering and scale normalization.
- `--branch location`: original location-learning behavior, with dataset/global normalization only and no per-entity centering or per-entity scaling.

The pipeline can now train separate shape and location models, export branch-specific embeddings, and export the full paper-order Geo2Vec representation:

```text
z_E = [z_E^loc, z_E^shp]
```

No handcrafted geometry features were added. The implementation restores the two original Geo2Vec branches only.

Smoke test status: passed on 8 buildings with `Geo_dim=4`. Shape-only exported 4D, location-only exported 4D, and full Geo2Vec exported 8D with columns ordered as `geo2vec_loc_*` followed by `geo2vec_shp_*`.

## 2. What the Paper Defines as the Final Geo2Vec Embedding

The requested final representation is the concatenation of the location embedding and shape embedding:

```text
z_E = [z_E^loc, z_E^shp]
```

Implementation requirement followed here:

- Train the location branch and shape branch as separate Geo2Vec SDF models.
- Export their entity embedding tables.
- Concatenate location first, shape second.
- Do not add area, perimeter, compactness, aspect ratio, bbox size, vertex count, centroid features, or any other handcrafted morphometric variables.

## 3. What the External Repository Actually Implements

Verified from code in `/members/dhnyu/fuse_external/GeoNeuralRepresentation`.

Neural model:

- `models/Geo2Vec.py`, class `Geo2Vec_Model`, lines 8-66:
  - defines `poly_embedding_layer = torch.nn.Embedding(n_poly, z_size)`;
  - defines `PositionalEncoder`;
  - positional-encodes SDF sample coordinates;
  - concatenates encoded coordinates with the entity embedding;
  - predicts one SDF value.

Preprocessing:

- `utils/preprocess.py`, `normalize_geometries(...)`, lines 38-68:
  - computes dataset total bounds;
  - translates by global `min_x, min_y`;
  - scales x by global width and y by global height.
- `utils/data_loader.py`, `preprocessing_list(...)`, lines 45-62:
  - calls `normalize_geometries(Geolist)`;
  - calls `poly_preprocess(poly)`;
  - stores `polys_dict_shape[id] = preprocess[0]`;
  - stores `polys_dict_location[id] = preprocess[1]`.

Branch training and concatenation:

- `runners/list2embedding.py`, `list2vec(...)`, lines 88-113:
  - exposes `location_learning` and `shape_learning`;
  - constructs both dictionaries through `preprocessing_list(...)`.
- Location branch:
  - lines 115-182 sample `polys_dict_loc`, train `Geo2Vec_Model`, and assign `location_embedding = model.poly_embedding_layer.weight.data.cpu().numpy()`.
- Shape branch:
  - lines 184-268 sample `polys_dict_shape`, train `Geo2Vec_Model`, and assign `shape_embedding = model.poly_embedding_layer.weight.data.cpu().numpy()`.
- Final embedding:
  - lines 270-275 concatenate with `np.concatenate((location_embedding, shape_embedding), axis=-1)` when both branches are enabled.

Conclusion: the original code implements the full representation as `[location_embedding, shape_embedding]`, not as a centroid model or handcrafted feature vector.

## 4. Current FUSE Shape-Only Status

Before this change, the optimized large-scale prototype under `/members/dhnyu/fuse/tests/geo2vec_large_scale/` only implemented shape SDF sampling:

- `generate_disk_backed_sdf_samples.py` used `normalize_for_shape(...)`.
- `train_global_geo2vec_from_sample_cache.py` trained one model from that shape cache.
- `export_global_geo2vec_embeddings.py` exported one model's embedding table.

Completed historical outputs are still shape-only and were not deleted or overwritten.

## 5. Implementation Changes Made

Modified files:

- `/members/dhnyu/fuse/tests/geo2vec_large_scale/generate_disk_backed_sdf_samples.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/train_global_geo2vec_from_sample_cache.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/export_global_geo2vec_embeddings.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/run_sample_density_sensitivity.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/run_epoch_saturation.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/run_sample_density_saturation.py`

Added file:

- `/members/dhnyu/fuse/tests/geo2vec_large_scale/export_full_geo2vec_embeddings.py`

Sampler changes:

- Added `--branch shape|location` in `generate_disk_backed_sdf_samples.py`, lines 82-102.
- Preserved `normalize_for_shape(...)`, lines 139-154.
- Added `normalize_for_location(...)`, lines 157-166.
- Added `normalize_geometry(...)`, lines 169-174.
- Added branch-specific normalization metadata, lines 177-203.
- Added branch-specific uniform sample bounds, lines 206-211.
- Wrote branch-specific cache directories:
  - `korea_geo2vec_shape_samples_{limit}_{sample_config_version}`
  - `korea_geo2vec_location_samples_{limit}_{sample_config_version}`
- Manifest now stores branch, source CRS, total bounds, normalization formula, sample config, entity count, sample count, seed, and timing metadata, lines 424-450.

Training changes:

- `train_global_geo2vec_from_sample_cache.py` now reads `manifest["branch"]`.
- Checkpoints record branch in `model_config["branch"]`, plus sample normalization/config metadata, lines 267-280.
- Default training run naming is branch-aware, lines 213-243.

Export changes:

- `export_global_geo2vec_embeddings.py` now supports:
  - branch inference or explicit `--branch`;
  - `--column-style legacy` for old `geo2vec_000` style;
  - `--column-style branch` for `geo2vec_shp_000` or `geo2vec_loc_000`, lines 24-57 and 90-110.
- `export_full_geo2vec_embeddings.py` exports full `[location, shape]` embeddings:
  - validates one location checkpoint and one shape checkpoint;
  - writes `geo2vec_loc_###` first and `geo2vec_shp_###` second;
  - records `branch_order = ["location", "shape"]`;
  - records `contains_handcrafted_geometry_features = false`, lines 58-123.

Compatibility:

- Existing shape-only export style remains available via `--column-style legacy`.
- Existing historical shape-only outputs were not overwritten.
- Study drivers were updated to pass `--branch shape` and use the new shape cache directory naming.

## 6. Location Branch Normalization Strategy

The location branch follows the original GeoNeuralRepresentation meaning:

```text
x_norm = (x - global_min_x) / (global_max_x - global_min_x)
y_norm = (y - global_min_y) / (global_max_y - global_min_y)
```

Important properties:

- Source geometries remain in EPSG:5186 on disk.
- Raw EPSG:5186 coordinates are not fed directly to `Geo2Vec_Model`.
- Location normalization is dataset/global only.
- No per-entity centering is applied.
- No per-entity scale normalization is applied.
- SDF samples are generated from the normalized full polygon geometry, preserving the original location-branch semantics.

Shape branch remains:

```text
global normalization -> per-entity bbox centering -> per-entity max-side scaling
```

This matches the external code path where `preprocessing_list(...)` first dataset-normalizes all geometries and then uses `poly_preprocess(...)` for the shape dictionary.

Smoke-test manifest examples:

- Shape manifest:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/full_geo2vec_smoke_20260609/korea_geo2vec_shape_samples_8_full_geo2vec_smoke_v1/manifest.json`
- Location manifest:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/full_geo2vec_smoke_20260609/korea_geo2vec_location_samples_8_full_geo2vec_smoke_v1/manifest.json`

Both manifests record `source_crs: EPSG:5186`, total bounds, branch, formula, seed, sample density, number of entities, and number of samples.

## 7. Output Schema

Branch-specific schema:

```text
building_id
geo2vec_internal_id
geo2vec_loc_000 ... geo2vec_loc_{Geo_dim-1}
```

or:

```text
building_id
geo2vec_internal_id
geo2vec_shp_000 ... geo2vec_shp_{Geo_dim-1}
```

Full Geo2Vec schema:

```text
building_id
geo2vec_internal_id
geo2vec_loc_000 ... geo2vec_loc_{Geo_dim-1}
geo2vec_shp_000 ... geo2vec_shp_{Geo_dim-1}
```

The full embedding order is location first, shape second, matching the paper definition.

No columns for area, perimeter, compactness, aspect ratio, bbox size, vertex count, centroid, or other handcrafted geometry variables are produced.

## 8. Smoke Test Results

Smoke test inputs:

- Dataset: national VWorld buildings through existing id-map/geometry paths.
- Limit: 8 buildings.
- `Geo_dim`: 4.
- Epochs: 1.
- Hidden size: 16.
- Layers: 1.
- Frequency bands: 2.
- Purpose: pipeline correctness only, not embedding quality.

Commands run:

- Built id map:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/full_geo2vec_smoke_20260609/korea_buildings_geo2vec_global_id_map_8.parquet`
- Generated shape cache:
  - branch `shape`;
  - 8 entities;
  - 137 samples;
  - validation passed.
- Generated location cache:
  - branch `location`;
  - 8 entities;
  - 134 samples;
  - validation passed.
- Trained shape model:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/full_geo2vec_smoke_20260609/shape_4d/checkpoint_step_00000002.pt`
- Trained location model:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/full_geo2vec_smoke_20260609/location_4d/checkpoint_step_00000002.pt`
- Exported shape-only branch-prefixed output:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/full_geo2vec_smoke_20260609/shape_4d_shape_embeddings/`
- Exported location-only branch-prefixed output:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/full_geo2vec_smoke_20260609/location_4d_location_embeddings/`
- Exported full `[location, shape]` output:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/full_geo2vec_smoke_20260609/smoke_full_geo2vec_4d_embeddings/`
- Exported legacy shape-only output for compatibility:
  - `/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/full_geo2vec_smoke_20260609_legacy_shape_check/shape_4d_embeddings/`

Verification:

```json
{
  "shape_rows": 8,
  "location_rows": 8,
  "full_rows": 8,
  "shape_dim": 4,
  "location_dim": 4,
  "full_dim": 8,
  "full_order_after_ids": [
    "geo2vec_loc_000",
    "geo2vec_loc_001",
    "geo2vec_loc_002",
    "geo2vec_loc_003",
    "geo2vec_shp_000",
    "geo2vec_shp_001",
    "geo2vec_shp_002",
    "geo2vec_shp_003"
  ],
  "order_is_location_then_shape": true,
  "handcrafted_columns": [],
  "id_columns": [
    "building_id",
    "geo2vec_internal_id"
  ]
}
```

Smoke-test conclusion:

- Shape-only output dimension equals `Geo_dim`.
- Location-only output dimension equals `Geo_dim`.
- Full output dimension equals `2 * Geo_dim`.
- Full output order is `[location, shape]`.
- No handcrafted variables are included.
- Shape-only legacy export remains available.

## 9. Remaining Steps Before Nationwide Training

1. Run a larger but still bounded branch-pair test, for example 1k or 10k buildings, using `Geo_dim=32`.
2. Compare sample count distributions for shape and location caches; location branch may need different density settings because global normalized geometry has very small national-scale footprint sizes.
3. Decide production sample density separately for shape and location, while keeping both faithful to the original SDF branch semantics.
4. Run a 50k full Geo2Vec dry run with checkpoint/resume and full export.
5. Confirm storage growth for two sample caches, two training runs, two checkpoints, and full concatenated embedding export.
6. Update monitoring/summarization scripts to report branch names and full Geo2Vec exports.
7. Only after 50k/100k branch-pair runs are stable, proceed to 300k/1M.
8. Do not promote a nationwide full run until checkpoint retention, resume, export, and downstream validation are confirmed for both branches.
