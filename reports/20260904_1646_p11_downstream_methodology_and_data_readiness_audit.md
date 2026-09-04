# P11 Downstream Methodology and Data Readiness Audit

## Verdict

`P11_DOWNSTREAM_METHODOLOGY_AND_DATA_READINESS_BLOCKED_PUSHED`

The available data are substantial and P10 supplies the required frozen
embeddings, but P11 cannot be implemented without choosing scientific rules not
fixed by the current dissertation or an accepted source contract. No P11
scientific work was executed.

## Scope and repository state

- Audit time: 2026-09-04 (Asia/Seoul)
- Fuse input: `24efc1b892560c20d7f2a43bc3379b5868e2d177`, branch `reduced`, clean and origin `0/0`
- Dissertation input: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, branch `reduced`, clean and origin `0/0`
- Scientific authority: the current reduced dissertation, especially
  `04-downstream-representation-utility.typ` and
  `results-06-downstream-datasets.typ`
- P10 input: accepted attempt `p10exec_7fee193dac532190c79e02c6`, acceptance
  `p10acc_6e5071beee7616750dec7907`, and single consumption
  `p10cons_7d0eba832b70d545fc5d3eb4`
- Prompt scope: read-only methodology/data audit and an implementation-ready
  plan; no preprocessing, inference, fold generation, fitting, or evaluation

## Authoritative downstream-task inventory

The dissertation body defines eleven scene-level responses. The parenthesized
Flickr row in the downstream dataset table is a separate unresolved scope item.

| Family | Responses | Source/version | Native support | Scene mapping | Current status |
|---|---|---|---|---|---|
| SGIS grid statistics | total population, households, housing units, establishments, workers | 2024 SGIS | 100 m grid, EPSG:5179 | overlap-weighted sum | Raw source available; codebook and missing semantics unresolved |
| Seoul living population | weekday daytime, weekday nighttime, weekend daytime, weekend nighttime means | 2025 daily/hourly grid files | 250 m grid, EPSG:5179 | first sum duplicate administrative rows by grid/date/hour, then overlap-weighted sum and temporal mean | Raw source available; holiday/time/missing coverage contract unresolved |
| Official land value | parcel land value | 2026 parcel source | parcel polygons, Seoul geometry EPSG:5186 | overlap-area-weighted mean | Raw source available; invalid/unmatched parcel policy unresolved |
| ECOSTRESS LST | land-surface temperature | 2025 ECO_L2T_LSTE.002 | 70 m UTM raster acquisitions | quality-masked acquisition-level area-weighted mean, then period mean | Raw source available; QA/cloud/unit/temporal coverage contract unresolved |
| Flickr geotagged photos | point activity, if in scope | table says 2020-2025 | point | unspecified | Source absent and body/accepted P0 contract omit it; unresolved methodology |

No P11 preprocessing implementation, accepted prepared dataset, spatial folds,
probe results, or P11 acceptance exists. The active graph exposes only the P0
`downstream_methodology_contract`; the P11 entries in the blueprint are
conceptual.

## Actual source-data readiness

The inspected root was
`/mnt/hdd002/dhnyu/fusedata/downstream_data`. It contains 1,086 files. A sorted
read-only SHA-256 inventory was computed; the inventory-list digest was
`977f61896d63fe9e4fe436e899af5880cb2d94bcf8d13dda51c6cfe39750f0ab`.

