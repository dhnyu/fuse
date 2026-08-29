# P8 13-Hyperparameter and 7-Comparison Plan Implementation

## 1. Verdict

`P8_13_HYPERPARAMETER_7_COMPARISON_PLAN_PASS_PUSHED` is the required final verdict after the enclosing publication commit is pushed and synchronized. All implementation, plan-only execution, schema, test, no-op, and immutability gates passed before publication.

## 2. Repository state

| Repository | Start | Implementation/publication state |
|---|---|---|
| Fuse `reduced` | `318c4f16948e4e77a20a7f822a5abd9aa91f5b9d` | implementation `bd3550af8188c4386eac1c1dcd334242c66ea3e6`; publication is the commit containing this report |
| Dissertation `reduced` | `2a1e93ff3dc3a9d5c312bfd20751b965e84a8c38` | `a456f46566c5e760c048091ead53cb4debe73832`, pushed and synchronized |

Both repositories started clean on `reduced` with ahead/behind `0/0`. No unexpected user change was present.

## 3. Dissertation methodology audit

The latest Typst sources already specified `d in {48,64,128}`, `d_c=d`, four attention heads, per-head dimensions `12/16/32`, 13 unique OFAT configurations, and peak learning rates `{1e-3,2e-3,3e-3,1e-2}`. The main configuration remains `d=64`, `d_c=64`, and peak LR `1e-3`.

Two prospective rules were missing and were added before results exist:

- comparison variants inherit the validation-selected FM configuration and never compete in hyperparameter selection;
- an evidence-complete non-finite `cfg_lr_10` outcome is `SCIENTIFIC_DIVERGENCE`, not infrastructure failure, and cannot be replaced post hoc by another LR.

Modified methodology modules:

- `template/sections/chapters/results/01-experimental-setup.typ`
- `template/sections/chapters/results/05-hyperparameter-study.typ`

## 4. Scoped methodology lineage

The dissertation change affects the P8 plan, P9 comparison sequencing, and P10 reporting policy. It does not change the accepted P7 main model, data, augmentation, optimizer protocol, or training configuration. P1-P7 artifacts therefore remain preserved. P8 binds dissertation commit `a456f465...` and the four scoped module digests in `p8mc_2f02bc13d7b04a410f01fe3e`.

The repository-wide legacy P0 authority still detects the newer dissertation commit and fails closed. This is deliberate: P8 does not silently republish P0. The scoped P8 compatibility record is the new-methodology boundary.

## 5. Blueprint and roadmap correction

The blueprint metadata now records the active P6/P7 lineage and cold-path runtime acceptance. P8 is plan-only and publishes 13 concrete P9-A specs plus seven deferred P9-B templates. P9-A precedes P9-B. P10 only maps frozen checkpoints to held-out evaluation; it cannot initialize training, construct an optimizer, mutate EMA/queue state, or select a new checkpoint.

Expected formal attempts are `13 + 7 = 20`, with main-training duplication `0`.

## 6. P8 identities

| Artifact | Identity |
|---|---|
| Methodology compatibility | `p8mc_2f02bc13d7b04a410f01fe3e` |
| Authority | `p8a_ced1badc5a539f3823a0fdd0` |
| Hyperparameter matrix | `p8hm_f34f1666b62255babab0ae08` |
| Comparison matrix | `p8cm_6b21d8791d82d24bf5e39ca3` |
| Augmentation-bank index | `p8bi_2e492527089bf5ce9d00a933` |
| Hyperparameter plan | `p8hp_8be2a3f54b3e0b5f9d1b809d` |
| Materialization template | `p8mt_f703966b2553da4cb9478a7d` |
| Acceptance | `p8acc_6a37d2978af940d03c597511` |

Acceptance SHA-256: `1d189a1b36b7aad3ac8ecf5fb051daef224b964cdd14e9b9f2aaeb8ababeb9e9`.

## 7. Hyperparameter configurations

