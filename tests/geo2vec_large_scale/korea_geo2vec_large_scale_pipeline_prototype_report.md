# Korea Geo2Vec Large-Scale Pipeline Prototype Report

Generated: `2026-06-08 KST`

## Summary

The 50k prototype was successful. It built a deterministic global id map, generated deterministic disk-backed SDF sample shards, validated the cache, trained one global Geo2Vec model with one global embedding table, checkpointed the run, resumed from the final checkpoint, and exported embeddings incrementally.

No full Korea training was run. No 100k, 300k, 1M, 5M, or full-national training was run.

Prototype code is under:

`/members/dhnyu/fuse/tests/geo2vec_large_scale/`

Prototype outputs are under:

`/members/dhnyu/fusedata/gwanak_test/validation/`

## Implemented Code

| File | Status |
|---|---|
| `README.md` | Design and operating guide written |
| `geo2vec_large_scale_common.py` | Shared paths, hashing, atomic writes, checksums, metrics helpers |
| `inspect_building_geometry_inventory.py` | Implemented and run |
| `build_global_building_id_map.py` | Implemented and run for 50k |
| `generate_disk_backed_sdf_samples.py` | Implemented and run for 50k |
| `validate_sample_cache.py` | Implemented and run |
| `train_global_geo2vec_from_sample_cache.py` | Implemented and run |
| `export_global_geo2vec_embeddings.py` | Implemented and run |
| `monitor_geo2vec_training.py` | Implemented and run |

All Python files passed `py_compile`.

## Inventory

Inventory output:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_buildings_geometry_inventory.json`

Observed national source:

- Geometry path: `/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld.gpkg`
- Layer: `buildings`
- CRS: `EPSG:5186`
- Feature count: `14,388,938`
- Geometry type: `MultiPolygon`
- Extent: `[-11852.272, 58136.440, 699976.861, 668864.023]`
- 1,000-row validity sample: no missing ids, no duplicate ids, no null/empty/invalid geometries.

## 50k Id Map

Output:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_buildings_geo2vec_global_id_map_50k.parquet`

Metadata:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_buildings_geo2vec_global_id_map_50k_metadata.json`

Result:

- Rows: `50,000`
- Ordering: `building_id` ascending with stable mergesort
- Internal ids: contiguous `0..49,999`
- Missing `building_id`: `0`
- Duplicate `building_id`: `0`
- Build time: `24.66 s`
- Id-map parquet size: about `0.58 MiB`

## 50k SDF Sample Cache

Output directory:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_sdf_samples_50k_sdf_proto_v1/`

Sample config:

- `base_seed`: `20260608`
- `sample_config_version`: `sdf_proto_v1`
- `samples_per_unit`: `4.0`
- `point_sample`: `1`
- `sample_band_width`: `0.08`
- `uniform_grid`: `2`
- `validation_ratio`: `0.1`
- Shards: `10`
- Buildings per shard: `5,000`

Result:

- Buildings: `50,000`
- Total samples: `1,202,704`
- Generation time: `45.88 s`
- Sampling throughput: `26,216 samples/sec`
- Cache bytes: `17,652,404` bytes, about `16.83 MiB`
- CPU RSS after generation: about `285 MB`
- Peak maxrss: about `282 MB`

The sample cache was valid:

- Required columns and dtypes passed.
- Finite `x`, `y`, and `sdf` passed.
- Shard checksums passed.
- Buildings with samples: `50,000`
- Missing building count: `0`
- Train rows: `1,083,086`
- Validation rows: `119,618`
- Observed validation ratio: `0.09946`
- Sample count median per building: `22`
- Sample count range: `17..277`

## Global Training

