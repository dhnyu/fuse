# P9 v2 V2-C Finalization and Acceptance Implementation

## Verdict

`P9_V2_C_FINALIZATION_ACCEPTANCE_PASS_PUSHED` is the publication verdict
contingent on the final scoped rerun, commit, push, clean-tree/origin check, and
post-push immutable hash readback recorded in the final response. All V2-C
contracts and pre-publication validations passed.

## Purpose and lineage

- Executed at: 2026-09-01 00:56 Asia/Seoul.
- Scope: V2-C selection contract, pure finalizer, acceptance publisher, resolver
  core, and synthetic tests only.
- Fuse start: `reduced@bc73e3dc285d571b7c993c6d19b69c5debbcd3eb`,
  clean, origin ahead/behind `0/0`.
- Dissertation:
  `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, clean,
  origin ahead/behind `0/0`.
- Fuse ending HEAD: the commit containing this report; the final response records
  its exact SHA because a commit cannot contain its own SHA.
- Input prompt summary: implement only V2-C over synthetic validated V2-B
  bundles; do not start historical import, downstream migration, training,
  evaluation, target activation, or v1 retirement.

The current P9 v2 blueprint, V2-A/V2-B runtime and reports, and active
dissertation selection methodology were read. No methodology conflict was
found. The dissertation was not modified.

## Files and runtime architecture

Added:

- `python/p9_v2_finalization.py`
- `python/p9_v2_acceptance.py`
- `config/schemas/p9_v2_selection_contract.schema.json`
- `config/schemas/p9_v2_finalization_result.schema.json`
- `config/schemas/p9_v2_acceptance.schema.json`
- `tests/python/p9_v2_c_test_support.py`
- `tests/python/test_p9_v2_finalization.py`
- `tests/python/test_p9_v2_acceptance_resolver.py`
- `tests/python/test_p9_v2_acceptance_crash.py`

Modified only to register/reuse the new contracts:

- `python/p9_v2_schema.py`
- `tests/python/p9_v2_bundle_test_support.py`
- `blueprint/p9_v2/README.md`
- `blueprint/p9_v2/finalization_acceptance_resolver.md`
- `blueprint/p9_v2/decision_log.md`
- `blueprint/p9_v2/risk_register.md`
- `blueprint/p9_v2/roadmap.md`

The finalizer imports V2-A canonical/schema/ledger code and the V2-B bundle
validator. The publisher and resolver import the same bundle validator and the
finalization-result validator. There is no second serializer, ledger reader,
replay state machine, bundle validator, locator implementation, controller, or
recovery path.

## Selection contract and replay

The immutable `p9-selection-v2.0.0` contract fixes:

- validation every five completed epochs;
- minimum validation retrieval loss as primary selection;
- strict absolute loss difference `< 0.0001` as equivalence;
- larger mean source-separation margin for equivalent loss;
- earlier completed epoch for a remaining exact tie;
- patience four, reset only when the candidate becomes the selected best;
- eligibility only from committed `VALIDATION_CHECKPOINT_COMMITTED` events.

Canonical JSON restores finite IEEE-754 binary64 values. Comparison uses
`Decimal.from_float()` for an exact promotion of both loss operands and the
binary64 tolerance, avoiding a second serialization or platform string-format
rule. MRR is absent.

Candidates replay in committed event-sequence order. Each candidate must have
exact five-epoch cadence and one matching `EARLY_STOPPING_UPDATED` event. Stored
checkpoint selector state, early-stopping evidence, and final selector summary
must match the independently recomputed best ID, decision basis, and
non-improvement count. A candidate after patience reaches four is rejected. The
completion boundary must equal the last eligible checkpoint boundary and, when
patience is reached, the patience-trigger boundary.

## Finalization result

`finalize_run_bundle()` validates the bundle and external artifacts, replays the
selector, and returns canonical `SUCCEEDED` or `FAILED` evidence without writing
files. It imports no PyTorch, CUDA, trainer, loader, optimizer, scheduler,
evaluation, checkpoint writer, target, or v1 recovery runtime.

`finalization_result_hash` is SHA-256 of the complete canonical result excluding
only `finalization_id` and `finalization_result_hash`.
`finalization_id = "p9fin_" + hash[0:24]`. The preimage binds bundle and
selection-contract identities/hashes, candidate-set hash, selected checkpoint,
selector/stopping summaries, provenance, zero evaluation consumption, and the
finalizer implementation version/hash. Same inputs are byte-identical; changing
the contract or implementation version changes identity.

Stable invalid-evidence codes are `BUNDLE_INVALID`, `BUNDLE_NOT_FOUND`,
`SCIENTIFICALLY_INCOMPLETE`, `SELECTION_CONTRACT_MISMATCH`,
`NO_ELIGIBLE_CANDIDATE`, `SELECTOR_REPLAY_MISMATCH`,
`STOPPING_SUMMARY_MISMATCH`, `CHECKPOINT_INVENTORY_MISMATCH`,
`SOURCE_PROVENANCE_MISMATCH`, and `UNSUPPORTED_SCHEMA_VERSION`. Filesystem or
publication exceptions remain operational failures outside training/scientific
state.

## Acceptance identity, layout, and commit

`acceptance_content_sha256` binds schema, authority identity/hash, bundle
identity/hash, finalization identity/hash, selected checkpoint identity and both
checkpoint hashes, and evaluation consumption zero.
`acceptance_id = "p9accv2_" + hash[0:24]`.

Layout:

```text
<acceptance-root>/p9accv2_<24 hex>/
  acceptance.json
  finalization_result.json
  commit/acceptance_commit_manifest.json
