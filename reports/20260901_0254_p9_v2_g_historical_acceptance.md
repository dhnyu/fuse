# P9 v2 V2-G Canonical Historical Import and Acceptance

## Verdict

`P9_V2_G_HISTORICAL_ACCEPTANCE_PASS_PUSHED` is the publication verdict,
conditional on the final post-report regression, commit, push, clean-tree/origin
check, and immutable-evidence readback recorded in the final response.

## Purpose and lineage

- Executed: 2026-09-01 02:54 Asia/Seoul.
- Fuse start: `reduced@f03c87d0ce58a34784e46a5d954c32ae62b32534`,
  clean and origin ahead/behind `0/0`.
- Dissertation:
  `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, clean,
  origin ahead/behind `0/0`, and unchanged.
- Input prompt: execute only V2-G using the V2-D adapter and V2-A/B/C/E
  runtime, under one bounded authority, with no scientific execution or v1
  mutation.

## Independent prepublication audit

The V2-D inspector was rerun before any canonical write. Restricted,
hash-gated `weights_only=True` checkpoint inspection reconfirmed:

- 25/25 exact validation-checkpoint pairs;
- 58 immutable source entries, digest
  `282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c`;
- 21 directly available, 6 deterministically derivable, 2 legacy-annotated,
  2 not applicable, and 0 missing/blocking fields;
- all online/EMA/optimizer/scheduler/RNG/queue/sampler/selector/trace state;
- validation every five epochs, 76 updates/epoch, coherent global queue
  arithmetic, cursor-zero exact resume boundaries, and world size two;
- evaluation consumption zero;
- v1 terminal state unchanged `FAILED_NONRESUMABLE`.

The actual V2-A/B/C dry-run replay using corrected
`p9-selection-v2.1.0` remained bundle `p9rb_65fc954ba2b95475aaf38ad7`
and selected epoch 105 before publication.

## Authority

Exactly one deterministic migration/publication authority was created:

- identity: `p9authv2_47f350372bf94162db8f9142`;
- content SHA-256:
  `47f350372bf94162db8f91427e06ac00b7d3b732ed46e89b05bb852737678b71`;
- source run: `p9run_6887930091dd2f2bfedc3c96`;
- imported run: `p9runv2_d6ffbd951bc813f78defeacc`;
- source-inventory and scientific-contract bindings are exact.

Its only permissions are canonical historical import, canonical bundle
publication, pure finalization, acceptance publication, eligibility snapshot
publication, and resolver verification. It explicitly prohibits training,
resume, recovery, validation, evaluation, checkpoint/cache modification, and
downstream scientific execution. No reservation, attempt, operation, or
recovery identity was created.

## Canonical artifacts

Canonical root:
`/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical`.

| Artifact | Identity | Full content hash |
|---|---|---|
| Authority | `p9authv2_47f350372bf94162db8f9142` | `47f350372bf94162db8f91427e06ac00b7d3b732ed46e89b05bb852737678b71` |
| Imported run | `p9runv2_d6ffbd951bc813f78defeacc` | hash-chained closed ledger, 106 events |
| Run bundle | `p9rb_78322173dfd691baf67a44a0` | `78322173dfd691baf67a44a00a270e18d2a68f45c44121f85a42bcc549121a25` |
| Finalization | `p9fin_2383ccda2e5391ecf75c6010` | `2383ccda2e5391ecf75c6010d4b0e5e01ad2cb941ce7d2fac67a81860f19fd04` |
| Acceptance | `p9accv2_d93b01ef13c3f26a22287ce7` | `d93b01ef13c3f26a22287ce79d16baacc2471de0d2eedfb06fee460f2b94a0c2` |
| Eligibility | `p9elig_335f0baafea2a7e381f3634e` | `335f0baafea2a7e381f3634e7beb4e56899dfdbe332fa4546ec4fdad9d4184e8` |

The canonical legacy annotation is schema-distinct from V2-D, binds the
authority and original dry-run annotation hash, and preserves the v1 identities
as provenance only. The bundle references all large checkpoint payloads and
manifests by immutable structured locator and hash; it copies none of them.

Authority and eligibility use same-filesystem staging, file `fsync`, atomic
link-if-absent, directory `fsync`, and create-or-validate. The ledger and bundle
reuse V2-A/B atomic publication. Acceptance reuses the V2-C short
acceptance-identity `flock`; atomic directory rename exposing
`acceptance_commit_manifest.json` remains its sole commit point.

## Finalization and resolver

The pure V2-C finalizer, version `p9-v2-finalizer-v2`, selected naturally from
all 25 committed candidates:

- checkpoint `p9ck_42f7957d2ea998ac9e8ff705`;
- completed/resume epoch 105/106;
- checkpoint optimizer update 7,980;
- retrieval loss `0.3806893527507782`;
- mean source-separation margin `0.28760260343551636`;
- stopping boundary epoch 125/resume 126/update 9,500;
- patience four, reached after four qualifying non-improvements.

Independent bundle validation, finalization-result validation, acceptance
readback, eligibility readback, and the V2-E resolver all passed. P9-B,
selected-FM, held-out evaluation, P10, and P11 resolver interfaces returned the
same immutable record. None executed scientific work.

Duplicate publication returned the exact same authority, ledger, bundle,
finalization, acceptance, and eligibility identities. Acceptance reported
`created=false`; the canonical root contains exactly one `p9accv2_*` directory
and one `p9authv2_*.json` authority.

## Fail-closed matrix

Copied/synthetic tests rejected source-inventory mutation, payload and manifest
hash changes, epoch/pair mismatch, queue mismatch, sampler mismatch, selector
trace mismatch, stopping-boundary mismatch, nonzero evaluation consumption,
authority scope/hash mutation, bundle identity mutation, and finalization
identity mutation. A V2-D `NONCANONICAL_DRY_RUN` bundle is now explicitly
rejected by both acceptance publication and readback validation.

## Implementation and complexity

Added one cohesive 374-line V2-G module with two result dataclasses and nine
functions. It composes the existing importer, ledger, bundle, finalizer,
publisher, eligibility, resolver, and five consumer adapters. One migration
authority schema was added; the legacy annotation schema gained one canonical
variant. No alternate importer, serializer, ledger, selector, finalizer,
publisher, resolver, controller, lock class, or recovery path was added.

The canonical root contains 239 small metadata/ledger files totaling 415,390
bytes. It contains no copied checkpoint or cache payload.

## Validation

- Focused V2-G: 17 passed, 0 failed.
- Combined V2-A/B/C/D/E/F/G: 318 passed, 0 failed.
- Existing relevant P8/P9/formal/recovery Python: 162 passed, 0 failed.
- Relevant R testthat: 39 assertions passed and the two documented pre-existing
  stale generation assertions failed; no unrelated R code was modified.
- Main/formal/recovery `targets::tar_validate()`: 3/3 passed using temporary
  stores; no target executed.
- All P9 v2 schemas parsed and passed Draft 2020-12 meta-validation.
- Python compile/import and `git diff --check`: passed before publication.
- Final post-report regression and repository checks are recorded in the final
  response.

## Prohibited-work accounting

| Activity | Count |
|---|---:|
| Migration/publication authority | 1 (explicitly required) |
| Reservation / attempt / operation / recovery identity | 0 / 0 / 0 / 0 |
| Training / resume / recovery | 0 / 0 / 0 |
| Validation / held-out evaluation / metric recomputation | 0 / 0 / 0 |
| Checkpoint/cache writes | 0 / 0 |
| Historical checkpoint/validation/state/report mutation | 0 |
| Dissertation mutation | 0 |
| Downstream scientific execution | 0 |
| V1 retirement / V2-H implementation | 0 / 0 |
| Canonical imported ledger/bundle/finalization/acceptance/eligibility | 1 / 1 / 1 / 1 / 1 |

## Historical immutability

| Evidence | Before | After canonical publication |
|---|---|---|
| Epoch-105 payload | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` | same |
| Epoch-105 manifest | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` | same |
| Full source inventory | `282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c` | same, 58 entries |
| v1 terminal state | `FAILED_NONRESUMABLE` | same |

## Risks and next unit

Restricted historical PyTorch parsing retains the documented residual parser
risk, mitigated by the pre-deserialization hash gate and fixed allowlist. V1
remains executable until the separately authorized V2-I retirement unit; this
work did not retire it.

The exact next work unit is:

`V2-H: production v2 training-controller implementation and production-shaped non-training pilot for future runs.`

V2-H was not started.
