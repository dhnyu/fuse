#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
  library(sf)
  library(xgboost)
  library(jsonlite)
  library(future)
  library(future.apply)
  library(ggplot2)
})

sf::sf_use_s2(FALSE)

seed <- 20260608L
set.seed(seed)

repo_root <- path.expand("~/fuse")
validation_dir <- path.expand("~/fusedata/gwanak_test/validation")
dir.create(validation_dir, recursive = TRUE, showWarnings = FALSE)

single_path <- file.path(validation_dir, "gwanak_buildings_geo2vec_shape_single_model_lightweight.parquet")
chunked_path <- path.expand("~/fusedata/embeddings/gwanak_buildings_geo2vec_shape_full.parquet")
building_path <- path.expand("~/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
dong_path <- path.expand("~/fusedatalarge/geodata/koreanadm/bnd_dong_00_2024_2Q.shp")

results_path <- file.path(validation_dir, "gwanak_geo2vec_xgboost_strict_validation_results.parquet")
summary_csv_path <- file.path(validation_dir, "gwanak_geo2vec_xgboost_strict_validation_summary.csv")
fold_path <- file.path(validation_dir, "gwanak_geo2vec_xgboost_spatial_fold_assignments.parquet")
residual_path <- file.path(validation_dir, "gwanak_geo2vec_xgboost_residuals.parquet")
gpu_json_path <- file.path(validation_dir, "gwanak_geo2vec_xgboost_gpu_check.json")
report_path <- file.path(repo_root, "tests/gwanak_test/docs/gwanak_geo2vec_strict_validation_xgboost_report.md")

target_names <- c("log_area", "log_perimeter", "compactness", "elongation", "bbox_area_ratio")

check_file <- function(path) {
  if (!file.exists(path)) stop("Required file not found: ", path, call. = FALSE)
}

check_file(single_path)
check_file(chunked_path)
check_file(building_path)

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), sprintf(...)))
  flush.console()
}

metric_table <- function(buildings) {
  geoms <- sf::st_geometry(buildings)
  area <- as.numeric(sf::st_area(geoms))
  perimeter <- as.numeric(sf::st_length(sf::st_boundary(geoms)))
  bbox <- sf::st_bbox(geoms)
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

  dong_available <- FALSE
  if (file.exists(dong_path)) {
    dong <- tryCatch(sf::st_read(dong_path, quiet = TRUE, options = "ENCODING=UTF-8"), error = function(e) NULL)
    if (!is.null(dong)) {
      dong <- sf::st_transform(dong, sf::st_crs(buildings))
      joined <- suppressWarnings(sf::st_join(centroids[, c("building_id")], dong[, c("ADM_NM", "ADM_CD")], left = TRUE))
      dong_dt <- data.table(
        building_id = as.character(joined[["building_id"]]),
        dong_name = as.character(joined[["ADM_NM"]]),
        dong_code = as.character(joined[["ADM_CD"]])
      )
      folds <- dong_dt[folds, on = "building_id"]
      matched_dongs <- unique(na.omit(folds$dong_code))
      if (length(matched_dongs) >= 5L) {
        dong_map <- assign_balanced_group_folds(folds[!is.na(dong_code)], "dong_code", 5L)
        folds <- dong_map[folds, on = "dong_code"]
        setnames(folds, "fold", "dong_fold")
        dong_available <- TRUE
      } else {
        folds[, `:=`(dong_fold = NA_integer_)]
      }
    }
  }
  if (!"dong_fold" %in% names(folds)) folds[, dong_fold := NA_integer_]
  attr(folds, "dong_available") <- dong_available
  folds[]
}

