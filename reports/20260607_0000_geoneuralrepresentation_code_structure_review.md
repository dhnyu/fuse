# GeoNeuralRepresentation Code Structure Review

This review is based on direct inspection of the cloned repository at `/members/dhnyu/fuse_external/GeoNeuralRepresentation` on 2026-06-07. The external repository was not modified.

## 1. Repository Overview

`GeoNeuralRepresentation` implements a Python/PyTorch project called **Geo2Vec: Shape- and Distance-Aware Neural Representation of Geospatial Entities**. The central idea is to represent each geospatial entity as a learnable latent vector and train a neural network to reconstruct a signed distance field (SDF) around that entity.

The repository is not primarily a downstream prediction package. It is mainly a **geometry and location representation learning** package. It can learn:

- **Shape embeddings**: entities are normalized individually around their own bounding boxes before SDF learning. This emphasizes local geometry independent of absolute location.
- **Location embeddings**: entities are kept in shared/global coordinates after possible dataset-level normalization. This emphasizes relative spatial position and distance structure.
- **Combined embeddings**: shape and location embeddings can be concatenated.

The implementation supports Shapely geometry objects including `Point`, `LineString`, `MultiLineString`, `Polygon`, and `MultiPolygon`. The code also handles polygons with holes when computing signed distance and boundary samples. Downstream evaluation utilities exist, but they are secondary: they train simple MLPs to predict class labels, edge counts, or pairwise distances from learned embeddings.

The research idea is close to implicit neural representation / DeepSDF-style learning for GIS entities: sample coordinates around each entity, compute true SDF values with Shapely, and optimize a network that receives `(entity_id, xy)` and predicts SDF. The entity embedding table is the desired representation.

## 2. Top-Level Directory Structure

Top-level files and directories inspected:

```text
/members/dhnyu/fuse_external/GeoNeuralRepresentation
├── .git/
├── .gitignore
├── .vscode/
├── __init__.py
├── data/
├── main.py
├── models/
├── pics/
├── readme.md
├── requirements.txt
├── runners/
├── tutorial.ipynb
└── utils/
```

Important components:

- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/readme.md`: high-level project description. It states that Geo2Vec generates embeddings for points, lines, polygons, multipolygons, and polygons with holes using SDF sampling and neural learning.
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/main.py`: full two-stage command-line training script. It first learns location embeddings, then shape embeddings, then concatenates both.
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/`: core model and sampling code. This is the source code most relevant for FUSE integration.
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/utils/`: data loading, geometry preprocessing, visualization, and representation evaluation helpers.
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/`: runnable scripts and a `list2vec` helper for converting an in-memory list of geometries to embeddings.
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/data/`: sample data and example trained outputs:
  - `ShapeClassification.gpkg`, 24,985,600 bytes, layer `test_5010_scaled_normalized`, 5,010 polygon features with `label`, `areas`, and `perimeter` fields.
  - `NYC_total_data.gpkg`, 10,964,992 bytes, layer `NYC_total_data`, 60,000 polygon features in EPSG:32118.
  - `Singapore_total_data.gpkg`, 37,890,709 bytes. In the current environment, `geopandas.read_file` and `ogrinfo` did not recognize this as a supported vector file.
  - `Singapore_total_data.gpkg.npy`, `test_location_loc.npy`, and `test_location.pth`, which appear to be embedding/model artifacts.
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/tutorial.ipynb`: notebook tutorial showing explicit loading, sampling, model construction, training, visualization, and saving of embeddings.
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/pics/visio144.png`: README figure.
- `/members/dhnyu/fuse_external/GeoNeuralRepresentation/requirements.txt`: UTF-16 encoded dependency list.

The repository is a script-style research codebase, not a packaged Python library. There is no `setup.py`, `pyproject.toml`, CLI package entry point, or test suite.

