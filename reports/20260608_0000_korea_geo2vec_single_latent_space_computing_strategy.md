# Korea Geo2Vec Single-Latent-Space Computing Strategy

Generated: `2026-06-08 KST`

## Executive Summary

Nationwide Korea building Geo2Vec training is methodologically feasible in one shared latent space, but the current GeoNeuralRepresentation implementation is not operationally safe at this scale. The correct design is not to train independent chunk models. The correct design is to chunk only geometry I/O, SDF sampling, sample caching, and embedding export while all minibatches update one persistent `Geo2Vec_Model` and one global entity embedding table with `n_poly = total_buildings`.

The current national building source is:

- Geometry: `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld.gpkg`
- Layer: `buildings`
- CRS: `EPSG:5186`
- Feature count: `14,388,938`
- Geometry type: multipolygon
- Key column: `building_id`
- Attribute parquet rows: `14,388,938`

The main bottleneck is unlikely to be the fp32 embedding table at `Geo_dim=32` or `64`. For 15M entities, the table is about `1.79 GiB` at 32D and `3.58 GiB` at 64D. The harder constraints are signed-distance sampling throughput, Python object materialization, disk cache size, DataLoader throughput, checkpoint size, failure recovery, and final export.

## 1. Current Limitation

The current implementation should not be used directly for nationwide Korea training.

The FUSE Gwanak wrapper calls `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/list2embedding.py::list2vec`. The shape branch does the following:

1. Accepts a complete Python list of geometries.
2. Calls `preprocessing_list(Geolist)`, which normalizes the whole list and creates `polys_dict_shape` and `polys_dict_location` dictionaries for every entity.
3. Calls `MP_Sampling.MP_sample(polys_dict_shape, ...)`.
4. `MP_sample` computes a global bounding box over all polygons, partitions by `hash(k) % division`, then accumulates `total_samples` as a Python dictionary keyed by polygon id.
5. `Geo2Vec_Dataset(samples, polys_dict_shape.keys())` preallocates CPU tensors for all ids, xy samples, and SDF distances, copying from the Python dictionary.
6. `random_split` creates train/validation subsets.
7. The DataLoader moves only minibatches to GPU.
8. At the end, `model.poly_embedding_layer.weight.data.cpu().numpy()` extracts the full embedding table.

Unsafe national-scale properties:

- **All-at-once geometry loading:** a complete geometry list/GDF is expected before preprocessing.
- **All-at-once geometry normalization:** `normalize_geometries` inspects all bounds and returns a full normalized list.
- **All-at-once SDF generation:** `MP_sample` materializes every entity's samples before training starts.
- **Python dictionary sample materialization:** samples are stored as nested dictionaries/lists/tuples/Python floats, with much higher overhead than the raw numeric arrays.
- **CPU tensor duplication:** `Geo2Vec_Dataset` copies the already materialized Python samples into contiguous CPU tensors.
- **No streaming dataset:** there is no `IterableDataset`, memory-mapped dataset, Arrow scanner, or shard-aware sampler.
- **No resumable checkpointing:** current save behavior is only best-model `state_dict`; it omits optimizer state, RNG state, sampler position, shard manifest, and id-map checksums.
- **Full embedding extraction at the end:** the whole entity table is copied to CPU as a NumPy array before output construction.

This is acceptable for Gwanak-scale experiments. It is not robust for roughly `14.4M` buildings and `780M-867M` SDF samples.

## 2. Correct Large-Scale Logic

The desired nationwide logic is:

1. Build a stable global id map:
   - Input key: `building_id`
   - Output key: `geo2vec_internal_id`
   - Domain: contiguous `0..N-1`
   - Store as parquet with checksums and deterministic ordering.
2. Initialize exactly one global model:
   - `Geo2Vec_Model(n_poly=N, z_size=Geo_dim, ...)`
   - Move the model, including `poly_embedding_layer`, to the selected device if memory permits.
