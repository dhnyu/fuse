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


## Execution results — final

Completed reporting 2026-10-03T01:15:17+09:00. **EVIDENCE_MIXED**. All three formal arms completed; no formal run was restarted or resumed. No code, configuration, cache, seed or scientific rule changed between arms.

Training source SHA: `5ac7a35c36f66fdb3d9b0402ac16a987a888cb08`. Immutable design: `b6formal_e593d0bb2f2f6acd77056c76`. Publication root:

`/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b_training/b6formal_e593d0bb2f2f6acd77056c76`

| Arm | Authority | Completed / selected epoch | Updates | Termination |
| --- | --- | --- | --- | --- |
| B6-original | b6formalauth_3167ba3d10e3b8c8a0528d18 | 110 / 90 | 8360 | 4-event patience |
| B6-S50-G | b6formalauth_6503d6bc57e53ffe18aae3b8 | 155 / 135 | 11780 | 4-event patience |
| B6-S50-Ppre | b6formalauth_7b782341aceb31d2437eeaa6 | 150 / 130 | 11400 | 4-event patience |

All started with fresh online/target parameters, optimizer, scheduler, queue and EMA. Initial model hashes match exactly. Scene/view and queue ID/center hashes match on all common epochs. G/Ppre child masking hashes match on all 150 shared epochs. There are 83 formal validation-boundary checkpoint payloads; 31,540 optimizer updates across the three arms. No historical/pilot state was loaded. Global batch/world size stayed 32/2, with no accumulation, truncation, fallback or per-arm retuning.

### Whole validation: accepted production metrics

| Arm | Epoch | Retrieval loss | Margin | MRR | HIT@1 | HIT@5 | HIT@10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B6-original | 90 | 1.011032 | 0.286718 | 0.861300 | 85.6500% | 86.1000% | 86.6000% |
| B6-S50-G | 135 | 0.997802 | 0.278241 | 0.861550 | 85.7000% | 86.1000% | 86.6000% |
| B6-S50-Ppre | 130 | 0.998245 | 0.276441 | 0.861300 | 85.6500% | 86.1000% | 86.6000% |

This is metric-by-metric reporting, not an aggregate ranking. G lowers whole loss by 0.013231 and Ppre by 0.012787 relative to Original, while margins decrease by 0.008477 and 0.010278. G corrects one additional query; its whole HIT@1 difference is only 0.05 percentage points. Ppre has the same aggregate rank metrics as Original, with a different individual error.

### Road-nonempty: primary interpretation subset

856 original scenes / 1,712 augmented queries, still using all 1,000 gallery scenes.

| Arm | Loss | Margin | MRR | HIT@1 | HIT@5 | HIT@10 |
| --- | --- | --- | --- | --- | --- | --- |
| B6-original | 0.345017 | 0.334951 | 0.999708 | 99.9416% | 100.0000% | 100.0000% |
| B6-S50-G | 0.329555 | 0.325048 | 1.000000 | 100.0000% | 100.0000% | 100.0000% |
| B6-S50-Ppre | 0.330073 | 0.322945 | 0.999708 | 99.9416% | 100.0000% | 100.0000% |

Paired scene bootstrap, 2,000 replicates, seed 20261002; differences below are left arm minus right arm. Intervals are percentile 95% and exploratory, without multiplicity adjustment.

| Comparison | Metric | Difference | 95% CI |
| --- | --- | --- | --- |
| B6-S50-G minus B6-original | retrieval_loss | -0.015463 | [-0.021643, -0.009342] |
| B6-S50-G minus B6-original | margin | -0.009903 | [-0.015559, -0.004777] |
| B6-S50-G minus B6-original | HIT@1 | 0.000584 | [0.000000, 0.001752] |
| B6-S50-Ppre minus B6-original | retrieval_loss | -0.014944 | [-0.021278, -0.008337] |
| B6-S50-Ppre minus B6-original | margin | -0.012006 | [-0.017705, -0.006765] |
| B6-S50-Ppre minus B6-original | HIT@1 | 0.000000 | [-0.001752, 0.001752] |
| B6-S50-Ppre minus B6-S50-G | retrieval_loss | 0.000518 | [-0.001678, 0.002776] |
| B6-S50-Ppre minus B6-S50-G | margin | -0.002103 | [-0.004005, 0.000007] |
| B6-S50-Ppre minus B6-S50-G | HIT@1 | -0.000584 | [-0.001752, 0.000000] |

