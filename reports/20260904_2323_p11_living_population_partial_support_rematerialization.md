# P11 Living-Population Partial-Support Rematerialization

## Verdict

`P11_LIVING_POPULATION_PARTIAL_SUPPORT_REMATERIALIZATION_PASS_PUSHED`

Execution began from Fuse `reduced@2ef56a7709480ea67c26cf7daf96b83e1cacc181`
and dissertation `reduced@4adbd49b6dacab589d2fa99d88ec5be83aceb287`.
The dissertation repository was read only.

## Authority And Scope

- Dissertation authority: `disauth_60a514578f57b9397ce71ee6`
- Active methodology: `p11meth_42070c9b832c232a6e989d25`
- Living-population source contract: `p11src_ff2f5bb24376968aedfdfecc`
- Source inventory: 369 files, 22,809,895,556 bytes,
  `80192bd35b7c0fb51fbed8225c01780f925f4b566314164b0b635c934f3dae57`
- Historical dataset preserved: `p11ds_fdb1f34c6daeda259e803e37`
- New living shard: `p11lp_a79001b2fc01b928ab67f303`
- New active dataset: `p11ds_39607da2de792ad6b3c9bb30`

The new dataset explicitly supersedes the historical dataset for
`living_population_methodology_authority_revision_to_partial_support`. The old
acceptance remains byte-identical and is neither invalidated nor rewritten.

## Grid-Hour Universe

The implementation constructs every expected
`scene x intersecting 250 m grid x date x hour` row before joining source
observations. A missing source row therefore remains unavailable support in the
denominator. Each `(grid_id, date, hour)` duplicate group is valid only when
all component rows are finite and nonnegative; incomplete groups are never
partially summed or zero-filled.

For each scene-hour, the response is the overlap-weighted extensive sum over
valid available support. It is not divided by observed coverage and does not
extrapolate unavailable area. The materialized diagnostics retain expected,
valid, and unavailable area and grid counts, raw/contributing/duplicate row
counts, suppression reasons, and the resulting support fraction. Controlled
daily validation confirmed exactly 250,000 square metres of expected support
for every 500 m scene-hour.

Temporal classification remains the frozen 2025 `Asia/Seoul` contract,
including accepted temporary holidays. Each target is the arithmetic mean of
all valid scene-hours in its class; eligibility is `valid_scene_hour_count >= 1`.

## Living-Population Coverage

| Target | Eligible | Ineligible | Eligible % | Valid hours min/median/max | Valid-hour fraction min/median/max | Spatial support min/median/max |
|---|---:|---:|---:|---:|---:|---:|
| weekday daytime | 1,570 | 30 | 98.1250 | 0 / 2,440 / 2,440 | 0 / 1 / 1 | 0.000013708 / 1 / 1 |
| weekday nighttime | 1,565 | 35 | 97.8125 | 0 / 3,416 / 3,416 | 0 / 1 / 1 | 0.000013708 / 1 / 1 |
| weekend daytime | 1,570 | 30 | 98.1250 | 0 / 1,210 / 1,210 | 0 / 1 / 1 | 0.000013708 / 1 / 1 |
| weekend nighttime | 1,567 | 33 | 97.9375 | 0 / 1,694 / 1,694 | 0 / 1 / 1 | 0.000013708 / 1 / 1 |

The 35 unique zero-observation scenes are:

`scn_0ad7c70a544a06571b6a39ef`, `scn_0c8b48090455456ca5b4efa1`,
`scn_243dc4309f8a0685c43d5a80`, `scn_24444fb40e9bd54eff2c9319`,
`scn_265c2f38bab1bd99fbc0a98c`, `scn_40fe49314465e5a4605c198d`,
`scn_412091083105f7a6eacb7b78`, `scn_58af0da6285e2e9af617c98e`,
`scn_5ac76ba568c94bb86b22f17b`, `scn_6076d5296a075f55244fce36`,
`scn_6212d798e4d8da093d846279`, `scn_63070ff5a2bc242d37f190c8`,
`scn_6fb4ffb7ff300a2535f7457b`, `scn_70d70167b675d798ca4be94d`,
`scn_7ac4008f1582865421c97d54`, `scn_82f84e20469361c25cac1b2f`,
`scn_83f4cefd60e30d9ee54599db`, `scn_84769532044f4cf55a964c16`,
`scn_9271bcf3477e3ae7afd5074f`, `scn_93d07737d07d9864ab2d6b4c`,
`scn_972257a2cacd50038b3671ef`, `scn_9aa5a544241e78222c511779`,
`scn_9d83d97f647924b32170bb84`, `scn_a2bd61e7b3edb1ac36f87dce`,
`scn_be67b7c4c4424dc380c822c5`, `scn_c0106cfff87593fee5f17f09`,
`scn_cf2612dadb6b471937d4ae91`, `scn_d1b94302f5cad2336ae245cd`,
`scn_d33e3901c98613ebbf9daeee`, `scn_d3a067c08ee33f1f1d283a99`,
`scn_d9fb95ee8b064a8846798599`, `scn_dc2caed0aa55dacf4d51758d`,
`scn_de33120e3ed82969042fffec`, `scn_f3967c8a1588b3515dfae61b`, and
`scn_f5ec4fd8493dc2fb133f2025`.