## 3. Main Python Modules and Their Roles

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/Geo2Vec.py`

This file defines the neural architecture, dataset wrapper, loss, and positional encoder.

Main classes and functions:

- `Geo2Vec_Model`: PyTorch `nn.Module`. Inputs are an entity ID tensor and an `xy` coordinate tensor. If IDs are `torch.long`, the model looks up a trainable embedding from `poly_embedding_layer`; otherwise it treats the first argument as an embedding vector directly. Output is a scalar predicted SDF value per input coordinate.
- `Geo2Vec_Dataset`: converts sampled SDF data into preallocated tensors containing entity IDs, sample coordinates, and true distances. This is used by PyTorch `DataLoader`.
- `SDFLoss`: absolute-error loss between predicted and true SDF, optionally plus latent-code L2 regularization.
- `PositionalEncoder`: Fourier-style coordinate encoder. It can use linearly spaced frequencies or log-spaced frequencies and can add a polar/radial Fourier feature block.
- `identity_collate`: returns the batch unchanged. In the current code this is used with `Geo2Vec_Dataset.__getitems__`, which already returns batched tensors for a list of indices.

Inputs:

- Entity IDs: integer IDs starting from zero in most repository workflows.
- Coordinates: two-column tensors, usually normalized or projected coordinates.
- Training samples: dictionary keyed by internal entity ID with `(sample_points, distances)`.

Outputs:

- Predicted SDF tensor from `Geo2Vec_Model.forward`.
- Learned entity embeddings available as `model.poly_embedding_layer.weight.data.cpu().numpy()`.

Connections:

- Used by `main.py`, `runners/learn_location_rep.py`, `runners/learn_shape_rep.py`, `runners/list2embedding.py`, and `tutorial.ipynb`.
- Receives samples from `models/MP_Sampling.py`.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/sample_function.py`

This file computes signed distances and creates SDF training samples around individual geometries.

Main functions:

- `signed_distance(pt, polygon)`: returns distance from a point to a Shapely geometry. For polygons and multipolygons, outside distances are positive and inside distances are negative. For lines and points, distances are nonnegative.
- `sample_perpendicular_at_fraction(...)`: samples a point at a fraction along a segment and offsets it perpendicularly by a random Gaussian distance.
- `sample_signed_distance(...)`: generates boundary and near-boundary samples for `Polygon`, `MultiPolygon`, `LineString`, `MultiLineString`, and `Point`.
- `sample_bounding_distance(...)`: generates a uniform grid over a bounding box and computes signed distance at every grid point.

Inputs:

- A Shapely geometry.
- Sampling hyperparameters such as `samples_perUnit`, `point_sample`, `sample_band_width`, and bounding box.

Outputs:

- `samples`: list of `(x, y)` pairs.
- `signed_distances`: list of float distances aligned to `samples`.

Connections:

- Called by `models/MP_Sampling.py`.
- Used indirectly by all training entry points.

Important implementation detail: for line and polygon sampling, the number of segment samples is proportional to Shapely length in the input coordinate units: `int(length * samples_perUnit)`. This makes CRS and coordinate scaling very important.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/MP_Sampling.py`

This file parallelizes SDF sampling across many geometries using Python `multiprocessing.Pool`.

Main functions:

- `sample(...)`: samples near-geometry SDF points for one entity.
- `sample_bounding(...)`: samples uniform bounding-box SDF points for one entity.
- `MP_sample(polys_dict, num_process, ...)`: computes the global bounding box of all geometries, samples near-boundary and bounding-grid points for every entity, and returns a dictionary keyed by entity ID.

Inputs:

- `polys_dict`: dictionary `{internal_integer_id: shapely_geometry}`.
- `num_process`: number of worker processes.
- sampling hyperparameters.

Outputs:

- `total_samples`: dictionary `{internal_integer_id: (samples, distances)}`.

Connections:

- Feeds `Geo2Vec_Dataset`.
- Called in all training scripts and in the notebook.

Scalability concern: `sample_bounding_distance` creates `samples_perUnit * samples_perUnit` grid points per entity. For large FUSE datasets, even `uniformed_sample_perUnit=20` means 400 extra grid samples per entity before boundary samples.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/utils/preprocess.py`

This file normalizes geometries and counts geometry edges.

Main functions:

- `count_edges(geom)`: counts edges for line and polygon geometries, including polygon holes and multipart geometries. Points return zero.
- `normalize_geometries(polys_list)`: dataset-level normalization. It translates all geometries by the shared minimum x/y and scales by total width and height into approximately `[0, 1]`.
- `poly_preprocess(poly)`: per-entity normalization. For shape representation, it centers each entity at its bounding-box center and scales by the maximum side length. For location representation, it also returns the original input geometry.
- `rotation(polygon)`: computes and applies a rotation based on the minimum rotated rectangle. This is defined but not used in the inspected training paths.

Outputs from `poly_preprocess`:

```python
(shape_normalized_geometry, original_geometry, scale, center_x, center_y)
```

The repository keeps only the first two values in most workflows:

- `polys_dict_shape[id] = preprocess[0]`
- `polys_dict_location[id] = preprocess[1]`

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/utils/data_loader.py`

This file loads data from GeoPackage, pickle, in-memory GeoDataFrame/DataFrame, or lists of Shapely geometries.

Main functions:

- `ensure_geodataframe(polys_scaled_normalized)`: converts a GeoDataFrame, DataFrame with `geometry`, shapely list/Series, or selected path types into a GeoDataFrame.
- `preprocessing_list(Geolist)`: accepts a list of Shapely geometries, dataset-normalizes them, then creates shape and location dictionaries.
- `load_data(dataset_name, visual=False)`: main loader used by scripts. It handles hard-coded names (`Building`, `MNIST`, `Singapore`, `NYC`), `.pkl`, `.gpkg`, and in-memory objects.

Important observations:

- `.gpkg` paths are supported directly in `load_data`.
- `ensure_geodataframe` only accepts `.shp`, `.json`, and `.geojson` when the input is a file path. This matters only when `load_data` falls through to `ensure_geodataframe`; `.gpkg` paths are handled earlier.
- Hard-coded `Singapore` and `NYC` branches expect `../data/Singapore_total_data.pkl` and `../data/NYC_total_data.pkl`, but those pickle files are not present in the clone.
- If total bounds exceed absolute value `1.1`, `load_data` dataset-normalizes all geometries and drops original attributes by creating `gpd.GeoDataFrame(geometry=...)`.
- Internal IDs are generated from `iterrows()` index values. External IDs are not preserved automatically.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/list2embedding.py`

This is the most useful integration surface for FUSE because it exposes `list2vec(Geolist, ...)`.

Main function:

```python
list2vec(
    Geolist,
    save_model_path=None,
    Geo_dim=128,
    num_epoch=None,
    location_learning=True,
    shape_learning=True,
    save_file_name=None,
    args=None
)
```

Inputs:

- `Geolist`: list of Shapely geometries.
- Optional model and embedding save paths.
- `Geo_dim`: latent dimension for each learned component.
- Flags to learn location, shape, or both.
- Optional argparse-like object to override sampling/training defaults.

Outputs:

- Returns a NumPy array of embeddings.
- If `save_file_name` is provided, writes `.npy` with `np.save`.
- If both location and shape are enabled, output dimension is `2 * Geo_dim`.

Connections:

- Calls `preprocessing_list`, `MP_sample`, `Geo2Vec_Dataset`, `Geo2Vec_Model`, and `SDFLoss`.
- Uses the same training logic as the scripts but is easier to call from a FUSE wrapper.

Caution: `list2vec` returns the full embedding-table weight. Because models are created with `n_poly=max_id + 2`, there may be two extra rows beyond the number of input geometries. FUSE wrappers should slice to `len(Geolist)` before joining IDs.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/main.py`

This is a combined command-line runner. It:

1. Parses default hyperparameters.
2. Loads data with `load_data`.
3. Learns location embeddings from `polys_dict_loc`.
4. Saves model state and location embedding when validation loss improves.
5. Learns shape embeddings from `polys_dict_shape`.
6. Saves model state and shape embedding when validation loss improves.
7. Concatenates location and shape embeddings and saves a combined `.npy`.

Defaults:

- location `z_size=256`, `hidden_size=256`, `num_layers=8`, `num_freqs=16`, `epochs=2`.
- shape `z_size=256`, `hidden_size=256`, `num_layers=8`, `num_freqs=8`, `epochs=2`.
- batch size `1024 * 20`.
- device is `cuda` if available, else `cpu`.

Caution: the default `file_path` is `data\merged_buildings_normalized.gpkg`, using Windows backslashes and a file that is not present in the clone.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/learn_location_rep.py`