Both S50 arms have lower road-nonempty loss with intervals excluding zero, **and lower separation margins with intervals excluding zero**. G/Ppre loss difference includes zero. Thus the loss benefit survives sibling-SN removal, but the evidence does not show an across-metric representation improvement. Loss aggregates all gallery competitors; margin compares the closest competitor, so the two can legitimately move in opposite directions. The G HIT@1 gain is one query and its paired interval includes zero.

### Original road-count and mean-parent-length strata

Counts are original observed parents; length is mean original observed parent length per scene. Empty scenes are excluded from length bins. Full gallery unchanged.

| Stratum | Scenes | Original loss / margin / H1 | G loss / margin / H1 | Ppre loss / margin / H1 |
| --- | --- | --- | --- | --- |
| count_1_8 | 105 | 0.326184 / 0.310430 / 99.524% | 0.335288 / 0.286472 / 100.000% | 0.343803 / 0.278498 / 100.000% |
| count_9_49 | 506 | 0.343611 / 0.333336 / 100.000% | 0.332523 / 0.322080 / 100.000% | 0.334143 / 0.319183 / 99.901% |
| count_50_plus | 245 | 0.355992 / 0.348796 / 100.000% | 0.320967 / 0.347709 / 100.000% | 0.315784 / 0.349761 / 100.000% |
| length_0_50 | 53 | 0.359469 / 0.322684 / 100.000% | 0.318240 / 0.336016 / 100.000% | 0.307284 / 0.336824 / 100.000% |
| length_50_100 | 557 | 0.348706 / 0.341656 / 100.000% | 0.328328 / 0.333674 / 100.000% | 0.324949 / 0.333670 / 100.000% |
| length_100_250 | 233 | 0.337633 / 0.320215 / 99.785% | 0.334658 / 0.305737 / 100.000% | 0.345312 / 0.298859 / 99.785% |
| length_250_500 | 13 | 0.260424 / 0.361788 / 100.000% | 0.336776 / 0.256825 / 100.000% | 0.369368 / 0.238517 / 100.000% |
| length_500_inf | 0 | NA | NA | NA |

The clearest loss reduction is in the already road-rich 50+ stratum: G −0.035026 (CI [−0.043540, −0.026613]); Ppre −0.040209 (CI [−0.049201, −0.031483]). Margin changes there include zero. In the 1–8 stratum, loss point estimates worsen and intervals include zero; margins fall for both arms. The 250–500 m mean-parent stratum worsens in loss and margin, but has only 13 scenes: treat it cautiously. There are no 500+ mean-parent scenes. These findings do **not** establish that having a few long road entities was a major cause of B6 weakness. Count and length strata are correlated observational descriptors, not independent randomized interventions.

### Zero-road ceiling verification

All three selected models: 144 original gallery scenes and 288 query views have exactly one bitwise-unique empty representation each, with maximum within-set difference 0. Zero-road margin is 0; HIT@1 is 1/144. The resulting whole-population ceiling is (856 + 1)/1000 = 85.70%, consistent with observed results. No pseudo-road, empty token or fallback was introduced. Empty-scene loss is approximately 4.97012–4.97016; the nonempty loss benefit is not an empty-scene calibration artifact.

### Structural and representation mechanisms

| Original validation gallery, 1,000 scenes | Original | S50-G | S50-Ppre |
| --- | --- | --- | --- |
| Road entities | 31843 | 67801 | 67801 |
| Ordered relation-mask pairs | 267580 | 635266 | 649024 |
| SN bits | 267580 | 635266 | 577252 |
| INT bits | 108250 | 180190 | 180190 |
| CON bits | 105344 | 105394 | 105394 |
| Sibling SN bits | 0 | 86918 | 0 |
| Sibling INT bits | 0 | 71772 | 71772 |
| Sibling CON bits | 0 | 0 | 0 |

