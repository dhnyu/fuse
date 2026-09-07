# Targets Moderate Refactor Implementation (Batches B-D)

## 1. Purpose and scope

- Executed at: 2026-09-07T23:22:14+09:00
- Repository: `/members/dhnyu/fuse`, branch `reduced`
- Starting commit: `f04ce229a3ce94b69c95548644cf79acccec2b45`
- Inputs: `20260907_2127_targets_pipeline_audit.md`, `20260907_2200_targets_refactor_blueprint.md`, and `20260907_2222_targets_moderate_refactor_implementation.md`
- Prompt summary: implement Moderate Refactor Batches B-D, permit only equivalent incoming-edge substitutions for the 30 Batch E targets, preserve all scientific artifacts and prohibit production execution.

## 2. Before/after counts

| metric | before | after |
|---|---:|---:|
| Total static targets | 203 | 167 |
| Main `_targets.R` static targets | 154 | 130 |
| Dynamic parents | 21 | 19 |
| Linked branches | 1,794 | 1,314 |
| P4 linked branches | 576 | 288 |
| P5 linked branches | 384 | 192 |
| Protected Batch E targets | 30 | 30 |

The linked-branch result is the declared-plan projection: `1,794 - 288 - 192 = 1,314`. Existing store metadata was not renamed or imported, so new dynamic-parent branch metadata will appear only on a future authorized run.

## 3. Changed topology

- Batch B: P10 source gate/readback, retrieval scene-index/validation projections, P1 source/plan projections, P7 acceptance/runtime projections, and P4/P5 thin plan/acceptance wrappers were consolidated.
- Batch C: P3 became six targets while preserving separate serialization and independent-validation dynamic parents. P4 and P5 each expose one validated file branch that registers an existing payload, runs the independent validator, and publishes a branch-local validation receipt.
- Batch D: five P11 pipelines now expose one tracked sources bundle and one output boundary each. P9 v1 stop-only nodes were removed; retired entrypoints fail before target graph evaluation. P0 now exposes source authority, six scientific module contracts, and final authority.

## 4. Rename map

Major mappings are:

| old | new / merged boundary |
|---|---|
| `p10_source_files`, `p10_source_gate` | `s10_evaluation_sources` |
| `retrieval_gallery_authority`, `retrieval_gallery_scene_index` | `s12_gallery_authority` |
| `research_config_files`, `research_implementation_files` | `s01_study_sources` |
| `reduced_scene_index_plan`, `spatial_scene_index` | `s01_scene_index` |
| four P7 training projections | `s07_pilot_training_acceptance` |
| P7 runtime contract/acceptance | `s07_runtime_acceptance` |
| P4 shard/validation parents | `s04_bank_validated_shard` |
| P5 shard/validation parents | `s05_query_validated_shard` |
| P3 contract/plan | `s03_scene_serialization_plan` |
| P3 roundtrip/index | `s03_scene_cache_index` |
| P3 manifest/acceptance | `s03_scene_dataset_acceptance` |
| P11 family source registrations | `s11_*_sources` |
| P0 git/source/conflict projections | `s00_methodology_source_authority` |
| P0 training/downstream/final projections | `s00_methodology_authority` |

## 5. Dynamic branch contraction and QC

- `s04_bank_validated_shard`: `map(s04_bank_shard_plan)`, 288 intended branches, file-tracked payload/manifest/execution/validation receipt.
- `s05_query_validated_shard`: `map(s05_query_shard_plan)`, 192 intended branches, file-tracked payload/manifest/execution/validation receipt with branch, split, namespace, and seed checks.
- The P3 independent `s03_scene_shard_validation` parent remains. Aggregate roundtrip now consumes its results and does not invoke the validator again.
- A three-branch fixture proved retry of only the failed branch, reuse of successful branches, and all-branch invalidation after validator-config change.

## 6. Preserved artifacts and protected targets

No production artifact, accepted JSON, checkpoint, target store, config, or historical artifact was rewritten or deleted. The research store fingerprint remained `1608` entries and SHA-256 `14d8dd0992cce0643d214d4c263d6249ad93f5aebf944493c13fc47f369ecfc2`.

Batch E protection result:

- `UNCHANGED`: 26
- `UPSTREAM_SYMBOL_ONLY`: 3
- `UPSTREAM_SELECTION_ONLY`: 1
- Target names/count/primary compute helper/format/iteration/pattern: preserved
- Incoming-edge substitutions: 9
- `s01_study_sources` config and implementation subsets: exact path, basename, ordering, length, MD5, and SHA-256 equality passed
- No Batch E scientific parameter, artifact path, recovery behavior, or output contract was changed

## 7. Validation results