This script trains location embeddings only. It is similar to the location half of `main.py`.

Default input is `data\ShapeClassification.gpkg`; on Linux this backslash path is not the same as `data/ShapeClassification.gpkg`, so users should pass `--file_path data/ShapeClassification.gpkg`.

Output:

- `.pth` model state.
- `_loc.npy` NumPy embedding array.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/learn_shape_rep.py`

This script trains shape embeddings only. It is similar to the shape half of `main.py`.

Default input is `..\data\merged_buildings_normalized.gpkg`, which does not exist in the clone and uses Windows path syntax.

Output:

- `.pth` model state.
- `_shp.npy` NumPy embedding array.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/utils/test_representation.py`

This file contains downstream evaluation utilities. It is not required for embedding generation.

Main components:

- `Distance_MLP` and `DistanceDataset`: learn pairwise distance prediction from two entity embeddings.
- `MLP` and `MLP_relationship`: simple downstream networks.
- `train_regression_model`, `train_classification_model`.
- `test_representation_embed`: evaluates embeddings on labels such as class labels or edge counts.
- `test_distance`: samples geometry pairs, computes actual Shapely distances, and evaluates whether embeddings can predict those distances.

### `/members/dhnyu/fuse_external/GeoNeuralRepresentation/utils/visualization.py`

This file plots geometries and SDF fields. It is useful for manual diagnostics and tutorial visualization, not for production embedding generation.

## 4. Execution Entry Points

Primary entry points:

### `tutorial.ipynb`

The notebook is the clearest research demonstration. It:

- imports the model, data loader, sampler, and visualization modules.
- loads `data/ShapeClassification.gpkg`.
- samples SDF points.
- constructs `Geo2Vec_Model`.
- trains shape and location models separately.
- extracts embeddings with:

```python
shape_embedding = model.poly_embedding_layer.weight.data[:len(polys_dict_shape)].cpu().numpy()
location_embedding = model.poly_embedding_layer.weight.data[:len(polys_dict_loc)].cpu().numpy()
```

The notebook explicitly slices to the number of geometries, avoiding the extra embedding rows from `max_id + 2`.

### `runners/list2embedding.py`

This is the best programmatic entry point for FUSE. It accepts a list of Shapely geometries:

```python
from runners.list2embedding import list2vec
emb = list2vec(geometries, Geo_dim=128, num_epoch=2, shape_learning=True, location_learning=True)
emb = emb[:len(geometries)]
```

This call produces embeddings. With both shape and location enabled and `Geo_dim=128`, expected output width is 256 before considering any extra rows.

### `main.py`

Example command, adjusted for Linux paths:

```bash
cd /members/dhnyu/fuse_external/GeoNeuralRepresentation
python main.py \
  --file_path data/ShapeClassification.gpkg \
  --save_file_name data/shapeclassification_review_test.pth \
  --epochs_location 1 \
  --epochs_shape 1 \
  --test_representation_location False \
  --test_representation_shape False \
  --visualSDF_location False \
  --visualSDF_shape False
```

This should train both location and shape embeddings if the Python environment has PyTorch and the other dependencies installed.

### `runners/learn_location_rep.py`

Trains only location embeddings and writes `_loc.npy`.

### `runners/learn_shape_rep.py`

Trains only shape embeddings and writes `_shp.npy`.

### `runners/test.py`

Downstream evaluation script using hard-coded absolute paths from the original author environment. It is not directly reusable without editing or wrapping.

## 5. Input Data Format

The repository expects geospatial entities as Shapely geometries, usually inside a GeoDataFrame or a Python list.

Supported input paths and objects:

- `.gpkg` path through `load_data`.
- `.pkl` path through `load_data`, expected to contain records with a `shape` key.
- GeoDataFrame.
- pandas DataFrame with a `geometry` column.
- list or pandas Series of Shapely geometries.
- `.shp`, `.json`, and `.geojson` through `ensure_geodataframe` in fallback paths.

Supported geometry types in core sampling:

- `Point`: represented by its coordinate plus Gaussian nearby samples; distances are nonnegative.
- `LineString`: represented by line vertices, near-vertex samples, and perpendicular samples along segments; distances are nonnegative.
- `MultiLineString`: recursively samples each part.
- `Polygon`: represented by exterior vertices, interior ring vertices, and near-boundary/perpendicular samples; inside distances are negative.
- `MultiPolygon`: recursively samples each polygon part while computing distances to the full multipolygon.

Geometry lists:

- `preprocessing_list(Geolist)` dataset-normalizes the list, enumerates geometries from `0`, and returns internal dictionaries for shape and location learning.

Coordinate arrays:

- Model training uses tensors of sample coordinates shaped like `(N, 2)`.
- Raw user inputs are not coordinate arrays; they are Shapely geometries that are sampled into coordinate arrays.

CRS assumptions:

- No CRS is enforced.
- SDF distances use Shapely distance in the input coordinate units.
- `load_data` checks bounds and normalizes if absolute bounds exceed `1.1`.
- `preprocessing_list` always dataset-normalizes input geometries.
- The positional encoder comments indicate the frequency defaults are intended to work for coordinates around `(-1, 1)`.

For FUSE, source geometries should be projected to EPSG:5186 before any intended metric interpretation. However, because GeoNeuralRepresentation often normalizes coordinates before learning, the meaning of learned distances depends on the chosen preprocessing strategy.

## 6. Output Data Format

The repository outputs:

- PyTorch model state dictionaries as `.pth`.
- NumPy embedding arrays as `.npy`.
- Optional Matplotlib visualizations in interactive contexts.

Embedding format:

- `model.poly_embedding_layer.weight.data.cpu().numpy()`.
- Shape: approximately `(n_entities + 2, z_size)` because models are initialized with `n_poly=max_id + 2`.
- `list2vec` with both location and shape enabled concatenates arrays along the last dimension, producing approximately `(n_entities + 2, 2 * Geo_dim)`.
- `main.py` default combined embedding dimension is 512 because location and shape are each 256-dimensional.
- `list2vec` default `Geo_dim=128`, so combined dimension is 256.

Object ID preservation:

- The repository uses internal integer IDs generated by enumeration or GeoDataFrame row index.
- Original object IDs are not preserved in output files.
- Output `.npy` rows can be mapped back only if the caller records the input order and slices off extra rows.

Recommended FUSE output mapping:

- Preserve a stable FUSE ID column externally, such as `building_id`, `poi_id`, `road_id`, or `grid_id`.
- Create an explicit `geo2vec_internal_id` equal to input row order.
- Store embeddings in Parquet with both IDs.

## 7. Model Architecture and Training Logic

Architecture:

- `Geo2Vec_Model` has a trainable `torch.nn.Embedding(n_poly, z_size)` table. Each entity gets one latent vector.
- Coordinates are transformed by `PositionalEncoder`.
- The encoded coordinate and entity embedding are concatenated.
- The first MLP block maps `(encoded_xy + z)` to `hidden_size`.
- A `ModuleList` of repeated intermediate blocks concatenates the original `(encoded_xy + z)` to the current hidden state before each block.
- Final linear layer maps hidden state to one scalar SDF prediction.
- Activations are `LeakyReLU` with default negative slope `0.01`.

Positional encoding:

- If `log_sampling=True`, frequencies are powers of two times pi.
- If `log_sampling=False`, frequencies are linearly spaced from 1 to 6.
- If `polar_fourier=True` and `input_dims == 2`, the encoder appends radial Fourier features using `r = sqrt(x^2 + y^2)`.

Loss:

- `SDFLoss` uses L1 distance between predicted and true SDF.
- Optional latent-code regularization adds `mean(latent_code.pow(2)) * code_reg_weight`.
- Location defaults often set `code_reg_weight=0.0`.
- Shape defaults often set `code_reg_weight=1.0`.

Optimizer:

- `torch.optim.Adam(model.parameters(), lr=0.001)`.
- No learning-rate scheduler is implemented.

Training loop:

- SDF samples are generated before training.
- `Geo2Vec_Dataset` preallocates all samples into tensors.
- Dataset is split into train/validation using `torch.utils.data.random_split`.
- Best validation loss triggers saving of model state and embedding array.
- Training and validation losses are printed per epoch.

