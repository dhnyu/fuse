# Current-lineage source and target cleanup

## Executive summary

The active `reduced` implementation is now current-lineage only. All 60 audited
legacy-bound main targets are absent, no aliases recreate them, obsolete
prototype/IP/P8/P9-v1/recovery/retrieval execution code is removed, and current
training/evaluation/downstream utilities use responsibility-oriented modules.

Final verdict: `PASS_WITH_INTENTIONAL_HISTORICAL_GUARDS`.

## Repository state

- Execution time: 2026-09-08 03:38-06:19 Asia/Seoul
- Input HEAD: `60f6b4affce9a46c1d6c06104571bc27bb3f0889`
- Implementation output HEAD: `3d6584fb42b8eb7b7d2873d6a10dbbda08e2d73c`
- Branch: `reduced`
- Input synchronization: `origin/reduced...HEAD = 0/0`
- Dissertation HEAD: `cbb824f19be8355296603f8426ac241ce587ddcc`
- Dissertation branch/synchronization: `reduced`, `0/0`, clean and unmodified

## Methodology authority

| Field | Before | After |
|---|---|---|
| Authority ID | `mta_03e8d7f42fe2018237f3fcde` | `mta_7875c4ba4587e4877ba0be1d` |
| Dissertation commit | `cbb824f19be8355296603f8426ac241ce587ddcc` | identical |
| Scientific modules | 10 | 10 |
| Changed modules | not applicable | 0 |
| Scientific contract SHA-256 | `426b2b6ce011794335d2e6f052e56ef463a7f0022f5733784c60eae9f85425ca` | identical |
| Authority file SHA-256 | `766e5b0e99f2342c19b477c8e5905124defeeccc9d7cf562640fe1b34f4994b2` | `b2991c2d22faefc2d35e11d57778dd2488a1059b090d20f7ce50dbc79a1e00cf` |

The new authority is an `OPERATIONAL_ONLY` immutable supersession. Publication
fails closed if the dissertation commit, module set, or any module SHA-256 differs
from the predecessor. The predecessor remains unchanged.

## Scientific invariants

The cleanup preserves 10,000 off-grid scenes, the 1,000/9,000 split, 50 m
off-grid distance, `d = d_c = 128`, contrastive-only training, modality masking,
momentum encoder, EMA, FIFO queue, 11 OFAT configurations, 17 compared models,
current A1-A5/B1-B9 semantics, and current augmentation/relation/downstream
contracts. Information-preservation loss and reconstruction decoders are absent
from current model construction and training.

## Target topology

| Metric | Before | After |
|---|---:|---:|
| Main targets | 132 | 61 |
| Dynamic parents | 19 | 9 |
| Graph edges | 430 | 199 |
| Audited legacy targets present | 60 | 0 |
| New current main targets | n/a | 11 |
| Weak graph components | not recorded | 2 |

The 11 new current target identities are current stage boundaries or replacements,
not compatibility aliases. The exact retired set in
`config/retired_main_targets.yml` is byte-order equivalent to the audit snapshot,
and its intersection with the active manifest is empty.

## Active target tree

The main `_targets.R` contains only s00, s01, s02, s03, s04, s05, s06, and s08.
Current training, evaluation, and downstream work remain in dedicated s09-s11
entrypoints. Maintenance remains isolated. `_targets_p9_formal.R` and
`_targets_p9_recovery.R` are immediate fail-closed guards rather than target DAGs.

## Source cleanup metrics

| Metric | Before | After |
|---|---:|---:|
| R files in `R/` | 63 | 36 |
| R files in `targets/` | 41 | 15 |
| R scripts | 23 | 14 |
| Python scripts | 57 | 27 |
| R tests | 54 | 22 |
| Python tests | 78 | 36 |
| Python library files | 92 | 39 |
| Total executable/test source files | 408 | 189 |
| Net source/test files removed | 0 | 219 |
| Tracked bytecode files | 66 | 0 |
| Files renamed | 0 | 153 |
| All tracked files deleted | 0 | 461 |
| Duplicate utility implementations consolidated | 0 | 4 |

The four consolidation clusters are the R source registry, training identity
validation, accepted-checkpoint resolution, and current methodology/experiment
contract validation. Cross-language implementations that enforce contracts on
both sides remain deliberately separate.

## Extracted current utilities

| Historical source | Current source | Result |
|---|---|---|
| `python/p9_identity_diagnostics.py` | `python/training_identity.py` | current-batch identity validation only |
| `python/p9_selected_fm_campaign.py` | `python/checkpoint_resolution.py` | acceptance-based checkpoint resolver only |
| duplicated `_targets.R`/test source lists | `R/current_source_registry.R` | one deterministic current loader |
| P-number training modules | `python/training_*.py` and `R/training_targets.R` | generalized current lifecycle without v1/import execution |
| P10/P11 modules | evaluation/downstream responsibility names | current entrypoints and tests updated |

## Removed obsolete behavior

- Prototype membership/observation/serialization/model/training DAGs and runners.
- IP loss, reconstruction decoders/loss/counters/smokes, and selected-FM IP campaign.
- Old P8 replay/builder and 13-row/seven-comparison executable contracts.
- P9-v1 authorization, execution, recovery, isolated execution, campaign, and
  historical import implementations.
- Active 400/1,600/2,000 scene assumptions and old retrieval gallery execution.
- Obsolete configs, schemas, fixtures, tests, target aliases, and source wrappers.
- Tracked `.pyc` files and cache directories; `.gitignore` now blocks recurrence.

## P9 retirement redesign

The current retirement record inventories immutable authority roots and historical
stores, records retired/prohibited interfaces and the replacement resolver, and
has publication identity `current-lineage-p9-v1-retirement-v2`. It does not hash
obsolete executable source files. The published record is
`p9ret_246eaf97570f115d4faaf3d1`. Two CLI and two target-entrypoint guards fail
immediately with the stable retirement error; no old executable graph remains.

## Validation

- R parse: 97 files passed.
- Python AST parse: 105 files passed at validation time.
- Full R testthat: passed.
- Full Python pytest: 422 passed.
- Active entrypoints: manifest and `tar_validate()` passed for main (61),
  maintenance (1), training (9), evaluation (5), diagnostics (2), downstream (2),
  readiness (2), and ridge (2).
- Retirement entrypoints: both produced the expected immediate guard failure.
- Main graph: no duplicate names, 61 targets, 9 dynamic parents, 199 edges.
- Target network HTML: regenerated and matched 61 targets/199 edges.
- P0 parity: dissertation commit identical, 10/10 module hashes identical,
  changed-module set empty.
- Forbidden-current scan: no current executable legacy behavior. Remaining terms
  occur only in retirement guards, negative validation sets, and guard fixtures.

During an early test pass, two obsolete tests invoked `targets::tar_make()` only
against disposable temporary fixture stores. This was unintended and those tests
were removed/replaced. No repository targets store, production input, accepted
artifact, training, evaluation, retrieval, downstream computation, or scientific
result was executed or modified.

## Remaining risks

- P1-P6 configs are intentionally `RECOMPUTE_REQUIRED` for the current authority;
  the next readiness audit must validate source availability before production.
- External immutable paths retain historical P-number directory names. Renaming
  them would violate artifact identity and was intentionally not attempted.
- The two P9 retirement guard names remain intentionally historical so operators
  receive an explicit failure instead of a missing or accidentally reusable path.

## Input prompt summary

Remove exactly 60 audited legacy-bound main targets and obsolete executable source,
extract current reusable logic, normalize current filenames, remove IP and stale
population paths, redesign retirement evidence, preserve scientific semantics and
immutable artifacts, publish an operational-only P0 supersession, validate without
production execution, commit, report, and push `reduced`.

## Exact 60-target disposition

