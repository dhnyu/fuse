# S09 runtime-provenance authority dependency repair

## Scope

- Execution window: 2026-09-11 00:06-00:29 KST
- Input Fuse HEAD: `394fdc9fae91135d73a0f2752d8cb26179903aef`
- Implementation commit: `caf45e8c5120519496e7f05d8a34b27a5b34e609`
- Branch: `reduced`
- Purpose: make current S09 runtime provenance an explicit dependency of OFAT and comparison authorities without rebuilding the accepted prepared cache.
- Prompt summary: diagnose stale authority reuse, add a first-class runtime-provenance target, preserve the blocked epoch-zero ledger and 296 GiB cache, prove 11/17 fresh authorities and target-currentness behavior, validate, commit, and push without training.

## Original failure

The 2026-09-11 formal attempt reused `s09auth_fdc2c9c375c4b893f33f8682`, whose `scientific_implementation_hash` was the previous `dae48488a25dec49003db488ce174f510e14fcfc99d80ff84007b5f91ca3da11`. Its run `p9runv2_a4b043fc216865cafa9076ab` had already ended at epoch/update 0/0 with no checkpoint. Ledger replay correctly returned `BLOCKED` / `RESTART_REQUIRED`, and the controller stopped with `RUN_NOT_STARTABLE_FROM_REPLAY_STATE` before DDP launch.

The old graph was:

```text
s09_training_sources -> s09_prepared_cache_acceptance
                     -> same immutable acceptance path/value
                     -> s09_ofat_authorities remained current
```

`s09_publish_ofat_authorities()` read the Python runtime implementation at execution time, but the authority target had no direct target dependency on that content. Because the cache target returned the same path and file hash, `{targets}` had no changed downstream value with which to invalidate the authority collection. The comparison authority collection had the same latent defect.

## Repaired provenance model

`config/s09_runtime_provenance.yml` is the single source registry for the seven files in the established S09 runtime implementation digest. `python/training_runtime_provenance.py` computes the canonical file hashes and digest; R obtains that exact Python result through `scripts/training_runtime_provenance.py` and verifies the registered path set.

- Current runtime implementation SHA-256: `b433a0236f58226330333bf0b34353a686c911dada074a78183389c35fe81876`
- Authority-publication provenance SHA-256: `cfd88989949c0b3749b6284d00046961490e45974bed09d8ac708723bdccd1c7`
- Selection-contract SHA-256: `74dce6af666427f1d1b821f94fd8ab5b5ddc16bdda3e73985c33a17500d23c10`

The training graph now contains:

```text
s09_prepared_cache_sources -> s09_prepared_cache_acceptance
s09_runtime_sources -> s09_runtime_implementation
s09_runtime_implementation -> s09_ofat_authorities
s09_runtime_implementation -> s09_comparison_authorities
```

Authority publication receives the explicit digest and independently checks it against the canonical Python calculation. A mismatch fails with `S09_RUNTIME_IMPLEMENTATION_HASH_MISMATCH`. Runtime worker/input changes no longer reach the prepared-cache target through the former broad source vector. Files that genuinely define cache construction remain in the cache-specific registry.

The resulting training DAG has 29 targets and 78 edges. The dependency network HTML was regenerated at `artifacts/targets-network-p9-v2-training/targets-network.html`.

## Fresh authority identities

Disposable materialization from the current S08 plan, lineage, cache acceptance, configs, and runtime digest produced:

- OFAT authorities: 11/11 unique, all bound to `b433a023...`
- Comparison authorities: 17/17 unique, all bound to `b433a023...`
- Stale OFAT authority IDs present: NO
- Fresh main authority: `s09auth_05cf31d6b21ad3fd2986da9f`
- Fresh main run: `p9runv2_dd960ce922ab1fc50a88513e`

The disposable comparison authorities were built only after a synthetic complete 11-result winner fixture. Selected hyperparameters propagated through the normal comparison-authority builder. No production authority was published.

## Epoch-zero ledger preservation

