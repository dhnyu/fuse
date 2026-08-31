# Immutable P9 v2 Run Bundle

Status: `V2_B_IMPLEMENTED`; this specification is descriptive and non-authorizing.

## Layout

```text
p9rb_<24 hex>/
  inventory.json
  commit/run_bundle_manifest.json
  authority/authority_manifest.json
  config/scientific_configuration.json
  runtime/runtime_digest.json
  parents/source_parents.json
  parents/cache_acceptance.json
  contracts/sampler_contract.json
  contracts/selection_contract.json
  ledger/header.json
  ledger/commit/ledger_manifest.json
  ledger/segments/*.jsonl
  summary/training_summary.json
  summary/final_selector_state.json
  summary/stopping_boundary.json
  events/validation_checkpoint_events.json
  checkpoints/checkpoint_inventory.json
  diagnostics/incidents.json
  provenance/source_inventory.json
```

Native V2-B bundles carry `legacy_import = {is_legacy_import: false, annotation: null}` in the commit manifest and do not create a migration file. V2-D may add a canonical legacy annotation under the future importer contract.

Checkpoint payloads and checkpoint manifests remain in immutable external object roots; they are not copied. Their structured locator is:

```json
{
  "backend": "filesystem",
  "location": {"namespace": "checkpoint-store", "relative_path": "objects/<id>/checkpoint.pt"},
  "immutable_object_id": "sha256:<content_sha256>",
  "content_sha256": "<64 hex>",
  "associated_manifest_sha256": "<64 hex>",
  "byte_size": 123,
  "role": "checkpoint_payload",
  "media_type": "application/x-pytorch"
}
```

The namespace and normalized POSIX relative key are canonical logical location. A validator receives the namespace-to-physical-root mapping separately. Absolute paths, `..`, backslashes, unknown backends, content-free object identities, and raw manual path strings are invalid. Moving identical bytes to a new physical root for the same namespace/key does not change bundle identity. Changing the logical key does. Location never substitutes for content verification.

## Required and optional artifacts

All listed native files are required. `diagnostics/incidents.json` is required but may contain an empty array. Ledger segments are copied because they are compact canonical evidence. Large checkpoint payloads and their manifests are hash-referenced. No `targets` metadata, mtime, inode, process identity beyond committed ledger evidence, temporary root, or physical namespace root enters the inventory.

`inventory.json` records every internal evidence file except itself and the commit manifest in ascending canonical relative-path order with size, SHA-256, media type, required flag, and provenance role. Duplicate, reordered, missing, or unexpected entries fail closed. The commit manifest binds the exact canonical inventory bytes by size and SHA-256 and binds an ordered external-object summary by object identity, role, content hash, size, and locator digest. `evaluation_consumption_count` must be exactly zero; held-out identities, paths, samples, metrics, and results are prohibited.

## Identity and publication

1. Build the complete canonical byte set in memory, then write it into a unique same-filesystem `.staging/<bundle-id>.*.incomplete` directory.
2. Validate every required artifact, closed ledger, event chain, external object hash, scientific completion rule, source parent, and evaluation count.
3. Construct the ordered internal inventory and ordered external-object summary. The commit-manifest preimage includes every manifest field except only `bundle_id` and `bundle_content_sha256`.
4. `bundle_content_sha256 = SHA256(V2-A canonical JSON(commit manifest preimage))`.
5. `bundle_id = "p9rb_" + bundle_content_sha256[0:24]`.
6. Insert identity fields, validate again, `fsync` every file and staging directory, and atomically rename the complete staging directory to the identity path. That directory rename is the single logical bundle commit point; the publication root is then `fsync`ed.
7. If the identity path exists, validate exact byte/hash equivalence and return it; never overwrite.

The bundle identity covers schema/run identity, authority, scientific configuration, runtime, parents, cache acceptance, sampler/selection contracts, closed ledger manifest identity (`sha256:<hash>`), manifest hash and events, summaries, validation-checkpoint/checkpoint inventories, selector/stopping evidence, incidents, evaluation count, source inventory, native/legacy annotation, ordered internal inventory, and immutable external references. It excludes directory mtimes, `targets` metadata, host roots, and publication time.

If a canonical path already exists, publication validates it and returns the existing object only when its content hash is identical. Concurrent identical publication produces one creator and one validated reuse. Corrupt or inconsistent destinations fail closed and are never overwritten. Staging debris has no commit path and is non-authoritative; no bundle recovery state machine or bundle lock class exists.

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

V2-B permits publication of structurally valid, scientifically incomplete evidence bundles and labels them `SCIENTIFICALLY_INCOMPLETE`; V2-C finalization must reject them. A complete bundle requires at least one committed validation-checkpoint candidate and exact equality between the final candidate and `TRAINING_COMPLETED` for `completed_epoch`, `resume_epoch`, and `optimizer_update`. `COMPLETE / FINALIZATION_FAILED / NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE` is valid because operational finalization failure does not downgrade science.

## Validation

The standalone validator returns a deterministic structured result containing validity, completeness, bundle identity/hash, all three replay dimensions, evidence errors, replay tail hash, candidate count, source inventory digest, and validation implementation version. It reuses V2-A canonical parsing, schema validation, closed-ledger reading, hash-chain validation, and replay. It verifies every external file's existence, byte size, and SHA-256 on every validation; changing a referenced object invalidates the bundle until the original bytes are restored.

The architecture draft remains [schemas/run_bundle.schema.json](schemas/run_bundle.schema.json). Authoritative runtime schemas are `config/schemas/p9_v2_run_bundle_manifest.schema.json`, `p9_v2_bundle_inventory.schema.json`, and `p9_v2_immutable_locator.schema.json`.
