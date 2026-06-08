# Large-Scale SDF-Geo2Vec Prototype

This directory contains an experimental data engineering pipeline for nationwide Korea building SDF-Geo2Vec training in one shared latent space. Code here is prototype-only and should not be promoted to production until the staged validation plan passes.

## Core Principle

Independent chunk models are methodologically wrong for this use case. If chunk 1 trains model A and chunk 2 trains model B, each model learns its own latent coordinate system. The resulting embeddings can be rotated, scaled, or arranged differently, so vectors from different chunks are not directly comparable.

Chunking is still allowed for I/O, SDF sampling, sample cache files, validation, checkpointing, and embedding export. The constraint is that all minibatches must update one persistent `Geo2Vec_Model` and one global entity embedding table initialized with `n_poly = total_buildings`.

Correct topology:

```text
global id map -> one Geo2Vec_Model(N) -> sample shard 0 -> sample shard 1 -> ... -> one global embedding table
```

Incorrect topology:

```text
shard 0 -> model A
shard 1 -> model B
```

## Pipeline

1. `inspect_building_geometry_inventory.py`
   - Inspects the national GeoPackage layer, CRS, feature count, extent, and optional bounded validity sample.
2. `build_global_building_id_map.py`
   - Builds a deterministic `building_id -> geo2vec_internal_id` parquet map.
3. `generate_disk_backed_sdf_samples.py`
   - Reads a bounded prototype id map and geometry subset, generates deterministic SDF samples, and writes parquet shards.
4. `validate_sample_cache.py`
   - Validates schema, dtypes, finite values, split distribution, per-building sample counts, and shard checksums.
5. `train_global_geo2vec_from_sample_cache.py`
   - Initializes one global Geo2Vec model and trains sequentially from all sample shards.
6. `export_global_geo2vec_embeddings.py`
   - Exports the global embedding table incrementally by id ranges.
7. `monitor_geo2vec_training.py`
   - Summarizes metrics, checkpoints, output sizes, and throughput.

## Sample Cache Format

Each sample shard is parquet with:

```text
geo2vec_internal_id int64
x float32
y float32
sdf float32
split uint8
sample_kind uint8
sample_index int32
```

`split` uses `0=train` and `1=validation`. `sample_kind` is a small integer describing boundary vertices, Gaussian boundary samples, length-proportional samples, or grid samples. Each shard is written atomically with `*.tmp` then renamed. A manifest records row count, building count, elapsed time, samples/sec, bytes, and checksum.

Per-building seeds use:

```text
stable_hash(base_seed, building_id, geo2vec_internal_id, sample_config_version)
```

Python `hash()` is never used because it is process-randomized.

## Expected Bottlenecks

On the current server, GPU VRAM is not expected to be the first bottleneck for 32D or 64D embeddings. The likely bottlenecks are:

- CPU-side Shapely signed-distance and containment calls.
- Geometry serialization/deserialization and multiprocessing overhead.
- Parquet write/read throughput.
- DataLoader or manual minibatch throughput.
- Checkpoint serialization for model plus Adam state.
- Resume correctness after interruption.
- Incremental embedding export and downstream validation.

## Failure Recovery

All large outputs use atomic writes. Shard manifests make generation resumable: completed shards with matching checksum are skipped. Training checkpoints include model state, optimizer state, epoch, global step, current shard index, sample offset, RNG states, training config, id-map checksum, and sample-manifest checksum.

Resume logic recreates the same model, validates checksums, restores optimizer/RNG state, skips completed shard positions, and continues updating the same global embedding table.

## Stage Plan

1. Reproduce Gwanak with the scalable runner.
2. Run deterministic 50k national prototype.
3. Run deterministic 100k national prototype.
4. Attempt 300k only after cache validation, checkpointing, and export are reliable.
5. Attempt 1M only after throughput and resume are stable.
6. Attempt 5M only after multi-hour checkpoint/resume testing.
7. Full Korea only if sampling throughput, storage, downstream validation, and recovery are acceptable.

Prototype outputs must stay under:

`/members/dhnyu/fusedata/gwanak_test/validation/`

Do not overwrite existing successful Gwanak outputs.
