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

output_root <- path.expand(get_arg("output-root", "~/fusedata/embeddings/regional_replication_model_c"))
run_id <- get_arg("run-id", stop("--run-id is required", call. = FALSE))
targets_path <- path.expand(get_arg("targets", stop("--targets is required", call. = FALSE)))
threads <- as.integer(get_arg("threads", Sys.getenv("FUSE_EVAL_THREADS", unset = "48")))
seed <- as.integer(get_arg("seed", "20260616"))
num_trees <- as.integer(get_arg("num-trees", "100"))
overwrite <- has_flag("overwrite")

if (is.na(threads) || threads < 1L) threads <- 48L
if (is.na(num_trees) || num_trees < 1L) num_trees <- 100L

data.table::setDTthreads(threads)
Sys.setenv(
  OMP_NUM_THREADS = as.character(threads),
  MKL_NUM_THREADS = as.character(threads),
  OPENBLAS_NUM_THREADS = as.character(threads),
  VECLIB_MAXIMUM_THREADS = as.character(threads),
  NUMEXPR_NUM_THREADS = as.character(threads)
)

if (!requireNamespace("ranger", quietly = TRUE)) {
  stop("Package 'ranger' is required for this evaluation.", call. = FALSE)
}

r2_score <- function(y, pred) {
  ok <- is.finite(y) & is.finite(pred)
  y <- y[ok]
  pred <- pred[ok]
  if (!length(y)) return(NA_real_)
  ss_tot <- sum((y - mean(y))^2)
  if (ss_tot <= 0) return(NA_real_)
  1 - sum((y - pred)^2) / ss_tot
}

rmse <- function(y, pred) {
  ok <- is.finite(y) & is.finite(pred)
  sqrt(mean((y[ok] - pred[ok])^2))
}

mae <- function(y, pred) {
  ok <- is.finite(y) & is.finite(pred)
  mean(abs(y[ok] - pred[ok]))
}

embedding_root <- file.path(output_root, "embeddings", run_id)
manifest_paths <- list.files(embedding_root, pattern = "embedding_export_manifest[.]json$", recursive = TRUE, full.names = TRUE)
if (!length(manifest_paths)) stop("No embedding manifests found under: ", embedding_root, call. = FALSE)

manifest <- NULL
for (path in manifest_paths) {
  candidate <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  if (identical(candidate$variant, "shape_scene_relative_location") &&
      !is.null(candidate$embedding_kind) &&
      identical(candidate$embedding_kind, "shape_scene_relative_location_full_location_shape")) {
    manifest <- candidate
    manifest$manifest_path <- path
    break
  }
}
if (is.null(manifest)) {
  stop("Full Model C embedding manifest not found under: ", embedding_root, call. = FALSE)
}
if (is.null(manifest$embedding_path) || !file.exists(manifest$embedding_path)) {
  stop("Model C embedding parquet missing: ", manifest$embedding_path, call. = FALSE)
}

targets <- as.data.table(read_parquet(targets_path))
required_target_cols <- c(
  "building_id", "spatial_fold", "area", "perimeter", "compactness",
  "aspect_ratio", "bbox_area_ratio", "centroid_x", "centroid_y"
)
missing_targets <- setdiff(required_target_cols, names(targets))
if (length(missing_targets)) {
  stop("Targets missing required columns: ", paste(missing_targets, collapse = ", "), call. = FALSE)
}

emb <- as.data.table(read_parquet(manifest$embedding_path))
feature_cols <- grep("^geo2vec_(loc|shp)_[0-9]{3}$", names(emb), value = TRUE)
if (!length(feature_cols)) stop("No Model C embedding columns found.", call. = FALSE)

dt <- merge(emb, targets, by = "building_id", all.x = TRUE, allow.cartesian = TRUE)
if (anyNA(dt$spatial_fold)) stop("Some embedding rows did not match target spatial folds.", call. = FALSE)
folds <- sort(unique(as.integer(dt$spatial_fold)))
if (length(folds) < 2L) stop("Need at least two spatial folds for CV.", call. = FALSE)