3. Process geometry in chunks for I/O and sampling:
   - Read a bounded shard of building geometries.
   - Join to the global id map.
   - Normalize each geometry for shape learning with the same semantics as the current Geo2Vec shape branch.
   - Generate deterministic SDF samples per building or read them from a disk-backed cache.
4. Feed sample minibatches to the same model:
   - Each batch contains `geo2vec_internal_id`, `xy`, and `sdf`.
   - Every batch calls `loss.backward()` and `optimizer.step()` on the same model and optimizer.
   - The same global embedding table row is updated whenever that building appears.
5. Checkpoint regularly:
   - Save model, optimizer, epoch, global step, shard position, RNG states, config, id-map checksum, and sample-cache manifest checksum.
6. Export embeddings incrementally:
   - Iterate over the embedding table by id ranges.
   - Join ids back to `building_id`.
   - Write partitioned or row-grouped parquet without building a 15M-row DataFrame in memory.

Chunking is allowed for data access, sample generation, sample cache files, and output writing. Chunking is not allowed as independent Geo2Vec model training, because independent chunk models produce unaligned latent spaces.

Correct training topology:

```text
global id map -> one Geo2Vec_Model(N) -> shard/minibatch 1 -> shard/minibatch 2 -> ... -> final global embeddings
```

Incorrect topology:

```text
chunk 1 -> model A -> embeddings A
chunk 2 -> model B -> embeddings B
chunk 3 -> model C -> embeddings C
```

## 3. Strategy Comparison

### A. Online Streaming Sampler

Generate SDF samples on the fly from geometry chunks during training.

Pros:

- Avoids storing a huge full sample cache.
- Can start training after the first chunk is sampled.
- Reduces long-lived disk usage.
- Good fit when sample settings are still changing.

Cons:

- Signed-distance sampling can starve the GPU unless CPU workers stay ahead.
- Determinism is harder with multiprocessing unless each building has an id-derived seed.
- Resuming mid-shard requires precise sampler state or deterministic regeneration.
- Repeated epochs repeat expensive sampling unless cached.
- Validation split must be deterministic per sample or per building.

Determinism requirement:

- Use `seed_i = hash64(base_seed, building_id, geo2vec_internal_id, sample_config_version)`.
- Do not rely on multiprocessing result order.
- Use a local RNG per building or per sample block, not global `random`/`np.random` state.

Best use:

- Initial 50k, 100k, and 300k engineering validation where disk cache design is still evolving.

### B. Disk-Backed Sample Cache

Precompute samples into partitioned Parquet/Arrow, Zarr, or memmap files, then train from that cache using an `IterableDataset` or indexable dataset.

Pros:

- Separates expensive sampling from model training.
- Reproducible if cache files and manifest are immutable.
- Training can resume by shard and row-group position.
- Multiple model settings can reuse the same sample cache.
- Enables validation of sample counts, finite values, id coverage, and compression before training.

Cons:

- Large storage requirement.
- Precompute can take a long time before any model training starts.
- Sample schema/versioning must be strict.
- Parquet row groups are good for scanning but not ideal for random per-sample access.
- Full-cache shuffle across 780M+ rows requires careful sharding strategy.

Recommended cache schema:

```text
geo2vec_internal_id int64
x float32
y float32
sdf float32
split uint8                 # optional: 0=train, 1=val
sample_kind uint8           # optional: boundary, gaussian, grid, etc.
sample_index int32          # optional within-building deterministic index
```

Storage format:

- Parquet is preferred for tabular analytical data and manifest inspection.
- Arrow IPC or memmap can be faster for sequential training reads.
- Zarr is reasonable if chunked multidimensional access becomes useful.
- Use partitioned flat files under `/members/dhnyu/fusedatalarge/processed` only if creating large processed outputs; for prototype validation outputs, use `/members/dhnyu/fusedata/gwanak_test/validation/`.

Best use:

- 300k and larger experiments, especially if repeating training runs.

### C. Hybrid Cache

Cache part of the sample information and recompute the rest.

Variants:

