# P9 v2 V2-B Immutable Run-Bundle Implementation

## Verdict

`P9_V2_B_RUN_BUNDLE_PASS_PUSHED` is the publication verdict contingent on the final scoped rerun, commit, push, clean-tree/origin check, and post-push immutable hash readback recorded in the final response. All V2-B contracts and pre-publication validations passed.

## Purpose and lineage

- Executed at: 2026-09-01 00:08 Asia/Seoul.
- Scope: V2-B canonical run-bundle schema, immutable locators, deterministic construction, content identity, atomic publication, standalone validation, and synthetic tests only.
- Fuse start: `reduced@b5e0f421b42cd230e672b72f3eab74f952f044d9`, clean, origin ahead/behind `0/0`.
- Dissertation: `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, clean, origin ahead/behind `0/0`.
- Fuse ending HEAD: the commit containing this report; the final response records its exact SHA because a commit cannot contain its own SHA.
- Input prompt summary: implement only immutable synthetic V2-B bundles over authoritative V2-A evidence; do not start finalization, acceptance, resolution, import, training, evaluation, or target activation.

The active P9 blueprint, V2-A report/runtime, and dissertation methodology were read. No methodology conflict was found. The dissertation was not modified.

## Files and architecture

Added runtime implementation:

- `python/p9_v2_bundle.py`
- `config/schemas/p9_v2_immutable_locator.schema.json`
- `config/schemas/p9_v2_bundle_inventory.schema.json`
- `config/schemas/p9_v2_run_bundle_manifest.schema.json`

Added synthetic test support and tests:

- `tests/python/p9_v2_bundle_test_support.py`
- `tests/python/test_p9_v2_bundle_schema_locator.py`
- `tests/python/test_p9_v2_bundle_build_validate.py`
- `tests/python/test_p9_v2_bundle_publication_corruption.py`

V2-A received one bounded reuse improvement: `p9_v2_canonical.py` now exposes the canonical byte parser, and `p9_v2_ledger.py` calls it instead of owning a private parser. Existing write-all and directory-`fsync` primitives received public names for bundle publication reuse. `p9_v2_schema.py` registers the three V2-B schemas, and the V2-A schema test now asserts its required subset rather than freezing the global registry size.

The blueprint README, run-bundle specification, roadmap, decision log, and risk register record only the now-closed V2-B choices. No target definition or runtime digest list changed.

## Immutable locator contract

The only V2-B backend is `filesystem`. A locator contains:

- canonical namespace and normalized POSIX relative key;
- `immutable_object_id = "sha256:" + content_sha256`;
- content SHA-256 and byte size;
- checkpoint payload or manifest role and media type;
- associated manifest SHA-256 for checkpoint payloads.

The namespace-to-physical-root mapping is supplied to validation and is excluded from bundle bytes. Absolute paths, traversal, backslashes, unknown backends, ambiguous object identities, and raw path strings fail closed. Every validation resolves safely beneath the supplied root and rereads size/hash. A physical root relocation that retains namespace/key and bytes preserves identity and validity.

## Copy-versus-reference decision

Canonical ledger header, segments, closed manifest, scientific contracts, summaries, event evidence, inventories, and diagnostics are copied into the bundle. Large checkpoint payloads and their manifests are not copied; they remain external structured, hash-bound objects. This prevents multi-GB duplication and makes cache copies or physical-root relocation irrelevant to scientific identity while retaining byte verification.

## Inventory and bundle identity

`inventory.json` lists every internal evidence file except itself and the commit manifest. Entries are sorted by canonical relative path and bind required status, media type, byte size, SHA-256, and provenance role. Validation-checkpoint records sort by completed epoch and checkpoint identity; source records sort by logical path; external summaries sort by role, object identity, and locator digest. Caller insertion and filesystem enumeration order are irrelevant.

The commit-manifest preimage binds schema/run identity, authority, scientific configuration, runtime, accepted parents, cache acceptance, sampler/selection contracts, closed-ledger manifest identity (`sha256:<hash>`) and hash, replayed states, training summary, validation-checkpoint and checkpoint inventories, selector/stopping evidence, incidents, evaluation count, source inventory, legacy annotation, internal inventory hash, and external-object summaries. It excludes only `bundle_id` and `bundle_content_sha256`.

```text
bundle_content_sha256 = SHA256(V2-A canonical JSON(commit manifest preimage))
bundle_id = "p9rb_" + bundle_content_sha256[0:24]
```

No mtime, inode, directory enumeration order, process ID outside committed evidence, temporary root, physical artifact root, target metadata, target currentness, or mutable helper state enters this preimage.

## Layout and publication

The bundle includes `inventory.json`, structured evidence directories, a complete copied `ledger/`, and `commit/run_bundle_manifest.json`. Publication writes a unique same-filesystem `.staging/<bundle-id>.*.incomplete` directory using exclusive file creation, file `fsync`, canonical reread/validation, and directory `fsync`.

Atomic rename of the complete staging directory to `<publication-root>/<bundle-id>` is the single logical bundle commit point, followed by publication-root `fsync`. Before rename, staging is non-authoritative. After rename, bytes are immutable. No recovery manager, mutable bundle status, or bundle lock class exists.

An existing valid identity path with the same full content hash is validated and returned. Sequential and concurrent identical attempts therefore converge. Corrupt, incomplete, or inconsistent existing destinations fail closed and are not overwritten.

## Validator behavior

`validate_run_bundle()` returns a deterministic structured result rather than only a boolean. It distinguishes `VALID` complete, `VALID` scientifically incomplete, and `INVALID/EVIDENCE_INVALID`, with stable error codes and replay/provenance fields.

Validation checks canonical JSON, Draft 2020-12 schemas, identity/name/hash, inventory ordering and uniqueness, exact allowed members, internal size/hash, bound evidence document hashes, authority/config/runtime/parent linkage, closed V2-A ledger and manifest hash, V2-A replay, exact committed validation-checkpoint inventory, external payload/manifest locators and bytes, source inventory/digest, selector/stopping evidence, evaluation isolation, and replayed state agreement. It does not deserialize PyTorch objects.

## Scientific completeness

Structurally coherent interrupted or failed evidence may be published as `SCIENTIFICALLY_INCOMPLETE`; V2-C must reject it for finalization. A complete bundle requires at least one committed validation-checkpoint candidate and exact equality between the last candidate and `TRAINING_COMPLETED` for completed epoch, resume epoch, and optimizer update.

The tested historical-style state remains valid:

```text
scientific = COMPLETE
operational = FINALIZATION_FAILED
resumability = NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE
bundle = SCIENTIFICALLY_COMPLETE
```

Operational finalization failure therefore does not rewrite or downgrade scientific evidence.

## Target independence

Synthetic target metadata was created beside the evidence, the candidate was built, that metadata was deleted, and the candidate was rebuilt. Canonical files, content hash, and bundle ID remained identical. Bundle runtime imports no R `targets` API, reads no target store, and has no target-currentness input. Corrupt ledger tail hints and staging debris likewise do not change identity.

## Synthetic cases

- Normal complete run: two committed validation-checkpoint events, selector updates, exact stopping boundary.
- Complete/finalization-failed run: accepted as scientifically complete.
- Exact-resume interruption: valid scientifically incomplete bundle.
- Training failure without checkpoint: valid scientifically incomplete bundle.
- Evaluation or target-metadata contamination: rejected.
- Completion boundary beyond final committed checkpoint: rejected.
- Standalone validation or extra checkpoint without committed event: rejected.

All ledgers were created and closed through the actual V2-A writer. All payloads, manifests, publications, mutations, and relocations were temporary synthetic filesystem fixtures.

## Determinism and portability

Repeated builds produced identical file maps, bundle hashes, and IDs. Reordered source/checkpoint input maps produced identical bytes. Equivalent fixtures under different temporary and physical roots produced identical IDs. A published bundle validated against a relocated physical artifact root. Changing scientific configuration, selection contract, or checkpoint content changed the bundle identity. Tail cache and ledger staging debris did not.

## Collision and external mutation

Sequential duplicate publication returned one creation and one validated reuse. Two concurrent publishers produced exactly one creator and one validated reuse. A pre-existing valid destination was returned; an inconsistent destination was preserved and rejected. Partial staging was not accepted.

After publication, mutating an external checkpoint payload or manifest caused size/hash validation failure. Restoring the payload bytes restored validity, demonstrating that existence and path are not identity.

## Corruption and rejection matrix

The focused matrix rejected missing required files, malformed canonical JSON, wrong bundle ID/content hash, duplicate/reordered inventory, inventoried and uninventoried unexpected members, missing/corrupt ledger manifest, ledger hash mismatch, run/authority/config mismatches, source inventory mismatch, missing or modified external artifacts, payload/manifest/size mismatch, validation/checkpoint identity mismatch, completed/resume/update mismatch, duplicate/conflicting checkpoint identity, invalid backend, malformed/raw path locator, held-out evaluation evidence, target metadata, standalone validation, partial staging, and inconsistent collision paths.

Fifty fixed-seed single-field commit-manifest corruptions were resealed into structurally valid identities and all failed semantic validation.

## Validation results

- Focused V2-B: 65 passed, 0 failed.
- Schema/locator: 10 passed.
- Build/completeness/determinism/portability: 19 passed.
- Publication/collision/corruption: 36 passed, including the 27-case explicit corruption matrix and 50-case fixed-seed corruption loop.
- V2-A regression: 74 passed, 0 failed. One initial run exposed only the obsolete exact registry-size assertion; after the bounded test correction, the full rerun passed.
- Existing relevant P9 Python regression: 153 passed, 0 failed.
- Main, isolated formal, and isolated recovery `targets::tar_validate()`: 3/3 passed with no target execution.
- Seven P9 v2 runtime schemas parsed as JSON; the three new schemas passed Draft 2020-12 meta-schema and valid/invalid instance tests.
- Changed Markdown H1/fence/final-newline/local-link checks and `git diff --check`: required final checks passed before publication; standalone Markdown linter was unavailable.
- The unrelated long-running pytest process was not awaited, reused, terminated, or touched.

## Complexity accounting

V2-B adds one runtime module and three runtime schemas. The module has six public functions (`make_bound_document`, `make_filesystem_locator`, `build_run_bundle`, `validate_run_bundle`, `load_run_bundle`, `publish_run_bundle`), 21 private cohesive helpers, four immutable result/input dataclasses, and one error type. It adds no controller, state machine, authority/reservation/attempt/operation identity, recovery path, lock, target, finalizer, publisher, acceptance, or resolver.

## Prohibited-work accounting

| Activity | Count |
|---|---:|
| Production authority/reservation/attempt/run/operation/acceptance | 0 / 0 / 0 / 0 / 0 / 0 |
| Training/resume/recovery | 0 / 0 / 0 |
| Production validation/held-out evaluation | 0 / 0 |
| Production checkpoint/cache writes | 0 / 0 |
| Historical evidence/dissertation mutations | 0 / 0 |
| Canonical historical import bundles | 0 |
| Finalization results/acceptance publications | 0 / 0 |
| New target scripts/targets/stores/lock classes | 0 / 0 / 0 / 0 |

Repository scope is eight new runtime/schema/test paths, nine modified V2-A/blueprint/test paths, and this report: 18 versioned paths. External production artifact mutation count is zero.

## Immutable historical evidence

Read-only before and pre-publication SHA-256 values remained exact:

| Evidence | Before | After |
|---|---|---|
| Epoch-105 payload | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` |
| Epoch-105 manifest | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` |

No real historical bundle was constructed. V2-D/V2-G remain the only historical import units.

## Remaining risks

- The initial runtime locator backend is filesystem-only; a future backend requires an explicit versioned schema/validator extension.
- POSIX directory rename and `fsync` behavior was tested on temporary local storage; production filesystem-class durability testing remains a V2-H gate.
- Physical namespace resolution is deployment configuration, but it conveys no trust because bytes are always size/hash verified.
- The source inventory binds canonical logical paths and hashes; historical source availability/loader hardening remains a V2-D audit responsibility.

These are later-unit gates, not unresolved V2-B contracts.

## Exact next work unit

`V2-C: pure deterministic finalizer, idempotent acceptance publisher, and accepted-checkpoint resolver core using synthetic validated V2-B bundles.`

V2-C was not started or executed.
