# S09 runtime input boundary repair

## Scope and execution

- Execution window: 2026-09-10 22:30-23:12 KST
- Input Fuse commit: `e9885baecd644a753e1a8bf8847fc3680f893c03`
- Implementation output commit: `fe880db7e11a2eac77088fbe11daeb525bd377b8`
- Branch: `reduced`
- Purpose: repair only the formal S09 prepared-data runtime boundary after the GPU parallelization decision retained one model on two-GPU DDP.
- Prompt summary: map logical augmentation intensity to the accepted physical P4 profile, resolve `scene_center_5186` from the exact accepted current scene index, preserve the 296 GiB prepared cache, prove the repaired formal input path with one disposable two-GPU epoch, and do not resume formal targets.

Formal S09 campaign execution was not resumed. No formal checkpoint, run acceptance, or target-store metadata was created or edited.

Changed tracked files:

- `R/training_targets.R`
- `python/training_campaign.py`
- `python/training_configuration.py`
- `python/training_runtime_inputs.py`
- `python/training_worker.py`
- `tests/python/test_training_controller.py`
- `tests/python/test_training_runtime_inputs.py`
- `tests/test_training_configuration.py`

## Root causes and repair

### Augmentation profile

`training_configuration.materialize_hyperparameter_configuration()` computed the correct P4 profile, but `training_worker.load_worker_values()` discarded that routing result and passed the logical numeric intensity to `ProductionPreparedData`. The cache reader requires a physical profile identifier.

One authoritative mapping now lives in `python/training_runtime_inputs.py`:

| Logical intensity | Physical profile |
|---:|---|
| 0.5 | `weak_0.5x` |
| 1.0 | `main_1.0x` |
| 2.0 | `strong_2.0x` |

Both configuration materialization and the formal worker use this mapping. Unsupported values fail with `S09_AUGMENTATION_INTENSITY_UNSUPPORTED`. The 11 OFAT configurations resolve to weak/main/strong counts of 1/9/1.

### Scene center

The immutable prepared payloads intentionally do not contain `scene_center_5186`, while formal collation requires one center per scene. Rebuilding 80,472 prepared entries to duplicate this parent data was unnecessary.

`SceneCenterIndex` now resolves centers at the prepared-data reader/formal assembly boundary. It follows the configured current P6 acceptance to the exact P1 scene index and validates:

- current methodology authority, P6 acceptance, P3 cache and P3 acceptance bindings;
- exact P1 scene index and scene acceptance identities;
- acceptance/manifest/parquet checksums;
- 12,421 unique scene IDs with split counts 2,421/1,000/9,000;
- EPSG:5186 and finite x/y coordinates;
- prepared sample scene, split, and current P3 cache lineage.

Historical sibling index generations are not scanned or accepted. The center is attached in memory immediately before collation; immutable prepared payloads are not rewritten.

## Current artifact validation

Prepared cache remained:

- cache ID: `s09cache_dc4e9e271e40ffe8ae17967c`
- acceptance ID: `s09ca_e2a1882eb206e1b5c930ddd5`
- entries: 80,472
- manifest SHA-256: `269f05b255cfaa0df8b21b17914d3475c65f4f3e2d672fd2669b927a00699370`
- acceptance file SHA-256: `201a79ddc9f858d7829518bcd96dc84d5bcfa85dea6cecef345534dda8fc7bf4`
- metadata/acceptance validation: PASS

Actual cache-index projection:

| Profile | Scenes | Physical views | Logical K=8 views | Representative collation |
|---|---:|---:|---:|---|
| `weak_0.5x` | 2,421 | 19,368 | 19,368 | PASS, center `[1,2]` finite |
| `main_1.0x` | 2,421 | 38,736 | 19,368 | PASS, center `[1,2]` finite |
| `strong_2.0x` | 2,421 | 19,368 | 19,368 | PASS, center `[1,2]` finite |

The cache files were not modified. Because the existing training DAG uses a broad `s09_training_sources` file target, `s09_prepared_cache_acceptance` is metadata-outdated after this implementation edit. This does not invalidate the cache identity or schedule payload construction: the existing cache destination is deterministic and the builder validates and returns its existing acceptance. The next formal run will re-evaluate the target, but it must reuse rather than regenerate the 80,472 payloads.

