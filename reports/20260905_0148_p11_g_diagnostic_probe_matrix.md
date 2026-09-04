# P11-G Diagnostic Probe Matrix

## Verdict

`P11_G_DIAGNOSTIC_PROBE_MATRIX_PASS_PUSHED`

## Purpose and scope

This work diagnoses low downstream R2 by separating spatial-CV effects from nonlinear accessibility in the frozen representations. It adds no encoder inference, target rematerialization, tuning, or model selection. Execution began and completed on 2026-09-05 (Asia/Seoul). The input prompt authorized exactly Spatial/Random CV crossed with Ridge/MLP; the later amendment required dual RTX A6000 execution for all MLP fits.

## Authorities and immutable inputs

- Fuse input HEAD: `f1fa3b1f4f2c2170961a16894e31d12bc5595dd0`
- Dissertation: `989c19d98e64ec129dc53b761c58a4d961fc3983` (unchanged)
- Dissertation authority: `disauth_febd90b8475a5e9caa9f7d2f`
- Transformation methodology: `p11meth_6cc844b7f5d1fc896d9e7be2`
- P11-C: `p11c_e78d7c740edc49f1f646ebc3`
- P11-E baseline: `p11e_047e764ed7467b72ebe846df`
- Dataset: `p11ds_39607da2de792ad6b3c9bb30`
- Embeddings: `p11emb_0fe61f9e1dc0faf640084abb`
- P11-G acceptance: `p11g_b1ad31498120f8f4a9445958`
- P11-G acceptance SHA-256: `a1310a4cc8a40e92645827616fbffea71e5c5fd8df2e7f3c5d7901e038c28218`
- P11-E acceptance pre/post SHA-256: `9cb67827449bbb5172af223fbd2798ca8bd7d2ffd99cf06f00b2e64c019a99d0`

All eight accepted P10 original-gallery slices are exactly 1,600 x 128; no augmented-query embedding is used.

## Random CV contract

The canonical 1,600 scene IDs are permuted once using NumPy PCG64 with content-derived global seed `4824802954555229827`, then assigned round-robin to five folds. Every fold contains 320 master scenes. Target eligibility is intersected afterward, so the assignment is target-independent and identical across models and probes. No target value is read to construct a fold.

## MLP contract

Every fit uses `Linear(128,64) -> exact GELU -> Dropout(0.1) -> Linear(64,1)`, AdamW (`lr=1e-3`, weight decay `1e-4`), batch 64, maximum 200 epochs, deterministic 10% inner validation, patience 20, strict transformed-scale validation-MSE improvement, and best-state restoration. Predictor statistics use only the inner-training partition. Target transforms and original-scale inverse/metrics are the accepted P11 method. No target standardization or architecture/hyperparameter search occurred.

## GPU Execution

- GPUs: two NVIDIA RTX A6000, driver 595.45.04, CUDA 13.0.
- Environment: PyTorch 2.12.0+cu130, cuDNN 9.2.0.
- Backend: four persistent workers, two per GPU; every fit stays entirely on one GPU.
- Precision: float32; mixed precision and TF32 disabled; deterministic algorithms and `CUBLAS_WORKSPACE_CONFIG=:4096:8` enabled.
- Backend-independent dropout: the CPU native-dropout schedule is frozen once per fit and transferred once to CUDA, preventing CPU/CUDA RNG-stream changes without epoch-level transfers.
- CPU/CUDA gate: same fit ID and best epoch on both GPUs; maximum prediction absolute/relative differences `9.1553e-05` / `3.3013e-07`; validation-loss difference `6.1035e-05`.
- One worker/GPU pilot: 0.471 fits/s, mean utilization 17.6%/18.7%, peak 465 MiB/GPU.
- Two workers/GPU pilot: 0.641 fits/s (+36%), mean utilization 84.9%/86.9%, peak 926 MiB/GPU, identical prediction hash.
- Full run: 2,640 MLP fits in 1842.072s; total matrix wall 1863.293s.
- Median/p95 MLP fit: 2.389s / 4.691s.
- Full-run utilization: GPU0 92.0%, GPU1 89.2%; peak 958 MiB each.
- Per-device workload: 1,320 fits each; failures/retries 0/0.
- Pre-amendment CPU evidence: an unreferenced, noncanonical 8-process CPU attempt completed in 375.386s before the amendment arrived. It remains preserved at `p11g_75d1e910d177bc4659c57c97`, was not adopted, and was not deleted or overwritten. The mandated GPU run was ~4.90x slower in wall time despite high utilization, reflecting the tiny-network kernel/coordination regime.

## Workload and integrity

- Reused Spatial Ridge fits: 2,200 (no refit).
- New Random Ridge fits: 440.
- New Spatial MLP fits: 2,200.
- New Random MLP fits: 440.
- New fits: 3,080/3,080 successful.
- Four-cell OOF rows: 513,728, exactly once per eligible scene/model/target/cell.
- Aggregate rows: 352/352.
- MLP: 2213 early-stopped; 431 maximum-epoch; 0 non-finite.
- Best epoch min/median/max: 14/94/200.
- Spatial Ridge metrics reproduce P11-E exactly; all 352 rows independently reproduce from stored OOF evidence.

## FM diagnostic summary

| target              |   spatial_ridge_r2 |   random_ridge_r2 |   spatial_mlp_r2 |   random_mlp_r2 |   ridge_spatial_penalty |   mlp_spatial_penalty |   spatial_nonlinear_gain |   random_nonlinear_gain |
|:--------------------|-------------------:|------------------:|-----------------:|----------------:|------------------------:|----------------------:|-------------------------:|------------------------:|
| ecostress_lst       |           0.439578 |          0.528962 |      -373.142    |     -380.536    |               -0.089385 |              7.39484  |              -373.581    |             -381.065    |
| establishments      |           0.192174 |          0.242537 |         0.218262 |        0.125183 |               -0.050363 |              0.093079 |                 0.026088 |               -0.117354 |
| households          |          -0.589404 |         -0.602779 |        -0.621563 |       -0.660846 |                0.013375 |              0.039283 |                -0.032159 |               -0.058066 |
| housing_units       |          -0.71665  |         -0.794994 |        -0.912841 |       -1.98288  |                0.078343 |              1.07004  |                -0.196191 |               -1.18789  |
| official_land_value |           0.108389 |          0.218345 |        -1.69462  |       -0.845387 |               -0.109956 |             -0.849234 |                -1.80301  |               -1.06373  |
| total_population    |          -0.83863  |         -0.91869  |        -0.876607 |       -1.07501  |                0.08006  |              0.198401 |                -0.037977 |               -0.156317 |
| weekday_daytime     |           0.155007 |          0.203342 |        -0.104813 |       -0.210891 |               -0.048335 |              0.106078 |                -0.25982  |               -0.414233 |
| weekday_nighttime   |          -0.075131 |         -0.077331 |        -0.3942   |       -0.464902 |                0.0022   |              0.070702 |                -0.31907  |               -0.387571 |
| weekend_daytime     |           0.031415 |          0.046974 |        -0.583746 |       -0.551858 |               -0.015559 |             -0.031888 |                -0.615161 |               -0.598833 |
| weekend_nighttime   |          -0.07321  |         -0.079063 |        -0.834213 |       -0.649067 |                0.005853 |             -0.185146 |                -0.761003 |               -0.570004 |
| workers             |           0.299895 |          0.324301 |         0.383938 |       -0.177499 |               -0.024406 |              0.561438 |                 0.084043 |               -0.501801 |

For FM, Random Ridge provides only modest target-dependent changes and does not systematically rescue the weak count/living-population results. The fixed MLP improves Spatial R2 for establishments and workers but degrades most FM targets. ECOSTRESS MLP is especially poor because the fixed contract trains directly against unstandardized Kelvin values; this finite result is retained without tuning. Raw deltas, not thresholded labels, are authoritative.

## Cross-model summary

