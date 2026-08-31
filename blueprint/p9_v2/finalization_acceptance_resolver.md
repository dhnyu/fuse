# Finalization, Acceptance, Locking, and Resolution

Status: `V2_EF_IMPLEMENTED_REFERENCE_NON_AUTHORIZING`

Runtime implementations are `python/p9_v2_finalization.py`,
`python/p9_v2_acceptance.py`, and `python/p9_v2_downstream.py`. Runtime schemas
are under `config/schemas/`.

## Pure deterministic finalizer

Conceptual API:

```text
finalize_run_bundle(bundle_locator, locator_roots, selection_contract_hash) -> finalization_result
```

Inputs are content hashes, resolved through immutable content-addressed storage:

```json
{
  "run_bundle_hash": "<64 hex>",
  "selection_contract_hash": "<64 hex>",
  "finalizer_schema_version": "2.0.0",
  "finalizer_implementation_hash": "<64 hex>"
}
```

The selection contract is `p9-selection-v2.1.0`: validate every five epochs;
minimize validation retrieval loss; treat the absolute loss difference as
equivalent only when it is strictly less than the binary64 value of `0.0001`;
then maximize mean source-separation margin; then retain the earlier completed
epoch. Checkpoint selection and patience are separate decisions: a margin-only
tie-break may replace the selected checkpoint, while patience resets only when
retrieval loss decreases by at least the binary64 tolerance. Patience is four.
Comparison promotes the canonical binary64 operands losslessly with
`Decimal.from_float()` before arithmetic. MRR is not an input.

The finalizer validates the bundle, takes candidates only from committed `VALIDATION_CHECKPOINT_COMMITTED` events, replays selector and early stopping, proves the stopping boundary, and emits:

```json
{
  "schema_version": "2.0.0",
  "finalization_id": "p9fin_<24 hex>",
  "status": "SUCCEEDED|FAILED",
  "failure_code": null,
  "evidence_class": "VALID_SCIENTIFIC_EVIDENCE|INVALID_SCIENTIFIC_EVIDENCE",
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

Stable evidence failure codes are `BUNDLE_INVALID`, `BUNDLE_NOT_FOUND`,
`SCIENTIFICALLY_INCOMPLETE`, `SELECTION_CONTRACT_MISMATCH`,
`NO_ELIGIBLE_CANDIDATE`, `SELECTOR_REPLAY_MISMATCH`,
`STOPPING_SUMMARY_MISMATCH`, `CHECKPOINT_INVENTORY_MISMATCH`,
`SOURCE_PROVENANCE_MISMATCH`, and `UNSUPPORTED_SCHEMA_VERSION`. Publication or
filesystem exceptions are operational failures outside the deterministic
scientific result taxonomy and do not become training failures.

The finalizer imports no GPU library, trainer, validation/evaluation loader, optimizer, or checkpoint writer. It performs no training, validation, checkpoint write, evaluation access, authority mutation, or bundle mutation. It requires no training lock. The same inputs and implementation version produce byte-identical output. A cached result uses atomic create-or-validate by finalization identity.

The runtime schema is
[`config/schemas/p9_v2_finalization_result.schema.json`](../../config/schemas/p9_v2_finalization_result.schema.json).

## Acceptance publisher

Conceptual API:

```text
publish_acceptance(finalization_result_hash, run_bundle_hash, authority_hash)
```

Publication steps:

1. Validate all three immutable inputs and require a `PASS` finalization result with zero evaluation consumption.
2. Compute the acceptance preimage and `acceptance_id = "p9accv2_" + SHA256(preimage)[0:24]`.
3. Acquire a bounded kernel `flock` scoped to that acceptance identity.
4. If a canonical directory exists, validate its manifest and exact input bindings and return it.
5. Otherwise write `acceptance.json`, an exact canonical copy of
   `finalization_result.json`, and
   `commit/acceptance_commit_manifest.json` to a same-filesystem staging
   directory, flush, reread, verify, atomically rename the directory to the
   identity path, and `fsync` its parent.
6. Release the lock. A collision with different bytes fails closed.

The atomic directory rename exposing `acceptance_commit_manifest.json` at the
canonical identity path is the acceptance commit point. Before rename, staging
is ignorable non-authoritative debris. After rename, the acceptance is immutable.
The protocol establishes the implemented POSIX file/directory `fsync` sequence;
power-loss behavior still depends on the mounted filesystem honoring those
operations. There is one canonical acceptance per identity. No heartbeat is
used because publication is bounded and short. Acceptance does not modify the
run bundle or finalization result and does not read target metadata.

The runtime union schema is
[`config/schemas/p9_v2_acceptance.schema.json`](../../config/schemas/p9_v2_acceptance.schema.json).

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

The V2-C resolver core validates the canonical acceptance directory and commit
manifest, authority binding, finalization result hash, bundle hash and
scientific completeness, checkpoint inventory linkage, and current external
payload/manifest bytes. V2-E configures this core with one immutable,
content-addressed eligibility snapshot. The snapshot is canonical JSON, has
sorted unique acceptance entries, and records each as `ELIGIBLE`, `SUPERSEDED`,
or `REVOKED` with exact authority identity/hash. Missing or ambiguous entries
fail as unresolved. It is evidence, not a new authority type or mutable registry,
and V2-E adds no publisher for it. The configured resolver exposes
`resolve_accepted_checkpoint(acceptance_identity)` with no path argument and
returns an immutable result record:

```json
{
  "acceptance_identity": "p9accv2_<24 hex>",
  "run_bundle_identity": "p9rb_<24 hex>",
  "selected_checkpoint_identity": "p9ck_<24 hex>",
  "payload_locator": {"backend": "filesystem", "location": {}},
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

It rejects missing/uncommitted manifests, unsuccessful results, incomplete
bundles, every hash/binding mismatch, unresolved locator namespaces, modified
external artifacts, path-only input, `latest`, and legacy recovery identities.
`python/p9_v2_downstream.py` is the sole consumer adapter. P9-B, selected-FM,
held-out evaluation, P10, and P11 all call the same configured resolver and
receive the same `AcceptedCheckpoint`. Their public APIs accept an acceptance
identity, never a checkpoint, bundle, finalization, recovery, or filesystem
path. There is no `latest` or manual fallback.
