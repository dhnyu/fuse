# Scientific and Operational State Model

Status: `V2_A_IMPLEMENTED`; this specification is descriptive and non-authorizing.

## Independent dimensions

Scientific state is derived only from committed scientific events and artifacts.

| State | Definition |
|---|---|
| `NOT_STARTED` | No scientific update has been durably committed. |
| `IN_PROGRESS` | At least one progress boundary exists, but no valid completion event exists. |
| `COMPLETE` | `TRAINING_COMPLETED` is supported by a coherent stopping boundary and all required committed evidence. |
| `INCOMPLETE` | Training ended or failed without evidence satisfying the scientific completion contract. |

Operational state records controller/publication progress independently.

| State | Definition |
|---|---|
| `AUTHORIZED` | Immutable authority is valid; no controller start committed. |
| `STARTING` | Controller owns the training lock and is preparing the process. |
| `RUNNING` | Scientific executor started and may append scientific events. |
| `FINALIZING` | Run bundle is complete and pure finalization is underway. |
| `ACCEPTED` | Canonical acceptance commit manifest is atomically visible. |
| `INTERRUPTED_RESUMABLE` | Controller stopped and the latest committed checkpoint passes exact-resume policy. |
| `TRAINING_FAILED` | Scientific execution terminated by a non-interruption failure. |
| `FINALIZATION_FAILED` | Scientific completion exists, but bundle construction/finalization did not complete. |
| `BLOCKED` | Preconditions fail before safe progress; reason is explicit and no scientific inference is made. |

Resumability is a field derived from the latest committed checkpoint and policy:

```text
NOT_APPLICABLE | EXACT_RESUME_ALLOWED | RESTART_REQUIRED |
NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE | FORBIDDEN_POLICY | EVIDENCE_INVALID
```

It is never a substitute for either state dimension.

## Valid combination matrix

`Y` is valid, `C` is conditionally valid, and `-` is invalid.

| Scientific \ Operational | AUTHORIZED | STARTING | RUNNING | FINALIZING | ACCEPTED | INTERRUPTED_RESUMABLE | TRAINING_FAILED | FINALIZATION_FAILED | BLOCKED |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `NOT_STARTED` | Y | Y | C | - | - | - | - | - | Y |
| `IN_PROGRESS` | - | - | Y | - | - | Y | C | - | C |
| `COMPLETE` | - | - | C | Y | Y | - | - | Y | C |
| `INCOMPLETE` | - | - | - | - | - | C | Y | - | C |

Conditions:

- `NOT_STARTED/RUNNING` is transient only between process start and the first durable scientific event.
- `IN_PROGRESS/TRAINING_FAILED` means failure occurred after durable work but before the completion contract.
- `COMPLETE/RUNNING` is transient while the controller closes the ledger and starts bundle publication.
- `COMPLETE/BLOCKED` is allowed when an external acceptance prerequisite fails; it must not downgrade science.
- `INCOMPLETE/INTERRUPTED_RESUMABLE` is allowed when a valid exact-resume checkpoint exists but a completion event does not.

## Transition ownership

Scientific state changes are replay results, not mutable assignments. `EPOCH_STARTED`, progress summaries, atomic validation-checkpoint commits, interruption/failure, and `TRAINING_COMPLETED` determine it. Operational transitions are explicit ledger events emitted by the controller/finalizer/publisher. A replayed state snapshot may be cached, but it is disposable and must carry the ledger tail hash used to derive it.

The historical import creates legacy-marked events whose derivation metadata points to immutable v1 evidence. It does not edit `attempt_state.json` or `terminal_failure.json`.

## V2-A replay transition table

| Event | Required predecessor | Scientific result | Operational result | Resumability result |
|---|---|---|---|---|
| `RUN_AUTHORIZED` | First event | `NOT_STARTED` | `AUTHORIZED` | `NOT_APPLICABLE` |
| `RUN_STARTING` | `AUTHORIZED`, or exact-resume interruption | unchanged | `STARTING` | unchanged, or reset on resume |
| `RUN_STARTED` | `STARTING` | `IN_PROGRESS` | `RUNNING` | `NOT_APPLICABLE` |
| Epoch/progress/update/validation-checkpoint/early-stop | active `IN_PROGRESS/RUNNING` | `IN_PROGRESS` | `RUNNING` | unchanged |
| `TRAINING_COMPLETED` | active `IN_PROGRESS/RUNNING` | `COMPLETE` | `RUNNING` until finalization begins | `NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE` |
| `TRAINING_INTERRUPTED` with matching latest committed checkpoint and exact policy | active training | `IN_PROGRESS` | `INTERRUPTED_RESUMABLE` | `EXACT_RESUME_ALLOWED` |
| `TRAINING_INTERRUPTED` with matching checkpoint but prohibited policy | active training | `IN_PROGRESS` | `BLOCKED` | `FORBIDDEN_POLICY` |
| `TRAINING_INTERRUPTED` without one | active training | `INCOMPLETE` | `BLOCKED` | `RESTART_REQUIRED` |
| `TRAINING_FAILED` | active training | `INCOMPLETE` | `TRAINING_FAILED` | exact resume only for matching committed checkpoint; otherwise restart |
| `FINALIZATION_STARTED` | complete science | `COMPLETE` | `FINALIZING` | scientifically complete |
| `FINALIZATION_COMPLETED` | finalizing and selected committed checkpoint exists | `COMPLETE` | `FINALIZING` | scientifically complete |
| ordinary `FINALIZATION_FAILED` | finalizing | `COMPLETE` | `FINALIZATION_FAILED` | scientifically complete |
| invalid-evidence `FINALIZATION_FAILED` | finalizing | `INCOMPLETE` | `BLOCKED` | `EVIDENCE_INVALID` |
| `ACCEPTANCE_PUBLISHED` | completed finalization | `COMPLETE` | `ACCEPTED` | scientifically complete |

Illegal transitions fail closed. Strict replay raises an error; diagnostic replay returns `INCOMPLETE/BLOCKED/EVIDENCE_INVALID` with validation reasons. Identical committed bytes produce identical replay output. V2-A does not implement finalization or publication business logic; their events exist only to make the independent state model complete.