targets_eval <- c("area", "perimeter", "compactness", "aspect_ratio", "bbox_area_ratio", "centroid_x", "centroid_y")
pred_rows <- list()
fold_rows <- list()

start <- proc.time()[["elapsed"]]
for (target in targets_eval) {
  for (fold in folds) {
    train_idx <- as.integer(dt$spatial_fold) != fold
    test_idx <- as.integer(dt$spatial_fold) == fold
    train_df <- as.data.frame(dt[train_idx, c("building_id", target, feature_cols), with = FALSE])
    test_df <- as.data.frame(dt[test_idx, c("building_id", target, feature_cols), with = FALSE])
    names(train_df)[names(train_df) == target] <- "y"
    y_test <- test_df[[target]]
    test_x <- test_df[, feature_cols, drop = FALSE]
    fit <- ranger::ranger(
      y ~ .,
      data = train_df[, c("y", feature_cols), drop = FALSE],
      num.trees = num_trees,
      num.threads = threads,
      seed = seed + fold,
      write.forest = TRUE
    )
    pred <- predict(fit, test_x)$predictions
    fold_rows[[length(fold_rows) + 1L]] <- data.table(
      embedding = manifest$embedding_kind,
      split = "spatial_block_cv",
      target = target,
      model = "ranger",
      fold = fold,
      r2 = r2_score(y_test, pred),
      rmse = rmse(y_test, pred),
      mae = mae(y_test, pred),
      train_rows = sum(train_idx),
      test_rows = sum(test_idx)
    )
    pred_rows[[length(pred_rows) + 1L]] <- data.table(
      building_id = test_df$building_id,
      target = target,
      fold = fold,
      y = y_test,
      pred = pred
    )
  }
}
elapsed <- proc.time()[["elapsed"]] - start

pred_dt <- rbindlist(pred_rows, use.names = TRUE, fill = TRUE)
fold_metrics <- rbindlist(fold_rows, use.names = TRUE, fill = TRUE)
cv_metrics <- pred_dt[, .(
  embedding = manifest$embedding_kind,
  split = "spatial_block_cv",
  model = "ranger",
  r2 = r2_score(y, pred),
  rmse = rmse(y, pred),
  mae = mae(y, pred),
  folds = length(unique(fold)),
  test_rows = .N
), by = target]
setcolorder(cv_metrics, c("embedding", "split", "target", "model", "r2", "rmse", "mae", "folds", "test_rows"))

out_dir <- file.path(output_root, "evaluations", run_id)
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
metrics_path <- file.path(out_dir, "spatial_block_cv_ranger_metrics.parquet")
fold_metrics_path <- file.path(out_dir, "spatial_block_cv_ranger_fold_metrics.parquet")
pred_path <- file.path(out_dir, "spatial_block_cv_ranger_predictions.parquet")
summary_path <- file.path(out_dir, "spatial_block_cv_ranger_summary.json")
for (path in c(metrics_path, fold_metrics_path, pred_path, summary_path)) {
  if (file.exists(path) && !overwrite) stop("Output exists; use --overwrite: ", path, call. = FALSE)
}

write_parquet(cv_metrics, metrics_path, compression = "zstd")
write_parquet(fold_metrics, fold_metrics_path, compression = "zstd")
write_parquet(pred_dt, pred_path, compression = "zstd")

summary <- list(
  run_id = run_id,
  output_root = output_root,
  targets_path = targets_path,
  embedding_manifest = manifest$manifest_path,
  embedding_path = manifest$embedding_path,
  row_count = nrow(dt),
  feature_count = length(feature_cols),
  spatial_folds = folds,
  model = "ranger",
  num_trees = num_trees,
  threads_requested = threads,
  datatable_threads = data.table::getDTthreads(),
  elapsed_seconds = elapsed,
  metrics = metrics_path,
  fold_metrics = fold_metrics_path,
  predictions = pred_path,
  environment_threads = as.list(Sys.getenv(c(
    "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"
  )))
)
writeLines(jsonlite::toJSON(summary, auto_unbox = TRUE, pretty = TRUE), summary_path, useBytes = TRUE)

cat(jsonlite::toJSON(summary, auto_unbox = TRUE, pretty = TRUE))
cat("\n")
