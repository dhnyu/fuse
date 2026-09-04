# P11-E Spatial Ridge Probes and OOF Predictions

## Verdict

`P11_E_SPATIAL_RIDGE_PROBES_AND_OOF_PREDICTIONS_PASS_PUSHED`

Executed 2026-09-05 KST. This work fit the frozen district-held-out ridge
probes, published exactly-once OOF predictions and pooled original-scale
metrics, and stopped before P11-F.

## Immutable Inputs

| Input | Identity |
|---|---|
| Dissertation | `989c19d98e64ec129dc53b761c58a4d961fc3983` |
| Dissertation authority | `disauth_febd90b8475a5e9caa9f7d2f` |
| Transformation methodology | `p11meth_6cc844b7f5d1fc896d9e7be2` |
| P11-C readiness | `p11c_e78d7c740edc49f1f646ebc3` |
| Master folds | `p11fold_48a03eba108b799379891e4c` |
| Embedding binding | `p11emb_0fe61f9e1dc0faf640084abb` |
| Downstream dataset | `p11ds_39607da2de792ad6b3c9bb30` |
| P10 acceptance | `p10acc_6e5071beee7616750dec7907` |

All 275 target-fold readiness rows were evaluable. All eight predictors used
the same ordered 1,600-scene original-gallery population and the accepted
target-specific eligible scene IDs. No inference or dataset rematerialization
occurred.

## Fixed Evaluation Contract

Each of the `8 x 11 x 25 = 2,200` fits used float64 predictors, training-fold
population mean and standard deviation (`ddof=0`), scale 1 for any zero-
variance dimension, an unpenalized intercept, and the exact objective
`SSE + 1 * ||beta||^2`. No dimensions were dropped. Ten targets used fixed
parameter-free `log1p`; ECOSTRESS Kelvin LST used identity. Log-scale
predictions were inverse-transformed with `expm1` and were not clipped.

The pre-production deterministic pilot repeated 100 representative fits and
produced digest
`1493d031a3394d9f3a2e16549d215f7bd1329a0fe0b85d95f2bc66d000d19f86`
twice.

## Acceptance And Runtime

- P11-E acceptance: `p11e_047e764ed7467b72ebe846df`.
- Content SHA-256: `047e764ed7467b72ebe846df04dd5e408f48c917da65eb5832b017b73f6c0766`.
- Acceptance SHA-256: `9cb67827449bbb5172af223fbd2798ca8bd7d2ffd99cf06f00b2e64c019a99d0`.
- Successful fits: 2,200/2,200.
- OOF rows: 128,432/128,432 expected.
- Model-target metric rows: 88/88.
- Execution: eight model-target thread workers, one BLAS thread each; 25 folds
  sequential within a task.
- Scientific execution wall: 16.30 s.
- Per-fit wall median/p95/max: 0.0424/0.0657/0.1070 s.
- Sum of independently timed fit work: 92.84 s.

The initial full calculation stopped before publication because canonical JSON
correctly rejected a land-value variance above its interoperable safe-number
range. Publication hashing was changed to deterministic Arrow IPC bytes, which
preserve float64 exactly. No artifact existed before the corrected run.

## Pooled OOF Metrics And FM Deltas

All metrics below are pooled over the complete original-scale OOF population.
Delta columns are `model - FM`; lower RMSE/MAE remains better. The complete
machine-readable tables are `pooled_metrics.parquet` and
`fm_relative_deltas.parquet` in the acceptance root.

