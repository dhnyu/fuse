# Current Dissertation Methodology Contract Migration

## Executive summary

- Status: **PASS_WITH_HISTORICAL_RECOMPUTE_REQUIRED**.
- Executed at: 2026-09-08 03:17 KST (Asia/Seoul).
- Dissertation scientific authority: `reduced` at `cbb824f19be8355296603f8426ac241ce587ddcc`.
- Fuse input: `reduced` at `76704e8450f9961a70b2fd0075c816a3b6d7b675`.
- Fuse implementation head before the report/test-evidence commit: `052b5b617d38ea7c7cde3f08c4ae8f6202f1d6b0`.
- Both repositories were clean and synchronized with `origin/reduced` at preflight. The dissertation repository remained unmodified throughout.
- The migration replaces the superseded scientific contract rather than preserving it through compatibility aliases. Historical publications remain immutable and are explicitly ineligible as current results where ancestry or scientific identity differs.
- No production preprocessing, target pipeline execution, model training, evaluation, retrieval, augmentation-bank generation, or downstream computation was run.

## Scope and evidence

The review resolved the import closure needed for `template/main.typ` and read the current model and training chapters, all five methodology sections, experimental setup, hyperparameter study, relevant imported tables, and included appendices A and B. Generated bibliography inputs and the pinned external `xarrow` package are recorded as non-scientific dependencies and do not block semantic extraction or determine scientific hashes.

The implementation audit covered P0 authority/config/schemas, hard-coded scientific inventories, P1 scene counts, P2-P7 ancestry and model/training contracts, P8 plan generation, P9 model families and training, P10 evaluation, P11 consumers, tests, target declarations, schemas, and blueprints.

## Old-vs-new scientific contract matrix

| Area | Superseded implementation contract | Current dissertation contract | Migration verdict |
|---|---|---|---|
| Off-grid scenes | 400 validation + 1,600 evaluation | 1,000 validation + 9,000 evaluation = 10,000 | RECOMPUTE_REQUIRED |
| Training lattice | Official 500 m centers and 50 m off-grid exclusion | Same | REUSABLE_EXACT at rule level |
| Entities/relations | B/R/P and SN/CNT/WIT/INT/CON | Same base predicates | REVALIDATE_ONLY |
| Original serialization | Deterministic Serialization-v3 | Same serialization semantics | REVALIDATE_ONLY after new population |
| Main representation | `d=d_c=64` in accepted lineage | `d=d_c=128` | RECOMPUTE_REQUIRED |
| Objective | Contrastive + information-preservation loss | Symmetric scene contrastive only | RECOMPUTE_REQUIRED |
| Reconstruction | Modality reconstruction decoders and IP parameters | Subsystem absent | RECOMPUTE_REQUIRED |
| OFAT | Six axes / 13 configurations, including IP | Five axes / 11 unique configurations | RECOMPUTE_REQUIRED |
| A1-A5 | Historical component meanings | Current nested component definitions | RECOMPUTE_REQUIRED |
| B1-B9 | No closed formal source-ablation set | Nine input-level retained-source contracts | RECOMPUTE_REQUIRED |
| Compared models | Eight accepted configurations | FM + A1-A5 + B1-B9 + SSV + DS = 17 | RECOMPUTE_REQUIRED |
| Evaluation | Historical 400/1,600 split | 1,000/9,000 split | RECOMPUTE_REQUIRED |
| Downstream | Historical P10 embeddings | Methods unchanged, inputs superseded | HISTORICAL_ONLY pending new P10 |

## P0 methodology authority changes

P0 now uses stable exact-one semantic block selectors and structured canonical contracts. Line movement changes source provenance but not scientific identity; a changed resolved field changes the appropriate module hash. Absolute line ranges are rejected. Scalar and file-vector inputs are normalized explicitly. Declared generated bibliography paths and non-scientific external Typst imports are recorded without being required to extract methodology.

The new immutable publication is:

- Authority ID: `mta_03e8d7f42fe2018237f3fcde`
- Authority path: `/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/authority/mta_03e8d7f42fe2018237f3fcde/reduced_methodology_authority.json`
- Authority SHA-256: `766e5b0e99f2342c19b477c8e5905124defeeccc9d7cf562640fe1b34f4994b2`
- Aggregate scientific hash: `45c7d018a8d6b959e30a9b8ca5c5279c2fe9177f397dd9b5e872e12a434fd5e8`
- Supersedes: `mta_f90fecff7bc7bb5d231cc79f` at dissertation commit `e66d17d65e97a5e3f50fa9a111a51559db05666f`

