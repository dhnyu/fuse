# Gwanak Geo2Vec Strict XGBoost Validation Report

Generated: `2026-06-08 03:07:50 KST`

## Summary

- Workers used: `8`; xgboost `nthread`: `3`
- Total validation elapsed seconds: `40.65`
- GPU xgboost available: `FALSE`; method: `cpu_fallback`
- Dong holdout available: `TRUE`
- Single model beats chunked on random split targets: `5 / 5`
- Single model beats chunked on spatial block CV targets: `5 / 5`

## GPU Check

```json
{
  "succeeded": false,
  "method": "cpu_fallback",
  "params": {
    "objective": "reg:squarederror",
    "eval_metric": "rmse",
    "tree_method": "hist"
  },
  "error": "No tested xgboost GPU mode succeeded."
}
```

If GPU setup failed, validation continued with CPU xgboost. The GPU check is intentionally non-fatal.

## Target Definitions

- `log_area = log1p(st_area(geometry))`
- `log_perimeter = log1p(st_length(st_boundary(geometry)))`
- `compactness = 4*pi*area/perimeter^2`
- `elongation = max(bbox_width, bbox_height) / min(bbox_width, bbox_height)`
- `bbox_area_ratio = area / (bbox_width*bbox_height)`

## Resampling Design

- Random split baseline: deterministic 80/20 building split.
- Spatial block CV: deterministic 500 m centroid grid blocks greedily assigned to 5 balanced folds.
- Administrative dong holdout: building point-on-surface joined to dong polygons, dongs greedily assigned to 5 balanced folds.

Fold assignments were saved to `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_xgboost_spatial_fold_assignments.parquet` and reused for both embeddings.

## Mean R2 By Target And Resampling

Key: <target, resampling>
Index: <resampling>
             target       resampling   chunked_64d single_model_32d
             <char>           <char>         <num>            <num>
 1: bbox_area_ratio     dong_holdout  0.2548767771       0.73099231
 2: bbox_area_ratio     random_split  0.3017711447       0.73802075
 3: bbox_area_ratio spatial_block_cv  0.2751903021       0.73261552
 4:     compactness     dong_holdout  0.1999692375       0.61148323
 5:     compactness     random_split  0.2178585765       0.60387505
 6:     compactness spatial_block_cv  0.2143131029       0.61335895
 7:      elongation     dong_holdout  0.3426572525       0.74501421
 8:      elongation     random_split  0.3675119379       0.75362695
 9:      elongation spatial_block_cv  0.3592279412       0.74744235
10:        log_area     dong_holdout -0.0316249328       0.06737715
11:        log_area     random_split  0.0099091574       0.10443683
12:        log_area spatial_block_cv  0.0004922768       0.08949191
13:   log_perimeter     dong_holdout -0.0128406497       0.14280584
14:   log_perimeter     random_split  0.0201372346       0.16906533
15:   log_perimeter spatial_block_cv  0.0111507067       0.15919840
    single_minus_chunked_r2
                      <num>
 1:              0.47611553
 2:              0.43624960
 3:              0.45742522
 4:              0.41151400
 5:              0.38601648
 6:              0.39904585
 7:              0.40235695
 8:              0.38611501
 9:              0.38821441
10:              0.09900208
11:              0.09452767
12:              0.08899963
13:              0.15564649
14:              0.14892810
15:              0.14804769

## Random Split To Spatial CV Drop

Key: <embedding_name, target>
      embedding_name          target   random_r2   spatial_r2
              <char>          <char>       <num>        <num>
 1:      chunked_64d bbox_area_ratio 0.301771145 0.2751903021
 2:      chunked_64d     compactness 0.217858577 0.2143131029
 3:      chunked_64d      elongation 0.367511938 0.3592279412
 4:      chunked_64d        log_area 0.009909157 0.0004922768
 5:      chunked_64d   log_perimeter 0.020137235 0.0111507067
 6: single_model_32d bbox_area_ratio 0.738020746 0.7326155236
 7: single_model_32d     compactness 0.603875054 0.6133589509
 8: single_model_32d      elongation 0.753626947 0.7474423474
 9: single_model_32d        log_area 0.104436827 0.0894919065
10: single_model_32d   log_perimeter 0.169065330 0.1591983958
    r2_drop_random_to_spatial
                        <num>
 1:               0.026580843
 2:               0.003545474
 3:               0.008283997
 4:               0.009416881
 5:               0.008986528
 6:               0.005405223
 7:              -0.009483897
 8:               0.006184600
 9:               0.014944921
10:               0.009866935

## Full Summary Table

