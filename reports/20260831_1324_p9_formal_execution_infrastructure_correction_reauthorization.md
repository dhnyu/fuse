# P9 formal execution infrastructure correction and reauthorization

## Verdict

`P9_FORMAL_EXECUTION_INFRASTRUCTURE_CORRECTION_AND_REAUTHORIZATION_PASS_PUSHED`

This report was prepared before the publication commit and push. The final publication commit and remote readback are appended by that commit's recorded Git history and the final task response. No formal attempt was started in this work unit.

## Purpose and scope

- Execution time: 2026-08-31 12:57-13:24 KST.
- Starting Fuse commit: `bd246a53a5e366699eb770610eef94cdf4131885` on `reduced`.
- Dissertation commit: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a` on `reduced`.
- Prompt scope: correct the missing formal P9 execution chain, publish an executable authority and an unstarted `cfg_main` reservation, and perform no formal training.
- Production cache and cache acceptance were read-only parents: `p9cache_f8b16c49f2c63216609b013b` and `p9ca_99725ef4c56f8b11b4d71935`.

## Blocked-attempt findings

The earlier launch correctly stopped before execution. The old authority `p9a_c16721ffbce259df3f723cdd` bound a different execution commit, the old reservation `p9res_c0f73b80e4f90ed3cc8a3346` omitted authority/execution identity from its duplicate key, and the target graph ended at reservation. The only runnable code was a bounded, explicitly non-formal 40-update pilot. Readback confirmed the old reservation remained `AUTHORIZED_NOT_STARTED`, with optimizer updates, formal validation, checkpoints, evaluation consumption, and run artifacts all zero.

## Runner architecture

The dedicated `scripts/p9_formal_training.py` runner is separate from the bounded pilot. It reuses the accepted P7/P9 data, model-family, loss, optimizer, EMA, queue, scheduler, cache-reader, and DDP primitives, but formal orchestration, state transition, validation selection, checkpoint publication, and terminal acceptance are explicit P9 contracts. Configuration is loaded from the accepted P8 matrix and authority; scientific CLI overrides are rejected.

The formal runner supports all registered P9 families, two-rank DDP, production cache indexes, 76 updates per epoch, the authority's full epoch/update budget, deterministic validation, early stopping, atomic full-state checkpoints, exact resume, best-versus-terminal checkpoint distinction, and coherent controller-owned rank failure handling. The bounded runner remains `formal_attempt: false`.

## Execution-commit solution

- Initial implementation commit: `9288c9ed8c4b38713a38d46fb68049ae7c290e5c`.
- Corrected production-plan reader commit: `c40c1adb302698195d111f48376644fcbef08e31` (authoritative implementation commit A).
- Scientific implementation parent: `eb90f6f667d1717684f47ddef30043992b70e788`.
- Authorized runtime file set: 24 files.
- Runtime-tree digest: `d8379196a400bc590575c00b6953d046ae50dc3878cd37bbeb98aa1f6d7dff55`.

The authority binds commit A and the canonical path/size/SHA-256 manifest for every runtime file. A future launch may use commit A or an allowlisted descendant only when all 24 runtime bytes reproduce the same digest. Descendant changes are restricted to publication reports and bindings. Changes to Python, R orchestration, target commands, runtime schemas/configuration, model, cache reader, optimizer, scheduler, validation, checkpoint, or locking code are rejected. The actual launch commit is additionally bound into the future run identity and duplicate ledger.

## New identities

- Corrected formal authority: `p9a_b295be97717efbd2305dd5a6`.
- Corrected `cfg_main` reservation: `p9res_51ed9e4731c21bda28d4d7a2`.
- Preassigned attempt: `p9attempt_f153ff8e7831effbf2f2d68a`.
- Supersession record: `p9sup_7a1836aaf4be3a298f77e14e`.
- Reservation state: `AUTHORIZED_NOT_STARTED`.
- Duplicate key: `b0660330d4809a9c4cc0d08b813cbcb46eee2181d69b446342ab72bd2fa77043`.

The duplicate key binds configuration identity, seed identity, P8 acceptance, P7 runtime acceptance, P9 readiness, production-cache acceptance, corrected formal authority, authorized runtime-tree identity, scientific implementation commit, and world size. The launch record must also bind the actual launch commit, verified runtime digest, run identity, and reservation.

## Supersession

The immutable supersession record classifies `p9a_c16721ffbce259df3f723cdd` and `p9res_c0f73b80e4f90ed3cc8a3346` as preserved, unexecuted, superseded, and ineligible for formal execution. It records optimizer updates 0, formal validation runs 0, checkpoints 0, and evaluation consumption 0. A pre-publication validation identity (`p9a_6a4cbc93682d3110e3cd93b6`, `p9res_b6a28fb1da823ce897fe6e34`) was also preserved as `UNEXECUTED_SUPERSEDED_BEFORE_ACCEPTANCE` after a cache-plan reader defect was found and corrected before acceptance. Neither identity was executed.

## State, lock, checkpoint, and validation contracts

Allowed states are `AUTHORIZED_NOT_STARTED`, `STARTING`, `RUNNING`, `INTERRUPTED_RESUMABLE`, `FAILED_NONRESUMABLE`, `COMPLETED_PENDING_VALIDATION`, `ACCEPTED`, and `REJECTED`; invalid transitions fail closed. A single controller owns kernel `flock` plus a durable validated owner/heartbeat record containing process, host, lineage, run, reservation, authority, and execution identity. Duplicate non-resume acquisition and automatic stale-lock deletion are rejected.

Checkpoints use staging plus atomic rename and bind online/EMA model, optimizer, scheduler, scaler applicability, epoch/update and within-epoch cursor, sampler and all RNG states, queue payload/pointers, early-stopping/best state, validation trace, complete lineage, cache/runtime identity, and world-size contract. Corruption or any incompatible identity fails closed; update-zero restart under the same interrupted identity is prohibited.

Validation requires exactly 800 queries and 400 galleries with no missing or duplicate identities and no held-out evaluation access. Lower retrieval loss is primary; when the absolute difference is below `1e-4`, larger source-separation margin wins, then earlier epoch. Validation occurs every five epochs and patience is four validation events. MRR/HIT are never selector inputs.

## Target DAG

The target graph now contains the explicit chain:

`p9_corrected_formal_training_authority` -> `p9_corrected_cfg_main_attempt_reservation` -> `p9_cfg_main_formal_run` -> `p9_cfg_main_validation_trace` -> `p9_cfg_main_checkpoint_candidates` -> `p9_cfg_main_selected_checkpoint` -> `p9_cfg_main_terminal_execution` -> `p9_cfg_main_attempt_acceptance`.

P7 runtime, P8 plan, P9 readiness, cache acceptance, authority, and reservation are direct target dependencies. The formal run requires the exact `FUSE_P9_FORMAL_RESERVATION_ID`; an unrestricted `tar_make()` without that explicit token fails before a formal runner starts. The regenerated network has 190 targets, 577 rendered dependency edges, and one weak component.

## Validation results

- Focused Python formal-execution tests: 9 passed.
- Full Python suite: 84 passed.
- Full R/testthat suite: passed with exactly the three documented legacy skips.
- Bounded synthetic integration: 8 optimizer updates total across direct and interrupted/resumed fixture trajectories; production scenes and formal identities were not used; exact state, trace, RNG, queue, optimizer, EMA, scheduler, and validation parity passed.
- R parsing and `targets::tar_validate()`: passed.
- Target manifest/network validation: 190 targets; formal run and downstream metadata absent.
- Python AST: 82 files passed.
- YAML/JSON parsing: 54 YAML and 102 JSON files passed.
- New artifact schema and canonical readback: 3/3 passed.
- Dissertation read-only Typst compile: passed; only pre-existing unavailable Korean font warnings were emitted.
- Target-network repeat render: byte-identical SHA-256 `8c769f94ec289c0c25f2ecb373948b3ba3405f42e9874c51ec3b92ba7c24ea91`.
- Corrected publication targets repeated with `shortcut=TRUE`: 6 skipped, builds 0, rewrites 0.
- `git diff --check`: passed.

## Immutability and prohibited execution

Before/after evidence is stored under `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_formal_execution_correction_20260831_125743/`.

- Pre-existing model/P1-P8 files verified: 2,420/2,420 SHA-256 exact.
- Pre-existing target-store objects verified: 1,266/1,266 SHA-256 exact.
- Production-cache manifest files: 3/3 SHA-256 exact.
- Production-cache payload inventory: 314,695/314,695 path/size/mtime records exact.
- Production-cache mutation: 0.
- Existing checkpoint mutation: 0.
- Formal `cfg_main` updates: 0.
- Accepted-data optimizer updates: 0.
- Formal validation queries: 0.
- Held-out evaluation queries: 0.
- Formal checkpoints: 0.
- Formal attempt starts: 0.
- P9-B, selected-FM, P10/P11, maintenance executions: 0.
- GPU processes and active formal locks after validation: 0.

Expected new external files are limited to immutable corrected authorization/supersession artifacts and selected target metadata. Cache payloads, checkpoints, logs, locks, target-store objects, and fixture artifacts are not tracked by Git.

## Changed files

Implementation commit A adds the formal execution Python modules and scripts, R/targets orchestration, eight schemas, blueprint contract, phase mapping, and focused Python/R tests. The publication commit adds `config/p9_formal_reauthorization.yml`, the bounded integration test extension, regenerated target-network HTML, and this report.

## Next task

The next separately authorized work unit is the formal `cfg_main` execution using reservation `p9res_51ed9e4731c21bda28d4d7a2`. It must first verify a clean launch commit with runtime digest `d8379196a400bc590575c00b6953d046ae50dc3878cd37bbeb98aa1f6d7dff55`, then execute only the allowlisted terminal target in a durable session with:

```bash
FUSE_P9_FORMAL_RESERVATION_ID=p9res_51ed9e4731c21bda28d4d7a2 \
Rscript -e 'targets::tar_make(names = p9_cfg_main_attempt_acceptance, shortcut = TRUE, store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-research")'
```

That command was not run in this work unit.
