# P8 Nested Comparison Blueprint Reaudit and Republication

## Verdict

`P8_NESTED_COMPARISON_REPUBLICATION_PASS_PUSHED`

This verdict is conditional on the publication commit containing this report being pushed to `origin/reduced`; the final push SHA and synchronization result are reported in the task close-out. All scientific, schema, execution, immutability, and no-op gates were complete before publication.

## Scope and inputs

- Execution date: 2026-08-30 KST
- Fuse branch/start HEAD: `reduced`, `a49802e2c1061acbd71a60163c0faa218c3a66ec`
- Fuse implementation commit: `f3db91dec04381c9c9bc7342038d8d3f953e1c2b`
- Dissertation branch/commit: `reduced`, `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`
- P7 acceptance/best checkpoint/runtime: `p7acc_3c78cc0e85b93aec6a0cc02c`, `p7ck_7d25fec7944dc108c5849cd7`, `p7rta_c780441a553abe26772827d0`
- Superseded P8 authority/acceptance/matrix: `p8a_ced1badc5a539f3823a0fdd0`, `p8acc_6a37d2978af940d03c597511`, `p8cm_6b21d8791d82d24bf5e39ca3`

The dissertation worktree was read-only and already synchronized. No dissertation commit was created by this task.

## Methodology and blueprint audit

The updated Compared Models section defines a cumulative A1-A5 sequence. The blueprint now records the following conditional interpretations, not order-invariant main effects:

| Contrast | Conditional contribution |
|---|---|
| A2-A1 | entity semantics |
| A3-A2 | object-level environmental context |
| A4-A3 | scene-level raster context |
| A5-A4 | generic relational contextualization |
| FM-A5 | heterogeneous relation identity |
| A2-SSV | intrinsic geometry |

A5 preserves the exact FM directed edge instances, direction, multiplicity, attention/message/residual/FFN structure, and maps `SN/CNT/WIT/INT/CON` to one learnable generic relation. Radius reconstruction and edge-support changes are rejected.

DS uses a common 100 x 100 grid and `C_cat + 4` channels. The realized augmented standardized DEM is reused at 17 x 17 and resampled by cell-center bilinear interpolation to 100 x 100. Perturbation regeneration, partial valid support, nodata imputation, entity encoders, modality fusion, relational contextualization, and the IP objective are prohibited; `lambda_IP=0`.

## New publication

| Artifact | Identity |
|---|---|
| P8 authority | `p8a_3cb1c49084529987f0244a93` |
| P8 acceptance | `p8acc_c9f16a07275aadfae928d329` |
| Comparison matrix | `p8cm_cd7d0f45dd41a7c351ea4d78` |
| A5 generic relation contract | `p8a5_497d83d2e948107488b44397` |
| DS raster materialization contract | `p8ds_73137985bd6b172f6711a062` |
| Hyperparameter matrix, reused | `p8hm_f34f1666b62255babab0ae08` |
| Augmentation bank index, reused | `p8bi_2e492527089bf5ce9d00a933` |

The immutable bundle is at:

`/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_plan/p8a_3cb1c49084529987f0244a93/p8acc_c9f16a07275aadfae928d329`

## Comparison templates

| Template | Template SHA-256 |
|---|---|
| `cmp_a1_geometric_core` | `36b124e7ddef9c78518e7805c23d4b97acb561ad52cf30594c84f368fe4db29d` |
| `cmp_a2_semantic_enriched` | `2baa42fe1fa62d5d603f949e611a26905958d7a12a29918bd7783e1927304af3` |
| `cmp_a3_object_context_enriched` | `e49ed21dfa80119c68a48f71f9dac1b4bb11231881f73448e44e8f5ae5b8188a` |
| `cmp_a4_raster_complete_non_relational` | `4b650ce82b661b0f6c897be17355970299fd8302227367e7e30a8392d467c467` |
| `cmp_a5_relation_type_agnostic` | `d4a3b814cb04945b61e17aed0fa7d043f6a44ed427426f89b99be20de88002c5` |
| `cmp_ssv_like` | `c32c80baae23d14a142555e85e2232daf55d58a3a16ca8b26318211043a6a748` |
| `cmp_ds_like` | `5ccf13ccc1d585ab4504d1cad3d1b8a0c2f06ca6f62db93f3a9d0b21d2f927e1` |

