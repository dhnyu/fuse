# P9 V2-H Production Training Controller

## Verdict

`P9_V2_H_PRODUCTION_TRAINING_CONTROLLER_PASS_PUSHED`

This report records the implementation result before the containing commit was
created. The final containing commit and remote synchronization are reported by
the task response and `git log`; the starting Fuse HEAD was
`2f5c89ee26b6759126f7ff3c05e19fb397bce4a7` on `reduced`. The dissertation
remained `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a` and was not
modified.

Execution time: 2026-09-01 Asia/Seoul. Prompt scope: implement a future formal
P9 v2 controller and validate production-shaped construction without any
optimizer update or formal execution.

## Audit findings

V2-A through V2-I remain the authoritative ledger, replay, bundle, finalizer,
acceptance, resolver, historical-import, downstream, and retirement layers.
The active dissertation and accepted P8 plan agree on validation every five
epochs, loss equivalence strictly below `1e-4`, margin then earlier-epoch
selection, loss-only patience reset at least `1e-4`, and patience four.

The prompt's five flat-removal P9-B labels do not match the current dissertation
or accepted P8 matrix `p8cm_cd7d0f45dd41a7c351ea4d78`. The implementation
therefore follows the authoritative cumulative templates:
`cmp_a1_geometric_core`, `cmp_a2_semantic_enriched`,
`cmp_a3_object_context_enriched`, `cmp_a4_raster_complete_non_relational`,
`cmp_a5_relation_type_agnostic`, `cmp_ssv_like`, and `cmp_ds_like`. No
methodology was changed.

## Controller architecture

- `python/p9_v2_training_controller.py` is the PyTorch-free control plane. It
  validates authority/startup, derives run identity, owns one ledger writer and
  one execution lock, coordinates checkpoint commit/linkage, and replays state.
- `python/p9_v2_training_pilot.py` is the science-plane construction and
  forward-only pilot. It imports model/data/optimizer primitives but no
  acceptance or target APIs.
- `scripts/p9_v2_training_controller.py` validates one explicit authority and
  supervises a separate science-worker command through canonical JSONL event
  proposals. It never performs model updates.
- `scripts/p9_v2_training_pilot.py` is nonauthorizing and writes only to its
  caller-provided temporary root.
- `scripts/p9_v2_resolve_checkpoint.py` makes the last target accept only a
  canonical acceptance identity and validates the existing resolver chain; it
  accepts no checkpoint path.
- Existing V2-B/V2-C/V2-E APIs remain the only bundle, finalization,
  acceptance, eligibility, and resolver path. No alternate subsystem exists.

## Identity model

The only new active identities are the existing V2 classes:

1. `p9authv2_`: a four-field V2-B bound document. Its content hash binds the
   accepted P8 configuration/hash, scientific implementation hash, methodology,
   P3-P8/cache parents, augmentation/fixed-validation identities, selection
   contract, root seed, world size, and exact-resume policy.
2. `p9runv2_`: deterministic from authority content hash and scientific run
   key. Exact resume continues this identity and ledger.

Paths, PID, hostname, log/store path, wall clock, and lock state are excluded.
No reservation, attempt, operation, or recovery identity was introduced.

Startup requires `reduced`, clean source/dissertation trees, the pinned
dissertation commit, valid retirement manifest and guards, accepted P8 row,
all exact parents, production cache ID/manifest/acceptance, zero evaluation
ancestry, separate writable/immutable roots, disk/read checks, and exactly two
visible GPUs. The explicitly configured immutable eligibility snapshot is
followed to accepted bundle configuration evidence; an already accepted ID or
hash is rejected without directory enumeration or `latest` lookup.

## Event, resume, and failure lifecycle

The controller writes the existing V2-A vocabulary. Rank 0 may propose epoch,
progress, update, validation-checkpoint, early-stop, and completion evidence;
the controller writes authority/start/interruption/failure transitions. A
progress event is batched rather than forced per update.

Exact resume requires the replayed latest durable boundary to equal the latest
committed checkpoint boundary and yields
`IN_PROGRESS / INTERRUPTED_RESUMABLE / EXACT_RESUME_ALLOWED`. Missing or corrupt
evidence cannot resume. Nonfinite science is recorded as
`SCIENTIFIC_DIVERGENCE`, not infrastructure failure; this covers the P8
`cfg_lr_10` outcome contract.

`commit_validation_checkpoint()` publishes opaque payload and manifest bytes,
verifies their hashes, then appends one
`VALIDATION_CHECKPOINT_COMMITTED`. Before that ledger event the checkpoint is
not a candidate. Crash/retry returns zero or exactly one linked candidate.
Checkpoint presence flags require online/EMA model, optimizer, scheduler,
queue, sampler, all-rank RNG, training/validation traces, early stopping, and
best-state convenience evidence. The finalizer remains selection authority.

## Targets integration

`_targets_p9_v2_training.R` has eight coarse targets and seven target-to-target
edges. It is inert without an explicit `P9_V2_TRAINING_AUTHORITY`. The
controller closure contains one authority/configuration and excludes other
P9-A variants, P9-B, evaluation, P10, P11, maintenance, v1, and recovery.
`targets` metadata is not scientific identity. The generated snapshot is
`artifacts/targets-network-p9-v2-training/targets-network.html`: 8 targets,
7 edges, one weak component; its temporary metadata store ran an empty pipeline
and no target command.

## Production-shaped non-training pilot