Batch processing:

- Default batch size is `1024 * 20`.
- Script DataLoaders use `num_workers` defaults around 8.
- `list2vec` uses `num_workers=0` in DataLoader but uses multiprocessing during sampling.

GPU/CPU behavior:

- Device defaults to `cuda` if `torch.cuda.is_available()` else `cpu`.
- Tensors and model are moved to `device`.
- `pin_memory=True` is set in DataLoaders even when CPU may be used.

Known unclear or risky details:

- No deterministic random seed is set in the repository.
- Sample count depends on geometry lengths after normalization/projection.
- The code saves full embedding tables, including possible extra rows.
- Command-line boolean parsing uses `type=bool`, which can behave unexpectedly because non-empty strings may evaluate as `True`.
- There is no checkpoint metadata recording geometry IDs, CRS, normalization parameters, or hyperparameters.

## 8. Dependencies and Environment

`requirements.txt` is UTF-16 encoded and contains:

```text
geopandas==0.14.4
osmnx==1.9.4
shapely==2.0.6
torch==2.7.1+cu128
tqdm
multiprocessing
```

Imports observed in code also require:

- `numpy`
- `pandas`
- `pyarrow`
- `matplotlib`
- standard library modules: `os`, `gc`, `argparse`, `random`, `pickle`, `multiprocessing`, `functools`

Current environment check from `/members/dhnyu/fuse_external/GeoNeuralRepresentation`:

- `python --version`: Python 3.14.0.
- `torch`: not installed in the active `rgeo` environment.
- `geopandas`: 1.1.3 installed.
- `shapely`: 2.1.2 installed.
- `numpy`: 2.4.6 installed.
- `pandas`: 2.3.3 installed.
- `pyarrow`: 22.0.0 installed.
- `tqdm`: 4.67.1 installed.
- `matplotlib`: 3.10.9 installed.
- `pyogrio`: 0.12.1 installed.

Compatibility concerns for FUSE:

- PyTorch support for Python 3.14 may be limited or unavailable depending on the exact build. A separate Python environment, likely Python 3.10 to 3.12, should be used.
- The pinned `torch==2.7.1+cu128` usually requires installing from the PyTorch CUDA wheel index, not just plain `pip install -r requirements.txt`.
- `multiprocessing` is part of the Python standard library and should not be listed as a pip dependency.
- `osmnx` is listed but not used by the inspected source files.
- The UTF-16 requirements file may confuse some tooling.

## 9. Minimal Reproducible Example

The smallest repository-native example is `data/ShapeClassification.gpkg`, because it is present and readable. It contains 5,010 normalized polygon features with labels.

A minimal programmatic example, assuming a working PyTorch environment:

```python
import sys
import geopandas as gpd

repo = "/members/dhnyu/fuse_external/GeoNeuralRepresentation"
sys.path.insert(0, repo)

from runners.list2embedding import list2vec

gdf = gpd.read_file(f"{repo}/data/ShapeClassification.gpkg").head(100)
geoms = list(gdf.geometry)

emb = list2vec(
    geoms,
    Geo_dim=32,
    num_epoch=1,
    location_learning=False,
    shape_learning=True,
)
emb = emb[:len(geoms)]
print(emb.shape)
```

This would train a small shape-only embedding model on 100 polygons and return a NumPy array. I did not run it because the active Python environment does not have `torch` installed.

An equivalent script command, also requiring PyTorch:

```bash
cd /members/dhnyu/fuse_external/GeoNeuralRepresentation
python runners/learn_shape_rep.py \
  --file_path data/ShapeClassification.gpkg \
  --save_file_name data/shapeclassification_shape_test.pth \
  --epochs 1 \
  --num_process 2 \
  --num_workers 0 \
  --samples_perUnit 20 \
  --point_sample 3 \
  --uniformed_sample_perUnit 5 \
  --visualSDF False \
  --test_representation False
```

However, because the script uses `type=bool`, the `False` arguments may still parse as true. For reliable FUSE usage, prefer a wrapper that imports functions and constructs an `args` object directly.

## 10. Relevance to the FUSE Project

Relevant FUSE assets:

- `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld.gpkg` - 3,833,729,024 bytes.
- `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet` - 1,034,196,055 bytes.
- `/members/dhnyu/fusedatalarge/processed/korea_togieeum_polygon.gpkg` - 957,370,368 bytes.
- `/members/dhnyu/fusedatalarge/processed/korea_togieeum_polygon_attributes.parquet` - 33,903,346 bytes.
- `/members/dhnyu/fusedatalarge/processed/korea_poi_ngii_point.gpkg` - 1,175,846,912 bytes.
- `/members/dhnyu/fusedatalarge/processed/korea_poi_ngii_attributes.parquet` - 456,341,155 bytes.
- `/members/dhnyu/fusedata/osm/canonical`
- `/members/dhnyu/fusedata/streetview`
- `/members/dhnyu/fusedatalarge/streetview`

Directly compatible after subsetting:

- Building polygons in `korea_buildings_vworld.gpkg`: compatible with `Polygon` and `MultiPolygon` support. This is likely the strongest initial match because Geo2Vec shape embeddings can encode footprint geometry.
- Togieeum polygon POIs in `korea_togieeum_polygon.gpkg`: compatible with polygon/multipolygon support. Good for shape and location embeddings of polygonal places.
- NGII point POIs in `korea_poi_ngii_point.gpkg`: compatible with `Point` support, but point-only shape embeddings are likely less informative because `poly_preprocess` collapses each point to `(0, 0)` for shape representation.
- OSM canonical data: likely compatible if point, polygon, and road geometries are read as Shapely objects. Roads as `LineString`/`MultiLineString` are supported.

Requires preprocessing:

- All large GeoPackages require spatial and/or row subsetting before loading into memory.
- All FUSE geometries should be filtered to valid, non-empty geometries.
- Multipart and geometry-collection cases should be inspected. The sampler supports `MultiPolygon` and `MultiLineString`, but not arbitrary `GeometryCollection` in `sample_signed_distance`.
- ID columns must be preserved outside the external repository because its internal IDs are just row order.
- CRS should be standardized. FUSE preferred CRS is EPSG:5186. GeoNeuralRepresentation does not enforce or record CRS.
- Attribute Parquets should not be loaded into GeoNeuralRepresentation unless needed for filtering or ID joins.

Not directly relevant:

- Streetview images and crop files are not geometry inputs for this repository.
- Streetview metadata could be used later to attach learned spatial embeddings to images by nearest building, road, POI, or grid cell, but GeoNeuralRepresentation itself does not process imagery.

## 11. Recommended FUSE Integration Strategy

Recommended first experiment:

- Start with **building footprints**, not POIs or roads.
- Use a small Seoul or district-scale subset from `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld.gpkg`.
- Target 1,000 to 10,000 valid polygons for the first run.
- Use shape-only embeddings first, because building footprints are the cleanest match to the repository's geometry representation.
- Use `Geo_dim=64` or `Geo_dim=128`, `num_epoch=1` to `3`, and reduced sampling parameters for the first validation run.

Preferred spatial unit:

- `building_id` as the stable entity key for building embeddings.
- Later experiments can use polygon POI IDs, road IDs, or regular grid IDs.

ID preservation:

- Build a FUSE wrapper that creates:
  - `building_id`
  - `geo2vec_internal_id` as zero-based row order
  - `geometry`
- Pass only `list(gdf.geometry)` into `list2vec`.
- Slice embeddings with `emb[:len(gdf)]`.
- Join embeddings back to IDs by `geo2vec_internal_id`.

Recommended output path:

- Large processed outputs should go to the flat directory `/members/dhnyu/fusedatalarge/processed`.
- Suggested first test output:
  - `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld_geo2vec_test_embeddings.parquet`
- Suggested later canonical output:
  - `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld_geo2vec_embeddings.parquet`

Recommended Parquet schema:

```text
building_id: string or int64, matching canonical attributes
geo2vec_internal_id: int64
source_dataset: string
geometry_type: string
crs_epsg: int32
embedding_kind: string              # "shape", "location", or "shape_location"
geo2vec_dim: int32                  # per-component dimension
geo2vec_total_dim: int32
geo2vec_model_tag: string
embedding: list<float32>            # preferred compact vector column if downstream tools support it
```

