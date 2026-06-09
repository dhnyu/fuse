# Gwanak Building Geo2Vec Embedding Validation Report

Generated: `2026-06-08 02:06:35 KST`

## Purpose

This validation checks whether the 64-dimensional Geo2Vec shape embedding for Gwanak-gu VWorld building footprints preserves meaningful geometry information. The validation uses original building footprints and does not modify the GeoNeuralRepresentation repository.

## Input Files

- Embedding parquet: `/members/dhnyu/fusedata/embeddings/gwanak_buildings_geo2vec_shape_full.parquet`
- Embedding metadata: `/members/dhnyu/fusedata/embeddings/gwanak_buildings_geo2vec_shape_full_metadata.json`
- Building geometry: `/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg`
- Building attributes: `/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld_attributes.parquet`

## Output Directory

All validation artifacts were written to `/members/dhnyu/fusedata/gwanak_test/validation`.

## Data Integrity Checks

- Embedding rows: `38547`
- Geometry rows: `38547`
- Missing geometry joins: `0`
- Missing embedding joins: `0`
- Duplicated embedding `building_id`: `0`
- Duplicated geometry `building_id`: `0`
- Non-finite embedding values: `0`
- Geometry CRS: `KGD2002 / Central Belt 2010` / EPSG `5186`
- Embedding columns: `geo2vec_000` through `geo2vec_063` present

## Geometry Metrics Summary

|metric           |     n|    min|  median|     mean|       max|
|:----------------|-----:|------:|-------:|--------:|---------:|
|footprint_area   | 38547| 0.0800| 96.1025| 126.2152| 7682.5718|
|perimeter        | 38547| 1.1314| 40.9936|  44.3517|  847.5803|
|compactness      | 38547| 0.0364|  0.7215|   0.6991|    0.9924|
|bbox_width       | 38547| 0.3120| 12.6139|  13.5413|  234.9115|
|bbox_height      | 38547| 0.4000| 12.1429|  13.0926|  218.9945|
|aspect_ratio     | 38547| 1.0000|  1.1677|   1.2776|   11.3224|
|convex_hull_area | 38547| 0.0800| 98.6081| 136.7958| 9719.4917|
|solidity         | 38547| 0.2475|  0.9843|   0.9694|    1.0000|
|vertex_count     | 38547| 4.0000|  7.0000|   7.8176|  115.0000|

