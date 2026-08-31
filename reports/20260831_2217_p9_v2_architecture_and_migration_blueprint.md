# P9 v2 Architecture and Migration Blueprint Audit

## Verdict

`P9_V2_ARCHITECTURE_AND_MIGRATION_BLUEPRINT_PASS_PUSHED`

`MIGRATION_ELIGIBLE_WITHOUT_RETRAINING`

This is a documentation and read-only audit verdict. It does not implement or authorize P9 v2, does not accept the historical run, and does not change the historical `FAILED_NONRESUMABLE` state. The pushed verdict is conditional on the final repository readback recorded in the task response: documentation commit present on `origin/reduced`, both repositories clean, and ahead/behind 0/0.

## Purpose and scope

- Execution time: 2026-08-31 22:12-22:36 KST before commit/push readback.
- Fuse start: `reduced@e84fc1943beee33a4299472369e2c976e6baa7e6`.
- Dissertation: `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`.
- Both repositories initially clean and synchronized with origin at 0/0.
- Scope: architecture inventory, failure analysis, complexity baseline, v2 design, read-only historical import feasibility, migration/retirement roadmap, draft non-runtime schemas.

The active blueprint and dissertation training, model-selection, and early-stopping sections were read before design. No methodology conflict was found. Validation every five epochs, retrieval loss primary selection, `1e-4` equivalence, larger margin then earlier epoch, and patience four remain unchanged.

## V1 complexity baseline

| Measure | Audited count |
|---|---:|
| Direct P9 implementation/config/schema files | 65: 10 R/target, 19 production Python, 6 config, 30 schema |
| P9 target scripts | 3 |
| Main DAG P9 targets/edges | 28/52: 50 internal, 2 inbound |
| Isolated formal DAG targets/edges | 26/50; terminal closure 25/49 |
| Recovery DAG targets/edges | 11/13 |
| Dedicated P9 stores/generations | 6: 3 formal, 3 recovery |
| Formal/recovery authority identities | 12: 9 formal, 3 recovery |
| Core formal/recovery identity types | 8, with additional supersession and acceptance artifact identities |
| Mutable state artifact classes | 8 |
| Lock implementations | 3: GPU pair, formal attempt, recovery transaction |
| Finalization/recovery paths | 3 |
| Acceptance/resolver paths | 3 |
| Direct P9 test files/named tests | 13/77: 65 Python, 12 R |
| Historical P9 reports | 19 |

The full path/function/artifact/plane/consumer/disposition inventory is in `blueprint/p9_v2/v1_inventory.md`.

## Failure taxonomy

The chronological failure chain was:

1. authority/commit and duplicate-key identity mismatch;
2. missing formal runner and terminal DAG;
3. `shortcut = TRUE` target bootstrap failure;
4. unsafe main-pipeline closure under `shortcut = FALSE`;
5. isolated formal DAG introduction, leaving duplicated control paths;
6. vocabulary direct-mapping versus obsolete-wrapper mismatch;
7. historical scene identity lookup failure;
8. global-batch padding duplication, then corrected uniqueness contract;
9. validation completed epoch `N` compared to checkpoint resume epoch `N+1`;
10. incomplete recovery DAG;
11. missing recovery lock transaction;
12. incomplete recovery transaction/commit/resolver validation.

The categories span identity contract, orchestration, execution isolation, data contract, scientific computation, artifact linkage, finalization, recovery, excessive governance complexity, and missing test boundaries. V2 structurally removes the target-metadata bootstrap, broad closure, semantic epoch join, special recovery DAG, recovery authority/lock, and recovery transaction defects. Vocabulary and sampler bugs remain scientific contract risks, but are isolated and tested at the scientific boundary.

## V2 architecture

The scientific plane owns data/cache reads, sampler, model, optimizer, EMA, scheduler, updates, validation, checkpoint payload creation, and scientific event proposals. It cannot determine authority state, target currentness, acceptance, supersession, or downstream resolution.