| ID | Factor | d | K | Intensity | EMA | lambda_IP | Peak LR | Hash prefix |
|---|---|---:|---:|---|---:|---:|---:|---|
| `cfg_main` | main | 64 | 8 | main 1.0x | .999 | 1 | 1e-3 | `9ca251b54d6f` |
| `cfg_d48` | d | 48 | 8 | main 1.0x | .999 | 1 | 1e-3 | `c155d758c8e0` |
| `cfg_d128` | d | 128 | 8 | main 1.0x | .999 | 1 | 1e-3 | `8ce5bf6d8fb0` |
| `cfg_k2` | K | 64 | 2 | main 1.0x | .999 | 1 | 1e-3 | `88640b266395` |
| `cfg_k4` | K | 64 | 4 | main 1.0x | .999 | 1 | 1e-3 | `151b0175e982` |
| `cfg_k16` | K | 64 | 16 | main 1.0x | .999 | 1 | 1e-3 | `3cb8c3f0bdca` |
| `cfg_intensity_05` | intensity | 64 | 8 | weak 0.5x | .999 | 1 | 1e-3 | `393a53e3f3a7` |
| `cfg_intensity_20` | intensity | 64 | 8 | strong 2.0x | .999 | 1 | 1e-3 | `2f8009ea1b97` |
| `cfg_ema_990` | EMA | 64 | 8 | main 1.0x | .990 | 1 | 1e-3 | `3037bf5812f8` |
| `cfg_ip_0` | lambda_IP | 64 | 8 | main 1.0x | .999 | 0 | 1e-3 | `df24728b96d9` |
| `cfg_lr_2` | peak LR | 64 | 8 | main 1.0x | .999 | 1 | 2e-3 | `74c793ef75ea` |
| `cfg_lr_3` | peak LR | 64 | 8 | main 1.0x | .999 | 1 | 3e-3 | `52de77c5402f` |
| `cfg_lr_10` | peak LR | 64 | 8 | main 1.0x | .999 | 1 | 1e-2 | `f1518224676d` |

All 12 non-main rows differ from main in exactly one factor. Duplicate hashes and non-OFAT rows are zero.

## 8. Comparison templates

| Template | Class | Template hash prefix | P8 final hash |
|---|---|---|---|
| `cmp_a1_no_geometry` | ablation | `a2b637971e13` | unresolved |
| `cmp_a2_no_semantics` | ablation | `d3a7848d774e` | unresolved |
| `cmp_a3_no_raster_context` | ablation | `57d2490de84f` | unresolved |
| `cmp_a4_no_spatial_relations` | ablation | `2b56cf8f124d` | unresolved |
| `cmp_a5_radius_context` | ablation | `57beb74f9c1f` | unresolved |
| `cmp_ssv_like` | controlled baseline | `c32c80baae23` | unresolved |
| `cmp_ds_like` | controlled baseline | `08ae319fab9f` | unresolved |

Every template requires `selected_configuration_identity`, inherits the selected FM settings except explicit transformations, is ineligible for hyperparameter selection, and rejects `cfg_main` substitution, latest-checkpoint fallback, old P7 lineage, and evaluation identity injection. Early materialization count is zero.

## 9. Bank and validation binding

P4 bank `augbank_252ce67e6d74679b02871e57` and acceptance `aba_39de6c260a8e427767bc01d6` are reused. K2/K4/K8/K16 have canonical nested subset identities; weak/main/strong profiles select the accepted profile banks. All 13 configurations and seven templates bind validation acceptance `fqsa_27565de68d9432e47fe7b99d`, query index `fqi_d7ec7e7a88237145e72e6f8a`, and gallery `fgg_325a8031c9428d72943848ff`.

Direct evaluation query identity and evaluation ancestry are absent. Acceptance reports evaluation ancestry count `0`.

## 10. d128 compatibility

Construction-only compatibility passed from fresh source without legacy artifacts:

| d | d_c | Heads | Per-head | Construction | Parameters in bounded compatibility model |
|---:|---:|---:|---:|---|---:|
| 48 | 48 | 4 | 12 | PASS | 47,520 |
| 64 | 64 | 4 | 16 | PASS | 81,792 |
| 128 | 128 | 4 | 32 | PASS | 311,040 |

