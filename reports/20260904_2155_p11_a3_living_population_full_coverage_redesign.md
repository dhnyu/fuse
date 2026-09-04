# P11-A3 Living-Population Full-Coverage Redesign Audit

## Verdict

`P11_A3_LIVING_POPULATION_FULL_COVERAGE_REDESIGN_BLOCKED_PUSHED`

The requested partial-support redesign is technically feasible for 1,565--1,570
of the 1,600 evaluation scenes, but it directly contradicts the authoritative
reduced dissertation requirement that geographic coverage span the complete
500 m scene. The fail-closed instruction therefore applies. No new methodology
artifact, source contract, living-population shard, downstream dataset, or
active pointer was created.

## Scope and immutable inputs

- Audit time: 2026-09-04 21:55 KST.
- Fuse input: `ca14ccf31e5e40f710e908b47c5579f4ea000c14`, branch `reduced`, clean and synchronized.
- Dissertation: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, unchanged.
- Existing methodology: `p11meth_c671fa4c1ebdf9ec3e79bd64`.
- Existing dataset: `p11ds_fdb1f34c6daeda259e803e37`.
- Living source contract: `p11src_fe6e9b4985da4229c182d1c1`.
- Living source inventory: 369 files, 22,809,895,556 bytes,
  `80192bd35b7c0fb51fbed8225c01780f925f4b566314164b0b635c934f3dae57`.
- Scene universe: the same 1,600 P10 evaluation originals, with no new embedding inference.

Pre/post hashes remained:

| Evidence | SHA-256 |
|---|---|
| Existing methodology JSON | `a7a583e81bdecfee097ee8aa57977a220a4d8c4343deb20476883e84e0ed65a5` |
| Existing living contract JSON | `23b2cc890c8966f8a37c6b02d2c25f3f7d5a505cb2b9722d7f35937e5662bab2` |
| Active dataset pointer | `e2c68ba6a40f566ee86b562f9495ef73ed826f473530073d7e190ed278af3249` |
| Existing dataset acceptance | `726fd5e1d9969a01fff797ccdff16bd7d7ae5e090591ea478850d11aa4079a8b` |

## Authoritative contradiction

The dissertation's downstream methodology states that living-population grid
counts are allocated by overlap-weighted summation and that suppressed values
are missing. It separately states:

> Geographic coverage was required to span the complete spatial scene.

The proposed P11-A3 contract instead makes a scene-hour usable when any source
support is present, without extrapolating missing area. That is not merely a
quality-threshold relaxation: it changes the estimand from a complete-scene
hourly population to an observed-support partial total whose support can vary
over time and between scenes. The prompt explicitly requires a stop rather than
silently overriding a dissertation requirement. The dissertation was not
modified.

## Current-result reproduction

The accepted living shard reproduces the requested baseline counts exactly:

| Temporal target | Eligible | Ineligible | Zero implementation-valid hours | Positive but below 90% |
|---|---:|---:|---:|---:|
| Weekday daytime | 471 | 1,129 | 56 | 1,073 |
| Weekday nighttime | 291 | 1,309 | 61 | 1,248 |
| Weekend daytime | 486 | 1,114 | 59 | 1,055 |
| Weekend nighttime | 360 | 1,240 | 64 | 1,176 |

The implemented gate requires an implementation-valid scene-hour count divided
by the fixed expected class hours to be at least 90%.

## Exclusion decomposition

A read-only scan constructed the full 365-day `(scene, grid, date, hour)`
universe before class aggregation. Causes overlap because a scene may contain
both omitted and suppressed support at different hours.

| Target | Existing excluded | Any partial-support hour | Any suppressed/non-numeric component | Any omitted source row | Zero actual usable hour | Positive actual support |
|---|---:|---:|---:|---:|---:|---:|
| Weekday daytime | 1,129 | 1,099 | 1,103 | 938 | 30 | 1,099 |
| Weekday nighttime | 1,309 | 1,274 | 1,282 | 1,097 | 35 | 1,274 |
| Weekend daytime | 1,114 | 1,084 | 1,088 | 885 | 30 | 1,084 |
| Weekend nighttime | 1,240 | 1,207 | 1,214 | 974 | 33 | 1,207 |

- No scene lacks intersecting 250 m geometry support.
- The raw relevant source contains 3,632,300 suppressed/non-numeric component
  rows and 3,522,969 invalid aggregated grid-hour groups.