Zero-observation counts occur only in district IDs 11010, 11090, 11100,
11110, 11120, 11210, and 11220. Low temporal coverage (`<25%`, eligible only)
occurs in district IDs 11010, 11030, 11070, 11090, 11140, 11160, 11210, and
11220. Full target-by-district evidence is returned by the execution audit and
the accepted shard retains scene-level coverage.

## Eleven-Target Dataset

| Target | Eligible | Ineligible | Eligible % | Spatial coverage min/median/max | Temporal coverage min/median/max |
|---|---:|---:|---:|---:|---:|
| total population | 1,372 | 228 | 85.750 | 0 / 0.5414 / 1 | n/a |
| households | 1,358 | 242 | 84.875 | 0 / 0.5363 / 1 | n/a |
| housing units | 1,324 | 276 | 82.750 | 0 / 0.4988 / 1 | n/a |
| establishments | 1,442 | 158 | 90.125 | 0 / 0.6367 / 1 | n/a |
| workers | 1,442 | 158 | 90.125 | 0 / 0.6367 / 1 | n/a |
| weekday daytime | 1,570 | 30 | 98.125 | 0.000014 / 0.9592 / 1 | 0 / 1 / 1 |
| weekday nighttime | 1,565 | 35 | 97.812 | 0.000014 / 0.9485 / 1 | 0 / 1 / 1 |
| weekend daytime | 1,570 | 30 | 98.125 | 0.000014 / 0.9627 / 1 | 0 / 1 / 1 |
| weekend nighttime | 1,567 | 33 | 97.938 | 0.000014 / 0.9533 / 1 | 0 / 1 / 1 |
| official land value | 1,244 | 356 | 77.750 | 0.0066 / 1 / 1 | n/a |
| ECOSTRESS LST | 1,600 | 0 | 100.000 | 0.8386 / 0.9140 / 0.9761 | 0.4177 / 0.5190 / 0.6329 |

The accepted dataset contains exactly 1,600 unique scenes, 11 targets, and
17,600 scene-target rows.

## Seven-Target Equivalence

The five SGIS targets, official land value, and ECOSTRESS LST were reused from
the historical dataset. The three family Parquet files and their three source
acceptances are byte-for-byte identical. Their source-contract identities,
values, eligibility, and coverage metadata therefore remain exact. Only the
four living-population rows and dataset-level lineage changed.

## Determinism And Publication

- Living shard content SHA-256:
  `a79001b2fc01b928ab67f30326e65afd026bfbed3f9310fc7814613e82e3580d`
- Dataset content SHA-256:
  `39607da2de792ad6b3c9bb305e390236e07da97726eae5ebb2d77e7e6bb1daed`
- Dataset acceptance SHA-256:
  `ff246a1134ebd3f6e63b826eab786053718bebb5c5e33baba58b85db246ee51f`

Two complete runs returned identical IDs, hashes, coverage, zero-scene, and
district evidence. The second run returned `shard_created = false`; all checked
publication mtimes were unchanged. A copied acceptance with a modified coverage
artifact failed closed on hash validation.

Two earlier noncanonical development outputs, `p11ds_5b0e57366d593c1ca4b02a35`
and `p11ds_6fe07c22b5aeba1e76ccd632`, exposed a temporary staging path in a daily
audit record. They remain noncanonical evidence. Replacing physical paths with
logical artifact locators closed the only determinism defect before activation.

Historical acceptance SHA-256 remains
`726fd5e1d9969a01fff797ccdff16bd7d7ae5e090591ea478850d11aa4079a8b`;
P10 acceptance SHA-256 remains
`f43a7206be6814c35e517017b438a977561c5113be855bff8d884c3d4a52e8c0`.

## Validation

- Focused living rematerialization: 27 R assertions passed.
- Relevant P10/P11/P9 downstream Python regression: 88 tests passed.
- Relevant existing preprocessing/targets R regression: 44 assertions passed.
- Main, P10, historical P11, and living-rematerialization `tar_validate()`:
  passed without target execution.
- Draft 2020-12 acceptance schema and artifact readback: passed.
- Deterministic full production rerun and create-or-validate: passed.
- Corruption rejection: passed.
- Target dependency network regenerated: 163 targets, 525 edges, zero errors.
- Python/R/JSON/YAML parse, Markdown links, and `git diff --check`: passed.

## Prohibited Work

| Activity | Count |
|---|---:|
| Fold generation | 0 |
| Ridge fitting | 0 |
| OOF predictions | 0 |
| R2/RMSE/MAE computation | 0 |
| Response-informed threshold tuning | 0 |
| Model-specific eligibility | 0 |
| New embedding inference or encoder tuning | 0 |
| Checkpoint changes | 0 |
| P9/P10 reruns | 0 |
| SGIS/land-value/ECOSTRESS rematerialization | 0 |
| Dissertation mutation | 0 |

## Next Work Unit

`P11_C_SPATIAL_FOLDS_AND_LEAKAGE_GATES`

No folds or ridge probes were generated in this work unit.

## Prompt Summary

Implement the dissertation-authorized partial-support living-population
mapping over the full grid-hour universe, rematerialize only four living
targets, publish an immutable superseding 1,600-by-11 dataset, and preserve all
other scientific evidence.
