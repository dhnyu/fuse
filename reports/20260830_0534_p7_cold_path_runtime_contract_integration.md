# P7 Cold-Path Runtime Contract Integration

## 1. Verdict

`P7_COLD_PATH_RUNTIME_CONTRACT_PASS_PUSHED`

The verified production-shaped cold path was integrated as an execution-only
runtime. It does not change or republish the accepted P6/P7 scientific lineage,
cache, checkpoints, run, or acceptance. A new runtime contract and acceptance
were published for future P9 training authorities.

## 2. Repository State

| Item | Start | Publication state |
|---|---|---|
| Fuse branch | `reduced` | `reduced` |
| Fuse HEAD | `9dd4d294da4a077b4f4917159a5584bf1f3980d4` | implementation commit `45e615d2e7889387c6deede39d185b6e01e76aa0`; final report commit and push recorded in the task response |
| Dissertation | `reduced`, `109355b3d744248ca14749c5f74511537970d660` | unchanged and clean |
| Initial ahead/behind | `0/0` | final `0/0` required after push |

Both repositories passed the clean/synchronized preflight. No reset, checkout,
stash, merge, or accepted-artifact overwrite was used.

## 3. Experimental Provenance

- Experiment worktree: `/tmp/fuse_p7_cold_prodshape_20260830_030352`
- Experiment branch: `experiment/p7-cold-production-shape-20260830_030352`
- Verified experimental diff SHA-256:
  `9abae9c5084600aa390335714b9a716c25dde031d27059f20192247ca4ca2167`
- Experiment report SHA-256:
  `dfac1346bd6cfbb59065943d08ccd1ddcfbf2bcf17c91206b2928f27beaa3153`
- Production implementation patch SHA-256:
  `bede9c5f22a2fcf4ddaf162acddbb1189018dbc7333615e8ea212494ca160944`

The experimental diff was audited by component. Production-adopted parts are
the spawn CPU pool, fixed-index staging, two single-context GPU producers,
canonical finalization, eager preload, memory admission, observability, and
parity harness. Experiment-only paths, caches, checkpoints, and diagnostics
were not copied into tracked source.

## 4. Adopted and Excluded Changes

`PRODUCTION_ADOPT`: 32/24/16 worker tiers, one native thread per worker,
CUDA-free CPU initialization, fixed global-index results, one producer per GPU,
batch size one, even/odd assignment, canonical manifest order, no-rewrite
finalization, eager preload, RNG gate, GPU locks, and runtime metrics.

`TEST_ONLY`: synthetic incomplete/corrupt staging, fixed-index collision,
CUDA-initialized worker, memory fallback, unsafe cleanup, and no-rewrite cases.

`REJECT/EXCLUDE`: 40-worker default, GPU batch size four, full-tensor pickle
queues, cross-rank mutable host cache, completion-order publication, layout-v2
fallback, and any P7 scientific configuration change.

## 5. Runtime Identities

| Artifact | Identity | Payload SHA-256 |
|---|---|---|
| Runtime contract | `p7rt_713d65cfbba7abf2f58e5097` | `ac05e9b05cda9819b6b4149e70a650fbdb3eb1eeec7d45c7556f7c2aa4c8d9c1` |
| Runtime acceptance | `p7rta_c780441a553abe26772827d0` | `ba7ee1f477aa481909268cea472cc0dc09984a1c18b4a81cc3327354abfaa744` |

Both artifacts bind source commit `45e615d2e7889387c6deede39d185b6e01e76aa0`.
The runtime acceptance is additional execution provenance, not a replacement
for `p7acc_3c78cc0e85b93aec6a0cc02c`.

## 6. Parent Lineage

- P6 v3 aggregate: `mda_b07032bd970d101ec1da7a4b`
- P7 authority: `p7a_99b71dcd4fc17e00b1cad76e`
- P7 run: `p7run_d5947018e270c55ae60f2696`
- P7 acceptance: `p7acc_3c78cc0e85b93aec6a0cc02c`
- Best checkpoint: `p7ck_7d25fec7944dc108c5849cd7`
- Latest checkpoint: `p7ck_294f2e926ed88ee63e0bb267`
- Geometry cache: `p7gc_4de4a140d54765f01a30e656`
- Geometry layout/cache schema: `3.0.0`

## 7. CPU Preparation Pool

The pool uses multiprocessing `spawn`. All computational thread environment
variables and Torch intra-op threads are one per worker. A worker fails before
input construction if CUDA was initialized. Tasks and results bind canonical
global index, role/scene/view identity, cache key, source-derived sample digest,
payload size, and SHA-256. Missing, duplicate, stale, or foreign results fail
before final publication.

## 8. Memory Admission and Fallback

| Tier | Required admission memory | Policy |
|---:|---:|---|
| 32 | 332,859,965,440 bytes (310 GiB) | preferred |
| 24 | 252,329,328,640 bytes (235 GiB) | first fallback |
| 16 | 171,798,691,840 bytes (160 GiB) | minimum fallback |

