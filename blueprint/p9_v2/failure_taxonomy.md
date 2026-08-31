# P9 v1 Failure Taxonomy

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

## Chronology

| Order | Failure | Root category | Consequence | Structural v2 prevention |
|---:|---|---|---|---|
| 1 | Formal authority bound the wrong execution commit; reservation duplicate key omitted authority/execution identity. | Identity contract | Launch blocked and authority republished. | Authority is a content-addressed manifest; run identity binds authority and scientific config exactly. No separate reservation. |
| 2 | Main graph ended at reservation and had no formal runner or terminal DAG. | Orchestration / missing test boundary | An authority existed without an executable completion path. | One coarse controller contract and synthetic end-to-end test must cover bundle through acceptance before authority. |
| 3 | `shortcut = TRUE` could not bootstrap the new formal target because metadata did not exist. | Orchestration / target metadata coupling | Runner never started. | New runs never use target metadata as scientific or bootstrap state; controller is called explicitly. |
| 4 | `shortcut = FALSE` over the main pipeline had an unsafe closure reaching broad upstream work. | Execution isolation | Safe launch could not be proven. | Isolated eight-target graph has literal immutable inputs and a bounded closure. |
| 5 | Isolated formal DAG was introduced as a correction. | Execution isolation | Reduced closure, but duplicated main and isolated control paths remained. | Only the v2 isolated graph is active; v1 graphs are frozen. |
| 6 | Trainer expected `values["vocabulary"]["fields"]` while canonical vocabulary was a direct field mapping. | Data contract / missing test boundary | Formal attempt failed during model construction at zero updates. | Production-shaped scientific input validation is owned by the executor contract and tested before authority issuance. |
| 7 | Historical scene identity lookup failed after epoch 15 because padded global batches could duplicate a base scene. | Scientific computation / identity contract | Attempt failed at epoch 16 after 1,140 updates. | Corrected global-batch uniqueness contract is an immutable scientific parent; bundle records its hash. |
| 8 | Padding selected a scene already in the final partial global batch. | Scientific computation / sampler contract | Positive lookup multiplicity was not guaranteed. | Global batch event/summary records sampler contract and cursor; uniqueness is a precondition, not a recovery check. |
| 9 | Post-training finalizer compared validation epoch `N` with checkpoint resume epoch `N+1`. | Artifact linkage / finalization | Completed epoch-125 trajectory collapsed into `FAILED_NONRESUMABLE`. | One atomic validation-checkpoint event carries `completed_epoch` and `resume_epoch`; finalizer never infers filenames or field equivalence. |
| 10 | First recovery authorization had no terminal recovery/acceptance chain. | Recovery / missing test boundary | Audit passed but authority was not executable. | No special recovery DAG for finalization; pure finalizer is the ordinary path and is tested end to end. |
| 11 | Completed recovery DAG lacked a kernel lock and durable transaction. | Orchestration / recovery | Production recovery was blocked. | Finalizer is lock-free; publisher uses one short acceptance lock with atomic create-or-validate. |
| 12 | Recovery lock prototype lacked complete operation-state transitions, exception semantics, canonical commit validation, and resolver rejection coverage. | Recovery / excessive governance complexity | More authorities and corrections accumulated without acceptance. | Publisher has a single commit manifest and resolver contract; no recovery authority/reservation/operation taxonomy. |

## Architectural diagnosis

The scientific trajectory itself completed correctly through the dissertation stopping boundary. The terminal failure arose because scientific evidence, controller state, target metadata, candidate linkage, finalization, and acceptance were represented in the same state machine and spread across mutable files. Each repair added an authority or recovery layer instead of removing the coupling.

V2 prevents the authority mismatch, target bootstrap, unsafe closure, semantic epoch join, incomplete recovery DAG, recovery lock gap, and recovery transaction gap by construction. Vocabulary and sampler defects remain scientific/data-contract risks; v2 does not make such bugs impossible, but places their validation at an explicit scientific boundary and preserves incomplete evidence without confusing it with controller failure.

## Historical run classification

The v1 record must remain:

```text
FAILED_NONRESUMABLE
```

The same immutable evidence, when imported into independent v2 dimensions, is:

```text
scientific_state  = COMPLETE
operational_state = FINALIZATION_FAILED
resumability      = NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE
```

This is an additive migration interpretation, not a rewrite or a claim that the historical formal run succeeded operationally.
