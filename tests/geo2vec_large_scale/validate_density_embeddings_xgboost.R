#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
  library(sf)
  library(xgboost)
  library(jsonlite)
})

sf::sf_use_s2(FALSE)
seed <- 20260608L
set.seed(seed)

args <- commandArgs(trailingOnly = TRUE)
study_name <- "gwanak_sample_density_sensitivity_v1"
if (length(args) >= 1L) {
  for (i in seq_along(args)) {
    if (args[[i]] == "--study-name" && i < length(args)) {
      study_name <- args[[i + 1L]]
    }
  }
}

root <- path.expand("~/fusedata/geo2vec_large_scale")
manifest_path <- file.path(root, "metadata", study_name, "sample_density_sensitivity_manifest.json")
geometry_path <- path.expand("~/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
dong_path <- path.expand("~/fusedata/geodata/koreanadm/bnd_dong_00_2024_2Q.shp")
out_dir <- file.path(root, "reports", study_name)
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

target_names <- c("log_area", "log_perimeter", "compactness", "elongation", "bbox_area_ratio")

metric_table <- function(buildings) {
  geoms <- sf::st_geometry(buildings)
  area <- as.numeric(sf::st_area(geoms))
  perimeter <- as.numeric(sf::st_length(sf::st_boundary(geoms)))
  bounds <- do.call(rbind, lapply(geoms, function(g) as.numeric(sf::st_bbox(g))))
  colnames(bounds) <- c("xmin", "ymin", "xmax", "ymax")
  width <- pmax(bounds[, "xmax"] - bounds[, "xmin"], 1e-6)
  height <- pmax(bounds[, "ymax"] - bounds[, "ymin"], 1e-6)
  bbox_area <- pmax(width * height, 1e-6)
  data.table(
    building_id = as.character(buildings[["building_id"]]),
    log_area = log1p(area),
    log_perimeter = log1p(perimeter),
    compactness = fifelse(perimeter > 0, 4 * pi * area / (perimeter^2), NA_real_),
    elongation = pmax(width, height) / pmax(pmin(width, height), 1e-6),
    bbox_area_ratio = area / bbox_area
  )
}

assign_balanced_group_folds <- function(group_dt, group_col, n_folds = 5L) {
  counts <- group_dt[, .N, by = group_col]
  setorderv(counts, c("N", group_col), order = c(-1L, 1L))
  fold_sizes <- rep(0L, n_folds)
  fold_ids <- integer(nrow(counts))
  for (i in seq_len(nrow(counts))) {
    fold <- which.min(fold_sizes)
    fold_ids[i] <- fold
    fold_sizes[fold] <- fold_sizes[fold] + counts$N[i]
  }
  counts[, fold := fold_ids]
  counts[, c(group_col, "fold"), with = FALSE]
}

make_folds <- function(buildings) {
  centroids <- sf::st_point_on_surface(buildings)
  coords <- sf::st_coordinates(centroids)
  folds <- data.table(
    building_id = as.character(buildings[["building_id"]]),
    centroid_x = coords[, 1],
    centroid_y = coords[, 2]
  )
  set.seed(seed)
  random_test <- sample(folds$building_id, size = floor(0.2 * nrow(folds)), replace = FALSE)
  folds[, random_split := fifelse(building_id %in% random_test, "test", "train")]
  folds[, random_fold := 1L]
  cell_size <- 500
  folds[, block_x := floor((centroid_x - min(centroid_x)) / cell_size)]
  folds[, block_y := floor((centroid_y - min(centroid_y)) / cell_size)]
  folds[, spatial_block_id := paste(block_x, block_y, sep = "_")]
  block_map <- assign_balanced_group_folds(folds, "spatial_block_id", 5L)
  folds <- block_map[folds, on = "spatial_block_id"]
  setnames(folds, "fold", "spatial_fold")
  if (file.exists(dong_path)) {
    dong <- tryCatch(sf::st_read(dong_path, quiet = TRUE, options = "ENCODING=UTF-8"), error = function(e) NULL)
    if (!is.null(dong)) {
      dong <- sf::st_transform(dong, sf::st_crs(buildings))
      joined <- suppressWarnings(sf::st_join(centroids[, c("building_id")], dong[, c("ADM_NM", "ADM_CD")], left = TRUE))
      dong_dt <- data.table(building_id = as.character(joined[["building_id"]]), dong_code = as.character(joined[["ADM_CD"]]))
      folds <- dong_dt[folds, on = "building_id"]
      matched <- unique(na.omit(folds$dong_code))
      if (length(matched) >= 5L) {
        if ("dong_fold" %in% names(folds)) {
          folds[, dong_fold := NULL]
        }
        dong_map <- assign_balanced_group_folds(folds[!is.na(dong_code)], "dong_code", 5L)
        folds <- dong_map[folds, on = "dong_code"]
        setnames(folds, "fold", "dong_fold")
      }
    }
  }
  if (!"dong_fold" %in% names(folds)) {
    folds[, dong_fold := NA_integer_]
  }
  folds[]
}

run_one <- function(dt, folds, target, resampling, fold_id) {
  feature_cols <- grep("^geo2vec_[0-9]{3}$", names(dt), value = TRUE)
  if (resampling == "random_split") {
    test_ids <- folds[random_split == "test", building_id]
  } else if (resampling == "spatial_block_cv") {
    test_ids <- folds[spatial_fold == fold_id, building_id]
  } else {
    test_ids <- folds[dong_fold == fold_id, building_id]
  }
  row_is_test <- dt$building_id %in% test_ids
  train_idx_all <- which(!row_is_test & is.finite(dt[[target]]))
  test_idx <- which(row_is_test & is.finite(dt[[target]]))
  set.seed(seed + fold_id + match(target, target_names) * 100L)
  val_n <- max(50L, floor(0.1 * length(train_idx_all)))
  val_idx <- sample(train_idx_all, size = val_n)
  train_idx <- setdiff(train_idx_all, val_idx)
  params <- list(
    objective = "reg:squarederror",
    eval_metric = "rmse",
    max_depth = 4,
    eta = 0.05,
    subsample = 0.8,
    colsample_bytree = 0.8,
    min_child_weight = 5,
    seed = seed,
    nthread = 8,
    tree_method = "hist"
  )
  dtrain <- xgb.DMatrix(as.matrix(dt[train_idx, ..feature_cols]), label = dt[[target]][train_idx])
  dval <- xgb.DMatrix(as.matrix(dt[val_idx, ..feature_cols]), label = dt[[target]][val_idx])
  dtest <- xgb.DMatrix(as.matrix(dt[test_idx, ..feature_cols]))
  start <- Sys.time()
  model <- xgb.train(params = params, data = dtrain, nrounds = 300, watchlist = list(validation = dval), early_stopping_rounds = 30, verbose = 0)
  pred <- predict(model, dtest)
  elapsed <- as.numeric(difftime(Sys.time(), start, units = "secs"))
  y <- dt[[target]][test_idx]
  resid <- y - pred
  data.table(
    target = target,
    resampling = resampling,
    fold_id = fold_id,
    n_train = length(train_idx),
    n_validation = length(val_idx),
    n_test = length(test_idx),
    rmse = sqrt(mean(resid^2)),
    mae = mean(abs(resid)),
    r2 = 1 - sum(resid^2) / sum((y - mean(y))^2),
    best_iteration = model$best_iteration,
    elapsed_seconds = elapsed
  )
}

manifest <- jsonlite::fromJSON(manifest_path, simplifyVector = FALSE)
buildings <- sf::st_read(geometry_path, layer = "gwanak_buildings", quiet = TRUE)
metrics <- metric_table(buildings)
folds <- make_folds(buildings)
arrow::write_parquet(folds, file.path(out_dir, "density_validation_fold_assignments.parquet"))

all_results <- list()
for (d in manifest$densities) {
  embedding_parts <- list.files(d$embedding_dir, pattern = "^embeddings_part_.*\\.parquet$", full.names = TRUE)
  stopifnot(length(embedding_parts) > 0L)
  emb <- rbindlist(lapply(embedding_parts, function(path) as.data.table(arrow::read_parquet(path))), fill = TRUE)
  feature_cols <- grep("^geo2vec_[0-9]{3}$", names(emb), value = TRUE)
  stopifnot(length(feature_cols) == 32L)
  stopifnot(all(is.finite(as.matrix(emb[, ..feature_cols]))))
  dt <- metrics[emb, on = "building_id"]
  tasks <- list()
  for (target in target_names) {
    tasks[[length(tasks) + 1L]] <- list(target = target, resampling = "random_split", fold_id = 1L)
    for (fold_id in 1:5) tasks[[length(tasks) + 1L]] <- list(target = target, resampling = "spatial_block_cv", fold_id = fold_id)
    if (any(is.finite(folds$dong_fold))) for (fold_id in 1:5) tasks[[length(tasks) + 1L]] <- list(target = target, resampling = "dong_holdout", fold_id = fold_id)
  }
  res <- rbindlist(lapply(tasks, function(task) run_one(dt, folds, task$target, task$resampling, task$fold_id)), fill = TRUE)
  res[, `:=`(
    density_name = d$name,
    epochs = if (!is.null(d$epochs)) as.integer(d$epochs) else NA_integer_,
    sample_config_version = d$sample_config_version,
    samples_per_unit = d$samples_per_unit,
    point_sample = d$point_sample,
    uniform_grid = d$uniform_grid
  )]
  result_key <- if (!is.null(d$epochs)) paste(d$name, d$epochs, sep = "_epoch_") else d$name
  all_results[[result_key]] <- res
}
results <- rbindlist(all_results, fill = TRUE)
summary <- results[, .(
  folds = .N,
  r2_mean = mean(r2),
  r2_sd = sd(r2),
  rmse_mean = mean(rmse),
  rmse_sd = sd(rmse),
  mae_mean = mean(mae),
  mae_sd = sd(mae)
), by = .(density_name, epochs, sample_config_version, target, resampling)]
arrow::write_parquet(results, file.path(out_dir, "density_xgboost_validation_results.parquet"))
arrow::write_parquet(summary, file.path(out_dir, "density_xgboost_validation_summary.parquet"))
fwrite(summary, file.path(out_dir, "density_xgboost_validation_summary.csv"))
cat(jsonlite::toJSON(list(results = file.path(out_dir, "density_xgboost_validation_results.parquet"), summary = file.path(out_dir, "density_xgboost_validation_summary.parquet")), auto_unbox = TRUE, pretty = TRUE), "\n")