The model uses 8 GiB fixed overhead, 7.5 GiB per worker, and a 25% safety
margin, grounded in the measured 32-worker peak and maximum worker RSS. Unsafe
worker overrides cannot bypass admission. The verified run selected tier 32.
Swap-in delta was zero. If tier 16 cannot be admitted, the build fails closed.

## 9. GPU Producer Lifecycle

The controller creates two subprocesses before the spawn CPU pool begins work.
Each producer owns exactly one CUDA context. GPU 0 consumes even canonical
indices and GPU 1 odd indices; each produced 1,072 entries. Producer batch size
was one. Completion order never entered the manifest identity.

Producer walls were 593.12 s and 589.67 s, an imbalance of about 0.58%.
Peak producer VRAM allocation/reservation was below 46/61 MB per GPU.

## 10. Fixed-Index Staging and Publication

The handoff has exactly 2,144 disk slots and used 2,854,021,856 bytes. CPU
workers atomically transition each prepared payload into its index slot. GPU
entries are also written through temporary paths and atomic transitions. The
manifest is canonical and the valid marker is published last after full entry
validation. A partial namespace has no accepted marker. A second finalization
verified every identity and returned without changing manifest/marker mtime or
bytes.

Staging roots overlapping the accepted prototype root or research target store
are rejected. Free-space admission includes prepared, final, validation
temporary, and 25% safety overhead. Cleanup accepts only an exact expected
namespace and rejects completed caches.

## 11. Eager Preload and RNG

Both ranks loaded all 2,144 required training and distributed-validation views
in canonical index order before update 1. Rank preload walls were 6.378 s and
6.354 s. Python, NumPy, Torch CPU, CUDA, sampler, view, and mask scientific RNG
state digests were identical before and after preload. A deterministic barrier
occurred only after both ranks validated complete coverage.

## 12. Full Cache Verification

| Metric | Result |
|---|---:|
| Entries | 2,144 / 2,144 |
| Missing / duplicate / corrupt | 0 / 0 / 0 |
| Raw tensor parity | 2,144 / 2,144 exact |
| Candidate / accepted cache ID | `p7gc_4de4a140d54765f01a30e656` / same |
| Candidate / accepted manifest SHA | `0f0cc30ae6f74007ef50e1b3802cd2affb477646f98db3a62a6f07c12d2b3bc3` / same |
| Problem candidate coordinates | 28 |
| Wrong ranges / Fourier corruption | 0 / 0 |

The complete readback verifier passed in 3.256 s. Plan SHA-256 was
`78336a258cf89af37b676ac12b1fca1b2a02130d39591997168a21c9cd7a2004`.

## 13. Cache-Build Performance

| Metric | Accepted production | Integrated verification |
|---|---:|---:|
| Wall | 2,176.04 s | 616.20 s |
| Reduction | - | 71.68% |
| CPU/GPU pipeline | - | 613.42 s |
| Canonical finalize/readback | - | 2.73 s |
| Prepared bytes | - | 2.854 GB |
| Final cache bytes | 2.093 GB | 2.093 GB |

Mean system CPU utilization was 70.70%. Mean GPU utilization during the
CPU-limited build was 22.82%/22.68%; this is observability evidence, not an
acceptance threshold. GPU producer queue wait was 101.01/126.36 s.

## 14. First-40 Training and Validation

| Metric | Result |
|---|---:|
| Trace records | 40/40 exact |
| Preload + updates + validation/checkpoint wall | 28.76 s |
| Update wall sum | 20.52 s |
| Median / p95 update | 0.5034 / 0.7342 s |
| Validation wall | 0.1297 s |
| Checkpoint wall | 0.0940 s |
| Validation coverage | 96, missing 0, duplicate 0 |
| Retrieval loss | 0.6880882382392883 |
| Margin | 0.13164612650871277 |
| State digest | `3f7a00befcccaa2aa66b9b472b432a3ae3af1c7a7618139be3857fed5dc44e6a` |

Scene/view/mask order, losses, gradients, optimizer/scheduler, model/EMA,
queue bytes/order/pointer/count, RNG, validation embeddings and selector input
matched the accepted first-40 trajectory exactly.

## 15. Resume Parity

Uninterrupted 40 updates and 20 updates plus a fresh two-rank resume to update
40 produced the same 40-record trace, validation result, checkpoint identity
`p7ck_3f7a00befcccaa2aa66b9b47`, and canonical state digest. Resume parity is
exact; no accepted checkpoint was read as a resume source or modified.

## 16. Runtime Resources

- Cache-build peak aggregate RSS: 251,980,738,560 bytes (234.68 GiB).
- Cache-build swap-in delta: 0; major worker faults: 0.
- First-40 peak aggregate RSS: 14.35 GB.
- Training peak allocated/reserved VRAM: 2.81/6.20 GiB.
- First-40 sampled GPU utilization: 25.10%/17.08%, including preload/startup.
- GPU processes and held locks after each gate: 0/0.