|Target|Model|N|R2|RMSE|MAE|dR2|dRMSE|dMAE|
|---|---|---:|---:|---:|---:|---:|---:|---:|
|ECOSTRESS LST|FM|1600|0.439578|1.09362|0.866920|0|0|0|
|ECOSTRESS LST|A1|1600|0.276680|1.24244|0.967890|-0.162898|+0.148816|+0.100970|
|ECOSTRESS LST|A2|1600|0.340243|1.18659|0.931510|-0.099335|+0.092971|+0.064591|
|ECOSTRESS LST|A3|1600|0.421711|1.11092|0.880793|-0.017866|+0.017296|+0.013873|
|ECOSTRESS LST|A4|1600|0.433205|1.09982|0.864495|-0.006373|+0.006201|-0.002424|
|ECOSTRESS LST|A5|1600|0.441067|1.09217|0.859805|+0.001489|-0.001454|-0.007115|
|ECOSTRESS LST|SSV|1600|0.323384|1.20166|0.949936|-0.116193|+0.108035|+0.083016|
|ECOSTRESS LST|DS|1600|0.435031|1.09805|0.866187|-0.004547|+0.004428|-0.000733|
|Establishments|FM|1442|0.192174|595.604|274.821|0|0|0|
|Establishments|A1|1442|0.009109|659.647|315.286|-0.183064|+64.043|+40.465|
|Establishments|A2|1442|0.277671|563.205|259.688|+0.085497|-32.400|-15.133|
|Establishments|A3|1442|0.260806|569.742|249.770|+0.068633|-25.863|-25.050|
|Establishments|A4|1442|0.235825|579.289|257.538|+0.043652|-16.315|-17.283|
|Establishments|A5|1442|0.157547|608.235|276.619|-0.034627|+12.631|+1.798|
|Establishments|SSV|1442|0.121746|621.025|284.474|-0.070428|+25.421|+9.654|
|Establishments|DS|1442|0.121443|621.132|275.441|-0.070731|+25.528|+0.620|
|Households|FM|1358|-0.589404|2021.09|1174.27|0|0|0|
|Households|A1|1358|0.034202|1575.47|1115.91|+0.623606|-445.615|-58.353|
|Households|A2|1358|-0.607983|2032.87|1190.23|-0.018579|+11.778|+15.961|
|Households|A3|1358|-0.410300|1903.81|1119.77|+0.179104|-117.277|-54.499|
|Households|A4|1358|-0.531570|1983.98|1162.02|+0.057834|-37.112|-12.248|
|Households|A5|1358|-0.502606|1965.13|1170.92|+0.086798|-55.961|-3.353|
|Households|SSV|1358|-0.500163|1963.53|1202.19|+0.089241|-57.559|+27.922|
|Households|DS|1358|-0.605410|2031.24|1193.70|-0.016006|+10.151|+19.437|
|Housing units|FM|1324|-0.716650|1518.11|865.485|0|0|0|
|Housing units|A1|1324|-0.122435|1227.56|877.179|+0.594215|-290.549|+11.694|
|Housing units|A2|1324|-0.677694|1500.78|885.271|+0.038957|-17.325|+19.786|
|Housing units|A3|1324|-0.434251|1387.63|842.720|+0.282400|-130.476|-22.765|
|Housing units|A4|1324|-0.821152|1563.63|868.285|-0.104502|+45.525|+2.800|
|Housing units|A5|1324|-0.615001|1472.47|870.642|+0.101649|-45.632|+5.157|
|Housing units|SSV|1324|-0.851743|1576.71|921.612|-0.135093|+58.603|+56.127|
|Housing units|DS|1324|-0.795420|1552.55|885.043|-0.078769|+34.439|+19.558|
|Official land value|FM|1244|0.108389|4.76232e6|2.32218e6|0|0|0|
|Official land value|A1|1244|0.022945|4.98529e6|2.51849e6|-0.085444|+222970|+196312|
|Official land value|A2|1244|0.139770|4.67777e6|2.38013e6|+0.031381|-84558|+57948|
|Official land value|A3|1244|0.141144|4.67403e6|2.26327e6|+0.032755|-88294|-58917|
|Official land value|A4|1244|0.193327|4.52981e6|2.19404e6|+0.084938|-232514|-128138|
|Official land value|A5|1244|0.205979|4.49415e6|2.16072e6|+0.097590|-268177|-161467|
|Official land value|SSV|1244|0.096888|4.79294e6|2.40544e6|-0.011501|+30616|+83259|
|Official land value|DS|1244|0.114788|4.74520e6|2.33427e6|+0.006399|-17120|+12088|
|Total population|FM|1372|-0.838630|4648.29|2629.35|0|0|0|
|Total population|A1|1372|-0.085647|3571.82|2559.06|+0.752982|-1076.46|-70.283|
|Total population|A2|1372|-0.815253|4618.64|2718.65|+0.023377|-29.644|+89.309|
|Total population|A3|1372|-0.618635|4361.34|2556.19|+0.219994|-286.943|-73.155|
|Total population|A4|1372|-0.858822|4673.74|2641.27|-0.020192|+25.454|+11.923|
|Total population|A5|1372|-0.867615|4684.78|2698.71|-0.028985|+36.495|+69.362|
|Total population|SSV|1372|-0.863315|4679.39|2804.74|-0.024685|+31.099|+175.400|
|Total population|DS|1372|-0.867914|4685.16|2718.83|-0.029285|+36.871|+89.484|
|Weekday daytime|FM|1570|0.155007|4386.90|2505.51|0|0|0|
|Weekday daytime|A1|1570|0.194240|4283.85|2523.78|+0.039233|-103.051|+18.269|
|Weekday daytime|A2|1570|0.283965|4038.30|2320.16|+0.128958|-348.602|-185.348|
|Weekday daytime|A3|1570|0.319126|3937.90|2239.82|+0.164119|-449.000|-265.692|
|Weekday daytime|A4|1570|0.160438|4372.78|2429.38|+0.005431|-14.120|-76.132|
|Weekday daytime|A5|1570|0.188534|4298.99|2484.04|+0.033527|-87.910|-21.473|
|Weekday daytime|SSV|1570|0.241639|4155.94|2430.17|+0.086632|-230.962|-75.339|
|Weekday daytime|DS|1570|-0.082039|4964.24|2706.48|-0.237046|+577.338|+200.974|
|Weekday nighttime|FM|1565|-0.075131|3669.52|2217.90|0|0|0|
|Weekday nighttime|A1|1565|0.264491|3035.10|2076.15|+0.339621|-634.421|-141.746|
|Weekday nighttime|A2|1565|0.257182|3050.14|1983.64|+0.332313|-619.380|-234.251|
|Weekday nighttime|A3|1565|0.212834|3139.87|1987.99|+0.287965|-529.648|-229.905|
|Weekday nighttime|A4|1565|0.080749|3393.09|2110.87|+0.155879|-276.427|-107.024|
|Weekday nighttime|A5|1565|0.026149|3492.41|2162.60|+0.101279|-177.112|-55.297|
|Weekday nighttime|SSV|1565|0.198693|3167.95|2059.25|+0.273823|-501.571|-158.643|
|Weekday nighttime|DS|1565|-0.287790|4016.07|2424.58|-0.212659|+346.548|+206.683|
|Weekend daytime|FM|1570|0.031415|3861.30|2318.97|0|0|0|
|Weekend daytime|A1|1570|0.251872|3393.54|2192.74|+0.220457|-467.763|-126.231|
|Weekend daytime|A2|1570|0.263309|3367.50|2093.82|+0.231894|-493.802|-225.152|
|Weekend daytime|A3|1570|0.267774|3357.28|2056.75|+0.236359|-504.022|-262.222|
|Weekend daytime|A4|1570|0.097398|3727.46|2220.86|+0.065983|-133.842|-98.110|
|Weekend daytime|A5|1570|0.115432|3690.04|2253.94|+0.084017|-171.266|-65.035|
|Weekend daytime|SSV|1570|0.222782|3458.89|2168.81|+0.191367|-402.415|-150.159|
|Weekend daytime|DS|1570|-0.144731|4197.75|2518.61|-0.176146|+336.449|+199.638|
|Weekend nighttime|FM|1567|-0.073210|3765.22|2253.36|0|0|0|
|Weekend nighttime|A1|1567|0.257386|3132.06|2143.66|+0.330596|-633.165|-109.701|
|Weekend nighttime|A2|1567|0.261631|3123.09|2016.81|+0.334841|-642.129|-236.545|
|Weekend nighttime|A3|1567|0.234107|3180.77|2021.75|+0.307317|-584.452|-231.605|
|Weekend nighttime|A4|1567|0.070313|3504.42|2159.09|+0.143523|-260.798|-94.266|
|Weekend nighttime|A5|1567|0.024448|3589.83|2205.75|+0.097658|-175.396|-47.604|
|Weekend nighttime|SSV|1567|0.204047|3242.59|2092.31|+0.277257|-522.632|-161.043|
|Weekend nighttime|DS|1567|-0.232431|4034.87|2463.34|-0.159220|+269.647|+209.981|
|Workers|FM|1442|0.299895|3916.04|1632.97|0|0|0|
|Workers|A1|1442|-0.027608|4744.37|2029.90|-0.327503|+828.337|+396.931|
|Workers|A2|1442|0.309177|3889.99|1618.36|+0.009282|-26.046|-14.611|
|Workers|A3|1442|0.306626|3897.17|1554.74|+0.006731|-18.870|-78.225|
|Workers|A4|1442|0.230411|4105.77|1575.73|-0.069484|+189.733|-57.243|
|Workers|A5|1442|0.291931|3938.25|1643.67|-0.007964|+22.210|+10.699|
|Workers|SSV|1442|0.211829|4155.04|1722.37|-0.088066|+239.006|+89.402|
|Workers|DS|1442|0.033063|4602.19|1723.89|-0.266832|+686.151|+90.922|