- Cache `geo2vec_internal_id`, `x`, `y`, `sample_kind`, and `sample_index`; recompute SDF from geometry at training time.
- Cache normalized geometry-derived boundary points or reusable local grids; generate noisy samples deterministically during training.
- Cache WKB-normalized geometries plus deterministic sampling metadata.

Pros:

- Reduces disk size versus full `id + xy + sdf`.
- Preserves reproducible sample coordinates.
- Allows SDF precision or truncation settings to change without regenerating coordinates.

Cons:

- Recomputing distance can still be the dominant CPU cost.
- Training remains dependent on geometry access.
- More complex cache invalidation because geometry, normalization, and sample config all affect results.

Best use:

- When full SDF cache storage is too large but deterministic sample coordinates are needed.

### D. Two-Stage Strategy

Stage 1: create global id map and deterministic samples.

Stage 2: train one global model from disk-backed samples.

Stage 3: export embeddings incrementally.

Pros:

- Cleanest failure isolation.
- Sampling and training can be profiled independently.
- Cache validation can catch geometry problems before GPU training.
- Training resume is simpler because the input cache is immutable.
- Best reproducibility story.

Cons:

- Requires enough disk for sample cache.
- Slower first result because precompute precedes training.
- Requires careful manifest/versioning design.

Best use:

- Recommended path before any 1M+ or national run.

### E. True Out-of-Sample Geometry Encoder Alternative

The current Geo2Vec implementation is entity-table based: every building has a learned row in `poly_embedding_layer`, and the shared SDF decoder regularizes those rows into one latent space. It is not a function that directly maps a new polygon to an embedding.

A future redesign could train an encoder that consumes polygon geometry, rasterized footprint, sampled boundary sequence, or graph representation and predicts a latent code. That would support out-of-sample inference and could avoid a 15M-row embedding table.

This is a future model redesign, not an immediate wrapper. It changes the learning problem and should not replace the current single-table Geo2Vec workflow until validated against Gwanak random split, spatial block CV, and dong holdout results.

## 4. Memory and Storage Estimates

Definitions:

- `GiB = 1024^3 bytes`
- Entity table fp32: `N * Geo_dim * 4`
- Adam state for embeddings: parameter + first moment + second moment, approximately `N * Geo_dim * 12`
- Gradients: approximately `N * Geo_dim * 4` when allocated
- Checkpoint embedding portion with Adam: approximately `N * Geo_dim * 12`, excluding decoder, metadata, serialization overhead, and possible temporary copies
- Output embedding parquet raw payload: `building_id/int64 equivalent + Geo_dim float32`; actual parquet depends on `building_id` string storage, row groups, and compression
- Sample count planning uses both `52` train samples/entity and `57.8` total samples/entity, matching prior Gwanak observations and the `780M-867M` national estimate.

### Entity Table and Optimizer

| Buildings | Geo_dim | Entity table fp32 | Entity + Adam | Entity + Adam + grad | Checkpoint embedding portion | Raw output payload |
|---:|---:|---:|---:|---:|---:|---:|
| 100k | 32 | 0.012 GiB | 0.036 GiB | 0.048 GiB | 0.036 GiB | 0.013 GiB |
| 100k | 64 | 0.024 GiB | 0.072 GiB | 0.095 GiB | 0.072 GiB | 0.025 GiB |
| 300k | 32 | 0.036 GiB | 0.107 GiB | 0.143 GiB | 0.107 GiB | 0.038 GiB |
| 300k | 64 | 0.072 GiB | 0.215 GiB | 0.286 GiB | 0.215 GiB | 0.074 GiB |
| 1M | 32 | 0.119 GiB | 0.358 GiB | 0.477 GiB | 0.358 GiB | 0.127 GiB |
| 1M | 64 | 0.238 GiB | 0.715 GiB | 0.954 GiB | 0.715 GiB | 0.246 GiB |
| 5M | 32 | 0.596 GiB | 1.788 GiB | 2.384 GiB | 1.788 GiB | 0.633 GiB |
| 5M | 64 | 1.192 GiB | 3.576 GiB | 4.768 GiB | 3.576 GiB | 1.229 GiB |
| 15M | 32 | 1.788 GiB | 5.364 GiB | 7.153 GiB | 5.364 GiB | 1.900 GiB |
| 15M | 64 | 3.576 GiB | 10.729 GiB | 14.305 GiB | 10.729 GiB | 3.688 GiB |