- Changed R parse: PASS
- Modified Python test syntax: PASS
- Relevant `testthat`: PASS
- P9 v1 Python tests: 56 passed
- Active entrypoint `tar_validate()`: 10/10 PASS
- Retired P9 formal/recovery entrypoints: expected immediate guard failure PASS
- `tar_manifest()`: total 167, main 130, duplicate names 0
- `tar_network(targets_only=TRUE, outdated=FALSE)`: 130 nodes, 426 edges, DAG PASS
- Dynamic parents: 19
- Phase assignment: all main targets mapped
- Network HTML: regenerated, 130-target manifest snapshot
- Production preprocessing/training/evaluation/retrieval/downstream execution: not run
- Production `tar_make()`/`tar_make_future()`: not run
- Fixture-only `tar_make()`: run for dynamic retry/invalidation and P11 file invalidation tests

## 8. Reproducibility risks and unresolved issues

The current dissertation repository HEAD is `989c19d98e64ec129dc53b761c58a4d961fc3983`, while `config/p0_authority.yml` remains anchored to its previously accepted commit. P0 correctly reports a fail-closed commit mismatch; this refactor did not modify the authority config or reinterpret the scientific lineage. The newer dissertation also contains Typst constructs not accepted by the current P0 resolver, which must be handled in a separate methodology-authority task.

New P4/P5 target names deliberately have no imported metadata in the existing store. Their future first authorized execution will read existing payloads and materialize only validation receipts; it will not regenerate payloads.

## 9. Exact changed files

The three batches and this implementation report changed 74 files:

```text
R/p10_evaluation_targets.R
R/p11_target_sources.R
R/research_fixed_augmentation_banks.R
R/research_fixed_queries.R
R/research_methodology_authority.R
R/research_original_scene_cache.R
R/research_p7_cold_path_runtime.R
R/research_prototype_training.R
R/research_scene_index_reduced.R
R/retrieval_gallery_targets.R
reports/20260907_2322_targets_moderate_refactor_implementation.md
_targets.R
_targets_p10.R
_targets_p11_diagnostics.R
_targets_p11_living_rematerialization.R
_targets_p11_preprocessing.R
_targets_p11_ridge.R
_targets_p11_spatial_readiness.R
_targets_p9_formal.R
_targets_p9_recovery.R
artifacts/targets-network/targets-network.html
targets/p10_targets.R
targets/p11_diagnostic_probes.R
targets/p11_downstream_preprocessing.R
targets/p11_living_population_rematerialization.R
targets/p11_spatial_readiness.R
targets/p11_spatial_ridge.R
targets/research_base_spatial.R
targets/research_fixed_augmentation_banks.R
targets/research_fixed_queries.R
targets/research_full_membership_plan.R
targets/research_membership.R
targets/research_methodology_authority.R
targets/research_model_dataloader.R
targets/research_observation.R
targets/research_original_scene_cache.R
targets/research_p7_cold_path_runtime.R
targets/research_p9_formal_authorization.R
targets/research_prototype_model_acceptance.R
targets/research_prototype_model_validation.R
targets/research_prototype_training.R
targets/research_raster_observation.R
targets/research_relation.R
targets/research_scene_index.R
targets/retrieval_gallery_targets.R
tests/fixtures/batch_e_target_protection.json
tests/python/test_p9_v1_retirement.py
tests/testthat/helper-study-pipeline.R
tests/testthat/test-dynamic-branch-recovery.R
tests/testthat/test-full-membership-plan.R
tests/testthat/test-moderate-refactor-protection.R
tests/testthat/test-p0-methodology-authority.R
tests/testthat/test-p10-evaluation-targets.R
tests/testthat/test-p11-diagnostic-probes-targets.R
tests/testthat/test-p11-spatial-readiness-targets.R
tests/testthat/test-p11-spatial-ridge-targets.R
tests/testthat/test-p11-target-sources.R
tests/testthat/test-p3-original-scene-cache.R
tests/testthat/test-p4-fixed-augmentation-banks.R
tests/testthat/test-p5-fixed-queries.R
tests/testthat/test-p6-model-dataloader.R
tests/testthat/test-p7-cold-path-runtime.R
tests/testthat/test-p7-deterministic-training.R
tests/testthat/test-p8-experiment-plan.R
tests/testthat/test-p9-formal-isolated-pipeline.R
tests/testthat/test-p9-v1-retirement.R
tests/testthat/test-prototype-model-acceptance.R
tests/testthat/test-prototype-model-validation.R
tests/testthat/test-prototype-training-acceptance-recovery.R
tests/testthat/test-prototype-training-plan.R
tests/testthat/test-research-scene-index.R
tests/testthat/test-study-pipeline.R
tests/testthat/test-validated-shard-contraction.R
tools/targets-network/target_phases.yml
```

## 10. Final verdict

PASS for the requested topology migration and static/fixture validation. Scientific production execution remains intentionally deferred. The accepted P0/dissertation commit mismatch is an explicit fail-closed follow-up, not resolved in this refactor.
