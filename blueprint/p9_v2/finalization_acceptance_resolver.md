# Finalization, Acceptance, Locking, and Resolution

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

## Pure deterministic finalizer

Conceptual API:

```text
finalize(run_bundle_hash, selection_contract_hash) -> finalization_result
```

Inputs are content hashes, resolved through immutable content-addressed storage:

```json
{
  "run_bundle_hash": "<64 hex>",
  "selection_contract_hash": "<64 hex>",
  "finalizer_schema_version": "2.0.0-draft",
  "finalizer_implementation_hash": "<64 hex>"
}
```

The selection contract contains validation interval, primary metric/direction, `0.0001` equivalence threshold, margin tie breaker, earlier-epoch final tie break, early-stopping reset rule, patience four, and candidate eligibility rule.

The finalizer validates the bundle, takes candidates only from committed `VALIDATION_CHECKPOINT_COMMITTED` events, replays selector and early stopping, proves the stopping boundary, and emits:

```json
{
  "schema_version": "2.0.0-draft",
  "finalization_id": "p9fin_<24 hex>",
  "status": "PASS|FAIL",
  "failure_code": null,
  "evidence_class": "VALID_SCIENTIFIC_EVIDENCE|INVALID_SCIENTIFIC_EVIDENCE|OPERATIONAL_FAILURE",
  "run_bundle_id": "p9rb_<24 hex>",
  "run_bundle_hash": "<64 hex>",
  "selection_contract_hash": "<64 hex>",
  "candidate_set_hash": "<64 hex>",
  "selected_checkpoint": {},
  "selected_validation_metrics": {},
  "recomputed_selector_state": {},
  "stopping_summary": {},
  "evaluation_consumption_count": 0,
  "provenance_chain": [],
  "finalization_result_hash": "<64 hex>"
}
```

`finalization_id` and result hash are derived from canonical inputs and output excluding the identity/hash fields. The finalizer has no clock field in hashed output. Diagnostics may carry a separate non-authoritative invocation record.

Stable failure codes include `BUNDLE_NOT_FOUND`, `BUNDLE_HASH_MISMATCH`, `SCIENTIFICALLY_INCOMPLETE`, `LEDGER_INVALID`, `CANDIDATE_SET_EMPTY`, `CHECKPOINT_INTEGRITY_INVALID`, `SELECTOR_REPLAY_MISMATCH`, `STOPPING_BOUNDARY_MISMATCH`, `EVALUATION_ALREADY_CONSUMED`, and `SCHEMA_UNSUPPORTED`. Invalid scientific evidence is distinguished from an ordinary read/IO/process failure.

The finalizer imports no GPU library, trainer, validation/evaluation loader, optimizer, or checkpoint writer. It performs no training, validation, checkpoint write, evaluation access, authority mutation, or bundle mutation. It requires no training lock. The same inputs and implementation version produce byte-identical output. A cached result uses atomic create-or-validate by finalization identity.

The draft schema is [schemas/finalization_result.schema.json](schemas/finalization_result.schema.json).

## Acceptance publisher

Conceptual API:

```text
publish_acceptance(finalization_result_hash, run_bundle_hash, authority_hash)
```

Publication steps:

1. Validate all three immutable inputs and require a `PASS` finalization result with zero evaluation consumption.
2. Compute the acceptance preimage and `acceptance_id = "p9accv2_" + SHA256(preimage)[0:24]`.
3. Acquire a nonblocking kernel `flock` scoped to that acceptance identity.
4. If a canonical directory exists, validate its manifest and exact input bindings and return it.
5. Otherwise write `acceptance.json` and `acceptance_commit_manifest.json` to a same-filesystem staging directory, flush, verify, atomically rename to the identity directory, and `fsync` its parent.
6. Release the lock. A collision with different bytes fails closed.

The atomic rename exposing `acceptance_commit_manifest.json` at the canonical identity path is the acceptance commit point. There is one canonical acceptance per identity. No heartbeat is used because publication is bounded and short. Acceptance does not modify the run bundle or finalization result and does not read target metadata.

The draft schema is [schemas/acceptance.schema.json](schemas/acceptance.schema.json).

## Lock classes

| Lock | Scope | Lifetime | Records | Recovery semantics |
|---|---|---|---|---|
| Training | Duplicate-run key | Entire controller lifetime | Kernel lock plus owner and periodic heartbeat evidence | Kernel releases on death; exact resume is a new controller invocation under explicit policy. |
| Acceptance publication | Acceptance identity | One atomic publication | Kernel lock; optional one-shot owner record | Retry create-or-validate. No state machine or heartbeat. |

The finalizer normally needs no lock. Content-addressed cache writes use `O_EXCL` or staging plus atomic rename and validate an existing result.

## Why the v1 recovery transaction disappears

V1 recovery combined source validation, candidate linkage, selection, recovery authority, reservation, operation ownership, mutable operation state, terminal publication, acceptance, and resolution. In v2, the atomic scientific event eliminates the linkage repair; the immutable bundle is the sole finalizer input; the finalizer is retryable and pure; and the publisher has one short commit. Finalization failure therefore means rerun the same function, not create a new attempt or recovery DAG.

## Canonical resolver

```text
resolve_accepted_checkpoint(acceptance_identity)
```

The resolver validates the canonical acceptance directory and commit manifest, acceptance status, authority eligibility, finalization result hash, bundle hash and completeness, checkpoint inventory linkage, payload/manifest hashes, and supersession/revocation index. It returns:

```json
{
  "acceptance_identity": "p9accv2_<24 hex>",
  "run_bundle_identity": "p9rb_<24 hex>",
  "selected_checkpoint_identity": "p9ck_<24 hex>",
  "payload_locator": "immutable://...",
  "payload_sha256": "<64 hex>",
  "manifest_sha256": "<64 hex>",
  "selected_validation_metrics": {
    "completed_epoch": 105,
    "validation_retrieval_loss": 0.3806893528,
    "mean_source_separation_margin": 0.2876026034
  },
  "stopping_summary": {},
  "scientific_configuration": {},
  "provenance_chain": []
}
```

It rejects missing/uncommitted manifests, non-PASS results, incomplete bundles, superseded or revoked acceptance, hash mismatch, path-only input, and mutable locator. P9-B, selected-FM, held-out evaluation, P10, and P11 must call this resolver. Their public APIs must accept an acceptance identity, never a checkpoint path.
