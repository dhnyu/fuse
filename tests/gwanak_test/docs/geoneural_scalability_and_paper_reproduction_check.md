# GeoNeuralRepresentation Scalability and Paper Reproduction Check

Generated: 2026-06-08 KST

## Summary

The apparent contradiction is mostly a disclosure and implementation gap, not proof that our environment is wrong. The Geo2Vec paper reports experiments on Singapore and NYC datasets with very large object counts, including 1,153,008 NYC buildings, but it does not specify the exact hardware, runtime, GPU memory, batch size, sampling density, embedding dimension, or whether every listed object count was used for every shape-learning experiment.

The public GeoNeuralRepresentation code is memory-sensitive. It materializes all sampled SDF points before training, constructs one learned embedding table row per entity, and has no built-in streaming, chunking, or out-of-sample encoder. The default public-code settings are much heavier than our lightweight benchmark: shape defaults use `z_size=256`, `hidden_size=256`, `num_layers=8`, `batch_size=20480`, `samples_perUnit_shape=100`, `point_sample_shape=20`, and `uniformed_sample_perUnit_shape=20`. Our successful benchmark used `Geo_dim=32`, `hidden_size=128`, `num_layers=4`, `batch_size=4096`, `samples_perUnit_shape=8`, `point_sample_shape=2`, and `uniformed_sample_perUnit_shape=4`.

For FUSE, the next practical test is a full Gwanak-gu single-model run with lightweight settings and explicit memory monitoring. The chunked full embedding succeeded operationally, but chunked latent spaces are not directly comparable unless aligned.

## Paper Dataset Scale

The PDF inspected was:

`/members/dhnyu/references/fuse_ref/Chu 및 Shahabi - Geo2Vec Shape- and Distance-Aware Neural Representation of Geospatial Entities.pdf`

The paper states that it used four datasets:

| Dataset | Paper description | Counts explicitly stated |
|:--|:--|:--|
| MNIST | Rasterized images converted into polygon representations, randomly placed within unit space | 60,000 polygons |
| Building | Building footprints with manual geometric-shape labels | 5,000 buildings |
| Singapore | Real-world OpenStreetMap dataset | 4,347 POIs, 45,634 roads, 109,877 buildings |
| NYC | Real-world OpenStreetMap dataset | 14,943 POIs, 139,512 roads, 1,153,008 buildings |

The paper evaluates shape representation on shape classification and edge-count prediction. It evaluates location representation on distance estimation and topological relationship classification. It also evaluates downstream GeoAI use by replacing RegionDCL building features with Geo2Vec or Poly2Vec features.

## What The Paper Specifies And Does Not Specify

Specified:

- Shape representation: polygons are individually scaled to canonical `[-1, 1] x [-1, 1]` before learning shape embeddings.
- Location representation: the entire dataset is normalized to a canonical space before learning location embeddings.
- Final representation is described as concatenating location and shape vectors.
- The training algorithm initializes a model and one latent code per entity, samples SDF points per entity, builds a global sampled training set, shuffles it, and updates the model and latent codes by mini-batch.
- The paper says joint optimization over a large batch including as many geo-entities as possible helps place latent representations in a shared structured space.
- Dataset counts for Singapore and NYC are explicitly stated as above.

Not specified in the paper text inspected:

- GPU model, GPU memory, CPU/RAM, or cluster hardware.
- Runtime.
- CUDA or framework version.
- Actual batch size used in experiments.
- Actual embedding dimension used in all tables.
- Exact sample density values used for Singapore and NYC.
- Exact number of training epochs.
- Whether all 1,153,008 NYC buildings were trained as one global shape model.
- Whether the paper used the same implementation and defaults as the public GitHub repository.
- Whether shape representation experiments on Singapore/NYC used all buildings, sampled buildings, or only entities involved in downstream tasks.

Important distinction: the paper clearly lists NYC as containing 1,153,008 buildings, and tables include NYC polygon-polygon tasks. It does not explicitly say that one shared shape-only latent model was trained over all 1,153,008 NYC buildings with the public GitHub defaults.

## Repository Implementation Defaults

The static diagnostic script is:

`/members/dhnyu/fuse/tests/gwanak_test/scripts/inspect_geoneural_defaults.py`

It inspects the external repo without importing it or running training.

### Public Wrapper Defaults

In `runners/list2embedding.py`, `list2vec` defaults to:

- `Geo_dim=128`
- `location_learning=True`
- `shape_learning=True`
- `num_epoch=None`, which then uses parsed default epochs.

