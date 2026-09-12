# S09 Nonpublishing All-Model Smoke Runner

Created: 2026-09-12 11:59 Asia/Seoul.
Repository: /members/dhnyu/fuse; branch: reduced.
Input HEAD: 632e9eb6dab64f8636215167f1e7d420336e1ef7.
Implementation HEAD: 52ca02dc05c4dc22eac74e874c41b8e8f7f2fe96.
This report is recorded in a subsequent report-only commit.

## Verdict

**PASS_S09_ALL_MODEL_SMOKE_RUNNER_READY**

The missing checkpoint-free qualification entrypoint is implemented and qualified on main, DS and B2 only. This is NOT PASS_S09_ALL_MODEL_SMOKE: the complete 28-case matrix has not been executed. GLOBAL_RETRAIN_REQUIRED remains binding. No historical result/checkpoint/winner is a smoke input or a future campaign reuse candidate.

Prompt summary: implement a tracked, isolated one-step two-GPU smoke operator using production science, deterministic real query/gallery validation, locked canonical transport, strict output/process safety, focused qualification and regression tests; commit/push without formal training or the full matrix.

Authoritative evidence read:
- reports/20260912_1126_s09_family_adapter_production_repair.md
- reports/20260912_1135_s09_all_model_ddp_smoke.md

The current dissertation experimental setup and training-time masking/online-target/EMA/queue descriptions were inspected. This tooling does not change scientific definitions or preparation.

## Preconditions

PASS: exact requested HEAD, reduced branch, clean worktree, live origin/reduced equality, ahead/behind 0/0. No active formal controller, torchrun worker or GPU compute workload; all canonical GPU locks available.

Main research-store tar_outdated was empty. S08 serialized SHA matched 74ae70958b96dd663d300c6f7441a0653b1a7c5066d6e1bfe9b4b459d7781789. Current plan remains s08plan_7cd58ffb65db3d43fd3fa234.

Accepted preparation remains s09cache_dc4e9e271e40ffe8ae17967c / s09ca_e2a1882eb206e1b5c930ddd5. Acceptance/manifest identity and current lineage checks pass; all 80,472 prepared payloads exist with registered sizes. No full 296GiB payload rehash was needed. Actual qualification reads the immutable current prepared data; DS additionally verifies accepted DS bindings and selected raster payload hashes through the production reader.

## Entrypoint And Inventory

New tracked files:
- scripts/s09_smoke_matrix.py: explicit smoke-only CLI.
- python/s09_smoke.py: input resolution, isolated process orchestration, production-science calls, evidence and validation.
- tests/python/test_s09_smoke.py: CPU/mocked contracts and process cleanup tests.

Supported commands:

```bash
python scripts/s09_smoke_matrix.py --mode one-step --case main
python scripts/s09_smoke_matrix.py --mode one-step --case DS
python scripts/s09_smoke_matrix.py --mode one-step --case B2
# Next separately authorized task only; NOT executed here:
python scripts/s09_smoke_matrix.py --mode one-step --all
```

An explicit selection is mandatory. Optional --output must be a new directory below logs/s09/smoke/. Default output is a fresh timestamp/microsecond directory. Existing directories are not resumed or overwritten. A failed case stops the matrix; a separately selected case uses fresh state and fresh evidence. There is no automatic retry or checkpoint resume.

Exact OFAT order:

1. main
2. ofat_d_64
3. ofat_d_256
4. ofat_K_aug_4
5. ofat_K_aug_16
6. ofat_augmentation_intensity_0.5
7. ofat_augmentation_intensity_2.0
8. ofat_ema_momentum_0.99
9. ofat_peak_learning_rate_0.002
10. ofat_peak_learning_rate_0.003
11. ofat_peak_learning_rate_0.005

Exact comparison order:

1. FM
2. A1
3. A2
4. A3
5. A4
6. A5
7. SSV
8. DS
9. B1
10. B2
11. B3
12. B4
13. B5
14. B6
15. B7
16. B8
17. B9

Comparison smoke explicitly uses SMOKE_ONLY_COMPARISON_HYPERPARAMETERS: current S08 main d=d_c=128, K_aug=8, intensity=1.0, EMA=.999, peak LR=.001. No winner is assumed or created. The selected row is adapted to the existing worker-value interface without a formal authority.

## Safety Architecture

Input resolution reads only the configured current S08 plan/controller contract, current lineage, content-addressed cache and canonical runtime provenance. It validates exact S08 bytes, cache parent/membership identity, acceptance, DS production binding and payload inventory. No historical S09 authority, winner, ledger or checkpoint is required.

The launcher holds the canonical pair/GPU0/GPU1 locks across both preflight and science. Same Python executable/environment, devices 0/1, NCCL world2, CUDA_VISIBLE_DEVICES=0,1, NCCL_P2P_DISABLE=1 and NCCL_IB_DISABLE=1. Existing 30-second transport preflight checks initialization, device/rank agreement, ALLREDUCE, ALLGATHER, DDP construction and destruction. Its supervisor bound is 40 seconds including launch allowance.