| Module | Current contract ID | Compatibility |
|---|---|---|
| scene | `mmc_a19149eea4f42a21` | changed |
| base spatial | `mmc_b75dcec66fe442fc` | unchanged scientific contract |
| original cache | `mmc_1989e1225beeb5f2` | unchanged scientific contract |
| augmentation | `mmc_048c824b82a8f75f` | revalidate canonical contract |
| model | `mmc_bb88e9fa8e10da65` | changed |
| training | `mmc_1cf3f3d37e489d9a` | changed |
| evaluation | `mmc_19e310bdf0496666` | changed |
| downstream | `mmc_49096d351f1d00d2` | unchanged method, changed upstream lineage |
| hyperparameter study | `mmc_cbfe6b31c1144f49` | new/changed |
| comparison | `mmc_06d2776ffecbf814` | new/changed |

The predecessor was not overwritten. The supersession record defaults incompatible descendants to historical-only unless explicit parity is proven.

## Current model and objective

The main model has `d=128`, `d_c=128`, four attention heads, 32 dimensions per head, and a 256-dimensional FFN hidden layer. Modality masking, momentum encoder, EMA, FIFO queue, and the contrastive projection head remain. Current P6/P7/P9 construction has no reconstruction decoders or active information-preservation loss/configuration. Training updates optimize only the symmetric scene-level contrastive loss.

## A1-A5 component contracts

| Model | Active modalities | Fusion | Relations | Scene raster |
|---|---|---|---|---|
| A1 | relative position | no | none | no |
| A2 | relative + intrinsic geometry | type-aware | none | no |
| A3 | relative + geometry + semantics + object environmental context | type-aware | none | no |
| A4 | same as A3 | type-aware | generic label over exactly FM's directed edge instances; direction and multiplicity preserved | no |
| A5 | same as A4 | type-aware | heterogeneous SN/CNT/WIT/INT/CON identities | no |
| FM | same as A5 | type-aware | heterogeneous | yes |

The resulting contrasts are A2-A1 geometry, A3-A2 semantics plus object environment, A4-A3 contextualization, A5-A4 relation identity, and FM-A5 scene raster.

## B1-B9 source contracts

| Model | Retained sources |
|---|---|
| B1 | B, R, P |
| B2 | B, R |
| B3 | B, P |
| B4 | R, P |
| B5 | B |
| B6 | R |
| B7 | P |
| B8 | B, R, P, LC |
| B9 | B, R, P, DEM |

Source selection is represented by one canonical retained-source set. Entity removal deletes excluded entity rows and derived modalities, and relation filtering takes the induced subgraph without inventing edges. Raster/environment pathways derive from the retained LC/DEM subset, including LC-only and DEM-only behavior. Fusion normalizes only over active modalities.

## Seventeen-model comparison matrix

The exact ordered closed set is:

`FM, A1, A2, A3, A4, A5, B1, B2, B3, B4, B5, B6, B7, B8, B9, SSV, DS`.

SSV and DS retain the current dissertation definitions. Neither includes an IP objective. P9/P10 fail closed with `RECOMPUTE_REQUIRED` until compatible P1-P8 inputs and trained model acceptances exist.

## Eleven-configuration OFAT matrix

The shared main row is `(d, K_aug, intensity, mu_EMA, eta) = (128, 8, 1.0, 0.999, 0.001)`. Each non-main candidate varies exactly one axis:

| ID | d | K_aug | intensity | EMA | peak LR |
|---|---:|---:|---:|---:|---:|
| main | 128 | 8 | 1.0 | 0.999 | 0.001 |
| d64 | 64 | 8 | 1.0 | 0.999 | 0.001 |
| d256 | 256 | 8 | 1.0 | 0.999 | 0.001 |
| k4 | 128 | 4 | 1.0 | 0.999 | 0.001 |
| k16 | 128 | 16 | 1.0 | 0.999 | 0.001 |
| intensity05 | 128 | 8 | 0.5 | 0.999 | 0.001 |
| intensity20 | 128 | 8 | 2.0 | 0.999 | 0.001 |
| ema0990 | 128 | 8 | 1.0 | 0.990 | 0.001 |
| lr002 | 128 | 8 | 1.0 | 0.999 | 0.002 |
| lr003 | 128 | 8 | 1.0 | 0.999 | 0.003 |
| lr005 | 128 | 8 | 1.0 | 0.999 | 0.005 |

`d_c=d` for every dimension row. Canonical generation and schema validation prove cardinality 11, uniqueness, exact candidate sets, and one shared-main row.

## Scene split and stage reconciliation