| model                                 |   median_spatial_ridge_r2 |   median_random_ridge_r2 |   median_spatial_mlp_r2 |   median_random_mlp_r2 |   median_ridge_spatial_penalty |   median_mlp_spatial_penalty |   median_spatial_nonlinear_gain |   median_random_nonlinear_gain |
|:--------------------------------------|--------------------------:|-------------------------:|------------------------:|-----------------------:|-------------------------------:|-----------------------------:|--------------------------------:|-------------------------------:|
| cfg_d128                              |                  0.031415 |                 0.046974 |               -0.621563 |              -0.649067 |                      -0.015559 |                     0.093079 |                       -0.25982  |                      -0.501801 |
| cmp_a1_geometric_core                 |                  0.034202 |                 0.051209 |               -0.762523 |              -1.28342  |                       0.019128 |                     0.393736 |                       -1.02701  |                      -1.38612  |
| cmp_a2_semantic_enriched              |                  0.261631 |                 0.246779 |               -0.951517 |              -1.08921  |                       0.000771 |                     0.101284 |                       -0.922264 |                      -1.04534  |
| cmp_a3_object_context_enriched        |                  0.234107 |                 0.264322 |               -0.576468 |              -0.467948 |                      -0.039169 |                     0.090729 |                       -0.553915 |                      -0.67418  |
| cmp_a4_raster_complete_non_relational |                  0.097398 |                 0.129711 |               -0.428597 |              -0.571419 |                      -0.036873 |                    -0.015836 |                       -0.3074   |                      -0.382494 |
| cmp_a5_relation_type_agnostic         |                  0.115432 |                 0.148152 |               -0.33418  |              -0.43712  |                      -0.038591 |                     0.077269 |                       -0.171548 |                      -0.361545 |
| cmp_ds_like                           |                 -0.144731 |                -0.022676 |                0.029104 |               0.04471  |                      -0.125642 |                    -0.01351  |                        0.218804 |                       0.162587 |
| cmp_ssv_like                          |                  0.198693 |                 0.207817 |               -0.753334 |              -0.552836 |                      -0.048175 |                     0.196552 |                       -0.599506 |                      -0.612536 |

DS-like is the only representation with positive median MLP gain under both CV regimes. For most representations, the fixed MLP does not expose additional downstream information relative to Ridge. Spatial-minus-random effects are generally smaller and mixed in sign compared with the MLP degradation, so the evidence does not support a universal spatial-shift-only explanation.

## Full 352-row result table

R2, RMSE, and MAE are pooled over original-scale OOF predictions. Spatial-Ridge rows are immutable P11-E evidence.