| old target | old command | old stage | legacy reason | still-needed scientific function? | extracted current logic | new current target | historical evidence retained | DELETE |
|---|---|---|---|---|---|---|---|---|
| `augmentation_benchmark_contract_files` | `normalizePath(augmentation_benchmark_contract_paths(), mustWork = TRUE)` | s04 | legacy-only orchestration or smoke boundary | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `training_plan_contract_files` | `normalizePath(training_plan_contract_paths(), mustWork = TRUE)` | s07 | superseded pilot/runtime lifecycle | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `s07_training_sources` | `p7_contract_files()` | s07 | superseded pilot/runtime lifecycle | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `joint_model_smoke_contract_files` | `normalizePath(joint_model_smoke_contract_paths(), mustWork = TRUE)` | s07 | legacy-only orchestration or smoke boundary | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `encoder_smoke_contract_files` | `normalizePath(encoder_smoke_contract_paths(), mustWork = TRUE)` | s07 | legacy-only orchestration or smoke boundary | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `s08_experiment_sources` | `p8_current_sources()` | s08 | superseded immutable P8 replay contract | yes, current semantics only | current helper retained without old target identity | `s08_current_plan_sources` | immutable old plan artifacts | YES |
| `prototype_model_acceptance_contract_files` | `normalizePath(prototype_model_acceptance_contract_paths(), mustWork = TRUE)` | s07 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `dataloader_smoke_contract_files` | `normalizePath(dataloader_smoke_contract_paths(), mustWork = TRUE)` | s07 | legacy-only orchestration or smoke boundary | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `full_membership_authorization_contract` | `normalizePath(full_membership_authorization_contract_path(), mustWork = TRUE)` | s02 | historical authorization/plan lineage | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_model_validation_contract_files` | `normalizePath(prototype_model_validation_contract_paths(), mustWork = TRUE)` | s07 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `s07_runtime_sources` | `p7_cold_path_contract_files()` | s07 | superseded pilot/runtime lifecycle | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `full_membership_plan_contract_files` | `normalizePath(full_membership_plan_contract_paths(), mustWork = TRUE)` | s02 | historical authorization/plan lineage | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `i06_accepted_model_sources` | `p7_resolve_p6_parent_reference(s07_training_sources)` | s07 | predecessor-bound immutable input | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `i07_training_input_sources` | `p7_resolve_immutable_parent_reference(s07_training_sources)` | s07 | superseded pilot/runtime lifecycle | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `s08_experiment_plan` | `p8_build_current_plan(s08_experiment_sources)` | s08 | superseded immutable P8 replay contract | yes, current semantics only | current helper retained without old target identity | `s08_current_experiment_plan` | immutable old plan artifacts | YES |
| `i05_validation_query_sources` | `p7_resolve_validation_query_reference(s05_query_sources, s07_training_sources)` | s05 | predecessor-bound immutable input | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_runtime_inputs` | `validate_runtime_mirror(runtime_mirror_contract_files)` | s07 | prototype lineage is not current methodology | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `full_membership_i24_authorization` | `validate_full_membership_i24_authorization(full_membership_authorization_contract)` | s02 | historical authorization/plan lineage | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `i07_runtime_validation_sources` | `p7_cold_path_verification_reference(s07_runtime_sources)` | s07 | superseded pilot/runtime lifecycle | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `s07_pilot_training_authority` | `p7_build_authority(i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources, i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources, i07_training_input_sources, i07_training_input_sources, s07_training_sources)` | s07 | superseded pilot/runtime lifecycle | yes, current semantics only | current helper retained without old target identity | `s09_training_contract (dedicated entrypoint)` | immutable training/checkpoint/retirement artifacts | YES |
| `s07_training_geometry_cache` | `p7_build_geometry_cache(s07_pilot_training_authority, i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources, i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources, i07_training_input_sources, s07_training_sources)` | s07 | superseded pilot/runtime lifecycle | yes, current semantics only | current helper retained without old target identity | `s09_training_geometry_cache (dedicated entrypoint)` | immutable training/checkpoint/retirement artifacts | YES |
| `s07_ddp_initialization_validation` | `p7_gpu_gate("init", s07_pilot_training_authority, i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources, i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources, i07_training_input_sources, s07_training_geometry_cache, s07_training_sources)` | s07 | superseded pilot/runtime lifecycle | yes, current semantics only | current helper retained without old target identity | `current training worker validation (library/test boundary)` | immutable training/checkpoint/retirement artifacts | YES |
| `s07_ddp_update_validation` | `{ s07_ddp_initialization_validation p7_gpu_gate("update", s07_pilot_training_authority, i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources, i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources, i07_training_input_sources, s07_training_geometry_cache, s07_training_sources) }` | s07 | superseded pilot/runtime lifecycle | yes, current semantics only | current helper retained without old target identity | `current training worker validation (library/test boundary)` | immutable training/checkpoint/retirement artifacts | YES |
| `s07_ddp_reference_validation` | `{ s07_ddp_update_validation p7_gpu_gate("reference", s07_pilot_training_authority, i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources, i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources, i07_training_input_sources, s07_training_geometry_cache, s07_training_sources) }` | s07 | superseded pilot/runtime lifecycle | yes, current semantics only | current helper retained without old target identity | `current training worker validation (library/test boundary)` | immutable training/checkpoint/retirement artifacts | YES |
| `s01_pilot_scene_index` | `build_reduced_prototype_scene_selection(scene_index_acceptance = s01_scene_acceptance, spatial_scene_index = s01_scene_index, p1_scene_index_contract_files = s01_scene_sources, workers = 1L, threads = 1L)` | s01 | legacy-only orchestration or smoke boundary | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `s07_ddp_resume_validation` | `{ s07_ddp_reference_validation p7_gpu_gate("resume", s07_pilot_training_authority, i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources, i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources, i07_training_input_sources, s07_training_geometry_cache, s07_training_sources) }` | s07 | superseded pilot/runtime lifecycle | yes, current semantics only | current helper retained without old target identity | `current training worker validation (library/test boundary)` | immutable training/checkpoint/retirement artifacts | YES |
| `base_spatial_prototype_membership_plan` | `p2_build_membership_plan("prototype", s01_scene_index, s01_pilot_scene_index, s01_scene_acceptance, s01_study_inventory_validation, s00_methodology_authority, s00_spatial_methodology_contract, membership_contract_files, p2_base_spatial_contract_files)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_membership_plan` | `build_prototype_membership_plan(prototype_scene_selection = s01_pilot_scene_index, study_data_inventory = s01_study_inventory_validation, membership_contract_files = membership_contract_files, research_config_files = s01_study_sources, workers = 1L, threads = 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `s07_pilot_training_execution` | `p7_run_production(s07_pilot_training_authority, s07_ddp_resume_validation, i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources, i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources, i07_training_input_sources, s07_training_geometry_cache, s07_training_sources)` | s07 | superseded pilot/runtime lifecycle | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `base_spatial_prototype_membership_shard` | `p2_build_membership_shard(base_spatial_prototype_membership_plan, i01_seoul_spatial_sources, i01_seoul_spatial_sources, membership_contract_files, 1L, 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_membership_shard` | `build_prototype_membership_shard(prototype_membership_plan = prototype_membership_plan, study_data_inputs = i01_seoul_spatial_sources, prototype_runtime_inputs = prototype_runtime_inputs, membership_contract_files = membership_contract_files, workers = 1L, threads = 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `s07_pilot_training_acceptance` | `p7_consolidated_acceptance(s07_pilot_training_authority, s07_pilot_training_execution, s07_training_geometry_cache, c(s07_ddp_initialization_validation, s07_ddp_update_validation, s07_ddp_reference_validation, s07_ddp_resume_validation), s07_training_sources)` | s07 | superseded pilot/runtime lifecycle | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `base_spatial_prototype_membership_acceptance` | `p2_accept_membership("prototype", base_spatial_prototype_membership_plan, base_spatial_prototype_membership_shard, s01_scene_index, s01_pilot_scene_index, s01_study_inventory_validation, membership_contract_files, p2_base_spatial_contract_files)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_membership_acceptance` | `build_prototype_membership_acceptance(prototype_membership_plan = prototype_membership_plan, prototype_membership_shard = prototype_membership_shard, prototype_scene_selection = s01_pilot_scene_index, study_data_inventory = s01_study_inventory_validation, membership_contract_files = membership_contract_files, workers = 1L, threads = 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `base_spatial_prototype_observation_plan` | `p2_build_observation_plan("prototype", base_spatial_prototype_membership_plan, base_spatial_prototype_membership_acceptance, s01_scene_index, s01_pilot_scene_index, observation_contract_files, raster_observation_contract_files, relation_contract_files, p2_base_spatial_contract_files)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_observation_plan` | `build_prototype_observation_plan(prototype_scene_selection = s01_pilot_scene_index, prototype_membership_acceptance = prototype_membership_acceptance, observation_contract_files = observation_contract_files, workers = 1L, threads = 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `base_spatial_prototype_vector_observation_shard` | `p2_build_vector_shard(base_spatial_prototype_observation_plan, base_spatial_prototype_membership_acceptance, i01_seoul_spatial_sources, i01_seoul_spatial_sources, observation_contract_files, 1L, 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_vector_observation_shard` | `build_prototype_vector_observation_shard(prototype_observation_plan = prototype_observation_plan, prototype_membership_acceptance = prototype_membership_acceptance, study_data_inputs = i01_seoul_spatial_sources, prototype_runtime_inputs = prototype_runtime_inputs, observation_contract_files = observation_contract_files, workers = 1L, threads = 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `base_spatial_prototype_raster_observation_shard` | `p2_build_raster_shard(base_spatial_prototype_observation_plan, base_spatial_prototype_vector_observation_shard, i01_seoul_spatial_sources, i01_seoul_spatial_sources, raster_observation_contract_files, 1L, 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `base_spatial_prototype_relation_graph_shard` | `p2_build_relation_shard(base_spatial_prototype_observation_plan, base_spatial_prototype_vector_observation_shard, i01_seoul_spatial_sources, i01_seoul_spatial_sources, relation_contract_files, 1L, 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `base_spatial_prototype_source_topology_shard` | `p2_build_topology_shard(base_spatial_prototype_observation_plan, base_spatial_prototype_vector_observation_shard, i01_seoul_spatial_sources, p2_base_spatial_contract_files, 1L, 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_relation_shard` | `build_prototype_relation_shard(prototype_observation_plan = prototype_observation_plan, prototype_vector_observation_shard = prototype_vector_observation_shard, study_data_inputs = i01_seoul_spatial_sources, prototype_runtime_inputs = prototype_runtime_inputs, relation_contract_files = relation_contract_files, workers = 1L, threads = 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_raster_observation_shard` | `recover_raster_observation_branch(spec = prototype_observation_plan, vector_files = prototype_vector_observation_shard, study_data_inputs = i01_seoul_spatial_sources, raster_observation_contract_files = raster_observation_contract_files, compute = build_prototype_raster_observation_shard(prototype_observation_plan = prototype_observation_plan, prototype_vector_observation_shard = prototype_vector_observation_shard, study_data_inputs = i01_seoul_spatial_sources, prototype_runtime_inputs = prototype_runtime_inputs, raster_observation_contract_files = raster_observation_contract_files, workers = 1L, threads = 1L))` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `base_spatial_prototype_acceptance` | `p2_build_base_spatial_acceptance("prototype", base_spatial_prototype_membership_plan, base_spatial_prototype_membership_acceptance, base_spatial_prototype_observation_plan, base_spatial_prototype_vector_observation_shard, base_spatial_prototype_raster_observation_shard, base_spatial_prototype_relation_graph_shard, base_spatial_prototype_source_topology_shard, s01_scene_index, s01_pilot_scene_index, s00_methodology_authority, s01_scene_acceptance, i01_seoul_spatial_sources, raster_observation_contract_files, relation_contract_files, p2_base_spatial_contract_files)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_spatial_acceptance` | `build_prototype_spatial_acceptance(prototype_observation_plan = prototype_observation_plan, prototype_vector_observation_shard = prototype_vector_observation_shard, prototype_raster_observation_shard = prototype_raster_observation_shard, prototype_relation_shard = prototype_relation_shard, prototype_runtime_inputs = prototype_runtime_inputs, methodology_contract = methodology_contract, spatial_acceptance_contract_files = spatial_acceptance_contract_files, workers = 1L, threads = 1L)` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `base_spatial_membership_plan` | `p2_build_membership_plan("production", s01_scene_index, s01_pilot_scene_index, s01_scene_acceptance, s01_study_inventory_validation, s00_methodology_authority, s00_spatial_methodology_contract, membership_contract_files, p2_base_spatial_contract_files, base_spatial_prototype_acceptance)` | s02 | legacy-only orchestration or smoke boundary | yes, current semantics only | current helper retained without old target identity | `s02_membership_plan` | immutable predecessor artifacts/stores | YES |
| `full_membership_plan` | `suppressWarnings(build_full_membership_plan(spatial_scene_index = s01_scene_index, prototype_spatial_acceptance = prototype_spatial_acceptance, prototype_model_acceptance = full_membership_i24_authorization, prototype_membership_acceptance = prototype_membership_acceptance, prototype_observation_plan = prototype_observation_plan, full_membership_plan_contract_files = full_membership_plan_contract_files))` | s02 | historical authorization/plan lineage | yes, current semantics only | current helper retained without old target identity | `s02_membership_plan` | immutable predecessor artifacts/stores | YES |
| `s07_runtime_acceptance` | `p7_cold_path_consolidated_acceptance(s06_dataset_acceptance, s07_pilot_training_acceptance, s07_training_geometry_cache, i07_runtime_validation_sources, s07_runtime_sources)` | s07 | superseded pilot/runtime lifecycle | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |
| `prototype_serialization_plan` | `{ base_spatial_acceptance build_prototype_serialization_plan(prototype_spatial_acceptance = prototype_spatial_acceptance, serialization_plan_contract_files = serialization_plan_contract_files, workers = 1L, threads = 1L) }` | s03 | prototype lineage is not current methodology | yes, current semantics only | current helper retained without old target identity | `s03_scene_serialization_plan` | immutable predecessor artifacts/stores | YES |
| `prototype_serialization_shard` | `recover_serialization_branch(spec = prototype_serialization_plan, serialization_shard_contract_files = serialization_shard_contract_files, compute = run_prototype_serialization_shard(prototype_serialization_plan = prototype_serialization_plan, serialization_shard_contract_files = serialization_shard_contract_files, workers = 1L, threads = 1L))` | s03 | prototype lineage is not current methodology | yes, current semantics only | current helper retained without old target identity | `s03_scene_serialization_shard` | immutable predecessor artifacts/stores | YES |
| `prototype_training_dataset_acceptance` | `recover_training_dataset_acceptance(serialization_plan = prototype_serialization_plan, serialization_branch_files = prototype_serialization_shard, spatial_files = prototype_spatial_acceptance, contract_files = training_dataset_acceptance_contract_files, compute = run_prototype_training_dataset_acceptance(prototype_spatial_acceptance = prototype_spatial_acceptance, prototype_serialization_plan = prototype_serialization_plan, prototype_serialization_shard = prototype_serialization_shard, training_dataset_acceptance_contract_files = training_dataset_acceptance_contract_files, workers = 1L, threads = 1L))` | s07 | prototype lineage is not current methodology | yes, current semantics only | current helper retained without old target identity | `s06_dataset_acceptance` | immutable training/checkpoint/retirement artifacts | YES |
| `prototype_dataloader_smoke` | `recover_file_target_metadata("prototype_dataloader_smoke", file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance), "smoke", "dataloader", "pdl_5eb0ccb9951d1015d6d64649"), run_prototype_dataloader_smoke(prototype_training_dataset_acceptance = prototype_training_dataset_acceptance, dataloader_smoke_contract_files = dataloader_smoke_contract_files, workers = 1L, threads = 1L))` | s07 | prototype lineage is not current methodology | yes, current semantics only | current helper retained without old target identity | `s06_dataset_loader_acceptance` | immutable predecessor artifacts/stores | YES |
| `prototype_model_validation` | `recover_file_target_metadata("prototype_model_validation", file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance), "validation", "prototype-model", "pmv_1d5412a7b035635a4187fbf6"), run_prototype_model_validation(prototype_training_acceptance = s07_pilot_training_acceptance, prototype_training_dataset_acceptance = prototype_training_dataset_acceptance, prototype_scene_selection = s01_pilot_scene_index, prototype_model_validation_contract_files = prototype_model_validation_contract_files, workers = 40L, threads = 1L))` | s07 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_scientific_geometry_roundtrip` | `recover_file_target_metadata("prototype_scientific_geometry_roundtrip", file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance), "roundtrip", "scientific-geometry", "pgr_77294c825bf26bf6fce721c3"), run_scientific_geometry_roundtrip(prototype_training_dataset_acceptance = prototype_training_dataset_acceptance, prototype_dataloader_smoke = prototype_dataloader_smoke, augmentation_benchmark_contract_files = augmentation_benchmark_contract_files, workers = 1L, threads = 1L))` | s02 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_encoder_smoke` | `recover_file_target_metadata("prototype_encoder_smoke", file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance), "smoke", "encoder", "pea_1c66760dbc1e6c0a8d71cb91"), run_prototype_encoder_smoke(prototype_training_dataset_acceptance = prototype_training_dataset_acceptance, prototype_dataloader_smoke = prototype_dataloader_smoke, encoder_smoke_contract_files = encoder_smoke_contract_files, workers = 1L, threads = 1L))` | s07 | prototype lineage is not current methodology | yes, current semantics only | current helper retained without old target identity | `s06_reference_encoder_validation` | immutable predecessor artifacts/stores | YES |
| `prototype_augmentation_benchmark` | `recover_file_target_metadata("prototype_augmentation_benchmark", file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance), "benchmark", "augmentation", "paa_5d2b1f56119e8d5f5050a75d"), run_prototype_augmentation_benchmark(prototype_training_dataset_acceptance = prototype_training_dataset_acceptance, prototype_dataloader_smoke = prototype_dataloader_smoke, prototype_scientific_geometry_roundtrip = prototype_scientific_geometry_roundtrip, augmentation_benchmark_contract_files = augmentation_benchmark_contract_files, workers = 1L, threads = 1L))` | s04 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_joint_model_smoke` | `recover_file_target_metadata("prototype_joint_model_smoke", file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance), "smoke", "joint-model", "pjm_6e64c022281a7f2648f78917"), run_prototype_joint_model_smoke(prototype_training_dataset_acceptance, prototype_dataloader_smoke, prototype_scientific_geometry_roundtrip, prototype_encoder_smoke, prototype_augmentation_benchmark, joint_model_smoke_contract_files, workers = 1L, threads = 1L))` | s07 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_model_acceptance` | `recover_file_target_metadata("prototype_model_acceptance", file.path(dirname(dirname(dirname(dirname(prototype_dataloader_smoke[basename(prototype_dataloader_smoke) == "prototype_dataloader_smoke.json"])))), "acceptance", "prototype-model", "pma_6282c9e9f9ebb9348484223a"), run_prototype_model_acceptance(prototype_dataloader_smoke = prototype_dataloader_smoke, prototype_encoder_smoke = prototype_encoder_smoke, prototype_augmentation_benchmark = prototype_augmentation_benchmark, prototype_training_acceptance = s07_pilot_training_acceptance, prototype_model_validation = prototype_model_validation, prototype_model_acceptance_contract_files = prototype_model_acceptance_contract_files))` | s07 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_distributed_joint_model_smoke` | `recover_file_target_metadata("prototype_distributed_joint_model_smoke", file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance), "distributed_joint", "pjd_69c0bd35dac8add3280d72e2"), run_prototype_distributed_joint_model_smoke(prototype_training_dataset_acceptance, prototype_joint_model_smoke, distributed_joint_model_contract_files, workers = 1L, threads = 1L))` | s07 | prototype lineage is not current methodology | no | none | `none` | immutable predecessor artifacts/stores | YES |
| `prototype_training_plan` | `recover_training_plan_metadata(training_plan_contract_files, build_prototype_training_plan(prototype_training_dataset_acceptance = prototype_training_dataset_acceptance, prototype_dataloader_smoke = prototype_dataloader_smoke, prototype_scientific_geometry_roundtrip = prototype_scientific_geometry_roundtrip, prototype_encoder_smoke = prototype_encoder_smoke, prototype_augmentation_benchmark = prototype_augmentation_benchmark, prototype_joint_model_smoke = prototype_joint_model_smoke, prototype_distributed_joint_model_smoke = prototype_distributed_joint_model_smoke, training_plan_contract_files = training_plan_contract_files, workers = 1L, threads = 1L))` | s07 | prototype lineage is not current methodology | no | none | `none` | immutable training/checkpoint/retirement artifacts | YES |