## Nested-Ablation Support

The following are `left - right` pooled R2 differences. The exact R2, RMSE,
and MAE differences for all 77 rows are in
`nested_ablation_deltas.parquet`; these are descriptive and do not select a
model.

|Target|A2-A1|A3-A2|A4-A3|A5-A4|FM-A5|A2-SSV|FM-DS|
|---|---:|---:|---:|---:|---:|---:|---:|
|ECOSTRESS LST|+0.0636|+0.0815|+0.0115|+0.0079|-0.0015|+0.0169|+0.0045|
|Establishments|+0.2686|-0.0169|-0.0250|-0.0783|+0.0346|+0.1559|+0.0707|
|Households|-0.6422|+0.1977|-0.1213|+0.0290|-0.0868|-0.1078|+0.0160|
|Housing units|-0.5553|+0.2434|-0.3869|+0.2062|-0.1016|+0.1740|+0.0788|
|Official land value|+0.1168|+0.0014|+0.0522|+0.0127|-0.0976|+0.0429|-0.0064|
|Total population|-0.7296|+0.1966|-0.2402|-0.0088|+0.0290|+0.0481|+0.0293|
|Weekday daytime|+0.0897|+0.0352|-0.1587|+0.0281|-0.0335|+0.0423|+0.2370|
|Weekday nighttime|-0.0073|-0.0443|-0.1321|-0.0546|-0.1013|+0.0585|+0.2127|
|Weekend daytime|+0.0114|+0.0045|-0.1704|+0.0180|-0.0840|+0.0405|+0.1761|
|Weekend nighttime|+0.0042|-0.0275|-0.1638|-0.0459|-0.0977|+0.0576|+0.1592|
|Workers|+0.3368|-0.0026|-0.0762|+0.0615|+0.0080|+0.0973|+0.2668|

