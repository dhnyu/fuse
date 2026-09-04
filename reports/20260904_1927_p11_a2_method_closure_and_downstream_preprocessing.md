# P11-A2 Method Closure and Downstream Preprocessing

## Verdict

`P11_A2_METHOD_CLOSURE_AND_PREPROCESSING_PASS_PUSHED`

Phase 1 closed every scientific decision required to map the four supplied
source families onto the fixed 1,600-scene P10 evaluation population. Phase 2
then published the accepted content-addressed dataset
`p11ds_fdb1f34c6daeda259e803e37`. No folds, new embeddings, model fitting, OOF
prediction, or P11 evaluation were produced.

## Scope and repository state

- Execution date: 2026-09-04 (Asia/Seoul)
- Fuse input: `b9a7ca38fffe4e95f77cc5d778e1c61fed9cefb0`, `reduced`, initially clean and synchronized `0/0`
- Dissertation: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, unchanged
- P10 parent: `p10acc_6e5071beee7616750dec7907`
- Scene universe: `rsi_80031f1493c75163f91b7c71`, exactly 1,600 original evaluation scenes
- Methodology decision: `p11meth_c671fa4c1ebdf9ec3e79bd64`
- `UNSPECIFIED_SCIENTIFIC_DECISION = 0` for preprocessing

The current reduced dissertation was read before implementation. Its body
defines eleven responses, overlap-weighted extensive/intensive mappings, four
living-population periods, acquisition-level ECOSTRESS aggregation, and
25-district center-based folds. No direct contradiction with this closure was
found.

## Final methodology decisions

### Scope and SGIS

Flickr is excluded from active P11 scope. Its parenthesized stale table row is
preserved historically, but the dissertation body, accepted lineage, and
available sources support exactly eleven responses.

The five 2024 SGIS targets use the previously audited codes: `to_in_001`,
`to_ga_001`, `to_ho_001`, `to_fa_010`, and `to_em_020`. Values remain official
privacy-protected releases: explicit zero remains zero and no value is denoised
or reconstructed. An omitted `(grid_id, code)` is unavailable, never zero. A
scene sum uses only explicitly present support and records represented and
missing source-grid area; no extrapolation is performed. Positive represented
area is the eligibility gate.

The nationwide 100 m and 250 m geometry packages contain repeated grid IDs.
Every duplicate examined in the scene extent had identical geometry. The
implementation deduplicates identical IDs deterministically and rejects any ID
with conflicting geometry, preventing double-counting.

### Living population

- Timezone/year: `Asia/Seoul`, 2025, all 365 daily files.
- Daytime: 09:00-18:59; nighttime: 19:00-08:59.
- Weekend class: Saturday, Sunday, and official holidays.
- Official calendar includes the 27 January temporary holiday and 3 June
  presidential-election holiday, in addition to KASI's published calendar.
- Expected hours are 2,440 weekday-daytime, 3,416 weekday-nighttime, 1,210
  weekend-daytime, and 1,694 weekend-nighttime.
- Duplicate administrative rows are summed by `(grid_id,date,hour)` only when
  every component is finite and nonnegative. Suppressed/nonnumeric components
  make that grid-hour unavailable, not partially summed or zero-filled.
- Each retained scene-hour has complete explicit spatial support. Each final
  temporal class requires at least 90% of its expected hours.

Calendar provenance is bound to the KASI 2025 calendar release
(`6ab901...b1e8`) and official temporary-holiday notices for 27 January
(`e9440e...f2c`) and 3 June (`1a54cf...6be`).

### Official land value

The source is the 2026 Seoul parcel package in EPSG:5186. The response is the
overlap-area-weighted mean in KRW/m2. `st_make_valid()` is allowed only when the
same parcel identity becomes valid nonempty polygonal geometry. Duplicate
parcel IDs fail closed. Geometry without value is unavailable, value without
geometry cannot contribute, and neither is imputed or zero-filled.