- Duplicate administrative aggregation is common: 12,919,062 relevant
  grid-hour groups contain more than one administrative row. A group is usable
  only when every component is finite and nonnegative.
- Scenes with zero usable hours contain only omitted and/or invalid source
  observations for the affected class. They cannot be made eligible without
  imputation or treating unavailability as zero.

## Implementation discrepancy

The current immutable implementation joins overlap geometry to only the
grid-hour groups that appear in each daily file. A missing `(grid_id,hour)` is
therefore absent from that hour's `total_source_area` denominator instead of
being represented as unavailable support. The accepted shard remains immutable,
but its 471/291/486/360 counts are not a strict implementation of the stated
complete-scene support rule.

When the full expected grid-hour universe is constructed explicitly, the same
90% complete-support rule yields:

| Target | Existing accepted count | Strict complete-universe count |
|---|---:|---:|
| Weekday daytime | 471 | 327 |
| Weekday nighttime | 291 | 192 |
| Weekend daytime | 486 | 332 |
| Weekend nighttime | 360 | 231 |

This is an additional blocker for promoting either old behavior or a new
partial-support behavior without a new methodology authority.

## Partial-support feasibility

The proposed response was computed for audit only as the overlap-weighted sum
over finite, nonnegative available grid observations, with no zero fill and no
coverage extrapolation. No response values or predictive metrics were inspected
when comparing eligibility thresholds.

| Minimum valid hours | Weekday day | Weekday night | Weekend day | Weekend night |
|---|---:|---:|---:|---:|
| `>=1` | 1,570 | 1,565 | 1,570 | 1,567 |
| `>=24` | 1,568 | 1,564 | 1,570 | 1,563 |
| `>=1%` | 1,568 | 1,564 | 1,570 | 1,563 |
| `>=10%` | 1,563 | 1,558 | 1,563 | 1,558 |
| `>=25%` | 1,558 | 1,557 | 1,560 | 1,556 |
| `>=90%` | 1,540 | 1,526 | 1,548 | 1,540 |

Under `>=1`, zero-valid-hour counts are respectively 30, 35, 30, and 33.
Among scenes with any valid hour, the minimum counts are 8, 9, 41, and 9;
the median equals the full expected 2,440, 3,416, 1,210, and 1,694 hours.
Thus most scenes have extensive temporal observations, while a small set has no
defensible response and a few have very sparse evidence.

Across all usable scene-hours, spatial-support fractions were:

| Target | Min | P1 | P10 | P25 | Median | Max |
|---|---:|---:|---:|---:|---:|---:|
| Weekday daytime | 0.000014 | 0.0452 | 0.3939 | 0.7625 | 1.0000 | 1.0000 |
| Weekday nighttime | 0.000014 | 0.0430 | 0.3601 | 0.7498 | 0.9851 | 1.0000 |
| Weekend daytime | 0.000014 | 0.0435 | 0.3878 | 0.7615 | 1.0000 | 1.0000 |
| Weekend nighttime | 0.000014 | 0.0430 | 0.3601 | 0.7498 | 0.9911 | 1.0000 |

The extremely small minimum support confirms that `>=1 hour` alone does not
guarantee a representative complete-scene estimand; coverage metadata cannot by
itself resolve the dissertation conflict.

## Zero-observation scenes

The union contains 35 scenes. Most lack usable observations in all four
classes; `scn_40fe49314465e5a4605c198d` and
`scn_cf2612dadb6b471937d4ae91` lack only weekday-nighttime observations, while
`scn_70d70167b675d798ca4be94d`, `scn_a2bd61e7b3edb1ac36f87dce`, and
`scn_f5ec4fd8493dc2fb133f2025` lack both nighttime classes.

