# P10 Prepared Input Optimization And Re-execution

## Verdict

`P10_PREPARED_INPUT_OPTIMIZATION_PASS_PUSHED`

`P10_REEXECUTED_WITH_PREPARED_INPUT_PIPELINE`

The optimization was committed and pushed as `4911c66` before the replacement
execution started. The replacement is an operational retry of the same closed P10
contract, not a new evaluation design or consumption event.

## Scope And Repository State

- Execution date: 2026-09-04 KST.
- Fuse branch: `reduced`.
- Starting HEAD: `1bfc7e7eedb046345b80ca8cb82cfe06d911a3e3` (the preceding read-only audit commit).
- Optimization HEAD: `4911c66`.
- Dissertation: `reduced` at `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, unchanged.
- Input prompt: stop only the active P10, preserve consumed/completed evidence,
  replace repeated scene reconstruction with exact prepared inputs, prove
  equivalence/performance, push first, then retry the same fixed eight-model P10.

The active dissertation P10 methodology and repository blueprint were checked before
implementation. The fixed eight-model set, P9 validation gate, 1,600-scene held-out
population, 3,200 queries, 1,600 gallery scenes, qualitative queries, 2 km exclusion,
retrieval metrics, UMAP/HDBSCAN settings, and interpretation contract are unchanged.

## Interrupted Attempt

Only tmux session `p10_model_shards_20260904` and its P10 evaluator/controller
processes were sent `SIGTERM`. The affected evaluator PIDs were `291189`, `4190372`,
`4190375`, `4190380`, `4190427`, and `4190482`; launcher/watchdog PIDs were scoped to
the same session. Their logs end with exit code 143. No unrelated tmux session or
process was signaled.

Immutable interruption evidence:

- Interruption: `p10int_192c1a7fb94ed0825764988c`
- Reason: `OPERATOR_REQUESTED_PERFORMANCE_REMEDIATION_P10_INPUT_PIPELINE`
- Authority: `p10auth_8b6919578aaa24fa8f1b98a2`
- Consumption: `p10cons_7d0eba832b70d545fc5d3eb4`
- Preserved complete models: `cmp_ssv_like`, `cmp_ds_like`
- Preserved incomplete models: `cfg_d128`, A1, A2, A3, A4, A5

The original 26 canonical files, including all eight validation revalidations and the
two completed evaluations, passed pre/post SHA-256 readback. Partial logs and outputs
were retained. Consumption remains the original committed transition `{before: 0,
after: 1}`; it was neither reset nor duplicated.

## Prepared Cache Contract

The evaluator now uses one immutable tensor-ready cache shared by all eight models.
Its identity binds the accepted P9 validation prepared cache, fixed P10 evaluation
split/query/gallery evidence, ordered scene/view identities, P3/P5 source hashes,
preprocessing/category contracts, batch size, tensor schema/dtype/layout, deterministic
DS rasters, and the fixed 2 km mask.

| Artifact | Identity | Manifest SHA-256 | Coverage | Build wall |
|---|---|---|---:|---:|
| Prepared input | `p10pi_da45b59753b561948fea78f5` | `4cfe28a85b735252e86070669fe19b6a490a42af7253c17a8bdbe5713f7305f6` | 6,000 records / 750 batches | 622.61 s |
| Prepared geometry | `p10geo_8cdab54a6886cb8217c0088b` | `94baa369361e3493fc6febcf3a83ce475394ddaf492013887dae711c3391cdfa` | 600 evaluation batches | 1,162.59 s |

The prepared cache is about 15 GiB and the geometry cache about 6.3 GiB. Both were
fully payload-hash validated after atomic same-filesystem publication. Formal P10 has
no dynamic fallback. Missing files, traversal/symlinks, wrong size/hash, stale contract,
invalid ordered inventory, malformed payload identity, or wrong parent cache fail
closed. A first cache built during development bound the wrong validation source; it
and its geometry derivative remain immutable superseded diagnostic artifacts and are
not referenced by the formal attempt.

The loader uses eight multiprocessing workers, bounded prefetch of two batches,
pinned host memory, nonblocking H2D transfer, and batch-level tensor assembly. The
fixed evaluation geometry Fourier tensors were materialized with the accepted
vectorized implementation on two RTX A6000 GPUs. Retrieval/ranking code was unchanged.

## Exact Equivalence

The bounded noncanonical pilot compared the old constructor and prepared payloads at
first/middle/last query and gallery boundaries for both validation and held-out data.

- All nested tensors, dtypes, shapes, IDs, ordering, and model inputs: bitwise equal.
- Dynamic versus cached DS raster tensors: bitwise equal.
- `cfg_d128` and DS-like embeddings: bitwise equal.
- Retrieval and qualitative ranking: equal.
- Fixed 2 km exclusion mask: bitwise equal.
- No training, optimizer update, checkpoint write, or evaluation publication occurred.

The complete cfg_d128 validation revalidation reproduced exactly:

| Metric | Immutable expected | Prepared reproduced | Delta |
|---|---:|---:|---:|
| Retrieval loss | 0.17650695145130157 | 0.17650695145130157 | 0 |
| Mean source-separation margin | 0.3754689395427704 | 0.3754689395427704 | 0 |

## Performance

Representative old dynamic held-out batches required 37.72-44.22 seconds for eight
records. The prepared pilot processed 16 batches in 11.14 seconds including worker
startup, or 11.49 records/s and a 63.5x startup-amortized speedup. Steady measurements:

| Stage | Median | p95 |
|---|---:|---:|
| Input wait | 0.00034 s | 2.704 s (initial prefetch) |
| Geometry lookup/H2D | 0.00198 s | 0.00457 s |
| Batch H2D | 0.00100 s | 0.00214 s |
| Forward | 0.01653 s | 0.02223 s |
| Whole batch | 0.02204 s | 2.729 s (initial prefetch) |

Peak pilot allocation was 646,722,048 bytes. Active GPU samples reached 40% SM;
one-second sampling undersamples the approximately 22 ms batches. The first formal
replacement model (`cfg_d128`) subsequently completed all 600 held-out batches,
retrieval, qualitative output, UMAP, HDBSCAN, and publication in 36.18 seconds. The
previous implementation required roughly eight hours per model. This demonstrates
that the one-core reconstruction/GPU-starvation bottleneck has been removed.

## Reproducible Environment

Formal retry startup compares installed versions exactly against the immutable attempt
contract and fails on any mismatch:

- PyTorch `2.12.0+cu130`
- NumPy `2.4.6`
- scikit-learn `1.7.2`
- umap-learn `0.5.9.post2`
- hdbscan `0.8.40`
- PyArrow `22.0.0`

This pins the scikit-learn/HDBSCAN interface that caused the earlier operational
failure. UMAP/HDBSCAN scientific parameters and seeds did not change.

## Replacement Execution

- Execution attempt: `p10exec_7fee193dac532190c79e02c6`
- Base authority: `p10auth_8b6919578aaa24fa8f1b98a2`
- Existing consumption: `p10cons_7d0eba832b70d545fc5d3eb4`
- Tmux session: `p10_prepared_reexecution_20260904`
- Log: `logs/20260904_p10_prepared_reexecution.log`
- Reattach: `tmux attach -t p10_prepared_reexecution_20260904`
- Launch command: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python python scripts/p10_evaluation.py --contract config/p10_evaluation.yml --reexecute`