## Disposable two-GPU formal-path gate

The repaired worker path was exercised with the retained formal runtime contract:

- one model, GPUs 0 and 1;
- NCCL DDP world size 2;
- per-rank batch 16, global batch 32;
- `NCCL_P2P_DISABLE=1`, `NCCL_IB_DISABLE=1`;
- 76 optimizer updates, one complete epoch, then one validation pass;
- accepted prepared cache and current scene-index lineage;
- no formal publication output.

Result:

- exit status: 0
- epoch wall time: 52.68 s
- validation wall time: 7.03 s
- aggregate throughput: 46.17 scenes/s
- mean training loss by rank: 6.0247 / 6.0607, all finite
- validation retrieval loss: 3.68725
- validation margin: 0.05418
- queue count: 4,864
- EMA updates: 76
- peak allocated VRAM: 5.60 / 7.02 GiB
- peak RSS: approximately 6.72 GiB per rank
- output: `logs/s09/benchmark/20260910_230242_repaired_formal_boundary_ddp2.json`

An earlier disposable attempt omitted the two formal NCCL transport environment variables and was stopped after communication did not progress normally. Its two child ranks were explicitly terminated, no process remained, and no formal artifact was touched. The corrected exact-environment run above passed.

## Authority and retry impact

- Previous implementation provenance hash: `dae48488a25dec49003db488ce174f510e14fcfc99d80ff84007b5f91ca3da11`
- Repaired registered implementation hash: `b433a0236f58226330333bf0b34353a686c911dada074a78183389c35fe81876`
- Selection hash: unchanged, `74dce6af666427f1d1b821f94fd8ab5b5ddc16bdda3e73985c33a17500d23c10`
- P0/S08 scientific methodology: unchanged
- Cache ID/acceptance: unchanged

The implementation provenance change deterministically requires fresh OFAT authority identities. A disposable materialization produced 11 unique authorities; the new main authority/run identities are `s09auth_05cf31d6b21ad3fd2986da9f` and `p9runv2_dd960ce922ab1fc50a88513e`. They were not published in this repair task; normal formal targets must publish them on the next run.

The old main attempt has no committed epoch or checkpoint and replays as `BLOCKED` / `RESTART_REQUIRED`. It must not resume or append to that run. The new implementation-bound authority creates a fresh run identity, preserving the old epoch-zero log history separately.

## Validation

- `git diff --check`: PASS
- Python compile: PASS
- R parse: PASS, 57 current R/target/entrypoint files
- JSON/YAML parse: PASS
- focused runtime/config/controller tests: PASS, 39 tests
- full Python pytest: PASS, 446 tests
- full R testthat: PASS
- `_targets_training.R` manifest: PASS, 27 targets
- `_targets_training.R` `tar_validate()`: PASS
- main `_targets.R` manifest/validate: PASS, 61 targets
- formal S09 campaign executed: NO
- production cache rebuilt: NO
- formal checkpoint created: NO
- production target store manually edited: NO
- GPU/DDP processes remaining after disposable gate: NONE
- implementation commit: `fe880db7e11a2eac77088fbe11daeb525bd377b8`
- implementation commit push: PASS to `origin/reduced`

At report time, the training-store outdated set begins with source/cache-acceptance re-evaluation and then the OFAT lifecycle. The cache content itself remains valid and reusable; fresh implementation-bound OFAT authorities and runs are expected. Main research-store outdated status observed during validation was `s08_current_plan_sources` and `s08_current_experiment_plan`, caused by current repository source provenance and unrelated to this S09 cache content.

## Final verdict

`PASS_S09_RUNTIME_INPUT_BOUNDARY_REPAIRED`

Next separately authorized action: run `Rscript scripts/run_training_targets.R campaign`. It must validate/reuse `s09cache_dc4e9e271e40ffe8ae17967c`, publish the new implementation-bound authorities, and enter the fresh real `main` OFAT epoch without reusing the failed epoch-zero run history.
