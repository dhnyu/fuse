# P11 Transformation Closure and Spatial Folds

## Verdict

`P11_TRANSFORMATION_CLOSURE_AND_P11_C_PASS_PUSHED`

Execution time: 2026-09-05 00:14 KST. This work closed the previously
unspecified target transformations, refreshed the future-facing dissertation
authority, materialized P11-C district folds and immutable P10 embedding
bindings, and stopped before ridge fitting.

## Repository And Authority State

| Item | Before | After |
|---|---|---|
| Fuse `reduced` | `1e29f3a17d777f600dc180012560459804121ee2` | recorded by final commit |
| Dissertation `reduced` | `4adbd49b6dacab589d2fa99d88ec5be83aceb287` | `989c19d98e64ec129dc53b761c58a4d961fc3983` |
| Prior dissertation authority | `disauth_60a514578f57b9397ce71ee6` | immutable historical evidence |
| Active future P11 authority | not defined | `disauth_febd90b8475a5e9caa9f7d2f` |
| P11 dataset | `p11ds_39607da2de792ad6b3c9bb30` | unchanged |
| P10 acceptance | `p10acc_6e5071beee7616750dec7907` | unchanged |

The dissertation change is limited to the downstream transformation and
inverse-reporting rule. It was committed and pushed before Fuse bound the new
authority. Historical P9, P10, earlier P11 methodology, and downstream dataset
artifacts were not rewritten.

## Transformation Methodology

Artifact `p11meth_6cc844b7f5d1fc896d9e7be2` has content SHA-256
`6cc844b7f5d1fc896d9e7be25ba48c7b544bb7b82750c40bc2d1eeb8b5c57ce9`.
The decision was fixed before inspecting any ridge result.

| Target | Transform |
|---|---|
| Total population | `log1p` |
| Households | `log1p` |
| Housing units | `log1p` |
| Establishments | `log1p` |
| Workers | `log1p` |
| Weekday daytime living population | `log1p` |
| Weekday nighttime living population | `log1p` |
| Weekend daytime living population | `log1p` |
| Weekend nighttime living population | `log1p` |
| Official land value | `log1p` |
| ECOSTRESS LST (Kelvin) | `identity` |

`log1p` is exactly `log(1 + y)` with inverse `exp(y_transformed) - 1` and
requires finite nonnegative input. Identity requires finite input. Both are
parameter-free. Future predictor standardization is training-fold-only. R2,
RMSE, and MAE must be computed only after inverse transformation on the
original response scale. No transform, offset, clipping rule, alpha, or ridge
lambda was tuned; ridge lambda remains exactly 1.

## Master District Folds

The master fold artifact is `p11fold_48a03eba108b799379891e4c`, content hash
`48a03eba108b799379891e4c475c2043f5fb17d7afb713c0f576f63dfc9d1d18`.
All 1,600 original evaluation scenes have exactly one center-point assignment,
all 25 Seoul autonomous districts are represented, there is no randomization
or buffer, and an exact boundary tie is resolved by lowest canonical district
ID.

| District | Scenes | District | Scenes | District | Scenes |
|---|---:|---|---:|---|---:|
| 11010 | 51 | 11020 | 31 | 11030 | 68 |
| 11040 | 48 | 11050 | 49 | 11060 | 40 |
| 11070 | 62 | 11080 | 62 | 11090 | 68 |
| 11100 | 41 | 11110 | 88 | 11120 | 69 |
| 11130 | 47 | 11140 | 70 | 11150 | 35 |
| 11160 | 114 | 11170 | 50 | 11180 | 44 |
| 11190 | 52 | 11200 | 42 | 11210 | 85 |
| 11220 | 124 | 11230 | 103 | 11240 | 93 |
| 11250 | 64 |  |  |  |  |

## Target-Fold Readiness