Each case launches a fresh torchrun session with two ranks. The science-worker timeout is 240 seconds; validation has an explicit 60-second deadline, with the parent case timeout as a second bound if a GPU call cannot promptly handle a signal. Process groups are terminated on failure, timeout or interruption, including surviving peers when the launcher has exited. Locks are held through cleanup and released on every path. FUSE_TRAINING_* environment bindings are removed before smoke execution.

Output restriction rejects paths outside logs/s09/smoke, traversal, symlinks, existing files and production artifact names (checkpoint, authority, acceptance, ledger, winner, campaign_status, current_status). There are no controller/publication calls or checkpoint serialization calls in the smoke operator. It does not call run_worker, bounded_validation, _stage_checkpoint, restore_checkpoint or targets.

The internal worker mode exists only for the guarded launch. It checks rank/world/environment, current runtime SHA and exact smoke-tool whole-file hashes before science. The runtime registry is unchanged; smoke tooling has separate evidence hashes.

## One-Step And Validation Contract

Fresh online/target, AdamW, ExactScheduler and empty queue are constructed through production create_state. Smoke-only root seed 20260912 is namespaced by case/order/config hash; rank-derived seeds are recorded. Production configure_process and rank-derived CUDA RNG behavior are retained. No formal run seed or checkpoint is imported.

Exactly one production training_update is invoked at epoch1/batch0. This reuses the production two-view sampler, family projection/masking, Fourier/topology/relations, DS/scene-center readers, online/target forward, symmetric contrastive objective, gradient clipping, optimizer, scheduler, EMA and enqueue implementation. Online-only masking is unchanged.

Observation wrappers count optimizer, scheduler and EMA calls without replacing their science. Each must equal one. Scheduler completed_updates must equal one. Queue must change from empty to valid_count=64, enqueue_count=64, pointer=64 (two views of global batch32). Online/target parameters and queue must be finite; target parameters remain no-grad. Expected active online parameters must all have finite gradients. DDP uses find_unused_parameters=False with unchanged bucket/static-graph options. Rank active-parameter inventories must agree.

Family module audits reject source-specific semantic modules for removed B/R/P, inactive geometry/environment/relations/raster modules, and DS entity modules. Actual online forward hooks record both views' entity counts, geometry rows, edges, active modalities, local mask counts and environmental/raster carriers. They do not assemble a separate diagnostic training batch.

Validation uses the first 32 lexically ordered current validation scene IDs, query view0 and corresponding gallery. The same production assemble_family_batch/family_encoder_batch and DS reader are used; role batches stay separate in groups of eight. Each rank executes this same small set independently. These are 32 unique queries/32 galleries, not 64 unique national samples. Production model forward, normalization and retrieval diagnostics exercise the real similarity path. Embeddings must have [32,d] shape and all vectors/similarities be finite. The result is labelled scientific_metric=false; it is not formal validation or performance evidence.

## Evidence Layout

Each new output has matrix.json and append-only matrix.tsv in exact case order. Per-case evidence includes:
- inputs.json and case.json: smoke-only configuration, seed, current input/runtime/tooling provenance, no authority.
- preflight.jsonl: start and PASS/FAIL transport evidence.
- stdout.log/stderr.log plus torchrun per-rank redirected stdout/stderr under ranks/.
- rank0.json/rank1.json: actual views, gradients, step/queue state, validation, dimensions, loss, elapsed time, allocated/reserved VRAM and RSS, or failure stage/traceback.
- case_result.json: aggregate PASS only after both rank result contracts validate; failure retains partial output.

All JSON evidence rejects nonfinite serialized numbers and is created exclusively, never overwriting old smoke evidence. Formal progress files are untouched.

## Final Qualification Results

Final tooling hashes:
- python/s09_smoke.py: ba394ca23c86fa34d796b5e7db412d54e6b92be5f0b001f98e0efc2eef5ab5f5
- scripts/s09_smoke_matrix.py: c4928e44928115051001ef757e0cd62d309de43d8a51be93188bb795ae20d03c

All three final qualification matrices bind these exact source bytes. Python 3.14.0, PyTorch 2.12.0+cu130, CUDA build 13.0; interpreter /members/dhnyu/.conda/envs/rgeo/bin/python.

| Case | Preflight | Step | Rank0 loss | Rank1 loss | Optimizer/scheduler/EMA | Queue | Validation | Case seconds | Verdict |
|---|---|---|---:|---:|---|---|---|---:|---|
| main | PASS | PASS | 3.6231889725 | 3.6726450920 | 1/1/1 each rank | 0 to 64 | 32/32 PASS | 26.258 | PASS |
| DS | PASS | PASS | 3.5733191967 | 3.4549360275 | 1/1/1 each rank | 0 to 64 | 32/32 PASS | 63.644 | PASS |
| B2 | PASS | PASS | 2.9742138386 | 3.2093806267 | 1/1/1 each rank | 0 to 64 | 32/32 PASS | 24.311 | PASS |

Final case time sums to 114.213 seconds, excluding per-invocation current input/cache inventory validation. These are not formal epoch timings or campaign ETA measurements.