The control plane owns authority validation, duplicate-run lock, supervision, canonical ledger append, bundle publication, pure finalization invocation, acceptance publication, canonical resolution, and operational incidents. It cannot change parameters, validation metrics, checkpoint payloads, sampler outcomes, or scientific configuration.

V2 proposes one ledger, one controller, one bundle validator, one pure finalizer, one publisher, one resolver, two lock classes, and five identities: execution authority, run, run bundle, finalization, acceptance. Reservation, preassigned attempt, operation, recovery authority/reservation, and authorization-acceptance identities are removed because their distinguishing information is already hash-bound by retained identities and lock scope.

## State model

Scientific states:

```text
NOT_STARTED | IN_PROGRESS | COMPLETE | INCOMPLETE
```

Operational states:

```text
AUTHORIZED | STARTING | RUNNING | FINALIZING | ACCEPTED |
INTERRUPTED_RESUMABLE | TRAINING_FAILED | FINALIZATION_FAILED | BLOCKED
```

Resumability is independent:

```text
NOT_APPLICABLE | EXACT_RESUME_ALLOWED | RESTART_REQUIRED |
NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE | FORBIDDEN_POLICY | EVIDENCE_INVALID
```

The historical evidence is represented in v2 as scientific `COMPLETE`, operational `FINALIZATION_FAILED`, resumability `NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE`. Its v1 terminal state remains byte-unchanged `FAILED_NONRESUMABLE`.

## Ledger and atomic event model

One run owns immutable canonical JSONL segments with monotonic sequence, deterministic event ID, run identity, RFC3339 timestamp, writer identity/role, schema version, previous-event hash, and event hash. A single serialized writer boundary uses same-filesystem staging, `O_EXCL`, file `fsync`, atomic rename, and directory `fsync`. A closed ledger manifest inventories ordered segment hashes. Replaceable tail caches are non-authoritative.

Required events include authorization/start, epoch start, progress summaries, atomic validation-checkpoint commits, early-stopping updates, training completion/interruption/failure, finalization start/completion/failure, and acceptance publication. Update traces are batched into immutable blocks with exact update ranges; one event per update is optional and not the default.

`VALIDATION_CHECKPOINT_COMMITTED` binds completed epoch, resume epoch, update, validation/checkpoint identities and hashes, retrieval loss, margin, selector state, queue count/pointer/enqueue state, sampler cursor, state-presence flags, atomic marker, and source run. `completed_epoch=N` and `resume_epoch=N+1` are explicit. Validation without a committed checkpoint is ineligible.

## Run bundle

The content-addressed run bundle includes authority, scientific configuration, runtime digest, parents, cache acceptance, sampler and selection contracts, closed ledger, training summary, validation-checkpoint events, checkpoint inventory, selector state, stopping boundary, incidents, evaluation count, and source inventory. Legacy import annotation is required only for imported runs.

`bundle_content_sha256` hashes the canonical ordered manifest preimage, including immutable external object locators and hashes. `bundle_id = p9rb_<first 24 hex>`. Publication uses validated same-filesystem staging, flush, atomic rename, and create-or-validate collision handling. Completeness and finalization do not depend on `targets` metadata.

## Finalization, acceptance, and resolver

The pure API is:

```text
finalize(run_bundle_hash, selection_contract_hash) -> finalization_result
```

It has no GPU/training/validation/evaluation/checkpoint-writing dependencies. It validates the bundle, selects only committed combined events, replays early stopping, emits checkpoint/metrics/stopping/provenance and stable failure codes, and is byte-deterministic for pinned input and implementation hashes. Scientifically incomplete or invalid evidence is distinct from operational IO/process failure.

Publication is:

```text
publish_acceptance(finalization_result_hash, run_bundle_hash, authority_hash)
```

It takes a short acceptance-identity kernel lock and atomically publishes acceptance plus commit manifest. The canonical directory rename exposing the commit manifest is the acceptance commit point. Duplicate publication validates and returns existing bytes. There is no heartbeat, training lock, recovery state machine, bundle mutation, or target metadata dependency.