The machine-readable complete 11 x 25 table is
`target_fold_readiness.parquet` under readiness acceptance
`p11c_e78d7c740edc49f1f646ebc3`. Every one of 275 rows records district scene
count, eligible/ineligible count, train/test N, train variance, and
evaluability.

| Target | Eligible | Test N min/median/max | Train N min/median/max | Evaluable | Empty |
|---|---:|---:|---:|---:|---:|
| ECOSTRESS LST | 1,600 | 31 / 62 / 124 | 1,476 / 1,538 / 1,569 | 25 | 0 |
| Establishments | 1,442 | 31 / 52 / 101 | 1,341 / 1,390 / 1,411 | 25 | 0 |
| Households | 1,358 | 30 / 49 / 98 | 1,260 / 1,309 / 1,328 | 25 | 0 |
| Housing units | 1,324 | 30 / 49 / 97 | 1,227 / 1,275 / 1,294 | 25 | 0 |
| Official land value | 1,244 | 18 / 43 / 102 | 1,142 / 1,201 / 1,226 | 25 | 0 |
| Total population | 1,372 | 30 / 49 / 99 | 1,273 / 1,323 / 1,342 | 25 | 0 |
| Weekday daytime | 1,570 | 31 / 62 / 118 | 1,452 / 1,508 / 1,539 | 25 | 0 |
| Weekday nighttime | 1,565 | 31 / 62 / 117 | 1,448 / 1,503 / 1,534 | 25 | 0 |
| Weekend daytime | 1,570 | 31 / 62 / 118 | 1,452 / 1,508 / 1,539 | 25 | 0 |
| Weekend nighttime | 1,567 | 31 / 62 / 118 | 1,449 / 1,505 / 1,536 | 25 | 0 |
| Workers | 1,442 | 31 / 52 / 101 | 1,341 / 1,390 / 1,411 | 25 | 0 |

All training-fold variances are positive. No minimum test-N threshold was
invented. Living-population ineligible scenes occur only in districts 11010,
11090, 11100, 11110, 11120, 11210, and 11220, depending on temporal class;
the accepted `valid_scene_hour_count >= 1` rule was not changed.

## Frozen Embedding Bindings

Embedding binding `p11emb_0fe61f9e1dc0faf640084abb` has content hash
`0fe61f9e1dc0faf640084abb811264eeea306fa2e412d6f274588105d4b6c405`.
Every stored P10 array was verified as float32 `4800 x 128`; only its exact
ordered `[3200:4800]` original-gallery slice is bound as the `1600 x 128` P11
predictor. Augmented query rows are excluded.

| Model | P9 acceptance | Checkpoint | Gallery SHA-256 |
|---|---|---|---|
| cfg_d128 | `p9accv2_a1c00e32a882ddc4b7e2677b` | `p9ck_56195e9ea3cd45d80cf5e23c` | `7e26862e75b2ba9c0c1f5f751c1dfa9eecf87d79d76d2f599c2481682a3f1d51` |
| A1 | `p9accv2_9a207a914e17fbdc663f738a` | `p9ck_37979e7a36f6b189ecf674d0` | `f8f419ac0034ac363aa8607d1dd26334af011b4791c4b5cf9362891c5c99c4c5` |
| A2 | `p9accv2_b603f92e47f7ffe6bdf3a5d3` | `p9ck_74cc9b14a7d294463bfd5a9c` | `4c12fec4d9b76924b04bfd6bb51dbf1d0163a18562a4e2ccb11529ce0a2a669f` |
| A3 | `p9accv2_90763f5a22a6aab791c42290` | `p9ck_c0784d438146deeaee04fd34` | `6c424fc28b8bff3162d2983561bdb8a8b8c0922c218bfc19fcac7ab4735fca40` |
| A4 | `p9accv2_b25055427137c88c820dcc51` | `p9ck_a71bec2d0fae827ee7c97879` | `a45a1a6f39ea6c231a6b949b188352026a9746e36d2abc21ea4eec7e12715389` |
| A5 | `p9accv2_0a4ac70cbf2ebcba233c6084` | `p9ck_0ee547be5473315d457bf104` | `86755226094c8ec939f03d725140d74365958759eac53b66478950da1edcc6b7` |
| SSV | `p9accv2_93c296bec0ffe6f1a3ccb8ee` | `p9ck_388bce700e35c96012e77b1a` | `04adf4efddbe893549fbf7e6c582318986daf5054276cccd5678783a1a87eb7a` |
| DS | `p9accv2_f4194b7c74f8dedb4c867e6b` | `p9ck_65cc78a1a97330f3af05fba4` | `82130271805665ed9bef1f1cc0ea3f93ef2fb64f752ae15aa241f204413b0dcf` |