If no explicit `args` object is supplied, the parser defaults include:

| Setting | Location default | Shape default |
|:--|--:|--:|
| `samples_perUnit` | 4000 | 100 |
| `point_sample` | 10 | 20 |
| `uniformed_sample_perUnit` | 30 | 20 |
| `sample_band_width` | 0.1 | 0.1 |
| `batch_size` | 20480 | shared `20480` |
| `epochs` | 2 | 2 |
| `z_size` | 256, but overridden by `Geo_dim` in `list2vec` when passed | 256, but overridden by `Geo_dim` in `list2vec` when passed |
| `hidden_size` | 256 | 256 |
| `num_layers` | 8 | 8 |
| `num_freqs` | 16 | 8 |
| code regularization | 0.0 | 1.0 |
| train split | 0.95 | 0.95 |
| device | `cuda` if available else `cpu` | parser has `device_shape`, but `list2vec` uses `args.device` |

The standalone `learn_shape_rep.py` default is similar but not identical: `epochs=5`, `z_size=256`, `hidden_size=256`, `num_layers=8`, `num_freqs=8`, `batch_size=20480`, `samples_perUnit=100`, `point_sample=5`, `uniformed_sample_perUnit=10`, `polar_fourier=True`, and `training_ratio=0.95`.

The tutorial notebook is not lighter. It shows shape defaults such as `samples_perUnit_shape=300` and `uniformed_sample_perUnit_shape=40`.

### Materialization And Model Structure

The implementation does the following:

- `MP_Sampling.MP_sample` samples each entity and returns a Python dictionary of all samples.
- `Geo2Vec_Dataset` pre-allocates tensors for all sampled IDs, sampled coordinates, and SDF distances before training.
- `DataLoader` is then constructed from that materialized dataset. In `list2embedding.py`, `num_workers` is hard-coded to `0` in the actual DataLoader calls even though `args.num_workers` exists.
- `pin_memory=True` is hard-coded in the DataLoaders.
- `Geo2Vec_Model` creates `torch.nn.Embedding(n_poly, z_size)`, so each entity has a trainable latent vector row.
- Training optimizes the model and embedding table together in one latent space for the entities passed into that call.
- There is no built-in streaming sampler, no chunked trainer, no anchor alignment, and no out-of-sample geometry encoder that maps a new polygon into the existing latent space after training.

This means a single call over `N` entities is a global model, but its memory footprint grows with both `N` and the total number of sampled SDF points. Separate calls over chunks create separate latent coordinate systems.

## FUSE Experiment Comparison

### A. Initial Full Gwanak Default Run

The current benchmark report records that a previous full GPU run failed with CUDA OOM at 38,547 Gwanak buildings. I did not find a preserved raw failure log in the inspected paths, so the exact stack trace and exact parameter object for that first failed run are not recoverable from the current files.

The plausible failure mode is still clear from the public defaults:

- Default/public settings are much heavier than the later benchmark.
- If `list2vec` defaults were used, both location and shape learning may have been enabled unless explicitly disabled.
- Shape defaults alone use `Geo_dim=128` through `list2vec`, `hidden_size=256`, `num_layers=8`, `num_freqs=8`, `batch_size=20480`, `samples_perUnit_shape=100`, `point_sample_shape=20`, `uniformed_sample_perUnit_shape=20`, and 95% training split.
- Location defaults are far denser, with `samples_perUnit_location=4000`.
- The implementation materializes all SDF samples before training and uses a learned embedding table for all entities.

Evidence vs inference: the OOM event is referenced by the FUSE benchmark report; the specific reason above is inferred from the external code defaults and public implementation pattern.

### B. Chunked Full Gwanak Run That Succeeded

The full embedding metadata shows:

- Input/valid geometries: 38,547.
- Output embeddings: 38,547.
- `Geo_dim=64`.
- `num_epoch=1`.
- `chunk_size=5000`.
- `number_of_chunks=8`.
- Device: CUDA.
- Elapsed time: about 39.75 seconds.

The wrapper settings were:

- `batch_size=8192`.
- `hidden_size_shape=128`.
- `num_layers_shape=4`.
- `num_freqs_shape=6`.
- `samples_perUnit_shape=16`.
- `point_sample_shape=4`.
- `uniformed_sample_perUnit_shape=5`.
- `sample_band_width_shape=0.08`.
- `code_reg_weight_shape=0.1`.

