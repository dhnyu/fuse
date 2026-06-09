# GeoNeuralRepresentation Shape/Location Audit

Generated: 2026-06-09

## 1. Executive Summary

Verified finding: the Geo2Vec / GeoNeuralRepresentation work currently used in FUSE is shape-only for the completed Gwanak and large-scale optimized experiments.

- The direct FUSE wrappers call `list2vec(..., location_learning=False, shape_learning=True)` in `/members/dhnyu/fuse/scripts/embedding/run_gwanak_buildings_geo2vec_shape_full.py` and `/members/dhnyu/fuse/tests/gwanak_test/scripts/run_gwanak_single_model_lightweight.py`.
- The optimized large-scale implementation under `/members/dhnyu/fuse/tests/geo2vec_large_scale/` reimplements shape SDF sampling with `normalize_for_shape(...)` and trains one `Geo2Vec_Model` from cached `x, y, sdf` samples. It does not implement the external repository's location branch.
- GeoNeuralRepresentation's "shape" and "location" branches are not separate encoder classes. Both use `Geo2Vec_Model`; the branch difference is the geometry dictionary used for SDF sampling:
  - shape: per-entity centered and scale-normalized geometry.
  - location: dataset-normalized geometry retaining relative global position and relative size within the dataset extent.
- The learned output embedding is the trainable `poly_embedding_layer.weight`, with dimension `z_size` or `Geo_dim`. If both branches are trained in `list2vec`, outputs are concatenated as `[location_embedding, shape_embedding]`.

Research implication: a "Building Geometry Embedding" should not be treated as complete if it only contains shape Geo2Vec vectors. For a nationwide urban-science representation, use shape embedding plus explicit scale variables at minimum. Add location either as a learned location SDF embedding, explicit normalized coordinates, or both depending on downstream goals and leakage risk.

## 2. Current Status: What We Have Actually Run So Far

Verified shape-only runs:

- `/members/dhnyu/fuse/scripts/embedding/run_gwanak_buildings_geo2vec_shape_full.py`
  - Script docstring says "shape-only Geo2Vec embeddings".
  - `list2vec` call passes `location_learning=False` and `shape_learning=True`.
  - Metadata writes `"embedding_kind": "shape"`.
  - Embedding column count is exactly `Geo_dim`, not `2 * Geo_dim`.
- `/members/dhnyu/fuse/tests/gwanak_test/scripts/run_gwanak_single_model_lightweight.py`
  - Report text explicitly says `shape_learning=True`, `location_learning=False`.
  - Metadata stores `"shape_learning": True`, `"location_learning": False`.
  - `list2vec` call passes `location_learning=False`, `shape_learning=True`.
- `/members/dhnyu/fuse/tests/test_geo2vec_gwanak_100.py`
  - Integration test docstring says "shape-only".
  - `list2vec` call passes `location_learning=False`, `shape_learning=True`.
  - Metadata writes `"embedding_kind": "shape"`.
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/`
  - Large-scale cache generation uses `normalize_for_shape(...)`.
  - Training uses one `Geo2Vec_Model` from cached shape-normalized SDF samples.
  - Export exports only the one model's `poly_embedding_layer.weight`.

Verified conclusion: current FUSE Geo2Vec outputs are shape embeddings. Location-learning parameters appear in wrapper arg objects, but they are unused when `location_learning=False`.

## 3. GeoNeuralRepresentation Architecture

Code paths inspected:

- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/Geo2Vec.py`
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/utils/preprocess.py`
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/utils/data_loader.py`
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/MP_Sampling.py`
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/sample_function.py`
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/list2embedding.py`
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/main.py`
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/learn_location_rep.py`
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/learn_shape_rep.py`

Verified architecture:

- `Geo2Vec_Model` in `models/Geo2Vec.py` is the only neural SDF model class used for both shape and location.
- It contains:
  - `poly_embedding_layer = torch.nn.Embedding(n_poly, z_size)`.
  - `PositionalEncoder(...)` for SDF sample coordinates.
  - A shared MLP that receives concatenated positional coordinate features and entity embedding.
  - `SDFLoss`, an L1 SDF reconstruction loss with optional latent-code regularization.