## Leakage And OOF Readiness

All gates passed: no target ancestry in representation training, disjoint
district train/test ownership, one district per scene, model-independent target
eligibility, identical target populations for all eight models, no model-
specific preprocessing, no use of P10 retrieval metrics, training-fold-only
future predictor standardization, fixed parameter-free target transforms,
ridge lambda 1, no alpha tuning/inner CV/random CV, and no manual/latest/V1
fallback.

Prospective OOF ownership is complete: each eligible scene belongs to exactly
one evaluable held-out district, no scene can receive more than one prediction,
and there are no eligible scenes excluded by a nonevaluable fold. Predictions
generated in this work unit: 0.

## Validation

- Focused P11-C Python tests: 4/4 PASS.
- Combined dissertation/P9 resolver/P10/P11 Python regression: 120/120 PASS.
- Existing P11 preprocessing/rematerialization R tests: 40/40 PASS.
- New P11-C target-closure R tests: 8/8 PASS.
- Isolated target execution: 3/3 targets completed in an external temporary
  store; repeated publication was idempotent.
- Isolated graph: 3 targets, 2 edges, one component, all up to date.
- `tar_validate()`: main, P10, P11 preprocessing, living rematerialization,
  and P11-C scripts PASS without scientific target execution.
- Draft 2020-12: new authority, transform methodology, and readiness acceptance
  schemas PASS. JSON/YAML, Python AST, and R parse checks PASS.
- Exact rerun retained readiness identity and acceptance mtime; copied-artifact
  corruption was rejected.
- Typst PDF build was attempted but unavailable because the installed Snap
  launcher rejected `/members/dhnyu` as its home directory. The edited Typst
  source is syntactically limited to prose/math already used in the document;
  the PDF was not regenerated.
- `git diff --check`: PASS.

Immutable readback SHA-256 values:

- P10 acceptance: `f43a7206be6814c35e517017b438a977561c5113be855bff8d884c3d4a52e8c0`.
- P11 dataset acceptance: `ff246a1134ebd3f6e63b826eab786053718bebb5c5e33baba58b85db246ee51f`.
- P11-C acceptance: `216d96f9bdc7ff70e49aa66e4784335430a0c380d0f73a615720e648836f5fae`.

## Prohibited Work Accounting

| Activity | Count |
|---|---:|
| Ridge fitting | 0 |
| OOF prediction generation | 0 |
| R2/RMSE/MAE computation | 0 |
| Transformation or alpha/lambda tuning | 0 |
| Fold redesign/random folds | 0 |
| Downstream dataset rematerialization | 0 |
| New embedding inference/fine-tuning | 0 |
| P9/P10 rerun or checkpoint mutation | 0 |

## Next Work Unit

`P11_E_SPATIAL_RIDGE_PROBES_AND_OOF_PREDICTIONS`

This report does not execute or begin P11-E.

## Prompt Summary

Close the predefined eleven-target transformation map in the dissertation and
Fuse authority, then resume P11-C to materialize deterministic 25-district
folds, target eligibility/evaluability, eight frozen P10 embedding bindings,
leakage gates, and OOF readiness while stopping before ridge fitting.