```text
scn_0ad7c70a544a06571b6a39ef  scn_0c8b48090455456ca5b4efa1
scn_243dc4309f8a0685c43d5a80  scn_24444fb40e9bd54eff2c9319
scn_265c2f38bab1bd99fbc0a98c  scn_40fe49314465e5a4605c198d
scn_412091083105f7a6eacb7b78  scn_58af0da6285e2e9af617c98e
scn_5ac76ba568c94bb86b22f17b  scn_6076d5296a075f55244fce36
scn_6212d798e4d8da093d846279  scn_63070ff5a2bc242d37f190c8
scn_6fb4ffb7ff300a2535f7457b  scn_70d70167b675d798ca4be94d
scn_7ac4008f1582865421c97d54  scn_82f84e20469361c25cac1b2f
scn_83f4cefd60e30d9ee54599db  scn_84769532044f4cf55a964c16
scn_9271bcf3477e3ae7afd5074f  scn_93d07737d07d9864ab2d6b4c
scn_972257a2cacd50038b3671ef  scn_9aa5a544241e78222c511779
scn_9d83d97f647924b32170bb84  scn_a2bd61e7b3edb1ac36f87dce
scn_be67b7c4c4424dc380c822c5  scn_c0106cfff87593fee5f17f09
scn_cf2612dadb6b471937d4ae91  scn_d1b94302f5cad2336ae245cd
scn_d33e3901c98613ebbf9daeee  scn_d3a067c08ee33f1f1d283a99
scn_d9fb95ee8b064a8846798599  scn_dc2caed0aa55dacf4d51758d
scn_de33120e3ed82969042fffec  scn_f3967c8a1588d3515dfae61b
scn_f5ec4fd8493dc2fb133f2025
```

They are concentrated in seven district codes: `11110` (8), `11210` (7),
`11220` (7), `11090` (5), `11120` (5), `11010` (2), and `11100` (1).
This is descriptive source-support evidence only; no folds were generated.

Using less than 25% of expected hours as a descriptive low-coverage marker,
the union is distributed across district codes `11210` (10), `11110` (8),
`11220` (7), `11090` (5), `11120` (5), `11160` (3), `11010` (2), and one
scene each in `11030`, `11070`, `11100`, and `11140`. This marker was not used
as an eligibility decision.

## Publication and supersession

- New methodology decision: not published.
- New living source/preprocessing contract: not published.
- New living prepared shard: not published.
- New dataset acceptance: not published.
- Active dataset pointer: unchanged.
- Existing dataset supersession: none; the existing dataset is retained exactly
  as accepted, but P11-C is blocked from consuming its living targets pending
  methodology resolution.
- Seven non-living targets: not recomputed and not modified.

Because Phase 1 failed, Phase 2 was correctly not entered. Cross-dataset
equivalence is not applicable because no candidate dataset exists.

## Validation

- Existing dataset validation/readback: PASS.
- Baseline living eligible counts: exact 471/291/486/360 reproduction from the
  accepted immutable shard.
- Full 365-day, 1,600-scene source audit: PASS.
- Calendar and expected-hour rules: unchanged from P11-A2.
- Source-only threshold sensitivity: completed without model outputs.
- P10/P11/source-contract Python regression: 81 passed.
- Focused R preprocessing regression: 13 passed.
- P11, main, and P10 `tar_validate()`: passed without target execution.
- Repository JSON/YAML and R parse checks, Markdown local-link check, and
  `git diff --check`: passed.
- Living source inventory full readback: 369 files and 22,809,895,556 bytes;
  digest matched `80192bd...dae57`.
- Audit scene-class table: 6,400 rows; diagnostic SHA-256
  `8e7a89cf2743dc646f444ea46d55a815956182e3237cb363ace4892ac7991c33`.
  It remained temporary and was not committed as a research dataset.

## Prohibited-work accounting

| Activity | Count |
|---|---:|
| New methodology/source contract | 0 |
| Downstream rematerialization | 0 |
| Fold generation | 0 |
| Ridge fitting | 0 |
| OOF prediction | 0 |
| Downstream model metrics inspected | 0 |
| Lambda tuning | 0 |
| Model-specific eligibility | 0 |
| New embedding inference | 0 |
| Encoder fine-tuning | 0 |
| P9/P10 rerun | 0 |
| Non-living methodology change | 0 |
| Dissertation mutation | 0 |

## Required next action

An explicit methodology-authority decision must resolve whether P11 living
population represents a complete-scene total or an observed-support partial
total. If partial support is scientifically approved, a follow-up can publish a
new contract, repair the explicit grid-hour denominator, rematerialize only the
living family, prove seven-target equivalence, and supersede the active dataset
by lineage. Only then is `P11_C_SPATIAL_FOLDS_AND_LEAKAGE_GATES` eligible.

## Prompt summary

Audit and, only if methodology permits, replace the strict living-population
coverage rules with available-support means, retain quality metadata, and
rematerialize a superseding 1,600-by-11 dataset without model-performance input.