`resolve_accepted_checkpoint(acceptance_identity)` returns bundle identity, selected checkpoint, immutable locator, payload/manifest hashes, selected metrics, stopping summary, scientific configuration, and provenance. It rejects incomplete, superseded, revoked, hash-mismatched, uncommitted, path-only, or mutable artifacts. P9-B, selected-FM, held-out evaluation, P10, and P11 must use it; manual checkpoint paths are prohibited.

## Minimal `targets` role

The conceptual isolated `_targets_p9_v2.R` has eight targets and seven internal edges: immutable inputs, authority, coarse run controller, run bundle, bundle validation, pure finalization, acceptance publication, accepted checkpoint. Mutable state transitions are ledger events. The historical import substitutes a read-only importer for the controller and shares the remaining validation/finalization/publication chain. This script/store is not implemented in this work unit.

## Historical migration audit

Read-only evidence confirmed:

- exact authority/reservation/attempt/run identities requested;
- 25 complete checkpoint payload/manifest pairs and 25 complete validation records;
- 25/25 `EXACT_MATCH` join;
- payload SHA-256 matches every manifest;
- every payload contains online model, EMA model, optimizer, scheduler, two-rank RNG state, queue payload/count/pointer/enqueue count, sampler epoch/cursor, early stopping, best checkpoint, validation trace, training trace, lineage, and world size;
- every checkpoint has `resume_epoch = completed_epoch + 1`, `global_update = completed_epoch * 76`, cursor zero, trace length equal to update, and validation count equal to its ordinal;
- queue count and pointer agree with `64 * optimizer_update` enqueues and capacity 8,192;
- last trace reaches epoch 125/update 9,500 and patience four;
- epoch 105 is the unique selected candidate under the immutable dissertation rule;
- selected ID, payload hash, and manifest hash are exact;
- evaluation consumption is zero;
- accepted P7/P8/readiness/cache/category parents and source hashes are intact.

The legacy atomic completion marker requires `AVAILABLE_WITH_LEGACY_ANNOTATION`; validation IDs, ledger chain, completion event, summary, stopping boundary, and source inventory are `DETERMINISTICALLY_DERIVABLE`. All other required scientific state is directly available or not applicable (`scaler=null` because AMP is false). `MISSING_BLOCKING` fields: none.

No metric/checkpoint is recomputed, no validation rerun is required, and retraining is not required. Actual import and acceptance require V2-G authority after V2-A through V2-F.

## Legacy retirement

V2-I will mark all nine formal and three recovery authorities ineligible, preserve every report and evidence byte, fail closed all v1 execution entry points, retain read-only inspection, label six stores historical, reject direct v1 resolution, and document v1 as evidence rather than an active path. Nothing is deleted or rewritten.

## Implementation sequence

1. V2-A schemas, ledger, state replay.
2. V2-B bundle builder/validator.
3. V2-C finalizer, publisher, resolver core.
4. V2-D historical importer dry run.
5. V2-E downstream resolver migration.
6. V2-F synthetic end-to-end execution.
7. V2-G historical import and acceptance.
8. V2-H optional future training controller migration.
9. V2-I v1 retirement.

Each unit has bounded inputs, outputs, mutations, prohibitions, tests, verdict, dependencies, and authority rules in `blueprint/p9_v2/roadmap.md`.

## Complexity reduction target

V2 reduces the active isolated target graph from formal 26/50 plus recovery 11/13 to 8/7, lock classes from three to no more than two, core formal/recovery identity types from at least eight to five, finalization/recovery paths from three to one, publishers/resolvers to one each, and scientific dependence on mutable target metadata to zero.

## Risks and unresolved decisions

