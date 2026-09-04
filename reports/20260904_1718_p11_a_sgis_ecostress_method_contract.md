# P11-A SGIS and ECOSTRESS Method Contract Audit

## Verdict

`P11_A_SGIS_ECOSTRESS_METHOD_CONTRACT_BLOCKED_PUSHED`

This bounded audit closes the SGIS five-code mapping and privacy-preserving
released-value treatment, and closes the ECOSTRESS product, pixel QA/cloud,
water, unit, timestamp, and temporal weighting rules. It does not close two
source/scientific gates: SGIS omitted rows have two officially documented but
indistinguishable meanings, and the dissertation does not specify ECOSTRESS
spatial/temporal coverage thresholds. Both source contracts are therefore
immutable `PARTIALLY_CLOSED` records with `preprocessing_authorized = false`.
Overall P11 readiness remains blocked by these and the unrelated prior blockers.

## Scope and starting state

- Audit date: 2026-09-04 (Asia/Seoul)
- Fuse input: `51abd1040c1f144bb27e7ac59ebec34341d1384f`, branch
  `reduced`, clean, origin synchronization `0/0`
- Dissertation: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, branch
  `reduced`, clean, origin synchronization `0/0`
- Previous audit:
  `reports/20260904_1646_p11_downstream_methodology_and_data_readiness_audit.md`
- Scientific work: none; only workbook/document/raster metadata and source-byte
  inspection, contract publication in Git, and tests

## SGIS codebook provenance

The exact prompt path `/mnt/data/3. 제공용 코드(statistics_code).xls` did not
exist. The supplied downstream package contained the same named workbook at:

`/mnt/hdd002/dhnyu/fusedata/downstream_data/grid_statistics/3. 제공용 코드(statistics_code).xls`

Its SHA-256 is
`e72eac92cce04bc01f3702ed37b5e3b12af2cee244e9af19c9595891392983e7`.
It is an Excel 97-2003 OLE workbook with CP949 metadata and two worksheets,
`집계구·행정동` and `격자`. The source-directory copy is the audited authority
for this contract. A separately discovered older workbook at
`/mnt/hdd001/Korea/census/meta/statistics_code.xls` has SHA-256
`44ef8f100b403ab11601c71e65f095cffb586a382305f2a2e53f58d1a2eb62b8`
and different dimensions/content; it is not substituted.

The official SGIS/SDC source listing states that a codebook and boundary files
accompany requested SGIS small-area statistics. The revised official small-area
statistics manual retrieved on 2026-09-04 has SHA-256
`144afc96aa9b68a1fad220346e614f8e045d78deb683b3e97abc0f0f166abb53`.

## Exact SGIS mapping

All five intended codes occur once in the workbook's `격자` worksheet and agree
with every raw 2024 CSV row. The workbook provides Korean labels, not English
labels or a separate unit column; English labels below are literal reporting
translations, and “count” follows the `총...수` statistic definition.

| Target | Worksheet hierarchy | Code | Korean label | Reporting label/unit | Raw rows |
|---|---|---|---|---|---:|
| Total population | 총괄 / 총인구 | `to_in_001` | 총인구 | total population / released persons count | 200,808 |
| Households | 총괄 / 총가구 | `to_ga_001` | 총가구수 | total households / released household count | 191,799 |
| Housing units | 총괄 / 총주택 | `to_ho_001` | 총주택(거처)수 | total housing units / released housing-unit count | 168,189 |
| Establishments | 총괄 / 총사업체 | `to_fa_010` | 총사업체수 | total establishments / released establishment count | 192,718 |
| Workers | 총괄 / 총종사자 | `to_em_020` | 총종사자수 | total workers / released persons count | 192,718 |

There are no duplicate `(year, grid_id, statistic_code)` rows and every audited
row has year `2024`. The population file also contains the expected male/female
codes, but only `to_in_001` is a P11 target. No alternative total-code candidate
was found.

## SGIS privacy, zero, and omission semantics

The official manual establishes:

- SGIS portal grid statistics apply BSCA privacy protection/noise; unprotected
  true values require the controlled SDC environment.
- Grid hierarchy and component totals may consequently differ.
- Population-family small values and establishment-family small values can be
  replaced under the privacy method rather than exposed as latent counts.
- A missing grid-statistic row can mean either no population/establishment in
  the grid or no value for the requested statistic.

The supplied distributions exhibit the documented protected-release signature
(large masses at released values such as population-family 0/5 and
establishment-family 0/3), and explicit zeros occur in all five files. The
frozen interpretation is therefore:

1. Use released values exactly as supplied.
2. Define the response as the official privacy-protected released statistic,
   never a reconstructed latent true count.
3. Preserve an explicit released `0` as `0`; it does not assert a latent true
   zero.
4. Preserve all other small released values; do not denoise, round, suppress,
   reverse BSCA, or treat them as missing.
5. Never turn an absent CSV row into zero.

Item 5 is a safe ingest rule but does not solve the source semantics. The source
has no per-row flag distinguishing structural absence from unavailable statistic.
That ambiguity can alter complete-scene coverage and sums, so the contract is
`BLOCKED_SOURCE_SEMANTICS` rather than silently treating absence as structural
zero.

## Frozen SGIS scene-level contract

The closed, non-executable portion is:

- Source year 2024; native 100 m grid; EPSG:5179; CP949 four-column CSV.
- The five variables are extensive.
- Future 500 m scene value is
  `sum(released_value * intersection_area / source_grid_area)` in the accepted
  equal-area scene CRS.
- Process source grids in deterministic `grid_id` order.
- Reject duplicate `(year, grid_id, code)` evidence.
- Emit at most one response per eligible scene and target.
- Keep absent rows missing pending explicit closure; no zero fill.

No scene response was materialized. Because the omission ambiguity remains,
this artifact does not authorize preprocessing.

## ECOSTRESS product and layer audit

The AppEEARS request is ID `87afc526-83d1-483a-9c70-f89c06b7416c`,
completed with AppEEARS 3.125 for 2025-01-01 through 2025-12-31. It requested
native-projection GeoTIFF layers from `ECO_L2T_LSTE.002`:

| Layer | Files | Role |
|---|---:|---|
| LST | 79 | Scaled land-surface temperature |
| QC | 112 | LSTE quality bit field |
| cloud | 112 | Separate clear/cloud mask |
| LST_err | 81 | Temperature uncertainty |
| EmisWB | 79 | Wideband emissivity |
| height | 81 | Height ancillary |
| water | 112 | Separate land/water mask |

All 79 LST rasters have exact timestamp-matched QC, cloud, and water rasters.
The native tiled output is UTM zone 52N (`EPSG:32652`) at 70 m. There are 79
distinct LST timestamps, including 15 extra same-day observations across 13
days. Different timestamps remain separate acquisitions. The 112 support-layer
records versus 79 LST records are consistent with AppEEARS omitting outputs that
contain only fill for a requested layer. NaN/fill prevalence is documented as
normal for tiled ECOSTRESS and is not itself source corruption.

The AppEEARS metadata XML is not well-formed: line 277 contains an unescaped
ampersand in the product citation. It was not repaired. Its hash remains bound,
and the relevant metadata were cross-checked against the request JSON, README,
GeoTIFF metadata, and official guide instead of accepting a tolerant XML parse.

The package README and Collection 2 guide explicitly state that QC no longer
contains cloud status. The separate cloud mask must be used. AppEEARS supplied
decoded QC and cloud lookup tables; `cloud=0` is Clear and `cloud=1` is Cloudy.

## ECOSTRESS accepted-pixel rule

The rule is fixed before preprocessing:

1. Require a finite LST value and reject GeoTIFF NaN/nodata without imputation.
2. Require the official product scaled-valid interval: raw 7500-65535 with
   scale 0.02, equivalent to 150-1310.7 K. Reject values outside it.
