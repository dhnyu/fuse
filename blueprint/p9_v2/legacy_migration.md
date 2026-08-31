# Historical Import and Legacy Retirement

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

## Read-only audit verdict

`MIGRATION_ELIGIBLE_WITHOUT_RETRAINING`

The audit found no missing scientific field that blocks a v2 bundle. All 25 payload hashes match their manifests; every selected checkpoint contains online model, EMA model, optimizer, scheduler, two-rank RNG state, sampler epoch/cursor, queue payload/count/pointer/enqueue count, early-stopping count, best-checkpoint state, validation trace, training trace, lineage, and world-size state. All epoch/update/cursor/queue invariants pass after applying the explicit legacy epoch normalization.

## Immutable source lineage

| Item | Audited value |
|---|---|
| Authority | `p9a_9d6f0554553ac43371b47efd` |
| Reservation | `p9res_0f5492c80e7c152e6c543012` |
| Attempt | `p9attempt_a754afd14ac87287afb04029` |
| Run | `p9run_6887930091dd2f2bfedc3c96` |
| v1 state | `FAILED_NONRESUMABLE` (unchanged) |
| Trajectory | epoch 125, update 9,500, 25 validations, 25 checkpoints |
| Join | 25/25 `EXACT_MATCH` |
| Best | epoch 105, loss `0.3806893527507782`, margin `0.28760260343551636` |
| Selected checkpoint | `p9ck_42f7957d2ea998ac9e8ff705` |
| Payload SHA-256 | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` |
| Manifest SHA-256 | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` |
| Stopping | epoch 125/update 9,500; four non-improvements after epoch 105 |
| Evaluation consumption | 0 |

Accepted parents are intact and hash-bound by immutable root inventory `p9root_4266c6b6b2c82019027f96ae`: P7 acceptance, P7 runtime acceptance `p7rta_c780441a553abe26772827d0`, P8 acceptance, P9 readiness, cache acceptance `p9ca_99725ef4c56f8b11b4d71935`, cache `p9cache_f8b16c49f2c63216609b013b`, and category vocabulary. The cache inventory remains 314,695 files and 391,466,804,516 bytes.

## Field mapping

| Required v2 field | Classification | Source or derivation |
|---|---|---|
| Authority manifest | `DIRECTLY_AVAILABLE` | Formal authority JSON and exact runtime file manifest. |
| Scientific configuration | `DIRECTLY_AVAILABLE` | P8 matrix row, authority training/validation contracts, dissertation binding. |
| Runtime digest | `DIRECTLY_AVAILABLE` | `219e8007...` in authority and checkpoint lineage. |
| Source parents/cache acceptance | `DIRECTLY_AVAILABLE` | Immutable root inventory and authority parents. |
| Sampler contract | `DIRECTLY_AVAILABLE` | Corrected global-batch sampler contract/hash. |
| Run identity | `DIRECTLY_AVAILABLE` | Attempt and terminal evidence. |
| Native contemporaneous v2 ledger | `NOT_APPLICABLE` | Import creates legacy-marked events; it must not claim contemporaneous writes. |
| Event sequence/hash chain | `DETERMINISTICALLY_DERIVABLE` | Canonical source order and importer version. |
| Completed epochs | `DIRECTLY_AVAILABLE` | Validation trace and checkpoint directory labels. |
| Resume epochs | `DETERMINISTICALLY_DERIVABLE` | Manifest/payload progress is `completed_epoch + 1`. |
| Optimizer updates | `DIRECTLY_AVAILABLE` | 76 per epoch and payload `global_update`; trace length agrees. |
| Validation IDs | `DETERMINISTICALLY_DERIVABLE` | Hash of source run, completed epoch, metric record, embedding hash. |
| Checkpoint IDs/hashes | `DIRECTLY_AVAILABLE` | 25 manifests and payload hashes. |
| Checkpoint manifest hash | `DIRECTLY_AVAILABLE` | Read-only SHA-256; recovery audit records all 25. |
| Atomic completion marker | `AVAILABLE_WITH_LEGACY_ANNOTATION` | Payload then manifest atomic publication contract plus complete pair; imported marker identifies legacy evidence. |
| Online/EMA model state | `DIRECTLY_AVAILABLE` | Both mappings present in every payload. |
| Optimizer/scheduler state | `DIRECTLY_AVAILABLE` | Both present in every payload. |
| Scaler state | `NOT_APPLICABLE` | AMP is false; payload records `scaler = null`. |
| Queue payload/count/pointer | `DIRECTLY_AVAILABLE` | Every payload; count/pointer/enqueue arithmetic coherent. |
| Sampler cursor/state | `DIRECTLY_AVAILABLE` | Every payload; resume epoch and cursor zero coherent. |
| Per-rank RNG state | `DIRECTLY_AVAILABLE` | Two records in every payload, matching world size two. |
| Early-stopping/selector state | `DIRECTLY_AVAILABLE` | Payload trace, best state, patience count; last count is four. |
| Training trace through 9,500 | `DIRECTLY_AVAILABLE` | Last payload trace length and terminal progress. |
| `TRAINING_COMPLETED` import event | `DETERMINISTICALLY_DERIVABLE` | Dissertation stopping replay reaches patience four at epoch 125. |
| Training summary/stopping boundary | `DETERMINISTICALLY_DERIVABLE` | Ledger replay and immutable trace. |
| Diagnostic incidents | `AVAILABLE_WITH_LEGACY_ANNOTATION` | v1 failure state/reports and epoch linkage exception. |
| Evaluation-consumption count | `DIRECTLY_AVAILABLE` | All 25 validation records, worker result, authority and terminal evidence report zero. |
| Source inventory digest | `DETERMINISTICALLY_DERIVABLE` | Ordered paths, sizes, and hashes of authority, run evidence, 25 pairs, parents and contracts. |
| v1 terminal state | `DIRECTLY_AVAILABLE` | Preserved as historical annotation only. |