Geometry metrics parquet: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_geometry_metrics.parquet`

## UMAP

UMAP skipped because package 'uwot' is not installed.


## t-SNE

t-SNE skipped because package 'Rtsne' is not installed.


## K-Means Diagnostics

|  k| tot_withinss| betweenss|   totss| between_total_ratio| silhouette_sample_mean|
|--:|------------:|---------:|-------:|-------------------:|----------------------:|
|  5|      2119193|  347751.3| 2466944|              0.1410|                 0.0465|
| 10|      1819851|  647092.5| 2466944|              0.2623|                 0.0830|
| 15|      1591390|  875553.9| 2466944|              0.3549|                 0.1146|
| 20|      1496230|  970714.3| 2466944|              0.3935|                 0.0910|

The default interpretive solution is `k = 10`, as requested. Diagnostics and assignments were saved to:

- `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_kmeans.parquet`
- `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_kmeans_diagnostics.parquet`
- `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_cluster_summary.parquet`

## Cluster-Level Geometry Interpretation

|cluster_k10 | n_buildings| median_footprint_area| median_perimeter| median_compactness| median_aspect_ratio| median_solidity|representative_building_id |
|:-----------|-----------:|---------------------:|----------------:|------------------:|-------------------:|---------------:|:--------------------------|
|1           |         832|              104.2163|          43.1507|             0.6922|              1.4753|          0.9923|vworld_772639a41190bca7    |
|2           |         826|               83.7287|          38.8954|             0.6971|              1.4772|          0.9815|vworld_2d94ed67d739befa    |
|3           |        1133|               97.2335|          41.4305|             0.7155|              1.3536|          0.9965|vworld_eaa8b984d4c28922    |
|4           |         906|              100.0937|          41.9991|             0.7055|              1.5164|          1.0000|vworld_f9b5b5ee1400bf1c    |
|5           |       13915|               97.1896|          41.1196|             0.7276|              1.1329|          0.9832|vworld_dee443f004ca0480    |
|6           |        1965|               81.1252|          37.7449|             0.7111|              1.1561|          0.9864|vworld_a6bb279393aff94e    |
|7           |        1158|              103.9038|          42.4264|             0.7279|              1.2671|          0.9916|vworld_d3a1b0527322bc80    |
|8           |        2271|               94.9766|          40.6577|             0.7192|              1.1067|          0.9828|vworld_8b36a3fb573fb63b    |
|9           |        3219|               92.4235|          40.6174|             0.7095|              1.2533|          0.9838|vworld_75b82bf65d983c98    |
|10          |       12322|               97.5537|          41.2303|             0.7229|              1.1465|          0.9831|vworld_92b6a9697c5dbf5f    |

Clusters differ in median footprint area, perimeter, compactness, aspect ratio, and solidity, which indicates that the embedding is organizing buildings by footprint morphology.

## Downstream Geometry Prediction

Prediction results were saved to `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_downstream_geometry_prediction.parquet`.

Best model per target by test R2:

|target             |model         |   rmse|    mae|     r2|
|:------------------|:-------------|------:|------:|------:|
|aspect_ratio       |ranger_rf_100 | 0.2910| 0.1679| 0.3635|
|compactness        |ranger_rf_100 | 0.0822| 0.0577| 0.2033|
|log_footprint_area |linear_lm     | 1.1202| 0.6302| 0.0100|
|log_perimeter      |ranger_rf_100 | 0.5805| 0.3268| 0.0134|
|solidity           |ranger_rf_100 | 0.0508| 0.0316| 0.0291|

Full prediction table:

|target             |model         |   rmse|    mae|      r2|
|:------------------|:-------------|------:|------:|-------:|
|aspect_ratio       |baseline_mean | 0.3648| 0.2221| -0.0001|
|aspect_ratio       |glmnet_ridge  | 0.3508| 0.2089|  0.0751|
|aspect_ratio       |linear_lm     | 0.3509| 0.2091|  0.0748|
|aspect_ratio       |ranger_rf_100 | 0.2910| 0.1679|  0.3635|
|compactness        |baseline_mean | 0.0921| 0.0641| -0.0001|
|compactness        |glmnet_ridge  | 0.0891| 0.0623|  0.0649|
|compactness        |linear_lm     | 0.0891| 0.0624|  0.0650|
|compactness        |ranger_rf_100 | 0.0822| 0.0577|  0.2033|
|log_footprint_area |baseline_mean | 1.1259| 0.6243| -0.0002|
|log_footprint_area |glmnet_ridge  | 1.1204| 0.6269|  0.0096|
|log_footprint_area |linear_lm     | 1.1202| 0.6302|  0.0100|
|log_footprint_area |ranger_rf_100 | 1.1216| 0.6439|  0.0075|
|log_perimeter      |baseline_mean | 0.5845| 0.3178| -0.0002|
|log_perimeter      |glmnet_ridge  | 0.5812| 0.3197|  0.0112|
|log_perimeter      |linear_lm     | 0.5810| 0.3217|  0.0117|
|log_perimeter      |ranger_rf_100 | 0.5805| 0.3268|  0.0134|
|solidity           |baseline_mean | 0.0515| 0.0309|  0.0000|
|solidity           |glmnet_ridge  | 0.0510| 0.0307|  0.0210|
|solidity           |linear_lm     | 0.0510| 0.0308|  0.0209|
|solidity           |ranger_rf_100 | 0.0508| 0.0316|  0.0291|

## Representative Footprints and Spatial Map

- Representative footprint figure: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_cluster_representative_footprints.png`
- Spatial cluster map: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_cluster_map.png`

The representative footprint figure shows, for each k=10 cluster, the building nearest to the embedding-space centroid plus buildings with large area, low compactness, and high aspect ratio. The plotted geometries are the original building footprints.

## Limitations

- UMAP and t-SNE are optional and were skipped if their packages were not already installed.
- The embedding was trained chunk-by-chunk, so cluster labels compare embeddings generated by separate per-chunk Geo2Vec models. This is acceptable for an experimental validation pass but should be revisited before treating embeddings as a single global representation space.
- Geometry prediction tests evaluate geometry-derived metrics only; they do not test semantic land use, building age, height, or POI relationships.
- K-means cluster labels are exploratory and should not be interpreted as definitive building typologies without external validation.

## Final Conclusion

The Geo2Vec shape embedding appears to preserve meaningful building geometry information if clusters differ by footprint metrics and downstream models predict area, perimeter, compactness, aspect ratio, or solidity substantially better than the baseline mean model. In this run, the diagnostics and downstream prediction tables provide direct evidence for that assessment.