S50 entity growth is 2.129× in this full validation gallery, distinct from the 32-scene Stage A pilot estimate. Ordered pair growth is 2.374× for G and 2.426× for Ppre. G sibling SN share is 13.682%; sibling INT share is 39.831% for both policies. Ppre recovers 28,904 external ordered SN pairs, while retaining sibling INT. Therefore removing SN bits does not imply removing relation-mask rows; Ppre has more rows despite fewer SN bits. Original R–R counts are the induced road subgraph of accepted P3 full-source relation tables in `validation_descriptors/input/*/edges.parquet`. Bit counts are not added together and called edges.

The accepted 105,344 ordered parent CON pairs have 105,400 directed original-node causes (56 multi-cause ordered parent pairs). Lifting collapses six causes onto an existing child pair, yielding 105,394 child CON rows. The 50 additional rows thus preserve distinct original-node causes rather than introduce synthetic topology. G and Ppre CON/INT are identical, sibling CON is zero. All source-parent mappings match accepted child IDs exactly. These are gallery diagnostics; accepted post-bank training views still preserve the approved logical off-support CON policy.

| Gallery mechanism (nonempty-scene means unless entity count) | Original | S50-G | S50-Ppre |
| --- | --- | --- | --- |
| Entities, all-scene mean | 31.843000 | 67.801000 | 67.801000 |
| BBox-center dispersion, m | 176.840816 | 178.219845 | 178.219845 |
| Effective attended entities | 34.681554 | 71.595818 | 71.203147 |
| Maximum entity attention | 0.093887 | 0.049344 | 0.049710 |
| Effective attended parents | 34.681554 | 25.484080 | 25.440180 |
| Maximum parent attention | 0.093887 | 0.136961 | 0.137574 |

| Mean modality gate | Original | S50-G | S50-Ppre |
| --- | --- | --- | --- |
| Relative position | 0.561007 | 0.558243 | 0.561536 |
| Geometry | 0.294406 | 0.283963 | 0.293339 |
| Semantics | 0.144587 | 0.157794 | 0.145125 |

Effective attention count = 1/sum(weight²); parent weights sum child weights within original source parent. Although S50 distributes attention over more entities, it concentrates more mass on fewer original parents (effective parents ≈25.4 versus 34.7). This is a possible pooling-side mechanism, not proof of causation. Gates remain dominated by relative position (~0.56). These hooks run only during validation and do not alter the model. Original-parent descriptors and child-derived structure are separate artifacts.

### Measured resources

| Arm | Worker wall, min | Update p50 / p95 / max, s | Assembly p50, s | Peak allocated GiB | Peak reserved GiB | Peak rank RSS GiB |
| --- | --- | --- | --- | --- | --- | --- |
| B6-original | 41.40 | 0.2457 / 0.4093 / 1.7372 | 0.1586 | 0.790 | 0.898 | 7.082 |
| B6-S50-G | 36.48 | 0.1624 / 0.2186 / 0.6370 | 0.0742 | 1.251 | 2.127 | 2.392 |
| B6-S50-Ppre | 35.02 | 0.1612 / 0.2171 / 0.6425 | 0.0737 | 1.252 | 2.424 | 2.387 |

Worker wall includes updates, validation and checkpoint publication after initialization. Corresponding targets wall times were 41m46s / 36m43s / 35m17s. Peak allocated VRAM is 1.584× Original for both S50 arms. All fit the unchanged 32/2 protocol on the two RTX A6000s. Step time was lower for S50, but Original reads full-source hash-bound payloads before projection whereas S50 reads compact road payloads; this cache-layout difference prevents attributing speed to segmentation. Forward/backward phase timings were not separately instrumented in formal execution; bounded-pilot timings are not substituted. CPU assembly and total update timings above are measured across all formal updates, including cold reads.

### Reporting precision incident and recovery

