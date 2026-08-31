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
| V2-G Historical import/acceptance | Validated importer, immutable v1 source | Canonical imported bundle, finalization result, v2 acceptance | New v2 content-addressed artifacts only | Source mutation, retraining, validation rerun, evaluation | Pre/post inventory, independent validator/finalizer, idempotent publication, resolver | `P9_V2_G_HISTORICAL_ACCEPTANCE_PASS` | A-F | Explicit migration/publication authority required |
| V2-H Future controller migration | V2-A-F, future scientific config | Production v2 training controller | Source/tests; future authorized run artifacts | Any launch in implementation unit, v1 execution | Production-shaped pilot, lock/process death, exact resume, resource/closure tests | `P9_V2_H_CONTROLLER_PASS` | A-F | Implementation no; future run yes |
| V2-I V1 retirement | Accepted v2 resolver and migration outcome | Retirement manifest, fail-closed v1 entry points, archived labels | Docs/source markers/new manifest | Deletion/rewrite of legacy evidence | All v1 entry points blocked, read-only tools pass, downstream rejects v1 | `P9_V2_I_V1_RETIRED_PASS` | E and G; H if future training needed | Explicit retirement publication authority |

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
| Isolated active targets/edges | 26/50 plus recovery 11/13 | 8/7 |
| Dedicated active stores | 6 historical generations plus main coupling | 1 generation per v2 pipeline generation; historical stores read-only |
| Mutable state artifact classes | 8 | 3 evidence files across two locks; scientific state is ledger-derived |
| Target metadata required for science | Yes | 0 |
| Separate finalization recovery DAG | Yes | 0 |

## Exact recommended next work unit

`V2-G: canonical historical import, pure finalization, acceptance publication, and resolver verification under explicit migration/publication authority.`