These estimates exclude decoder parameters, batch activations, PyTorch allocator reserve, pinned-memory buffers, validation batches, and serialization duplication. The lightweight Gwanak decoder is small relative to the entity table.

### Sample Cache Size, Raw Numeric Payload

Full sample schema:

- `id int64`: 8 bytes
- `xy float32[2]`: 8 bytes
- `sdf float32`: 4 bytes
- Total: 20 bytes/sample

XY-only schema:

- `id int64`: 8 bytes
- `xy float32[2]`: 8 bytes
- Total: 16 bytes/sample

Float16 variants:

- `id int64 + xy float16[2] + sdf float16`: 14 bytes/sample
- `id int64 + xy float16[2]`: 12 bytes/sample

| Buildings | Samples/entity | Samples | id+xy32+sdf32 | id+xy32 only | id+xy16+sdf16 | id+xy16 only |
|---:|---:|---:|---:|---:|---:|---:|
| 100k | 52.0 | 5.20M | 0.097 GiB | 0.077 GiB | 0.068 GiB | 0.058 GiB |
| 100k | 57.8 | 5.78M | 0.108 GiB | 0.086 GiB | 0.075 GiB | 0.065 GiB |
| 300k | 52.0 | 15.60M | 0.291 GiB | 0.232 GiB | 0.203 GiB | 0.174 GiB |
| 300k | 57.8 | 17.34M | 0.323 GiB | 0.258 GiB | 0.226 GiB | 0.194 GiB |
| 1M | 52.0 | 52.00M | 0.969 GiB | 0.775 GiB | 0.678 GiB | 0.581 GiB |
| 1M | 57.8 | 57.80M | 1.077 GiB | 0.861 GiB | 0.754 GiB | 0.646 GiB |
| 5M | 52.0 | 260.00M | 4.843 GiB | 3.874 GiB | 3.390 GiB | 2.906 GiB |
| 5M | 57.8 | 289.00M | 5.383 GiB | 4.306 GiB | 3.768 GiB | 3.230 GiB |
| 15M | 52.0 | 780.00M | 14.529 GiB | 11.623 GiB | 10.170 GiB | 8.717 GiB |
| 15M | 57.8 | 867.00M | 16.149 GiB | 12.919 GiB | 11.304 GiB | 9.689 GiB |

Parquet compression likely range:

- Full `id + xy32 + sdf32`: about `0.5x-1.2x` of raw numeric payload depending on row ordering, coordinate entropy, compression codec, and metadata overhead.
- `id` compresses well if sorted by building/shard.
- `xy` and `sdf` floats often compress weakly unless quantized, rounded, or encoded as float16.
- Float16 may be safe for `xy` and possibly `sdf` only after validating downstream loss and embedding quality. Keep training tensors as float32 unless a mixed-precision path is explicitly validated.

Operational storage should budget more than raw payload:

- Sample manifest and row-group metadata.
- Temporary files during shard writes.
- Checkpoints.
- Logs.
- Validation subsets.
- Failed partial shard cleanup.

For national planning, reserve at least `30-80 GiB` for a full sample cache and training artifacts under conservative parquet settings, more if multiple sample configurations are retained.

## 5. Runtime Bottlenecks

Likely bottlenecks, in priority order:

1. **Signed-distance sampling from polygons:** current code calls Shapely distance/contains point by point. This is CPU-heavy and scales with sample count and polygon complexity.
2. **Shapely/geopandas overhead:** Python object geometry operations dominate unless batched/vectorized carefully.
3. **Multiprocessing overhead:** spawning processes, pickling Shapely objects, collecting unordered results, and building dictionaries can offset parallel gains.
4. **Disk read/write bandwidth:** full sample cache writes and reads can saturate storage, especially with many small shards.
5. **DataLoader throughput:** GPU training only helps if sample batches arrive quickly enough.
6. **GPU underutilization:** online sampling may leave the GPU idle; disk cache may improve this if scanning is efficient.
7. **Checkpoint overhead:** 15M x 64D with Adam state is about `10.7 GiB` for embedding-related checkpoint data alone, and checkpoint serialization can temporarily duplicate tensors.
8. **Final embedding export:** copying the full table to CPU and constructing one DataFrame is avoidable; export must be incremental.
9. **Downstream validation and visualization:** full UMAP, full spatial joins, and full interactive maps are not feasible as default validation.

## 6. Recommended FUSE-Side Implementation Architecture

Do not modify `/members/dhnyu/fuse_external/GeoNeuralRepresentation` directly unless absolutely necessary. Treat the large-scale runner as an experimental FUSE prototype under:

`/members/dhnyu/fuse/tests/geo2vec_large_scale/`

Do not place new code under `scripts/`.

### `inspect_building_geometry_inventory.py`

Inputs:

- `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld.gpkg`
- Optional attributes: `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet`

Outputs:

- Prototype metadata JSON/parquet under `/members/dhnyu/fusedata/gwanak_test/validation/` for small diagnostics.
- For full national inventory metadata only, a small manifest can be written under `/members/dhnyu/fusedatalarge/processed` if needed.

Key columns:

- `building_id`
- `fid` or source feature index if available
- geometry validity flags
- bounds
- CRS

Failure recovery:

- Read-only diagnostics should be restartable.
- Persist manifest atomically via `*.tmp` then rename.

Determinism:

- No random sampling.
- Sort reported samples by stable `building_id` or `fid`.

Logging/metadata:

- File size, layer name, feature count, CRS, extent, geometry type counts, invalid geometry count, duplicate/missing `building_id` count.

### `build_global_building_id_map.py`

Inputs:

- National GeoPackage layer `buildings`.
- Attribute parquet if geometry scan is too expensive and attributes are confirmed complete.

Outputs:

- `korea_buildings_geo2vec_global_id_map.parquet`
- `korea_buildings_geo2vec_global_id_map_metadata.json`

Recommended final location:

- Large canonical map: `/members/dhnyu/fusedatalarge/processed`
- Prototype maps: `/members/dhnyu/fusedata/gwanak_test/validation/`

Key columns:

- `building_id` string
- `geo2vec_internal_id` int64
- optional `source_feature_index`, `source_zip`, `source_layer`

Failure recovery:

- Write a temporary parquet and metadata file.
- Validate row count, uniqueness, and contiguous id range before atomic rename.
- Do not overwrite an existing validated id map unless explicitly requested.

Deterministic seed logic:

- The id map itself should not use randomness.
- Ordering should be stable: prefer existing canonical row order if documented, otherwise sort by `building_id`.

Logging/metadata:

- Input checksums or file size/mtime.
- Row count.
- Duplicate and missing key counts.
- `sha256` checksum of `(building_id, geo2vec_internal_id)` records or parquet file.

### `generate_disk_backed_sdf_samples.py`

Inputs:

- Geometry GeoPackage.
- Global id map parquet.
- Sampling config JSON.

Outputs:

- Partitioned sample shards such as:
  - `korea_geo2vec_sdf_samples_shard_000000.parquet`
  - `korea_geo2vec_sdf_samples_manifest.parquet`
  - `korea_geo2vec_sdf_samples_metadata.json`

Key columns:

- `geo2vec_internal_id` int64
- `x` float32
- `y` float32
- `sdf` float32
- optional `split` uint8
- optional `sample_kind` uint8
- optional `sample_index` int32

Failure recovery:

- Write each shard to `*.tmp`.
- Validate finite values, expected columns, row count, and id coverage before renaming.
- Manifest records shard status: `pending`, `writing`, `complete`, `failed`.
- Resume skips complete shards whose checksum matches metadata.

Deterministic seed logic:

- `sample_seed = hash64(base_seed, geo2vec_internal_id, sample_config_version)`.
- Use local RNG objects inside workers.
- Avoid Python's process-randomized `hash()` for partitioning; use stable hashing such as xxhash/sha256 modulo shard count.

Logging/metadata:

- Shard id, id range or stable hash bucket, row count, building count, elapsed seconds, samples/sec, invalid geometry count, output bytes, checksum.

### `validate_sample_cache.py`

Inputs:

- Sample cache manifest.
- Global id map.
- Sampling config.

Outputs:

- Validation report JSON/parquet under the prototype validation directory.

Key checks:

- Required columns and dtypes.
- Finite `x`, `y`, `sdf`.
- No missing ids outside the intended subset.
- Sample count distribution per building.
- Train/validation split distribution if stored.
- Manifest checksum consistency.

Failure recovery:

- Validation is read-only.
- Can resume shard-by-shard by persisting validation status.

Determinism:

- Fixed random seed for spot-check selection.
- Spot-check ids generated from `base_seed`.

Logging/metadata:

- Shard-level and global summary.
- Worst offending shard ids and sample rows, without dumping huge data.

### `train_global_geo2vec_from_sample_cache.py`

Inputs:

- Sample cache manifest.
- Global id map metadata.
- Training config JSON.
- Optional checkpoint path.

Outputs:

- Checkpoints under a configured run directory.
- Training metrics parquet/JSONL.
- Final model checkpoint.

Key columns:

- `geo2vec_internal_id`
- `x`
- `y`
- `sdf`
- optional `split`

Failure recovery:

- Resume from latest complete checkpoint.
- Verify id-map checksum and sample manifest checksum before loading optimizer state.
- Resume at `epoch`, `global_step`, `shard_index`, and `row_group/sample_offset`.

Deterministic seed logic:

- Fixed `base_seed`.
- Store and restore Python, NumPy, Torch CPU, and Torch CUDA RNG states.
- If shuffling shards, precompute deterministic shard order per epoch and checkpoint it.

Logging/metadata:

- Loss, validation loss, samples/sec, GPU allocated/reserved, CPU RSS, DataLoader queue health if available, checkpoint time, and bytes read/sec.

### `export_global_geo2vec_embeddings.py`

Inputs:

- Final or selected checkpoint.
- Global id map parquet.
- Export config.

Outputs:

- Embedding parquet, preferably row-grouped or partitioned:
  - `building_id`
  - `geo2vec_internal_id`
  - `geo2vec_000 ... geo2vec_031` or `geo2vec_063`

Failure recovery:

- Export id ranges/shards independently.
- Manifest tracks completed output parts.
- Skip completed parts with matching checksum.

Determinism:

- No randomness.
- Stable id order.

Logging/metadata:

- Export range, row count, bytes, checksum, elapsed seconds.

### `monitor_geo2vec_training.py`

Inputs:

- Training metrics JSONL/parquet.
- Checkpoint directory.
- Optional `nvidia-smi` polling.

Outputs:

- Lightweight status report and plots under validation output.

Failure recovery:

- Read-only.

Determinism:

- No randomness except fixed sampling for any displayed examples.

Logging/metadata:

- CPU RSS, GPU allocated/reserved, GPU utilization if available, samples/sec, validation loss, checkpoint cadence, shard throughput.

## 7. Checkpoint and Resume Design

Each checkpoint should contain:

```python
{
    "model_state_dict": model.state_dict(),
    "optimizer_state_dict": optimizer.state_dict(),
    "epoch": epoch,
    "global_step": global_step,
    "samples_seen": samples_seen,
    "current_shard_index": current_shard_index,
    "current_row_group": current_row_group,
    "current_sample_offset": current_sample_offset,
    "epoch_shard_order": epoch_shard_order,
    "python_rng_state": random.getstate(),
    "numpy_rng_state": np.random.get_state(),
    "torch_rng_state": torch.get_rng_state(),
    "torch_cuda_rng_state_all": torch.cuda.get_rng_state_all(),
    "training_config": training_config,
    "model_config": model_config,
    "sample_config": sample_config,
    "global_id_map_checksum": id_map_checksum,
    "sample_cache_manifest_checksum": sample_manifest_checksum,
    "external_repo_commit": "07c0681",
}
```

