# P9 v2 V2-EF Resolver Migration and Synthetic End-to-End Validation

## Verdict

`P9_V2_EF_RESOLVER_AND_SYNTHETIC_E2E_PASS_PUSHED` is the publication verdict
contingent on the final rerun, commit, push, clean-tree/origin check, and
post-push historical hash readback recorded in the final response.

- V2-E: `P9_V2_E_RESOLVER_MIGRATION_PASS`.
- V2-F: `P9_V2_F_SYNTHETIC_E2E_PASS`.

## Purpose and lineage

- Executed at: 2026-09-01 02:22 Asia/Seoul.
- Fuse start: `reduced@cf458e306f51729acbc80da3f448c3b3076f14c2`,
  clean and origin ahead/behind `0/0`.
- Dissertation:
  `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, clean
  and origin ahead/behind `0/0`.
- Fuse ending HEAD: the commit containing this report; the final response records
  its exact SHA because a commit cannot contain its own SHA.
- Scope: resolver-only interfaces for P9-B, selected-FM, held-out evaluation,
  P10 and P11; corrected V2-C patience semantics; actual V2-A/B/C synthetic
  chains. No downstream science or production/historical publication.

The current V2 blueprint and V2-A/B/C/D reports, P8/P9 plan interfaces, P10/P11
blueprint contracts, and active dissertation selection methodology were read.
The dissertation repository was not modified.

## Implementation

Added:

- `python/p9_v2_downstream.py`
- `config/schemas/p9_v2_acceptance_eligibility.schema.json`
- `tests/python/p9_v2_ef_test_support.py`
- `tests/python/test_p9_v2_downstream.py`
- `tests/python/test_p9_v2_synthetic_e2e.py`
- this report

Modified:

- V2-C finalizer, selection schema, and synthetic fixture;
- V2-D importer to reuse the corrected patience function;
- P8/P9 comparison materialization interfaces;
- V2 blueprint/roadmap/decision/risk and active P9/P10/P11 interface docs;
- focused regression tests.

No target, controller, target store, scientific worker, evaluation function,
checkpoint writer, recovery path, or fallback resolver was added.

## Patience discrepancy resolution

The dissertation is authoritative:

- checkpoint selection minimizes retrieval loss;
- loss difference strictly below the binary64 value of `1e-4` is equivalent;
- equivalent losses use larger margin, then earlier epoch;
- patience resets only when retrieval loss decreases by at least `1e-4`;
- margin-only checkpoint replacement does not reset patience.

The runtime contract is now `p9-selection-v2.1.0`. Selection and patience reset
are separate pure decisions. Binary64 values are promoted exactly with
`Decimal.from_float()`. The finalizer implementation identity advanced to
`p9-v2-finalizer-v2`. Tests prove a margin winner becomes selected while the
counter advances, and a primary-loss improvement crossing the tolerance resets
the counter.

Historical read-only replay remains scientifically unchanged:

- selected checkpoint `p9ck_42f7957d2ea998ac9e8ff705`;
- completed epoch 105;
- retrieval loss `0.3806893527507782`;
- margin `0.28760260343551636`;
- terminal epoch 125/update 9,500;
- replay `COMPLETE / FINALIZATION_FAILED /
  NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE`.

The corrected selection-contract hash changes only derived noncanonical dry-run
identities: bundle `p9rb_65fc954ba2b95475aaf38ad7`, bundle SHA-256
`65fc954ba2b95475aaf38ad76e526884be3c89e8f42797917c13712869a259aa`,
and pure finalization `p9fin_33282fcfaf185a56949f7621`. No historical file or
previous report was changed.

## V2-E resolver contract

`AcceptedCheckpointResolver` is configured once with acceptance/bundle roots,
immutable locator roots, and a content-addressed eligibility snapshot. Its only
consumer-facing method is:

```text
resolve_accepted_checkpoint(acceptance_identity)
```

The eligibility snapshot is canonical, hash-sealed, sorted, duplicate-free, and
binds acceptance identity/status to authority identity/hash. Status is one of
`ELIGIBLE`, `SUPERSEDED`, or `REVOKED`. Missing/ambiguous entries fail
unresolved; noneligible entries fail closed. The snapshot is evidence rather
than a new execution authority or mutable registry. V2-E provides no production
publisher; V2-G must bind its canonical snapshot to explicit migration/
publication authority.

After eligibility, the existing V2-C resolver validates:

```text
acceptance commit
-> finalization bytes/result
-> scientifically complete bundle
-> checkpoint inventory/locator
-> external payload and manifest bytes
```

All five adapters call one `resolve_consumer_checkpoint()` function and return
the same immutable `AcceptedCheckpoint` record.

| Consumer | Migrated interface | Status |
|---|---|---|
| P9-B | acceptance identity -> common resolver -> comparison plan | PASS |
| selected-FM | acceptance identity -> common resolver | PASS |
| held-out evaluation | acceptance identity -> common resolver | PASS; no evaluation run |
| P10 | acceptance identity -> common resolver | PASS; no P10 run |
| P11 | acceptance identity -> common resolver | PASS; no P11 run |

P8/P9 plan materialization no longer accepts a selected-checkpoint dictionary.
It requires an acceptance identity and the configured resolver. The returned
plan binds acceptance and checkpoint identities without executing training.

## Rejection matrix

Every one of the five consumers rejects:

- raw absolute or relative checkpoint paths;
- `latest` and manual override tokens;
- v1 checkpoint and recovery identities;
- direct bundle and finalization paths;
- malformed/noncanonical acceptance identities;
- valid-looking but uncommitted acceptance identities;
- acceptance missing from eligibility;
- superseded or revoked acceptance;
- corrupted eligibility identity/hash/order;
- authority mismatch;
- corrupt acceptance or bundle chain;
- mutated external payload or manifest.

The explicit fallback matrix covers 5 consumers x 8 path/token/legacy/direct
forms, plus five-consumer uncommitted/ineligible and external-mutation cases.
There is no alternate code path or manual/latest/v1 fallback.

## V2-F synthetic scenarios

All artifacts existed only in pytest temporary roots and used actual V2-A/B/C
runtime functions.

| Scenario | Result |
|---|---|
| Normal complete run | Bundle finalized, acceptance committed, all five consumers resolved identical evidence. |
| Interrupted with exact checkpoint | `IN_PROGRESS / INTERRUPTED_RESUMABLE / EXACT_RESUME_ALLOWED`; finalization rejected incomplete evidence. |
| Training failure | `INCOMPLETE / TRAINING_FAILED`; finalization rejected incomplete evidence. |
| Complete + prior finalization failure | Same bundle finalized purely and resolved without retraining/recovery. |
| Acceptance publication failure | Precommit fault left no canonical acceptance; retry committed once; duplicate retry returned existing. |
| Committed acceptance + bookkeeping failure | Resolver recognized committed acceptance independently. |
| Corrupt bundle | Full-chain resolver rejected. |
| Corrupt acceptance | Full-chain resolver rejected. |
| Mutated external checkpoint | Hash verification rejected. |
| Manual/latest/v1 attempts | Canonical identity gate rejected every attempt. |

For the successful case all consumers received identical checkpoint identity,
payload/manifest hashes, validation metrics, stopping summary, scientific
configuration, authority, and provenance. No model, loader, trainer, optimizer,
validation, evaluation, P10, or P11 computation was imported or run by the
downstream adapter.

## Validation

- Focused V2-E: 55 passed, 0 failed.
- Focused V2-F: 13 passed, 0 failed.
- Patience/finalizer focused suite: 26 passed, 0 failed.
- Combined V2-A/B/C/D/E/F: 301 passed, 0 failed.
- V2-A/B/C/D regression subset: 233 passed, 0 failed.
- Existing relevant P8/P9/formal/recovery Python regression: 145 passed, 0 failed.
- Relevant R testthat: 39 assertions passed, 2 failed in the unchanged baseline
  test expecting obsolete generation `p9gen_acb72f...`; tracked config remains
  `p9gen_batchuniq_20260831`. No V2-EF R runtime code changed.
- Main/formal/recovery `targets::tar_validate()`: 3/3 passed with no target run.
- Twelve V2 runtime schemas parsed and passed Draft 2020-12 meta-validation;
  selection and eligibility valid/invalid fixtures passed.
- Python AST parse/import checks passed.
- Markdown/local-path checks and `git diff --check` passed before publication.
- The unrelated long-running pytest process was not awaited, reused, terminated,
  or touched.

## Complexity

V2-E adds one cohesive 156-line resolver adapter and one bounded schema. It has
one configured resolver, one shared consumer dispatch, five explicit one-line
consumer interfaces, and deterministic eligibility make/validate helpers. V2-F
adds test support and tests only.

There is still one acceptance chain resolver, no consumer-specific validator,
no resolver fallback hierarchy, no recovery DAG, no eligibility publisher/state
machine/lock, and no new authority/reservation/attempt/operation identity.

## Prohibited-work accounting

| Activity | Count |
|---|---:|
| Production authority / run / training / resume / recovery | 0 / 0 / 0 / 0 / 0 |
| Validation / held-out evaluation execution | 0 / 0 |
| P9-B / selected-FM / P10 / P11 scientific task execution | 0 / 0 / 0 / 0 |
| Production checkpoint/cache writes | 0 / 0 |
| Historical mutation / dissertation mutation | 0 / 0 |
| Canonical historical import / finalization / acceptance | 0 / 0 / 0 |
| V1 retirement | 0 |

Synthetic authority-like documents, ledgers, bundles, finalizations,
acceptances, eligibility snapshots, and checkpoint bytes existed only in
temporary test fixtures and were removed by fixture cleanup.

## Immutable history

| Evidence | Before | Pre-publication after |
|---|---|---|
| Epoch-105 payload | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` |
| Epoch-105 manifest | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` |

Post-push readback is recorded in the final response.

## Next work unit

The exact next work unit is:

`V2-G: canonical historical import, pure finalization, acceptance publication, and resolver verification under explicit migration/publication authority.`

V2-G was not started.
