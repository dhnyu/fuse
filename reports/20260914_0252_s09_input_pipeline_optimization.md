# S09 CPU Input Pipeline Optimization

## Scope And Verdict

Created 2026-09-14 02:52 KST. Request: optimize recurring CPU projection/masking without changing scientific values, seed bytes, checksums or fail-closed contracts; qualify disposable execution; preserve the interrupted campaign; commit/push only on PASS.

Input HEAD: `844d07e1a7df94c905eb2daeedd3ea7dfcc591ff`, branch `reduced`.
Authoritative baseline: `reports/20260914_0232_s09_stopped_input_bottleneck_audit.md`.

Implementation/validation verdict: **PASS_S09_INPUT_PIPELINE_OPTIMIZED_FRESH_CAMPAIGN_REQUIRED**.
Git publication status is recorded in the Git section after the final publication gate.

Formal training restarted: NO. Interrupted checkpoint resumed: NO. New production checkpoint/result/authority: NO. Prepared cache rebuild: NO. Manual target-store edits: NO. S10: NO.

## Preconditions And Protection

- Local `reduced` and fetched `origin/reduced` synchronized, 0/0; tracked worktree clean before implementation.
- Research outdated set empty before and after source changes.
- No formal controller, torchrun/DDP ranks or GPU compute workload at preflight.
- Canonical GPU pair/device locks available.
- Canonical cache `s09cache_dc4e9e271e40ffe8ae17967c`, acceptance `s09ca_e2a1882eb206e1b5c930ddd5`.
- SSD root `/members/dhnyu/fuse-cache/s09cache_dc4e9e271e40ffe8ae17967c`.
- Before/after receipt/inventory validation PASS: 241,422 files / 316,304,040,996 bytes; inventory `b62b68806b9e2633025195d9b4f9203dbe25c07d0db9b2169fcd6b30ac031b0f`.
- Protected 2,811 unique files by SHA-256, including interrupted ledger/checkpoint, historical evidence, formal logs, S08, cache acceptance/manifests, receipt, and research/training store metadata. After-check: zero changes.
- Checkpoint `p9ck_8cb9e8264463a35bbbdc56a6` remains intact: payload SHA `44914bbb504abf848a10ecfa35259c42a714e37a4dfebde8431e5299b53a9db3`.

Replica validation checks the receipt, canonical identities, inventory paths/sizes and metadata hashes; production readers continue hashing accessed prepared/geometry/DS payloads. This task did not rehash every byte of the 296-GiB payload inventory. No code in the task writes those payloads.

## Scientific Contract And Implementation

Reviewed the dissertation's `04-methodology-training.typ`, Training-time View Selection and Modality Masking, and `results/01-experimental-setup.typ` family definitions. No conflict or scientific definition change was introduced. The current corrected A1/A2/B1/SSV semantics, not their historical buggy versions, are the equivalence reference.

Only production file changed: `python/training_family_inputs.py`.

### Projection

- Vectorized prefix sums and selected segment expansion using indexed starts, lengths and repeat-interleave. No Python torch.arange call per entity/part.
- Full-retention contiguous segments use one range when retained rows are exactly the original ordered identity map and offsets start at zero. This is a structural identity fast path, not a blanket family bypass.
- Ring-coordinate construction uses the same segment operation; ring-owner bounds are checked vectorially instead of per entity.
- Source membership uses tensor membership; original local entity IDs, compact mappings, Fourier rows, edge order/masks, topology, environmental blocks and scene raster routing retain their original semantics.
- Deep copies are retained. Output cannot mutate immutable input storage. Floating payload values are selected/copied, not recomputed.

The same identity-segment optimization applies wherever a structure is fully retained: OFAT/FM and entity-retaining comparison families. It does NOT bypass A3's edge removal, A4's generic relation routing, A-series raster removal, B8/B9 environmental filtering or B2-B7 induced graph/source projection.

### Validation

No cache structural check was removed or moved behind a trust flag. Pre- and post-projection validation remain active; only equivalent ring-owner checks were vectorized. Unknown fields, bad dtypes, invalid offsets/owners, topology and relation failures remain fail-closed. Since vectorization materially reduced validation cost, an immutable-validation cache was not introduced: this avoids a new mutation/invalidation proof obligation.

Prepared, geometry, DS and SSD receipt verification code is unchanged.

### Masking

`EntitySeedBytes` prevalidates fixed seed fields per scene/view/rank/epoch and operation. Keys and fixed values use the existing canonical encoder; the only inserted value is a checked integer local_entity_id in canonical decimal form. Sorted keys, escaping, UTF-8 encoding, separators and trailing newline are unchanged. SHA-256 and extraction of the 63-bit seed are unchanged.

The gate and available-modality operation each have their own template. Eligibility, mask probability, namespace, stable entity identity, epoch/rank/view/worker fields and global-to-local modality mapping are unchanged. Availability choices are converted once per batch instead of calling torch.where for each selected entity. No global RNG state, alternative RNG or Python hash is introduced.

