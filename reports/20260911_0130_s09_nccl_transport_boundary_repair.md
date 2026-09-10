# S09 NCCL transport boundary repair

## Scope

- Time: 2026-09-11 01:01-01:30 KST
- Input Fuse HEAD: `6c76084ca4816b4285dc6ff64cd90839cfd55fb4`
- Branch: `reduced`
- Purpose: repair the formal S09 GPU/NCCL execution boundary after the first DDP parameter-shape `ALLGATHER` timed out for 600 seconds.
- Prompt summary: enforce the host-required NCCL transport environment, add a locked fail-closed two-rank transport preflight, preserve the failed run and prepared cache, validate without formal training, then commit and push.

## Failure and root cause

The failed run was `p9runv2_dd960ce922ab1fc50a88513e` under authority `s09auth_05cf31d6b21ad3fd2986da9f`. Both ranks reached `DistributedDataParallel` construction, then timed out at NCCL `ALLGATHER` sequence 1 before epoch/update `0/0`. There was no checkpoint or scientific result.

The formal controller acquired GPU locks and set `CUDA_VISIBLE_DEVICES=0,1`, but it neither set nor validated `NCCL_P2P_DISABLE=1` and `NCCL_IB_DISABLE=1`. The previously successful disposable path had both settings. The historical ledger and logs were not modified or reopened.

## Repair

- `config/training_controller.yml` is the single transport configuration source: devices `0,1`, world size 2, NCCL backend, P2P disabled, IB disabled, and a 30-second preflight timeout.
- `python/training_transport.py` owns environment validation, pair and per-device locks, workload exclusion, preflight execution, and the worker-launch gate.
- Formal order is now: acquire locks, construct and validate environment, reject conflicting GPU work, run preflight, launch worker only after PASS, release locks on every exit path.
- The preflight uses the same Python executable and `python -m torch.distributed.run --standalone --nproc_per_node=2` construction as the science worker.
- It verifies process-group initialization, rank/world/device agreement, NCCL ALLREDUCE, NCCL ALLGATHER, `DistributedDataParallel(...)` parameter synchronization, and clean group destruction.
- Per-run append-only `*.nccl_preflight.jsonl` records authority/run identity, selected GPUs, non-secret transport values, stages, elapsed time, and status. `NCCL_PREFLIGHT` is also recorded in normal progress state.
- A disposable `transport-preflight` controller action is restricted to a system temporary log root and never creates a formal ledger or launches a science worker.

## Disposable GPU result

The exact repaired controller boundary ran on GPUs 0 and 1 under the final disposable authority/run:

- environment: `CUDA_VISIBLE_DEVICES=0,1`, `NCCL_P2P_DISABLE=1`, `NCCL_IB_DISABLE=1`
- world/backend: `2 / nccl`
- init/rank-device/ALLREDUCE/ALLGATHER/DDP-construction/destroy: PASS
- transport elapsed: 7.99 seconds
- controller wall time: 11.84 seconds
- peak process-tree RSS reported by `/usr/bin/time -v`: 1,067,512 KiB
- disposable log: `/tmp/s09-nccl-final-preflight-uuIQ7l/`
- formal training, optimizer updates, and formal checkpoints: none

A full disposable epoch was not repeated. The exact repaired preflight now covers the latest failing DDP-construction collective, while the immediately preceding accepted evidence already covers 76 updates and validation under the same required transport variables. Avoiding another full data-path run kept this task limited to the transport boundary.

## Provenance and authority impact

- Previous runtime implementation SHA-256: `b433a0236f58226330333bf0b34353a686c911dada074a78183389c35fe81876`
- Repaired runtime implementation SHA-256: `0479d8ae41fb22a4c3c2f82360fa2d12cd0f59fd73d8a50ef0868d2eff1cf66d`
- Transport config, environment builder, controller, preflight, worker entrypoint, and progress implementation are registered in one canonical runtime digest.
- Disposable OFAT materialization: 11/11 unique, all bound to the repaired runtime SHA.
- New main authority: `s09auth_6446cd16ebc90b8d29a07d8a`
- New main run: `p9runv2_1a7e1c84f3ee97d3d2dda4c3`
- Disposable comparison materialization from a synthetic winner: 17/17 unique, all bound to the repaired runtime SHA.
- S08 remains `s08plan_7cd58ffb65db3d43fd3fa234` with content SHA `7cd58ffb65db3d43fd3fa234fb5c6b7489640ea7e1e2a1bda76082f3ac3e81e3`; main-store outdated is empty.

## Cache preservation and next currentness

Read-only full cache validation passed in 79.45 seconds:

- cache: `s09cache_dc4e9e271e40ffe8ae17967c`
- acceptance: `s09ca_e2a1882eb206e1b5c930ddd5`
- entries: 80,472
- manifest SHA-256: `269f05b255cfaa0df8b21b17914d3475c65f4f3e2d672fd2669b927a00699370`
- payload regeneration: NO

The next training invocation will reevaluate the broad source and cache-acceptance targets, but `prepare_training_cache.py` deterministically finds the existing destination, validates all payload hashes, and returns the same acceptance. Runtime provenance, OFAT authorities, fresh run branches, winner, comparisons, and campaign acceptance are pending. No target-store metadata was manually edited.

## Validation

- Python compile: PASS
- focused transport/progress/campaign/controller/replay tests: 68 PASS
- full Python pytest: 456 PASS
- focused training-target R tests: PASS
- full R testthat: PASS
- YAML/config parse: PASS
- `_targets.R`: manifest 61 targets / 212 edges, acyclic, validate PASS
- `_targets_training.R`: manifest 29 targets / 78 edges, acyclic, validate PASS
- `git diff --check`: PASS
- dependency network HTML: unchanged because no target declaration, dependency, pattern, resource, format, or target output contract changed
- formal S09 training executed: NO
- GPU/DDP science worker executed: NO
- formal checkpoint created: NO
- prepared cache rebuilt: NO
- target-store metadata manually edited: NO

## Repository publication

- Implementation commit: `8dca4e2a8420e4fcc9226a7fabe93218697d3056`
- Push: PASS to `origin/reduced`

## Verdict

`PASS_S09_NCCL_TRANSPORT_BOUNDARY_REPAIRED`

The next separately authorized action is `Rscript scripts/run_training_targets.R campaign`. That run must validate/reuse the existing cache, materialize authorities bound to runtime SHA `0479d8ae...f66d`, create the fresh main run, and pass the NCCL preflight before the science worker starts.