## Complete deleted-file list

- `R/p11_living_population_rematerialization.R`
- `R/research_augmentation_benchmark.R`
- `R/research_contracts.R`
- `R/research_dataloader_smoke.R`
- `R/research_distributed_joint_model_smoke.R`
- `R/research_dynamic_branch_recovery.R`
- `R/research_encoder_smoke.R`
- `R/research_full_membership_authorization.R`
- `R/research_full_membership_plan.R`
- `R/research_joint_model_smoke.R`
- `R/research_membership.R`
- `R/research_metadata_recovery.R`
- `R/research_methodology_authority.R`
- `R/research_p7_cold_path_runtime.R`
- `R/research_p8_experiment_plan.R`
- `R/research_p9_checkpoint_recovery.R`
- `R/research_p9_formal_authorization.R`
- `R/research_p9_formal_execution_isolated.R`
- `R/research_p9_infrastructure.R`
- `R/research_p9_v1_retirement.R`
- `R/research_p9_v2_training.R`
- `R/research_prototype.R`
- `R/research_prototype_model_acceptance.R`
- `R/research_prototype_model_validation.R`
- `R/research_prototype_training.R`
- `R/research_raster_pilot.R`
- `R/research_raster_verification.R`
- `R/research_runtime_mirror.R`
- `R/research_scene_index.R`
- `R/research_serialization_plan.R`
- `R/research_serialization_shard.R`
- `R/research_spatial_acceptance.R`
- `R/research_training_dataset_acceptance.R`
- `R/research_training_plan.R`
- `R/retrieval_gallery.R`
- `R/retrieval_gallery_targets.R`
- `_targets_p10.R`
- `_targets_p11_living_rematerialization.R`
- `_targets_retrieval_gallery.R`
- `artifacts/targets-network-retrieval-gallery/targets-network.html`
- `blueprint/p9_v2/README.md`
- `blueprint/p9_v2/decision_log.md`
- `blueprint/p9_v2/event_ledger.md`
- `blueprint/p9_v2/failure_taxonomy.md`
- `blueprint/p9_v2/finalization_acceptance_resolver.md`
- `blueprint/p9_v2/legacy_migration.md`
- `blueprint/p9_v2/p9_a_selection_plan.json`
- `blueprint/p9_v2/risk_register.md`
- `blueprint/p9_v2/roadmap.md`
- `blueprint/p9_v2/run_bundle.md`
- `blueprint/p9_v2/schemas/acceptance.schema.json`
- `blueprint/p9_v2/schemas/finalization_result.schema.json`
- `blueprint/p9_v2/schemas/run_bundle.schema.json`
- `blueprint/p9_v2/schemas/validation_checkpoint_event.schema.json`
- `blueprint/p9_v2/state_model.md`
- `blueprint/p9_v2/v1_inventory.md`
- `config/augmentation.yml`
- `config/dataloader_smoke.yml`
- `config/dissertation_authority_refresh.json`
- `config/distributed_training.yml`
- `config/full_membership_authorization.yml`
- `config/full_membership_plan.yml`
- `config/full_membership_plan_runtime.yml`
- `config/full_training_sampler.yml`
- `config/joint_model.yml`
- `config/learning_rate_diagnostic.yml`
- `config/model_architecture.yml`
- `config/p10_evaluation_historical.yml`
- `config/p11_downstream_preprocessing_v2.yml`
- `config/p11_living_population_source_contract_v2.json`
- `config/p11_methodology_decision_v2.json`
- `config/p7_cold_path_runtime.yml`
- `config/p8_formal_experiment_plan.yml`
- `config/p8_refactor_replay.yml`
- `config/p9_formal_authorization.yml`
- `config/p9_formal_isolated_publication.yml`
- `config/p9_formal_isolated_runtime.yml`
- `config/p9_formal_reauthorization.yml`
- `config/p9_global_batch_sampler_contract.json`
- `config/p9_infrastructure.yml`
- `config/p9_selected_fm_confirmation_matrix.json`
- `config/p9_v2_training_controller.yml`
- `config/prototype_model_acceptance.yml`
- `config/prototype_model_validation.yml`
- `config/prototype_training.yml`
- `config/retrieval_gallery.yml`
- `config/runtime_mirror.yml`
- `config/scene_construction.yml`
- `config/schemas/dissertation_authority_refresh.schema.json`
- `config/schemas/full_training_sampler.schema.json`
- `config/schemas/methodology_contract.schema.json`
- `config/schemas/p11_downstream_dataset_acceptance_v2.schema.json`
- `config/schemas/p11_downstream_source_contract_v2.schema.json`
- `config/schemas/p1_prototype_scene_selection.schema.json`
- `config/schemas/p7_checkpoint_manifest.schema.json`
- `config/schemas/p7_cold_path_runtime_acceptance.schema.json`
- `config/schemas/p7_cold_path_runtime_contract.schema.json`
- `config/schemas/p7_geometry_cache_manifest.schema.json`
- `config/schemas/p7_gpu_gate.schema.json`
- `config/schemas/p7_prototype_training_acceptance.schema.json`
- `config/schemas/p7_selector_result.schema.json`
- `config/schemas/p7_training_authority.schema.json`
- `config/schemas/p7_training_execution.schema.json`
- `config/schemas/p7_training_trace.schema.json`
- `config/schemas/p8_a5_generic_relation_mapping_contract.schema.json`
- `config/schemas/p8_comparison_variant_materialization_template.schema.json`
- `config/schemas/p8_comparison_variant_template_matrix.schema.json`
- `config/schemas/p8_ds_raster_materialization_contract.schema.json`
- `config/schemas/p8_experiment_augmentation_bank_index.schema.json`
- `config/schemas/p8_formal_experiment_plan_acceptance.schema.json`
- `config/schemas/p8_formal_hyperparameter_experiment_plan.schema.json`
- `config/schemas/p8_hyperparameter_configuration_matrix.schema.json`
- `config/schemas/p8_methodology_compatibility.schema.json`
- `config/schemas/p9_b_selected_model_plan.schema.json`
- `config/schemas/p9_b_training_matrix.schema.json`
- `config/schemas/p9_cache_identity_contract.schema.json`
- `config/schemas/p9_cache_resource_plan.schema.json`
- `config/schemas/p9_cache_reuse_graph.schema.json`
- `config/schemas/p9_cache_shard_plan.schema.json`
- `config/schemas/p9_cfg_main_attempt_reservation.schema.json`
- `config/schemas/p9_checkpoint_manifest.schema.json`
- `config/schemas/p9_checkpoint_selection.schema.json`
- `config/schemas/p9_configuration_acceptance.schema.json`
- `config/schemas/p9_execution_record.schema.json`
- `config/schemas/p9_final_model_decision.schema.json`
- `config/schemas/p9_formal_attempt_acceptance.schema.json`
- `config/schemas/p9_formal_attempt_reservation_v2.schema.json`
- `config/schemas/p9_formal_execution_authority.schema.json`
- `config/schemas/p9_formal_execution_supersession.schema.json`
- `config/schemas/p9_formal_failed_state.schema.json`
- `config/schemas/p9_formal_resume_checkpoint.schema.json`
- `config/schemas/p9_formal_running_state.schema.json`
- `config/schemas/p9_formal_terminal_execution.schema.json`
- `config/schemas/p9_formal_training_authority.schema.json`
- `config/schemas/p9_formal_validation_event.schema.json`
- `config/schemas/p9_infrastructure_readiness.schema.json`
- `config/schemas/p9_isolated_execution_authorization_acceptance.schema.json`
- `config/schemas/p9_isolated_immutable_root_inventory.schema.json`
- `config/schemas/p9_isolated_preassigned_attempt.schema.json`
- `config/schemas/p9_production_cache_acceptance.schema.json`
- `config/schemas/p9_production_cache_build_authority.schema.json`
- `config/schemas/p9_production_startup_gate_evidence.schema.json`
- `config/schemas/p9_run.schema.json`
- `config/schemas/p9_selected_fm_confirmation_matrix.schema.json`
- `config/schemas/p9_selected_fm_decision.schema.json`
- `config/schemas/p9_training_configuration.schema.json`
- `config/schemas/p9_v2_legacy_import.schema.json`
- `config/schemas/p9_v2_migration_authority.schema.json`
- `config/schemas/p9_v2_training_pilot.schema.json`
- `config/schemas/p9_validation_history.schema.json`
- `config/schemas/prototype_augmentation_benchmark.schema.json`
- `config/schemas/prototype_dataloader_smoke.schema.json`
- `config/schemas/prototype_distributed_joint_model_smoke.schema.json`
- `config/schemas/prototype_encoder_smoke.schema.json`
- `config/schemas/prototype_joint_model_smoke.schema.json`
- `config/schemas/prototype_model_acceptance.schema.json`
- `config/schemas/prototype_model_validation.schema.json`
- `config/schemas/prototype_scientific_geometry_roundtrip.schema.json`
- `config/schemas/prototype_serialization_plan.schema.json`
- `config/schemas/prototype_serialization_shard.schema.json`
- `config/schemas/prototype_spatial_acceptance.schema.json`
- `config/schemas/prototype_training_acceptance.schema.json`
- `config/schemas/prototype_training_dataset_acceptance.schema.json`
- `config/schemas/prototype_training_plan.schema.json`
- `config/schemas/retrieval_gallery/acceptance.schema.json`
- `config/schemas/retrieval_gallery/prototype_raster_observation.schema.json`
- `config/schemas/retrieval_gallery/prototype_relation.schema.json`
- `config/schemas/retrieval_gallery/prototype_vector_observation.schema.json`
- `config/serialization_plan.yml`
- `config/serialization_plan_runtime.yml`
- `config/serialization_shard.yml`
- `config/serialization_shard_runtime.yml`
- `config/spatial_acceptance.yml`
- `config/training_dataset_acceptance.yml`
- `config/training_plan.yml`
- `python/__pycache__/accept_prototype_model.cpython-314.pyc`
- `python/__pycache__/accept_prototype_training_dataset.cpython-314.pyc`
- `python/__pycache__/benchmark_i21_input_pipeline.cpython-314.pyc`
- `python/__pycache__/compute_scene_dem_statistics.cpython-314.pyc`
- `python/__pycache__/ddp_nccl_transport_preflight.cpython-314.pyc`
- `python/__pycache__/extract_spatial_codebooks.cpython-314.pyc`
- `python/__pycache__/prototype_augmentation.cpython-314.pyc`
- `python/__pycache__/prototype_dataloader.cpython-314.pyc`
- `python/__pycache__/prototype_ddp_exact_probe.cpython-314.pyc`
- `python/__pycache__/prototype_ddp_joint_model.cpython-314.pyc`
- `python/__pycache__/prototype_ddp_joint_objective_smoke.cpython-314.pyc`
- `python/__pycache__/prototype_ddp_optimizer_smoke.cpython-314.pyc`
- `python/__pycache__/prototype_encoder.cpython-314.pyc`
- `python/__pycache__/prototype_encoder_smoke_impl.cpython-314.pyc`
- `python/__pycache__/prototype_joint_model.cpython-314.pyc`
- `python/__pycache__/prototype_joint_model_smoke_impl.cpython-314.pyc`
- `python/__pycache__/prototype_sparse_reconstruction_smoke.cpython-314.pyc`
- `python/__pycache__/prototype_training_data.cpython-314.pyc`
- `python/__pycache__/prototype_training_runtime.cpython-314.pyc`
- `python/__pycache__/prototype_training_runtime_mirror.cpython-314.pyc`
- `python/__pycache__/prototype_validation.cpython-314.pyc`
- `python/__pycache__/recover_prototype_training_acceptance.cpython-314.pyc`
- `python/__pycache__/rotating_padding_sampler.cpython-314.pyc`
- `python/__pycache__/run_prototype_augmentation_benchmark.cpython-314.pyc`
- `python/__pycache__/run_prototype_dataloader_smoke.cpython-314.pyc`
- `python/__pycache__/run_prototype_ddp_joint_smoke.cpython-314.pyc`
- `python/__pycache__/run_prototype_encoder_smoke.cpython-314.pyc`
- `python/__pycache__/run_prototype_joint_model_smoke.cpython-314.pyc`
- `python/__pycache__/run_prototype_model_validation.cpython-314.pyc`
- `python/__pycache__/run_prototype_model_validation_locked.cpython-314.pyc`
- `python/__pycache__/run_prototype_training.cpython-314.pyc`
- `python/__pycache__/run_prototype_training_ddp.cpython-314.pyc`
- `python/__pycache__/run_prototype_training_ddp_locked.cpython-314.pyc`
- `python/__pycache__/run_prototype_training_locked.cpython-314.pyc`
- `python/__pycache__/run_scientific_geometry_roundtrip.cpython-314.pyc`
- `python/__pycache__/serialize_prototype_shard.cpython-314.pyc`
- `python/__pycache__/validate_prototype_checkpoint.cpython-314.pyc`
- `python/__pycache__/validate_prototype_serialization_shards.cpython-314.pyc`
- `python/__pycache__/write_geoparquet.cpython-314.pyc`
- `python/__pycache__/write_raster_zarr.cpython-314.pyc`
- `python/accept_prototype_model.py`
- `python/accept_prototype_training_dataset.py`
- `python/p10_completion_audit.py`
- `python/p7_cold_path_runtime.py`
- `python/p8_experiment_plan.py`
- `python/p8_plan_replay.py`
- `python/p9_a_campaign.py`
- `python/p9_b_campaign.py`
- `python/p9_checkpoint_recovery.py`
- `python/p9_data.py`
- `python/p9_final_model_selection.py`
- `python/p9_formal_authorization.py`
- `python/p9_formal_execution.py`
- `python/p9_formal_isolated_authorization.py`
- `python/p9_formal_reauthorization.py`
- `python/p9_infrastructure.py`
- `python/p9_p10_results_report.py`
- `python/p9_recovery_transaction.py`
- `python/p9_selected_fm_campaign.py`
- `python/p9_v2_historical_acceptance.py`
- `python/p9_v2_legacy_import.py`
- `python/p9_v2_schema.py`
- `python/p9_v2_training_pilot.py`
- `python/prototype_ddp_exact_probe.py`
- `python/prototype_ddp_joint_model.py`
- `python/prototype_ddp_joint_objective_smoke.py`
- `python/prototype_ddp_optimizer_smoke.py`
- `python/prototype_encoder_smoke_impl.py`
- `python/prototype_joint_model.py`
- `python/prototype_joint_model_smoke_impl.py`
- `python/prototype_sparse_reconstruction_smoke.py`
- `python/prototype_training_data.py`
- `python/prototype_training_runtime.py`
- `python/prototype_training_runtime_mirror.py`
- `python/prototype_validation.py`
- `python/recover_prototype_training_acceptance.py`
- `python/retrieval_gallery_gpu.py`
- `python/retrieval_gallery_inputs.py`
- `python/retrieval_gallery_pipeline.py`
- `python/retrieval_gallery_ranking.py`
- `python/run_prototype_augmentation_benchmark.py`
- `python/run_prototype_dataloader_smoke.py`
- `python/run_prototype_ddp_joint_smoke.py`
- `python/run_prototype_encoder_smoke.py`
- `python/run_prototype_joint_model_smoke.py`
- `python/run_prototype_model_validation.py`
- `python/run_prototype_model_validation_locked.py`
- `python/run_prototype_training.py`
- `python/run_prototype_training_ddp.py`
- `python/run_prototype_training_ddp_locked.py`
- `python/run_prototype_training_locked.py`
- `python/run_scientific_geometry_roundtrip.py`
- `python/serialize_prototype_shard.py`
- `python/validate_prototype_checkpoint.py`
- `python/validate_prototype_serialization_shards.py`
- `scripts/__pycache__/prepare_runtime_mirror.cpython-314.pyc`
- `scripts/__pycache__/sqlite_subset.cpython-314.pyc`
- `scripts/audit_prototype_relation.R`
- `scripts/benchmark_prototype_membership.R`
- `scripts/benchmark_prototype_observation.R`
- `scripts/diagnostics/__pycache__/audit_i21_validation_saturation.cpython-314.pyc`
- `scripts/diagnostics/__pycache__/benchmark_i21_input_pipeline.cpython-314.pyc`
- `scripts/diagnostics/__pycache__/diagnose_i21_learning_rate.cpython-314.pyc`
- `scripts/diagnostics/__pycache__/summarize_i21_learning_rate.cpython-314.pyc`
- `scripts/diagnostics/__pycache__/validate_i19_full_parity.cpython-314.pyc`
- `scripts/diagnostics/audit_i21_validation_saturation.py`
- `scripts/diagnostics/benchmark_i21_input_pipeline.py`
- `scripts/diagnostics/diagnose_i21_learning_rate.py`
- `scripts/diagnostics/summarize_i21_learning_rate.py`
- `scripts/diagnostics/validate_i12_full_parity.R`
- `scripts/diagnostics/validate_i19_full_parity.py`
- `scripts/p10_completion_audit.py`
- `scripts/p10_prepared_input_pilot.py`
- `scripts/p11_living_population_rematerialization.R`
- `scripts/p7_cold_path_runtime_cli.py`
- `scripts/p7_prototype_training.py`
- `scripts/p8_formal_experiment_plan.py`
- `scripts/p9_a_campaign.py`
- `scripts/p9_b_campaign.py`
- `scripts/p9_b_family_pilot.py`
- `scripts/p9_bounded_main_pilot.py`
- `scripts/p9_final_model_selection.py`
- `scripts/p9_formal_isolated_authorization.py`
- `scripts/p9_formal_reauthorization.py`
- `scripts/p9_formal_training.py`
- `scripts/p9_infrastructure.py`
- `scripts/p9_model_family_smoke.py`
- `scripts/p9_production_cache.py`
- `scripts/p9_selected_fm_campaign.py`
- `scripts/p9_v2_intensity_role_pilot.py`
- `scripts/p9_v2_training_pilot.py`
- `scripts/p9_v2_training_remediation_pilot.py`
- `scripts/prepare_runtime_mirror.py`
- `scripts/retrieval_gallery.R`
- `scripts/retrieval_gallery_benchmark_summary.py`
- `scripts/retrieval_gallery_parity.R`
- `scripts/retrieval_gallery_pilot.py`
- `scripts/retrieval_gallery_pilot_inputs.py`
- `scripts/retrieval_gallery_pipeline.py`
- `scripts/validate_prototype_relation_determinism.R`
- `scripts/validate_prototype_relation_reference.R`
- `targets/p11_living_population_rematerialization.R`
- `targets/research_augmentation_benchmark.R`
- `targets/research_base_spatial.R`
- `targets/research_dataloader_smoke.R`
- `targets/research_distributed_joint_model_smoke.R`
- `targets/research_encoder_smoke.R`
- `targets/research_full_membership_plan.R`
- `targets/research_immutable_parent_references.R`
- `targets/research_joint_model_smoke.R`
- `targets/research_membership.R`
- `targets/research_observation.R`
- `targets/research_p7_cold_path_runtime.R`
- `targets/research_p8_experiment_plan.R`
- `targets/research_p9_checkpoint_recovery.R`
- `targets/research_p9_formal_authorization.R`
- `targets/research_p9_formal_execution.R`
- `targets/research_p9_infrastructure.R`
- `targets/research_p9_v2_training.R`
- `targets/research_prototype_model_acceptance.R`
- `targets/research_prototype_model_validation.R`
- `targets/research_prototype_training.R`
- `targets/research_raster_observation.R`
- `targets/research_relation.R`
- `targets/research_serialization_plan.R`
- `targets/research_serialization_shard.R`
- `targets/research_spatial_acceptance.R`
- `targets/research_training_dataset_acceptance.R`
- `targets/research_training_plan.R`
- `targets/retrieval_gallery_targets.R`
- `tests/fixtures/batch_e_target_protection.json`
- `tests/python/__pycache__/test_accept_prototype_training_dataset.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_i21_input_pipeline.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_i21_input_pipeline.cpython-314.pyc`
- `tests/python/__pycache__/test_i21_terminal_resume.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_i21_terminal_resume.cpython-314.pyc`
- `tests/python/__pycache__/test_prototype_augmentation.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_prototype_dataloader.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_prototype_dataloader.cpython-314.pyc`
- `tests/python/__pycache__/test_prototype_encoder.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_prototype_model_acceptance.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_prototype_model_validation.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_prototype_training_runtime_mirror.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_prototype_training_runtime_mirror.cpython-314.pyc`
- `tests/python/__pycache__/test_prototype_validation.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_recover_prototype_training_acceptance.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_recover_prototype_training_acceptance.cpython-314.pyc`
- `tests/python/__pycache__/test_rotating_padding_sampler.cpython-314-pytest-7.4.4.pyc`
- `tests/python/__pycache__/test_rotating_padding_sampler.cpython-314.pyc`
- `tests/python/__pycache__/test_serialize_prototype_shard.cpython-314-pytest-7.4.4.pyc`
- `tests/python/emit_selected_host_parity.py`
- `tests/python/test_accept_prototype_training_dataset.py`
- `tests/python/test_dissertation_authority_refresh.py`
- `tests/python/test_i21_input_pipeline.py`
- `tests/python/test_i21_terminal_resume.py`
- `tests/python/test_p10_completion_audit.py`
- `tests/python/test_p11_diagnostic_probes.py`
- `tests/python/test_p11_spatial_readiness.py`
- `tests/python/test_p11_spatial_ridge.py`
- `tests/python/test_p8_plan_replay.py`
- `tests/python/test_p9_a_campaign.py`
- `tests/python/test_p9_b_campaign.py`
- `tests/python/test_p9_checkpoint_recovery.py`
- `tests/python/test_p9_ds_raster_cache.py`
- `tests/python/test_p9_final_model_selection.py`
- `tests/python/test_p9_formal_bootstrap_correction.py`
- `tests/python/test_p9_formal_execution.py`
- `tests/python/test_p9_formal_isolated_authorization.py`
- `tests/python/test_p9_p10_results_report.py`
- `tests/python/test_p9_recovery_hard_crash.py`
- `tests/python/test_p9_selected_fm_campaign.py`
- `tests/python/test_p9_v1_retirement.py`
- `tests/python/test_p9_v2_historical_acceptance.py`
- `tests/python/test_p9_v2_legacy_import.py`
- `tests/python/test_p9_v2_prepared_cache.py`
- `tests/python/test_p9_v2_training_remediation.py`
- `tests/python/test_p9_v2_training_variants.py`
- `tests/python/test_prototype_augmentation.py`
- `tests/python/test_prototype_dataloader.py`
- `tests/python/test_prototype_encoder.py`
- `tests/python/test_prototype_model_acceptance.py`
- `tests/python/test_prototype_model_validation.py`
- `tests/python/test_prototype_training_runtime_mirror.py`
- `tests/python/test_prototype_validation.py`
- `tests/python/test_recover_prototype_training_acceptance.py`
- `tests/python/test_retrieval_gallery_browser.py`
- `tests/python/test_retrieval_gallery_pilot.py`
- `tests/python/test_retrieval_gallery_pipeline.py`
- `tests/python/test_retrieval_gallery_ranking.py`
- `tests/python/test_retrieval_inspector.py`
- `tests/python/test_retrieval_inspector_current.py`
- `tests/python/test_retrieval_inspector_presentation.py`
- `tests/python/test_serialize_prototype_shard.py`
- `tests/test_p7_cold_path_runtime.py`
- `tests/test_p8_experiment_plan.py`
- `tests/test_p9_formal_authorization.py`
- `tests/test_p9_infrastructure.py`
- `tests/testthat/test-dynamic-branch-recovery.R`
- `tests/testthat/test-full-membership-plan.R`
- `tests/testthat/test-i16-immutable-reuse.R`
- `tests/testthat/test-immutable-parent-references.R`
- `tests/testthat/test-metadata-recovery.R`
- `tests/testthat/test-moderate-refactor-protection.R`
- `tests/testthat/test-p11-diagnostic-probes-targets.R`
- `tests/testthat/test-p11-living-population-rematerialization.R`
- `tests/testthat/test-p11-target-sources.R`
- `tests/testthat/test-p7-cold-path-runtime.R`
- `tests/testthat/test-p7-deterministic-training.R`
- `tests/testthat/test-p8-experiment-plan.R`
- `tests/testthat/test-p9-formal-authorization.R`
- `tests/testthat/test-p9-formal-execution.R`
- `tests/testthat/test-p9-formal-isolated-pipeline.R`
- `tests/testthat/test-p9-infrastructure.R`
- `tests/testthat/test-p9-v2-training-targets.R`
- `tests/testthat/test-prototype-augmentation-benchmark.R`
- `tests/testthat/test-prototype-dataloader-smoke.R`
- `tests/testthat/test-prototype-encoder-smoke.R`
- `tests/testthat/test-prototype-membership.R`
- `tests/testthat/test-prototype-model-acceptance.R`
- `tests/testthat/test-prototype-model-validation.R`
- `tests/testthat/test-prototype-raster-observation.R`
- `tests/testthat/test-prototype-relation.R`
- `tests/testthat/test-prototype-serialization-plan.R`
- `tests/testthat/test-prototype-serialization-shard.R`
- `tests/testthat/test-prototype-spatial-acceptance.R`
- `tests/testthat/test-prototype-training-acceptance-recovery.R`
- `tests/testthat/test-prototype-training-dataset-acceptance.R`
- `tests/testthat/test-prototype-training-plan.R`
- `tests/testthat/test-prototype-vector-observation.R`
- `tests/testthat/test-retrieval-gallery.R`
- `tests/testthat/test-runtime-mirror.R`
- `tests/testthat/test-validated-shard-contraction.R`
- `tools/render_retrieval_inspector.py`
- `tools/retrieval_inspector/README.md`
- `tools/retrieval_inspector/__init__.py`
- `tools/retrieval_inspector/app.js`
- `tools/retrieval_inspector/artifacts.py`
- `tools/retrieval_inspector/browser_validation.py`
- `tools/retrieval_inspector/example_output.json`
- `tools/retrieval_inspector/index.html`
- `tools/retrieval_inspector/inspector.py`
- `tools/retrieval_inspector/presentation.py`
- `tools/retrieval_inspector/style.css`
- `tools/retrieval_inspector/supplemental_output.json`
- `tools/targets-network/retrieval_gallery_phases.yml`
- `tools/verify_p6_geometry_layout_v3.py`