The current contract is 10,000 off-grid scenes: 1,000 validation and 9,000 evaluation, with `D_off=50 m`. P1-P5 schemas/configuration now encode these counts, P9 full validation covers 2,000 queries and 1,000 gallery scenes, and P10 encodes 18,000 evaluation queries and 9,000 gallery scenes.

Current ancestry does not falsely adopt historical IDs. P1-P6, P9, and P10 use explicit pending/recompute states where new population-derived artifacts are absent. Historical input paths remain as lineage evidence, not current acceptance.

## Historical artifact compatibility

| Artifact family | Classification | Required action |
|---|---|---|
| 2,000-row P1 scene source/index | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | Create current 10,000-row off-grid population |
| P2 observations and relations | HISTORICAL_ONLY for current lineage | Recompute from current P1; base rules reusable |
| P3 serialized scene cache | HISTORICAL_ONLY for current lineage | Recompute/revalidate new population |
| P4 augmentation bank | HISTORICAL_ONLY for current lineage | Recompute for current population/configuration |
| P5 fixed queries | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | Regenerate 1,000/9,000 splits and queries |
| P6/P7 accepted model/training | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | Rebuild d128 decoder-free model and retrain |
| Nine-file historical P8 bundle | HISTORICAL_ONLY | Preserve bytes; generate new current plan separately |
| P9 accepted training outputs | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | Train current 11 OFAT/17 comparison contract |
| P10 evaluations | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | Evaluate current model set/populations |
| P11 analyses | HISTORICAL_ONLY | Recompute only after current P10 outputs |

`REUSABLE_EXACT` applies only to immutable files whose content and full scientific ancestry match. Rule-level equality does not authorize relabeling an artifact from a changed population or model lineage.

## Tests and validation

- R parse: PASS for 104 R/target files.
- Python AST parse: PASS for 222 Python/script/test files.
- Full R `testthat`: PASS; three explicitly historical integration cases skipped, zero failures.
- Full Python suite: 862 passed, 66 skipped.
- Post-publication focused Python suite: 130 passed, 3 skipped.
- P0 fixture publication and actual published-authority readback/parity: PASS.
- Current experiment plan fixture/schema: PASS; plan ID `s08plan_6251279e73673603ee370be2`, 11 OFAT and 17 comparisons.
- Active `tar_manifest()` and `tar_validate()`: PASS for all ten entrypoints. Counts: main 132, maintenance 1, P10 5, five P11 entrypoints 2 each, P9 v2 9, retrieval 12; total 169 static declarations.
- Main dynamic parents: 19.
- `tar_network(targets_only=TRUE, outdated=FALSE)`: PASS.
- Retired P9 formal and recovery entrypoints: expected immediate guard failure, PASS.
- Network HTML rendered from the current manifest: 132 main targets, 430 edges, two weak components, zero error nodes.
- Current-contract stale-token scan: old terms occur only in fail-closed forbidden-token validators, not as active scientific fields.

The first Python focus invocation omitted `PYTHONPATH` and stopped during import collection; rerunning the identical test selection with the repository-standard `PYTHONPATH=python:scripts` passed 130 tests. This was a test invocation issue, not an implementation failure.

## Modified files

Implementation and evidence changes comprise the following 91 paths (89 code/config/test/network paths plus two reports):