The source-wide audit retained 898,884 geometry rows and 887,699 value rows,
with 886,821 common IDs, 878 value-only IDs, 12,063 geometry-only IDs, and 304
initially invalid geometries. In the evaluation-scene bounding extent, 460,006
parcels were spatially relevant; 213 were repaired successfully and none failed
the polygonal validity gate. Of those relevant geometries, 6,519 lacked a
value. A scene is eligible only with positive parcel support and complete value
coverage over that support.

### ECOSTRESS

The accepted P11-A pixel contract is unchanged: finite `ECO_L2T_LSTE.002` LST
in the official 150-1310.7 K range, mandatory QA bits `00`, separate
`cloud=0`, valid water retained, distinct timestamps, and equal weighting of
accepted per-acquisition scene means.

Coverage was frozen before response or model-performance inspection. Among 79
timestamps and 1,600 scenes, positive-support acquisition fractions had median
0.974; a 50% per-acquisition gate left 33-50 acquisitions per scene and at
least three in the least-supported quarter. The final transparent rules are:

1. valid intersection area at least 50% of the 500 m scene per acquisition;
2. at least 12 accepted acquisitions per scene;
3. at least one accepted acquisition in every calendar quarter.

All 1,600 scenes satisfy these gates. Kelvin remains the output unit.

### Future district folds

The frozen but unexecuted contract is exactly 25 leave-one-Seoul-autonomous-
district-out folds by scene center. A center on a boundary uses the lowest
canonical district ID among covering polygons. There is no added buffer; scene
footprints may cross boundaries. Fold membership is target-independent. Empty
target-specific test folds remain structurally recorded but are excluded from
metric aggregation with an explicit reason, and fitting requires nonzero train
and test populations.

## Source contracts and acceptances

| Family | Closed contract | Source inventory SHA-256 | Source acceptance |
|---|---|---|---|
| SGIS | `p11src_484dbd54b6722fed6fcb1187` | `bf9e5dd4859362529cfb7bf53a7f959e8a2fceb01d25b999df39b882f86dde96` | `p11sa_c53b6df5c5065b562c90e3f3` |
| Living population | `p11src_fe6e9b4985da4229c182d1c1` | `80192bd35b7c0fb51fbed8225c01780f925f4b566314164b0b635c934f3dae57` | `p11sa_6f962ac32289683d493bf5f7` |
| Official land value | `p11src_2ae748fc8cbd5bcfc0a63388` | `038c509062175f4e1eb637f166ed11be138d7220c98fba5b9fda56a58d3444ca` | `p11sa_7bff9060233ec05a3b2367e8` |
| ECOSTRESS | `p11src_a54ca1cb6685381047646483` | `269fd12a88f3472731e1384bf43ad831048c4c5f791f68ca3dda1392e6a16b72` | `p11sa_647fce85630b4566d6fe03c0` |

The source inventories bind 10 SGIS files (1,698,681,320 bytes), 369 living-
population files (22,809,895,556 bytes), 43 land-value files (6,890,946,659
bytes), and 665 ECOSTRESS files (194,051,026 bytes).

## Materialized dataset

The isolated four-target/three-edge graph in `_targets_p11_preprocessing.R`
published:

- four source-family Parquet shards;
- `scene_targets.parquet` with 17,600 rows (1,600 scenes x 11 targets);
- target-independent `target_eligibility.parquet`;
- target coverage summary and four source-acceptance manifests;
- `downstream_dataset_acceptance.json`.

The dataset identity is `p11ds_fdb1f34c6daeda259e803e37`; its content digest
is `fdb1f34c6daeda259e803e378cf5325c5e8377edcc76f8dac3e1f82bec421197`.
The physical publication root is
`/mnt/hdd002/dhnyu/fusedata/downstream_data/p11_prepared/p11ds_fdb1f34c6daeda259e803e37`.
The active reference is `config/p11_downstream_dataset.yml`, whose acceptance
file hash is `726fd5e1d9969a01fff797ccdff16bd7d7ae5e090591ea478850d11aa4079a8b`.
Three content-addressed development outputs are retained but explicitly marked
noncanonical there: one predates output-content binding, one exposed an
undeclared idempotent-readback helper, and one predates explicit hash-connection
closure. None is an input to the next phase.