The validation report confirms 38,547 embedding rows, no missing geometry joins, no non-finite values, and 64 embedding columns. It also flags the key limitation: embeddings were trained chunk-by-chunk, so k-means compares embeddings generated by separate Geo2Vec models.

### C. CPU/GPU Lightweight Benchmark

The benchmark report shows shape-only learning with:

- `Geo_dim=32`.
- `num_epoch=1`.
- `batch_size=4096`.
- `hidden_size_shape=128`.
- `num_layers_shape=4`.
- `num_freqs_shape=4`.
- `samples_perUnit_shape=8`.
- `point_sample_shape=2`.
- `uniformed_sample_perUnit_shape=4`.
- `sample_band_width_shape=0.08`.
- `training_ratio_shape=0.9`.

Results:

| sample size | CPU seconds | GPU seconds | average training samples/entity | GPU allocated MB | GPU reserved MB |
|--:|--:|--:|--:|--:|--:|
| 1,000 | 2.55 | 2.24 | 51.28 | 59.82 | 68 |
| 5,000 | 4.65 | 3.56 | 53.12 | 61.81 | 70 |
| 10,000 | 7.69 | 5.53 | 52.69 | 65.15 | 88 |

The benchmark was run with `CUDA_VISIBLE_DEVICES=1` because GPU 0 was occupied. It temporarily forced `pin_memory=False` for CPU runs, because the external wrapper hard-codes `pin_memory=True`.

## Why The OOM Happened

The direct cause of the initial OOM cannot be proven without the raw failure log. The evidence points to a combination of public-code defaults and implementation design:

1. Default model size is large.
   - Public defaults use `hidden_size=256`, `num_layers=8`, and `batch_size=20480`.
   - The benchmark cut those to `hidden_size=128`, `num_layers=4`, and `batch_size=4096`.

2. Default sampling is much denser.
   - Public shape defaults use `samples_perUnit_shape=100`, `point_sample_shape=20`, and `uniformed_sample_perUnit_shape=20`.
   - The benchmark used `8`, `2`, and `4`.
   - Uniform samples alone are `20 x 20 = 400` points per entity under defaults versus `4 x 4 = 16` in the benchmark.

3. All samples are materialized.
   - The code first builds a full `training_samples` dictionary, then a full tensor-backed `Geo2Vec_Dataset`.
   - This is not a streaming design.

4. The model has one trainable latent vector per entity.
   - This is conceptually correct for Geo2Vec, but it means a single global model grows with entity count.
   - For 38,547 buildings this table is manageable; for 1.15 million buildings at 256 dimensions, the embedding table and optimizer state become a material GPU/CPU cost.

5. The paper does not disclose enough reproduction details.
   - It reports dataset scale and task results, but not hardware, memory, runtime, exact sample density, or exact object subsets per task.
   - Therefore, the paper’s NYC count should not be read as evidence that the public defaults can train all NYC buildings as one shape model on a single commodity GPU.

6. Public GitHub code may differ from paper experiment code.
   - This is speculation, but common. The public repo may expose illustrative defaults rather than the exact experiment harness used for large-scale paper tables.

## Why Chunked Embeddings Are Problematic

Chunking solves memory by training separate Geo2Vec models on subsets. That is operationally useful but mathematically different from one global model:

- Each chunk initializes its own embedding table and neural SDF model.
- Latent dimensions can rotate, reflect, scale, or otherwise drift across chunks.
- A vector from chunk 0 is not guaranteed to be directly comparable to a vector from chunk 5.
- K-means or nearest-neighbor search across concatenated chunk outputs can be misleading.
- The validation report is still useful as an experimental morphology check, but it should not be treated as a canonical global embedding space.

Possible mitigations:

- Train a single global model if memory permits.
- Use anchor geometries repeated in every chunk, then align chunk embeddings with Procrustes/orthogonal transforms.
- Train overlapping chunks and solve a graph alignment problem.
- Replace per-entity latent optimization with an out-of-sample geometry encoder, so all embeddings are emitted by one shared encoder.

## Recommended FUSE Scaling Roadmap

### Gwanak-gu

Recommendation: run a full single global model with lightweight settings.

- Use the successful benchmark settings first.
- Run on a free GPU with explicit `CUDA_VISIBLE_DEVICES`.
- Record elapsed time, sampled points/entity, GPU allocated/reserved memory, CPU RSS/RAM, output validity, and downstream validation.
- Compare against the existing chunked 64D embedding using geometry prediction and cluster diagnostics.

If the full lightweight run succeeds, test a quality-oriented memory-aware configuration.

