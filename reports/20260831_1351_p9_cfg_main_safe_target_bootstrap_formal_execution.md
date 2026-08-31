# P9 cfg_main safe target bootstrap and formal execution

## Verdict

`P9_CFG_MAIN_SAFE_TARGET_BOOTSTRAP_BLOCKED`

The read-only dependency-closure gate failed. `shortcut = FALSE` was not executed, the formal runner did not start, and the reservation remains `AUTHORIZED_NOT_STARTED`.

## Scope and inputs

- Audit time: 2026-08-31 13:45-13:51 KST.
- Starting Fuse commit: `89bce7cc9ab71d188a4afc0722019b934d7ac438`.
- Dissertation commit: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`.
- Blocked invocation launch commit: `95be285cfd7eac1c5672b4e3c67f5fbb8bfa45aa`.
- Implementation commit: `c40c1adb302698195d111f48376644fcbef08e31`.
- Runtime digest: `d8379196a400bc590575c00b6953d046ae50dc3878cd37bbeb98aa1f6d7dff55`.
- Authority: `p9a_b295be97717efbd2305dd5a6`.
- Reservation: `p9res_51ed9e4731c21bda28d4d7a2`.
- Attempt: `p9attempt_f153ff8e7831effbf2f2d68a`.
- Target store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-research`.
- Machine-readable closure evidence: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_cfg_main_safe_bootstrap_20260831_134917/closure_audit.json`.

## Previous failure boundary

The prior report and independent metadata/process/artifact inspection agree that the previous invocation failed inside `targets` before `p9_cfg_main_formal_run` was scheduled. The corrected reservation still records:

- state `AUTHORIZED_NOT_STARTED`;
- `formal_attempt_started: false`;
- optimizer updates 0;
- formal validation runs 0;
- formal checkpoints 0;
- evaluation-query consumption 0.

There is no formal attempt output directory, run identity, active lock, controller, DDP rank, GPU process, or metadata record for any target from `p9_cfg_main_formal_run` through `p9_cfg_main_attempt_acceptance`. The event remains a failed invocation, not a started or interrupted scientific attempt. Exact resume is inapplicable.

## Repository and runtime preflight

- Fuse was `reduced`, clean, and synchronized with `origin/reduced` at 0/0.
- HEAD was exactly the expected blocked-report commit and descended from the authorized implementation commit.
- Dissertation was `reduced`, clean, and synchronized at 0/0.
- The formal validator accepted the authority, reservation, matrix row, production cache, categories, launch tree, and byte-identical descendant policy.
- All 24 runtime files reproduced the authorized digest.
- No formal controller, DDP rank, GPU training process, lock, attempt output, or duplicate attempt existed.
- The production cache remained complete and readable.
- Superseded authority `p9a_c16721ffbce259df3f723cdd` and reservation `p9res_c0f73b80e4f90ed3cc8a3346` remained preserved, unexecuted, and ineligible.

## Shortcut authority audit

`shortcut` does not occur in the immutable formal authority, reservation, duplicate key, runtime-file manifest, runtime digest, schemas, R target declarations, Python formal runner, or runtime configuration. It occurs only in operational report commands. Therefore `shortcut` is a `targets` traversal option, not part of the scientific or execution identity.

Using `shortcut = FALSE` for a first metadata materialization would not by itself create a new scientific attempt. However, it is admissible only if the actual target closure is bounded to current immutable parents plus the six intended formal targets. That closure gate failed.

## Dependency-closure method

The audit used public read-only `targets` APIs against the accepted store:

- `tar_manifest()` for current target declarations and commands;
- `tar_network()` for dependency-to-dependent edges;
- `tar_outdated()` for the current build set;
- `tar_meta()` for existing metadata records.

Starting at `p9_cfg_main_attempt_acceptance`, the audit repeatedly followed target-to-target upstream edges. It then joined Phase assignments from `tools/targets-network/target_phases.yml`, current/outdated status, metadata presence, command classification, and expected build behavior. No target command was executed.

## Closure result

- Transitive target closure: 100 targets.
- Target-to-target edges inside closure: 283.
- Pipeline-wide outdated targets: 148.
- Outdated targets inside selected closure: 71.
- Expected new formal targets: 6, all outdated and without metadata.
- Unexpected outdated/build candidates inside closure: 65.
- Closure verdict: FAIL.

Phase accounting:

| Phase | Closure targets | Outdated |
|---|---:|---:|
| P0 | 13 | 13 |
| P2 | 1 | 0 |
| P3 | 6 | 0 |
| P4 | 10 | 9 |
| P5 | 13 | 12 |
| P6 | 6 | 5 |
| P7 | 19 | 4 |
| P8 | 4 | 4 |
| P9 | 28 | 24 |

The six intended targets were correctly present:

1. `p9_cfg_main_formal_run`
2. `p9_cfg_main_validation_trace`
3. `p9_cfg_main_checkpoint_candidates`
4. `p9_cfg_main_selected_checkpoint`
5. `p9_cfg_main_terminal_execution`
6. `p9_cfg_main_attempt_acceptance`

But `shortcut = FALSE` would also schedule accepted or historical parents and heavy cache work. Critical examples include:

| Target | Current status | Metadata | Consequence |
|---|---|---:|---|
| `p7_cold_path_runtime_acceptance` | outdated | yes | accepted P7 runtime would rebuild |
| `hyperparameter_configuration_matrix` | outdated | yes | accepted P8 scientific matrix would rebuild |
| `p9_corrected_formal_training_authority` | outdated | yes | immutable authority would republish |
| `p9_corrected_cfg_main_attempt_reservation` | outdated | yes | immutable reservation would republish |
| `p9_production_cache_acceptance` | outdated | yes | cache acceptance would republish |
| `p9_production_cache_validation` | outdated | yes | complete cache validation would execute |
| `p9_production_cache_materialization` | outdated | yes | production cache construction target would execute |
| `p9_infrastructure_readiness` | up to date | yes | safely skipped, but insufficient to bound closure |

Additional unexpected candidates span methodology authority, augmentation-bank construction/validation, fixed query construction/validation, P6 model/DataLoader acceptance, P7 runtime publication, and P8 plan publication. This violates the explicit requirements that all accepted upstream scientific parents be current, cache construction not be scheduled, and unrelated P1-P8 branches not enter the executable closure.

## Bootstrap decision

The interpretation that `shortcut = FALSE` is operationally permissible is valid in principle, but the concrete invocation is unsafe against the current store snapshot. Running it would not be a six-target bootstrap; it would traverse 65 additional outdated targets, including production-cache materialization.

No fake metadata, placeholder object, addendum, new authority, new reservation, direct Python invocation, `torchrun`, `tar_make()`, or unrelated target-currentness repair was performed. The exact `shortcut = FALSE` formal command was not launched.

## Formal state and prohibited execution

- Reservation: `AUTHORIZED_NOT_STARTED`.
- New run identity: none.
- State transition to `STARTING`/`RUNNING`: 0.
- Lock acquisition: 0.
- DDP/GPU processes: 0.
- Optimizer updates: 0.
- Formal validation queries/galleries: 0/0.
- Held-out evaluation consumption: 0.
- Checkpoints: 0.
- Other P9-A attempts: 0.
- P9-B, selected-FM, P10, P11, evaluation, maintenance: 0.
- Production-cache construction/validation execution: 0.

## Immutability evidence

Pre-execution fingerprints are stored beside the closure audit. Because the closure gate failed, these are also the terminal fingerprints for this work unit.

- Model/P1-P8/authorization files: 2,426 SHA-256 records.
- Existing target-store objects: 1,266 SHA-256 records.
- Production-cache inventory: 314,695 path/size/mtime records.
- Fuse tracked files: 534 SHA-256 records before this report.
- Dissertation tracked files: 63 SHA-256 records.

The model, cache, and target-store inventories are byte-for-byte identical to the post-invocation inventories from the preceding blocked work unit. No scientific artifact, cache payload, checkpoint, lock, or target object was created or mutated.

## Validation and remaining work

The formal validator and runtime digest gate passed. Full test suites, target execution, no-op replay, and Typst compilation were not rerun because the mandatory read-only closure gate failed before any source change or formal execution. The repository runtime remains the already validated and published runtime tree.

A separately authorized correction must narrow the executable target closure without fabricating metadata or rebuilding immutable parents. The correction should make accepted P7/P8/P9/cache references explicit immutable file parents or otherwise provide an allowlisted formal bootstrap entry whose closure contains only current references and the six formal targets. After implementation, the closure audit must be repeated before this same reservation can be used.

## Prompt summary

The user authorized reuse of the same unstarted `cfg_main` attempt and allowed `shortcut = FALSE` only after a fail-closed dependency audit proved a bounded closure. The audit found 65 unexpected build candidates, so training was correctly withheld.
