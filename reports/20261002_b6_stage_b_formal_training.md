# B6 formal Stage B three-arm experiment

## Scope and predeclaration

Created 2026-10-02 22:50 Asia/Seoul. User authorizes fresh, formal training of
exactly B6-original, B6-S50-G, B6-S50-Ppre. Entry B6 SHA
`35863f46aff153311b7946b2404581bed0602701`, clean and synchronized with origin/B6.
No dissertation, reduced, canonical artifacts or canonical campaign changes.
This report is updated after execution as explicitly requested.

Implementation: `python/b6_formal_training.py`, `python/b6_formal_analysis.py`,
`config/b6_stage_b_training.yml` and schema, `R/b6_stage_b_training.R`,
`targets/b6_stage_b_training.R`, `_targets_b6_stage_b_training.R`, focused tests,
and dedicated dependency-network documentation. Formal source is committed
before authority issuance; the authority binds that exact SHA and a complete
Python/config/orchestration source inventory. Reports do not change science IDs.

## Immutable inputs and preflight

22,836 manifest payload references verified before implementation. Stage A
`b6a_f5d6a32cdd09cf5688b0666a`; preparation
`b6b_d5d52fa75ab30db61957a391`; CON
`b6con_032b560f2d826f3177854e91`; paired inputs
`b6s50_a37a4debfbbde575348e5470`; bounded pilot
`b6pilot_4b63bd096bcf68cfa07aa4d1`.
Original parity 22,368/22,368 PASS. Input acceptance PASS; pilot readiness
READY_FOR_STAGE_B_TRAINING_AUTHORIZATION. S50-G prepared identity
`b6prepared_76dd087e86c3adcb6067e76d`, Ppre
`b6prepared_21e3681ce766ef1bf35db3b6`, shared Fourier
`b6shared_e8ff824e161eacf7075b5f16`.

Original uses immutable hash-bound canonical prepared/Fourier inputs through
`ProductionPreparedData` and `GeometryCacheReader`; no historical weights.
S50 reads paired accepted payloads through `FormalReader` (bounded retained
payload memory, full fixed validation membership). Both segmented arms share
geometry/semantics/child RNG and differ only in SN. CON policy remains
`accepted_parent_con_nearest_chain_child_v1`, including logical off-support
inheritance. Receiver attributes and sibling INT are unchanged.

## Fixed scientific contract

All arms: d=d_c=256, heads=4, relation layers=3, dropout=.2, K_aug=8,
intensity=1, EMA=.999, peak LR=.001, global batch=32, world=2, per-rank=16,
queue=8192, temperature=.1, exclusion=750 m, masking=.30, maximum epochs=200,
76 updates/epoch. AdamW weight decay=.0001, betas=(.9,.999), eps=1e-8,
gradient norm clipping=1. Warmup 760 updates, cosine decay 14,440 updates.
Symmetric scene objective, float32 strict deterministic execution, TF32/AMP off.
Accepted resolved snapshot is copied, not base defaults. Root seed=1629790839;
arm/config names never derive seeds. Initialization is fresh for every arm.
Per-update scene/view, queue ID/center and mask hashes permit paired verification
on all common epochs (stopping epoch may differ). G/Ppre child masks must match.

Scientific functions reused unchanged: `training_worker.create_state`,
`training_update`, `full_validation`, `_stage_checkpoint`, `restore_checkpoint`;
`training_finalization.evaluate_selection_candidate` and
`qualifies_patience_reset`. Separate authority namespace `b6-stage-b-formal-v1`
is not eligible for canonical resolvers. No canonical campaign import.

Sequential GPU-pair execution under accepted lock/controller. CPU threads=1 per
rank, one arm at a time. Descriptor preparation uses configurable 8 workers ×
1 native thread, before GPU training. Each validation boundary stages full model, target,
optimizer, scheduler, queue, both rank RNGs, sampler, traces and selector state;
readback/content validation precedes immutable boundary receipt. Recovery starts
from the latest committed boundary; intermediate failed work is retained as
attempt evidence. All final boundaries are replayed at acceptance. No pilot
state is restored into a formal arm.

## Validation and diagnostics fixed before training