| model                                 | target              | cv_regime   | probe   |   eligible_n |          r2 |           rmse |            mae |
|:--------------------------------------|:--------------------|:------------|:--------|-------------:|------------:|---------------:|---------------:|
| cfg_d128                              | ecostress_lst       | random      | mlp     |         1600 | -380.536    |   28.535       |   22.4902      |
| cfg_d128                              | ecostress_lst       | random      | ridge   |         1600 |    0.528962 |    1.00262     |    0.79573     |
| cfg_d128                              | ecostress_lst       | spatial     | mlp     |         1600 | -373.142    |   28.2571      |   21.8074      |
| cfg_d128                              | ecostress_lst       | spatial     | ridge   |         1600 |    0.439578 |    1.09362     |    0.86692     |
| cfg_d128                              | establishments      | random      | mlp     |         1442 |    0.125183 |  619.808       |  267.156       |
| cfg_d128                              | establishments      | random      | ridge   |         1442 |    0.242537 |  576.739       |  268.323       |
| cfg_d128                              | establishments      | spatial     | mlp     |         1442 |    0.218262 |  585.908       |  269.163       |
| cfg_d128                              | establishments      | spatial     | ridge   |         1442 |    0.192174 |  595.604       |  274.821       |
| cfg_d128                              | households          | random      | mlp     |         1358 |   -0.660846 | 2066.01        | 1178.79        |
| cfg_d128                              | households          | random      | ridge   |         1358 |   -0.602779 | 2029.58        | 1169.97        |
| cfg_d128                              | households          | spatial     | mlp     |         1358 |   -0.621563 | 2041.43        | 1200.04        |
| cfg_d128                              | households          | spatial     | ridge   |         1358 |   -0.589404 | 2021.09        | 1174.27        |
| cfg_d128                              | housing_units       | random      | mlp     |         1324 |   -1.98288  | 2001.15        |  942.589       |
| cfg_d128                              | housing_units       | random      | ridge   |         1324 |   -0.794994 | 1552.36        |  871.805       |
| cfg_d128                              | housing_units       | spatial     | mlp     |         1324 |   -0.912841 | 1602.51        |  882.123       |
| cfg_d128                              | housing_units       | spatial     | ridge   |         1324 |   -0.71665  | 1518.11        |  865.485       |
| cfg_d128                              | official_land_value | random      | mlp     |         1244 |   -0.845387 |    6.85133e+06 |    3.31603e+06 |
| cfg_d128                              | official_land_value | random      | ridge   |         1244 |    0.218345 |    4.45901e+06 |    2.14671e+06 |
| cfg_d128                              | official_land_value | spatial     | mlp     |         1244 |   -1.69462  |    8.27904e+06 |    3.59925e+06 |
| cfg_d128                              | official_land_value | spatial     | ridge   |         1244 |    0.108389 |    4.76232e+06 |    2.32218e+06 |
| cfg_d128                              | total_population    | random      | mlp     |         1372 |   -1.07501  | 4938.05        | 2821.06        |
| cfg_d128                              | total_population    | random      | ridge   |         1372 |   -0.91869  | 4748.41        | 2644.66        |
| cfg_d128                              | total_population    | spatial     | mlp     |         1372 |   -0.876607 | 4696.05        | 2722.64        |
| cfg_d128                              | total_population    | spatial     | ridge   |         1372 |   -0.83863  | 4648.29        | 2629.35        |
| cfg_d128                              | weekday_daytime     | random      | mlp     |         1570 |   -0.210891 | 5251.5         | 2907           |
| cfg_d128                              | weekday_daytime     | random      | ridge   |         1570 |    0.203342 | 4259.58        | 2437.92        |
| cfg_d128                              | weekday_daytime     | spatial     | mlp     |         1570 |   -0.104813 | 5016.21        | 2871.2         |
| cfg_d128                              | weekday_daytime     | spatial     | ridge   |         1570 |    0.155007 | 4386.9         | 2505.51        |
| cfg_d128                              | weekday_nighttime   | random      | mlp     |         1565 |   -0.464902 | 4283.34        | 2558.44        |
| cfg_d128                              | weekday_nighttime   | random      | ridge   |         1565 |   -0.077331 | 3673.27        | 2176.06        |
| cfg_d128                              | weekday_nighttime   | spatial     | mlp     |         1565 |   -0.3942   | 4178.7         | 2483.39        |
| cfg_d128                              | weekday_nighttime   | spatial     | ridge   |         1565 |   -0.075131 | 3669.52        | 2217.9         |
| cfg_d128                              | weekend_daytime     | random      | mlp     |         1570 |   -0.551858 | 4887.55        | 2794.35        |
| cfg_d128                              | weekend_daytime     | random      | ridge   |         1570 |    0.046974 | 3830.16        | 2277.25        |
| cfg_d128                              | weekend_daytime     | spatial     | mlp     |         1570 |   -0.583746 | 4937.51        | 2835.12        |
| cfg_d128                              | weekend_daytime     | spatial     | ridge   |         1570 |    0.031415 | 3861.3         | 2318.97        |
| cfg_d128                              | weekend_nighttime   | random      | mlp     |         1567 |   -0.649067 | 4667.32        | 2626.11        |
| cfg_d128                              | weekend_nighttime   | random      | ridge   |         1567 |   -0.079063 | 3775.48        | 2223.77        |
| cfg_d128                              | weekend_nighttime   | spatial     | mlp     |         1567 |   -0.834213 | 4922.36        | 2658.72        |
| cfg_d128                              | weekend_nighttime   | spatial     | ridge   |         1567 |   -0.07321  | 3765.22        | 2253.36        |
| cfg_d128                              | workers             | random      | mlp     |         1442 |   -0.177499 | 5078.62        | 1722.15        |
| cfg_d128                              | workers             | random      | ridge   |         1442 |    0.324301 | 3847.17        | 1619.59        |
| cfg_d128                              | workers             | spatial     | mlp     |         1442 |    0.383938 | 3673.48        | 1584.65        |
| cfg_d128                              | workers             | spatial     | ridge   |         1442 |    0.299895 | 3916.04        | 1632.97        |
| cmp_a1_geometric_core                 | ecostress_lst       | random      | mlp     |         1600 | -473.248    |   31.8136      |   24.4619      |
| cmp_a1_geometric_core                 | ecostress_lst       | random      | ridge   |         1600 |    0.311997 |    1.21173     |    0.947378    |
| cmp_a1_geometric_core                 | ecostress_lst       | spatial     | mlp     |         1600 | -384.737    |   28.6917      |   22.6414      |
| cmp_a1_geometric_core                 | ecostress_lst       | spatial     | ridge   |         1600 |    0.27668  |    1.24244     |    0.96789     |
| cmp_a1_geometric_core                 | establishments      | random      | mlp     |         1442 |   -0.091373 |  692.286       |  343.624       |
| cmp_a1_geometric_core                 | establishments      | random      | ridge   |         1442 |    0.034212 |  651.238       |  314.551       |
| cmp_a1_geometric_core                 | establishments      | spatial     | mlp     |         1442 |   -0.085563 |  690.44        |  338.415       |
| cmp_a1_geometric_core                 | establishments      | spatial     | ridge   |         1442 |    0.009109 |  659.647       |  315.286       |
| cmp_a1_geometric_core                 | households          | random      | mlp     |         1358 |   -1.4022   | 2484.7         | 1551.03        |
| cmp_a1_geometric_core                 | households          | random      | ridge   |         1358 |    0.011655 | 1593.76        | 1119.21        |
| cmp_a1_geometric_core                 | households          | spatial     | mlp     |         1358 |   -1.35184  | 2458.51        | 1484.55        |
| cmp_a1_geometric_core                 | households          | spatial     | ridge   |         1358 |    0.034202 | 1575.47        | 1115.91        |
| cmp_a1_geometric_core                 | housing_units       | random      | mlp     |         1324 |   -1.35168  | 1776.85        | 1156.59        |
| cmp_a1_geometric_core                 | housing_units       | random      | ridge   |         1324 |   -0.141563 | 1237.97        |  886.129       |
| cmp_a1_geometric_core                 | housing_units       | spatial     | mlp     |         1324 |   -1.47889  | 1824.27        | 1189.52        |
| cmp_a1_geometric_core                 | housing_units       | spatial     | ridge   |         1324 |   -0.122435 | 1227.56        |  877.179       |
| cmp_a1_geometric_core                 | official_land_value | random      | mlp     |         1244 |   -3.26703  |    1.04182e+07 |    4.47907e+06 |
| cmp_a1_geometric_core                 | official_land_value | random      | ridge   |         1244 |    0.051209 |    4.91266e+06 |    2.47475e+06 |
| cmp_a1_geometric_core                 | official_land_value | spatial     | mlp     |         1244 |   -2.28792  |    9.14518e+06 |    4.26938e+06 |
| cmp_a1_geometric_core                 | official_land_value | spatial     | ridge   |         1244 |    0.022945 |    4.98529e+06 |    2.51849e+06 |
| cmp_a1_geometric_core                 | total_population    | random      | mlp     |         1372 |   -2.55585  | 6464.24        | 3815.43        |
| cmp_a1_geometric_core                 | total_population    | random      | ridge   |         1372 |   -0.138298 | 3657.41        | 2584.82        |
| cmp_a1_geometric_core                 | total_population    | spatial     | mlp     |         1372 |   -1.73805  | 5672.39        | 3524.24        |
| cmp_a1_geometric_core                 | total_population    | spatial     | ridge   |         1372 |   -0.085647 | 3571.82        | 2559.06        |
| cmp_a1_geometric_core                 | weekday_daytime     | random      | mlp     |         1570 |   -0.976777 | 6709.8         | 3600.55        |
| cmp_a1_geometric_core                 | weekday_daytime     | random      | ridge   |         1570 |    0.190406 | 4294.03        | 2541.1         |
| cmp_a1_geometric_core                 | weekday_daytime     | spatial     | mlp     |         1570 |   -0.55319  | 5947.62        | 3336.47        |
| cmp_a1_geometric_core                 | weekday_daytime     | spatial     | ridge   |         1570 |    0.19424  | 4283.85        | 2523.78        |
| cmp_a1_geometric_core                 | weekday_nighttime   | random      | mlp     |         1565 |   -1.15626  | 5196.71        | 3145.89        |
| cmp_a1_geometric_core                 | weekday_nighttime   | random      | ridge   |         1565 |    0.229858 | 3105.73        | 2114           |
| cmp_a1_geometric_core                 | weekday_nighttime   | spatial     | mlp     |         1565 |   -0.762523 | 4698.35        | 2902.05        |
| cmp_a1_geometric_core                 | weekday_nighttime   | spatial     | ridge   |         1565 |    0.264491 | 3035.1         | 2076.15        |
| cmp_a1_geometric_core                 | weekend_daytime     | random      | mlp     |         1570 |   -1.28342  | 5928.68        | 3241.66        |
| cmp_a1_geometric_core                 | weekend_daytime     | random      | ridge   |         1570 |    0.229685 | 3443.49        | 2233.03        |
| cmp_a1_geometric_core                 | weekend_daytime     | spatial     | mlp     |         1570 |   -0.646046 | 5033.68        | 3060.39        |
| cmp_a1_geometric_core                 | weekend_daytime     | spatial     | ridge   |         1570 |    0.251872 | 3393.54        | 2192.74        |
| cmp_a1_geometric_core                 | weekend_nighttime   | random      | mlp     |         1567 |   -0.985629 | 5121.5         | 3094.99        |
| cmp_a1_geometric_core                 | weekend_nighttime   | random      | ridge   |         1567 |    0.232542 | 3184.02        | 2171.74        |
| cmp_a1_geometric_core                 | weekend_nighttime   | spatial     | mlp     |         1567 |   -0.735967 | 4788.72        | 2981.89        |
| cmp_a1_geometric_core                 | weekend_nighttime   | spatial     | ridge   |         1567 |    0.257386 | 3132.06        | 2143.66        |
| cmp_a1_geometric_core                 | workers             | random      | mlp     |         1442 |   -0.125271 | 4964.71        | 2198.06        |
| cmp_a1_geometric_core                 | workers             | random      | ridge   |         1442 |   -0.007175 | 4696.97        | 2024.76        |
| cmp_a1_geometric_core                 | workers             | spatial     | mlp     |         1442 |   -0.119591 | 4952.16        | 2170.57        |
| cmp_a1_geometric_core                 | workers             | spatial     | ridge   |         1442 |   -0.027608 | 4744.37        | 2029.9         |
| cmp_a2_semantic_enriched              | ecostress_lst       | random      | mlp     |         1600 | -435.7      |   30.5282      |   23.6359      |
| cmp_a2_semantic_enriched              | ecostress_lst       | random      | ridge   |         1600 |    0.405134 |    1.12673     |    0.889085    |
| cmp_a2_semantic_enriched              | ecostress_lst       | spatial     | mlp     |         1600 | -406.301    |   29.4827      |   22.928       |
| cmp_a2_semantic_enriched              | ecostress_lst       | spatial     | ridge   |         1600 |    0.340243 |    1.18659     |    0.93151     |
| cmp_a2_semantic_enriched              | establishments      | random      | mlp     |         1442 |    0.159099 |  607.675       |  288.373       |
| cmp_a2_semantic_enriched              | establishments      | random      | ridge   |         1442 |    0.279002 |  562.686       |  262.41        |
| cmp_a2_semantic_enriched              | establishments      | spatial     | mlp     |         1442 |    0.245975 |  575.429       |  277.6         |
| cmp_a2_semantic_enriched              | establishments      | spatial     | ridge   |         1442 |    0.277671 |  563.205       |  259.688       |
| cmp_a2_semantic_enriched              | households          | random      | mlp     |         1358 |   -1.17827  | 2366.05        | 1378.24        |
| cmp_a2_semantic_enriched              | households          | random      | ridge   |         1358 |   -0.62402  | 2042.98        | 1179.21        |
| cmp_a2_semantic_enriched              | households          | spatial     | mlp     |         1358 |   -1.50571  | 2537.66        | 1385.59        |
| cmp_a2_semantic_enriched              | households          | spatial     | ridge   |         1358 |   -0.607983 | 2032.87        | 1190.23        |
| cmp_a2_semantic_enriched              | housing_units       | random      | mlp     |         1324 |   -1.83906  | 1952.31        | 1080.63        |
| cmp_a2_semantic_enriched              | housing_units       | random      | ridge   |         1324 |   -0.687874 | 1505.33        |  891.837       |
| cmp_a2_semantic_enriched              | housing_units       | spatial     | mlp     |         1324 |   -1.1264   | 1689.6         | 1028.62        |
| cmp_a2_semantic_enriched              | housing_units       | spatial     | ridge   |         1324 |   -0.677694 | 1500.78        |  885.271       |
| cmp_a2_semantic_enriched              | official_land_value | random      | mlp     |         1244 |   -3.83141  |    1.10858e+07 |    4.51165e+06 |
| cmp_a2_semantic_enriched              | official_land_value | random      | ridge   |         1244 |    0.212537 |    4.47555e+06 |    2.27928e+06 |
| cmp_a2_semantic_enriched              | official_land_value | spatial     | mlp     |         1244 |   -2.02919  |    8.77797e+06 |    3.73726e+06 |
| cmp_a2_semantic_enriched              | official_land_value | spatial     | ridge   |         1244 |    0.13977  |    4.67777e+06 |    2.38013e+06 |
| cmp_a2_semantic_enriched              | total_population    | random      | mlp     |         1372 |   -1.84984  | 5787.04        | 3403.32        |
| cmp_a2_semantic_enriched              | total_population    | random      | ridge   |         1372 |   -0.804507 | 4604.95        | 2689.25        |
| cmp_a2_semantic_enriched              | total_population    | spatial     | mlp     |         1372 |   -1.74856  | 5683.27        | 3211.41        |
| cmp_a2_semantic_enriched              | total_population    | spatial     | ridge   |         1372 |   -0.815253 | 4618.64        | 2718.65        |
| cmp_a2_semantic_enriched              | weekday_daytime     | random      | mlp     |         1570 |   -0.43564  | 5718.13        | 3158           |
| cmp_a2_semantic_enriched              | weekday_daytime     | random      | ridge   |         1570 |    0.283194 | 4040.47        | 2352.54        |
| cmp_a2_semantic_enriched              | weekday_daytime     | spatial     | mlp     |         1570 |   -0.638298 | 6108.4         | 3096.73        |
| cmp_a2_semantic_enriched              | weekday_daytime     | spatial     | ridge   |         1570 |    0.283965 | 4038.3         | 2320.16        |
| cmp_a2_semantic_enriched              | weekday_nighttime   | random      | mlp     |         1565 |   -1.08921  | 5115.28        | 2830.91        |
| cmp_a2_semantic_enriched              | weekday_nighttime   | random      | ridge   |         1565 |    0.246779 | 3071.42        | 2002.47        |
| cmp_a2_semantic_enriched              | weekday_nighttime   | spatial     | mlp     |         1565 |   -0.951517 | 4943.84        | 2871.59        |
| cmp_a2_semantic_enriched              | weekday_nighttime   | spatial     | ridge   |         1565 |    0.257182 | 3050.14        | 1983.64        |
| cmp_a2_semantic_enriched              | weekend_daytime     | random      | mlp     |         1570 |   -1.03685  | 5599.44        | 3036.02        |
| cmp_a2_semantic_enriched              | weekend_daytime     | random      | ridge   |         1570 |    0.261791 | 3370.97        | 2104.71        |
| cmp_a2_semantic_enriched              | weekend_daytime     | spatial     | mlp     |         1570 |   -0.388538 | 4623.21        | 2792.06        |
| cmp_a2_semantic_enriched              | weekend_daytime     | spatial     | ridge   |         1570 |    0.263309 | 3367.5         | 2093.82        |
| cmp_a2_semantic_enriched              | weekend_nighttime   | random      | mlp     |         1567 |   -0.646102 | 4663.12        | 2740.25        |
| cmp_a2_semantic_enriched              | weekend_nighttime   | random      | ridge   |         1567 |    0.262457 | 3121.35        | 2025.92        |
| cmp_a2_semantic_enriched              | weekend_nighttime   | spatial     | mlp     |         1567 |   -0.921778 | 5038.48        | 2915.66        |
| cmp_a2_semantic_enriched              | weekend_nighttime   | spatial     | ridge   |         1567 |    0.261631 | 3123.09        | 2016.81        |
| cmp_a2_semantic_enriched              | workers             | random      | mlp     |         1442 |    0.144974 | 4327.68        | 1783.32        |
| cmp_a2_semantic_enriched              | workers             | random      | ridge   |         1442 |    0.20452  | 4174.26        | 1669.21        |
| cmp_a2_semantic_enriched              | workers             | spatial     | mlp     |         1442 |    0.049177 | 4563.68        | 1822.94        |
| cmp_a2_semantic_enriched              | workers             | spatial     | ridge   |         1442 |    0.309177 | 3889.99        | 1618.36        |
| cmp_a3_object_context_enriched        | ecostress_lst       | random      | mlp     |         1600 | -422.041    |   30.047       |   22.9144      |
| cmp_a3_object_context_enriched        | ecostress_lst       | random      | ridge   |         1600 |    0.487882 |    1.04543     |    0.829612    |
| cmp_a3_object_context_enriched        | ecostress_lst       | spatial     | mlp     |         1600 | -391.956    |   28.9589      |   21.9683      |
| cmp_a3_object_context_enriched        | ecostress_lst       | spatial     | ridge   |         1600 |    0.421711 |    1.11092     |    0.880793    |
| cmp_a3_object_context_enriched        | establishments      | random      | mlp     |         1442 |    0.279072 |  562.658       |  261.986       |
| cmp_a3_object_context_enriched        | establishments      | random      | ridge   |         1442 |    0.298336 |  555.09        |  246.389       |
| cmp_a3_object_context_enriched        | establishments      | spatial     | mlp     |         1442 |    0.298741 |  554.93        |  257.452       |
| cmp_a3_object_context_enriched        | establishments      | spatial     | ridge   |         1442 |    0.260806 |  569.742       |  249.77        |
| cmp_a3_object_context_enriched        | households          | random      | mlp     |         1358 |   -0.858671 | 2185.59        | 1279.97        |
| cmp_a3_object_context_enriched        | households          | random      | ridge   |         1358 |   -0.301118 | 1828.63        | 1088.39        |
| cmp_a3_object_context_enriched        | households          | spatial     | mlp     |         1358 |   -0.64269  | 2054.69        | 1240.54        |
| cmp_a3_object_context_enriched        | households          | spatial     | ridge   |         1358 |   -0.4103   | 1903.81        | 1119.77        |
| cmp_a3_object_context_enriched        | housing_units       | random      | mlp     |         1324 |   -0.908668 | 1600.76        |  962.174       |
| cmp_a3_object_context_enriched        | housing_units       | random      | ridge   |         1324 |   -0.374827 | 1358.58        |  830.419       |
| cmp_a3_object_context_enriched        | housing_units       | spatial     | mlp     |         1324 |   -0.988166 | 1633.76        |  988.864       |
| cmp_a3_object_context_enriched        | housing_units       | spatial     | ridge   |         1324 |   -0.434251 | 1387.63        |  842.72        |
| cmp_a3_object_context_enriched        | official_land_value | random      | mlp     |         1244 |   -1.68169  |    8.25915e+06 |    3.63011e+06 |
| cmp_a3_object_context_enriched        | official_land_value | random      | ridge   |         1244 |    0.256739 |    4.34812e+06 |    2.10061e+06 |
| cmp_a3_object_context_enriched        | official_land_value | spatial     | mlp     |         1244 |   -2.11011  |    8.89445e+06 |    3.85878e+06 |
| cmp_a3_object_context_enriched        | official_land_value | spatial     | ridge   |         1244 |    0.141144 |    4.67403e+06 |    2.26327e+06 |
| cmp_a3_object_context_enriched        | total_population    | random      | mlp     |         1372 |   -1.40438  | 5315.54        | 3012.7         |
| cmp_a3_object_context_enriched        | total_population    | random      | ridge   |         1372 |   -0.510612 | 4213.3         | 2503.95        |
| cmp_a3_object_context_enriched        | total_population    | spatial     | mlp     |         1372 |   -0.994622 | 4841.46        | 2914.11        |
| cmp_a3_object_context_enriched        | total_population    | spatial     | ridge   |         1372 |   -0.618635 | 4361.34        | 2556.19        |
| cmp_a3_object_context_enriched        | weekday_daytime     | random      | mlp     |         1570 |   -0.404132 | 5655.03        | 2991.89        |
| cmp_a3_object_context_enriched        | weekday_daytime     | random      | ridge   |         1570 |    0.358295 | 3822.95        | 2212.79        |
| cmp_a3_object_context_enriched        | weekday_daytime     | spatial     | mlp     |         1570 |   -0.257917 | 5352.51        | 2904.84        |
| cmp_a3_object_context_enriched        | weekday_daytime     | spatial     | ridge   |         1570 |    0.319126 | 3937.9         | 2239.82        |
| cmp_a3_object_context_enriched        | weekday_nighttime   | random      | mlp     |         1565 |   -0.291444 | 4021.76        | 2524.95        |
| cmp_a3_object_context_enriched        | weekday_nighttime   | random      | ridge   |         1565 |    0.249007 | 3066.88        | 1948.14        |
| cmp_a3_object_context_enriched        | weekday_nighttime   | spatial     | mlp     |         1565 |   -0.232431 | 3928.8         | 2443.29        |
| cmp_a3_object_context_enriched        | weekday_nighttime   | spatial     | ridge   |         1565 |    0.212834 | 3139.87        | 1987.99        |
| cmp_a3_object_context_enriched        | weekend_daytime     | random      | mlp     |         1570 |   -0.380827 | 4610.36        | 2715.48        |
| cmp_a3_object_context_enriched        | weekend_daytime     | random      | ridge   |         1570 |    0.293353 | 3298.12        | 2029.38        |
| cmp_a3_object_context_enriched        | weekend_daytime     | spatial     | mlp     |         1570 |   -0.576468 | 4926.15        | 2802.35        |
| cmp_a3_object_context_enriched        | weekend_daytime     | spatial     | ridge   |         1570 |    0.267774 | 3357.28        | 2056.75        |
| cmp_a3_object_context_enriched        | weekend_nighttime   | random      | mlp     |         1567 |   -0.467948 | 4403.56        | 2598.55        |
| cmp_a3_object_context_enriched        | weekend_nighttime   | random      | ridge   |         1567 |    0.264322 | 3117.4         | 1989.42        |
| cmp_a3_object_context_enriched        | weekend_nighttime   | spatial     | mlp     |         1567 |   -0.377219 | 4265.3         | 2593.87        |
| cmp_a3_object_context_enriched        | weekend_nighttime   | spatial     | ridge   |         1567 |    0.234107 | 3180.77        | 2021.75        |
| cmp_a3_object_context_enriched        | workers             | random      | mlp     |         1442 |    0.218647 | 4137.03        | 1647.73        |
| cmp_a3_object_context_enriched        | workers             | random      | ridge   |         1442 |    0.333646 | 3820.48        | 1559.08        |
| cmp_a3_object_context_enriched        | workers             | spatial     | mlp     |         1442 |    0.319111 | 3861.92        | 1632.59        |
| cmp_a3_object_context_enriched        | workers             | spatial     | ridge   |         1442 |    0.306626 | 3897.17        | 1554.74        |
| cmp_a4_raster_complete_non_relational | ecostress_lst       | random      | mlp     |         1600 | -388.397    |   28.8274      |   22.8937      |
| cmp_a4_raster_complete_non_relational | ecostress_lst       | random      | ridge   |         1600 |    0.50675  |    1.02599     |    0.811656    |
| cmp_a4_raster_complete_non_relational | ecostress_lst       | spatial     | mlp     |         1600 | -390.427    |   28.9025      |   22.6313      |
| cmp_a4_raster_complete_non_relational | ecostress_lst       | spatial     | ridge   |         1600 |    0.433205 |    1.09982     |    0.864495    |
| cmp_a4_raster_complete_non_relational | establishments      | random      | mlp     |         1442 |   -0.005244 |  664.408       |  280.022       |
| cmp_a4_raster_complete_non_relational | establishments      | random      | ridge   |         1442 |    0.272698 |  565.14        |  256.038       |
| cmp_a4_raster_complete_non_relational | establishments      | spatial     | mlp     |         1442 |    0.169538 |  603.891       |  274.757       |
| cmp_a4_raster_complete_non_relational | establishments      | spatial     | ridge   |         1442 |    0.235825 |  579.289       |  257.538       |
| cmp_a4_raster_complete_non_relational | households          | random      | mlp     |         1358 |   -0.809082 | 2156.24        | 1241.35        |
| cmp_a4_raster_complete_non_relational | households          | random      | ridge   |         1358 |   -0.438523 | 1922.77        | 1140.69        |
| cmp_a4_raster_complete_non_relational | households          | spatial     | mlp     |         1358 |   -0.497474 | 1961.77        | 1193.09        |
| cmp_a4_raster_complete_non_relational | households          | spatial     | ridge   |         1358 |   -0.53157  | 1983.98        | 1162.02        |
| cmp_a4_raster_complete_non_relational | housing_units       | random      | mlp     |         1324 |   -0.851278 | 1576.51        |  923.883       |
| cmp_a4_raster_complete_non_relational | housing_units       | random      | ridge   |         1324 |   -0.637016 | 1482.48        |  850.764       |
| cmp_a4_raster_complete_non_relational | housing_units       | spatial     | mlp     |         1324 |   -1.11873  | 1686.55        |  964.909       |
| cmp_a4_raster_complete_non_relational | housing_units       | spatial     | ridge   |         1324 |   -0.821152 | 1563.63        |  868.285       |
| cmp_a4_raster_complete_non_relational | official_land_value | random      | mlp     |         1244 |   -1.99993  |    8.73548e+06 |    3.73259e+06 |
| cmp_a4_raster_complete_non_relational | official_land_value | random      | ridge   |         1244 |    0.283919 |    4.26788e+06 |    2.04053e+06 |
| cmp_a4_raster_complete_non_relational | official_land_value | spatial     | mlp     |         1244 |   -1.50105  |    7.97614e+06 |    3.54125e+06 |
| cmp_a4_raster_complete_non_relational | official_land_value | spatial     | ridge   |         1244 |    0.193327 |    4.52981e+06 |    2.19404e+06 |
| cmp_a4_raster_complete_non_relational | total_population    | random      | mlp     |         1372 |   -1.44911  | 5364.76        | 2986.15        |
| cmp_a4_raster_complete_non_relational | total_population    | random      | ridge   |         1372 |   -0.731446 | 4510.77        | 2592.81        |
| cmp_a4_raster_complete_non_relational | total_population    | spatial     | mlp     |         1372 |   -1.56998  | 5495.54        | 2873.63        |
| cmp_a4_raster_complete_non_relational | total_population    | spatial     | ridge   |         1372 |   -0.858822 | 4673.74        | 2641.27        |
| cmp_a4_raster_complete_non_relational | weekday_daytime     | random      | mlp     |         1570 |   -0.161538 | 5143.37        | 2855.31        |
| cmp_a4_raster_complete_non_relational | weekday_daytime     | random      | ridge   |         1570 |    0.195272 | 4281.1         | 2376.42        |
| cmp_a4_raster_complete_non_relational | weekday_daytime     | spatial     | mlp     |         1570 |   -0.065549 | 4926.26        | 2828.34        |
| cmp_a4_raster_complete_non_relational | weekday_daytime     | spatial     | ridge   |         1570 |    0.160438 | 4372.78        | 2429.38        |
| cmp_a4_raster_complete_non_relational | weekday_nighttime   | random      | mlp     |         1565 |   -0.571419 | 4436.34        | 2503.21        |
| cmp_a4_raster_complete_non_relational | weekday_nighttime   | random      | ridge   |         1565 |    0.112788 | 3333.43        | 2052.53        |
| cmp_a4_raster_complete_non_relational | weekday_nighttime   | spatial     | mlp     |         1565 |   -0.226651 | 3919.57        | 2397.92        |
| cmp_a4_raster_complete_non_relational | weekday_nighttime   | spatial     | ridge   |         1565 |    0.080749 | 3393.09        | 2110.87        |
| cmp_a4_raster_complete_non_relational | weekend_daytime     | random      | mlp     |         1570 |   -0.252783 | 4391.4         | 2541.9         |
| cmp_a4_raster_complete_non_relational | weekend_daytime     | random      | ridge   |         1570 |    0.129711 | 3660.13        | 2168.15        |
| cmp_a4_raster_complete_non_relational | weekend_daytime     | spatial     | mlp     |         1570 |   -0.428597 | 4689.43        | 2784.79        |
| cmp_a4_raster_complete_non_relational | weekend_daytime     | spatial     | ridge   |         1570 |    0.097398 | 3727.46        | 2220.86        |
| cmp_a4_raster_complete_non_relational | weekend_nighttime   | random      | mlp     |         1567 |   -0.31768  | 4172.09        | 2402.12        |
| cmp_a4_raster_complete_non_relational | weekend_nighttime   | random      | ridge   |         1567 |    0.105179 | 3438.08        | 2098.16        |
| cmp_a4_raster_complete_non_relational | weekend_nighttime   | spatial     | mlp     |         1567 |   -0.333516 | 4197.08        | 2509.37        |
| cmp_a4_raster_complete_non_relational | weekend_nighttime   | spatial     | ridge   |         1567 |    0.070313 | 3504.42        | 2159.09        |
| cmp_a4_raster_complete_non_relational | workers             | random      | mlp     |         1442 |    0.273584 | 3988.94        | 1597.62        |
| cmp_a4_raster_complete_non_relational | workers             | random      | ridge   |         1442 |    0.260853 | 4023.75        | 1547.51        |
| cmp_a4_raster_complete_non_relational | workers             | spatial     | mlp     |         1442 |    0.252746 | 4045.75        | 1679.02        |
| cmp_a4_raster_complete_non_relational | workers             | spatial     | ridge   |         1442 |    0.230411 | 4105.77        | 1575.73        |
| cmp_a5_relation_type_agnostic         | ecostress_lst       | random      | mlp     |         1600 | -358.223    |   27.688       |   22.0084      |
| cmp_a5_relation_type_agnostic         | ecostress_lst       | random      | ridge   |         1600 |    0.522213 |    1.00978     |    0.79622     |
| cmp_a5_relation_type_agnostic         | ecostress_lst       | spatial     | mlp     |         1600 | -364.239    |   27.9189      |   21.8791      |
| cmp_a5_relation_type_agnostic         | ecostress_lst       | spatial     | ridge   |         1600 |    0.441067 |    1.09217     |    0.859805    |
| cmp_a5_relation_type_agnostic         | establishments      | random      | mlp     |         1442 |    0.186835 |  597.569       |  256.149       |
| cmp_a5_relation_type_agnostic         | establishments      | random      | ridge   |         1442 |    0.192219 |  595.588       |  272.57        |
| cmp_a5_relation_type_agnostic         | establishments      | spatial     | mlp     |         1442 |    0.052704 |  644.973       |  253.674       |
| cmp_a5_relation_type_agnostic         | establishments      | spatial     | ridge   |         1442 |    0.157547 |  608.235       |  276.619       |
| cmp_a5_relation_type_agnostic         | households          | random      | mlp     |         1358 |   -0.43712  | 1921.83        | 1170.78        |
| cmp_a5_relation_type_agnostic         | households          | random      | ridge   |         1358 |   -0.464016 | 1939.73        | 1142.85        |
| cmp_a5_relation_type_agnostic         | households          | spatial     | mlp     |         1358 |   -0.426749 | 1914.88        | 1121.33        |
| cmp_a5_relation_type_agnostic         | households          | spatial     | ridge   |         1358 |   -0.502606 | 1965.13        | 1170.92        |
| cmp_a5_relation_type_agnostic         | housing_units       | random      | mlp     |         1324 |   -0.751694 | 1533.52        |  884.683       |
| cmp_a5_relation_type_agnostic         | housing_units       | random      | ridge   |         1324 |   -0.60921  | 1469.83        |  854.579       |
| cmp_a5_relation_type_agnostic         | housing_units       | spatial     | mlp     |         1324 |   -0.39057  | 1366.34        |  844.171       |
| cmp_a5_relation_type_agnostic         | housing_units       | spatial     | ridge   |         1324 |   -0.615001 | 1472.47        |  870.642       |
| cmp_a5_relation_type_agnostic         | official_land_value | random      | mlp     |         1244 |   -2.17525  |    8.98711e+06 |    3.54286e+06 |
| cmp_a5_relation_type_agnostic         | official_land_value | random      | ridge   |         1244 |    0.298914 |    4.22296e+06 |    2.01683e+06 |
| cmp_a5_relation_type_agnostic         | official_land_value | spatial     | mlp     |         1244 |   -1.71707  |    8.31345e+06 |    3.55782e+06 |
| cmp_a5_relation_type_agnostic         | official_land_value | spatial     | ridge   |         1244 |    0.205979 |    4.49415e+06 |    2.16072e+06 |
| cmp_a5_relation_type_agnostic         | total_population    | random      | mlp     |         1372 |   -1.42057  | 5333.4         | 2858.45        |
| cmp_a5_relation_type_agnostic         | total_population    | random      | ridge   |         1372 |   -0.865467 | 4682.09        | 2656.68        |
| cmp_a5_relation_type_agnostic         | total_population    | spatial     | mlp     |         1372 |   -0.664314 | 4422.46        | 2653.35        |
| cmp_a5_relation_type_agnostic         | total_population    | spatial     | ridge   |         1372 |   -0.867615 | 4684.78        | 2698.71        |
| cmp_a5_relation_type_agnostic         | weekday_daytime     | random      | mlp     |         1570 |   -0.278148 | 5395.38        | 2918.95        |
| cmp_a5_relation_type_agnostic         | weekday_daytime     | random      | ridge   |         1570 |    0.235675 | 4172.25        | 2444.56        |
| cmp_a5_relation_type_agnostic         | weekday_daytime     | spatial     | mlp     |         1570 |    0.115912 | 4487.23        | 2644.44        |
| cmp_a5_relation_type_agnostic         | weekday_daytime     | spatial     | ridge   |         1570 |    0.188534 | 4298.99        | 2484.04        |
| cmp_a5_relation_type_agnostic         | weekday_nighttime   | random      | mlp     |         1565 |   -0.295874 | 4028.65        | 2416.41        |
| cmp_a5_relation_type_agnostic         | weekday_nighttime   | random      | ridge   |         1565 |    0.065671 | 3420.8         | 2144.7         |
| cmp_a5_relation_type_agnostic         | weekday_nighttime   | spatial     | mlp     |         1565 |   -0.285441 | 4012.4         | 2402.07        |
| cmp_a5_relation_type_agnostic         | weekday_nighttime   | spatial     | ridge   |         1565 |    0.026149 | 3492.41        | 2162.6         |
| cmp_a5_relation_type_agnostic         | weekend_daytime     | random      | mlp     |         1570 |   -0.463951 | 4747.1         | 2732.01        |
| cmp_a5_relation_type_agnostic         | weekend_daytime     | random      | ridge   |         1570 |    0.148152 | 3621.15        | 2232.24        |
| cmp_a5_relation_type_agnostic         | weekend_daytime     | spatial     | mlp     |         1570 |   -0.187561 | 4275.56        | 2624.39        |
| cmp_a5_relation_type_agnostic         | weekend_daytime     | spatial     | ridge   |         1570 |    0.115432 | 3690.04        | 2253.94        |
| cmp_a5_relation_type_agnostic         | weekend_nighttime   | random      | mlp     |         1567 |   -0.297773 | 4140.45        | 2490.52        |
| cmp_a5_relation_type_agnostic         | weekend_nighttime   | random      | ridge   |         1567 |    0.058315 | 3526.97        | 2189.21        |
| cmp_a5_relation_type_agnostic         | weekend_nighttime   | spatial     | mlp     |         1567 |   -0.33418  | 4198.13        | 2497.47        |
| cmp_a5_relation_type_agnostic         | weekend_nighttime   | spatial     | ridge   |         1567 |    0.024448 | 3589.83        | 2205.75        |
| cmp_a5_relation_type_agnostic         | workers             | random      | mlp     |         1442 |    0.043114 | 4578.2         | 1665.49        |
| cmp_a5_relation_type_agnostic         | workers             | random      | ridge   |         1442 |    0.33693  | 3811.05        | 1606.57        |
| cmp_a5_relation_type_agnostic         | workers             | spatial     | mlp     |         1442 |    0.120383 | 4389.47        | 1682.33        |
| cmp_a5_relation_type_agnostic         | workers             | spatial     | ridge   |         1442 |    0.291931 | 3938.25        | 1643.67        |
| cmp_ds_like                           | ecostress_lst       | random      | mlp     |         1600 | -231.139    |   22.2579      |   17.2685      |
| cmp_ds_like                           | ecostress_lst       | random      | ridge   |         1600 |    0.529557 |    1.00199     |    0.791177    |
| cmp_ds_like                           | ecostress_lst       | spatial     | mlp     |         1600 | -255.881    |   23.414       |   17.4093      |
| cmp_ds_like                           | ecostress_lst       | spatial     | ridge   |         1600 |    0.435031 |    1.09805     |    0.866187    |
| cmp_ds_like                           | establishments      | random      | mlp     |         1442 |    0.278847 |  562.746       |  243.479       |
| cmp_ds_like                           | establishments      | random      | ridge   |         1442 |    0.168781 |  604.166       |  267.654       |
| cmp_ds_like                           | establishments      | spatial     | mlp     |         1442 |    0.326836 |  543.7         |  244.243       |
| cmp_ds_like                           | establishments      | spatial     | ridge   |         1442 |    0.121443 |  621.132       |  275.441       |
| cmp_ds_like                           | households          | random      | mlp     |         1358 |    0.08864  | 1530.43        |  962.679       |
| cmp_ds_like                           | households          | random      | ridge   |         1358 |   -0.479768 | 1950.14        | 1157.68        |
| cmp_ds_like                           | households          | spatial     | mlp     |         1358 |    0.029104 | 1579.63        |  978.325       |
| cmp_ds_like                           | households          | spatial     | ridge   |         1358 |   -0.60541  | 2031.24        | 1193.7         |
| cmp_ds_like                           | housing_units       | random      | mlp     |         1324 |    0.01569  | 1149.55        |  748.039       |
| cmp_ds_like                           | housing_units       | random      | ridge   |         1324 |   -0.772957 | 1542.8         |  866.457       |
| cmp_ds_like                           | housing_units       | spatial     | mlp     |         1324 |    0.07891  | 1112.02        |  744.068       |
| cmp_ds_like                           | housing_units       | spatial     | ridge   |         1324 |   -0.79542  | 1552.55        |  885.043       |
| cmp_ds_like                           | official_land_value | random      | mlp     |         1244 |    0.04471  |    4.92945e+06 |    2.60141e+06 |
| cmp_ds_like                           | official_land_value | random      | ridge   |         1244 |    0.248143 |    4.3732e+06  |    2.14085e+06 |
| cmp_ds_like                           | official_land_value | spatial     | mlp     |         1244 |   -0.057932 |    5.18752e+06 |    2.745e+06   |
| cmp_ds_like                           | official_land_value | spatial     | ridge   |         1244 |    0.114788 |    4.7452e+06  |    2.33427e+06 |
| cmp_ds_like                           | total_population    | random      | mlp     |         1372 |   -0.177398 | 3719.7         | 2277.87        |
| cmp_ds_like                           | total_population    | random      | ridge   |         1372 |   -0.709127 | 4481.6         | 2632.57        |
| cmp_ds_like                           | total_population    | spatial     | mlp     |         1372 |    0.040296 | 3358.26        | 2249.51        |
| cmp_ds_like                           | total_population    | spatial     | ridge   |         1372 |   -0.867914 | 4685.16        | 2718.83        |
| cmp_ds_like                           | weekday_daytime     | random      | mlp     |         1570 |    0.255753 | 4117.08        | 2416.45        |
| cmp_ds_like                           | weekday_daytime     | random      | ridge   |         1570 |    0.093166 | 4544.59        | 2563.12        |
| cmp_ds_like                           | weekday_daytime     | spatial     | mlp     |         1570 |    0.242242 | 4154.28        | 2498.81        |
| cmp_ds_like                           | weekday_daytime     | spatial     | ridge   |         1570 |   -0.082039 | 4964.24        | 2706.48        |
| cmp_ds_like                           | weekday_nighttime   | random      | mlp     |         1565 |    0.015553 | 3511.35        | 2145.84        |
| cmp_ds_like                           | weekday_nighttime   | random      | ridge   |         1565 |   -0.151925 | 3798.31        | 2309.37        |
| cmp_ds_like                           | weekday_nighttime   | spatial     | mlp     |         1565 |   -0.068986 | 3659.02        | 2306.86        |
| cmp_ds_like                           | weekday_nighttime   | spatial     | ridge   |         1565 |   -0.28779  | 4016.07        | 2424.58        |
| cmp_ds_like                           | weekend_daytime     | random      | mlp     |         1570 |    0.114768 | 3691.42        | 2256.91        |
| cmp_ds_like                           | weekend_daytime     | random      | ridge   |         1570 |   -0.022676 | 3967.66        | 2397.08        |
| cmp_ds_like                           | weekend_daytime     | spatial     | mlp     |         1570 |   -0.197413 | 4293.26        | 2535.48        |
| cmp_ds_like                           | weekend_daytime     | spatial     | ridge   |         1570 |   -0.144731 | 4197.75        | 2518.61        |
| cmp_ds_like                           | weekend_nighttime   | random      | mlp     |         1567 |   -0.058084 | 3738.59        | 2317.87        |
| cmp_ds_like                           | weekend_nighttime   | random      | ridge   |         1567 |   -0.124249 | 3853.71        | 2354.41        |
| cmp_ds_like                           | weekend_nighttime   | spatial     | mlp     |         1567 |   -0.070533 | 3760.52        | 2348.62        |
| cmp_ds_like                           | weekend_nighttime   | spatial     | ridge   |         1567 |   -0.232431 | 4034.87        | 2463.34        |
| cmp_ds_like                           | workers             | random      | mlp     |         1442 |    0.348885 | 3776.54        | 1532.11        |
| cmp_ds_like                           | workers             | random      | ridge   |         1442 |    0.162639 | 4282.74        | 1640.31        |
| cmp_ds_like                           | workers             | spatial     | mlp     |         1442 |    0.399624 | 3626.41        | 1546.41        |
| cmp_ds_like                           | workers             | spatial     | ridge   |         1442 |    0.033063 | 4602.19        | 1723.89        |
| cmp_ssv_like                          | ecostress_lst       | random      | mlp     |         1600 | -428.72     |   30.2833      |   23.4402      |
| cmp_ssv_like                          | ecostress_lst       | random      | ridge   |         1600 |    0.39497  |    1.13631     |    0.900755    |
| cmp_ssv_like                          | ecostress_lst       | spatial     | mlp     |         1600 | -392.552    |   28.9808      |   22.7679      |
| cmp_ssv_like                          | ecostress_lst       | spatial     | ridge   |         1600 |    0.323384 |    1.20166     |    0.949936    |
| cmp_ssv_like                          | establishments      | random      | mlp     |         1442 |    0.111717 |  624.56        |  292.694       |
| cmp_ssv_like                          | establishments      | random      | ridge   |         1442 |    0.169921 |  603.752       |  281.207       |
| cmp_ssv_like                          | establishments      | spatial     | mlp     |         1442 |    0.308269 |  551.147       |  279.237       |
| cmp_ssv_like                          | establishments      | spatial     | ridge   |         1442 |    0.121746 |  621.025       |  284.474       |
| cmp_ssv_like                          | households          | random      | mlp     |         1358 |   -0.925217 | 2224.38        | 1358.14        |
| cmp_ssv_like                          | households          | random      | ridge   |         1358 |   -0.442956 | 1925.73        | 1174.68        |
| cmp_ssv_like                          | households          | spatial     | mlp     |         1358 |   -1.00211  | 2268.36        | 1375.06        |
| cmp_ssv_like                          | households          | spatial     | ridge   |         1358 |   -0.500163 | 1963.53        | 1202.19        |
| cmp_ssv_like                          | housing_units       | random      | mlp     |         1324 |   -1.16509  | 1704.9         | 1049.35        |
| cmp_ssv_like                          | housing_units       | random      | ridge   |         1324 |   -0.878311 | 1587.98        |  918.036       |
| cmp_ssv_like                          | housing_units       | spatial     | mlp     |         1324 |   -0.93292  | 1610.9         |  993.973       |
| cmp_ssv_like                          | housing_units       | spatial     | ridge   |         1324 |   -0.851743 | 1576.71        |  921.612       |
| cmp_ssv_like                          | official_land_value | random      | mlp     |         1244 |   -3.03014  |    1.01249e+07 |    4.14301e+06 |
| cmp_ssv_like                          | official_land_value | random      | ridge   |         1244 |    0.158745 |    4.62589e+06 |    2.30987e+06 |
| cmp_ssv_like                          | official_land_value | spatial     | mlp     |         1244 |   -2.47233  |    9.39814e+06 |    3.9157e+06  |
| cmp_ssv_like                          | official_land_value | spatial     | ridge   |         1244 |    0.096888 |    4.79294e+06 |    2.40544e+06 |
| cmp_ssv_like                          | total_population    | random      | mlp     |         1372 |   -1.68467  | 5616.83        | 3229           |
| cmp_ssv_like                          | total_population    | random      | ridge   |         1372 |   -0.808731 | 4610.34        | 2748.57        |
| cmp_ssv_like                          | total_population    | spatial     | mlp     |         1372 |   -1.0183   | 4870.11        | 2994.6         |
| cmp_ssv_like                          | total_population    | spatial     | ridge   |         1372 |   -0.863315 | 4679.39        | 2804.74        |
| cmp_ssv_like                          | weekday_daytime     | random      | mlp     |         1570 |   -0.294514 | 5429.81        | 3072.44        |
| cmp_ssv_like                          | weekday_daytime     | random      | ridge   |         1570 |    0.25891  | 4108.34        | 2408.27        |
| cmp_ssv_like                          | weekday_daytime     | spatial     | mlp     |         1570 |   -0.388495 | 5623.45        | 3098.6         |
| cmp_ssv_like                          | weekday_daytime     | spatial     | ridge   |         1570 |    0.241639 | 4155.94        | 2430.17        |
| cmp_ssv_like                          | weekday_nighttime   | random      | mlp     |         1565 |   -0.297812 | 4031.66        | 2554.21        |
| cmp_ssv_like                          | weekday_nighttime   | random      | ridge   |         1565 |    0.207817 | 3149.86        | 2036.57        |
| cmp_ssv_like                          | weekday_nighttime   | spatial     | mlp     |         1565 |   -0.753334 | 4686.09        | 2755.93        |
| cmp_ssv_like                          | weekday_nighttime   | spatial     | ridge   |         1565 |    0.198693 | 3167.95        | 2059.25        |
| cmp_ssv_like                          | weekend_daytime     | random      | mlp     |         1570 |   -0.380147 | 4609.22        | 2787.47        |
| cmp_ssv_like                          | weekend_daytime     | random      | ridge   |         1570 |    0.232389 | 3437.44        | 2151.44        |
| cmp_ssv_like                          | weekend_daytime     | spatial     | mlp     |         1570 |   -0.484177 | 4779.78        | 2949.76        |
| cmp_ssv_like                          | weekend_daytime     | spatial     | ridge   |         1570 |    0.222782 | 3458.89        | 2168.81        |
| cmp_ssv_like                          | weekend_nighttime   | random      | mlp     |         1567 |   -0.461523 | 4393.91        | 2708.28        |
| cmp_ssv_like                          | weekend_nighttime   | random      | ridge   |         1567 |    0.215336 | 3219.51        | 2073.18        |
| cmp_ssv_like                          | weekend_nighttime   | spatial     | mlp     |         1567 |   -0.395459 | 4293.45        | 2635.82        |
| cmp_ssv_like                          | weekend_nighttime   | spatial     | ridge   |         1567 |    0.204047 | 3242.59        | 2092.31        |
| cmp_ssv_like                          | workers             | random      | mlp     |         1442 |   -0.552836 | 5832.14        | 1947.23        |
| cmp_ssv_like                          | workers             | random      | ridge   |         1442 |    0.273645 | 3988.77        | 1696.2         |
| cmp_ssv_like                          | workers             | spatial     | mlp     |         1442 |    0.111274 | 4412.14        | 1827.64        |
| cmp_ssv_like                          | workers             | spatial     | ridge   |         1442 |    0.211829 | 4155.04        | 1722.37        |