| Target | Eligible | Missing | Median support coverage |
|---|---:|---:|---:|
| Total population | 1,372 | 228 | 0.5414 spatial |
| Households | 1,358 | 242 | 0.5363 spatial |
| Housing units | 1,324 | 276 | 0.4988 spatial |
| Establishments | 1,442 | 158 | 0.6367 spatial |
| Workers | 1,442 | 158 | 0.6367 spatial |
| Weekday daytime | 471 | 1,129 | 0.7918 temporal |
| Weekday nighttime | 291 | 1,309 | 0.7056 temporal |
| Weekend daytime | 486 | 1,114 | 0.8037 temporal |
| Weekend nighttime | 360 | 1,240 | 0.7305 temporal |
| Official land value | 1,244 | 356 | 1.0000 valued-parcel support |
| ECOSTRESS LST | 1,600 | 0 | 0.9140 mean accepted-acquisition area |

Living-population medians include ineligible scenes and therefore sit below the
90% gate; accepted rows individually satisfy the fixed gate. SGIS values are
not rescaled for missing support, so the coverage columns must accompany every
future analysis.

ECOSTRESS produced 126,400 scene-acquisition records. 77,871 had positive valid
pixel support and 65,696 passed the 50% acquisition gate. The source audit found
16,404,606 finite LST pixels and 13,753,718 after mandatory QA and separate
clear-cloud filtering. Accepted acquisition counts are 33-50 per scene.

## Validation and determinism

- Phase-1 Draft 2020-12/source identity tests: 8 passed.
- Focused R preprocessing tests: 13 passed, including calendar classification,
  250 m ID normalization, SGIS conservation, cardinality, and immutable
  publication collision behavior.
- P10/P11/resolver Python regression: 109 passed.
- P11, main, and P10 `tar_validate()`: passed without unintended execution.
- R parse, JSON parse, Draft 2020-12 schema checks, and `git diff --check`: passed.
- Full source hash readback: all four inventory digests matched.
- Dataset validator: 11 targets, 1,600 unique scenes, 17,600 rows, all accepted
  artifact byte sizes/hashes and source/dataset identities passed.
- Independent full rerun: create-or-validate returned the same dataset ID,
  content digest, and exact artifact bytes without rewriting the destination.
- Dependency network: four targets, three edges, one component, written to
  `artifacts/targets-network-p11/targets-network.html`.

## Leakage and prohibited work

| Activity | Count |
|---|---:|
| Downstream source preprocessing/materialization | 1 accepted deterministic run |
| New embedding inference | 0 |
| Encoder fine-tuning | 0 |
| Fold generation | 0 |
| Ridge fitting | 0 |
| OOF prediction | 0 |
| P11 model evaluation | 0 |
| P9/P10 rerun | 0 |
| Dissertation mutation | 0 |
| Response-informed threshold tuning | 0 |

Eligibility is derived once per target without model inputs. All eight later
models must join the same accepted scene IDs. No P9/P10 embedding or checkpoint
artifact was mutated.

## Exact next work unit

`P11_C_SPATIAL_FOLDS_AND_LEAKAGE_GATES`

That unit may materialize the frozen 25-district folds and leakage gates. It
must not fit ridge models until those gates pass.

## Prompt summary

Close Flickr, SGIS omission, ECOSTRESS coverage, living-population calendar and
completeness, land-value repair/unmatched, and district-fold decisions; then,
only after closure, immediately materialize deterministic scene targets for the
fixed P10 scene universe without new embeddings, folds, or regression.