```text
R/research_fixed_queries.R
R/research_methodology_authority.R
R/research_methodology_current.R
R/research_model_dataloader.R
R/research_p8_experiment_plan.R
R/research_prototype_training.R
R/research_scene_index_reduced.R
_targets.R
artifacts/targets-network/targets-network.html
blueprint/p9_v2/README.md
blueprint/targets_implementation_blueprint.md
config/current_methodology.yml
config/p0_authority.yml
config/p10_evaluation.yml
config/p10_evaluation_historical.yml
config/p1_scene_index.yml
config/p2_base_spatial.yml
config/p3_original_scene_cache.yml
config/p5_deterministic_queries.yml
config/p6_model_dataloader.yml
config/p7_deterministic_training.yml
config/p8_formal_experiment_plan.yml
config/p9_v2_training_controller.yml
config/schemas/current_experiment_plan.schema.json
config/schemas/p0_methodology_authority.schema.json
config/schemas/p0_methodology_conflict_gate.schema.json
config/schemas/p0_methodology_git_state.schema.json
config/schemas/p0_methodology_module_contract.schema.json
config/schemas/p0_methodology_source_set.schema.json
config/schemas/p10_evaluation.schema.json
config/schemas/p1_off_grid_source.schema.json
config/schemas/p1_prototype_scene_selection.schema.json
config/schemas/p1_scene_index_acceptance.schema.json
config/schemas/p1_scene_index_manifest.schema.json
config/schemas/p1_scene_index_plan.schema.json
config/schemas/p1_study_data_inventory.schema.json
config/schemas/p2_base_spatial_acceptance.schema.json
config/schemas/p2_membership_acceptance.schema.json
config/schemas/p2_membership_plan.schema.json
config/schemas/p2_observation_plan.schema.json
config/schemas/p3_original_cache_contract.schema.json
config/schemas/p5_fixed_query_acceptance.schema.json
config/schemas/p5_fixed_query_plan.schema.json
config/schemas/p5_fixed_query_split_acceptance.schema.json
config/schemas/p6_architecture_manifest.schema.json
config/schemas/p7_deterministic_training_supplement.schema.json
python/current_methodology.py
python/p10_evaluation.py
python/p5_fixed_queries.py
python/p6_data.py
python/p6_model.py
python/p7_training.py
python/p8_experiment_plan.py
python/p9_model_families.py
python/p9_v2_training_worker.py
scripts/p6_model_dataloader.py
scripts/p7_prototype_training.py
scripts/p9_formal_training.py
scripts/p9_model_family_smoke.py
scripts/p9_v2_training_controller.py
targets/research_methodology_authority.R
targets/research_p8_experiment_plan.R
tests/python/test_dissertation_authority_refresh.py
tests/python/test_p10_completion_audit.py
tests/python/test_p10_evaluation.py
tests/python/test_p11_diagnostic_probes.py
tests/python/test_p11_spatial_readiness.py
tests/python/test_p11_spatial_ridge.py
tests/python/test_p9_formal_bootstrap_correction.py
tests/python/test_p9_formal_isolated_authorization.py
tests/python/test_p9_v2_training_controller.py
tests/test_canonical_config.py
tests/test_current_methodology.py
tests/test_p6_model_dataloader.py
tests/test_p9_model_families.py
tests/testthat/helper-study-pipeline.R
tests/testthat/test-p0-current-methodology.R
tests/testthat/test-p0-methodology-authority.R
tests/testthat/test-p1-scene-index.R
tests/testthat/test-p3-original-scene-cache.R
tests/testthat/test-p5-fixed-queries.R
tests/testthat/test-p6-model-dataloader.R
tests/testthat/test-p8-experiment-plan.R
tests/testthat/test-prototype-training-acceptance-recovery.R
tests/testthat/test-prototype-training-plan.R
tests/testthat/test-research-scene-index.R
tests/testthat/test-study-pipeline.R
tests/testthat/test-target-network.R
tools/targets-network/target_phases.yml
reports/20260908_0234_p0_current_methodology_prepublication_audit.md
reports/20260908_0317_methodology_contract_migration.md
```

## Commits and publication

Implementation commits completed before this report:

1. `5d230c680cf02d0ac165bdb8c6d8a86423982fdf` - `fix(p0): support current dissertation methodology resolution`
2. `aae48ebd3f669989f49a9b07b17b4f2611605de2` - `refactor(p0): align scientific contracts with current dissertation`
3. `052b5b617d38ea7c7cde3f08c4ae8f6202f1d6b0` - `refactor(experiments): adopt revised ablation and hyperparameter specification`

The final test/evidence commit and push result are recorded in the task completion response because a commit cannot contain its own SHA.

## Risks and remaining work

- The contract migration is complete, but current P1-P11 scientific products do not exist. The intended execution boundary begins with P1 current off-grid scene generation, followed by P2-P6, current P8 publication, P9 training, P10 evaluation, and P11 analysis.
- P9/P10 parent IDs deliberately remain pending and fail closed. They must be populated only by newly accepted current-lineage artifacts.
- Historical files retain old terms by design. They are not active final-methodology contracts and must not be used as current acceptance evidence.
- Expensive recomputation requires separate operator authorization, resource planning, pilots, and acceptance checks.

## Final verdict

**PASS_WITH_HISTORICAL_RECOMPUTE_REQUIRED.** The current dissertation has been published as a new superseding semantic authority and future implementation contracts match it. Historical scientific outputs remain immutable but cannot stand in for the new 10,000-scene, decoder-free, 11-OFAT, 17-comparison lineage.

## Input prompt summary

Treat the current dissertation `reduced` branch as scientific authority; migrate P0 and future Fuse implementation contracts to the 1,000/9,000 split, contrastive-only decoder-free model, exact 11-row OFAT, and exact 17-model comparison set; preserve historical artifacts; validate statically and with fixtures; commit and push only after all checks pass.