## Equivalence Evidence

Baseline production files were frozen before editing under `/tmp/s09_input_opt_20260914/`. Their source hash reconstructs the exact original runtime SHA. No historical scientific run was used as initialization.

- Canonical frozen fixture: `tests/fixtures/s09_corrected_input_reference.json`, generated with the pre-edit corrected implementation at the input HEAD. 17 families x three source populations, including empty and zero-edge cases; exact projected/batch/mask digests.
- New regression file: `tests/python/test_training_input_optimization.py`. 204 tests cover segment selection including reordered/empty segments, invalid index dtype, multipart/hole/sparse geometry, seed bytes/digests/seeds/gates, Unicode/escaped fields, absent eligibility, nonaliasing and all-family frozen digests. Existing family tests also cover multi-scene ragged collation, topology, relation masks and source removal.
- Real current SSD data: all 11 OFAT plus all 17 comparisons. Two scenes per role for training, validation query and gallery: **84 case/role comparisons PASS**.
- Exact projected sample/metadata, original IDs, compact maps, geometry/Fourier rows and batched tensors matched. Masks compared for epochs 1/9/200, both ranks and both views. Fixed-state CPU outputs matched exactly and were finite, including DS through the accepted DS raster reader.
- Main disposable epoch-1 rank-0 trace compared after execution against the first 76 rows stored in the interrupted checkpoint: **entire trace exactly equal**, including loss, gradient norm, LR, batch digest and queue counts/pointers. Maximum loss difference 0.0. This is read-only reference comparison, not checkpoint resume or warm-start.

These are deterministic regression proofs over the stated fixtures, not a claim that all possible inputs have been exhaustively enumerated.

## CPU Benchmark

Same main epoch 9, ranks 0/1, batch IDs 0/1, per-rank 16 scenes with two views, one CPU thread, verified SSD root. Three repetitions, reversed old/new order in the middle repetition, geometry LRU cleared before each case. OS page cache was not dropped. 24 measurements, exact input and mask digests in every paired case. A CPU test-suite process was also running on the shared host during this benchmark; these are not isolated-machine timings. The independent DDP gates were run without that suite.

Mean seconds per rank input batch:

| Stage | Before | After | Speedup |
|---|---:|---:|---:|
| Family projection | 0.9833 | 0.0635 | 15.49x |
| Masking | 0.3964 | 0.0756 | 5.24x |
| Prepared read/check | 0.0573 | 0.0531 | 1.08x |
| Geometry read/check | 0.0587 | 0.0588 | 1.00x |
| Total assembly, excluding masking | 1.2760 | 0.3508 | 3.64x |
| Total CPU input, including masking | 1.6724 | 0.4264 | 3.92x |

Assembly includes additional collation/attachment/allocation costs, so named substages do not exhaust it. Saved CPU time is approximately 1.246 seconds per sampled rank batch, about 66% of the previous 1.9-second formal update. Translating that directly to epoch savings would ignore rank imbalance and GPU work; the DDP measurement below is the stronger execution evidence.

Same rank0/batch2 cProfile: projection 0.657 -> 0.083 s; masking 0.450 -> 0.068 s; total 1.231 -> 0.238 s. The second profile had a warmer geometry LRU, so it is diagnostic and not the primary total-speedup estimate. The counterbalanced table above equalizes that LRU state.

## Disposable DDP Qualification

Canonical GPU pair/device locks held across the canonical 30-second NCCL preflight and the disposable worker. GPUs 0/1, NCCL world size 2, 16/rank, CUDA_VISIBLE_DEVICES=0,1, NCCL_P2P_DISABLE=1, NCCL_IB_DISABLE=1. Both preflights passed init, rank/device, ALLREDUCE, ALLGATHER, DDP construction and clean destruction. No find_unused_parameters workaround.

Fresh models/optimizer/EMA/queue; exactly 76 production training_update calls and full production validation (2,000 queries / 1,000 gallery). No controller/ledger/checkpoint publication API. Main uses current main defaults. B2 uses legal main-default hyperparameters (d128), not an assumed new winner or historical winner checkpoint.

| Metric | Main | B2 |
|---|---:|---:|
| Epoch seconds, rank0 | 42.105 | 26.873 |
| Median update seconds | 0.540 | 0.343 |
| p95 update seconds | 0.691 | 0.490 |
| Scene throughput / second | 57.76 | 90.50 |
| Full validation seconds | 11.665 | 9.390 |
| Training loss, rank0 | 6.02473 | 5.91040 |
| Optimizer/scheduler updates | 76 | 76 |
| EMA updates | 76 | 76 |
| Queue valid/enqueued/pointer | 4864/4864/4864 | 4864/4864/4864 |
| Peak allocated VRAM rank0, bytes | 6012821504 | 3248591360 |
| Peak reserved VRAM rank0, bytes | 17213423616 | 8961130496 |
| Peak RSS rank0, bytes | 7717097472 | 7375843328 |

