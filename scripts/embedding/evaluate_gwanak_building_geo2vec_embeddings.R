#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
})

args <- commandArgs(trailingOnly = TRUE)
get_arg <- function(name, default = NULL) {
  flag <- paste0("--", name)
  idx <- match(flag, args)
  if (is.na(idx)) return(default)
  args[[idx + 1L]]
}
has_flag <- function(name) paste0("--", name) %in% args
`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0L || all(is.na(x)) || identical(x, "")) y else x
}

output_root <- path.expand(get_arg("output-root", "~/fusedata/embeddings/gwanak_building_geo2vec"))
run_id <- get_arg("run-id", "phase1_smoke")
targets_path <- path.expand(get_arg("targets", file.path(output_root, "phase0_current/targets/gwanak_building_geometry_targets.parquet")))
report_dir <- path.expand(get_arg("report-dir", "reports/experiments"))
seed <- as.integer(get_arg("seed", "20260615"))
threads <- as.integer(get_arg("threads", Sys.getenv("FUSE_EVAL_THREADS", unset = "1")))
if (is.na(threads) || threads < 1L) threads <- 1L
overwrite <- has_flag("overwrite")
suppress_report <- has_flag("suppress-report")

data.table::setDTthreads(threads)
Sys.setenv(
  OMP_NUM_THREADS = as.character(threads),
  MKL_NUM_THREADS = as.character(threads),
  OPENBLAS_NUM_THREADS = as.character(threads),
  VECLIB_MAXIMUM_THREADS = as.character(threads),
  NUMEXPR_NUM_THREADS = as.character(threads)
)

pkg_available <- function(pkg) requireNamespace(pkg, quietly = TRUE)
optional <- list(
  glmnet = pkg_available("glmnet"),
  ranger = pkg_available("ranger"),
  xgboost = pkg_available("xgboost")
)

metric_row <- function(embedding_name, split_name, target, model, y, pred, n_train, n_test) {
  ok <- is.finite(y) & is.finite(pred)
  y <- y[ok]
  pred <- pred[ok]
  ss_res <- sum((y - pred)^2)
  ss_tot <- sum((y - mean(y))^2)
  data.table(
    embedding = embedding_name,
    split = split_name,
    target = target,
    model = model,
    r2 = ifelse(ss_tot > 0, 1 - ss_res / ss_tot, NA_real_),
    rmse = sqrt(mean((y - pred)^2)),
    mae = mean(abs(y - pred)),
    train_rows = n_train,
    test_rows = n_test
  )
}

embedding_cols <- function(dt) grep("^geo2vec_(loc|shp)_", names(dt), value = TRUE)

fit_eval <- function(name, dt, cols, split_col) {
  split_name <- sub("^split_", "", split_col)
  train_idx <- dt[[split_col]] == "train"
  test_idx <- dt[[split_col]] == "test"
  if (sum(train_idx) < 5L || sum(test_idx) < 2L) return(data.table())
  x_train <- as.matrix(dt[train_idx, ..cols])
  x_test <- as.matrix(dt[test_idx, ..cols])
  targets <- c("area", "log_area", "perimeter", "log_perimeter", "compactness", "aspect_ratio", "bbox_area_ratio", "vertex_count", "centroid_x", "centroid_y")
  rows <- list()
  for (target in targets) {
    y_train <- dt[[target]][train_idx]
    y_test <- dt[[target]][test_idx]
    train_df <- data.frame(y = y_train, x_train)
    test_df <- data.frame(x_test)
    lin <- stats::lm(y ~ ., data = train_df)
    rows[[length(rows) + 1L]] <- metric_row(name, split_name, target, "linear", y_test, predict(lin, test_df), sum(train_idx), sum(test_idx))
    if (optional$glmnet && length(unique(y_train)) > 1L) {
      ridge <- glmnet::cv.glmnet(x_train, y_train, alpha = 0, nfolds = min(5L, sum(train_idx)))
      pred <- as.numeric(predict(ridge, x_test, s = "lambda.min"))
      rows[[length(rows) + 1L]] <- metric_row(name, split_name, target, "ridge", y_test, pred, sum(train_idx), sum(test_idx))
    }
    if (optional$ranger) {
      rf <- ranger::ranger(y ~ ., data = train_df, num.trees = 100, seed = seed, num.threads = threads)
      pred <- predict(rf, test_df)$predictions
      rows[[length(rows) + 1L]] <- metric_row(name, split_name, target, "ranger", y_test, pred, sum(train_idx), sum(test_idx))
    }
    if (optional$xgboost) {
      dtrain <- xgboost::xgb.DMatrix(x_train, label = y_train)
      dtest <- xgboost::xgb.DMatrix(x_test)
      xgb <- xgboost::xgb.train(
        params = list(objective = "reg:squarederror", eta = 0.05, max_depth = 3, nthread = threads),
        data = dtrain,
        nrounds = 80,
        verbose = 0
      )
      rows[[length(rows) + 1L]] <- metric_row(name, split_name, target, "xgboost", y_test, predict(xgb, dtest), sum(train_idx), sum(test_idx))
    }
  }
  rbindlist(rows, use.names = TRUE, fill = TRUE)
}

targets <- as.data.table(read_parquet(targets_path))
embedding_root <- file.path(output_root, "embeddings", run_id)
manifest_paths <- list.files(embedding_root, pattern = "embedding_export_manifest[.]json$", recursive = TRUE, full.names = TRUE)
if (!length(manifest_paths)) stop("No embedding manifests found under: ", embedding_root, call. = FALSE)

dir.create(file.path(output_root, "evaluations", run_id), recursive = TRUE, showWarnings = FALSE)
dir.create(report_dir, recursive = TRUE, showWarnings = FALSE)
results <- list()
manifest_rows <- list()
for (manifest_path in manifest_paths) {
  manifest <- jsonlite::fromJSON(manifest_path, simplifyVector = FALSE)
  if (is.null(manifest$embedding_path) || !file.exists(manifest$embedding_path)) next
  emb <- as.data.table(read_parquet(manifest$embedding_path))
  cols <- embedding_cols(emb)
  if (!length(cols)) next
  name <- manifest$embedding_kind %||% basename(dirname(manifest_path))
  dt <- merge(emb, targets, by = "building_id", all.x = TRUE, allow.cartesian = TRUE)
  results[[length(results) + 1L]] <- fit_eval(name, dt, cols, "split_random")
  results[[length(results) + 1L]] <- fit_eval(name, dt, cols, "split_spatial")
  manifest_rows[[length(manifest_rows) + 1L]] <- data.table(
    embedding = name,
    manifest_path = manifest_path,
    embedding_path = manifest$embedding_path,
    row_count = nrow(emb),
    embedding_dim = length(cols)
  )
}

metrics <- rbindlist(results, use.names = TRUE, fill = TRUE)
manifest_dt <- rbindlist(manifest_rows, use.names = TRUE, fill = TRUE)
metrics_path <- file.path(output_root, "evaluations", run_id, "object_level_metrics.parquet")
manifest_out <- file.path(output_root, "evaluations", run_id, "evaluation_inputs.parquet")
write_parquet(metrics, metrics_path, compression = "zstd")
write_parquet(manifest_dt, manifest_out, compression = "zstd")

report_path <- NULL
if (!suppress_report) {
  stamp <- format(Sys.time(), "%Y%m%d_%H%M")
  report_path <- file.path(report_dir, paste0(stamp, "_gwanak_building_geo2vec_object_evaluation.md"))
  if (file.exists(report_path) && !overwrite) stop("Report exists: ", report_path, call. = FALSE)
  summary <- metrics[, .(mean_r2 = mean(r2, na.rm = TRUE), mean_mae = mean(mae, na.rm = TRUE)), by = .(embedding, split, model)]
  lines <- c(
    "# Gwanak Building Geo2Vec Object Evaluation",
    "",
    paste("Generated:", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
    "",
    "This report evaluates object-level building geometry embeddings only. Centroid x/y targets are leakage diagnostics.",
    "",
    "## Inputs",
    "",
    paste("- Targets:", targets_path),
    paste("- Embedding root:", embedding_root),
    paste("- Metrics:", metrics_path),
    "",
    "## Available Packages",
    "",
    paste("- glmnet:", optional$glmnet),
    paste("- ranger:", optional$ranger),
    paste("- xgboost:", optional$xgboost),
    paste("- threads:", threads),
    paste("- data.table threads:", data.table::getDTthreads()),
    "",
    "## Summary",
    "",
    paste(capture.output(print(summary)), collapse = "\n")
  )
  writeLines(lines, report_path, useBytes = TRUE)
}

cat(jsonlite::toJSON(list(metrics = metrics_path, inputs = manifest_out, report = report_path), auto_unbox = TRUE, pretty = TRUE))
cat("\n")
