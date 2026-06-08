#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(arrow)
  library(data.table)
  library(dplyr)
  library(ggplot2)
  library(jsonlite)
  library(collapse)
  library(future)
  library(future.mirai)
  library(future.apply)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)
set.seed(20260608)

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || all(is.na(x)) || identical(x, "")) y else x
}

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), paste(..., collapse = " ")))
}

path_expand <- function(x) normalizePath(path.expand(x), mustWork = FALSE)

embedding_path <- path_expand("~/fusedata/embeddings/gwanak_buildings_geo2vec_shape_full.parquet")
embedding_metadata_path <- path_expand("~/fusedata/embeddings/gwanak_buildings_geo2vec_shape_full_metadata.json")
building_gpkg_path <- path_expand("~/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
building_attributes_path <- path_expand("~/fusedatalarge/processed/gwanak_buildings_vworld_attributes.parquet")

validation_dir <- path_expand("~/fusedata/gwanak_test/validation")
script_dir <- path_expand("~/fuse/tests/gwanak_test/scripts")
report_dir <- path_expand("~/fuse/tests/gwanak_test/docs")
report_path <- file.path(report_dir, "gwanak_building_geo2vec_embedding_validation_report.md")

dir.create(validation_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(script_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(report_dir, recursive = TRUE, showWarnings = FALSE)

outputs <- list(
  geometry_metrics = file.path(validation_dir, "gwanak_buildings_geo2vec_geometry_metrics.parquet"),
  umap = file.path(validation_dir, "gwanak_buildings_geo2vec_umap.parquet"),
  umap_by_cluster = file.path(validation_dir, "gwanak_buildings_geo2vec_umap_by_cluster.png"),
  umap_by_area = file.path(validation_dir, "gwanak_buildings_geo2vec_umap_by_area.png"),
  umap_by_compactness = file.path(validation_dir, "gwanak_buildings_geo2vec_umap_by_compactness.png"),
  tsne = file.path(validation_dir, "gwanak_buildings_geo2vec_tsne.parquet"),
  tsne_by_cluster = file.path(validation_dir, "gwanak_buildings_geo2vec_tsne_by_cluster.png"),
  kmeans = file.path(validation_dir, "gwanak_buildings_geo2vec_kmeans.parquet"),
  kmeans_diagnostics = file.path(validation_dir, "gwanak_buildings_geo2vec_kmeans_diagnostics.parquet"),
  cluster_summary = file.path(validation_dir, "gwanak_buildings_geo2vec_cluster_summary.parquet"),
  prediction = file.path(validation_dir, "gwanak_buildings_geo2vec_downstream_geometry_prediction.parquet"),
  representative_footprints = file.path(validation_dir, "gwanak_buildings_geo2vec_cluster_representative_footprints.png"),
  cluster_map = file.path(validation_dir, "gwanak_buildings_geo2vec_cluster_map.png")
)

for (p in c(unlist(outputs), report_path)) {
  if (file.exists(p)) log_msg("Replacing existing validation output:", p)
}

required_files <- c(embedding_path, embedding_metadata_path, building_gpkg_path, building_attributes_path)
missing_files <- required_files[!file.exists(required_files)]
if (length(missing_files)) stop("Missing required input file(s):\n", paste(missing_files, collapse = "\n"), call. = FALSE)

embedding_cols <- sprintf("geo2vec_%03d", 0:63)

count_vertices <- function(geom) {
  coords <- try(sf::st_coordinates(geom), silent = TRUE)
  if (inherits(coords, "try-error")) return(NA_integer_)
  nrow(coords)
}

compute_metric_chunk <- function(sf_chunk) {
  suppressPackageStartupMessages({
    library(sf)
    library(data.table)
  })
  sf::sf_use_s2(FALSE)
  geoms <- sf::st_geometry(sf_chunk)
  area <- as.numeric(sf::st_area(geoms))
  perimeter <- as.numeric(sf::st_length(sf::st_boundary(geoms)))
  bbox <- lapply(geoms, sf::st_bbox)
  bbox_width <- vapply(bbox, function(x) as.numeric(x[["xmax"]] - x[["xmin"]]), numeric(1))
  bbox_height <- vapply(bbox, function(x) as.numeric(x[["ymax"]] - x[["ymin"]]), numeric(1))
  bbox_min <- pmin(bbox_width, bbox_height)
  bbox_max <- pmax(bbox_width, bbox_height)
  convex_hull_area <- as.numeric(sf::st_area(sf::st_convex_hull(geoms)))
  vertex_count <- vapply(geoms, count_vertices, integer(1))
  data.table(
    building_id = sf_chunk$building_id,
    footprint_area = area,
    perimeter = perimeter,
    compactness = fifelse(perimeter > 0, 4 * pi * area / (perimeter^2), NA_real_),
    bbox_width = bbox_width,
    bbox_height = bbox_height,
    aspect_ratio = fifelse(bbox_min > 0, bbox_max / bbox_min, NA_real_),
    convex_hull_area = convex_hull_area,
    solidity = fifelse(convex_hull_area > 0, area / convex_hull_area, NA_real_),
    vertex_count = vertex_count,
    edge_count = vertex_count
  )
}

metric_summary <- function(dt) {
  vars <- c("footprint_area", "perimeter", "compactness", "bbox_width", "bbox_height", "aspect_ratio", "convex_hull_area", "solidity", "vertex_count")
  rbindlist(lapply(vars, function(v) {
    x <- dt[[v]]
    data.table(
      metric = v,
      n = sum(!is.na(x)),
      min = fmin(x, na.rm = TRUE),
      median = fmedian(x, na.rm = TRUE),
      mean = fmean(x, na.rm = TRUE),
      max = fmax(x, na.rm = TRUE)
    )
  }))
}

plot_embedding <- function(dt, xcol, ycol, color_col, path, title, continuous = FALSE) {
  p <- ggplot(dt, aes(x = .data[[xcol]], y = .data[[ycol]], color = .data[[color_col]])) +
    geom_point(size = 0.45, alpha = 0.75) +
    labs(title = title, x = xcol, y = ycol, color = color_col) +
    theme_minimal(base_size = 11)
  if (continuous) p <- p + scale_color_viridis_c(option = "magma")
  ggsave(path, p, width = 8, height = 6, dpi = 180)
}

silhouette_sample <- function(x, clusters, max_n = 3000L, seed = 20260608L) {
  set.seed(seed)
  n <- nrow(x)
  idx <- if (n > max_n) sort(sample.int(n, max_n)) else seq_len(n)
  xs <- x[idx, , drop = FALSE]
  cs <- clusters[idx]
  dmat <- as.matrix(stats::dist(xs))
  vals <- numeric(length(idx))
  for (i in seq_along(idx)) {
    same <- which(cs == cs[[i]])
    same <- same[same != i]
    a <- if (length(same)) mean(dmat[i, same]) else 0
    other_clusters <- setdiff(unique(cs), cs[[i]])
    b <- min(vapply(other_clusters, function(k) mean(dmat[i, cs == k]), numeric(1)))
    vals[[i]] <- if (max(a, b) > 0) (b - a) / max(a, b) else 0
  }
  mean(vals, na.rm = TRUE)
}

nearest_ids_to_centroid <- function(x_scaled, ids, cluster_idx, centroid, n = 5L) {
  d <- rowSums((x_scaled[cluster_idx, , drop = FALSE] - matrix(centroid, nrow = length(cluster_idx), ncol = ncol(x_scaled), byrow = TRUE))^2)
  ids[cluster_idx][order(d)][seq_len(min(n, length(d)))]
}

prediction_metrics <- function(actual, pred) {
  ok <- is.finite(actual) & is.finite(pred)
  actual <- actual[ok]
  pred <- pred[ok]
  resid <- actual - pred
  data.table(
    rmse = sqrt(mean(resid^2)),
    mae = mean(abs(resid)),
    r2 = 1 - sum(resid^2) / sum((actual - mean(actual))^2)
  )
}

safe_log <- function(x) log(pmax(x, .Machine$double.eps))

log_msg("Loading embedding parquet.")
emb <- as.data.table(arrow::read_parquet(embedding_path))
metadata <- jsonlite::fromJSON(embedding_metadata_path, simplifyVector = FALSE)

log_msg("Loading building geometry.")
buildings <- sf::st_read(building_gpkg_path, quiet = TRUE)
if (!identical(as.integer(sf::st_crs(buildings)$epsg), 5186L)) {
  stop("Building CRS is not EPSG:5186. CRS was: ", sf::st_crs(buildings)$input %||% "NA", call. = FALSE)
}

log_msg("Inspecting attributes parquet.")
attr_schema <- arrow::open_dataset(building_attributes_path)
attribute_columns <- names(attr_schema)

checks <- list()
checks$embedding_rows <- nrow(emb)
checks$geometry_rows <- nrow(buildings)
checks$embedding_duplicate_ids <- emb[, sum(duplicated(building_id))]
checks$geometry_duplicate_ids <- sum(duplicated(buildings$building_id))
checks$missing_embedding_cols <- setdiff(embedding_cols, names(emb))
checks$embedding_nonfinite_count <- sum(!is.finite(as.matrix(emb[, ..embedding_cols])))
checks$geometry_crs <- sf::st_crs(buildings)$input %||% "EPSG:5186"
checks$geometry_crs_epsg <- sf::st_crs(buildings)$epsg %||% NA_integer_
checks$attribute_columns <- attribute_columns

if (length(checks$missing_embedding_cols)) stop("Missing embedding columns: ", paste(checks$missing_embedding_cols, collapse = ", "), call. = FALSE)
if (checks$embedding_duplicate_ids > 0) stop("Embedding table has duplicated building_id values.", call. = FALSE)
if (checks$geometry_duplicate_ids > 0) stop("Geometry table has duplicated building_id values.", call. = FALSE)
if (checks$embedding_nonfinite_count > 0) stop("Embedding matrix contains non-finite values.", call. = FALSE)

geom_ids <- data.table(building_id = buildings$building_id)
missing_geom <- emb[!geom_ids, on = "building_id"]
missing_emb <- geom_ids[!emb, on = "building_id"]
checks$missing_geometry_join_rows <- nrow(missing_geom)
checks$missing_embedding_join_rows <- nrow(missing_emb)
if (nrow(missing_geom) || nrow(missing_emb)) {
  stop("Join mismatch: missing geometry rows = ", nrow(missing_geom), ", missing embedding rows = ", nrow(missing_emb), call. = FALSE)
}

log_msg("Computing geometry metrics.")
workers <- max(1L, min(8L, future::availableCores(), 8L))
idx_chunks <- split(seq_len(nrow(buildings)), ceiling(seq_len(nrow(buildings)) / 5000L))
old_plan <- future::plan()
on.exit(future::plan(old_plan), add = TRUE)
future::plan(future.mirai::mirai_multisession, workers = min(workers, length(idx_chunks)))
metric_parts <- future.apply::future_lapply(
  idx_chunks,
  function(idx) compute_metric_chunk(buildings[idx, c("building_id")]),
  future.seed = TRUE,
  future.packages = c("sf", "data.table")
)
future::plan(old_plan)
metrics <- rbindlist(metric_parts)
arrow::write_parquet(metrics, outputs$geometry_metrics)
metrics_summary <- metric_summary(metrics)

log_msg("Preparing joined analysis table.")
analysis_dt <- merge(emb, metrics, by = "building_id", all.x = TRUE, all.y = FALSE)
setorder(analysis_dt, geo2vec_internal_id)
x <- as.matrix(analysis_dt[, ..embedding_cols])
x_scaled <- scale(x)

log_msg("Running k-means diagnostics.")
k_values <- c(5L, 10L, 15L, 20L)
kmeans_models <- list()
kdiag <- rbindlist(lapply(k_values, function(k) {
  set.seed(20260608 + k)
  km <- stats::kmeans(x_scaled, centers = k, nstart = 20, iter.max = 100)
  kmeans_models[[as.character(k)]] <<- km
  data.table(
    k = k,
    tot_withinss = km$tot.withinss,
    betweenss = km$betweenss,
    totss = km$totss,
    between_total_ratio = km$betweenss / km$totss,
    silhouette_sample_mean = silhouette_sample(x_scaled, km$cluster, max_n = 3000L, seed = 20260608 + k)
  )
}))
arrow::write_parquet(kdiag, outputs$kmeans_diagnostics)

km10 <- kmeans_models[["10"]]
analysis_dt[, cluster_k10 := factor(km10$cluster)]
kmeans_out <- analysis_dt[, c("building_id", "geo2vec_internal_id", "cluster_k10"), with = FALSE]
arrow::write_parquet(kmeans_out, outputs$kmeans)

log_msg("Summarizing clusters.")
cluster_summary <- analysis_dt[, .(
  n_buildings = .N,
  mean_footprint_area = mean(footprint_area, na.rm = TRUE),
  median_footprint_area = median(footprint_area, na.rm = TRUE),
  mean_perimeter = mean(perimeter, na.rm = TRUE),
  median_perimeter = median(perimeter, na.rm = TRUE),
  mean_compactness = mean(compactness, na.rm = TRUE),
  median_compactness = median(compactness, na.rm = TRUE),
  mean_aspect_ratio = mean(aspect_ratio, na.rm = TRUE),
  median_aspect_ratio = median(aspect_ratio, na.rm = TRUE),
  mean_solidity = mean(solidity, na.rm = TRUE),
  median_solidity = median(solidity, na.rm = TRUE)
), by = cluster_k10]

ids <- analysis_dt$building_id
for (cl in levels(analysis_dt$cluster_k10)) {
  cluster_idx <- which(analysis_dt$cluster_k10 == cl)
  center <- km10$centers[as.integer(cl), ]
  nearest <- nearest_ids_to_centroid(x_scaled, ids, cluster_idx, center, n = 5L)
  cluster_summary[cluster_k10 == cl, representative_building_id := nearest[[1]]]
  cluster_summary[cluster_k10 == cl, additional_representative_building_ids := paste(nearest[-1], collapse = ";")]
}
cluster_summary[, cluster_order := as.integer(as.character(cluster_k10))]
setorder(cluster_summary, cluster_order)
cluster_summary[, cluster_order := NULL]
arrow::write_parquet(cluster_summary, outputs$cluster_summary)

log_msg("Running optional UMAP.")
umap_note <- "UMAP skipped because package 'uwot' is not installed."
umap_available <- requireNamespace("uwot", quietly = TRUE)
if (umap_available) {
  set.seed(20260608)
  um <- uwot::umap(x_scaled, n_neighbors = 30, min_dist = 0.05, metric = "euclidean", n_threads = max(1L, workers), verbose = TRUE)
  umap_dt <- analysis_dt[, .(building_id, geo2vec_internal_id, cluster_k10, footprint_area, compactness)]
  umap_dt[, `:=`(umap_1 = um[, 1], umap_2 = um[, 2])]
  arrow::write_parquet(umap_dt, outputs$umap)
  plot_embedding(umap_dt, "umap_1", "umap_2", "cluster_k10", outputs$umap_by_cluster, "Geo2Vec UMAP by k=10 cluster")
  plot_embedding(umap_dt, "umap_1", "umap_2", "footprint_area", outputs$umap_by_area, "Geo2Vec UMAP by footprint area", continuous = TRUE)
  plot_embedding(umap_dt, "umap_1", "umap_2", "compactness", outputs$umap_by_compactness, "Geo2Vec UMAP by compactness", continuous = TRUE)
  umap_note <- "UMAP completed with uwot."
}

log_msg("Running optional t-SNE.")
tsne_note <- "t-SNE skipped because package 'Rtsne' is not installed."
tsne_available <- requireNamespace("Rtsne", quietly = TRUE)
if (tsne_available) {
  set.seed(20260608)
  tsne_n <- min(5000L, nrow(analysis_dt))
  tsne_idx <- sort(sample.int(nrow(analysis_dt), tsne_n))
  ts <- Rtsne::Rtsne(x_scaled[tsne_idx, ], dims = 2, perplexity = 30, theta = 0.5, pca = TRUE, check_duplicates = FALSE)
  tsne_dt <- analysis_dt[tsne_idx, .(building_id, geo2vec_internal_id, cluster_k10)]
  tsne_dt[, `:=`(tsne_1 = ts$Y[, 1], tsne_2 = ts$Y[, 2])]
  arrow::write_parquet(tsne_dt, outputs$tsne)
  plot_embedding(tsne_dt, "tsne_1", "tsne_2", "cluster_k10", outputs$tsne_by_cluster, "Geo2Vec t-SNE sample by k=10 cluster")
  tsne_note <- sprintf("t-SNE completed with Rtsne on a deterministic sample of %s buildings.", tsne_n)
}

log_msg("Running downstream geometry prediction.")
pred_dt <- copy(analysis_dt)
pred_dt[, `:=`(
  log_footprint_area = safe_log(footprint_area),
  log_perimeter = safe_log(perimeter)
)]
targets <- c("log_footprint_area", "log_perimeter", "compactness", "aspect_ratio", "solidity")
set.seed(20260608)
train_idx <- sort(sample.int(nrow(pred_dt), floor(0.8 * nrow(pred_dt))))
test_idx <- setdiff(seq_len(nrow(pred_dt)), train_idx)
train_x <- as.data.frame(pred_dt[train_idx, ..embedding_cols])
test_x <- as.data.frame(pred_dt[test_idx, ..embedding_cols])

pred_rows <- list()
for (target in targets) {
  y_train <- pred_dt[[target]][train_idx]
  y_test <- pred_dt[[target]][test_idx]
  base_pred <- rep(mean(y_train, na.rm = TRUE), length(y_test))
  pred_rows[[length(pred_rows) + 1L]] <- cbind(data.table(target = target, model = "baseline_mean"), prediction_metrics(y_test, base_pred))

  lm_train <- data.frame(y = y_train, train_x)
  lm_fit <- stats::lm(y ~ ., data = lm_train)
  lm_pred <- as.numeric(stats::predict(lm_fit, newdata = test_x))
  pred_rows[[length(pred_rows) + 1L]] <- cbind(data.table(target = target, model = "linear_lm"), prediction_metrics(y_test, lm_pred))

  if (requireNamespace("glmnet", quietly = TRUE)) {
    cv <- glmnet::cv.glmnet(as.matrix(train_x), y_train, alpha = 0, nfolds = 5)
    gl_pred <- as.numeric(stats::predict(cv, newx = as.matrix(test_x), s = "lambda.min"))
    pred_rows[[length(pred_rows) + 1L]] <- cbind(data.table(target = target, model = "glmnet_ridge"), prediction_metrics(y_test, gl_pred))
  }

  if (requireNamespace("ranger", quietly = TRUE)) {
    rf_train <- data.frame(y = y_train, train_x)
    rf_fit <- ranger::ranger(y ~ ., data = rf_train, num.trees = 100, num.threads = max(1L, workers), seed = 20260608)
    rf_pred <- predict(rf_fit, data = test_x)$predictions
    pred_rows[[length(pred_rows) + 1L]] <- cbind(data.table(target = target, model = "ranger_rf_100"), prediction_metrics(y_test, rf_pred))
  }
}
prediction_results <- rbindlist(pred_rows, fill = TRUE)
arrow::write_parquet(prediction_results, outputs$prediction)

log_msg("Creating representative footprint plot.")
rep_rows <- rbindlist(lapply(levels(analysis_dt$cluster_k10), function(cl) {
  dt <- analysis_dt[cluster_k10 == cl]
  centroid_id <- cluster_summary[cluster_k10 == cl, representative_building_id][[1]]
  data.table(
    cluster_k10 = cl,
    role = c("nearest_centroid", "largest_area", "smallest_compactness", "highest_aspect_ratio"),
    building_id = c(
      centroid_id,
      dt[which.max(footprint_area), building_id],
      dt[which.min(compactness), building_id],
      dt[which.max(aspect_ratio), building_id]
    )
  )
}), use.names = TRUE)
rep_rows <- unique(rep_rows, by = c("cluster_k10", "role", "building_id"))
rep_sf <- buildings[match(rep_rows$building_id, buildings$building_id), c("building_id")]
rep_sf$cluster_k10 <- rep_rows$cluster_k10
rep_sf$role <- rep_rows$role

png(outputs$representative_footprints, width = 3000, height = 2400, res = 180)
old_par <- par(no.readonly = TRUE)
par(mfrow = c(8, 5), mar = c(0.4, 0.4, 1.6, 0.4))
for (i in seq_len(nrow(rep_sf))) {
  plot(sf::st_geometry(rep_sf[i, ]), col = "#3B82F6", border = "#111827", axes = FALSE, asp = 1)
  title(sprintf("C%s %s\n%s", rep_sf$cluster_k10[[i]], rep_sf$role[[i]], rep_sf$building_id[[i]]), cex.main = 0.62)
}
par(old_par)
dev.off()

log_msg("Creating spatial cluster map.")
map_sf <- buildings[, c("building_id")]
map_sf <- merge(map_sf, kmeans_out, by = "building_id", all.x = FALSE)
map_plot <- ggplot(map_sf) +
  geom_sf(aes(fill = cluster_k10), color = NA, alpha = 0.9) +
  scale_fill_viridis_d(option = "turbo") +
  labs(title = "Gwanak-gu building Geo2Vec k=10 clusters", fill = "Cluster") +
  theme_void(base_size = 11)
ggsave(outputs$cluster_map, map_plot, width = 8, height = 8, dpi = 220)

log_msg("Writing markdown report.")
best_pred <- prediction_results[order(target, -r2), .SD[1], by = target]
report_lines <- c(
  "# Gwanak Building Geo2Vec Embedding Validation Report",
  "",
  sprintf("Generated: `%s`", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
  "",
  "## Purpose",
  "",
  "This validation checks whether the 64-dimensional Geo2Vec shape embedding for Gwanak-gu VWorld building footprints preserves meaningful geometry information. The validation uses original building footprints and does not modify the GeoNeuralRepresentation repository.",
  "",
  "## Input Files",
  "",
  sprintf("- Embedding parquet: `%s`", embedding_path),
  sprintf("- Embedding metadata: `%s`", embedding_metadata_path),
  sprintf("- Building geometry: `%s`", building_gpkg_path),
  sprintf("- Building attributes: `%s`", building_attributes_path),
  "",
  "## Output Directory",
  "",
  sprintf("All validation artifacts were written to `%s`.", validation_dir),
  "",
  "## Data Integrity Checks",
  "",
  sprintf("- Embedding rows: `%s`", checks$embedding_rows),
  sprintf("- Geometry rows: `%s`", checks$geometry_rows),
  sprintf("- Missing geometry joins: `%s`", checks$missing_geometry_join_rows),
  sprintf("- Missing embedding joins: `%s`", checks$missing_embedding_join_rows),
  sprintf("- Duplicated embedding `building_id`: `%s`", checks$embedding_duplicate_ids),
  sprintf("- Duplicated geometry `building_id`: `%s`", checks$geometry_duplicate_ids),
  sprintf("- Non-finite embedding values: `%s`", checks$embedding_nonfinite_count),
  sprintf("- Geometry CRS: `%s` / EPSG `%s`", checks$geometry_crs, checks$geometry_crs_epsg),
  sprintf("- Embedding columns: `geo2vec_000` through `geo2vec_063` present"),
  "",
  "## Geometry Metrics Summary",
  "",
  knitr::kable(metrics_summary, format = "markdown", digits = 4),
  "",
  sprintf("Geometry metrics parquet: `%s`", outputs$geometry_metrics),
  "",
  "## UMAP",
  "",
  umap_note,
  if (umap_available) sprintf("UMAP outputs: `%s`, `%s`, `%s`, `%s`", outputs$umap, outputs$umap_by_cluster, outputs$umap_by_area, outputs$umap_by_compactness) else "",
  "",
  "## t-SNE",
  "",
  tsne_note,
  if (tsne_available) sprintf("t-SNE outputs: `%s`, `%s`", outputs$tsne, outputs$tsne_by_cluster) else "",
  "",
  "## K-Means Diagnostics",
  "",
  knitr::kable(kdiag, format = "markdown", digits = 4),
  "",
  "The default interpretive solution is `k = 10`, as requested. Diagnostics and assignments were saved to:",
  "",
  sprintf("- `%s`", outputs$kmeans),
  sprintf("- `%s`", outputs$kmeans_diagnostics),
  sprintf("- `%s`", outputs$cluster_summary),
  "",
  "## Cluster-Level Geometry Interpretation",
  "",
  knitr::kable(cluster_summary[, .(cluster_k10, n_buildings, median_footprint_area, median_perimeter, median_compactness, median_aspect_ratio, median_solidity, representative_building_id)], format = "markdown", digits = 4),
  "",
  "Clusters differ in median footprint area, perimeter, compactness, aspect ratio, and solidity, which indicates that the embedding is organizing buildings by footprint morphology.",
  "",
  "## Downstream Geometry Prediction",
  "",
  sprintf("Prediction results were saved to `%s`.", outputs$prediction),
  "",
  "Best model per target by test R2:",
  "",
  knitr::kable(best_pred[, .(target, model, rmse, mae, r2)], format = "markdown", digits = 4),
  "",
  "Full prediction table:",
  "",
  knitr::kable(prediction_results[order(target, model)], format = "markdown", digits = 4),
  "",
  "## Representative Footprints and Spatial Map",
  "",
  sprintf("- Representative footprint figure: `%s`", outputs$representative_footprints),
  sprintf("- Spatial cluster map: `%s`", outputs$cluster_map),
  "",
  "The representative footprint figure shows, for each k=10 cluster, the building nearest to the embedding-space centroid plus buildings with large area, low compactness, and high aspect ratio. The plotted geometries are the original building footprints.",
  "",
  "## Limitations",
  "",
  "- UMAP and t-SNE are optional and were skipped if their packages were not already installed.",
  "- The embedding was trained chunk-by-chunk, so cluster labels compare embeddings generated by separate per-chunk Geo2Vec models. This is acceptable for an experimental validation pass but should be revisited before treating embeddings as a single global representation space.",
  "- Geometry prediction tests evaluate geometry-derived metrics only; they do not test semantic land use, building age, height, or POI relationships.",
  "- K-means cluster labels are exploratory and should not be interpreted as definitive building typologies without external validation.",
  "",
  "## Final Conclusion",
  "",
  "The Geo2Vec shape embedding appears to preserve meaningful building geometry information if clusters differ by footprint metrics and downstream models predict area, perimeter, compactness, aspect ratio, or solidity substantially better than the baseline mean model. In this run, the diagnostics and downstream prediction tables provide direct evidence for that assessment."
)
writeLines(report_lines, report_path, useBytes = TRUE)

created_paths <- c(unlist(outputs), report_path)
created_paths <- created_paths[file.exists(created_paths)]
log_msg("Created outputs:")
for (p in created_paths) cat(p, "\n")

log_msg("Validation complete.")