Summary CSV: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_xgboost_strict_validation_summary.csv`

      embedding_name          target       resampling       mean_r2       sd_r2
              <char>          <char>           <char>         <num>       <num>
 1: single_model_32d        log_area     random_split  0.1044368275          NA
 2: single_model_32d        log_area spatial_block_cv  0.0894919065 0.034312231
 3: single_model_32d        log_area     dong_holdout  0.0673771463 0.082425530
 4: single_model_32d   log_perimeter     random_split  0.1690653304          NA
 5: single_model_32d   log_perimeter spatial_block_cv  0.1591983958 0.044694300
 6: single_model_32d   log_perimeter     dong_holdout  0.1428058448 0.082607276
 7: single_model_32d     compactness     random_split  0.6038750536          NA
 8: single_model_32d     compactness spatial_block_cv  0.6133589509 0.019922393
 9: single_model_32d     compactness     dong_holdout  0.6114832327 0.027811300
10: single_model_32d      elongation     random_split  0.7536269474          NA
11: single_model_32d      elongation spatial_block_cv  0.7474423474 0.022887222
12: single_model_32d      elongation     dong_holdout  0.7450142061 0.025264266
13: single_model_32d bbox_area_ratio     random_split  0.7380207462          NA
14: single_model_32d bbox_area_ratio spatial_block_cv  0.7326155236 0.019492514
15: single_model_32d bbox_area_ratio     dong_holdout  0.7309923099 0.022848402
16:      chunked_64d        log_area     random_split  0.0099091574          NA
17:      chunked_64d        log_area spatial_block_cv  0.0004922768 0.008746524
18:      chunked_64d        log_area     dong_holdout -0.0316249328 0.044064989
19:      chunked_64d   log_perimeter     random_split  0.0201372346          NA
20:      chunked_64d   log_perimeter spatial_block_cv  0.0111507067 0.011184247
21:      chunked_64d   log_perimeter     dong_holdout -0.0128406497 0.034182998
22:      chunked_64d     compactness     random_split  0.2178585765          NA
23:      chunked_64d     compactness spatial_block_cv  0.2143131029 0.016965890
24:      chunked_64d     compactness     dong_holdout  0.1999692375 0.017499793
25:      chunked_64d      elongation     random_split  0.3675119379          NA
26:      chunked_64d      elongation spatial_block_cv  0.3592279412 0.044835473
27:      chunked_64d      elongation     dong_holdout  0.3426572525 0.058477666
28:      chunked_64d bbox_area_ratio     random_split  0.3017711447          NA
29:      chunked_64d bbox_area_ratio spatial_block_cv  0.2751903021 0.027667045
30:      chunked_64d bbox_area_ratio     dong_holdout  0.2548767771 0.074929468
      embedding_name          target       resampling       mean_r2       sd_r2
     mean_rmse   mean_mae mean_elapsed_seconds folds
         <num>      <num>                <num> <int>
 1: 0.87108122 0.56743869            0.4186091     1
 2: 0.87423671 0.56727232            0.6264493     5
 3: 0.87832958 0.57405197            0.8640102     5
 4: 0.47249844 0.29593900            1.2502418     1
 5: 0.47568001 0.29617383            1.0343100     5
 6: 0.47743669 0.29903457            0.7349299     5
 7: 0.05788915 0.04122972            1.1053684     1
 8: 0.05695267 0.04072470            0.8514888     5
 9: 0.05708233 0.04077103            0.9935990     5
10: 0.19967317 0.10000483            1.3632667     1
11: 0.18843202 0.10209431            0.9832870     5
12: 0.18922152 0.10301371            0.5478206     5
13: 0.07098839 0.05129701            0.8515327     1
14: 0.07157654 0.05171190            1.2800988     5
15: 0.07164498 0.05184911            0.8877920     5
16: 0.91590000 0.56979898            0.7435720     1
17: 0.91614119 0.57364695            1.0528304     5
18: 0.92410815 0.58307831            0.6865906     5
19: 0.51309711 0.30122432            0.5357449     1
20: 0.51633168 0.30391282            1.1398633     5
21: 0.51954070 0.30705765            1.1247850     5
22: 0.08134366 0.05676002            0.9367135     1
23: 0.08125158 0.05707517            0.9933119     5
24: 0.08205741 0.05761183            2.0546034     5
25: 0.31992582 0.16896704            0.8351557     1
26: 0.30024239 0.16981292            0.6888413     5
27: 0.30413546 0.17235400            1.3458503     5
28: 0.11589181 0.09021865            2.1338656     1
29: 0.11798651 0.09235963            1.3681806     5
30: 0.11937296 0.09387448            0.7646493     5
     mean_rmse   mean_mae mean_elapsed_seconds folds

## Answers

1. Random split: single-model outperformed chunked on `5` of `5` targets by mean R2.
2. Spatial block CV: single-model outperformed chunked on `5` of `5` targets by mean R2.
3. Performance generally drops from random split to spatial CV when embeddings exploit local morphology/spatial autocorrelation; see the drop table above.
4. The random-split result should be treated as optimistic if spatial CV R2 is materially lower.
5. Consistency across geometry targets should be judged target-by-target; area/perimeter are often harder than compactness/elongation-style shape metrics.
6. This xgboost validation directly tests whether the earlier random-forest finding holds under stricter folds.
7. GPU xgboost availability: `FALSE`; fallback/method: `cpu_fallback`.
8. The default Gwanak building shape embedding should be the single global model if it remains stronger under spatial CV, because it has one shared latent space.
9. For Seoul/Korea, prefer single-model staged feasibility tests where possible; if chunking is needed, use anchor alignment before treating vectors as comparable.

## Outputs

- Results parquet: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_xgboost_strict_validation_results.parquet`
- Summary CSV: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_xgboost_strict_validation_summary.csv`
- Fold assignments: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_xgboost_spatial_fold_assignments.parquet`
- Residuals parquet: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_xgboost_residuals.parquet`
- GPU check JSON: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_geo2vec_xgboost_gpu_check.json`