Resume logic:

1. Locate the newest checkpoint with a complete sidecar marker.
2. Load training config and compare it to the requested run config.
3. Verify global id-map checksum.
4. Verify sample-cache manifest checksum.
5. Recreate `Geo2Vec_Model(n_poly=N, ...)` and optimizer.
6. Load model and optimizer states.
7. Restore RNG states.
8. Recreate deterministic shard order for the epoch or load it from checkpoint.
9. Seek the dataset iterator to `current_shard_index`, `current_row_group`, and `current_sample_offset`.
10. Continue training from `global_step + 1`.

Checkpoint writing should be atomic:

1. Write to `checkpoint_step_XXXXXX.pt.tmp`.
2. Flush and verify file size.
3. Rename to `checkpoint_step_XXXXXX.pt`.
4. Write `checkpoint_step_XXXXXX.complete.json`.

For large national checkpoints, consider:

- Keeping the latest `K` checkpoints.
- Saving less frequent full optimizer checkpoints and more frequent lightweight model-only snapshots.
- Exporting checkpoints to CPU tensors to reduce GPU memory spikes during serialization.
- Measuring checkpoint wall time before 1M+ training.

## 8. Validation Plan

Validation should grow only after the previous stage passes both engineering and downstream checks.

| Stage | Purpose | What to measure |
|---|---|---|
| Reproduce Gwanak | Confirm the scalable runner preserves the single-model methodology | Embedding row count, validation loss, CPU RSS, GPU allocated/reserved, samples/sec, downstream random split, spatial block CV, dong holdout status |
| 50k deterministic national sample | First national geometry heterogeneity test | Geometry read rate, invalid geometry count, sample generation rate, cache bytes, training samples/sec, checkpoint size, finite embeddings |
| 100k deterministic national sample | Confirm stable memory and resume | CPU RSS, GPU allocated/reserved, DataLoader throughput, resume after forced interruption, output size |
| 300k | First meaningful scale test | Sampling throughput, cache validation time, validation loss, checkpoint overhead, embedding export time |
| 1M | Stress test for national architecture | End-to-end wall time, storage pressure, checkpoint/resume reliability, downstream geometry validation on sampled regions |
| 5M | Only after 1M success | Multi-day fault tolerance, shard scheduler behavior, sustained disk bandwidth, validation sample quality |
| Full Korea | Only if justified | All previous metrics plus final output integrity, national coverage, downstream reproducibility, and storage cleanup plan |

Per-stage metrics:

- CPU RSS and peak maxrss.
- GPU allocated and reserved memory.
- GPU utilization if available.
- Sample generation rate in buildings/sec and samples/sec.
- Training throughput in samples/sec.
- DataLoader wait time if instrumented.
- Disk bytes read/written per second.
- Sample cache size and compression ratio.
- Checkpoint size and checkpoint write time.
- Validation loss and sampled reconstruction diagnostics.
- Embedding parquet size and export time.
- Downstream geometry validation status.
- Logs and metadata completeness.

Keep all small diagnostic outputs below `100k` buildings and write them only under:

`/members/dhnyu/fusedata/gwanak_test/validation/`

Do not overwrite existing Gwanak outputs.

## 9. Recommended Next Action

The single safest next implementation step is:

**Build `tests/geo2vec_large_scale/build_global_building_id_map.py` and run it first on a deterministic subset below 100k buildings, writing only to `/members/dhnyu/fusedata/gwanak_test/validation/`.**

This step is low risk, does not start training, does not overwrite Gwanak outputs, and establishes the stable `building_id -> geo2vec_internal_id` contract required by every scalable training strategy. After that map contract is validated, implement a tiny disk-backed SDF sample cache prototype and use it to reproduce the Gwanak single-model result with one global model and one global embedding table.