SSV canonical bytes and scientific meaning were unchanged. The other six templates were reissued. All seven remain selected-FM-derived, validation-only, ineligible for hyperparameter selection, unresolved before P9-A selection, and free of evaluation ancestry.

## Byte-identical reuse

| Artifact | Identity | File/canonical SHA-256 | Result |
|---|---|---|---|
| Hyperparameter matrix | `p8hm_f34f1666b62255babab0ae08` | `3d769843aa807630eb8e108554f57adab8ee3932cdf2feb37012b6e3abc63d6e` | byte-identical |
| Augmentation bank index | `p8bi_2e492527089bf5ce9d00a933` | `93facdae8cd93ab07df8ca64d2b7b49548d7758a56f1a9cb637295754e0a3903` | byte-identical |
| SSV template payload | `c32c80baae23d14a142555e85e2232daf55d58a3a16ca8b26318211043a6a748` | canonical `cc8b6ac7d8ad3b26f5bf6436001de7ff7a72de59299242f0b4d26b69be21c738` | byte-identical |

The builder fails closed if any of these accepted bytes change.

## Plan accounting and lineage

- Hyperparameter configurations: 13
- Comparison templates: 7
- Expected P9 attempts: 20
- Main duplication: 0
- Premature comparison materialization: 0
- Evaluation ancestry: 0
- Optimizer updates/checkpoints: 0/0
- P9/P10/P11 executions: 0
- Maintenance executions: 0

Future P9 must bind `p8acc_c9f16a07275aadfae928d329` and runtime acceptance `p7rta_c780441a553abe26772827d0`. The old P8 bundle is preserved with `SUPERSEDED_PRESERVED` status and is not the new P9 parent.

## Target execution and no-op

Only `formal_experiment_plan_acceptance` was selected with store `/mnt/hdd002/dhnyu/fusedata/targets/fuse-research`.

- First execution: 11 completed, 0 skipped, 10.3 seconds.
- Repeated execution: 0 builds, 11 skipped.
- Repeated artifact path/size/mtime/SHA changes: 0.
- P8 outdated count after the repeat: 0.
- Published JSON artifacts validated against all nine actual schemas and canonical readback passed.

## Validation

- Focused Python P8: 9 passed.
- Full Python: 191 passed.
- Full R/testthat: PASS with exactly the three documented legacy skips.
- Python compile/AST, R manifest parsing, YAML/JSON parsing: PASS.
- `targets::tar_validate()`: PASS.
- Target manifest/network: PASS; 162 targets and regenerated HTML.
- Dissertation Typst compile: PASS; only existing unavailable Korean-font warnings.
- Markdown local-link check and `git diff --check`: PASS.

## Immutability and non-execution

The preflight inventory contained 1,609 files across the existing formal-plan publication and research target store. Post-publication comparison found:

- Existing scientific/artifact payload SHA changes: 0.
- Existing P1-P7 and old P8 artifact mutations: 0.
- New immutable P8 JSON files: 9.
- Expected targets metadata files changed: `meta/crew`, `meta/meta`, `meta/process`, `meta/progress` only.
- P9/P10/P11, optimizer, checkpoint, evaluation, maintenance, and GPU execution: 0.
- Dissertation file mutation: 0.

## Changed files

Production changes cover the P8 Python builder, R orchestration, target declarations, configuration, two new schemas, updated comparison/acceptance/methodology schemas, focused Python/R tests, manifest expectation, blueprint comparison scope, and regenerated target-network HTML. No cache, checkpoint, target-store object, credential, or temporary output is tracked.

## Next action

Perform the P9 implementation audit against the new P8 acceptance before authorizing any formal training.