- `PositionalEncoder` applies sin/cos features to `x, y`; optional `polar_fourier_encoding` appends radial Fourier terms.
- There is no separate centroid encoder, graph encoder, scale encoder, semantic encoder, or image encoder in the external implementation.

How the model is trained:

- SDF sample rows contain entity id, sample coordinate `x, y`, and target signed distance.
- `Geo2Vec_Model.forward(id, xy)` positional-encodes `xy`, looks up or accepts the entity embedding, concatenates both, and predicts one SDF value.
- The exported embedding is not the coordinate encoding. It is the learned entity row in `poly_embedding_layer.weight`.

## 4. Shape Encoder Audit

Verified shape preprocessing:

- `preprocessing_list(Geolist)` in `utils/data_loader.py` first calls `normalize_geometries(Geolist)`.
- `normalize_geometries(...)` in `utils/preprocess.py` dataset-normalizes all input geometries to a global `[0, 1]` style extent by subtracting global `min_x, min_y` and scaling `x` and `y` independently by dataset width and height.
- Then `poly_preprocess(poly)` creates shape geometry by:
  - computing the entity bounding-box center;
  - scaling by the entity's max bounding-box side;
  - returning `preprocess[0]` as centered/scaled geometry.
- `preprocessing_list` stores this as `polys_dict_shape[id]`.

Verified shape sampling:

- `runners/list2embedding.py` samples `polys_dict_shape` when `shape_learning=True`.
- `MP_Sampling.MP_sample(...)` calls:
  - `sample_signed_distance(...)` for boundary vertices, Gaussian near-boundary/near-vertex samples, and length-proportional edge samples;
  - `sample_bounding_distance(...)` for uniform grid samples over a bounding box.
- The apparent adaptive hook based on edge count is dead code: `if num_edges > float('inf')` never triggers.

What shape branch learns:

- It learns an entity latent vector that helps reconstruct each centered and scale-normalized geometry's SDF.
- It captures outline, compactness, elongation, holes, complexity, and related morphology to the extent SDF samples and model capacity preserve them.
- It intentionally removes absolute location.
- It largely removes absolute scale because each entity is normalized by its own max side length before shape SDF training.

Shape embedding dimension:

- In `list2vec`, shape dimension is `Geo_dim` if provided, otherwise `args.z_size_shape`.
- In external `main.py`, default shape dimension is `z_size_shape=256`.
- In FUSE completed runs, verified dimensions include 32D and 64D shape-only outputs depending on script/config.

## 5. Location Encoder Audit

Where flags are defined:

- `location_learning` and `shape_learning` are function parameters in `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/list2embedding.py`, defaulting to `True`.
- `main.py` does not expose branch on/off flags; it trains location first and shape second.
- `learn_location_rep.py` trains only location; `learn_shape_rep.py` trains only shape.

Where flags are used:

- `list2vec(...)` calls `preprocessing_list(Geolist)` once.
- If `location_learning` is true, it samples and trains `polys_dict_loc`.
- If `shape_learning` is true, it samples and trains `polys_dict_shape`.
- If both are true, it concatenates the two learned embedding arrays.

Verified location preprocessing:

- `preprocessing_list(Geolist)` first dataset-normalizes all geometries using `normalize_geometries`.
- `poly_preprocess(poly)` returns a tuple whose second element is the input `poly` at that stage.
- `preprocessing_list` stores `polys_dict_location[id] = preprocess[1]`.
- Because `Geolist` has already been dataset-normalized, `polys_dict_location` is the dataset-normalized geometry, not the raw CRS geometry.

What location branch actually learns:

- It does not use centroid coordinates as the sole input.
- It uses polygon/line/point geometry after dataset-level normalization.
- It samples SDF points around the normalized full geometry using the same SDF sampling machinery as the shape branch.
- It uses boundary samples, Gaussian near-boundary samples, length-proportional edge samples, and uniform grid samples.
- It passes SDF sample coordinates through `PositionalEncoder` inside `Geo2Vec_Model`.
- The learned embedding is an entity-level latent vector trained to reconstruct the SDF of the entity in normalized global coordinate space.