These results are not monotonic across the cumulative architecture sequence.
Several ablations outperform FM for individual downstream targets, while FM
remains the fixed P9-selected model. P11-E does not reopen P9/P10 selection.

## Fold Diagnostics

- Numerical status PASS: 2,200/2,200.
- Singular/non-finite fits or predictions: 0.
- Zero-variance embedding dimensions: 0 across all fits.
- Coefficient norm min/median/p95/max: 3.678/7.414/9.550/10.293.
- Prediction range: -0.815 to 39,615,486.133.
- Finite negative inverse predictions: 143/128,432. These arise from
  `expm1` of negative transformed predictions and were intentionally not
  clipped. Counts were 78 establishments, 15 households, 10 housing units,
  8 total population, 1 weekday nighttime, 2 weekend nighttime, and 29
  workers.

Negative pooled R2 values are retained exactly as observed under district-held-
out original-scale evaluation. No lambda, transform, eligibility, or model was
changed in response.

## Determinism, Leakage, And Validation

- Exact OOF key uniqueness and target-specific coverage: PASS.
- Fold ownership and P11-C train/test counts: exact.
- Accepted observed responses and fixed forward/inverse transforms: PASS.
- Pooled metrics independently recomputed from stored OOF rows: bitwise PASS.
- Complete rerun returned the same acceptance ID and did not rewrite the
  acceptance file.
- Copied-artifact corruption rejection: PASS.
- Focused P11-E tests: 6/6 PASS.
- Combined dissertation/P9 resolver/P10/P11 Python regression: 126/126 PASS.
- Relevant P11 R tests: 58/58 PASS.
- Isolated P11-E target graph: 3/3 targets, 3 vertices, 2 edges, one component,
  all up to date.
- Applicable `tar_validate()`: main, P10, P11 preprocessing, living
  rematerialization, P11-C, and P11-E PASS without unintended execution.
- Draft 2020-12 acceptance schema, Python AST, R, JSON, and YAML parse: PASS.
- `git diff --check`: PASS.

Train-only scaling identities hash each training scene population, mean,
standard deviation, and zero-variance index set. All eight models use identical
eligible populations per target. No test-district statistics, P10 retrieval
metrics, random folds, manual/latest/V1 fallback, or model-specific target
preprocessing entered any fit.

## Prohibited Work Accounting

| Activity | Count |
|---|---:|
| Encoder/model fine-tuning | 0 |
| New embedding inference | 0 |
| Ridge lambda or transformation tuning | 0 |
| Fold or eligibility changes | 0 |
| Downstream dataset rematerialization | 0 |
| P9/P10 rerun or checkpoint reselection | 0 |
| Model reselection | 0 |
| Dissertation mutation | 0 |

## Next Work Unit

`P11_F_FINAL_DOWNSTREAM_COMPARISON_AND_ACCEPTANCE`

P11-F was not started.

## Prompt Summary

Execute exactly 2,200 fixed-lambda spatial ridge fits over eight frozen P10
representations, eleven accepted targets, and 25 district-held-out folds;
publish complete original-scale OOF predictions, pooled R2/RMSE/MAE and fixed
comparison artifacts without tuning, inference, or model reselection.