| Source | Inventory and observed properties | Readiness |
|---|---|---|
| SGIS | 9 files, 1.582 GiB; five headerless CP949 CSVs plus nationwide 100 m polygon shapefile; 10,246,019 polygons, EPSG:5179. CSVs have unique key/code rows and no negative values. | `SOURCE_INCOMPLETE`: no local authoritative codebook/header/provenance manifest; omitted-cell semantics are not fixed |
| Living population | 369 files, 21.243 GiB; 365 daily CP949 CSVs cover every date in 2025; stable 33-column header; 250 m grid has 1,693,148 polygons, EPSG:5179. Samples contain expected duplicate grid/hour rows across administrative subdivisions and suppressed/non-numeric values. | `RAW_SOURCE_AVAILABLE`; temporal aggregation is stated, but calendar, timezone, suppression denominator, and minimum coverage are unresolved |
| Official land value | 43 files, 6.418 GiB; 2026 Seoul/Incheon/Gyeonggi geometry/value sources. Seoul has 898,884 polygons and 887,699 value rows; 886,821 IDs intersect, 878 values lack geometry, 12,063 geometries lack values, and 304 geometries are invalid. | `RAW_SOURCE_AVAILABLE`; join, invalid-geometry, and incomplete-coverage policies are unresolved |
| ECOSTRESS | 665 files, 0.181 GiB; AppEEARS request completed for 2025 ECO_L2T_LSTE.002; 79 LST acquisitions with exact QC/cloud counterparts, UTM zone 52N, 70 m Float32 Kelvin grids. LST scan found 16,404,606 finite of 29,535,651 pixels and raw range 156.12-1244.28 K. | `RAW_SOURCE_AVAILABLE`; accepted QA/cloud bit mask, outlier/unit policy, acquisition weighting, day/night policy, and coverage gates are unresolved |
| Flickr | No corresponding source directory or metadata found. | `SOURCE_INCOMPLETE` if the table row is authoritative; otherwise must be explicitly removed from P11 scope |

These are read-only observations, not source acceptance. No file was repaired,
converted, normalized, or copied.

## Preprocessing status

| Component | Status |
|---|---|
| Source inventory and schema inspection | Audited read-only, not accepted |
| Source contracts | High-level P0 contract exists; dataset-specific executable contracts absent |
| Deterministic spatial preprocessing | Specified in part, not implemented |
| Scene-target alignment | Not materialized |
| Coverage/QC acceptance | Not implemented; thresholds incomplete |
| Spatial folds | Not materialized |
| Frozen embedding binding | P10 source artifacts exist; P11 binding not implemented |
| Ridge/OOF evaluation | Not implemented and not executed |

## Scene-to-target construction contract

### Fixed

- Extensive grid variables use overlap-weighted sums.
- Intensive parcel/raster variables use area-weighted means.
- Living-population duplicate administrative subdivisions are summed by
  grid/date/hour before scene aggregation.
- Weekday daytime is 09:00-18:59; weekday nighttime is 19:00-08:59; weekend
  covers Saturday, Sunday, and public holidays.
- ECOSTRESS invalid/cloud pixels are excluded and acquisition-level values are
  averaged over the study period.
- Only evaluation scenes satisfying target-specific spatial/temporal coverage
  are eligible; every model must use the same eligible scenes for a target.

### Derivable from existing contracts

- Reproject immutable sources to the accepted scene CRS and intersect the
  accepted 500 m scene polygons using deterministic ordering.
- Bind every response to the accepted scene ID, source ID, source hash, and
  mapping-contract hash.
- Enforce exactly one finite response per eligible scene and preserve missing as
  missing until the accepted dataset-specific rule applies.

### Unspecified scientific decisions

1. Whether Flickr is a twelfth downstream response or a stale table entry.
2. Authoritative SGIS field-code mapping and omitted/suppressed versus observed-zero semantics.
3. Exact transformation for each response described only as transformed “where required.”
4. Operational definition/tolerance for “full geographic scene coverage.”
5. Minimum spatial and temporal coverage by target.
6. Living-population public-holiday calendar/version, timezone, and valid-hour denominator.
7. Official-land-value invalid geometry repair/drop and unmatched parcel handling.
8. ECOSTRESS accepted QC/cloud bits, physically invalid-value policy, day/night policy, minimum acquisitions, weighting, and reported unit.

## Frozen predictor population and lineage

The intended predictor population is the 1,600 original P9 evaluation scenes,
not training or validation scenes and not a broader inferred population. The
accepted scene index `rsi_80031f1493c75163f91b7c71` contains 2,421 training,
400 validation, and 1,600 evaluation scenes.

P10 already contains, for each of the fixed eight models, a combined embedding
artifact ordered as 3,200 augmented queries followed by 1,600 original gallery
scenes. Every accepted embedding dimension is 128. P11 should bind the immutable
P10 acceptance and its per-model gallery slice, scene order, and hashes. New
embedding inference is neither required nor authorized. A P11 binding manifest
does not yet exist.

## Spatial-fold contract audit

Fixed by the dissertation:

- 25 leave-one-Seoul-autonomous-district-out folds.
- District membership is assigned by scene center.
- The same target-specific eligible scene set and fold identities are shared
  across all eight model comparisons.
- Random K-fold substitution is prohibited.

