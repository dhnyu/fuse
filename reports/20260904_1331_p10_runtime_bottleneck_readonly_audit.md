# P10 Runtime Bottleneck Read-Only Audit

## Verdict

`P10_RUNTIME_BOTTLENECK_READONLY_AUDIT_COMPLETE`

Bottleneck classification: `MIXED_BOTTLENECK` (`CPU_BOUND` plus
`GPU_UNDERFED`). The workload is progressing. It is not an I/O-device stall,
not dominated by retrieval ranking, and not a `POSSIBLE_STALL`.

This audit did not signal, attach to, restart, reconfigure, or modify the
running P10 evaluation. Sampling used read-only process, filesystem, system,
and GPU interfaces. Temporary monitoring output was written only under
`/tmp/p10-runtime-audit-20260904-1328`.

## Scope And Inputs

- Audit time: 2026-09-04 13:27-13:32 KST.
- Repository: `/members/dhnyu/fuse`, branch `reduced`.
- Source HEAD: `a806171e9bf7365bd09b2e3c9863aded2fca6d6e`.
- P10 authority: `p10auth_8b6919578aaa24fa8f1b98a2`.
- Qualitative contract: `p10qq_dd7d0775f5809a793575342b`.
- Analysis contract: `p10ana_8fc83be04542d925a4574e3c`.
- Consumption: `p10cons_7d0eba832b70d545fc5d3eb4`.
- Active tmux session: `p10_model_shards_20260904`, created 05:20:47 KST.
- Prompt scope: identify the active evaluation and characterize its runtime
  without changing the current scientific execution.

The worktree already contained the uncommitted P10 implementation and Python
bytecode changes when this audit began. This report does not alter or stage
those files.

## Active Execution

At 13:32 KST, two of eight models had canonical `evaluation.json` commits:

| Model | Commit time | Status |
|---|---:|---|
| `cmp_ssv_like` | 13:19:48 | complete, exit 0 |
| `cmp_ds_like` | 13:31:11 | complete, exit 0 |

The six remaining evaluator workers were all reading accepted P3 original
scene-cache archives. This identifies the active phase as held-out embedding
generation, before retrieval/ranking, qualitative retrieval, UMAP, HDBSCAN,
and artifact publication for those models. Validation revalidation and
validation embedding had already completed for all eight models.

| Model | Launcher PID | Worker PID | Elapsed at sample | Current phase |
|---|---:|---:|---:|---|
| `cfg_d128` retry | 291186 | 291189 | 1:40:38 | held-out embedding |
| `cmp_a1_geometric_core` | 4190369 | 4190372 | 8:11:19 | held-out embedding |
| `cmp_a2_semantic_enriched` | 4190374 | 4190375 | 8:11:19 | held-out embedding |
| `cmp_a3_object_context_enriched` | 4190378 | 4190380 | 8:11:19 | held-out embedding |
| `cmp_a4_raster_complete_non_relational` | 4190426 | 4190427 | 8:11:19 | held-out embedding |
| `cmp_a5_relation_type_agnostic` | 4190480 | 4190482 | 8:11:19 | held-out embedding |

The shell launchers are orchestration wrappers; each Python PID is the actual
model evaluator. The session also had a non-scientific watchdog shell at PID
4190633. It was observed only and was not invoked or modified by this audit.

An earlier `cfg_d128` evaluator started at 03:08 and reached HDBSCAN after
UMAP, then exited at 11:31 because `hdbscan 0.8.40` was incompatible with the
then-installed scikit-learn 1.8 interface. It did not publish a model
evaluation. The active retry uses scikit-learn 1.7.2, UMAP 0.5.9.post2, and
HDBSCAN 0.8.40. This operational history predates this read-only audit.

## Utilization Sample

A 30-second `pidstat`, `vmstat`, `iostat`, and `nvidia-smi dmon` observation
window showed:

| Worker | CPU | Threads | RSS |
|---|---:|---:|---:|
| `cfg_d128` | about 105% | 109 | 3.82 GB |
| A1 | about 105% | 110 | 3.99 GB |
| A2 | about 105% | 110 | 4.05 GB |
| A3 | about 105% | 110 | 4.04 GB |
| A4 | about 105% | 110 | 4.29 GB |
| A5 | about 105% | 110 | 4.31 GB |
| DS-like, before completion | about 106% | 111 | 3.62 GB |

Thread-level inspection showed one runnable Python thread carrying essentially
all useful CPU work while framework-created threads were mostly idle.

Host observations:

- Load average: 8.46 / 8.59 / 8.78 with seven active evaluators at sampling.
- CPU: 15.2-15.5% user, 0.29-0.39% system, 84.1-84.5% idle.
- I/O wait: 0.03-0.05%.
- Memory: 754 GiB total, about 718 GiB available.
- Per-worker physical read rate: effectively 0 KiB/s during the sample.
- Per-worker write rate: about 280-421 KiB/s, with `iodelay=0`.
- NVMe utilization: about 0.5%; HDD utilization: about 0.1-0.22%.

