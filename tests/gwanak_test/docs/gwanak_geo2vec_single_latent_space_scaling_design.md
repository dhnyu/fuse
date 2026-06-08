# Gwanak Geo2Vec Single-Latent-Space Scaling Design

Generated: `2026-06-08 KST`

## Summary

Sequential GPU minibatch training is compatible with one shared Geo2Vec latent space, but only if all batches update the same `Geo2Vec_Model` instance and the same entity embedding table. This is different from the previous chunked Gwanak output, where separate chunks were trained as separate models and therefore produced separate latent coordinate systems.

The current GeoNeuralRepresentation implementation already trains with sequential minibatches after sample generation. However, it does not stream geometry batches from disk into a persistent global model. It first preprocesses all geometries, generates all SDF samples into Python dictionaries, copies all samples into CPU tensors, then trains a single model with a PyTorch `DataLoader`.

For Korea-scale building training, GPU VRAM is probably not the first hard bottleneck at `Geo_dim=32` or `64` on a 48 GB RTX A6000. The larger bottlenecks are CPU-side sample materialization, multiprocessing sampling throughput, all-entity optimizer/checkpoint management, output writing, and total runtime. Before attempting 1M+ buildings, FUSE should add a streaming or disk-backed dataset while preserving one global entity embedding table.

## Architecture Inspection

The FUSE wrapper is `/members/dhnyu/fuse/tests/gwanak_test/scripts/run_gwanak_single_model_lightweight.py`. It imports `list2vec` from `/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/list2embedding.py` and passes shape-only settings:

- `shape_learning=True`
- `location_learning=False`
- `Geo_dim=32`
- `hidden_size_shape=128`
- `num_layers_shape=4`
- `num_freqs_shape=4`
- `batch_size=4096`
- `samples_perUnit_shape=8`
- `point_sample_shape=2`
- `uniformed_sample_perUnit_shape=4`

The Geo2Vec model is a hybrid, but the learned representation is entity-table based:

- `models/Geo2Vec.py:16` creates `torch.nn.Embedding(n_poly, z_size)`.
- `models/Geo2Vec.py:49-54` looks up `poly_embedding_layer(id)` and concatenates that entity vector with positional encodings of sampled coordinates.
- `models/Geo2Vec.py:33-47` uses an MLP/SDF decoder to predict signed distance values from `(sample coordinate encoding, entity embedding)`.
- `runners/list2embedding.py:228-231` creates one `Geo2Vec_Model(n_poly=max_id + 2, ...)` for shape learning.
- `runners/list2embedding.py:239-249` iterates over the DataLoader minibatches and updates the same model.
- `runners/list2embedding.py:263-264` returns `model.poly_embedding_layer.weight.data.cpu().numpy()`.

Therefore, Geo2Vec is not an out-of-sample geometry encoder that maps a new polygon directly to an embedding. Each building has its own learnable latent vector. The shared part is the SDF decoder and coordinate encoder, which constrain all entity vectors to live in one jointly trained latent space.

## Sequential Batches vs Bad Chunking

Bad chunking:

```text
Chunk 1 -> Model A -> latent space A
Chunk 2 -> Model B -> latent space B
Chunk 3 -> Model C -> latent space C
```

These vectors are not directly comparable because each model can rotate, scale, or otherwise arrange its latent space independently.

Desired large-scale training:

```text
One Model with one embedding table -> sample batch 1 -> sample batch 2 -> ... -> sample batch N
```

This preserves one latent space because every optimizer step updates the same decoder parameters and the same entity embedding table. The current training loop already has this property once the full dataset has been converted into a PyTorch Dataset. What it lacks is scalable streaming construction of that Dataset.

## Sample Materialization

The current implementation materializes samples before training:

- `runners/list2embedding.py:201-205` calls `MP_Sampling.MP_sample(...)`.
- `models/MP_Sampling.py:48-70` accumulates `total_samples` as a Python dictionary keyed by polygon id.
- `models/Geo2Vec.py:78-99` constructs `Geo2Vec_Dataset` by preallocating CPU tensors for all sample ids, sample coordinates, and distances.
- `runners/list2embedding.py:217-224` creates DataLoaders over `random_split(total_dataset, ...)`.
- Only inside the training loop are each batch's `id`, `sample`, and `dist` moved to GPU.