3. Require QC mandatory bits 1-0 equal `00`, “Pixel produced by TES.” The
   official ECOSTRESS FAQ identifies this as the best-quality filter.
4. Independently require decoded cloud value `0` (Clear); reject `1` (Cloudy).
5. Retain both decoded water values `0` and `1` if the preceding rules pass.
   Water is a surface classification, not an invalidity flag, and the
   dissertation does not define a land-only response.
6. Retain all remaining QC fields as diagnostics. Do not tune thresholds using
   iterations, opacity, MMD, emissivity accuracy, LST accuracy, or LST_err after
   viewing downstream results.

Read-only source auditing found 16,404,606 finite LST pixels with range
156.12-1244.28 K. Applying mandatory QA `00` and separate clear-cloud filtering
leaves 13,753,718 pixels with range 156.12-340.5 K; mandatory QA filtering
removes the observed extreme high values. These counts are source diagnostics,
not materialized downstream data.

## ECOSTRESS units and aggregation

The product guide defines LST in Kelvin with source scale factor 0.02 and offset
0. AppEEARS has already applied scaling: the delivered LST GeoTIFFs are Float32,
declare `units=Kelvin`, `scale_factor=1`, and `add_offset=0`. The downstream
response is frozen in Kelvin with no later conversion.

The future procedure is:

1. Apply the fixed pixel rule independently to every timestamp.
2. Compute one overlap-area-weighted scene mean per timestamp from accepted
   pixels and record accepted intersection area divided by scene area.
3. Never merge different timestamps, including acquisitions on the same day.
4. Include accepted daytime and nighttime acquisitions. UTC and derived
   Asia/Seoul local time are provenance only, not selection criteria.
5. Compute the annual response as the arithmetic mean of accepted
   per-acquisition scene means. Each acquisition has equal weight; coverage does
   not reweight its temperature after it passes the coverage gate.

The equal-acquisition rule follows the dissertation's instruction to calculate
each valid observation and subsequently average those scene observations over
the reference period. It is not a convenience-driven choice.

## Remaining ECOSTRESS coverage decisions

The following remain `BLOCKED_SCIENTIFIC_DECISION`:

- Minimum accepted pixel/intersection-area fraction for one scene-acquisition.
- Minimum number of accepted acquisitions per scene.
- Final temporal coverage gate, including required seasonal/monthly balance or
  maximum temporal gaps.

The dissertation requires “sufficient” spatial/temporal coverage and complete
geographic scene coverage but gives no numerical operational definition. Product
documentation does not prescribe one for this downstream task. No threshold was
invented.

## P11 blocker matrix after P11-A

| Decision | Classification | Result |
|---|---|---|
| Flickr scope | `BLOCKED_SCIENTIFIC_DECISION` | Unchanged; body has 11 targets while table also lists Flickr |
| SGIS five-code mapping | `CLOSED` | Exact worksheet/code/raw consistency established |
| SGIS released-value/privacy semantics | `CLOSED` | Use official privacy-protected values as released; no reconstruction |
| SGIS explicit zero | `CLOSED` | Retain released zero as zero |
| SGIS omitted row | `BLOCKED_SOURCE_SEMANTICS` | Officially means either structural absence or unavailable statistic; no row flag |
| Living-population calendar/completeness | `BLOCKED_SCIENTIFIC_DECISION` | Not in this bounded unit |
| Land-value invalid/unmatched handling | `BLOCKED_SCIENTIFIC_DECISION` | Not in this bounded unit |
| ECOSTRESS product/layer identity | `CLOSED` | Product, period, projection, resolution, layers, timestamp identity fixed |
| ECOSTRESS QC/cloud/water | `CLOSED` | Mandatory `00`, separate clear `0`, retain valid water |
| ECOSTRESS fill/range/unit | `CLOSED` | Finite official range; delivered Kelvin retained |
| ECOSTRESS acquisition aggregation | `CLOSED` | All times, distinct timestamps, equal accepted-acquisition mean |
| ECOSTRESS spatial/temporal coverage | `BLOCKED_SCIENTIFIC_DECISION` | Three numerical gates remain unspecified |
| District boundary/fold minimum coverage | `BLOCKED_SCIENTIFIC_DECISION` | Not in this bounded unit |