| Case | Peak allocated VRAM MiB | Peak reserved VRAM MiB | Peak RSS MiB |
|---|---:|---:|---:|
| main | 5476.63 | 5660 | 2938.61 |
| DS | 152.33 | 190 | 2792.42 |
| B2 | 1248.65 | 1318 | 2612.83 |

Main: both ranks have 232 active parameter tensors with finite gradients; all full-family inputs present. DS: 26 active parameter tensors; no entity modalities, masks, geometry or edges; dedicated all-source raster in both views. B2: all four rank/view entity compositions have P=0: 2667/509/0, 2699/508/0, 3168/588/0, 3176/592/0. Geometry row counts are respectively 3176, 3207, 3756, 3768, matching retained B+R counts. No environment/scene raster is present. Production relation/geometry entry checks and forward/backward succeed.

Final evidence roots:
- logs/s09/smoke/20260912_final_main/
- logs/s09/smoke/20260912_final_DS/
- logs/s09/smoke/20260912_final_B2/

Earlier main and DS qualification passes are preserved under 20260912_qualification_main and 20260912_qualification_DS. They preceded additional tool-side module/result-schema hardening; final passes above use identical final committed tool source bytes. No cases other than main, DS and B2 were executed. --all was never invoked.

## Regression And Read-Only Validation

PASS:
- python -m compileall -q python scripts tests/python
- python -m pytest -q tests/python/test_s09_smoke.py: 56 passed.
- python -m pytest -q: 626 passed in 87.66 seconds.
- Rscript tests/testthat.R: full suite PASS.
- git diff --cached --check and git diff --check.
- Main manifest/validate/DAG: 61 targets, 212 edges, acyclic.
- Training manifest/validate/DAG: 29 targets, 80 edges, acyclic.
- Main tar_outdated empty after implementation.
- GPU compute query empty, no lingering smoke/formal/DDP process; canonical locks reacquired/released successfully.

Tests cover exact inventory/order, comparison defaults, deterministic seeds, one-step counters, gradients, real validation assembly/DS routing with CPU fixtures, output escape/production-name/symlink/overwrite rejection, preflight failure blocking science, exact environment and lock scope, child-peer/timeout/SIGTERM cleanup, retained failure evidence, result schema and forbidden family modules. No GPU execution occurs in unit tests.

During test development, one process-cleanup assertion sampled /proc immediately after SIGKILL and saw a transient runnable state. The regression now requires actual disappearance/zombie state within a bounded two seconds rather than assuming synchronous kernel signal delivery. Final focused and full suites pass; genuine surviving peers still fail. An initial read-only manifest command used an unsupported store argument; corrected API invocation passed. Neither issue changed production science or target metadata.

No R/config files or target declarations changed. R parse/config parse for modified files is not applicable. Existing YAML/JSON inputs are parsed by actual qualification. Existing dependency network structure/HTML remains valid; no graph update was necessary.

## Provenance And Preservation

Production S09 runtime SHA remains exactly:
baf19aa078973c19e19ed55c8ea6ee2f733db9d9b94a33b0c8e03e74fc695c9a.

Smoke-only files are not registered in formal runtime provenance and are not formal execution dependencies. Therefore S08 scientific identity, production authority derivation and prepared-cache content identity are unchanged. No authority or winner was materialized, reinterpreted or migrated.

Before/after qualification and final regression checks: 2,274 protected historical files (including 18 selected checkpoint payloads) match their existing baseline SHA values. Training targets store inventory/hashes: all 10 files unchanged. S08, old OFAT results/winner, comparison ledgers/checkpoints, failed B2 evidence, prepared manifests/acceptance and formal logs are preserved. Evidence: logs/s09/smoke/20260912_runner_qualification/preservation_*.

Formal training = NO.
28-case matrix = NOT EXECUTED.
Disposable GPU qualification = main/DS/B2 only.
Production authority/checkpoint/result/finalization/acceptance publication = NO.
Target-store mutation = NO.
Cache rebuild = NO.
S10/evaluation/downstream = NO.

## Git And Next Action

Implementation commit 52ca02dc05c4dc22eac74e874c41b8e8f7f2fe96 pushed to origin/reduced: PASS; ahead/behind 0/0 verified. This report is a separate documentation commit, followed by final remote equality verification reported to the user. Only explicit implementation/test/report files are staged; logs/data/checkpoints/stores are excluded.

Next separately authorized task: execute the exact 28-case matrix using the new operator. Do not treat three qualification cases as 28/28 readiness.

The smoke execution and evidence order is FM,A1-A5,SSV,DS,B1-B9. Formal campaign routing was intentionally not modified by this smoke-tool task: its current comparison registry still has B-series before SSV/DS. The requested future formal execution/presentation order needs a separately validated operational change before that campaign; S08 scientific definitions must not be rewritten to obtain display order.

Only after all 28 smoke cases pass may a separately authorized fresh campaign begin: fresh OFAT main epoch0, all11 new OFAT, new winner, all17 fresh comparisons. No historical checkpoint/result reuse. No formal training started.