## Complete rename map

- `R/research_fixed_augmentation_banks.R` -> `R/augmentation.R` (R093)
- `R/research_canonical_config.R` -> `R/canonical_config.R` (R100)
- `R/research_methodology_current.R` -> `R/current_methodology.R` (R070)
- `R/p11_downstream_preprocessing.R` -> `R/downstream_preprocessing.R` (R098)
- `R/p11_target_sources.R` -> `R/downstream_sources.R` (R083)
- `R/p10_evaluation_targets.R` -> `R/evaluation_targets.R` (R082)
- `R/research_fixed_queries.R` -> `R/fixed_queries.R` (R096)
- `R/research_immutable_parent_references.R` -> `R/immutable_inputs.R` (R100)
- `R/research_model_dataloader.R` -> `R/model_inputs.R` (R089)
- `R/research_raster_observation.R` -> `R/raster_observations.R` (R097)
- `R/research_original_scene_cache.R` -> `R/scene_cache.R` (R092)
- `R/research_scene_index_reduced.R` -> `R/scene_index.R` (R088)
- `R/research_base_spatial.R` -> `R/spatial_observations.R` (R091)
- `R/research_relation_tiered_execution.R` -> `R/spatial_relation_execution.R` (R100)
- `R/research_relation.R` -> `R/spatial_relations.R` (R088)
- `R/research_observation.R` -> `R/vector_observations.R` (R057)
- `_targets_p11_diagnostics.R` -> `_targets_s11_diagnostics.R` (R057)
- `_targets_p11_preprocessing.R` -> `_targets_s11_downstream.R` (R056)
- `_targets_p11_spatial_readiness.R` -> `_targets_s11_readiness.R` (R057)
- `_targets_p11_ridge.R` -> `_targets_s11_ridge.R` (R058)
- `_targets_p9_v2_training.R` -> `_targets_training.R` (R058)
- `config/p10_evaluation.yml` -> `config/evaluation.yml` (R084)
- `config/p6_model_dataloader.yml` -> `config/model_inputs.yml` (R098)
- `config/schemas/p10_evaluation.schema.json` -> `config/schemas/evaluation.schema.json` (R098)
- `config/schemas/prototype_membership.schema.json` -> `config/schemas/membership_branch.schema.json` (R088)
- `config/schemas/prototype_raster_observation.schema.json` -> `config/schemas/raster_observation_branch.schema.json` (R093)
- `config/schemas/prototype_relation.schema.json` -> `config/schemas/relation_branch.schema.json` (R095)
- `config/schemas/p7_deterministic_training_supplement.schema.json` -> `config/schemas/training.schema.json` (R085)
- `config/schemas/p9_v2_acceptance.schema.json` -> `config/schemas/training_acceptance.schema.json` (R093)
- `config/schemas/p9_v2_acceptance_eligibility.schema.json` -> `config/schemas/training_acceptance_eligibility.schema.json` (R089)
- `config/schemas/p9_v2_bundle_inventory.schema.json` -> `config/schemas/training_bundle_inventory.schema.json` (R089)
- `config/schemas/p9_v2_checkpoint_commit.schema.json` -> `config/schemas/training_checkpoint_commit.schema.json` (R090)
- `config/schemas/p9_v2_event.schema.json` -> `config/schemas/training_event.schema.json` (R098)
- `config/schemas/p9_v2_finalization_result.schema.json` -> `config/schemas/training_finalization_result.schema.json` (R097)
- `config/schemas/p9_v2_immutable_locator.schema.json` -> `config/schemas/training_immutable_locator.schema.json` (R094)
- `config/schemas/p9_v2_ledger_header.schema.json` -> `config/schemas/training_ledger_header.schema.json` (R090)
- `config/schemas/p9_v2_ledger_manifest.schema.json` -> `config/schemas/training_ledger_manifest.schema.json` (R093)
- `config/schemas/p9_v2_run_bundle_manifest.schema.json` -> `config/schemas/training_run_bundle_manifest.schema.json` (R097)
- `config/schemas/p9_v2_selection_contract.schema.json` -> `config/schemas/training_selection_contract.schema.json` (R091)
- `config/schemas/p9_v2_tail_cache.schema.json` -> `config/schemas/training_tail_cache.schema.json` (R084)
- `config/schemas/p9_v2_training_authority.schema.json` -> `config/schemas/training_training_authority.schema.json` (R060)
- `config/schemas/p9_v2_worker_ipc.schema.json` -> `config/schemas/training_worker_ipc.schema.json` (R096)
- `config/schemas/prototype_vector_observation.schema.json` -> `config/schemas/vector_observation_branch.schema.json` (R090)
- `config/p7_deterministic_training.yml` -> `config/training.yml` (R085)
- `python/p9_v2_canonical.py` -> `python/artifact_protocol.py` (R100)
- `python/p4_fixed_augmentation.py` -> `python/augmentation_bank.py` (R099)
- `python/p4_deterministic_rng.py` -> `python/augmentation_rng.py` (R100)
- `python/p9_v2_downstream.py` -> `python/checkpoint_resolution.py` (R085)
- `python/p11_diagnostic_probes.py` -> `python/downstream_diagnostics.py` (R097)
- `python/p11_spatial_readiness.py` -> `python/downstream_readiness.py` (R091)
- `python/p10_evaluation.py` -> `python/evaluation.py` (R092)
- `python/p10_prepared_input.py` -> `python/evaluation_inputs.py` (R096)
- `python/p5_fixed_queries.py` -> `python/fixed_queries.py` (R099)
- `python/p6_data.py` -> `python/model_data.py` (R096)
- `python/p9_model_families.py` -> `python/model_families.py` (R091)
- `python/requirements-p10.txt` -> `python/requirements-evaluation.txt` (R100)
- `python/prototype_augmentation.py` -> `python/scene_augmentation.py` (R100)
- `python/prototype_dataloader.py` -> `python/scene_dataloader.py` (R100)
- `python/prototype_encoder.py` -> `python/scene_encoder.py` (R099)
- `python/p6_model.py` -> `python/scene_model.py` (R099)
- `python/p11_spatial_ridge.py` -> `python/spatial_ridge.py` (R089)
- `python/p9_v2_acceptance.py` -> `python/training_acceptance.py` (R091)
- `python/p9_v2_bundle.py` -> `python/training_bundle.py` (R091)
- `python/p9_v2_training_controller.py` -> `python/training_controller.py` (R091)
- `python/p9_v2_finalization.py` -> `python/training_finalization.py` (R096)
- `python/p7_geometry_cache.py` -> `python/training_geometry_cache.py` (R098)
- `python/p9_identity_diagnostics.py` -> `python/training_identity.py` (R100)
- `python/p9_v2_ledger.py` -> `python/training_ledger.py` (R090)
- `python/p9_v2_training_lifecycle.py` -> `python/training_lifecycle.py` (R086)
- `python/p9_v2_prepared_cache.py` -> `python/training_prepared_cache.py` (R094)
- `python/p9_v2_replay.py` -> `python/training_replay.py` (R099)
- `python/p7_training.py` -> `python/training_support.py` (R065)
- `python/p9_v2_training_worker.py` -> `python/training_worker.py` (R094)
- `scripts/p4_aggregate_bank.py` -> `scripts/aggregate_augmentation_bank.py` (R100)
- `scripts/p4_v2_pilot.py` -> `scripts/augmentation_pilot.py` (R097)
- `scripts/p4_build_fixed_bank.py` -> `scripts/build_augmentation_bank.py` (R096)
- `scripts/p3_deterministic_tar.py` -> `scripts/build_deterministic_scene_archive.py` (R100)
- `scripts/p5_fixed_queries.py` -> `scripts/build_fixed_queries.py` (R094)
- `scripts/p6_model_dataloader.py` -> `scripts/build_model_inputs.py` (R093)
- `scripts/p2_zarr_compare.py` -> `scripts/compare_raster_zarr.py` (R100)
- `scripts/diagnostics/benchmark_i12_rann.R` -> `scripts/diagnostics/benchmark_rann.R` (R100)
- `scripts/p2_bbox_proxy_counts.py` -> `scripts/estimate_spatial_costs.py` (R100)
- `scripts/p10_evaluation.py` -> `scripts/evaluate_scene_encoder.py` (R089)
- `scripts/finalize_p2_relation_tiered.R` -> `scripts/finalize_spatial_relations.R` (R054)
- `scripts/p10_prepared_input.py` -> `scripts/prepare_evaluation_inputs.py` (R094)
- `scripts/prepare_p2_relation_tiered.R` -> `scripts/prepare_spatial_relations.R` (R071)
- `scripts/p9_v2_resolve_checkpoint.py` -> `scripts/resolve_training_checkpoint.py` (R087)
- `scripts/run_p4_tiered_bank.py` -> `scripts/run_augmentation_bank.py` (R098)
- `scripts/p11_diagnostic_probes.py` -> `scripts/run_downstream_diagnostics.py` (R097)
- `scripts/run_p5_tiered_queries.py` -> `scripts/run_fixed_queries.py` (R099)
- `scripts/run_p2_relation_branch.R` -> `scripts/run_spatial_relation_branch.R` (R098)
- `scripts/run_p2_relation_tiered.py` -> `scripts/run_spatial_relations.py` (R098)
- `scripts/p11_spatial_ridge.py` -> `scripts/run_spatial_ridge.py` (R096)
- `scripts/p4_smoke.py` -> `scripts/smoke_test_augmentation.py` (R099)
- `scripts/p9_v2_training_controller.py` -> `scripts/training_controller.py` (R083)
- `scripts/p9_v2_training_lifecycle.py` -> `scripts/training_lifecycle.py` (R082)
- `scripts/p9_v2_training_worker.py` -> `scripts/training_worker.py` (R092)
- `scripts/p4_validate_fixed_bank.py` -> `scripts/validate_augmentation_bank.py` (R100)
- `scripts/p4_v2_validate_pilot.py` -> `scripts/validate_augmentation_pilot.py` (R099)
- `scripts/p11_spatial_readiness.py` -> `scripts/validate_downstream_readiness.py` (R092)
- `scripts/p3_validate_cache.py` -> `scripts/validate_scene_cache.py` (R100)
- `targets/research_methodology_authority.R` -> `targets/s00_methodology.R` (R098)
- `targets/research_scene_index.R` -> `targets/s01_scene_index.R` (R066)
- `targets/research_original_scene_cache.R` -> `targets/s03_scene_cache.R` (R080)
- `targets/research_fixed_augmentation_banks.R` -> `targets/s04_augmentation.R` (R078)
- `targets/research_fixed_queries.R` -> `targets/s05_fixed_queries.R` (R076)
- `targets/research_model_dataloader.R` -> `targets/s06_model_inputs.R` (R062)
- `targets/p10_targets.R` -> `targets/s10_evaluation.R` (R081)
- `targets/p11_diagnostic_probes.R` -> `targets/s11_diagnostics.R` (R092)
- `targets/p11_downstream_preprocessing.R` -> `targets/s11_downstream.R` (R100)
- `targets/p11_spatial_readiness.R` -> `targets/s11_readiness.R` (R091)
- `targets/p11_spatial_ridge.R` -> `targets/s11_ridge.R` (R092)
- `tests/python/test_p9_v2_downstream.py` -> `tests/python/test_checkpoint_resolution.py` (R075)
- `tests/python/test_p11_source_contracts.py` -> `tests/python/test_downstream_sources.py` (R084)
- `tests/python/test_p10_evaluation.py` -> `tests/python/test_evaluation.py` (R082)
- `tests/python/test_p9_v2_acceptance_crash.py` -> `tests/python/test_training_acceptance_crash.py` (R094)
- `tests/python/test_p9_v2_acceptance_resolver.py` -> `tests/python/test_training_acceptance_resolver.py` (R096)
- `tests/python/test_p9_v2_canonical_schema.py` -> `tests/python/test_training_artifact_protocol.py` (R094)
- `tests/python/test_p9_v2_bundle_build_validate.py` -> `tests/python/test_training_bundle_build_validate.py` (R098)
- `tests/python/test_p9_v2_bundle_publication_corruption.py` -> `tests/python/test_training_bundle_publication_corruption.py` (R098)
- `tests/python/test_p9_v2_bundle_schema_locator.py` -> `tests/python/test_training_bundle_schema_locator.py` (R090)
- `tests/python/test_p9_v2_training_controller.py` -> `tests/python/test_training_controller.py` (R088)
- `tests/python/test_p9_v2_crash_corruption.py` -> `tests/python/test_training_crash_corruption.py` (R095)
- `tests/python/test_p9_v2_finalization.py` -> `tests/python/test_training_finalization.py` (R094)
- `tests/python/test_p9_identity_diagnostics.py` -> `tests/python/test_training_identity.py` (R061)
- `tests/python/test_p9_v2_ledger.py` -> `tests/python/test_training_ledger.py` (R096)
- `tests/python/test_p9_v2_replay.py` -> `tests/python/test_training_replay.py` (R097)
- `tests/python/test_p9_v2_synthetic_e2e.py` -> `tests/python/test_training_synthetic_e2e.py` (R094)
- `tests/python/p9_v2_bundle_test_support.py` -> `tests/python/training_bundle_test_support.py` (R097)
- `tests/python/p9_v2_c_test_support.py` -> `tests/python/training_c_test_support.py` (R095)
- `tests/python/p9_v2_ef_test_support.py` -> `tests/python/training_ef_test_support.py` (R080)
- `tests/python/p9_v2_test_support.py` -> `tests/python/training_test_support.py` (R097)
- `tests/test_p4_fixed_augmentation.py` -> `tests/test_augmentation_bank.py` (R096)
- `tests/test_p4_deterministic_rng.py` -> `tests/test_augmentation_rng.py` (R098)
- `tests/test_p5_fixed_queries.py` -> `tests/test_fixed_queries.py` (R098)
- `tests/test_p9_model_families.py` -> `tests/test_model_families.py` (R072)
- `tests/test_p6_model_dataloader.py` -> `tests/test_model_inputs.py` (R097)
- `tests/test_p7_geometry_cache.py` -> `tests/test_training_geometry_cache.py` (R096)
- `tests/test_p7_training.py` -> `tests/test_training_support.py` (R080)
- `tests/testthat/test-p4-fixed-augmentation-banks.R` -> `tests/testthat/test-augmentation.R` (R090)
- `tests/testthat/test-p0-current-methodology.R` -> `tests/testthat/test-current-methodology.R` (R100)
- `tests/testthat/test-p11-downstream-preprocessing.R` -> `tests/testthat/test-downstream-preprocessing.R` (R097)
- `tests/testthat/test-p11-spatial-readiness-targets.R` -> `tests/testthat/test-downstream-readiness.R` (R075)
- `tests/testthat/test-p10-evaluation-targets.R` -> `tests/testthat/test-evaluation-targets.R` (R067)
- `tests/testthat/test-p5-fixed-queries.R` -> `tests/testthat/test-fixed-queries.R` (R094)
- `tests/testthat/test-p0-methodology-authority.R` -> `tests/testthat/test-methodology-authority.R` (R087)
- `tests/testthat/test-p6-model-dataloader.R` -> `tests/testthat/test-model-inputs.R` (R092)
- `tests/testthat/test-p3-original-scene-cache.R` -> `tests/testthat/test-scene-cache.R` (R092)
- `tests/testthat/test-research-scene-index.R` -> `tests/testthat/test-scene-index-support.R` (R085)
- `tests/testthat/test-p1-scene-index.R` -> `tests/testthat/test-scene-index.R` (R091)
- `tests/testthat/test-p2-base-spatial.R` -> `tests/testthat/test-spatial-observations.R` (R093)
- `tests/testthat/test-p11-spatial-ridge-targets.R` -> `tests/testthat/test-spatial-ridge.R` (R078)
- `tests/testthat/test-p9-v1-retirement.R` -> `tests/testthat/test-training-retirement.R` (R071)