If list columns are inconvenient, use wide columns:

```text
geo2vec_000: float32
geo2vec_001: float32
...
```

For analytics and model training, Parquet is preferred over CSV. Geometry should not be duplicated in the embedding Parquet; geometry remains in the canonical GeoPackage and can be joined by ID.

Wrapper strategy:

- Wrap the external repository from FUSE scripts instead of editing `/members/dhnyu/fuse_external/GeoNeuralRepresentation`.
- Use `sys.path.insert(0, "/members/dhnyu/fuse_external/GeoNeuralRepresentation")` in a FUSE script or run from the external repo working directory.
- Construct an explicit args object rather than using command-line defaults.
- Record all hyperparameters, source paths, row filters, CRS, and random seeds in a sidecar metadata file or in Parquet metadata.

Suggested first FUSE wrapper behavior:

1. Read a small building subset from `korea_buildings_vworld.gpkg`.
2. Reproject to EPSG:5186 if needed.
3. Filter empty/invalid geometries and repair simple invalid polygons if appropriate.
4. Preserve `building_id` and add `geo2vec_internal_id`.
5. Call `list2vec` shape-only with conservative sampling settings.
6. Slice extra rows.
7. Write embeddings to Parquet.
8. Save model state to `/members/dhnyu/fusedatalarge/processed` only if needed; otherwise keep embeddings as the canonical output.

## 12. Risks, Unclear Points, and Questions

- **CRS handling**: the repository does not preserve or validate CRS. Distances depend on coordinate units before normalization.
- **Normalization semantics**: `preprocessing_list` always dataset-normalizes input geometries. Shape embeddings then use per-entity normalization. This may remove absolute size information unless location embeddings or separate attributes are retained.
- **Object ID preservation**: original IDs are not preserved. FUSE must manage ID mapping externally.
- **Extra embedding rows**: model embedding tables are sized as `max_id + 2`; output arrays may contain rows not corresponding to real entities.
- **Scalability**: all samples are materialized in memory in `Geo2Vec_Dataset`. This is risky for millions of buildings.
- **Sampling cost**: boundary samples scale with geometry length and `samples_perUnit`; bounding samples scale with `uniformed_sample_perUnit ** 2` per entity.
- **Multiprocessing memory**: large geometry dictionaries are passed through Python multiprocessing. This may cause high memory use.
- **GPU support**: code supports CUDA if PyTorch sees a GPU, but the active FUSE Python environment currently lacks PyTorch.
- **Python compatibility**: the current environment is Python 3.14, while PyTorch CUDA wheels may require an older supported Python version.
- **Geometry validity**: invalid polygons may cause Shapely distance/sampling failures or silent distance value `0` from the exception handler.
- **GeometryCollection handling**: edge counting supports `GeometryCollection`, but SDF sampling does not.
- **Point shape embeddings**: point shape preprocessing collapses every point to `(0, 0)`, so shape-only point embeddings may be uninformative.
- **Pretrained weights**: no general pretrained model is provided. The `.pth` and `.npy` files in `data/` appear to be example artifacts, not documented pretrained weights for FUSE use.
- **Reproducibility**: no seeds are set for Python `random`, NumPy, PyTorch, DataLoader splitting, or multiprocessing.
- **Command-line defaults**: some defaults reference missing files or use Windows path separators.
- **Boolean CLI flags**: `type=bool` makes disabling evaluation/visualization from CLI unreliable.
- **Sample data issue**: `data/Singapore_total_data.gpkg` was not readable by `geopandas.read_file` in the current environment, despite its name.

Main questions before full-scale FUSE generation:

- Should FUSE use shape-only embeddings, location-only embeddings, or concatenated shape-location embeddings for the first downstream task?
- Should absolute footprint size be encoded through Geo2Vec location learning, separate attributes, or both?
- What maximum number of entities and samples per entity can fit in the target GPU/CPU memory?
- Should we train separate models by city/region to control memory, or one national model for comparable embeddings?
- What stable ID columns exist in each canonical FUSE GeoPackage and attributes Parquet?
- Should embeddings be stored as list-vector Parquet columns or wide float columns for the intended downstream tooling?