The 2025 Q2 administrative source contains exactly 25 unique Seoul districts in
EPSG:5179. Still unresolved are deterministic boundary-tie behavior and whether
scene footprints crossing district boundaries satisfy the blueprint's stronger
“spatially disjoint” wording or require a buffer/exclusion rule. Minimum
train/test samples per fold and handling of targets missing from a district are
also unspecified. No folds were generated.

Recommended methodology-compatible closure: retain center-based district
assignment as written, explicitly define point-on-boundary tie resolution,
decide whether footprint overlap is acceptable or buffered, and freeze
target-specific minimum fold coverage before inspecting responses.

## Ridge-probe contract audit

Fixed:

- Linear ridge regression with intercept.
- Penalty `lambda = 1`; there is no alpha grid or inner-CV selection.
- One fit per outer training fold.
- Predictor standardization is fit on the training fold only.
- Any accepted target transform is fit on the training fold only and inverted
  before reporting.
- Exactly one out-of-fold prediction per eligible scene.
- Pooled OOF R2, RMSE, and MAE are the final metric set.

Unresolved:

- The per-response target transformation map.
- Constant-target/zero-variance and numerical edge conventions.
- Whether coefficients and fold-local scaling parameters must be retained in
  addition to the required predictions and metrics.
- Missing-response and minimum-fold-sample thresholds.

No ridge model was fit.

## Leakage matrix

| Leakage path | Required future gate |
|---|---|
| Downstream labels enter P9/P10 representation learning | Prove downstream source identities are not ancestors of any accepted checkpoint/embedding |
| P10 results influence P11 contract choices | Freeze source, transform, coverage, fold, and ridge contracts before inspecting P11 responses/results |
| Model-specific eligible populations | Build target eligibility independently of model and require identical scene/fold IDs for all eight models |
| Same scene in train and test | Unique scene IDs and exactly one district fold assignment |
| Spatially adjacent/overlapping footprints cross folds | Enforce the pending boundary/buffer decision and audit geometry |
| Test statistics enter standardization/transformation | Persist fold-local fit parameters and reject global fits |
| Test outcome selects ridge penalty | Bind fixed `lambda = 1`; reject selection fields or test-driven tuning |
| Duplicate source entities/scenes | Resolve duplicates before fold assignment under an accepted source-specific rule |
| P10 held-out ranking drives P11 tuning | Bind closed model set and fixed P11 contract; P10 metrics are descriptive inputs only |
| Mutable/manual embeddings | Require P10 acceptance, canonical P9 resolver chain, artifact hashes, gallery slice, and exact scene ordering |
| Temporal/source mismatch | Bind stated source year/version and reject unmatched periods |

## Coverage and validity gates

Every future dataset acceptance must verify source inventory/hash and provenance,
schema/code/unit/CRS/date contract, deterministic duplicate handling, finite
responses, unique scene IDs, one response per scene, spatial coverage, fold
coverage, non-degenerate target variance, and exactly-once OOF coverage. The
maximum population is the accepted 1,600 evaluation scenes; usable counts are
target-specific and cannot be known before authorized preprocessing.

The minimum valid scene count, missing-response fraction, spatial/temporal
coverage, samples per fold, and variance thresholds are scientific decisions not
currently fixed. This audit does not invent numeric thresholds.

## Proposed P11 DAG

The smallest useful graph is:

```text
source inventory -> source acceptance -> scene-target plan -> mapped target shards
                                                        -> downstream dataset acceptance
P10 acceptance + P9 resolver chains --------------------> frozen embedding binding
dataset acceptance + 25-district source ----------------> spatial folds
dataset + folds + embeddings ---------------------------> leakage/coverage gates
accepted gates ------------------------------------------> fixed ridge probes
fixed ridge probes --------------------------------------> OOF predictions/metrics
all immutable evidence ----------------------------------> P11 acceptance
```

This needs no reservation, attempt, recovery, mutable registry, new inference
controller, or alternate checkpoint resolver.

## Phased implementation plan

### P11-A: methodology-decision closure and source acceptance

- Inputs: dissertation decision record, the audited raw sources, codebooks and
  calendars, P0 authority.
- Outputs: versioned source-family contracts, canonical ordered inventories,
  source acceptances, and resolved target inventory.
- Gates: every unresolved scientific decision above is explicit;
  `UNSPECIFIED_SCIENTIFIC_DECISION = 0`.