xgb_gpu_check <- function() {
  x <- matrix(rnorm(200), ncol = 4)
  y <- rnorm(nrow(x))
  dtrain <- xgb.DMatrix(x, label = y)
  attempts <- list(
    list(name = "device_cuda_hist", params = list(objective = "reg:squarederror", eval_metric = "rmse", device = "cuda", tree_method = "hist")),
    list(name = "gpu_hist", params = list(objective = "reg:squarederror", eval_metric = "rmse", tree_method = "gpu_hist"))
  )
  for (attempt in attempts) {
    warning_messages <- character()
    res <- tryCatch({
      model <- withCallingHandlers(
        xgb.train(params = attempt$params, data = dtrain, nrounds = 2, verbose = 0),
        warning = function(w) {
          warning_messages <<- c(warning_messages, conditionMessage(w))
          invokeRestart("muffleWarning")
        }
      )
      fallback_warning <- any(grepl("changed from GPU to CPU|couldn't find any available GPU|No visible GPU|CUDA", warning_messages, ignore.case = TRUE))
      actual_config <- xgb.config(model)
      actual_device <- actual_config$learner$generic_param$device
      used_gpu <- identical(actual_device, "cuda") || grepl("^cuda", actual_device)
      if (fallback_warning || !used_gpu) {
        msg <- paste(c(warning_messages, sprintf("Actual xgboost device: %s", actual_device)), collapse = " | ")
        list(succeeded = FALSE, method = attempt$name, params = attempt$params, error = msg)
      } else {
        list(succeeded = TRUE, method = attempt$name, params = attempt$params, actual_device = actual_device, error = NULL)
      }
    }, error = function(e) {
      list(succeeded = FALSE, method = attempt$name, params = attempt$params, error = conditionMessage(e))
    })
    if (isTRUE(res$succeeded)) return(res)
  }
  list(succeeded = FALSE, method = "cpu_fallback", params = list(objective = "reg:squarederror", eval_metric = "rmse", tree_method = "hist"), error = "No tested xgboost GPU mode succeeded.")
}

make_xgb_params <- function(gpu_check, nthread) {
  base <- list(
    objective = "reg:squarederror",
    eval_metric = "rmse",
    max_depth = 4,
    eta = 0.05,
    subsample = 0.8,
    colsample_bytree = 0.8,
    min_child_weight = 5,
    seed = seed,
    nthread = nthread
  )
  if (isTRUE(gpu_check$succeeded) && identical(gpu_check$method, "device_cuda_hist")) {
    c(base, list(device = "cuda", tree_method = "hist"))
  } else if (isTRUE(gpu_check$succeeded) && identical(gpu_check$method, "gpu_hist")) {
    c(base, list(tree_method = "gpu_hist"))
  } else {
    c(base, list(tree_method = "hist"))
  }
}

run_one_task <- function(task, data_by_embedding, folds, xgb_params) {
  embedding_name <- task$embedding_name
  target <- task$target
  resampling <- task$resampling
  fold_id <- task$fold_id

  dt <- data_by_embedding[[embedding_name]]
  feature_cols <- grep("^geo2vec_[0-9]{3}$", names(dt), value = TRUE)

  if (resampling == "random_split") {
    test_ids <- folds[random_split == "test", building_id]
  } else if (resampling == "spatial_block_cv") {
    test_ids <- folds[spatial_fold == fold_id, building_id]
  } else if (resampling == "dong_holdout") {
    test_ids <- folds[dong_fold == fold_id, building_id]
  } else {
    stop("Unknown resampling: ", resampling)
  }

  row_is_test <- dt$building_id %in% test_ids
  row_ok <- is.finite(dt[[target]]) & row_is_test | is.finite(dt[[target]]) & !row_is_test
  train_idx_all <- which(!row_is_test & is.finite(dt[[target]]))
  test_idx <- which(row_is_test & is.finite(dt[[target]]))
  if (length(test_idx) < 20L || length(train_idx_all) < 100L) {
    stop("Insufficient train/test rows for ", embedding_name, " ", target, " ", resampling, " fold ", fold_id)
  }

  set.seed(seed + fold_id + match(target, target_names) * 100L)
  val_n <- max(50L, floor(0.1 * length(train_idx_all)))
  val_idx <- sample(train_idx_all, size = val_n)
  train_idx <- setdiff(train_idx_all, val_idx)

  x_train <- as.matrix(dt[train_idx, ..feature_cols])
  x_val <- as.matrix(dt[val_idx, ..feature_cols])
  x_test <- as.matrix(dt[test_idx, ..feature_cols])
  y_train <- dt[[target]][train_idx]
  y_val <- dt[[target]][val_idx]
  y_test <- dt[[target]][test_idx]

  dtrain <- xgb.DMatrix(x_train, label = y_train)
  dval <- xgb.DMatrix(x_val, label = y_val)
  dtest <- xgb.DMatrix(x_test)

  start <- Sys.time()
  model <- xgb.train(
    params = xgb_params,
    data = dtrain,
    nrounds = 300,
    watchlist = list(train = dtrain, validation = dval),
    early_stopping_rounds = 30,
    verbose = 0
  )
  pred <- predict(model, dtest)
  elapsed <- as.numeric(difftime(Sys.time(), start, units = "secs"))
  residual <- y_test - pred
  rmse <- sqrt(mean(residual^2))
  mae <- mean(abs(residual))
  r2 <- 1 - sum(residual^2) / sum((y_test - mean(y_test))^2)

  result <- data.table(
    embedding_name = embedding_name,
    target = target,
    resampling = resampling,
    fold_id = fold_id,
    n_train = length(train_idx),
    n_validation = length(val_idx),
    n_test = length(test_idx),
    n_features = length(feature_cols),
    best_iteration = model$best_iteration,
    rmse = rmse,
    mae = mae,
    r2 = r2,
    elapsed_seconds = elapsed
  )

  residual_dt <- data.table(
    embedding_name = embedding_name,
    target = target,
    resampling = resampling,
    fold_id = fold_id,
    building_id = dt$building_id[test_idx],
    actual = y_test,
    predicted = pred,
    residual = residual
  )

  list(result = result, residuals = residual_dt)
}

