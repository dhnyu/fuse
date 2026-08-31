# Immutable P9 v2 Run Bundle

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

## Layout

```text
p9rb_<24 hex>/
  bundle_manifest.json
  authority/authority_manifest.json
  config/scientific_configuration.json
  runtime/runtime_digest.json
  parents/source_parents.json
  parents/cache_acceptance.json
  contracts/sampler_contract.json
  contracts/selection_contract.json
  ledger/ledger_manifest.json
  ledger/segments/*.jsonl
  summary/training_summary.json
  summary/final_selector_state.json
  summary/stopping_boundary.json
  events/validation_checkpoint_events.json
  checkpoints/checkpoint_inventory.json
  diagnostics/incidents.json
  provenance/source_inventory.json
  migration/legacy_import.json              # optional
```

Checkpoint payloads may remain in an immutable external object root. The inventory must record a canonical immutable locator, payload and manifest hashes, size, identity, source run, and atomic-completion evidence. A local relative payload is also allowed. Absolute mutable paths alone are invalid.

## Required and optional artifacts

All listed files except `migration/legacy_import.json` are required. `diagnostics/incidents.json` is required but may contain an empty array. `legacy_import.json` is required for imported v1 evidence and prohibited for native v2 runs.

`bundle_manifest.json` records every file or referenced object in canonical relative-path order with size and SHA-256, schema version, required/optional classification, media type, and provenance role. It also records `evaluation_consumption_count`, which must be zero before P9 acceptance.

## Identity and publication

1. Build the complete directory in a same-filesystem staging root.
2. Validate every required artifact, closed ledger, event chain, external object hash, scientific completion rule, source parent, and evaluation count.
3. Construct a canonical source inventory and manifest excluding only `bundle_id` and `bundle_content_sha256` fields from the preimage.
4. `bundle_content_sha256 = SHA256(canonical bundle manifest preimage)`.
5. `bundle_id = "p9rb_" + bundle_content_sha256[0:24]`.
6. Insert identity fields, validate again, `fsync` files and directories, and atomically rename staging to the identity path.
7. If the identity path exists, validate exact byte/hash equivalence and return it; never overwrite.

The bundle identity covers the ordered content inventory and immutable external references, not directory mtimes, `targets` metadata, host paths, or publication time.

## Completeness rules

A bundle is scientifically complete only when:

- authority, scientific configuration, runtime digest, accepted parents, cache acceptance, and sampler/selection contracts are valid and mutually linked;
- the ledger is closed, hash-contiguous, and contains one valid `TRAINING_COMPLETED` event;
- all progress ranges are non-overlapping and end at the stopping boundary;
- every candidate is a valid `VALIDATION_CHECKPOINT_COMMITTED` event;
- checkpoint payload/manifest hashes and full required state presence pass;
- selector state and early stopping replay exactly;
- stopping boundary is consistent with the contract;
- evaluation consumption is zero;
- source inventory is complete and immutable;
- no unresolved scientific inconsistency or `MISSING_BLOCKING` field exists.

Operational incidents do not invalidate a scientifically complete bundle unless they undermine scientific evidence. An incident such as an epoch-field join exception is recorded without changing the scientific result.

## Validation

The validator returns a deterministic report containing bundle identity, validation status, scientific state, evidence errors, operational warnings, replay tail hash, candidate count, stopping boundary, source inventory digest, and validation implementation version. It reads no target store and writes no bundle content.

The draft schema is [schemas/run_bundle.schema.json](schemas/run_bundle.schema.json).