No optimizer, queue, checkpoint, or formal training was created. Legacy d128 artifact adoption is false.

## 11. LR 1e-2 divergence contract

Accepted triggers are non-finite loss, gradients, parameters, validation metrics, scientifically invalid optimizer state, or deterministic unrecoverable numerical divergence. The terminal record must preserve the last valid update, detection reason, complete trace through that update, and deterministic detection record. It is winner-ineligible but reportable. Infrastructure failure cannot use this status, and replacement LR is prohibited.

## 12. Target execution

Only `formal_experiment_plan_acceptance` was selected with the explicit research store. First execution built nine reachable P8 targets in 9.8 seconds. P9/P10/P11, maintenance, P7 training, evaluation, and GPU targets were not selected or executed.

The immediate repeat skipped all nine reachable targets: builds `0`, rewrites `0`, GPU executions `0`, optimizer updates `0`, checkpoint creations `0`. Seven bundle files retained identical path, size, mtime, and SHA-256. P8 outdated count is `0`.

The global store reports 113 outdated targets because the historical repository-wide P0 dissertation binding and blueprint-dependent older targets see the scoped methodology/blueprint revision. These were not executed or rewritten. P8 uses immutable accepted parent readback plus the scoped compatibility gate.

## 13. Validation results

- Focused P8 Python: 7 passed.
- Focused P6/P7/P8 Python: 44 passed.
- Full Python: 189 passed.
- Focused P8/P0/manifest R: PASS.
- Full R/testthat: PASS with exactly three documented legacy skips.
- Seven actual P8 JSON artifacts: schema PASS.
- Python compile/AST, R parse, YAML/JSON parse: PASS.
- `targets::tar_manifest()`: 160 targets, seven required logical P8 targets present.
- `targets::tar_validate()`: PASS.
- Target network render and tests: PASS.
- `git diff --check`: PASS.
- Dissertation Typst 0.15.1 compile: PASS; only pre-existing missing Korean font warnings.

## 14. Immutability and non-execution

The pre-inventory contains 7,966 accepted/store files (`/tmp/p8_pre_inventory_20260830.tsv`, SHA-256 `1bd618aa270c11745db4b3c9a53e7f2c2140aea1f0202949e2259ad99ed55069`). Post comparison found missing `0` and scientific/accepted payload mutations `0`.

Four store control metadata files (`meta/crew`, `meta/meta`, `meta/process`, `meta/progress`) changed as the explicit P8 execution was recorded. No pre-existing target-store object or P3-P7 artifact payload changed. P9/P10/P11/maintenance executions, optimizer updates, formal checkpoints, and evaluation consumption are all `0`.

## 15. Changed files

Implementation includes the P8 YAML contract, seven schemas, Python builder/validator, R orchestration, target declarations, focused Python/R tests, root target registration, blueprint correction, and regenerated target-network HTML. Dissertation changes are limited to the two prospective methodology clarifications listed above. No cache, checkpoint, target store, credential, bytecode, or bulk runtime payload is tracked.

## 16. Publication

- Dissertation: `a456f46566c5e760c048091ead53cb4debe73832` (`Clarify formal experiment selection protocol`), pushed.
- Fuse implementation: `bd3550af8188c4386eac1c1dcd334242c66ea3e6` (`Implement P8 formal experiment planning`).
- Fuse publication: the enclosing commit containing this report.

Final fetch, local/remote equality, ahead/behind `0/0`, and clean-worktree checks are performed after the publication push.

## 17. Next action

The next single work unit is the P9 implementation audit: audit P9-A/P9-B training infrastructure and all A1-A5/SSV-like/DS-like model/data transformations, then require a production-shaped main-configuration pilot before authorizing formal runs.

## Prompt summary

Implement and publish a plan-only P8 contract that freezes 13 OFAT hyperparameter configurations and seven selected-FM-derived comparison templates, corrects the P8/P9/P10 blueprint, excludes evaluation and training from P8, validates no-op and immutability, and pushes only after complete PASS.