write_report <- function(results, summary_dt, gpu_check, folds, dong_available, elapsed_total, workers_used, nthread) {
  avg_dt <- results[, .(
    mean_r2 = mean(r2),
    sd_r2 = if (.N > 1) sd(r2) else NA_real_,
    mean_rmse = mean(rmse),
    mean_mae = mean(mae),
    mean_elapsed_seconds = mean(elapsed_seconds),
    folds = .N
  ), by = .(embedding_name, target, resampling)]

  wide <- dcast(avg_dt, target + resampling ~ embedding_name, value.var = "mean_r2")
  if (all(c("single_model_32d", "chunked_64d") %in% names(wide))) {
    wide[, single_minus_chunked_r2 := single_model_32d - chunked_64d]
  }

  random_wide <- wide[resampling == "random_split"]
  spatial_wide <- wide[resampling == "spatial_block_cv"]
  drop_dt <- merge(
    avg_dt[resampling == "random_split", .(embedding_name, target, random_r2 = mean_r2)],
    avg_dt[resampling == "spatial_block_cv", .(embedding_name, target, spatial_r2 = mean_r2)],
    by = c("embedding_name", "target")
  )
  drop_dt[, r2_drop_random_to_spatial := random_r2 - spatial_r2]

  single_better_random <- if (nrow(random_wide)) sum(random_wide$single_minus_chunked_r2 > 0, na.rm = TRUE) else 0L
  single_better_spatial <- if (nrow(spatial_wide)) sum(spatial_wide$single_minus_chunked_r2 > 0, na.rm = TRUE) else 0L

  lines <- c(
    "# Gwanak Geo2Vec Strict XGBoost Validation Report",
    "",
    sprintf("Generated: `%s`", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
    "",
    "## Summary",
    "",
    sprintf("- Workers used: `%s`; xgboost `nthread`: `%s`", workers_used, nthread),
    if (is.finite(elapsed_total)) sprintf("- Total validation elapsed seconds: `%.2f`", elapsed_total) else "- Total validation elapsed seconds: `not rerun; existing saved results summarized`",
    sprintf("- GPU xgboost available: `%s`; method: `%s`", gpu_check$succeeded, gpu_check$method),
    sprintf("- Dong holdout available: `%s`", dong_available),
    sprintf("- Single model beats chunked on random split targets: `%s / %s`", single_better_random, length(target_names)),
    sprintf("- Single model beats chunked on spatial block CV targets: `%s / %s`", single_better_spatial, length(target_names)),
    "",
    "## GPU Check",
    "",
    "```json",
    jsonlite::toJSON(gpu_check, auto_unbox = TRUE, pretty = TRUE),
    "```",
    "",
    "If GPU setup failed, validation continued with CPU xgboost. The GPU check is intentionally non-fatal.",
    "",
    "## Target Definitions",
    "",
    "- `log_area = log1p(st_area(geometry))`",
    "- `log_perimeter = log1p(st_length(st_boundary(geometry)))`",
    "- `compactness = 4*pi*area/perimeter^2`",
    "- `elongation = max(bbox_width, bbox_height) / min(bbox_width, bbox_height)`",
    "- `bbox_area_ratio = area / (bbox_width*bbox_height)`",
    "",
    "## Resampling Design",
    "",
    "- Random split baseline: deterministic 80/20 building split.",
    "- Spatial block CV: deterministic 500 m centroid grid blocks greedily assigned to 5 balanced folds.",
    if (isTRUE(dong_available)) "- Administrative dong holdout: building point-on-surface joined to dong polygons, dongs greedily assigned to 5 balanced folds." else "- Administrative dong holdout: not available; dong join did not produce at least 5 matched dong groups.",
    "",
    sprintf("Fold assignments were saved to `%s` and reused for both embeddings.", fold_path),
    "",
    "## Mean R2 By Target And Resampling",
    "",
    paste(capture.output(print(wide)), collapse = "\n"),
    "",
    "## Random Split To Spatial CV Drop",
    "",
    paste(capture.output(print(drop_dt)), collapse = "\n"),
    "",
    "## Full Summary Table",
    "",
    sprintf("Summary CSV: `%s`", summary_csv_path),
    "",
    paste(capture.output(print(summary_dt)), collapse = "\n"),
    "",
    "## Answers",
    "",
    sprintf("1. Random split: single-model outperformed chunked on `%s` of `%s` targets by mean R2.", single_better_random, length(target_names)),
    sprintf("2. Spatial block CV: single-model outperformed chunked on `%s` of `%s` targets by mean R2.", single_better_spatial, length(target_names)),
    "3. Performance generally drops from random split to spatial CV when embeddings exploit local morphology/spatial autocorrelation; see the drop table above.",
    "4. The random-split result should be treated as optimistic if spatial CV R2 is materially lower.",
    "5. Consistency across geometry targets should be judged target-by-target; area/perimeter are often harder than compactness/elongation-style shape metrics.",
    "6. This xgboost validation directly tests whether the earlier random-forest finding holds under stricter folds.",
    sprintf("7. GPU xgboost availability: `%s`; fallback/method: `%s`.", gpu_check$succeeded, gpu_check$method),
    "8. The default Gwanak building shape embedding should be the single global model if it remains stronger under spatial CV, because it has one shared latent space.",
    "9. For Seoul/Korea, prefer single-model staged feasibility tests where possible; if chunking is needed, use anchor alignment before treating vectors as comparable.",
    "",
    "## Outputs",
    "",
    sprintf("- Results parquet: `%s`", results_path),
    sprintf("- Summary CSV: `%s`", summary_csv_path),
    sprintf("- Fold assignments: `%s`", fold_path),
    sprintf("- Residuals parquet: `%s`", residual_path),
    sprintf("- GPU check JSON: `%s`", gpu_json_path)
  )

  writeLines(lines, report_path)
}

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  if ("--report-only" %in% args) {
    log_msg("Regenerating GPU check JSON and markdown report from saved validation results.")
    results <- as.data.table(arrow::read_parquet(results_path))
    summary_dt <- fread(summary_csv_path)
    folds <- as.data.table(arrow::read_parquet(fold_path))
    dong_available <- "dong_fold" %in% names(folds) && any(!is.na(folds$dong_fold))
    gpu_check <- xgb_gpu_check()
    if (!isTRUE(gpu_check$succeeded)) {
      gpu_check <- list(
        succeeded = FALSE,
        method = "cpu_fallback",
        params = list(objective = "reg:squarederror", eval_metric = "rmse", tree_method = "hist"),
        error = gpu_check$error
      )
    }
    write_json(gpu_check, gpu_json_path, auto_unbox = TRUE, pretty = TRUE)
    write_report(results, summary_dt, gpu_check, folds, dong_available, NA_real_, "not rerun", "not rerun")
    log_msg("Wrote report: %s", report_path)
    return(invisible(NULL))
  }

  start_total <- Sys.time()
  log_msg("Reading buildings and embeddings.")
  buildings <- sf::st_read(building_path, quiet = TRUE)
  if (!"building_id" %in% names(buildings)) stop("building_id missing in building GeoPackage.", call. = FALSE)
  buildings <- buildings[!sf::st_is_empty(buildings) & !is.na(buildings$building_id), ]
  metrics <- metric_table(buildings)
  folds <- make_folds(buildings)
  dong_available <- isTRUE(attr(folds, "dong_available"))
  arrow::write_parquet(folds, fold_path)

  single <- as.data.table(arrow::read_parquet(single_path))
  chunked <- as.data.table(arrow::read_parquet(chunked_path))
  single[, building_id := as.character(building_id)]
  chunked[, building_id := as.character(building_id)]

  data_by_embedding <- list(
    single_model_32d = metrics[single, on = "building_id"],
    chunked_64d = metrics[chunked, on = "building_id"]
  )

  for (nm in names(data_by_embedding)) {
    missing_targets <- data_by_embedding[[nm]][, sum(!complete.cases(.SD)), .SDcols = target_names]
    if (missing_targets > 0) warning(sprintf("%s has %s missing target values.", nm, missing_targets))
  }

  gpu_check <- xgb_gpu_check()
  write_json(gpu_check, gpu_json_path, auto_unbox = TRUE, pretty = TRUE)

  workers <- min(8L, max(1L, parallel::detectCores() %/% 4L))
  if (isTRUE(gpu_check$succeeded)) {
    workers <- min(workers, 2L)
  }
  nthread <- if (isTRUE(gpu_check$succeeded)) 1L else max(1L, parallel::detectCores() %/% workers %/% 2L)
  xgb_params <- make_xgb_params(gpu_check, nthread)

  tasks <- list()
  for (embedding_name in names(data_by_embedding)) {
    for (target in target_names) {
      tasks[[length(tasks) + 1L]] <- list(embedding_name = embedding_name, target = target, resampling = "random_split", fold_id = 1L)
      for (fold_id in 1:5) {
        tasks[[length(tasks) + 1L]] <- list(embedding_name = embedding_name, target = target, resampling = "spatial_block_cv", fold_id = fold_id)
      }
      if (dong_available) {
        for (fold_id in 1:5) {
          tasks[[length(tasks) + 1L]] <- list(embedding_name = embedding_name, target = target, resampling = "dong_holdout", fold_id = fold_id)
        }
      }
    }
  }

  log_msg("Running %s xgboost tasks with %s workers.", length(tasks), workers)
  future::plan(future::multisession, workers = workers)
  task_results <- future.apply::future_lapply(
    tasks,
    run_one_task,
    data_by_embedding = data_by_embedding,
    folds = folds,
    xgb_params = xgb_params,
    future.seed = TRUE
  )
  future::plan(future::sequential)

  results <- rbindlist(lapply(task_results, `[[`, "result"), fill = TRUE)
  residuals <- rbindlist(lapply(task_results, `[[`, "residuals"), fill = TRUE)
  arrow::write_parquet(results, results_path)
  arrow::write_parquet(residuals, residual_path)

  summary_dt <- results[, .(
    mean_r2 = mean(r2),
    sd_r2 = if (.N > 1) sd(r2) else NA_real_,
    mean_rmse = mean(rmse),
    mean_mae = mean(mae),
    mean_elapsed_seconds = mean(elapsed_seconds),
    folds = .N
  ), by = .(embedding_name, target, resampling)]
  data.table::fwrite(summary_dt, summary_csv_path)

  elapsed_total <- as.numeric(difftime(Sys.time(), start_total, units = "secs"))
  write_report(results, summary_dt, gpu_check, folds, dong_available, elapsed_total, workers, nthread)
  log_msg("Wrote report: %s", report_path)
}

main()