So samples are not streamed from geometry to GPU batch-by-batch. They are generated all at once, held as Python objects, then copied into CPU tensors. There is no disk cache, memory map, IterableDataset, resumable checkpoint loop, or incremental embedding writer in the current code.

## Why Gwanak GPU Memory Was Low

The successful Gwanak lightweight run reported:

- Rows: `38,547`
- Average training samples per entity: `52.003`
- Peak GPU allocated: about `79 MB`
- Peak GPU reserved: about `116 MB`
- Peak process RSS: about `1.63 GB`
- GPU: RTX A6000, about `49,140 MiB` total memory

Low GPU memory is expected because:

- The entity embedding table is small for Gwanak. At `38,547 x 32 x float32`, the table is only about `4.6 MiB`.
- The MLP decoder is small. For `Geo_dim=32`, `hidden_size=128`, `num_layers=4`, `num_freqs=4`, decoder parameters are about `0.69 MiB` in fp32, or about `2.1 MiB` including Adam moments for decoder parameters.
- The DataLoader keeps all samples on CPU and moves only the current minibatch to GPU.
- `batch_size=4096` limits activation tensors.
- The full embedding table is on GPU because `model.to(device)` moves the model, including `poly_embedding_layer`, to CUDA. It is just small at Gwanak scale.

Thus the low Gwanak GPU usage is not evidence that Korea scale is free. It is evidence that this lightweight configuration has low per-batch activation cost and a small table at 38k entities.

## Memory Estimates

Assumptions:

- Training samples per entity are based on the Gwanak run: `52.003` training samples/entity with `training_ratio=0.9`, or about `57.78` total samples/entity before train/validation split.
- Minimum CPU tensor storage per sample is `20 bytes`: `id int64` = 8, `xy float32[2]` = 8, `distance float32[1]` = 4.
- Python pre-Dataset materialization can be much larger than tensor storage. A conservative planning range is `5x-10x` the minimum tensor bytes because samples are held as dictionaries, lists, tuples, and Python floats during multiprocessing collection.
- Adam persistent state for the embedding table is estimated as parameter + first moment + second moment = `12 bytes/entity/dim`; gradients add another transient `4 bytes/entity/dim` once materialized.
- Output parquet estimates below show raw float payload only. Real parquet files also include ids, metadata, compression effects, and page overhead.

| Scale | Buildings | Samples at 57.8/entity | Min CPU sample tensors | Rough Python sample pressure, 5x-10x |
|---|---:|---:|---:|---:|
| Gwanak | 38,547 | 2.23M | 0.04 GB | 0.2-0.4 GB |
| 100k | 100,000 | 5.78M | 0.11 GB | 0.5-1.1 GB |
| 300k | 300,000 | 17.33M | 0.32 GB | 1.6-3.2 GB |
| 1M | 1,000,000 | 57.78M | 1.08 GB | 5.4-10.8 GB |
| 5M | 5,000,000 | 288.91M | 5.38 GB | 26.9-53.8 GB |
| Korea | 15,000,000 | 866.72M | 16.14 GB | 80.7-161.4 GB |

The user-provided `15M x 52 = 780M` sample estimate is consistent with the training-sample count. Including validation samples from the observed 0.9 split gives about `867M` total samples.

### Entity Table, Optimizer, Checkpoint, Output