Run directory:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_50k_sdf_proto_v1_32d/`

Training used one global model and one global embedding table:

- `Geo2Vec_Model(n_poly=50000, z_size=32, hidden_size=128, num_layers=4, num_freqs=4)`
- One optimizer over the same model parameters.
- All 10 sample shards were loaded sequentially and updated the same model.
- No separate shard models were trained.

Training result:

- Device: CUDA
- Epochs: `1`
- Batch size: `4096`
- Optimizer steps: `270`
- Training samples seen: `1,083,086`
- Last validation L1: about `0.0436`
- Checkpoints: steps `100`, `200`, and `270`
- Latest checkpoint size: about `20.43 MiB`
- Run directory size: about `61.28 MiB`

GPU VRAM was not a bottleneck:

- Peak GPU allocated reported during first run: about `84.6 MB`
- Per-shard monitor max allocated: about `43.4 MB`
- Max reserved in monitor: about `120 MB`

Training throughput note:

- The first training run finished quickly; process wall time was a few seconds for the 50k prototype.
- Per-shard training throughput in the initial metrics is likely overstated because CUDA timing was asynchronous.
- The trainer has now been patched to synchronize CUDA around shard timing for future runs.

## Checkpoint and Resume

Checkpoint payload includes:

- `model_state_dict`
- `optimizer_state_dict`
- `epoch`
- `global_step`
- `current_shard_index`
- `current_sample_offset`
- `samples_seen`
- RNG states for Python, NumPy, Torch CPU, and Torch CUDA
- Training config
- Model config
- Id-map checksum
- Sample-manifest checksum

Resume status:

- A resume smoke test was run against the final checkpoint.
- The first attempt found a real RNG restore bug: CPU Torch RNG state had been mapped to CUDA by `torch.load(..., map_location=device)`.
- The bug was fixed by coercing saved RNG tensors back to CPU `uint8` before restore.
- The second resume attempt succeeded, verified the id-map and sample-manifest checksums, loaded the checkpoint, and exited without retraining because epoch 1 was already complete.

Remaining resume work before 300k+:

- Test interruption and resume in the middle of a shard.
- Avoid overwriting `training_summary.json` during no-op resume checks.
- Add an explicit resume audit record separate from the main training summary.

## Embedding Export

Output directory:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_50k_sdf_proto_v1_32d_embeddings/`

Result:

- Rows: `50,000`
- Geo_dim: `32`
- Parts: `5`
- Finite value check: passed
- Row count validation: passed
- Output size: about `8.92 MiB`
- Export time: about `0.11 s`

Export is incremental by id-map batches and does not need to construct a national-scale embedding DataFrame in one object.

## Bottleneck Assessment

For this 50k prototype, CPU-side SDF sampling was the main measured bottleneck:

- Id map build: `24.66 s`
- SDF generation: `45.88 s`
- Cache validation: sub-second
- Training: a few seconds at this scale
- Export: sub-second

GPU VRAM was not a bottleneck. Disk size was not a bottleneck at 50k with the light sample config. The likely bottlenecks at 300k+ remain SDF sampling throughput, cache I/O, checkpoint overhead, and robust mid-shard resume behavior.

## What Is Ready

Ready for controlled prototype use:

- Deterministic id-map creation for 50k/100k prototype limits.
- Bounded GeoPackage inventory without full geometry loading.
- Deterministic per-building SDF sampling with stable SHA-256-derived seeds.
- Partitioned parquet sample cache with checksums and manifest.
- Sample cache validation.
- Single global-model training from sample shards.
- Checkpoint writing and final-checkpoint resume.
- Incremental embedding export.
- Monitoring summary.

## What Remains Before Larger Runs

Before 300k:

- Run the 100k prototype with CUDA-synchronized timing.
- Test forced interruption and mid-shard resume.
- Add stronger manifest validation before training starts.
- Decide whether sample config is sufficient for representation quality; the current config is intentionally light.
- Add optional multiprocessing or producer-consumer sampling only after deterministic single-process behavior is locked down.

Before 1M:

- Benchmark cache read throughput and checkpoint write time.
- Keep only the latest `K` checkpoints or implement checkpoint retention.
- Consider Arrow IPC or memmap if parquet scan overhead becomes significant.
- Add downstream geometry validation on sampled regions.

Before 5M or full Korea:

- Validate storage budget for the chosen sample density.
- Validate multi-hour or multi-day failure recovery.
- Profile CPU sampling across 48 cores with deterministic worker seeds.
- Add a full run manifest with source file checksums, software versions, GPU id, and external repo commit.
- Confirm that global shape normalization semantics match the intended Geo2Vec methodology.

## Recommended Next Step

Run the same pipeline at `100k` with the patched CUDA-synchronized trainer timing, then perform an intentional mid-shard interruption/resume test. Do not proceed to `300k` until resume is proven after interruption and the 100k sample/training throughput is recorded.
