# P9 Recovery Resolver Rejection Matrix Validation

## Verdict

`P9_RECOVERY_RESOLVER_REJECTION_MATRIX_COMPLETION_AND_VALIDATION_BLOCKED_PUSHED`

The implementation and synthetic matrix harness are preserved, but this work
unit cannot claim the required full validation because an unrelated pytest
controller has remained active since 2026-08-23. It was not signalled,
attached to, or treated as this work unit's test result.

## Preserved Worktree Inventory

The inherited uncommitted changes were preserved and extended:

- `python/p9_recovery_transaction.py`: synthetic-only hard crash hook,
  20 named controller boundaries, transaction manifest identity bindings, and
  stricter context/path/lineage/counter resolver checks.
- `tests/python/test_p9_checkpoint_recovery.py`: controller regression tests.
- `tests/python/test_p9_recovery_hard_crash.py`: fresh-root child-process
  matrix using `os._exit(86)` and table-driven resolver mutations.

No existing crash harness was discarded or recreated. No production path can
set a hard-crash hook: `TransactionContext.create()` rejects it unless
`synthetic=True`, and the normal recovery CLI has no fault-injection option.

## Completed Bounded Evidence

- Focused recovery and hard-crash tests: 58 passed.
- Hard crashes: 20 named boundaries, each from an independent child process.
  Pre-commit boundaries produce no resolvable canonical recovery; post-commit
  boundaries remain resolvable through the manifest. Parent inspection
  reacquired the duplicate-key kernel lock after every child death.
- Resolver table currently covers manifest identity/runtime/store mutations,
  payload/hash/presence failures, source-lineage, selection, stopping,
  candidate-digest, prohibited-counter, and acceptance-link failures.
- Resolver calls were checked as read-only for terminal, acceptance, and
  commit-manifest hashes/mtimes; duplicate completion rejected a second staged
  transaction without rewriting canonical payloads.

## Remaining Required Before PASS

The exhaustive condition checklist requested by this work unit remains
incomplete: individual source-progress, checkpoint-integrity, metric,
per-counter, state, and adapter cases require separate rows with outer hashes
recomputed where needed. A separately owned, nonoverlapping full Python suite
also remains mandatory, followed by the full R/testthat suite and validation
commands.

## Prohibited Work Accounting

Production recovery operations, terminal recoveries, acceptances, authorities,
reservations, and operations: 0. Optimizer/EMA/scheduler updates,
validation/evaluation, checkpoint writes, DDP/GPU launches, cache writes, and
historical source mutations: 0.

## Next Authorized Work

After the unrelated pytest process exits or a nonoverlapping validation window
is available, complete every independent resolver matrix row, rerun all 20
hard-crash boundaries, run owned full Python and R suites, then reassess
reauthorization. Production recovery remains unauthorized.