Large logical reads were served from page cache. By 13:28, the long-running
workers had each issued approximately 157-170 GB of logical reads and 9.3-10.3
GB of canceled temporary writes, despite negligible contemporaneous physical
disk reads. This is repeated archive decoding/extraction work, not storage
device saturation.

GPU observations over six five-second samples:

| GPU | Resident memory | SM utilization samples | Power range |
|---|---:|---|---:|
| RTX A6000 0 | 2,179 MiB | 0, 0, 0, 38, 38, 0% | 6-70 W |
| RTX A6000 1 | 6,601 MiB shared by shards | 37, 0, 38, 0, 0, 0% | 73-82 W |

The low, bursty GPU duty cycle combined with one saturated CPU thread per
worker and abundant idle host CPU is direct evidence that synchronous input
construction underfeeds the GPUs. No OOM or GPU-compute saturation was seen.

## Phase Timing

The current evaluator does not emit internal stage timers, so some stages can
only be bounded rather than isolated precisely.

### Pre-held-out gate

- Original process start: 03:08:20.
- Qualitative and analysis contracts plus authority: committed by 03:08:35.
- Eight validation results: 03:08:51 through 03:09:57.
- Authority-to-consumption validation gate: 82.47 seconds.
- Process-start-to-consumption: 97.33 seconds.
- Per-model validation revalidation after the first model: 7.5-10.9 seconds;
  the first model took 16.3 seconds including one-time setup.
- Each validation cache contained 1,200 records. Observed aggregate cost was
  approximately 6.2-13.5 ms per record, or 50-108 ms per batch of eight.

### Held-out model path

`cmp_ssv_like` provides the first complete stage boundary:

- Shard start: 05:20:47.
- Compressed array artifact timestamp: 13:19:33.
- Qualitative/evaluation commit: 13:19:48.
- Total: about 7 h 59 min.
- 4,800 records (3,200 queries plus 1,600 gallery) imply about 5.99 seconds per
  record, or 47.9 seconds per batch of eight, for the dominant embedding path.
- The observable array-to-final-publication tail was about 15.2 seconds.

`cmp_ds_like` completed after about 8 h 10 min. The original `cfg_d128` attempt
spent about 8 h 22 min reaching post-UMAP HDBSCAN before the dependency error.
These observations independently place the dominant cost before or during
held-out embedding, not in final ranking or publication.

Checkpoint load and model initialization occur once per model and are bounded
by the 7.5-16.3 second validation gate, but cannot be separated from validation
embedding using current logs. Retrieval, qualitative, UMAP, HDBSCAN, and
serialization likewise lack individual timestamps. Code-level complexity and
the 15-second post-array tail show they are minor compared with the roughly
eight-hour embedding path, though exact per-stage values require future
instrumentation.

## Retrieval Complexity

Quantitative retrieval is implemented with batched tensor operations:

- Per model, `queries @ galleries.T` creates 3,200 x 1,600 = 5.12 million
  similarities.
- Stable `torch.argsort` ranks each query.
- There is no Python nested scalar-distance loop and no repeated gallery model
  call per query.
- Embeddings are moved to CPU before the matrix operation. GPU ranking could
  save seconds, but cannot explain hours of wall time.

Qualitative retrieval reuses the already generated gallery embeddings. It
performs only ten vector-matrix products plus sorting/filtering over 1,599
candidates. It does not re-embed queries or candidates. The 2 km spatial mask
is recomputed for every model, but its scale is small; the immutable mask could
be shared in a future run.

Verdict: retrieval implementation is not the current dominant bottleneck.

## Embedding And Input Path

The dominant repeated deterministic work is in source materialization:

1. `_embed()` iterates batches of eight but constructs each record serially in
   Python before a synchronous `to(device, non_blocking=False)` transfer.
2. `read_original_scene()` reopens a scene archive for every record and reads
   full building, road, POI, context, relation, and topology parquet members.
3. The table reader converts a complete parquet member to Python objects, then
   filters to the requested scene.
4. Land-cover and DEM Zarr trees are extracted from the tar archive into a
   temporary directory for each scene read.
5. Each original scene is reconstructed for two augmented evaluation queries
   and again for the gallery within one model, then repeated across models.
6. Geometry Fourier features are deterministically recomputed for each
   applicable model/view.
7. DS-like evaluation uses deterministic Shapely rasterization when no prepared
   evaluation cache is supplied, adding entity/cell Python work.

Checkpoint loading and model initialization happen once per model and are
scientifically necessary. Gallery encoding also must happen once per model
because model parameters differ; the implementation correctly computes it
once and reuses it for quantitative and qualitative retrieval.

| Operation | Classification |
|---|---|
| Checkpoint load/model initialization | scientifically necessary once/model |
| Gallery embedding | scientifically necessary once/model; already reused |
| Query/gallery tensor materialization | reusable across all eight models |
| Original scene underlying two query views and gallery | reusable within model and across models |
| Parquet scan, Python conversion, tar/Zarr extraction | safely cacheable or shard-batchable in future |
| Geometry Fourier features | deterministic; reusable across compatible models |
| DS raster input | deterministic; safely cacheable for a future P10 run |
| Non-local 2 km exclusion masks | reusable across models |
| Quantitative similarities/ranking | scientifically necessary once/model; already vectorized |
| Qualitative embeddings | already reused; no duplicate encoding found |

