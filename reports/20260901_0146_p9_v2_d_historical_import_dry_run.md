# P9 v2 V2-D Historical Import Dry Run

## Verdict

`P9_V2_D_IMPORT_DRY_RUN_PASS_PUSHED` is the publication verdict contingent on
the final scoped rerun, commit, push, clean-tree/origin check, and post-push hash
readback recorded in the final response.

Migration dry-run verdict: `MIGRATION_DRY_RUN_ELIGIBLE`.

This is not a canonical migration or acceptance. The immutable v1 state remains
`FAILED_NONRESUMABLE`.

## Purpose and lineage

- Executed at: 2026-09-01 01:46 Asia/Seoul.
- Fuse start: `reduced@5433b1535a930a1b2281b1c92cafee0202a4b0c1`,
  clean and origin ahead/behind `0/0`.
- Dissertation:
  `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, clean
  and origin ahead/behind `0/0`.
- Fuse ending HEAD: the commit containing this report; the final response records
  its exact SHA because a commit cannot contain its own SHA.
- Prompt scope: inspect immutable v1 evidence, map it through V2-A, build and
  validate a noncanonical V2-B bundle, and exercise V2-C only as a pure in-memory
  audit. No canonical publication, finalization publication, acceptance,
  training, validation, evaluation, resume, recovery, or downstream execution.

The active dissertation methodology and the P9 v2 blueprint/V2-A/B/C runtime
were read before implementation. The dissertation repository was not modified.

## Historical roots

- Attempt:
  `/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/attempts/p9attempt_a754afd14ac87287afb04029`
- Authority:
  `/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/authorization/p9a_9d6f0554553ac43371b47efd`
- Join audit:
  `/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/recovery_authorization/p9ra_2b5e0dc9eebb81c028fefedf/checkpoint_join_audit.json`
- Source identities: authority `p9a_9d6f0554553ac43371b47efd`, reservation
  `p9res_0f5492c80e7c152e6c543012`, attempt
  `p9attempt_a754afd14ac87287afb04029`, run
  `p9run_6887930091dd2f2bfedc3c96`.

The ordered import source inventory contains 58 authority, terminal, trace,
join, manifest, and payload entries. Its canonical digest is
`282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c`.

## Files and architecture

Added:

- `python/p9_v2_legacy_import.py`
- `config/schemas/p9_v2_legacy_import.schema.json`
- `tests/python/test_p9_v2_legacy_import.py`
- this report

Modified narrowly:

- `python/p9_v2_bundle.py`: accepts and verifies the runtime legacy annotation.
- `python/p9_v2_schema.py`: registers the annotation schema.
- `python/p9_v2_finalization.py`: exposes the existing canonical candidate
  comparator for the adapter; no second selector was added.
- P9 v2 README, legacy migration, roadmap, decision log, and risk register.

The importer reuses V2-A canonical JSON, hashing, ledger writer/reader, schemas,
and replay; V2-B locators, builder, publisher, and validator; and V2-C selection
contract, candidate comparator, and pure finalizer. It adds no serializer,
replay engine, bundle format, selector, authority hierarchy, lock, state machine,
recovery path, target, or active store.

## Hardened deserialization

Every payload is gated by its immutable manifest and independent join-audit
hash before deserialization. The selected manifest itself is independently
hash-gated. PyTorch 2.12.0+cu130 could not read this NumPy-bearing historical
format with the default restricted allowlist. The importer therefore uses:

- `torch.load(..., map_location="cpu", weights_only=True)`;
- function-local `torch.serialization.safe_globals()`;
- only `numpy._core.multiarray._reconstruct`, `numpy.ndarray`, `numpy.dtype`,
  `numpy._core.multiarray.scalar`, and `numpy.dtypes.UInt32DType`;
- no unrestricted fallback and no global safe-global mutation.

The result must be a mapping and its canonical state-content digest must match
the manifest. The loader is private to this one historical importer. Residual
risk remains because a restricted parser still reads binary input; V2-G must pin
the environment and retain all integrity gates.

## 25/25 mapping

Every row was independently matched to a validation record, manifest, payload,
state-content digest, and worker-result manifest. Discovery order was explicitly
sorted by completed epoch.

| Ordinal | Completed/resume epoch | Update | Checkpoint |
|---:|---:|---:|---|
| 1 | 5/6 | 380 | `p9ck_c8f480a5402a791d25f3fa57` |
| 2 | 10/11 | 760 | `p9ck_967844071a5f47bb93a0d0eb` |
| 3 | 15/16 | 1,140 | `p9ck_0c376f6401607f22e343d475` |
| 4 | 20/21 | 1,520 | `p9ck_9e67ac2469ab79383ac44fbb` |
| 5 | 25/26 | 1,900 | `p9ck_3db3874296288e6d1c27ccb8` |
| 6 | 30/31 | 2,280 | `p9ck_b9a6f933c88542d83dc34ad0` |
| 7 | 35/36 | 2,660 | `p9ck_850b101b176e4ab9a27696df` |
| 8 | 40/41 | 3,040 | `p9ck_1c964f112d6c19bd61dd1902` |
| 9 | 45/46 | 3,420 | `p9ck_16551e994cf829315288d97f` |
| 10 | 50/51 | 3,800 | `p9ck_90e51fc85660a135f6fd701b` |
| 11 | 55/56 | 4,180 | `p9ck_ce07e70e22b82cedd58bd8d3` |
| 12 | 60/61 | 4,560 | `p9ck_6ebbdc8fe7838b65e88d67c5` |
| 13 | 65/66 | 4,940 | `p9ck_86543a99e3989b36d92266a6` |
| 14 | 70/71 | 5,320 | `p9ck_4e98ecb855bd48bd01c3b8a2` |
| 15 | 75/76 | 5,700 | `p9ck_92e48ac4af3d7c360046e599` |
| 16 | 80/81 | 6,080 | `p9ck_a9bed64639f473409d75c9b6` |
| 17 | 85/86 | 6,460 | `p9ck_8939f4635637bb006a6b4ccf` |
| 18 | 90/91 | 6,840 | `p9ck_98bdef9caeb49474da520842` |
| 19 | 95/96 | 7,220 | `p9ck_43d68b94c47eb5639c38f070` |
| 20 | 100/101 | 7,600 | `p9ck_4df12cca884d3d38344234a8` |
| 21 | 105/106 | 7,980 | `p9ck_42f7957d2ea998ac9e8ff705` |
| 22 | 110/111 | 8,360 | `p9ck_8808fdfedfe96931e625d2b5` |
| 23 | 115/116 | 8,740 | `p9ck_0953400b0e8339cd66afe847` |
| 24 | 120/121 | 9,120 | `p9ck_636ffac9aaebf83f2478eb3f` |
| 25 | 125/126 | 9,500 | `p9ck_f5eb10cb5744026013f54882` |

All 25 payload and all 25 manifest SHA-256 values matched both current bytes
and the immutable join audit. The full machine-verifiable inventory is produced
deterministically in memory and bound into the dry-run bundle; no persistent
runtime output was retained.

## State, epoch, queue, and sampler audit

All checkpoints contain online model, EMA, optimizer, scheduler, queue, sampler,
two-rank RNG, early-stopping, best-checkpoint, validation trace, training trace,
lineage, and world-size state. AMP is disabled and every scaler is explicitly
null/`NOT_APPLICABLE`.

For every ordinal, `completed_epoch = 5 * ordinal`, `resume_epoch =
completed_epoch + 1`, and `global_update = completed_epoch * 76`. Checkpoint
progress and sampler state both use resume epoch with cursor zero, proving no
hidden partial epoch at these boundaries. Training trace length equals update;
validation trace length equals ordinal.

Queue capacity is 8,192. For every checkpoint, enqueue count equals
`optimizer_update * 32 global batch * 2 views`, count equals the lesser of
capacity/enqueue count, and pointer equals enqueue count modulo 8,192. The final
boundary reproduces epoch 125/update 9,500 and four non-improvements.

## Selector and evaluation audit

The authoritative V2-C comparator replayed all 25 candidates in committed
order. It naturally selected `p9ck_42f7957d2ea998ac9e8ff705` at completed epoch
105 with retrieval loss `0.3806893527507782` and mean source-separation margin
`0.28760260343551636`. The selected payload hash is
`fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6`;
the manifest hash is
`87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc`.

All validation, worker-result, authority, and terminal evidence reports
evaluation consumption zero. No metric, embedding, validation, or evaluation
was recomputed or executed.

The dissertation resets patience only for retrieval-loss decrease of at least
`1e-4`; V2-C currently resets whenever a tie-break selects a new best. The
historical trace has no margin-only best replacement, so both rules produce the
same selection and stopping boundary. This general V2-C discrepancy is recorded
as R16/D41 and must be resolved before V2-G; it does not block this historical
dry-run verdict.

## Field classification and annotations

| Classification | Count |
|---|---:|
| `DIRECTLY_AVAILABLE` | 21 |
| `DETERMINISTICALLY_DERIVABLE` | 6 |
| `AVAILABLE_WITH_LEGACY_ANNOTATION` | 2 |
| `NOT_APPLICABLE` | 2 |
| `MISSING_BLOCKING` | 0 |

The annotation preserves v1 authority/reservation/attempt/run identities only
as provenance. Legacy payload/manifest atomic completion is annotated rather
than represented as a contemporaneous native V2 event. Ambiguous, missing,
duplicate, unsupported, hash-inconsistent, evaluation-contaminated, or
state-incomplete evidence fails closed; no nearest/latest/mtime repair exists.

## Imported ledger and bundle

- Imported run: `p9runv2_d6ffbd951bc813f78defeacc`.
- ID rule: importer version + v1 run ID + ordered source inventory digest;
  V2-A derives event IDs/hashes from canonical envelopes.
- Ledger: 106 committed events, including all 25 atomic candidate events and
  matching early-stopping updates.
- Replay: `COMPLETE / FINALIZATION_FAILED /
  NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE`.
- Bundle: `p9rb_3c86e72ef17ebd7045ae36fb`.
- Bundle hash:
  `3c86e72ef17ebd7045ae36fb55e7d391330b1f860bbf88e4be42599110ceb995`.
- V2-B validation: valid, `SCIENTIFICALLY_COMPLETE`.
- Pure in-memory finalization: `p9fin_7c871b84f097bc6a96c7f0a6`, succeeded.

Publication was only under
`v2_d_noncanonical_dry_run/ineligible_for_acceptance/bundles` inside temporary
roots. Schema flags require canonical-publication and acceptance eligibility
false. No dry-run files were retained, no canonical V2 namespace was written,
and the acceptance publisher/resolver was not called.

Two independent runs, including reversed source discovery, produced identical
imported run ID, event/ledger manifest bytes, bundle bytes/hash/ID, replay, and
pure finalization result. Physical temporary roots and target metadata were
irrelevant.

## Rejection and validation results

The copied/synthetic corruption matrix rejected missing manifest/source,
payload and manifest hash mismatch, duplicate checkpoint, missing pair,
duplicate/mutated validation counterpart, completed/resume epoch mismatch,
optimizer update mismatch, queue arithmetic mismatch, sampler mismatch, missing
RNG/state presence, selector trace mismatch, stopping mismatch, nonzero
evaluation consumption, unsupported historical/annotation schema, source
inventory mismatch, ambiguous IDs, and `MISSING_BLOCKING` evidence. The SHA gate
test proved deserialization is not reached after a payload mismatch.

- Focused V2-D: 30 passed, 0 failed.
- Combined V2-A/B/C/D: 231 passed, 0 failed.
- V2-A/B/C regression subset: 201 passed, 0 failed.
- Existing relevant formal/recovery Python regression: 128 passed, 0 failed.
- Relevant R testthat: 39 assertions passed, 2 failed in an unchanged baseline
  test expecting obsolete generation `p9gen_acb72f...`; tracked config at both
  start/current HEAD is `p9gen_batchuniq_20260831`. No V2-D R code changed.
- Main/formal/recovery `targets::tar_validate()`: 3/3 passed, no targets run.
- Runtime schemas parsed and passed Draft 2020-12 validation through the combined
  V2 schema suite; legacy valid/invalid fixtures passed.
- Python compile/import passed.
- `git diff --check`, Markdown/path checks, immutable hashes, clean trees, and
  origin synchronization are rerun immediately before/after publication.
- The unrelated long-running pytest process was not awaited, reused, terminated,
  or touched.

## Complexity accounting

V2-D adds one cohesive runtime adapter, one bounded schema, and one focused test
module. The adapter exposes five useful entry points (source declaration,
inspection, validation, mapping, and dry-run construction), five immutable
result/source dataclasses, one stable error type, and ten private inspection/
hash/time helpers. V2-B gains one annotation validation branch; V2-C gains a
public name for its existing comparator.

No migration framework, alternate bundle/ledger/selector, controller, mutable
status, lock, authority/reservation/attempt/operation, recovery path, target,
store, checkpoint writer, or acceptance path was added.

## Prohibited-work accounting

| Activity | Count |
|---|---:|
| New production authority / reservation / attempt / run / operation | 0 / 0 / 0 / 0 / 0 |
| Production/canonical acceptance | 0 |
| Training / resume / recovery / validation execution | 0 / 0 / 0 / 0 |
| Held-out evaluation execution / metric recomputation | 0 / 0 |
| Production checkpoint/cache writes | 0 / 0 |
| Historical checkpoint/validation/state/report mutations | 0 / 0 / 0 / 0 |
| Dissertation mutations | 0 |
| Canonical historical bundle/finalization publication | 0 / 0 |
| Historical acceptance/resolver consumption | 0 / 0 |
| Active target additions / P9 target executions | 0 / 0 |

## Immutable evidence

| Evidence | Before | Pre-publication after |
|---|---|---|
| Epoch-105 payload | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` |
| Epoch-105 manifest | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` |

The post-push readback is recorded in the final response. No historical file
was opened for writing.

## Risks and next work unit

No V2-D-specific blocker remains and retraining is not required by the imported
evidence. The patience-reset discrepancy described above must be resolved before
canonical V2-G. Restricted legacy parsing retains bounded residual risk. The
unchanged stale R test expectation should be repaired in a separately scoped
maintenance change.

The exact next work unit is:

`V2-E: migrate P9-B, selected-FM, held-out evaluation, P10, and P11 interfaces to the single V2 accepted-checkpoint resolver contract, with manual/latest/v1 fallback rejection and no downstream execution.`

V2-E was not started.
