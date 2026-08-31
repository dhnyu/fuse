# P9 Recovery Production Controller Transaction Integration

## Verdict

`P9_RECOVERY_PRODUCTION_CONTROLLER_TRANSACTION_INTEGRATION_PASS_PUSHED`

This is a bounded controller-integration result only. It does not authorize or
execute production recovery, create a recovery authority, reservation, or
operation, or alter the historical formal failure.

## Scope and Inputs

- Fuse implementation start: `0f37a2ecae21081cfd4d4202cb1a6dc8ec37dc5d`
- Dissertation input: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`
- Source formal lineage remained immutable: `p9a_9d6f0554553ac43371b47efd`,
  `p9res_0f5492c80e7c152e6c543012`,
  `p9attempt_a754afd14ac87287afb04029`, and
  `p9run_6887930091dd2f2bfedc3c96`.
- Historical state remains `FAILED_NONRESUMABLE`; the completed scientific
  trajectory remains epoch 125/update 9,500 with 25 validation/checkpoint
  pairs and zero held-out evaluation consumption.

No methodology, model, sampler, validation metric, scientific artifact, or
dissertation file was changed.

## Controller Integration

The sole production transaction entry remains `execute()` in
`scripts/p9_checkpoint_recovery_authorization.py`, invoked only from
`p9r_execute_terminal()` and therefore
`p9_cfg_main_terminal_recovery`. It now constructs one `TransactionContext`
after token and immutable authorization agreement, then uses one
`RecoveryTransactionController` for every canonical publication path.

The context binds authority, reservation, operation, duplicate key,
source-inventory digest, runtime/DAG digests, terminal target, store, lock
root, owner/heartbeat/state paths, staging path, final transaction path,
transaction ID, launch commit, and synthetic/production mode. Helpers no
longer independently derive publication paths.

Observed synthetic success sequence:

1. `ACQUIRING_LOCK`
2. `STARTING`
3. `VALIDATING_SOURCE`
4. `DERIVING_CANDIDATES`
5. `SELECTING_CHECKPOINT`
6. `RECONSTRUCTING_STOPPING_BOUNDARY`
7. `STAGING_TERMINAL_RECOVERY`
8. `STAGING_ACCEPTANCE`
9. `COMMITTING`
10. `RECOVERY_ACCEPTED`

Source validation checks exact failed lineage, immutable terminal-failure
hash/state, 25 joined candidates, zero evaluation, deterministic epoch-105
selection, and the epoch-125/update-9,500 patience-four stopping contract.
The selection is recomputed rather than overridden.

## Commit and Failure Semantics

The kernel lock is acquired before any operation state, staging, terminal, or
acceptance path is created. `STARTING` is the durable operation-start boundary.
Every transition atomically persists `OperationState` and updates the
recovery-only heartbeat. Owner/heartbeat files document the descriptor owner;
they never establish ownership themselves.

Terminal and acceptance artifacts are written only under a same-filesystem
staging directory. Their hashes, candidate digest, selection digest, stopping
digest, source digest, and recovery lineage are bound by
`transaction_manifest.json`. Atomic publication of that directory exposes the
manifest with the payload pair; `resolve_committed()` treats no staged or
payload-only artifact as canonical. It rechecks payload hashes and exact
context identity before returning an acceptance.

Pre-commit exceptions after `STARTING` transition to
`RECOVERY_FAILED_NONMUTATING`, preserve the original exception, publish no
canonical manifest, and release the lock with its actual outcome. A failure
after a canonical manifest is present is recorded as a post-commit integrity
incident and does not delete or downgrade the committed transaction.

## Focused Tests

- `tests/python/test_p9_checkpoint_recovery.py`: 9 passed.
- The synthetic entry-point integration exercised exact token validation, lock
  acquisition, all ten states, 25 exact matches, deterministic epoch-105
  selection, stopping reconstruction, staged pair, commit-manifest resolver,
  release, and canonical readback.
- Token mismatch was rejected before lock, state, staging, or output creation.
- Pre-commit exception ended in `RECOVERY_FAILED_NONMUTATING` with no resolver
  result.
- A simulated post-commit bookkeeping error left the manifest-resolvable
  transaction accepted.
- Full Python suite: 295 passed.
- Full R/testthat suite passed with its documented skips.
- Python compilation, R parsing, main and recovery `tar_validate()`, and
  `git diff --check` passed. These validations did not execute a recovery
  terminal target.

The recovery target closure remains the 11-target recovery-only graph. No
formal trainer, DDP, CUDA, optimizer, validation runner, evaluation runner,
checkpoint writer, cache builder, or main research store is reached by the
controller code path.

## Prohibited-Work and Immutability Accounting

- New authorities/reservations/operations: 0/0/0
- Production recovery operations/terminal recoveries/acceptances: 0/0/0
- Optimizer, EMA, scheduler updates: 0/0/0
- Validation/evaluation/checkpoint writes: 0/0/0
- DDP/GPU launches: 0/0
- Cache and historical-source mutations: 0/0
- Active recovery/formal controllers, GPU compute processes, and locks at
  completion: 0/0/0

The historical failed run, previous recovery lineages, target stores,
production cache, P1-P8 inputs, and dissertation were only read or inspected.

## Deferred Work

This bounded work unit intentionally does not complete the hard-process crash
matrix or the exhaustive resolver rejection matrix. Those tests, followed by a
separate reauthorization work unit, remain required before production recovery
can be considered executable. No existing authority is executable as a result
of this change.

## Prompt Summary

Integrate the production recovery controller with the durable transaction core,
test it only with synthetic/copy-backed fixtures, and do not execute or
reauthorize production recovery.
