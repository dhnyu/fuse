# P9 v2 Phased Implementation Roadmap

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

Each work unit is independently reviewed, committed, and authorized where stated. No unit silently expands into training or held-out evaluation.

| Unit | Inputs | Outputs | Permitted mutations | Prohibited actions | Required tests | Success verdict | Depends on | Authority? |
|---|---|---|---|---|---|---|---|---|
| V2-A Schemas, ledger, state | This blueprint, dissertation contracts | Runtime schemas, canonical JSON/hash library, ledger/state replay | Source/tests and synthetic temp fixtures | Production artifacts, authority, training | Schema, hash chain, torn append, replay/property, state matrix | `P9_V2_A_LEDGER_STATE_PASS` | None | No |
| V2-B Bundle builder/validator | V2-A, synthetic committed events/artifacts | Immutable bundle builder, validator, inventory | Source/tests and synthetic bundles | Historical import, acceptance, GPU | Completeness, collision, external locator, hash, target-metadata independence | `P9_V2_B_RUN_BUNDLE_PASS` | A | No |
| V2-C Finalizer/publisher | V2-B, selection contract | Pure finalizer, acceptance publisher, resolver core | Source/tests and synthetic acceptance root | Training, validation/evaluation, production publication | Determinism, selector/early stop, failure codes, concurrent/idempotent publish, crash points | `P9_V2_C_FINALIZATION_ACCEPTANCE_PASS` | A-B | No |
| V2-D Historical importer dry run | V2-A/B, immutable v1 evidence | Read-only import audit and noncanonical dry-run bundle | Source/tests and external temporary dry-run output | Source writes, canonical bundle/acceptance, metric recompute | 25/25 mapping, state presence, hashes, derivation annotations, rerun identity | `P9_V2_D_IMPORT_DRY_RUN_PASS` (implemented) | A-C | No authority issued |
| V2-E Resolver migration | V2-C, consumer interfaces | One public resolver and consumer contract changes | Source/tests | Evaluation, P9-B training, manual path fallback | Rejection matrix and contract tests for P9-B/selected-FM/eval/P10/P11 | `P9_V2_E_RESOLVER_MIGRATION_PASS` (implemented in V2-EF) | C | No execution authority |
| V2-F Synthetic end to end | V2-A-E | Synthetic controller-to-resolver acceptance | Synthetic fixture roots only | Production cache/run/evaluation | Interruption/resume, training failure, finalization retry, publish retry, bookkeeping failure | `P9_V2_F_SYNTHETIC_E2E_PASS` (implemented in V2-EF) | A-E | Synthetic fixtures only; no authority issued |
| V2-G Historical import/acceptance | Validated importer, immutable v1 source | Canonical imported bundle, finalization result, v2 acceptance | New v2 content-addressed artifacts only | Source mutation, retraining, validation rerun, evaluation | Pre/post inventory, independent validator/finalizer, idempotent publication, resolver | `P9_V2_G_HISTORICAL_ACCEPTANCE_PASS` (implemented) | A-F | Bounded authority `p9authv2_47f350372bf94162db8f9142` |
| V2-H Future controller migration | V2-A-I, future scientific config | Production v2 training controller and isolated 8-target graph | Source/tests; future authorized run artifacts | Any optimizer update or formal launch in implementation unit, v1 execution | Production-shaped 2-GPU forward-only pilot, lock/process death, exact resume, resource/closure tests | `P9_V2_H_PRODUCTION_TRAINING_CONTROLLER_PASS` (implemented) | A-I | Implementation no; each future run yes |
| V2-I V1 retirement | Accepted v2 resolver and migration outcome | Retirement manifest, fail-closed v1 entry points, archived labels | Docs/source markers/new manifest | Deletion/rewrite of legacy evidence | All v1 entry points blocked, read-only tools pass, downstream rejects v1 | `P9_V2_I_V1_RETIRED_PASS` (implemented) | E and G | Explicit V2-I work-unit instruction; no new execution authority |

## Failure and recovery behavior

| Failure class | Scientific state | Operational handling |
|---|---|---|
| Training interruption with complete resumable checkpoint | `IN_PROGRESS` | `INTERRUPTED_RESUMABLE`; exact resume only under explicit policy using the same run identity and ledger continuation. |
| Training failure without valid checkpoint | `INCOMPLETE` | `TRAINING_FAILED`; no finalization. A new run requires a new authority if policy permits. |
| Training complete, finalization fails | `COMPLETE` | `FINALIZATION_FAILED`; rerun pure finalizer over the same bundle. No attempt/recovery DAG. |
| Acceptance publication fails | `COMPLETE` | Retry idempotent publication. No scientific recomputation. |
| Acceptance committed, bookkeeping fails | `COMPLETE` | Resolver recognizes canonical commit; repair targets/report bookkeeping separately. |

These rules handle the historical target bootstrap and closure failures as `BLOCKED/NOT_STARTED`, vocabulary and sampler failures as `TRAINING_FAILED` with science incomplete at their respective boundaries, and the completed epoch-125 linkage failure as `COMPLETE/FINALIZATION_FAILED`.