- Prohibited: preprocessing, embedding inference, fold construction, fitting.

### P11-B: deterministic preprocessing and scene-target alignment

- Inputs: P11-A acceptances and accepted scene index/polygons.
- Outputs: content-addressed source-family shards and one response per eligible
  scene per target with coverage evidence.
- Gates: schema/hash/CRS/unit/date, aggregation equivalence, duplicate/missing,
  spatial/temporal coverage, deterministic rerun.
- Prohibited: model features and regression.

### P11-C: spatial folds and leakage/coverage gates

- Inputs: accepted aligned targets and immutable 25-district geometry.
- Outputs: deterministic target-specific eligible populations, shared 25-fold
  assignments, leakage and coverage decisions.
- Gates: unique membership, no disallowed overlap, sufficient accepted coverage,
  fold determinism.
- Prohibited: random folds and response-informed contract changes.

### P11-D: frozen embedding binding

- Inputs: P10 acceptance, eight canonical P9 acceptances/resolver results, P10
  gallery embeddings, P11-C scene IDs.
- Outputs: immutable per-model gallery-slice binding manifests.
- Gates: hash, dimension, ordering, exact scene identity and no manual/latest/v1
  fallback.
- Prohibited: new inference or embedding mutation.

### P11-E: spatial ridge probes and OOF predictions

- Inputs: accepted targets/folds and frozen embedding bindings.
- Outputs: fold-local scaling/transform evidence, fixed-`lambda = 1` fits, OOF
  predictions, and pooled R2/RMSE/MAE.
- Gates: train-only fitting, identical populations across models, exactly-once
  OOF predictions, deterministic aggregate recomputation.
- Prohibited: alpha tuning, fine-tuning, P10-informed selection.

### P11-F: final comparison and acceptance

- Inputs: all source, dataset, fold, embedding, leakage, coverage, prediction,
  and metric evidence.
- Outputs: immutable P11 acceptance and final downstream comparison artifacts.
- Gates: complete lineage and independent aggregate/readback validation.
- Prohibited: retrospective target/model/metric changes.

## Validation results

- Focused Python downstream/P10 tests: 73 passed.
- P0 methodology-authority R tests: 38 passed.
- P10 target-contract R tests: 4 passed.
- Study-pipeline R tests: 49 passed and 1 failed.
  The failure is the documented stale static target-generation list: the current
  manifest contains retired/v2 entries not represented in the old expected list.
  It does not execute targets or affect this audit conclusion.
- Main `targets::tar_validate()`: PASS, no target execution.
- P10 `targets::tar_validate()`: PASS using an empty temporary store, no target execution.
- Source inventory/schema/spatial scans: PASS as read-only audit; scientific
  source acceptance remains blocked by the decisions above.
- Post-audit verification: all 1,086 source-file hashes matched the pre-audit
  inventory; P10 acceptance SHA-256 remained
  `f43a7206be6814c35e517017b438a977561c5113be855bff8d884c3d4a52e8c0`.
- Python AST parse: 132 files; R parse: 98 files; JSON parse: 133 files;
  Draft 2020-12 schema checks: 130 schemas; YAML parse: 58 files. All passed.
- `git diff --check`: PASS.
- Dissertation mutations: 0.

## Prohibited-work accounting

| Activity | Count |
|---|---:|
| Downstream preprocessing | 0 |
| Scene-target materialization | 0 |
| New embedding inference | 0 |
| Ridge fitting | 0 |
| Fold generation | 0 |
| P11 evaluation | 0 |
| P9/P10 rerun | 0 |
| Dissertation mutation | 0 |

## Warnings and unresolved risks

The primary blocker is methodology incompleteness, not compute or basic source
availability. In particular, the table/body Flickr conflict and the target-
specific transformation, quality, coverage, and spatial-boundary rules can
change the eligible population and reported scientific results. They must be
resolved before implementation. The 304 invalid Seoul parcel geometries and
ECOSTRESS raw outliers make silent default handling especially unsafe.

## Exact next work unit

`P11-A: methodology-decision closure and immutable downstream source-contract acceptance (no preprocessing).`

## Prompt summary

Audit the dissertation, blueprint, P10 lineage, P11 plans, and actual downstream
sources; determine whether preprocessing, frozen predictors, spatial folds, and
fixed ridge probes can be implemented without inventing methodology; document a
phased P11 plan; perform no P11 scientific execution.