## 17. Failure and Restart Contract

Worker or producer failure, timeout, wrong digest, missing/duplicate index,
memory-cap violation, swap-in beyond the declared limit, partial publication,
foreign staging, and corruption all fail closed. An interrupted namespace is
not accepted without a complete validated marker. Existing completed cache
finalization is idempotent and does not rewrite it.

## 18. Target Execution and No-Op

The first explicit `p7_cold_path_runtime_acceptance` selection completed only
the four new runtime targets and skipped 1,020 targets. No GPU target ran. The
immediate repeated selection skipped all 1,024 reachable targets: builds 0,
GPU execution 0, staging creation 0, and runtime artifact rewrites 0.

`tar_validate()` passed and no runtime target remained outdated. The existing
P7 acceptance and geometry-cache targets remained current.

## 19. Tests

- Python full suite: 182 passed.
- Focused final P7 runtime/cache/training suite: 24 passed.
- R full non-execution suite: PASS with exactly three documented legacy skips.
- Python AST/compile, R parse through suite, YAML/JSON parse: PASS.
- Runtime contract/acceptance JSON Schema validation: PASS.
- `targets::tar_validate()`: PASS before and after publication.
- Target manifest/network tests and regenerated HTML: PASS.
- `git diff --check` and staged `git diff --cached --check`: PASS.

## 20. Existing P7 and P8 Compatibility

Existing P7 acceptance, best/latest checkpoints, cache and manifests were
unchanged. P8 remains bound to acceptance
`p7acc_3c78cc0e85b93aec6a0cc02c` and best checkpoint
`p7ck_7d25fec7944dc108c5849cd7`; latest-checkpoint fallback is prohibited.
The runtime acceptance is not a P8 scientific parent.

## 21. Future P9 Binding

Every future P9 training authority must bind both its P6/P7 scientific lineage
and runtime acceptance `p7rta_c780441a553abe26772827d0`. The binding records
the selected admitted worker tier as runtime evidence without changing the
scientific cache/manifest identity.

## 22. Immutability Audit

The accepted pre/post inventory covered 6,362 existing files. Existing changed
files: 0; missing files: 0. Exactly two new runtime JSON artifacts were added.
The research target store had no existing payload mutation; only the normal
`meta/crew`, `meta/meta`, `meta/process`, and `meta/progress` files changed for
the explicit new target execution.

P3-P7 accepted artifacts, accepted cache/checkpoints, dissertation sources,
and non-target runtime payloads had mutation count zero.

## 23. Non-Execution

- Full P7 training executions: 0.
- P8/P9 executions: 0.
- Evaluation/maintenance executions: 0.
- Existing checkpoint/cache rewrites: 0.
- System-wide page-cache manipulation: 0.

## 24. Changed Files

Tracked changes comprise the runtime Python module/CLI, runtime YAML and two
schemas, R orchestration and four target declarations, focused Python/R tests,
P7 schema/manifest regression updates, blueprint evidence, `_targets.R`, the
regenerated dependency network, and this report. Runtime cache, prepared
staging, checkpoints, logs and inventories remain outside Git.

## 25. Evidence Locations

- Integration evidence:
  `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p7_cold_path_runtime_integration_20260830_045824`
- Verification record:
  `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p7_cold_path_runtime_verification/active_verification/verification.json`
- Verification record SHA-256:
  `3c9fecc4ce28e8d1e8b841ecf5e1cb845e63b4ed3853f3d54bd0b61521919cb9`

## 26. Commits and Push

- Implementation commit: `45e615d2e7889387c6deede39d185b6e01e76aa0`
  (`Implement P7 cold-path runtime contract`).
- Final publication commit and pushed `origin/reduced` SHA are reported in the
  task response because a Git commit cannot contain its own SHA.
- Required post-push state: local/remote exact, ahead/behind `0/0`, both
  worktrees clean.

## 27. Warnings

The 32-worker build remains CPU-materialization limited and has a high but
bounded 234.68 GiB aggregate RSS peak. The 24/16 thresholds are deliberately
conservative modeled fallbacks; the selected production-shaped verification
used tier 32. This runtime integration does not claim a new P7 scientific
result and does not justify changing the accepted P7 metrics.

## 28. Next Work Unit

Audit and implement the P8 methodology and target contract using the unchanged
canonical P7 acceptance and best checkpoint. Do not treat the runtime
acceptance as a replacement scientific parent.

## 29. Prompt Summary

The approved task requested production integration and publication of the
verified 32-process deterministic CPU pool, two single-context GPU producers,
fixed-index staging, canonical publication, eager preload, memory fallback,
failure/restart rules, parity gates and runtime observability, without rerunning
full P7 or changing existing P6/P7 scientific artifacts.