### Seoul

Recommendation: feasibility study before committing to global training.

- Start with deterministic samples: 10k, 50k, 100k buildings.
- Use single global lightweight settings while recording memory curves.
- If memory grows acceptably, attempt one Seoul-wide single model.
- If not, use anchor-aligned chunks rather than naive chunks.

### Nationwide Korea

Recommendation: do not assume naive single global latent optimization is practical.

- For exploratory analysis, use chunked or regional models with explicit anchor alignment.
- For canonical nationwide embeddings, consider a redesigned geometry encoder or a two-stage method: learn a strong model on representative samples, then encode or align the remaining geometries.
- Keep geometry and attributes separated: GeoPackage for minimal geometry + stable key, Parquet for embedding tables.

## Proposed Next Commands

Inspect defaults only:

```bash
python /members/dhnyu/fuse/tests/gwanak_test/scripts/inspect_geoneural_defaults.py
```

Run full Gwanak single-model conservative lightweight experiment:

```bash
CUDA_VISIBLE_DEVICES=1 python /members/dhnyu/fuse/tests/gwanak_test/scripts/benchmark_geo2vec_cpu_gpu.py \
  --sample-sizes 38547 \
  --overwrite
```

That command uses the benchmark harness and records memory, but it writes benchmark-style filenames. For a canonical full embedding, create or adapt a single-model output script so the output goes to a clearly named Parquet such as:

`/members/dhnyu/fusedata/embeddings/gwanak_buildings_geo2vec_shape_global_lightweight.parquet`

Quality-oriented but memory-aware settings to test after the conservative run:

```bash
CUDA_VISIBLE_DEVICES=1 python /members/dhnyu/fuse/tests/gwanak_test/scripts/benchmark_geo2vec_cpu_gpu.py \
  --sample-sizes 10000 38547 \
  --batch-size 4096 \
  --samples-per-unit-shape 12 \
  --point-sample-shape 3 \
  --uniformed-sample-per-unit-shape 5 \
  --sample-band-width-shape 0.08 \
  --overwrite
```

The current benchmark script does not expose `Geo_dim`, `hidden_size`, `num_layers`, or `num_freqs` as CLI flags. Add those flags before using it as a general quality-sweep harness.

## Actionable Single-Model Configurations

### Config 1: Conservative Lightweight

- `Geo_dim=32`
- `hidden_size=128`
- `num_layers=4`
- `num_freqs=4`
- `batch_size=4096`
- `samples_perUnit_shape=8`
- `point_sample_shape=2`
- `uniformed_sample_perUnit_shape=4`
- `sample_band_width_shape=0.08`
- `num_epoch=1`
- `training_ratio_shape=0.9`
- `code_reg_weight_shape=0.1`

Purpose: prove full Gwanak single-model feasibility and establish memory/runtime scaling.

### Config 2: Quality-Oriented But Memory-Aware

- `Geo_dim=64`
- `hidden_size=128` first; try `256` only after memory headroom is confirmed.
- `num_layers=4`
- `num_freqs=4` first; try `8` after memory headroom is confirmed.
- `batch_size=2048` or `4096`, chosen by observed GPU reserved memory.
- `samples_perUnit_shape=12` to `16`
- `point_sample_shape=3` to `4`
- `uniformed_sample_perUnit_shape=5`
- `sample_band_width_shape=0.08`
- `num_epoch=1` first; increase only after validating memory.
- `training_ratio_shape=0.9` or `0.95`
- `code_reg_weight_shape=0.1`

Purpose: improve embedding quality without returning to public default memory pressure.

Monitor:

- elapsed seconds
- average training samples per entity
- `torch.cuda.max_memory_allocated()`
- `torch.cuda.max_memory_reserved()`
- CPU RAM / process RSS
- output row count, embedding dimension, and finite values
- downstream geometry prediction performance
- UMAP/t-SNE if packages are available
- k-means structure and cluster geometry summaries

## Open Questions

- What exact hyperparameters did the paper use for the NYC and Singapore experiments?
- Did the paper train all NYC buildings for shape representation, or only subsets/buildings involved in downstream regions/tasks?
- What hardware and runtime were used?
- Did the authors use streaming or a different training harness not reflected in the public repository?
- Are the published real-world tasks driven mainly by location embeddings, shape embeddings, or concatenated shape-location embeddings for all entity types?
- For FUSE, what downstream task should decide whether 32D lightweight embeddings are good enough versus 64D/stronger embeddings?