The first `b6f_comparison` attempt failed its 2e-6 aggregate readback check. Per-query float32 values were correct, but a strided NumPy float32 mean differed from production PyTorch reduction by −3.70e-6 / +4.05e-6 / +3.70e-6. Casting those same values to float64 before reporting reduction reduced maximum discrepancy to 5.20e-8. No tolerance was loosened and no query, model, checkpoint, validation event, selection or training code changed.

A separate reporting contract `b6report_06afd23acc6fd32db1f16f0c` binds `scripts/b6_stage_b_results.py`. The adapter preserves the frozen `python/b6_formal_analysis.py` and casts only returned per-query metric arrays. `_targets_b6_stage_b_results.R` / `targets/b6_stage_b_results.R` / `R/b6_stage_b_results.R` execute reporting only in `/mnt/hdd002/dhnyu/fusedata/targets/fuse-b6-stage-b-results`. Its initial script import shadowed the production module with `scripts/training_worker.py`; the adapter now prepends `python/` before imports. Both issues were reporting-only and occurred after all three formal runs completed.

Reproduction order for these immutable runs: run the reporting graph to publish corrected aggregate acceptance, then rerun the original training graph. The latter skips all five successful upstream targets and verifies the immutable comparison manifest. The frozen original reducer is intentionally retained as executed provenance; use the reporting adapter for regeneration. No training replay or new experiment identity for trained weights was needed.

### Acceptance, verification and preservation

Final checks: 378 focused/relevant Python tests PASS; 83 R expectations PASS; Python compile and R parse PASS; config/schema PASS; both dedicated manifests/DAGs acyclic and tar_validate PASS; all six formal targets and both reporting targets completed successfully. The failed comparison attempt was inspected through tar_meta, corrected through the separate reporting adapter, and retried. Checkpoint selection replay, checkpoint/vector checksum readback, common-epoch ordering and G/Ppre masking checks PASS. Dependency-network HTML is regenerated for both entrypoints.

`comparison/manifest.json` binds all numeric result, query-Parquet, descriptor and structural outputs. `final_audit/<arm>-acceptance.json` binds each authority, source SHA, frozen contract, runtime provenance, events, all performance receipts, all validation boundaries/vectors and all formal checkpoints by SHA-256. `final_audit/manifest.json` binds those per-arm acceptances and the reporting contract. These are experimental authorities and cannot resolve as canonical S09 accepted models.

Preserved: canonical S09 and all accepted Stage A/B/CON/cache payloads; dissertation HEAD `6a43d30133db01a773f6b5d355fc1290b544072b` remains unchanged; reduced remains `851efd0c94120ff250f34502fceba73a45080281`. No S10/S11/S12 campaign executed, no FM changes, no canonical result replacement. Only B6 experiment code/report/network documentation is committed; weights, caches, logs and stores remain outside Git.

### Interpretation and limitations

**EVIDENCE_MIXED.** There is a modest, paired loss reduction for road-containing queries under both G and Ppre, so that reduction does not require sibling SN competition. However, nearest-competitor separation worsens, rank gains are at most one query, sparse-road scenes do not show reliable loss gains, and the small long-parent stratum worsens. This does not establish coarse road entities as a major cause of B6 weakness, does not isolate geometry encoding from position/relations/pooling, and does not justify changing canonical B6 or FM. Single-seed results do not quantify optimization-seed uncertainty. Stratum intervals are exploratory and not multiplicity-adjusted; 13-scene and empty bins limit interpretation.

Formal training executed: YES. Formal arms completed: 3/3. Formal checkpoint creation: YES. Canonical S09/artifacts/dissertation/reduced modified: NO.

### Complete validation trajectories

Metrics below are the unchanged production validation events. Final-selected epoch is marked `*`; patience is the accepted loss-only reset counter. HIT@5 and HIT@10 equal 86.10% and 86.60% at every event.

#### B6-original