All such changes are unsafe to introduce into the active execution. They
require a new prepared-cache contract and equivalence tests before a future
run.

## Representation Analysis

Representation analysis runs once per model on the 1,600 x 128 gallery
embedding matrix:

- UMAP: `n_neighbors=15`, `min_dist=0.1`, cosine metric,
  `random_state=20260904`, `transform_seed=20260904`, `n_jobs=1`.
- HDBSCAN: `min_cluster_size=30`, `min_samples=10`, Euclidean metric,
  `cluster_selection_method=eom`, `allow_single_cluster=false`.

There is no accidental repeated fit in the model path. At this scale its
expected cost is minutes or less, not the observed eight-hour embedding cost.
The original cfg_d128 dependency failure demonstrates that the analysis
environment must bind the transitive scikit-learn version as well as UMAP and
HDBSCAN versions. The current authority records the direct package contracts
but this audit found a residual reproducibility risk if scikit-learn is not
also identity-bound. It does not justify interrupting the active retry.

## Completion Estimate

- Canonically complete: 2/8 models (25% by model count).
- Remaining: `cfg_d128` and A1-A5.
- A1-A5 had run about 8 h 11 min and were still making progress through P3
  source archives; they appeared near the late part of the dominant embedding
  path but lacked record-level progress counters.
- `cfg_d128` retry had run about 1 h 41 min and is the critical path.
- Estimated aggregate compute completion: approximately 80-85%, based on two
  complete paths, five late paths, and one early retry.
- Estimated remaining wall time under the current implementation: about
  5.5-7 hours, dominated by the cfg_d128 retry. This estimate assumes no new
  dependency or correctness failure.

## Bottleneck Ranking

1. **Per-record CPU source reconstruction**: dominant. Repeated tar/parquet/Zarr
   decoding and Python object conversion keeps one core busy per evaluator.
2. **GPU underfeeding**: direct consequence of serial preparation and
   synchronous CPU-to-GPU transfer; SM utilization is mostly zero.
3. **Repeated deterministic preprocessing across models/views**: large avoidable
   multiplier, scientifically safe only after a future cache contract is
   validated.
4. **DS raster and geometry feature construction**: family-specific CPU work,
   secondary to general source decoding.
5. **Compressed artifact serialization and representation analysis**: visible
   but minor compared with embedding.
6. **Retrieval/ranking and qualitative retrieval**: efficient enough at this
   scale and not material to total wall time.

There is no evidence of hardware storage saturation, memory pressure, GPU OOM,
or a deadlock. Process wall time and archive handles continue to advance.

## Safe Post-Run Recommendations

These are recommendations only; none was applied:

1. Publish a content-addressed prepared P10 input cache keyed by accepted
   P3/P5/evaluation/preprocessing identities. Store tensor-ready 3,200 queries
   and 1,600 gallery scenes once, then reuse them across the closed model set.
   Validation prepared-cache versus dynamic-record timing suggests a very
   large preprocessing reduction; a conservative end-to-end estimate is
   20-100x for the current input-bound path after equivalence validation.
2. If a full prepared cache is unsuitable, make the reader shard-aware: open
   each archive once, scan each parquet member once, extract raster arrays once
   per shard, and emit all requested scenes. Estimated input-stage speedup:
   5-20x.
3. Reuse one decoded original within a model for both augmented query views and
   the gallery. Upper-bound source-decoding reduction: about 3x.
4. Add DataLoader-style multiprocessing, bounded prefetch, pinned memory, and
   nonblocking transfers after determinism tests. Given 84% idle host CPU and
   0-38% GPU duty samples, a conservative end-to-end target is 3-6x.
5. Precompute identity-bound geometry features, DS raster tensors, and 2 km
   exclusion masks. Estimated affected-family improvement: 1.2-3x, potentially
   larger for DS rasterization.
6. Keep the current vectorized retrieval implementation. Moving its small
   matrix/ranking stage to GPU is lower priority and likely saves seconds, not
   hours.
7. Add monotonic stage and record counters for checkpoint load, input decode,
   transfer, forward, retrieval, qualitative, UMAP, HDBSCAN, serialization,
   fsync, and publication. This will replace bounds with exact timings.
8. Bind scikit-learn explicitly in the immutable representation-analysis
   environment contract to prevent the observed HDBSCAN API incompatibility.

## Current-Run Safety And Warnings

- Signals sent by this audit: 0.
- Interactive tmux attachments: 0.
- Process restarts: 0.
- Source/config/environment changes: 0.
- Evaluation artifact writes or mutations: 0.
- Cache generation: 0.
- Scientific execution initiated by this audit: 0.
- Tests or profilers requiring process injection: 0.

The completion estimate is necessarily approximate because current logs do not
record held-out record counters or internal stage transitions. The active P10
evaluation should be allowed to finish unchanged. Any optimization should be
implemented only after completion using a separately authorized, equivalence-
tested prepared-input path.