## Source-contract artifacts

| Source | Contract | Content SHA-256 | Status | Preprocessing authorized |
|---|---|---|---|---|
| SGIS | `p11src_9e57aab4897734490f26037a` | `9e57aab4897734490f26037ad360ef4f049a02ebf62f8a9666e3a7b413028e94` | `PARTIALLY_CLOSED` | false |
| ECOSTRESS | `p11src_683e32d59c65b8094c308d19` | `683e32d59c65b8094c308d19c9e0305e61489dc5764e5070f54e932bacda4ad8` | `PARTIALLY_CLOSED` | false |

Both identities are the first 24 hexadecimal characters of the existing
canonical JSON SHA-256 over the artifact without `contract_id` and
`content_sha256`. The SGIS inventory binds 10 files, 1,698,681,320 bytes, digest
`bf9e5dd4859362529cfb7bf53a7f959e8a2fceb01d25b999df39b882f86dde96`.
The ECOSTRESS inventory binds 665 files, 194,051,026 bytes, digest
`269fd12a88f3472731e1384bf43ad831048c4c5f791f68ca3dda1392e6a16b72`.

## Validation

- Source-contract focused Python tests: 5 passed, 0 failed. The schema rejects
  any attempt to set `preprocessing_authorized = true`.
- Combined source-contract, downstream resolver, and P10 regression: 78 passed,
  0 failed.
- SGIS workbook: both worksheets parsed; five mappings were unique and all raw
  codes/year/cardinalities agreed (16 assertions).
- ECOSTRESS README/request/granule list/lookups parsed; metadata XML correctly
  failed strict parsing at its upstream unescaped ampersand and was cross-checked
  without mutation; 79/79 LST science acquisitions had timestamp-matched
  QC/cloud/water inputs (20 assertions plus the expected strict XML rejection).
- Read-only pixel audit: the fixed QA `00` plus clear-cloud mask yielded
  13,753,718 accepted pixels in 156.12-340.5 K.
- Source inventory/hash readback: SGIS 10/10 files retained digest
  `bf9e5dd4859362529cfb7bf53a7f959e8a2fceb01d25b999df39b882f86dde96`;
  ECOSTRESS 665/665 files retained digest
  `269fd12a88f3472731e1384bf43ad831048c4c5f791f68ca3dda1392e6a16b72`.
- P0 methodology-authority R tests: 38 passed, 0 failed. P10 target-contract R
  tests: 4 passed, 0 failed.
- Study-pipeline R tests: 49 passed, 1 failed on the documented stale static
  target-generation list. The assertion omits current retired/v2 targets and is
  unrelated to this source-contract-only change; it was not weakened.
- Main and P10 `targets::tar_validate()` passed against empty temporary stores;
  no target executed.
- Python AST: 132 files; R parse: 98 files; JSON parse: 136 files; Draft 2020-12
  schema checks: 131 schemas; YAML parse: 59 files. All passed.
- Markdown local-link check and `git diff --check`: passed.

## Prohibited-work accounting

| Activity | Count |
|---|---:|
| Downstream preprocessing | 0 |
| Scene-target materialization | 0 |
| Fold generation | 0 |
| Ridge fitting | 0 |
| New embedding inference | 0 |
| P11 evaluation | 0 |
| P9/P10 rerun | 0 |
| Dissertation mutation | 0 |

## Exact next work unit

`P11-A2: close SGIS omitted-row policy and remaining downstream methodology decisions, including ECOSTRESS coverage, Flickr scope, living-population completeness, land-value validity, and district-fold gates (no preprocessing).`

## Prompt summary

Audit the supplied SGIS codebook and privacy/omission semantics and the official
ECOSTRESS Collection 2 QA/cloud/unit/aggregation semantics; publish only
non-authorizing immutable source contracts; update the blocker matrix; execute
no downstream science.