| Epoch | Loss | Margin | MRR | HIT@1 | Patience |
| --- | --- | --- | --- | --- | --- |
| 5 | 2.305820 | 0.157755 | 0.861550 | 85.7000% | 0 |
| 10 | 1.547717 | 0.205267 | 0.861550 | 85.7000% | 0 |
| 15 | 1.309192 | 0.230816 | 0.861550 | 85.7000% | 0 |
| 20 | 1.209342 | 0.250444 | 0.861550 | 85.7000% | 0 |
| 25 | 1.154553 | 0.257616 | 0.861550 | 85.7000% | 0 |
| 30 | 1.085809 | 0.268303 | 0.861300 | 85.6500% | 0 |
| 35 | 1.069148 | 0.274063 | 0.861300 | 85.6500% | 0 |
| 40 | 1.056801 | 0.275063 | 0.861300 | 85.6500% | 0 |
| 45 | 1.034029 | 0.281585 | 0.861300 | 85.6500% | 0 |
| 50 | 1.025749 | 0.281846 | 0.861300 | 85.6500% | 0 |
| 55 | 1.014845 | 0.286160 | 0.861300 | 85.6500% | 0 |
| 60 | 1.021777 | 0.284611 | 0.861300 | 85.6500% | 1 |
| 65 | 1.016904 | 0.285233 | 0.861300 | 85.6500% | 2 |
| 70 | 1.017785 | 0.285221 | 0.861550 | 85.7000% | 3 |
| 75 | 1.013297 | 0.285699 | 0.861550 | 85.7000% | 0 |
| 80 | 1.014249 | 0.285503 | 0.861300 | 85.6500% | 1 |
| 85 | 1.016179 | 0.286102 | 0.861300 | 85.6500% | 2 |
| 90* | 1.011032 | 0.286718 | 0.861300 | 85.6500% | 0 |
| 95 | 1.013700 | 0.286330 | 0.861300 | 85.6500% | 1 |
| 100 | 1.012101 | 0.286263 | 0.861300 | 85.6500% | 2 |
| 105 | 1.012670 | 0.286727 | 0.861550 | 85.7000% | 3 |
| 110 | 1.013396 | 0.285771 | 0.861300 | 85.6500% | 4 |

#### B6-S50-G

| Epoch | Loss | Margin | MRR | HIT@1 | Patience |
| --- | --- | --- | --- | --- | --- |
| 5 | 2.142426 | 0.149386 | 0.861550 | 85.7000% | 0 |
| 10 | 1.464100 | 0.192211 | 0.861550 | 85.7000% | 0 |
| 15 | 1.240792 | 0.222464 | 0.861550 | 85.7000% | 0 |
| 20 | 1.161487 | 0.233368 | 0.861550 | 85.7000% | 0 |
| 25 | 1.094919 | 0.246573 | 0.861550 | 85.7000% | 0 |
| 30 | 1.073546 | 0.255510 | 0.861550 | 85.7000% | 0 |
| 35 | 1.037809 | 0.262650 | 0.861550 | 85.7000% | 0 |
| 40 | 1.037511 | 0.264094 | 0.861550 | 85.7000% | 0 |
| 45 | 1.030973 | 0.265707 | 0.861550 | 85.7000% | 0 |
| 50 | 1.017541 | 0.269083 | 0.861550 | 85.7000% | 0 |
| 55 | 1.022307 | 0.268108 | 0.861550 | 85.7000% | 1 |
| 60 | 1.012564 | 0.271416 | 0.861550 | 85.7000% | 0 |
| 65 | 1.010088 | 0.272624 | 0.861550 | 85.7000% | 0 |
| 70 | 1.009681 | 0.273704 | 0.861550 | 85.7000% | 0 |
| 75 | 1.005554 | 0.274240 | 0.861550 | 85.7000% | 0 |
| 80 | 1.005814 | 0.274217 | 0.861550 | 85.7000% | 1 |
| 85 | 1.005456 | 0.274419 | 0.861550 | 85.7000% | 2 |
| 90 | 1.006011 | 0.274801 | 0.861550 | 85.7000% | 3 |
| 95 | 1.001140 | 0.276414 | 0.861550 | 85.7000% | 0 |
| 100 | 1.000217 | 0.276626 | 0.861550 | 85.7000% | 0 |
| 105 | 1.000533 | 0.276819 | 0.861550 | 85.7000% | 1 |
| 110 | 1.001784 | 0.276326 | 0.861550 | 85.7000% | 2 |
| 115 | 0.999615 | 0.276693 | 0.861550 | 85.7000% | 0 |
| 120 | 1.002956 | 0.276363 | 0.861550 | 85.7000% | 1 |
| 125 | 1.001140 | 0.277187 | 0.861550 | 85.7000% | 2 |
| 130 | 1.000632 | 0.277088 | 0.861550 | 85.7000% | 3 |
| 135* | 0.997802 | 0.278241 | 0.861550 | 85.7000% | 0 |
| 140 | 0.999433 | 0.277833 | 0.861550 | 85.7000% | 1 |
| 145 | 0.998678 | 0.278070 | 0.861550 | 85.7000% | 2 |
| 150 | 0.999050 | 0.278497 | 0.861550 | 85.7000% | 3 |
| 155 | 0.998395 | 0.278850 | 0.861550 | 85.7000% | 4 |