The final pilot used accepted `cfg_d48`, the full production cache, two RTX
A6000 GPUs with NCCL/DDP, a real global batch of 32 (16 per rank), fixed
validation identity resolution (400 scenes), model, EMA, AdamW optimizer,
exact scheduler, queue, sampler, and geometry cache. It computed one finite
forward-only contrastive loss per rank under `no_grad`:

| Rank | Local batch | Loss | State unchanged | Updates | Queue count |
|---:|---:|---:|---|---:|---:|
| 0 | 16 | 2.7300751209259033 | yes | 0 | 0 |
| 1 | 16 | 3.0593011379241943 | yes | 0 | 0 |

Backward, optimizer step, EMA update, queue enqueue, checkpoint publication,
acceptance publication, validation execution, and evaluation were all zero.
Temporary pilot evidence was not retained in a canonical namespace.

## Crash/restart matrix

| Boundary | Restart observation |
|---|---|
| Before/inside ledger staging and before event rename | Previous valid ledger |
| After event rename, before directory fsync/tail update | Event exactly once |
| Before checkpoint staging/payload/manifest/directory exposure | No canonical checkpoint |
| After checkpoint directory exposure, before directory fsync | One valid checkpoint; retry validates |
| Checkpoint committed before ledger event | Immutable but candidate-ineligible; retry links once |
| After validation-checkpoint ledger event | Candidate exactly once |
| Duplicate controller | Second `flock` acquisition rejected |
| Stale owner bytes after process death | New kernel lock succeeds; ledger unchanged |
| Finalization failure/retry | Existing V2-C pure retry regression passes |
| Acceptance publication failure/retry | Existing V2-C idempotent retry regression passes |

No recovery DAG, recovery authority, recovery lock, or alternate ledger path
was added.

## Variant and leakage audit

All 13 accepted P9-A rows route and construct configuration contracts without
execution: cfg_main plus the 12 remaining variants across d, K, augmentation,
EMA, information preservation, and learning rate. cfg_main authority creation
is explicitly rejected. All seven authoritative cumulative P9-B model/cache
family contracts validate without execution. `p9-selection-v2.1.0` is reused;
no selector was added.

Pilot evaluation query loads, gallery loads, embeddings, and metrics were each
zero. Evaluation ancestry is false in authority, P8 row, ledger/bundle handoff,
and startup gates.

## Validation results

| Validation | Result |
|---|---|
| Focused V2-H Python | 26 passed, 0 failed |
| Final related Python: V2-A-I, P8/P9, P7 sampler/training/cache | 372 passed, 0 failed in 198.69 s |
| New R graph assertions | 5 passed, 0 failed |
| Relevant R P9 assertions | 49 passed; 2 pre-existing stale generation assertions failed |
| `tar_validate()` | main, formal, recovery, and v2 training passed; no target execution |
| Runtime schemas | 17 P9 v2/retirement schemas pass Draft 2020-12 checks |
| Python compile/import and R parse | passed |
| Target snapshot | 8 targets, 7 edges, one component |
| `git diff --check` | passed |

The two unrelated R failures expect `p9gen_acb72f...` while immutable runtime
configuration records `p9gen_batchuniq_20260831`. They predate V2-H and were not
changed to manufacture a green result.

## Complexity accounting

Added production responsibility is bounded to one control runtime module, one
science pilot module, two thin CLI entry points, one R orchestration module,
one target definition, and three schemas. The Python files contain 35 functions
including small methods and 7 classes including typed errors/dataclasses. Each
exists for canonical authority/startup, lock/ledger/checkpoint coordination,
production science construction, or CLI separation. There is one controller,
one training lock class, one ledger writer path, and no mutable truth database.

## Immutability and prohibited-work accounting

| Item | Count |
|---|---:|
| New production authority/run/reservation/attempt/operation | 0 / 0 / 0 / 0 / 0 |
| Formal training/resume/recovery | 0 / 0 / 0 |
| Backward passes / optimizer updates / EMA updates / queue mutations | 0 / 0 / 0 / 0 |
| Production validation / held-out evaluation | 0 / 0 |
| Training checkpoint / production cache writes | 0 / 0 |
| Canonical bundle/finalization/acceptance/eligibility writes | 0 / 0 / 0 / 0 |
| P9-B/P10/P11/downstream/maintenance execution | 0 |
| Historical v1 / canonical cfg_main / retirement mutation | 0 / 0 / 0 |
| Dissertation mutation | 0 |

Readback hashes remained:

- epoch-105 payload: `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6`;
- epoch-105 manifest: `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc`;
- v1 source inventory: `282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c`;
- retirement manifest file: `4fd252ecfefa7436b0665b97cabe5976f3000a827d8ad229d8f0a17b161aac91`;
- canonical cfg_main acceptance file: `ad1fe493610f92fe97aa6f4b40048ff8d56e54d9e074cff74c43fe243df0a713`.

V1 remains `FAILED_NONRESUMABLE`, retirement remains
`p9ret_7921290e923f5d879e6d84c1`, and canonical acceptance remains
`p9accv2_d93b01ef13c3f26a22287ce7` selecting
`p9ck_42f7957d2ea998ac9e8ff705`.

## Remaining risk and exact next action

No production training or power-loss durability test was permitted. The first
formal run must retain the explicit one-authority gate, verify a clean committed
source tree, and monitor the production filesystem without changing scientific
cadence. It must not batch all variants.

Exact next work unit:

`P9-A formal variant execution -- begin with one explicitly authorized non-main hyperparameter configuration, using the new V2 controller.`

Remaining P9-A: 12. Remaining P9-B: 7. Held-out evaluation: not started.