Every five epochs: 2,000 fixed augmented queries against the unchanged 1,000
original-scene gallery. Unit-normalized scene embeddings, cosine retrieval,
retrieval loss, separation margin, MRR/HIT@1/5/10. Selection minimizes loss;
strict abs(loss difference)<1e-4 permits higher margin then earlier epoch.
Patience four validation events resets only on loss decrease >=1e-4.
No diagnostic subset or HIT metric selects a checkpoint. Whole HIT@1 >.857
triggers campaign stop and population/input/leakage audit.

After selection, retain full gallery for all query subsets: road-nonempty,
zero-road, original count 1–8/9–49/50+, and **scene mean original-parent length**
0–50/50–100/100–250/250–500/500+ metres (left closed, right open). The existing S11 shards cover evaluation only (9,000 scenes), so reuse the
unchanged `R/scene_descriptors.R` functions on original P3 validation roads via
`R/b6_validation_descriptors.R` and `python/b6_validation_descriptors.py`.
Compute 1,000 validation descriptors in the experiment namespace; bind P3 member
checksums, category dictionary and function hash. Never compute these descriptors
on children or change canonical S11 artifacts. Fixed grouped bootstrap seed
20261002, 2,000 replicates, paired scene groups with both queries together;
percentile 95% intervals. Intervals describe scene sampling, not training-seed
uncertainty. This is a single shared-seed experiment.

Descriptive mechanisms: output-hook modality gate means, bbox-position dispersion,
road attention maximum/effective entity count, separate S50 structural relation
panel. Hooks are evaluation-only, no model edits or training RNG consumption.
Original-gallery child-parent maps are rebuilt with the accepted lineage/subdivision
functions and matched exactly against accepted child IDs before use. They support
parent attention concentration and exact sibling SN/INT/CON diagnostics without
inference from geometry proximity.

Interpretation is metric-by-metric. Both segmented arms improving supports
spatial granularity; G-only improvement suggests sibling dependence; stronger
Ppre suggests external-neighbor competition; neither improving weakens the
hypothesis. Loss/margin improvement without HIT improvement is ceiling-compatible.
For transparent summary categorization, road-nonempty paired loss CI wholly below
zero plus positive margin difference counts as supported improvement; this does
not select checkpoints or create an aggregate model ranking. All raw metrics
and intervals remain authoritative over a categorical label.

## Verification before formal launch

Python regression: 251 tests passed (formal adapters, Stage B/CON, family,
selection/finalization/checkpoint/resolver/runtime/transport). R: 83 expectations
passed (new formal graph plus Stage A/preparation/CON regressions). Dedicated
manifest has six targets; DAG acyclic and tar_validate passes. New Python compiles
and R parses. Initial validation command used an unsupported `tar_manifest(store=)`
argument; corrected to supported API. Target/global naming collision corrected
before execution. Network renderer initially required store metadata; source-file
only target populated the dedicated store. No canonical target executed.

Optimizer-free two-GPU smoke for each arm passed full 2,000/1,000 validation,
unchanged model-state assertion, canonical checkpoint readback/RNG restore, and
zero optimizer updates. Evidence:
`/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b_training/engineering-smoke-1790948786572368924`.
The first smoke attempt found missing experimental root creation; fixed before
any GPU work. Smoke checkpoint files are engineering evidence, never formal
initialization or accepted scientific models.

A second optimizer-free GPU smoke including exact gallery parent-attention
aggregation passed for all three arms, at `engineering-descriptor-validation/`
under the same experimental root.

Validation descriptor preflight: all 1,000 scene IDs and original road counts
verified, 144 zero-road scenes, mean parent lengths agree with P3
`observed_length_m` within 1e-8 m. Child IDs reproduced exactly, Ppre sibling SN
and sibling CON both zero. Full R relation descriptor adapter initially included
nullable provenance columns; narrowed to the exact three-column S11 reader
contract before successful QC. No scientific semantics changed.

Additional lifecycle/identity/replay/controller/crash/ledger/augmentation regression:
135 tests passed, including 9 repeated formal tests.

## Execution results

Pending formal authority issuance and execution. No scientific result claimed
at source freeze. Final authorities, lifecycle, trajectories, selected metrics,
paired diagnostics, resource usage and verdict will be appended after acceptance.
