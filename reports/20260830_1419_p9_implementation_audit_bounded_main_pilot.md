# P9 Implementation Audit and Bounded Main Pilot

## Verdict

`P9_IMPLEMENTATION_AUDIT_AND_BOUNDED_MAIN_PILOT_PASS_PUSHED`

This verdict is conditional on the publication push recorded in the final response. The work unit
implemented P9 infrastructure, ran an externally namespaced 40-update `cfg_main` pilot, and
published infrastructure readiness only. It did not authorize or execute a formal P9 attempt.

## Scope and inputs

- Execution time: 2026-08-30 12:30-14:20 KST.
- Fuse starting commit: `54dabb111418a503209cead26967d95482563a54` (`reduced`).
- Dissertation binding: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a` (`reduced`).
- P8 acceptance: `p8acc_c9f16a07275aadfae928d329`.
- P8 hyperparameter/comparison matrices: `p8hm_f34f1666b62255babab0ae08` and
  `p8cm_cd7d0f45dd41a7c351ea4d78`.
- P8 A5/DS contracts: `p8a5_497d83d2e948107488b44397` and
  `p8ds_73137985bd6b172f6711a062`.
- P8 bank index: `p8bi_2e492527089bf5ce9d00a933`.
- P7 runtime acceptance: `p7rta_c780441a553abe26772827d0`.
- Input prompt summary: audit and implement P9-A/P9-B infrastructure and all eight model
  families, then execute only a temporary production-shaped `cfg_main` pilot capped at 40
  updates with one validation and exact resume comparison.

The dissertation Typst source and the accepted P8 artifacts agreed on the nested A1-A5, SSV,
and DS contracts. No methodology conflict was found.

## Implementation audit

| Area | Disposition | Result |
|---|---|---|
| P6 v3 scene tensorization and P7 deterministic objective | `REUSE_EXACT` | Reused without changing geometry or loss semantics. |
| D6 DDP, EMA, queue, validation and checkpoint primitives | `ADAPT_FOR_P9` | Full-population sampler and P9 seed/schedule routing added. |
| P9 authority/run/checkpoint/acceptance schemas | `NEW_IMPLEMENTATION_REQUIRED` | Versioned schemas added, but no formal artifact was published. |
| P9-A matrix routing | `NEW_IMPLEMENTATION_REQUIRED` | All 13 P8 rows route d/K/intensity/EMA/IP/LR independently. |
| P9-B materialization | `NEW_IMPLEMENTATION_REQUIRED` | Fails closed until a stable selected-FM identity exists. |
| Legacy P7 checkpoint warm start | `LEGACY_REJECT` | Prohibited by configuration and tests. |
| Evaluation queries in P9 ancestry | `LEGACY_REJECT` | Reader and readiness contract reject access/injection. |

The full sampler contains 2,421 unique training scenes plus 11 explicit rotating padding
identities, yielding 2,432 consumptions, 76 global batches, and duplicate-scene negative
exclusion. The readiness graph contains only contract-file and readiness targets; it has no
reachable training command.

## Model families

Inactive modules are not instantiated and `find_unused_parameters` remains false. Actual-data,
two-rank forward/loss/backward smokes reported zero missing active gradients and zero optimizer
updates.

| Family | Active contract | Parameters (d=64) | Result |
|---|---|---:|---|
| FM | all modalities, raster, heterogeneous relations | 934,420 | PASS |
| A1 | relative position + intrinsic geometry | 233,587 | PASS |
| A2 | A1 + semantics | 638,778 | PASS |
| A3 | A2 + object LC/DEM context | 660,180 | PASS |
| A4 | A3 + scene raster, no relations | 827,316 | PASS |
| A5 | A4 + one generic relation on exact FM edges | 934,292 | PASS |
| SSV | relative position + semantics | 479,930 | PASS |
| DS | 26-channel 100 x 100 raster, no IP | 97,056 | PASS |

A5 preserved directed edge instances, direction, and multiplicity on both ranks and mapped all
labels to one `GEN` embedding. It never reconstructed a radius graph. DS produced
`[4, 26, 100, 100]` tensors per rank, reused realized DEM perturbations through cell-center
bilinear interpolation, zeroed masked land-cover composition channels, and rejected incomplete
support. A2 and SSV differ only by intrinsic geometry.

FM d=48, d=64 and d=128 all passed two-rank actual-data forward/loss/backward. The d=128 peak
allocated VRAM was 473,221,120 bytes on rank 0 and 527,391,744 bytes on rank 1 for the bounded
rank-batch-four smoke. No legacy d128 artifact was adopted.

## Cache and population audit

The P7 prototype cache was not treated as a P9 production cache. Cache identities distinguish
view/bank/layout-dependent geometry, FM heterogeneous edge labels, A5 generic runtime mapping,
and DS raster materialization. Model dimension, EMA, IP weight and learning rate do not alter the
geometry-feature bytes.

- Full main-K8 geometry requirement: `2,421 * 8 + 1,200 = 20,568` entries.
- Bounded pilot cache: 3,760 entries (2,560 selected training views, 800 queries, 400 galleries).
- Bounded raw bytes: 5,361,063,936; disk bytes: 5,384,758,250.
- Extrapolated main-K8 disk requirement: about 29.5 GB. This is a projection, not a production
  acceptance measurement.
- Build duration: about 1,606 seconds with 32 CPU preparation workers and two GPU producers.
- Accepted P7-cache overlap: 386/386 identity, magnitude, and phase tensors exact; mismatch 0.
- Evaluation entries: 0.

An initial cache attempt was stopped before training when per-worker reader caches caused
unbounded aggregate RSS. Workers were changed to clear execution-only reader caches per task;
the succeeding run completed. A later lazy trajectory was also stopped before acceptance because
it bypassed the accepted eager-preparation path. These fail-closed diagnostics were not counted as
formal attempts.

## Bounded cfg_main pilot

The final pilot evidence is stored at
`/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_bounded_main_trajectory_eager_20260830_135426/`.
It used two RTX A6000 GPUs, FP32 deterministic DDP, global batch 32, rank batch 16, the accepted
main K8 bank, and no evaluation queries.

| Metric | Uninterrupted 40 | 20-update interruption | Resume to 40 |
|---|---:|---:|---:|
| Preload entries/rank | 1,880 | 1,880 | 1,880 |
| Preload wall | 3.260 s | 3.266 s | 3.240 s |
| Trajectory wall | 28.156 s | 13.275 s | 15.658 s |
| Update median | 0.6164 s | 0.6281 s | 0.6224 s |
| Update p95 | 0.8527 s | 0.8484 s | 0.8983 s |
| Peak allocated VRAM | 4.615 GB | 4.615 GB | 4.547 GB |
| Final state SHA-256 | `a4b7b43c...e15a4f` | `c194bf07...36429e` | `a4b7b43c...e15a4f` |

Preload preserved the combined rank RNG digest exactly
(`b40e19a7303440d61a3b0879db39763004a008d313d2e862db12883cff8d65c0`).
Uninterrupted and resumed traces, online/EMA model, optimizer/scheduler, queue, sampler, RNG,
checkpoint canonical state and final state digest were exact.

The single distributed validation covered 800 queries and 400 galleries exactly once, with
missing/duplicate counts 0/0. Validation retrieval loss was `3.3906667232513428`, mean margin
was `0.04601933807134628`, and the embedding digest was
`9f26058c41b74e0dee681e160e139c7544ee27ef5efd1ddc28a3948659bc2157`.
The resumed validation was exact.

Historical P7 first-40 bytes are not an authoritative equality target: P9 derives a
configuration-specific seed (`1749989426`), uses 2,421-scene rotating padding, and uses a
760-update warm-up rather than the P7 prototype population/schedule. The unexplained-divergence
gate was instead applied to two executions from the identical P9 scientific state; that gate
passed exactly.

Controller NVML sampling covered 97.75 seconds across three sequential trajectory processes.
Mean utilization was 21.58%/21.79%, nonzero coverage 50.32%/50.32%, and observed peak 100% on
both GPUs. Peak `nvidia-smi` memory was 7,683/7,929 MiB. Minimum host `MemAvailable` was
732.6 GiB. The aggregate utilization is not a steady-training estimate because checkpoint/resume
process startup and validation are included.

## Readiness publication

- Implementation commit: `9e700754023c548d9940acba854f4559a05888a3`.
- Readiness ID: `p9ready_521c12a65d9b2984fac2cf11`.
- Readiness content SHA-256: `521c12a65d9b2984fac2cf11dedc31530a144863c52fee4d8cd97fa03cbfa24a`.
- Artifact file SHA-256: `40c7af3ab9943ad0a4e67498d24dcaa0552ef10fc4e2316bf9edd43f3f1732e9`.
- Counts: 13 hyperparameter configurations, 7 comparison templates, 0 formal attempts,
  0 optimizer updates.
- First explicit make: 2 targets built.
- Repeated explicit make: 2 targets skipped, builds 0, artifact rewrite 0.
- P9 outdated count after no-op: 0. The 124 unrelated historical outdated targets were not run.

This readiness record is not a P9 scientific authority, run, selection, checkpoint, or
configuration acceptance.

## Validation

- Focused Python: 25 passed.
- Full Python: 216 passed.
- Focused R: passed.
- Full R/testthat: passed with exactly three documented legacy skips.
- Eight new JSON Schemas: JSON parse, Draft 2020-12 metaschema and artifact validation PASS.
- Python AST, R parse, YAML parse and `git diff --check`: PASS.
- `targets::tar_validate()`: PASS.
- Target manifest: 164 targets; only P9 readiness targets added.
- Dependency network: regenerated and validated.
- Dissertation Typst: compiled read-only with Typst 0.15.1; existing unavailable Korean-font
  warnings only.
- GPU processes and P9 locks after execution: 0/0.

## Immutability and non-execution

- P1-P8 scene-data inventory: 60,428/60,428 path/size/mtime exact.
- Preflight partial payload hashes: 3,733/3,733 exact.
- Existing model artifacts: 2,391/2,391 SHA-256 exact; one new readiness JSON was added.
- Target-store payload changes: 0. Normal target metadata changed only in
  `meta/{meta,progress,crew,process}`.
- Existing cache/checkpoint mutation: 0.
- Formal P9 attempts: 0; non-main formal executions: 0.
- P9-A selection/P9-B materialization: 0/0.
- Evaluation/P10/P11/maintenance execution: 0/0/0/0.
- Permanent checkpoint creation: 0. All bounded checkpoints remain under the external temporary
  namespace and are not tracked.

## Changed source

The implementation adds P9 configuration, eight schemas, full-population data routing, the
eight-family registry, bounded smoke/pilot entry points, focused Python/R tests, two plan-only
targets, blueprint evidence, and the regenerated dependency network. No runtime cache,
checkpoint, log, target store, or credential is tracked.

## Warnings and next step

The full main-K8 cache requirement is projected rather than built, and only `cfg_main` was run
for 40 updates. Formal authority construction, full production-cache sizing/admission, a
production-scale main pilot authorization, duplicate-attempt locking, and formal selection
publication remain separate gates.

The next work unit is the formal P9 implementation/authorization audit: review production cache
resources and authority/run publication paths, then explicitly authorize the canonical
production-scale `cfg_main` run before any of the 20 formal attempts begins.