The historical stale run remains unchanged:

- authority: `s09auth_fdc2c9c375c4b893f33f8682`
- run: `p9runv2_a4b043fc216865cafa9076ab`
- ledger sequence: 4
- final event hash: `c4c5d8384c4b1921935a7127dbdec49a09e4eec0cff18f8a089b2c29e7bd0235`
- state: `BLOCKED` / `RESTART_REQUIRED`
- resume allowed: false

Existing controller tests confirm that a blocked epoch-zero authority cannot restart and that a new implementation-bound authority obtains a distinct authority, run key, run ID, ledger path, and progress-log identity.

## Prepared-cache preservation

- Cache ID: `s09cache_dc4e9e271e40ffe8ae17967c`
- Acceptance ID: `s09ca_e2a1882eb206e1b5c930ddd5`
- Prepared payloads: 80,472
- Acceptance file SHA-256: `201a79ddc9f858d7829518bcd96dc84d5bcfa85dea6cecef345534dda8fc7bf4`
- Manifest SHA-256: `269f05b255cfaa0df8b21b17914d3475c65f4f3e2d672fd2669b927a00699370`
- Payload rebuild: NO

The disposable `{targets}` currentness regression built cache, runtime, OFAT, winner, and comparison stages with runtime digest A, then changed only the runtime source to digest B. Cache source, payload target, and cache acceptance remained current; runtime provenance, OFAT authorities/runs, winner, comparison authorities/runs became outdated.

The real training-store read-only audit reports 27 pending/outdated targets. `s09_prepared_cache_acceptance` is included once because its target source dependency was split; its deterministic builder will validate and return the existing destination before its payload construction branch. Runtime provenance, fresh authorities, OFAT lifecycle, winner, comparison lifecycle, and campaign acceptance are pending. The production store was not executed or edited.

## S08 isolation

- Plan ID: `s08plan_7cd58ffb65db3d43fd3fa234`
- Content SHA-256: `7cd58ffb65db3d43fd3fa234fb5c6b7489640ea7e1e2a1bda76082f3ac3e81e3`
- Serialized SHA-256: `74ae70958b96dd663d300c6f7441a0653b1a7c5066d6e1bfe9b4b459d7781789`
- Main research-store outdated count: 0

S08 has no edge to S09 runtime provenance. Runtime changes remain S09 authority/run provenance and do not change the scientific experiment-plan identity.

## Validation

- `git diff --check`: PASS
- R parse: PASS, 57 R/target/entrypoint files
- Python compile: PASS
- YAML/JSON parse: PASS
- Focused S09 target/currentness tests: PASS
- Focused authority and ledger/resume tests: PASS
- Disposable authority publication: PASS, 11 OFAT and 17 comparison authorities
- Full Python pytest: PASS, 449 tests
- Full R testthat: PASS
- `_targets.R` manifest/validate: PASS, 61 targets
- `_targets_training.R` manifest/validate: PASS, 29 targets
- Training DAG: PASS, 78 edges, acyclic
- Dependency network regeneration: PASS. The generic renderer's first attempt encountered retained historical error/outdated overlap; regeneration used live outdated state as precedence without modifying the store.
- Formal training executed: NO
- GPU/DDP executed: NO
- Production cache rebuilt: NO
- Production authority published: NO
- Targets-store metadata manually edited: NO
- Historical logs modified: NO

## Git result

- Implementation commit: `caf45e8c5120519496e7f05d8a34b27a5b34e609`
- Commit message: `fix(s09): bind authorities to runtime provenance`
- Push result: recorded after report commit
- Final repository synchronization: recorded after push

## Next action

With separate authorization, execute `Rscript scripts/run_training_targets.R campaign`. It must validate/reuse the current cache, publish authorities bound to `b433a023...`, create fresh main run `p9runv2_dd960ce922ab1fc50a88513e`, and enter the two-GPU DDP epoch without selecting the historical blocked run.

`PASS_S09_RUNTIME_AUTHORITY_DEPENDENCY_REPAIRED`