```

Publication holds one acceptance-identity-scoped kernel `flock` only around the
publication decision. It has no heartbeat or owner state. Canonical acceptance
and exact finalization bytes are written with exclusive creation into a
same-filesystem staging directory, file-`fsync`ed, reread, verified, and bound by
the staged commit manifest. Atomic directory rename exposing that manifest is
the commit point, followed by publication-root `fsync`. POSIX durability still
depends on the mounted filesystem honoring `fsync` and rename semantics.

An existing exact acceptance validates and returns unchanged. An inconsistent
identity path fails closed and is preserved. Pre-commit staging is
non-authoritative debris. No publication recovery state machine or additional
lock class exists.

## Crash matrix

| Injected boundary | Restart observation |
|---|---|
| Before lock acquisition | No canonical acceptance; retry creates one. |
| After lock, before staging | No canonical acceptance; retry creates one. |
| After staging create, before write | Staging only; retry creates one. |
| During acceptance metadata write | Torn staging only; retry creates one. |
| After file fsync, before reread | Staging only; retry creates one. |
| After verification, before commit exposure rename | Complete staging only; retry creates one. |
| After commit exposure rename, before parent fsync | Exactly one valid canonical acceptance; retry validates existing. |
| After parent fsync, before lock release | Exactly one valid canonical acceptance; retry validates existing. |
| Concurrent identical publication | One create and one validate-return, one identity. |
| Existing inconsistent destination | Fail closed without overwrite. |

All boundaries used real temporary filesystem bytes and post-fault reread.

## Resolver contract and rejection matrix

`resolve_accepted_checkpoint(acceptance_identity)` accepts only a canonical
`p9accv2_` identity. It validates:

```text
acceptance commit and record
-> exact finalization result
-> scientifically complete run bundle
-> selected checkpoint inventory record
-> current external payload and manifest bytes
```

It returns acceptance/bundle/finalization/checkpoint identities and hashes,
structured payload locator, completed/resume epochs, optimizer update, selected
loss/margin, stopping summary, scientific configuration evidence, authority,
and source/provenance summary.

Tests reject missing/corrupt/uncommitted acceptance manifests, malformed record,
wrong acceptance identity/hash, wrong authority, bundle, finalization, or
selected-checkpoint binding, unsuccessful finalization, incomplete bundle,
unresolved locator namespace, modified payload/manifest, path-only input,
`latest`, checkpoint identity input, and legacy recovery identity. Missing or
corrupt `targets` metadata is irrelevant. Eligibility/supersession indexing is
explicitly deferred to V2-E rather than introducing a V2-C mutable subsystem.

## Historical-style retry regression

A synthetic ledger replaying as
`COMPLETE / FINALIZATION_FAILED / NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE` was
bundled once. The pure finalizer succeeded over that same immutable bundle,
acceptance published, and the resolver returned its selected checkpoint. No
training, validation, new authority, recovery identity, or recovery DAG was
used. A separate injected publication failure retried the identical already
computed finalization result and converged without a finalizer rerun.

## Validation results

- Focused V2-C: 62 passed, 0 failed.
- Finalizer/selection/stopping/determinism/import boundary: 24 passed.
- Acceptance/resolver/schema/corruption: 28 passed.
- Acceptance crash/retry: 10 passed.
- Combined V2-A/B/C: 201 passed, 0 failed (A 74, B 65, C 62).
- Existing relevant P9 Python regression: 153 passed, 0 failed.
- Non-executing relevant R P9 tests: 25 assertions passed.
- Main, isolated formal, and isolated recovery `targets::tar_validate()`: 3/3
  passed with no target execution.
- Ten runtime schemas parsed and passed Draft 2020-12 meta-schema validation;
  all three V2-C schemas have valid/invalid instance coverage.
- Python compile/import checks passed. `ruff` was unavailable in the environment.
- An initial existing-test invocation omitted repository `PYTHONPATH` and stopped
  during collection; rerun with `PYTHONPATH=.:python` passed all 153 tests.
- Markdown structure/local-link, `git diff --check`, and final clean-tree checks
  are rerun immediately before publication.
- The unrelated long-running pytest process was not awaited, reused, terminated,
  or touched.

## Complexity accounting

V2-C adds two cohesive runtime modules and three schemas. It exposes seven small
public functions: selection-contract creation/content, finalization and result
validation, acceptance validation/publication, and resolution. Sixteen private
helpers implement one selector replay, canonical identity sealing, staged I/O,
and chain checks. Five data/error types carry immutable results and stable
failures. The two-module split keeps pure finalization separate from mutating
publication/resolution.

V2-C adds no controller, target, target store, training or recovery path,
authority/reservation/attempt/operation identity, heartbeat, mutable state file,
manual/latest resolver, publication operation identity, or persistent lock
hierarchy. The active concepts remain exactly one finalizer, one acceptance
publisher, and one resolver core. The only V2-C lock is the already-approved
short acceptance publication lock; the future training lock remains the other
architecture lock class.

## Prohibited-work accounting

| Activity | Count |
|---|---:|
| New production authority / reservation / attempt / run / operation | 0 / 0 / 0 / 0 / 0 |
| Historical acceptance / bundle import / finalization / resolver consumption | 0 / 0 / 0 / 0 |
| Training / resume / recovery | 0 / 0 / 0 |
| Production validation / held-out evaluation | 0 / 0 |
| Production checkpoint / cache writes | 0 / 0 |
| Historical evidence / dissertation mutations | 0 / 0 |
| Active target additions or P9 target executions | 0 / 0 |

All finalization, acceptance, checkpoint, bundle, and crash artifacts were
synthetic temporary fixtures.

## Immutable historical evidence

| Evidence | Before | Pre-publication after |
|---|---|---|
| Epoch-105 payload | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` |
| Epoch-105 manifest | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` |

Post-push readback is recorded in the final response.

## Risks and next work unit

No V2-C blocker remains. Authority eligibility/supersession index representation
remains intentionally unresolved until V2-E. Production-filesystem power-loss
behavior requires a later filesystem-specific pilot. Neither affects synthetic
V2-C correctness or authorizes production publication.

The exact next work unit is:

`V2-D: read-only historical importer dry run producing a noncanonical synthetic/dry-run V2 bundle from immutable v1 evidence, without historical mutation, metric recomputation, validation rerun, finalization publication, or acceptance.`

V2-D was not started.