Online/target parameters and losses finite. Production gradient assertions and relation/geometry contracts remained enabled.

Main reference: recent formal epochs 7-9 146.7 s, epoch9 148.5 s, boundary10 training loop 144.5 s and validation 46.5 s. New disposable main is approximately 3.43x faster than the 144.5 s reference (70.9% shorter); validation approximately 3.99x faster. These are different epochs and allocator/cache states; no long-run ETA or sustained formal guarantee is inferred. The old 53-second pre-adapter benchmark is not used as the baseline.

Two-second resource samples, approximate training windows inferred from completion and measured phase durations: main GPU mean 44.9%/35.1%, active rank CPU approximately 100%; B2 GPU 15.5%/17.5%, active rank CPU approximately 98%. Window edges have sampling uncertainty; these are coarse utilization diagnostics, not kernel-level attribution. Full resource samples retained. No GPU processes remained after qualification; locks released.

## Prefetch Decision

Evaluated but NOT implemented. A future candidate is one next-input slot per rank, immutable scene/view/batch descriptors, pure stateless seed derivation, FIFO exception delivery before the corresponding optimizer step, a hard memory bound including both current and next ragged tensors, and cancellation/join on controller interruption. It would need exact synchronous-vs-prefetch trace equivalence and failure/cancellation tests, especially around geometry LRU ownership.

The measured synchronous optimization already reduces main epoch time materially. Adding scheduling, shared-cache concurrency and cancellation semantics now would broaden the repair without a measured need. No thread, worker, OMP/MKL or rank-count change was made.

## Provenance And Next Boundary

Old runtime: `a2bbddf036e4a9a023caa32cbf7a10927d7b35450318121c47f9b3a6c2ecb06a`.

New runtime: `d244e40a910e559cf2ac333609e3730bf19b368c7ea71ee31cb123eb138d0ac5`.

Existing whole-file runtime registration naturally includes the changed module; no source exclusion or component migration was added. S08 remains `s08plan_7cd58ffb65db3d43fd3fa234`. Canonical cache/acceptance and SSD physical placement remain unchanged.

Read-only training currentness marks runtime sources/implementation, authorities and downstream lifecycles/results outdated. Prepared-cache sources/acceptance are NOT in that outdated set. Main research outdated set remains empty. Training DAG remains 29 targets, 80 target-to-target edges, acyclic (tar_network additionally includes global/function edges: 134 total). Definitions/dependencies and generated network structure did not change, so network HTML regeneration was not required.

Policy **B**: runtime changed; interrupted epoch-10 checkpoint is historical/ineligible under the new runtime. Its original interrupted ledger remains untouched and resumable only under its original exact contract, not the new code. No selective legacy reuse.

Next separately authorized formal boundary: **fresh main epoch 0 -> all 11 fresh OFAT -> new winner -> FM,A1,A2,A3,A4,A5,SSV,DS,B1-B9 -> campaign acceptance**. No formal restart in this task.

## Validation And Evidence

- `git diff --check`: PASS.
- `python -m compileall -q python/training_family_inputs.py tests/python/test_training_input_optimization.py`: PASS.
- New fixture JSON parsed by regression tests; production YAML/schema files unchanged.
- Existing family projection/encoder tests: 105 PASS.
- Optimization tests: 204 PASS.
- Final `python -m pytest tests/python -q`: **739 passed, 1 skipped**, 132.58 s. Skip is the opt-in tiny-replica copy test (`FUSE_TEST_REAL_CACHE_REPLICA` unset); current real SSD readers were independently exercised by 84 CPU comparisons and both DDP qualifications.
- `Rscript tests/testthat.R`: PASS, exit 0.
- `_targets.R` / `_targets_training.R` manifest, validation and DAG checks: PASS; read-only main currentness empty. No tar_make.
- Protected after-check: 2,811 SHA-256 matches, zero mutations.

Evidence workspace: `/tmp/s09_input_opt_20260914/` containing frozen baseline sources, protected.json, real_equivalence.json, timings.json, counterbalanced_cpu.json, old/new profiles, main/B2 rank results and traces, preflight results, stdout/stderr/exit, resource samples, runtime.json and preservation_after.json. Disposable scripts are `/tmp/s09_input_opt_real.py`, `/tmp/s09_opt_cpu_benchmark.py`, `/tmp/s09_opt_ddp_worker.py`, `/tmp/s09_opt_ddp_launch.py`.

## Git

Implementation commit: `85d3eee4189f8fd3bb2087a371a9e225801d7ae4` (`perf(s09): optimize family input assembly`).

Implementation push to origin/reduced: PASS. Remote refs verified independently with git ls-remote; exact same implementation HEAD. Clean tracked worktree and ahead/behind 0/0 after implementation push. Post-commit fresh-process research currentness: 0 outdated.

This report is recorded in a following documentation-only commit; its commit ID and final push verification are reported to the user after publication. Runtime SHA is unchanged by Git publication. No training restart.
