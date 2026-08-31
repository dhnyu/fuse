# Canonical Run Event Ledger

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

## Storage

Each run owns one ledger directory:

```text
ledger/
  header.json
  segments/
    000000000001-000000000128.jsonl
    000000000129-000000000256.jsonl
  tail.json
  commit/
    ledger_manifest.json
```

Segments are immutable after publication. `tail.json` is an optional replaceable acceleration hint and is never authoritative. `ledger_manifest.json` lists ordered segment path, byte count, first/last sequence, and SHA-256; it is the closed-ledger commit point included in the run bundle.

## Event envelope

Every line is canonical UTF-8 JSON with sorted keys, no insignificant whitespace, and a trailing newline. Required fields are:

```json
{
  "schema_version": "2.0.0-draft",
  "event_type": "RUN_STARTED",
  "event_sequence": 3,
  "event_id": "p9evt_<24 hex>",
  "run_id": "p9runv2_<24 hex>",
  "occurred_at": "RFC3339 UTC",
  "writer": {"writer_id": "...", "role": "controller|rank0|finalizer|publisher"},
  "legacy_import": false,
  "previous_event_hash": "<64 hex or GENESIS>",
  "payload": {},
  "event_hash": "<64 hex>"
}
```

`event_id = "p9evt_" + SHA256(canonical envelope excluding event_id and event_hash)[0:24]`. `event_hash` is SHA-256 of the complete canonical event excluding only `event_hash`. Sequence starts at 1 and increments by one. Every replay verifies run identity, sequence, previous hash, event hash, writer permission, schema, and transition validity.

## Crash-safe append protocol

1. The single run controller obtains the training lock and validates the committed segment tail.
2. The authorized writer creates the next segment or batch in a same-filesystem staging path using `O_CREAT|O_EXCL`.
3. It writes canonical bytes, flushes the file with `fsync`, and verifies sequence/hash continuity by reread.
4. It atomically renames the segment into `segments/` and `fsync`s the directory.
5. It may atomically replace `tail.json`. A crash before segment rename leaves no event; a crash after rename leaves a replayable event even if the hint is stale.
6. At scientific completion, the controller publishes `ledger_manifest.json` by stage, `fsync`, atomic rename, and directory `fsync`. Closed segments are never reopened.

There is one serialized writer boundary per run. Rank workers submit scientific event proposals to rank 0/controller; they do not concurrently append to the canonical ledger.

## Required event types

| Event | Writer | Minimum payload/purpose |
|---|---|---|
| `RUN_AUTHORIZED` | controller | Authority hash, scientific config hash, parent identities, duplicate-run key. |
| `RUN_STARTING` | controller | Owner identity, execution environment digest, lock key. |
| `RUN_STARTED` | controller | Process identity, world size, runtime digest. |
| `EPOCH_STARTED` | scientific rank 0 | Epoch, starting update, sampler cursor. |
| `PROGRESS_SUMMARY_COMMITTED` | scientific rank 0 | Durable update range, exact ending update/cursor, trace block hash. |
| `UPDATE_COMMITTED` | scientific rank 0 | Optional, only when an individual update itself is a configured durable recovery boundary. |
| `VALIDATION_CHECKPOINT_COMMITTED` | scientific rank 0 | Atomic validation/checkpoint linkage defined below. |
| `EARLY_STOPPING_UPDATED` | scientific rank 0 | Selector state, best candidate, non-improvement count, decision basis. |
| `TRAINING_COMPLETED` | scientific rank 0/controller | Exact stopping boundary and completion reason. |
| `TRAINING_INTERRUPTED` | controller | Last durable boundary, interruption cause, checkpoint eligibility. |
| `TRAINING_FAILED` | controller | Failure class/stage and last durable boundary; no science-state collapse. |
| `FINALIZATION_STARTED` | finalizer adapter | Bundle and selection-contract hashes. |
| `FINALIZATION_COMPLETED` | finalizer adapter | Result hash and selected checkpoint identity. |
| `FINALIZATION_FAILED` | finalizer adapter | Stable failure code and evidence class. |
| `ACCEPTANCE_PUBLISHED` | publisher | Acceptance identity, result hash, bundle hash, commit manifest hash. |

## Progress batching

One event per optimizer update is not required. Exact recovery uses checkpointed summaries:

- The scientific executor accumulates update trace records in an immutable compressed block.
- At a configured durability boundary, it flushes and hashes the trace block and appends `PROGRESS_SUMMARY_COMMITTED` with inclusive update range, ending epoch/cursor, sampler-state hash, RNG-state hash, queue summary hash, and trace block hash.
- Every `VALIDATION_CHECKPOINT_COMMITTED` is a full durable boundary and includes exact optimizer update.
- Recovery may resume only from a complete checkpoint named by a committed event. A progress summary without a checkpoint records evidence but is not resumable.

This preserves exact update accounting without forcing synchronous disk I/O for every update.

## Atomic validation-checkpoint event

The event is eligible only after the checkpoint payload and manifest have been atomically committed and hash-verified. Required payload fields are:

```text
completed_epoch, resume_epoch, optimizer_update,
validation_id, checkpoint_id,
checkpoint_payload_sha256, checkpoint_manifest_sha256,
validation_retrieval_loss, mean_source_separation_margin,
selector_state,
queue: {count, pointer, enqueue_count, state_sha256},
sampler: {epoch, cursor, state_sha256},
state_presence: {online_model, ema_model, optimizer, scheduler,
                 rng_states, queue, sampler, early_stopping,
                 best_checkpoint, validation_trace},
atomic_completion_marker,
source_run_id
```

The invariant is explicit: `completed_epoch = N`, `resume_epoch = N + 1`, and `optimizer_update = N * updates_per_epoch` for this contract. The finalizer compares `completed_epoch` only with selection metrics and never infers it from a directory name or `resume_epoch`. A validation with no committed checkpoint event is diagnostic only and is never a candidate.

The draft schema is [schemas/validation_checkpoint_event.schema.json](schemas/validation_checkpoint_event.schema.json).