## Complexity targets

| Measure | V1 baseline | V2 target |
|---|---:|---:|
| Canonical ledgers | Multiple mutable files/no canonical ledger | 1 |
| Training controllers | Main + isolated formal paths | 1 |
| Bundle validators | 0 standalone | 1 |
| Finalization/recovery paths | 3 | 1 pure finalizer |
| Acceptance publishers | 2 plus target exposure | 1 |
| Resolvers | Recovery resolver plus path exposure | 1 |
| Lock classes | 3 | 2 maximum |
| Formal/recovery identity types | At least 8 core, more acceptance/supersession types | 5 total |
| P9 target scripts | 3 | 1 isolated v2 script; v1 frozen |
| Isolated active targets/edges | 26/50 plus recovery 11/13 | 9/20 executable native closure |
| Dedicated active stores | 6 historical generations plus main coupling | 1 generation per v2 pipeline generation; historical stores read-only |
| Mutable state artifact classes | 8 | 3 evidence files across two locks; scientific state is ledger-derived |
| Target metadata required for science | Yes | 0 |
| Separate finalization recovery DAG | Yes | 0 |

## Current execution status and exact next work unit

- `cfg_main` canonical V2 acceptance: complete; reported as `cfg_d64`; duplicate training prohibited.
- `cfg_d48` native formal V2 acceptance: complete; selected epoch 130 and duplicate training prohibited.
- V1 execution retirement: complete.
- V2-H controller foundation: complete.
- V2-H production-worker remediation: complete; update/checkpoint/resume and V2-B/C/E closure validated in temporary evidence.
- New formal variant architecture: executable; one non-main formal trajectory has completed.
- P9-A configurations: 13/13 canonically accepted and resolver-validated. The
  original failed `cfg_intensity_05` authority/run remains preserved as
  `INCOMPLETE / BLOCKED / RESTART_REQUIRED`; the corrected run is independently
  accepted.
- Validation-only factor selection: `d=128`, `K=4`, weak `0.5x`, EMA `0.999`,
  `lambda_IP=0`, and peak LR `3e-3`.
- Selected-FM interaction confirmation: complete. IP1 won only within the
  factor-wise joint pair; both acceptances remain immutable evidence.
- Final full model: `cfg_d128`, acceptance
  `p9accv2_a1c00e32a882ddc4b7e2677b`, selected across all executed validation
  candidates by `p9fms_389a0ce89992eee507d7c846`.
- P9-B comparisons: 7/7 canonically complete and resolver-validated under
  `p9bplan_e36f7c9c5069a504eb31a9ef`. The original DS-like trajectory remains
  preserved as operator-abandoned evidence; its fresh cached replacement is
  acceptance `p9accv2_f4194b7c74f8dedb4c867e6b`.
- P10 held-out evaluation: complete for the closed eight-model set under
  `p10auth_8b6919578aaa24fa8f1b98a2`; prepared-input attempt
  `p10exec_7fee193dac532190c79e02c6` is accepted as
  `p10acc_6e5071beee7616750dec7907` and reuses the single consumption record
  `p10cons_7d0eba832b70d545fc5d3eb4`.
- Future P11 scientific contracts bind dissertation
  `reduced@989c19d98e64ec129dc53b761c58a4d961fc3983` through
  `disauth_febd90b8475a5e9caa9f7d2f`; historical P9/P10 and earlier P11 bindings remain
  immutable.

The P9-A campaign completion audit found no scientific comparability blocker.
`P9_SELECTED_FM_IP_COMPARISON` and P9-B are complete. The P9 ablation
completion audit verified every canonical chain and exact dynamic/cached
overlap. P10 has since completed without reopening P9 selection. P11-A2
materialized the immutable historical eleven-target dataset
`p11ds_fdb1f34c6daeda259e803e37`. The dissertation-authorized partial-support
rematerialization supersedes it with `p11ds_39607da2de792ad6b3c9bb30`, without
rewriting the historical dataset. The replacement constructs the full
scene-grid-date-hour support universe, keeps absent observations unavailable,
and accepts a temporal class only when at least one valid scene-hour exists.
The target transformation map is closed by
`p11meth_6cc844b7f5d1fc896d9e7be2`: the five SGIS responses, four living-
population responses, and official land value use parameter-free `log1p`,
while ECOSTRESS Kelvin LST uses identity. P11-C readiness
`p11c_e78d7c740edc49f1f646ebc3` assigns all 1,600 scenes to exactly one of 25
district folds, binds the original 1,600-row gallery slice for all eight P10
models, and passes all 275 target-fold evaluability and leakage gates without
fitting a ridge model or producing predictions. P11-E is now complete:
`p11e_047e764ed7467b72ebe846df` binds 2,200 successful fixed-
lambda ridge fits, 128,432 exactly-once original-scale OOF predictions, and 88
pooled metric rows. It uses only training-fold predictor statistics and does
not alter P9/P10 selection. The exact next work unit is
`P11_F_FINAL_DOWNSTREAM_COMPARISON_AND_ACCEPTANCE`.