Key risks are filesystem durability, cross-language canonical JSON, ledger I/O, external locator immutability, legacy PyTorch deserialization, publication races, finalizer-version drift, authority eligibility, evaluation leakage, manual downstream fallback, and plane import regressions. V2-A must decide canonical numeric encoding and segment cadence; V2-B locator syntax; V2-C eligibility index; V2-D hardened deserialization; V2-H heartbeat and progress cadence after I/O pilot. None changes dissertation methodology.

## Prohibited-work accounting

- Runtime code changes: 0.
- Dissertation changes: 0.
- Training/resume/recovery target executions: 0/0/0.
- New authorities/reservations/attempts/runs/operations/acceptances: 0/0/0/0/0/0.
- Production optimizer/EMA/scheduler updates: 0/0/0.
- Validation/evaluation executions: 0/0.
- Checkpoint/cache writes: 0/0.
- Historical checkpoint/validation/state/report rewrites: 0.
- Production cache mutations: 0.
- P9-B/selected-FM/P10/P11/maintenance execution: 0.

## Immutability audit

The audit used path, size, canonical JSON, source inventory, and SHA-256 readback. The selected payload and manifest remain:

```text
fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6
87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc
```

The accepted cache/root inventory remains 314,695 files and 391,466,804,516 bytes. Final pre/post repository and immutable-evidence comparisons are recorded after validation below.

## Validation

- Markdown H1, heading spacing, balanced fence, final-newline, and local-link/path checks: 12/12 documents passed. A standalone Markdown linter was unavailable.
- Draft JSON parse and Draft 2020-12 meta-schema validation: 4/4 passed.
- Main, isolated formal, and isolated recovery `targets::tar_validate()`: passed with no target execution.
- Read-only manifest/dependency inspection reproduced main P9 28 targets/52 incoming edges, isolated formal 26/50, and recovery 11/13.
- Historical payload CPU readback: 25/25 payload hashes and all required state/invariants passed. This was deserialization only; no model forward, validation, training, or write occurred.
- Selected payload/manifest, terminal state, immutable root inventory, and cache acceptance SHA-256 readback: passed before final publication checks.
- `git diff --check`, final scoped-file review, post-audit immutable hash readback, and repository synchronization: required immediately before/after publication.
- Runtime R/Python parse was not required because runtime code changed by this work unit is zero.
- Read-only Typst compilation was attempted to stdout but could not start: the installed snap requires invalid home directory `/members/dhnyu` and returned `snap-update-ns failed with code 1`. No dissertation file changed. This environment limitation does not alter the methodology read or architecture evidence.
- The unrelated long-running pytest process was neither awaited nor terminated, as required.

## Blueprint artifacts

- `blueprint/p9_v2/README.md`
- `blueprint/p9_v2/v1_inventory.md`
- `blueprint/p9_v2/failure_taxonomy.md`
- `blueprint/p9_v2/state_model.md`
- `blueprint/p9_v2/event_ledger.md`
- `blueprint/p9_v2/run_bundle.md`
- `blueprint/p9_v2/finalization_acceptance_resolver.md`
- `blueprint/p9_v2/legacy_migration.md`
- `blueprint/p9_v2/roadmap.md`
- `blueprint/p9_v2/risk_register.md`
- `blueprint/p9_v2/decision_log.md`
- `blueprint/p9_v2/schemas/*.schema.json`

These drafts are outside production runtime configuration and are explicitly non-runtime/non-authorizing.

## Recommended next work unit

`V2-A: schemas, canonical append-only ledger, independent state replay model, and synthetic crash-safety tests.`

V2-A must not issue authority, execute training, import the historical run, publish acceptance, consume evaluation, mutate production cache, or retire v1.

## Input prompt summary

Design and audit a simplified P9 v2 architecture separating science from control, using one append-only ledger, atomic validation-checkpoint linkage, immutable bundles, pure finalization, idempotent acceptance, minimal targets and locking, one downstream resolver, read-only historical migration feasibility, v1 retirement, phased implementation, measurable complexity reduction, validation, commit, and push, without implementing or executing P9 v2 runtime.