## Leakage and determinism gates

- Outer-test predictors and targets never enter standardization, inner validation, training, or early stopping: PASS.
- Random folds use no target values and are shared across models/probes: PASS.
- Target populations are identical across all eight models and four cells: PASS.
- Target transformations, eligibility, spatial folds, embeddings, ridge lambda, and MLP contract are unchanged: PASS.
- Same-GPU post-run reproduction and cross-GPU prediction equality: PASS.
- Metric recomputation from OOF artifacts: PASS.
- P11-E mutation and P9 model reselection: 0/0.

## Prohibited work accounting

| Activity | Count |
|---|---:|
| Encoder fine-tuning | 0 |
| New embedding inference | 0 |
| Target rematerialization/eligibility change | 0 |
| Accepted spatial-fold redesign | 0 |
| Ridge lambda tuning | 0 |
| MLP architecture/hyperparameter search | 0 |
| Target-transform change | 0 |
| P9/P10 rerun or checkpoint reselection | 0 |
| Model reselection | 0 |
| Dissertation mutation | 0 |

## Warnings and interpretation boundary

The fixed MLP produces severe negative R2 for several model-target pairs, most visibly Kelvin LST. These are finite, reproducible diagnostic outcomes and were not repaired by target standardization, LR changes, clipping, or retuning because all are prohibited. This work does not define an overall model winner and does not modify P11-E or any P11-F acceptance.

## Next work unit

`P11_F_FINAL_DOWNSTREAM_COMPARISON_AND_ACCEPTANCE`
