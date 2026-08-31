# P9 v2 Decision Log

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D1 | Separate scientific and operational state dimensions. | The epoch-125 trajectory is scientifically complete although controller finalization failed. | Accepted for blueprint. |
| D2 | Use one append-only hash-chained ledger per run. | Removes duplicated mutable counters and makes replay the state authority. | Accepted for blueprint. |
| D3 | Bind validation and checkpoint in one committed event. | Eliminates the v1 `N` versus `N+1` semantic join. | Accepted for blueprint. |
| D4 | Treat the run bundle, not target metadata, as finalizer input. | Makes evidence portable, immutable, and orchestration-independent. | Accepted for blueprint. |
| D5 | Make finalization pure and retryable. | Ordinary post-training failures do not justify a recovery state machine. | Accepted for blueprint. |
| D6 | Use one short acceptance publication lock. | Only canonical publication has a race; finalization is content-addressed. | Accepted for blueprint. |
| D7 | Retain five identity types. | Authority prevents unauthorized execution; run distinguishes trajectories; bundle binds evidence; finalization binds deterministic interpretation; acceptance is downstream commit. | Accepted for blueprint. |
| D8 | Remove reservation, preassigned attempt, operation, recovery authority/reservation, and authorization-acceptance identities. | Their distinguishing data are already bound by authority/run/bundle hashes and locks. | Accepted for blueprint. |
| D9 | Keep `targets` coarse grained with eight targets. | Target metadata is orchestration cache, not mutable scientific state. | Accepted for blueprint. |
| D10 | Permit read-only legacy import with explicit annotations. | Evidence is complete and retraining would add cost without repairing the original scientific trajectory. | Accepted for blueprint. |
| D11 | Preserve v1 `FAILED_NONRESUMABLE` unchanged. | Migration interpretation must not rewrite history or claim operational success. | Accepted for blueprint. |
| D12 | Require every downstream consumer to resolve a v2 acceptance identity. | Prevents manual-path, latest-checkpoint, and uncommitted-artifact use. | Accepted for blueprint. |

## Retained identity justification

| Identity | Race/ambiguity prevented | Creator | Immutable point | Binds | Consumers |
|---|---|---|---|---|---|
| Execution authority | Unauthorized or scientifically different launch | Authority publisher | Atomic authority publication | Scientific config, parents, runtime policy, allowed run key | Controller |
| Run identity | Confusion between independent trajectories/resumes | Controller deterministically from authority + run nonce/policy | `RUN_AUTHORIZED` | Authority, scientific config, seed, duplicate key | Ledger, bundle |
| Run-bundle identity | Evidence substitution | Bundle builder | Bundle atomic publication | Complete ordered evidence inventory | Finalizer, audit |
| Finalization identity | Selection interpretation drift | Pure finalizer | Result create-or-validate | Bundle, selection contract, finalizer version | Publisher, audit |
| Acceptance identity | Duplicate or ambiguous downstream commit | Publisher | Acceptance manifest atomic rename | Authority, bundle, finalization result | Resolver and all downstream consumers |

## Unresolved implementation decisions

These do not block the architecture verdict but must be closed in the named unit:

- V2-A: canonical JSON number encoding and segment size/frequency.
- V2-B: immutable locator backend syntax and whether checkpoint payloads are copied or hash-referenced.
- V2-C: location and format of the authority eligibility/supersession index.
- V2-D: hardened legacy PyTorch deserialization strategy.
- V2-H: precise heartbeat interval, interruption policy, and configurable progress-summary cadence after I/O pilot.