`MISSING_BLOCKING`: none.

## Importer rules

The importer is a future read-only tool. It receives explicit source run/attempt/authority identities and an expected source-inventory digest. It must:

1. Open all source artifacts read-only and reject symlinks, mutable aliases, unexpected files, hash changes, or incomplete pairs.
2. Revalidate 25 validation records and 25 manifests/payloads without executing model code, validation, or evaluation.
3. Emit canonical legacy events ordered by source validation epoch and control evidence order. Every event has `legacy_import: true`, source path/hash, derivation rule ID, importer implementation hash, and `observed_source_timestamp`; it never claims an event occurred at import time.
4. Normalize `completed_epoch=N` and `resume_epoch=N+1` explicitly. It never changes source manifests.
5. Derive IDs, selector state, completion, stopping boundary, and source inventory only through documented pure rules. It does not recompute metrics or model outputs.
6. Publish a new content-addressed v2 bundle atomically. It does not publish acceptance in the same work unit.
7. Preserve `FAILED_NONRESUMABLE` in `migration/legacy_import.json` and record the v2 interpretation separately.

## Migration acceptance criteria

All must pass before historical v2 acceptance:

- 25/25 exact atomic validation-checkpoint events;
- one unique epoch-105 selected candidate;
- selected checkpoint and payload/manifest hashes exact;
- epoch 125/update 9,500 stopping boundary and four non-improvements exact;
- zero evaluation consumption;
- complete parent and runtime provenance;
- immutable source inventory;
- online model, EMA, optimizer, scheduler, RNG, queue, sampler, early-stopping, best and trace state present and coherent;
- no scientific inconsistency;
- independent bundle validator and pure finalizer agree on selection and stopping.

The present read-only audit satisfies these evidence criteria. Retraining is not required. Actual import and acceptance remain prohibited until V2-A through V2-F pass and V2-G is separately authorized.

## V1 retirement plan

V2-I will, without deleting artifacts:

- publish one retirement manifest marking all 9 formal and 3 recovery authorities v1-ineligible;
- preserve reports, logs, stores, checkpoints, validation records, locks, and state evidence;
- make v1 run/recovery entry scripts fail closed with a historical-only message;
- retain read-only inventory, hash, and diagnostic tools;
- label three formal and three recovery stores as archived historical generations;
- make the canonical resolver reject every direct v1 artifact and recovery acceptance;
- update documentation to call v1 historical evidence, not an active execution path;
- prohibit downstream checkpoint paths and require a v2 acceptance identity.

This blueprint does not implement retirement.