Interpretation:

- Location branch encodes absolute spatial position indirectly because the SDF sample coordinates remain in global normalized dataset coordinates.
- It also encodes relative geometry size weakly/implicitly because location geometries are not individually rescaled after dataset normalization.
- It still uses polygon geometry, not just centroid distance. Therefore "location embedding" is better described as a global-coordinate SDF embedding.

Location embedding dimension:

- In `list2vec`, location dimension is `Geo_dim` if provided, otherwise `args.z_size_location`.
- In external `main.py`, default location dimension is `z_size_location=256`.

Combination:

- `list2vec` concatenates embeddings with `np.concatenate((location_embedding, shape_embedding), axis=-1)` when both flags are true.
- `main.py` also concatenates location and shape arrays at the end.
- There is no summation or learned fusion layer at export.
- Separate outputs exist in `main.py` (`_loc`, `_shp`) and branch-specific runner scripts.

## 6. Embedding Export Pipeline

External repository:

- `list2vec(...)` returns:
  - shape only: `shape_embedding`;
  - location only: `location_embedding`;
  - both: concatenated `[location, shape]`;
  - neither: zero array.
- The returned arrays are full embedding-table weights. Because models are built with `n_poly=max_id + 2`, wrappers must slice to the input geometry count. FUSE wrappers do this.
- `main.py` saves `_loc.npy`, `_shp.npy`, and combined `_conbine.npy`.
- `learn_location_rep.py` saves `_loc.npy`.
- `learn_shape_rep.py` saves `_shp.npy`.

FUSE wrappers:

- `/members/dhnyu/fuse/scripts/embedding/run_gwanak_buildings_geo2vec_shape_full.py` exports wide Parquet columns `geo2vec_000...` for shape only.
- `/members/dhnyu/fuse/tests/gwanak_test/scripts/run_gwanak_single_model_lightweight.py` exports wide Parquet columns for shape only.
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/export_global_geo2vec_embeddings.py` reconstructs one `Geo2Vec_Model`, loads one checkpoint, and exports only that model's embedding table. It has no branch metadata or support for exporting separate shape/location tables.

## 7. Audit of Our Optimized Large-Scale Implementation

Verified files:

- `/members/dhnyu/fuse/tests/geo2vec_large_scale/geo2vec_large_scale_common.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/build_global_building_id_map.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/generate_disk_backed_sdf_samples.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/train_global_geo2vec_from_sample_cache.py`
- `/members/dhnyu/fuse/tests/geo2vec_large_scale/export_global_geo2vec_embeddings.py`

Verified behavior:

- `geo2vec_large_scale_common.py` sets canonical geometry path `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld.gpkg` and attributes path `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet`.
- `build_global_building_id_map.py` creates contiguous `geo2vec_internal_id` values sorted by `building_id`.
- `generate_disk_backed_sdf_samples.py` implements its own sampling pipeline and writes Parquet sample shards with `geo2vec_internal_id, x, y, sdf, split, sample_kind, sample_index`.
- `sample_geometry(...)` calls `normalize_for_shape(...)`.
- `normalize_for_shape(...)`:
  - extracts polygonal geometry;
  - applies dataset total-bounds normalization;
  - recenters each entity by its own bounding-box center;
  - rescales each entity by its own max side length.
- `train_global_geo2vec_from_sample_cache.py` trains one global `Geo2Vec_Model(n_poly=N)` from the cached samples.
- `export_global_geo2vec_embeddings.py` exports the single learned embedding table.

Current implementation status:

- Effective mode: shape-only.
- Location support in the optimized path: not implemented.
- Location-related code was not preserved in the optimized sampler; it was replaced with a shape-specific `normalize_for_shape`.
- `location_learning=True` cannot be enabled immediately in the optimized path because there is no `location_learning` flag, no location sample cache variant, no location model/checkpoint naming convention, and no combined exporter.

Required code changes for location embeddings:

- Add an explicit `embedding_kind` or `branch` argument with at least `shape`, `location`, and optionally `shape_location`.
- Add `normalize_for_location(...)` that applies only dataset/global normalization and does not per-entity center or scale geometry.
- Record normalization metadata in the sample manifest: source CRS, total bounds, normalization formula, width, height, branch, and sample config.
- Generate separate location SDF caches or add branch to cache directory names.
- Train separate models for shape and location, or implement a coordinated runner that trains both and exports concatenated embeddings.
- Update exporter to support:
  - shape-only;
  - location-only;
  - shape+location concatenation with prefixed columns such as `geo2vec_shape_000` and `geo2vec_location_000`.
- Update validation scripts to avoid assuming exactly `geo2vec_000...geo2vec_031` means shape-only.

Coordinate handling:

- External `preprocessing_list` normalizes all input coordinates to dataset bounds before either branch.
- FUSE large-scale `normalize_for_shape` uses GeoPackage total bounds for initial normalization and then per-entity shape normalization.
- CRS is assumed by project convention to be EPSG:5186, but the large-scale sampler does not enforce CRS in code. It uses `pyogrio.read_info(...)"total_bounds"` and geometry coordinates as given.

## 8. Risks of Using Raw EPSG:5186 Coordinates

Verified code risk:

- `PositionalEncoder._create_freq_bands(...)` comments indicate default frequency bands work for coordinates around `(-1, 1)`.
- Raw EPSG:5186 coordinates are meter-scale national projected coordinates, often hundreds of thousands of meters.
- Feeding raw EPSG:5186 coordinates directly to the positional encoder would cause high-frequency sin/cos features to oscillate extremely rapidly and make learning numerically and statistically unstable.
- Raw SDF distances in meters would also be on a very different scale from the current normalized SDF distances.

Do not use raw EPSG:5186 directly as Geo2Vec SDF coordinates.

Recommended normalization:

- Keep source geometry in EPSG:5186 for metric attributes such as area, perimeter, compactness, and distance calculations.
- For shape Geo2Vec:
  - global bounds normalization is optional but harmless before per-entity normalization;
  - per-entity center by bounding-box center;
  - divide by max(width, height);
  - store the removed scale values as explicit attributes.
- For location Geo2Vec:
  - transform all geometries into a stable national normalized coordinate system;
  - use one documented normalization for all runs, not per-chunk normalization;
  - recommended: subtract national total-bounds center and divide both axes by one common scale such as `max(width, height)` so metric aspect is preserved;
  - avoid independent `x` and `y` scaling if preserving distance geometry matters, because independent scaling distorts angles and distances.
- Store normalization metadata with every sample cache and embedding table.

Speculation/inference: the external repository's `normalize_geometries` independently scales x and y. That keeps coordinates bounded but does not preserve Euclidean distance when width and height differ. For nationwide Korea, a common isotropic scale is preferable if location embeddings are expected to represent distance relationships.

## 9. Recommended Final Geometry Embedding Design

Use a composed building representation rather than a single learned vector assumed to contain everything:

1. Shape channel:
   - Geo2Vec shape embedding trained from per-building normalized SDF.
   - Captures outline and morphology.

2. Location channel:
   - Either learned Geo2Vec location embedding from globally normalized geometries, explicit normalized centroid coordinates, or both.
   - Use with care in downstream prediction because it can encode regional identity and spatial leakage.

3. Explicit scale/morphometric channel:
   - Add at least `log_area`, `log_perimeter`, `log_bbox_width`, `log_bbox_height`, `aspect_ratio`, and optionally compactness/solidity/vertex count.
   - Compute these from EPSG:5186 geometry before normalization.
   - Standardize or robust-scale for downstream models.

Assessment by component:

| Component | Geo2Vec shape | Geo2Vec location | Recommendation |
|---|---:|---:|---|
| Outline/shape | Explicitly learned | Also present, but mixed with global position | Keep shape branch |
| Compactness/elongation/complexity | Explicitly/strongly learned if sampled well | Weak to moderate | Validate against morphometrics |
| Absolute location | Not represented | Learned implicitly through global normalized SDF coordinates | Add location channel or explicit centroid |
| National-scale spatial position | Not represented | Represented if one national normalization is used | Use national normalization only |
| Area/perimeter/size | Mostly removed by shape normalization | Weakly/implicitly present through dataset-normalized geometry | Add explicit scale variables |
| CRS/metric scale | Removed from model input | Normalized away | Preserve in explicit attributes |

Conclusion: area and perimeter should be added explicitly. Do not assume the shape branch learns scale. Do not rely on the location branch alone for stable, interpretable building size.

## 10. Proposed Experiment Matrix

Assume `Geo_dim=32` for each learned Geo2Vec branch unless otherwise stated. Explicit scale variables can start with 6D: `log_area`, `log_perimeter`, `log_bbox_width`, `log_bbox_height`, `aspect_ratio`, `compactness`.

| Experiment | Composition | Dimensionality | Required code modifications | Cost | Advantages | Disadvantages |
|---|---|---:|---|---|---|---|
| A. Shape only | `shape_geo2vec` | 32 | None for optimized path | Baseline | Already implemented; clean morphology signal; lowest cost | No absolute location; scale mostly removed |
| B. Shape + explicit scale | `shape_geo2vec + scale_features` | 38 if 32+6 | Add feature table and export/join logic; no new Geo2Vec training | Low | Captures morphology plus footprint size; interpretable | Still no absolute location |
| C. Location only | `location_geo2vec` | 32 | Implement `normalize_for_location`, location cache, location training/export | Similar to A or higher if samples denser | Tests whether global-coordinate SDF embedding carries spatial context | Spatial leakage risk; mixes location, shape, and size; not a pure geometry morphology vector |
| D. Shape + location | `shape_geo2vec + location_geo2vec` | 64 | Implement location path and concatenated exporter | About 2x A for training/cache if trained separately | Covers normalized outline plus national position | More storage and compute; location may dominate downstream tasks |
| E. Shape + location + explicit scale | `shape_geo2vec + location_geo2vec + scale_features` | 70 if 32+32+6 | Same as D plus feature table | About 2x A plus low feature cost | Most complete building representation among proposed options | Highest dimensionality; strongest leakage/control concerns |

Downstream evaluation strategy:

- Use identical train/test splits across all experiments.
- Include random split, spatial block cross-validation, and region/dong/city holdout.
- Evaluate both geometry reconstruction proxies and urban-science tasks.
- Geometry proxy targets:
  - `log_area`, `log_perimeter`, compactness, aspect ratio, solidity, vertex count, bbox area ratio.
- Spatial leakage diagnostics:
  - predict centroid coordinates or administrative region from embeddings;
  - compare random CV vs spatial holdout performance.
- Downstream task metrics:
  - regression RMSE/R2 for continuous outcomes;
  - classification AUC/F1 for categorical outcomes;
  - retrieval quality for nearest-neighbor morphology search.
- Use simple linear/ridge models and tree/boosted models. Linear performance reveals directly encoded information; nonlinear performance reveals recoverable information.

Recommended decision rule:

- If B outperforms A on scale-sensitive tasks without hurting spatial holdout, keep explicit scale.
- If D/E improve only random split but collapse under spatial holdout, treat location as leakage-prone context rather than a general geometry channel.
- If E is consistently best under spatial holdout and task-relevant, use E as the final building object geometry representation.

## 11. Concrete Next Steps

1. Preserve current shape-only outputs as baselines; do not overwrite them.
2. Add an explicit morphometric feature builder that writes Parquet keyed by `building_id`.
3. Add Experiment B first because it is low cost and directly addresses missing scale.
4. Extend `/members/dhnyu/fuse/tests/geo2vec_large_scale/generate_disk_backed_sdf_samples.py` with `--branch shape|location` and a verified `normalize_for_location(...)`.
5. Add manifest fields for branch and normalization metadata.
6. Train a small Gwanak or 50k national location-only smoke run before any long run.
7. Update export schema to use branch-specific prefixes.
8. Run the full A-E evaluation matrix on Gwanak first, then 100k/300k national subsets.
9. Only after location normalization and evaluation are stable, consider a nationwide location branch.

Final recommendation: the current FUSE Geo2Vec implementation should be documented as shape-only. The next scientifically defensible building geometry embedding is Experiment B immediately, followed by D/E only after implementing a controlled national location-normalized branch.