| Buildings | Dim | Embedding table fp32 | Embedding + Adam state | With gradients during train | Checkpoint table | Raw output floats |
|---:|---:|---:|---:|---:|---:|---:|
| 38,547 | 32 | 0.005 GB | 0.014 GB | 0.018 GB | 0.005 GB | 0.005 GB |
| 38,547 | 64 | 0.009 GB | 0.028 GB | 0.037 GB | 0.009 GB | 0.009 GB |
| 100k | 32 | 0.012 GB | 0.036 GB | 0.048 GB | 0.012 GB | 0.012 GB |
| 100k | 64 | 0.024 GB | 0.072 GB | 0.095 GB | 0.024 GB | 0.024 GB |
| 300k | 32 | 0.036 GB | 0.107 GB | 0.143 GB | 0.036 GB | 0.036 GB |
| 300k | 64 | 0.072 GB | 0.215 GB | 0.286 GB | 0.072 GB | 0.072 GB |
| 1M | 32 | 0.119 GB | 0.358 GB | 0.477 GB | 0.119 GB | 0.119 GB |
| 1M | 64 | 0.238 GB | 0.715 GB | 0.954 GB | 0.238 GB | 0.238 GB |
| 5M | 32 | 0.596 GB | 1.788 GB | 2.384 GB | 0.596 GB | 0.596 GB |
| 5M | 64 | 1.192 GB | 3.576 GB | 4.768 GB | 1.192 GB | 1.192 GB |
| 15M | 32 | 1.788 GB | 5.364 GB | 7.153 GB | 1.788 GB | 1.788 GB |
| 15M | 64 | 3.576 GB | 10.729 GB | 14.305 GB | 3.576 GB | 3.576 GB |

These table sizes are compatible with a 48 GB GPU at `Geo_dim=32` and probably `Geo_dim=64`, assuming batch activations remain controlled. They do not include allocator fragmentation, validation batches, DataLoader pinned memory, checkpoint duplication, or accidental large tensors such as full embedding copies.

### Decoder and Activation Memory

For the lightweight settings, model parameter memory excluding the entity table is tiny:

| Geo_dim | hidden_size | num_layers | num_freqs | Decoder params | Decoder fp32 | Decoder + Adam |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 128 | 4 | 4 | 181,207 | 0.69 MB | 2.07 MB |
| 64 | 128 | 4 | 4 | 201,687 | 0.77 MB | 2.31 MB |
| 64 | 256 | 4 | 8 | 719,271 | 2.74 MB | 8.23 MB |
| 64 | 256 | 8 | 8 | 1,345,959 | 5.13 MB | 15.40 MB |

Batch activation memory grows mainly with `batch_size`, `hidden_size`, `num_layers`, `num_freqs`, and `Geo_dim`. It is independent of total building count except through the entity table and optimizer. This is why sequential minibatching can make GPU VRAM manageable.

## Is Korea-Scale Single Global Geo2Vec Feasible?

Theoretically, yes: a single global entity embedding table and one shared SDF decoder can be trained with sequential sample batches. That preserves a single latent space.

Practically, the current code should not be used naively for 15M buildings because it materializes all samples before training and assumes all geometries are passed into `list2vec` at once. At 15M buildings and roughly 780M-867M samples, the CPU sampling/data phase becomes the likely bottleneck. GPU memory for the embedding table is not necessarily fatal at `Geo_dim=32` or `64`, but CPU RAM, multiprocessing overhead, sampling runtime, checkpoint size, and fault tolerance become serious engineering issues.

The most likely bottlenecks are:

1. CPU sampling throughput and Shapely signed-distance calls.
2. Python object materialization during `MP_sample`.
3. CPU RAM pressure before `Geo2Vec_Dataset` is built.
4. Lack of resumable checkpoints during sampling and training.
5. Full embedding extraction as one NumPy array at the end.
6. Output writing and downstream validation/visualization at 15M rows.
7. Runtime, especially if more than one epoch or denser sampling is needed.

GPU VRAM becomes a secondary bottleneck if `Geo_dim`, `batch_size`, `hidden_size`, `num_layers`, or optimizer state increase, but it is not the only or first concern under the lightweight settings.

## Required Code Changes Before 1M+ or Korea Scale

Do not modify the external repository directly unless that becomes an explicit project decision. Instead, implement a FUSE-side scalable runner or a documented fork/patch. Required design changes:

1. Keep one persistent `Geo2Vec_Model(n_poly=N, ...)` for the full dataset.
2. Assign stable global integer ids from `0..N-1` before training.
3. Replace all-at-once `MP_sample` with a streaming or disk-backed sampler.
4. Use an `IterableDataset` or indexable dataset backed by memory-mapped arrays, Arrow/Parquet fragments, Zarr, or NumPy memmap.
5. Generate deterministic samples per building id from a stable seed, not from uncontrolled multiprocessing order.
6. Avoid holding both Python sample dictionaries and tensor copies for the full dataset.
7. Save checkpoints every fixed number of batches, including model state, optimizer state, epoch, sampler position, RNG states, and id mapping.
8. Write embeddings incrementally after training rather than constructing a huge in-memory DataFrame.
9. Avoid full UMAP for 1M+ and use deterministic samples for visualization.
10. Add monitoring for CPU RSS, GPU allocated/reserved, sample generation rate, batch training rate, checkpoint size, and output write throughput.

For a global embedding table with geometry streamed by chunks, every chunk must use the same model instance. It is acceptable to process geometry/sample batches sequentially as long as the embedding table has rows for all global ids or can be safely expanded while preserving optimizer state. Expanding `torch.nn.Embedding` and Adam state during training is possible but error-prone; preallocating the full table is simpler for 1M-15M if GPU memory allows it.

## Safe Staged Experiment Parameters

These are engineering-safe starting points, not final quality settings. Increase quality only after memory and throughput are measured.

| Stage | Buildings | Geo_dim | batch_size | hidden_size_shape | num_layers_shape | samples_perUnit_shape | point_sample_shape | uniformed_sample_perUnit_shape | num_epoch | num_process | Checkpoint frequency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 50k | 50,000 | 32 | 4096 | 128 | 4 | 8 | 2 | 4 | 1 | 8 | every epoch |
| 100k | 100,000 | 32 | 4096 | 128 | 4 | 8 | 2 | 4 | 1 | 8 | every epoch + final |
| 300k | 300,000 | 32 | 4096 | 128 | 4 | 6-8 | 2 | 3-4 | 1 | 8-12 | every 25k-50k batches |
| 1M | 1,000,000 | 32 | 2048-4096 | 128 | 4 | 4-8 | 1-2 | 2-4 | 1 | 8-16 | every 25k batches |
| 5M | 5,000,000 | 32 | 2048 | 128 | 4 | 4-6 | 1 | 2 | 1 | 8-16 | every 10k-25k batches |
| Korea | 15,000,000 | 32 first, 64 only after proof | 1024-2048 | 128 | 4 | 4 | 1 | 2 | 1 | 8-16 | every 10k batches plus resumable sampler state |

Quality-oriented settings such as `Geo_dim=64`, `hidden_size=256`, `num_freqs=8`, or denser sampling should wait until 300k-1M has been proven with the streaming path. `num_process` should be raised carefully because multiprocessing can multiply memory pressure during sampling.

## Next Safest Experiment

The next safest experiment is not Korea full and not a separate-model chunking run.

Recommended next step:

1. Build a FUSE-side diagnostic/scalable prototype that preserves one global model but uses disk-backed or streaming samples.
2. Test it on Gwanak 38,547 and verify embeddings match the current single-model methodology qualitatively.
3. Run deterministic 50k and 100k samples from a larger Seoul/Korea building source.
4. Record sample generation time, CPU RSS, GPU allocated/reserved, examples/second, checkpoint size, and output parquet size.
5. Only after 100k is stable, attempt 300k with checkpoint/resume enabled.

This directly tests the desired design:

```text
one global model + one global embedding table + sequential sample batches
```

It avoids the known methodological problem:

```text
many independently trained chunk models + unaligned latent spaces
```

## Open Questions

- How much of Korea's 15M-building geometry has already been cleaned into valid polygons with stable `building_id` values?
- What is the observed sample generation rate per million buildings under the lightweight sampler?
- Does one epoch remain sufficient for downstream quality at 300k, 1M, and Seoul scale?
- Does `Geo_dim=32` remain expressive enough outside Gwanak?
- Should FUSE preserve entity-table Geo2Vec, or should it eventually move to a true shared geometry encoder for out-of-sample inference?
- Can the current signed-distance sampling be vectorized or replaced with a faster geometry kernel for nationwide training?