At report publication, prepared-cache progress logs showed cfg_d128 complete and A1
running. The cfg_d128 result is committed only inside the new execution-attempt
namespace; original SSV-like/DS-like commits were not overwritten. The new result used
the exact 3,200/1,600 query/gallery counts and reported held-out retrieval loss
0.5894929171, margin 0.2855600119, MRR 0.9970607758, HIT@1 0.9956250191,
HIT@5 0.9996874928, and HIT@10 1.0. These values do not reopen P9 selection.

## Validation

- Focused P10/schema/cache/interruption tests: 15 passed, 0 failed.
- Combined P9/V2/P10 Python regression: 325 passed, 0 failed in 202.26 s.
- Relevant R expectations: 61 passed; two documented stale v1 generation assertions
  failed unchanged (`p9gen_acb72...` expected versus historical
  `p9gen_batchuniq_20260831`).
- `tar_validate()`: main, P9 formal, P9 recovery, P9 V2 training, and P10 passed without
  scientific execution.
- Draft 2020-12 schemas: 130 parsed and meta-validated; P10 fixture validated.
- Python compile, R parse (98 files), config JSON parse, and `git diff --check`: passed.
- P10 target network regenerated: 7 targets, 9 edges, one weak component.

## Safety And Immutability

| Activity | Count |
|---|---:|
| Training / optimizer updates | 0 |
| Checkpoint creation, mutation, or reselection | 0 |
| P9 reruns / hyperparameter tuning | 0 |
| New evaluation authority or consumption | 0 |
| Model-set / qualitative-query / analysis-contract changes | 0 |
| P11 execution | 0 |
| Dissertation mutation | 0 |
| Existing SSV-like/DS-like evaluation rewrites | 0 |

The same eight acceptance/checkpoint resolver bindings are used. The retry attempt
binds the new implementation/cache/environment while retaining the original closed
authority and consumption. Existing P9 and P10 canonical evidence passed resolver and
SHA-256 readback.

## Next Action

Allow `p10_prepared_reexecution_20260904` to finish. Then audit all eight attempt
results, reproduce the committed aggregates, publish/read back the single P10
acceptance for this attempt, and report the exact P11 work unit from the active
roadmap. Do not start P11 before P10 acceptance passes.