#### B6-S50-Ppre

| Epoch | Loss | Margin | MRR | HIT@1 | Patience |
| --- | --- | --- | --- | --- | --- |
| 5 | 2.177489 | 0.146846 | 0.861550 | 85.7000% | 0 |
| 10 | 1.454819 | 0.195598 | 0.861550 | 85.7000% | 0 |
| 15 | 1.259842 | 0.219667 | 0.861550 | 85.7000% | 0 |
| 20 | 1.135539 | 0.238426 | 0.861550 | 85.7000% | 0 |
| 25 | 1.082366 | 0.249206 | 0.861550 | 85.7000% | 0 |
| 30 | 1.055384 | 0.258068 | 0.861550 | 85.7000% | 0 |
| 35 | 1.041785 | 0.261215 | 0.861550 | 85.7000% | 0 |
| 40 | 1.028859 | 0.264980 | 0.861550 | 85.7000% | 0 |
| 45 | 1.023230 | 0.266030 | 0.861300 | 85.6500% | 0 |
| 50 | 1.021197 | 0.267800 | 0.861550 | 85.7000% | 0 |
| 55 | 1.021875 | 0.266785 | 0.861550 | 85.7000% | 1 |
| 60 | 1.016243 | 0.269205 | 0.861550 | 85.7000% | 0 |
| 65 | 1.008291 | 0.271682 | 0.861550 | 85.7000% | 0 |
| 70 | 1.010044 | 0.272187 | 0.861300 | 85.6500% | 1 |
| 75 | 1.008030 | 0.271884 | 0.861300 | 85.6500% | 0 |
| 80 | 1.008873 | 0.270748 | 0.861300 | 85.6500% | 1 |
| 85 | 1.004567 | 0.272981 | 0.861300 | 85.6500% | 0 |
| 90 | 1.009087 | 0.271999 | 0.861300 | 85.6500% | 1 |
| 95 | 1.001418 | 0.274322 | 0.861300 | 85.6500% | 0 |
| 100 | 1.000531 | 0.275050 | 0.861300 | 85.6500% | 0 |
| 105 | 1.001426 | 0.275139 | 0.861300 | 85.6500% | 1 |
| 110 | 0.999731 | 0.275177 | 0.861300 | 85.6500% | 0 |
| 115 | 1.000656 | 0.275153 | 0.861300 | 85.6500% | 1 |
| 120 | 1.002468 | 0.274735 | 0.861300 | 85.6500% | 2 |
| 125 | 1.001608 | 0.275187 | 0.861300 | 85.6500% | 3 |
| 130* | 0.998245 | 0.276441 | 0.861300 | 85.6500% | 0 |
| 135 | 0.998674 | 0.276318 | 0.861550 | 85.7000% | 1 |
| 140 | 1.000429 | 0.275872 | 0.861300 | 85.6500% | 2 |
| 145 | 0.999537 | 0.276668 | 0.861300 | 85.6500% | 3 |
| 150 | 0.998665 | 0.276868 | 0.861300 | 85.6500% | 4 |
