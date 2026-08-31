# P9 v2 V2-A Ledger and State Implementation

## Verdict

`P9_V2_A_LEDGER_STATE_PASS_PUSHED` is the publication verdict contingent on the final scoped test rerun, commit, push, clean-tree check, origin synchronization, and post-push immutable hash readback recorded in the final response. All V2-A implementation and pre-publication validation requirements passed.

## Purpose and scope

- Executed at: 2026-08-31 23:25 Asia/Seoul.
- Input prompt: implement only V2-A runtime schemas, canonical serialization and hashing, one append-only ledger, independent replay, and synthetic crash/corruption tests.
- Fuse start: `reduced@9035ee61ab0439e3b52b99becedcbdf883656fe7`, clean, origin ahead/behind `0/0`.
- Dissertation: `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, clean, origin ahead/behind `0/0`.
- Fuse ending HEAD: the commit containing this report; its exact SHA is recorded after publication in the final response because a commit cannot contain its own SHA.
- Methodology checked read-only: `template/sections/chapters/04-methodology-training.typ` and the active P9 selection methodology. No contradiction was found and the dissertation was not modified.
- V2-B and all later units were excluded.

## Files

Runtime modules added:

- `python/p9_v2_canonical.py`
- `python/p9_v2_schema.py`
- `python/p9_v2_ledger.py`
- `python/p9_v2_replay.py`

Draft 2020-12 runtime schemas added:

- `config/schemas/p9_v2_event.schema.json`
- `config/schemas/p9_v2_ledger_header.schema.json`
- `config/schemas/p9_v2_ledger_manifest.schema.json`
- `config/schemas/p9_v2_tail_cache.schema.json`

Synthetic tests/helpers added:

- `tests/python/p9_v2_test_support.py`
- `tests/python/test_p9_v2_canonical_schema.py`
- `tests/python/test_p9_v2_ledger.py`
- `tests/python/test_p9_v2_replay.py`
- `tests/python/test_p9_v2_crash_corruption.py`

The V2-A decisions were recorded without redesigning the architecture in `blueprint/p9_v2/README.md`, `event_ledger.md`, `state_model.md`, `decision_log.md`, and `risk_register.md`. No target script, target store, runtime digest declaration, v1 source, or dissertation file changed.

## Implementation architecture

The implementation has four cohesive modules: one serializer/hasher, one schema adapter, one ledger reader/writer, and one pure replay module. The canonical reader and writer share the same serializer, event verifier, schema validator, and transition rules. There is no controller, authority class, reservation, attempt, operation, recovery subsystem, finalizer, publisher, resolver, bundle builder, or new lock implementation.

Complexity accounting is four runtime modules, four runtime schemas, 29 module-level functions (14 public and 15 private), 11 methods, four substantive types (`LedgerWriter`, `LedgerRead`, `ReplayResult`, and the private replay accumulator), and seven focused error classes. The errors distinguish canonical/schema corruption, illegal transitions, closed ledgers, and staging collision without adding state machines. The module split prevents duplicate serializers and duplicate replay paths.

## Canonical JSON contract

Contract `p9-v2-exact-binary64-decimal-v1` uses canonical UTF-8, sorted Unicode-scalar object keys, NFC-only strings, minimal JSON escapes, no insignificant whitespace, and one trailing newline only for event records. Integers are unpadded base-10 in `[-(2^53-1), 2^53-1]`. Finite IEEE-754 binary64 values within the same magnitude bound are expanded exactly in base 10 without exponent notation or redundant fractional trailing zeros. Both zero signs become `0`.

NaN, positive/negative infinity, out-of-range numbers, non-string keys, non-NFC strings, lone surrogates, and unsupported native objects are rejected. Event ID hashes the canonical envelope without `event_id` or `event_hash`; event hash hashes the canonical event without only `event_hash`. Version `2.0.0` is the only accepted runtime schema version.

## Ledger and atomic append contract

Each run has one header, immutable committed segments, optional non-authoritative tail cache, staging/debris directories, and an optional closed-ledger manifest. V2-A closes one event per segment, maximum 1,048,576 bytes, with filename `first-last` where both 12-digit sequence values are equal. Sequence starts at 1.

Append validates all committed evidence, creates staging with `O_CREAT|O_EXCL`, writes canonical bytes, file-`fsync`s, rereads/verifies, renames to `segments/`, directory-`fsync`s, then optionally replaces the tail atomically. Segment rename is the logical event commit point. Staging debris is ignored by replay and preserved in `.debris/` before the next writer append. Tail corruption or staleness cannot alter replay.

The closed manifest is staged, file-`fsync`ed, reread, renamed, and directory-`fsync`ed; manifest rename is its logical commit point. Same-filesystem POSIX rename is required. The code does not claim durability beyond the mounted filesystem/storage implementation. A real power loss between rename and directory `fsync` may reveal the old or new namespace state, but never a partially named canonical segment. V2-A introduces zero lock classes; the future controller supplies the single serialized run-writer boundary, while exclusive staging creation fails closed on collision.

## State replay semantics

Replay independently derives:

- science: `NOT_STARTED`, `IN_PROGRESS`, `COMPLETE`, `INCOMPLETE`;
- operation: `AUTHORIZED`, `STARTING`, `RUNNING`, `FINALIZING`, `ACCEPTED`, `INTERRUPTED_RESUMABLE`, `TRAINING_FAILED`, `FINALIZATION_FAILED`, `BLOCKED`;
- resumability: `NOT_APPLICABLE`, `EXACT_RESUME_ALLOWED`, `RESTART_REQUIRED`, `NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE`, `FORBIDDEN_POLICY`, `EVIDENCE_INVALID`.

It also returns run ID, tail sequence/hash, durable scientific boundary, completed/resume epochs, optimizer update, event-backed best checkpoint state, terminal training evidence, finalization/acceptance status, and diagnostic errors. `resume_policy` is explicit evidence and cannot substitute for checkpoint presence.

The critical regression sequence `TRAINING_COMPLETED -> FINALIZATION_STARTED -> FINALIZATION_FAILED(OPERATIONAL_FAILURE)` yields `COMPLETE / FINALIZATION_FAILED / NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE`. Acceptance is only representable after successful finalization; no publisher was implemented. Replay uses no `targets` metadata, v1 state, mtime, latest-file rule, path fallback, or process-global state.

## Validation-checkpoint event

The runtime event binds explicit `completed_epoch`, `resume_epoch`, optimizer update, validation/checkpoint identities, payload and manifest SHA-256, both selection metrics, selector state, queue count/pointer/enqueue count/hash, sampler epoch/cursor/hash, all required state-presence flags, atomic completion marker, and source run. Runtime semantics enforce `resume_epoch = completed_epoch + 1`, sampler epoch equals explicit resume epoch, and native source run equals the event run. A standalone validation record is not an eligible ledger event.

## Crash-safety matrix

| Injected boundary | Restart observation in the test | Required invariant |
|---|---|---|
| Before staging create | Previous ledger | Event absent |
| After exclusive create, before write | Previous ledger plus ignored debris | Event absent |
| During write | Previous ledger plus truncated debris | Event absent |
| After write, before file `fsync` | Previous ledger plus debris | Event absent |
| After file `fsync`, before verify | Previous ledger plus debris | Event absent |
| After verify, before rename | Previous ledger plus verified debris | Event absent |
| After rename, before directory `fsync` | New ledger in injected process | Event visible exactly once; real power loss may expose old or new |
| After directory `fsync`, before tail | New ledger with stale tail | Event visible exactly once |
| During tail replacement | New ledger with stale/debris tail | Event visible exactly once |
| During manifest staging write | Open ledger plus debris | Manifest absent |
| After manifest rename, before directory `fsync` | Closed ledger in injected process | Valid manifest visible; real power loss may expose open or closed |

All 11 boundaries use real temporary filesystem files, actual reread, rename, and `fsync`; fault hooks only choose the interruption point. Reopen then appends/ closes normally without duplicate application.

## Corruption and rejection matrix

Committed replay rejects missing/duplicate/reordered sequence evidence, wrong prior hash, wrong event hash/ID, another run, illegal writer role, unsupported version, illegal transition, malformed payload, validation/resume epoch mismatch, invalid checkpoint hash, nonfinite/noncanonical numeric values, truncated/torn/noncanonical JSONL, unexpected committed entries, corrupted segments, and manifest inventory/hash mismatch. One hundred fixed-seed single-field committed-event corruptions were all rejected.

Uncommitted staging debris and stale/corrupt `tail.json` are ignored by canonical replay. Writer reopen preserves staging debris before reuse. This is the explicit distinction between ignorable debris and canonical evidence corruption.

## Test results

- Focused V2-A: 74 passed, 0 failed: canonical/schema 25, ledger 10, replay/state 15, crash/corruption 24.
- Deterministic property-style coverage: 100 fixed-seed valid state sequences and 100 fixed-seed single-field corruptions, plus 100 repeated serialization and replay checks.
- Runtime schema JSON parse and Draft 2020-12 meta-schema/instance tests: 4/4 schemas passed.
- Existing relevant P9 Python regression suite: 153 passed, 0 failed. An initial collection command omitted repository root from `PYTHONPATH`; it ran zero tests and was corrected before the passing run.
- Main, isolated formal, and isolated recovery `targets::tar_validate()`: 3/3 passed; no target executed.
- Changed-document H1, fence, final-newline, and local-link/path checks: passed; standalone Markdown linter unavailable.
- Python syntax was exercised by import/test collection; `git diff --check` passed.
- Full repository pytest was intentionally not required or run. The unrelated long-running pytest process was not awaited, reused, terminated, or otherwise touched.

## Production and prohibited-work accounting

| Activity | Count |
|---|---:|
| New production authority/reservation/attempt/run/operation/acceptance | 0 / 0 / 0 / 0 / 0 / 0 |
| Training/resume/recovery execution | 0 / 0 / 0 |
| Production validation/held-out evaluation execution | 0 / 0 |
| Production checkpoint/cache writes | 0 / 0 |
| Historical evidence/dissertation mutations | 0 / 0 |
| New target scripts/targets/stores/lock classes | 0 / 0 / 0 / 0 |
| Synthetic temporary ledgers | Test-scoped only, removed by pytest temporary fixture lifecycle |

Repository changes are 13 new runtime/schema/test files, five modified blueprint documents, and this new report: 19 versioned paths. External artifact mutation count is zero.

## Immutable v1 evidence

Read-only pre-implementation and pre-publication SHA-256 values match exactly:

| Evidence | Before | After |
|---|---|---|
| Epoch-105 payload | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` |
| Epoch-105 manifest | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` |
| Attempt state | `cfbc58731ebfa8e7c06f827fa95553553db622c047e94fbde5d2a54bccd76ac2` | `cfbc58731ebfa8e7c06f827fa95553553db622c047e94fbde5d2a54bccd76ac2` |
| Terminal failure | `cfbc58731ebfa8e7c06f827fa95553553db622c047e94fbde5d2a54bccd76ac2` | `cfbc58731ebfa8e7c06f827fa95553553db622c047e94fbde5d2a54bccd76ac2` |

The historical `FAILED_NONRESUMABLE` state was not rewritten and no claim of historical operational success is made.

## Remaining risks

- Production-filesystem power-loss testing is deferred to V2-H before any training controller authority.
- A second-language writer requires independent golden-vector parity before it can append.
- One-event-per-segment I/O cadence requires a V2-H benchmark; scientific progress batching already avoids one event per optimizer update.

These are explicit later-unit gates, not unresolved V2-A contracts.

## Exact next work unit

`V2-B: immutable run-bundle builder and validator using synthetic committed V2-A evidence.`

V2-B was not started or executed.