## Merge and split map

- `_targets.R` and `tests/testthat/helper-study-pipeline.R` source lists -> `R/current_source_registry.R`.
- Historical methodology base plus current overrides -> self-contained `R/current_methodology.R`.
- `R/research_base_spatial.R` responsibilities -> `R/spatial_membership.R`, `R/vector_observations.R`, `R/raster_observations.R`, `R/spatial_relations.R`, `R/spatial_observations.R`, and `R/spatial_relation_execution.R`.
- P7/P9 identity logic -> `python/training_identity.py`; obsolete diagnostics removed.
- Selected-FM resolver -> `python/checkpoint_resolution.py`; campaign execution removed.
- P9-v2 current lifecycle -> neutral `python/training_*.py`; legacy import/campaign/v1 code removed.
- P10/P11 helpers -> `R/evaluation_targets.R`, `R/downstream_*.R`, and neutral Python/script names.

## Tests removed, rewritten, and renamed

Obsolete implementation tests were deleted with their source closures. Current methodology, stage contracts, training lifecycle, checkpoint resolution, downstream sources, and retirement guards were retained or rewritten. All test-file renames are included in the complete rename map above. New focused tests include `tests/python/test_training_retirement.py`, `tests/python/test_downstream_contracts.py`, `tests/testthat/test-downstream-sources.R`, and current responsibility-named stage tests.

## Final verdict

- `PASS_WITH_INTENTIONAL_HISTORICAL_GUARDS`
