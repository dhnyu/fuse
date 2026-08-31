# P9 scene identity diagnostic instrumentation and accounting correction

## Verdict

`P9_SCENE_IDENTITY_DIAGNOSTIC_INSTRUMENTATION_AND_ACCOUNTING_CORRECTION_PASS_PUSHED`

This publication improves failure observability and durable terminal accounting
only. It does not reproduce, explain, or scientifically correct the historical
`global scene identity lookup mismatch`; no replacement formal authority,
reservation, attempt, or run was issued.

## Starting Lineage and Preservation

- Fuse start: `b66fa60e456662f5279ac39281a4ca894b035671` on `reduced`.
- Dissertation: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, unchanged.
- Preserved terminal lineage: `p9a_b0c50c956d84a1c3664d7934`,
  `p9res_15556054a164595be7829160`, `p9attempt_25b780995291c86ce49b2182`,
  `p9run_f62cd1d3b2430cd1f0eccc9d`.
- The historical attempt remains `FAILED_NONRESUMABLE`; its directory,
  checkpoints, lock records, logs, and isolated store were not modified.
- Durable historical progress remains epoch 15 / 1,140 updates / three
  validations / three checkpoints. Best observed checkpoint remains
  `p9ck_b8ab1f9dd7da1ea84ed3268d` with loss `0.9153134227` and margin
  `0.1881786585`.

## Evidence Limitation

The preserved failure does not include failing rank-local IDs, gathered IDs,
their lookup multiplicities/order, sampler cursor, or queue operands. A
read-only epoch-15 checkpoint reconstruction reached the two-rank epoch-16
batch-0 gather and contrastive lookup: all 32 gathered IDs were unique, every
lookup multiplicity was one, and all 8,192 queue IDs belonged to the accepted
2,421-scene training population. The original exception did not reproduce.

This means the historical root cause remains unproven. The new implementation
does not infer a cache, queue, sampler, or scientific identity defect from the
generic historical exception.

## Assertion and Identity Domains

`local_infonce_sum()` requires each rank-local current-batch
`scene_numeric_id` to occur exactly once in the rank-major DDP-gathered current
batch. It does not use queue IDs for positive lookup. Cache-entry identity,
realized view identity, base scene identity, rank-local position, and
collective-row position remain distinct domains. The machine-readable map is
external evidence under:

`/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_identity_instrumentation_20260831_165122/identity_domain_map.json`

The classified fail-closed conditions are:

- `CURRENT_BATCH_ID_MISSING`
- `CURRENT_BATCH_ID_DUPLICATE`
- `GATHER_LENGTH_MISMATCH`
- `ID_DOMAIN_MISMATCH`
- `QUEUE_ALIGNMENT_MISMATCH`

They preserve the original one-positive invariant. No ID is reordered,
deduplicated, substituted, or ignored.

## Failure Evidence and Accounting

On invariant failure, every rank atomically writes only the required identity
metadata, tensor shapes/dtypes/checksums, lookup positions, queue metadata,
sampler state, RNG checksums, and lineage. The controller assembles a manifest
which explicitly records `COMPLETE` or `PARTIAL` rank evidence. Capture failure
is appended to, rather than replacing, the classified invariant exception.

Terminal accounting now resolves durable progress in this precedence order:
atomic checkpoint payload/manifest, worker progress, then zero when no durable
source exists. Disagreement is preserved in `accounting_conflict`. The
historical terminal JSON is intentionally not rewritten.

Synthetic recovery verified epoch 15 / update 1,140 / three validations,
queue count 8,192 and pointer 7,424, while preserving a conflicting worker
record as an explicit conflict.

## Bounded Audits

- Optimizer-free two-rank epoch-16 replay: PASS, no historical mismatch.
- 200-epoch identity-only audit: 15,200 updates, 2,200 padded samples,
  972,800 logical queue insertions, 118 expected queue wraps.
- The audit found 14 future rotating-padding groups with a duplicate base scene
  in the same collective (first: epoch 20, batch 75). This is recorded as a
  future diagnostic condition, not asserted as the cause of the historical
  epoch-16 event. Evidence:
  `full_horizon_identity_audit.json` in the same external directory.

## Validation and Non-execution

- Focused Python: 64 passed.
- Full Python: 286 passed.
- Full R/testthat: completed with the documented skips.
- Python compile and R parse: PASS.
- Main and isolated `targets::tar_validate()`: PASS without target execution.
- No formal target was run. Production optimizer updates, formal validations,
  held-out evaluation consumption, production checkpoints, and new formal
  attempts: all 0.
- Production cache, P1-P8 artifacts, historical P9 evidence, main store, and
  dissertation mutations: 0.
- Remaining GPU compute processes and active formal locks: 0.

## Next Authorization Required

A future work unit must explicitly choose either a narrowly proved correction
after new evidence is captured, or an instrumented replacement attempt that
acknowledges the historical failure-time operands are unavailable. It must not
resume or reuse the preserved failed attempt.

## Prompt Summary

This work was limited to diagnostic instrumentation and durable terminal
failure accounting; it did not authorize or execute scientific training.
