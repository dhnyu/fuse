#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
  library(sf)
  library(ggplot2)
})

args <- commandArgs(trailingOnly = TRUE)
get_arg <- function(name, default = NULL) {
  flag <- paste0("--", name)
  idx <- match(flag, args)
  if (is.na(idx)) return(default)
  args[[idx + 1]]
}
has_flag <- function(name) paste0("--", name) %in% args

shape_dir <- get_arg("shape-embedding-dir")
location_dir <- get_arg("location-embedding-dir")
full_dir <- get_arg("full-embedding-dir")
geometry_path <- get_arg("geometry", "/members/dhnyu/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
layer <- get_arg("layer", "gwanak_buildings")
split_path <- get_arg("split-path", "/members/dhnyu/fusedata/geo2vec_large_scale/metadata/evaluation_splits/gwanak_building_evaluation_split.parquet")
output_dir <- get_arg("output-dir")
seed <- as.integer(get_arg("seed", "20260610"))
max_model_rows <- as.integer(get_arg("max-model-rows", "0"))
xgb_rounds <- as.integer(get_arg("xgb-rounds", "120"))
nthreads_xgboost <- as.integer(get_arg("nthreads-xgboost", "32"))
nthreads_umap <- as.integer(get_arg("nthreads-umap", "32"))
overwrite <- has_flag("overwrite")

if (is.null(shape_dir) || is.null(location_dir) || is.null(full_dir) || is.null(output_dir)) {
  stop("Required: --shape-embedding-dir, --location-embedding-dir, --full-embedding-dir, --output-dir")
}
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
manifest_path <- file.path(output_dir, "r_evaluation_manifest.json")
if (file.exists(manifest_path) && !overwrite) {
  cat(readLines(manifest_path), sep = "\n")
  quit(status = 0)
}

set.seed(seed)
pkg_available <- function(pkg) requireNamespace(pkg, quietly = TRUE)
optional_packages <- list(
  ranger = pkg_available("ranger"),
  xgboost = pkg_available("xgboost"),
  uwot = pkg_available("uwot"),
  glmnet = pkg_available("glmnet"),
  FNN = pkg_available("FNN")
)

read_json_simple <- function(path) {
  txt <- paste(readLines(path, warn = FALSE), collapse = "\n")
  jsonlite::fromJSON(txt, simplifyVector = FALSE)
}

read_embedding_dir <- function(path) {
  parts_path <- file.path(path, "embedding_export_parts.parquet")
  parts <- as.data.table(read_parquet(parts_path))
  parts <- parts[order(part_index)]
  rbindlist(lapply(parts$path, function(p) as.data.table(read_parquet(p))), use.names = TRUE)
}

embedding_cols <- function(dt, prefix = NULL) {
  cols <- grep("^geo2vec_", names(dt), value = TRUE)
  if (!is.null(prefix)) cols <- grep(paste0("^", prefix), cols, value = TRUE)
  sort(cols)
}

ring_vertex_count <- function(g) {
  if (inherits(g, "POLYGON")) {
    return(sum(vapply(g, function(r) max(0L, nrow(r) - 1L), integer(1))))
  }
  if (inherits(g, "MULTIPOLYGON")) {
    return(sum(vapply(g, function(poly) sum(vapply(poly, function(r) max(0L, nrow(r) - 1L), integer(1))), integer(1))))
  }
  0L
}

build_labels <- function(building_ids) {
  g <- st_read(geometry_path, layer = layer, quiet = TRUE)
  g$building_id <- as.character(g$building_id)
  g <- g[match(building_ids, g$building_id), ]
  if (any(is.na(g$building_id))) stop("Some embedding building_id values were not found in geometry.")
  geom <- st_geometry(g)
  area <- as.numeric(st_area(geom))
  perimeter <- as.numeric(st_length(st_boundary(geom)))
  bbox <- st_bbox(geom)
  per_geom_bbox <- st_as_sfc(st_bbox(g[1, ]))
  bmat <- do.call(rbind, lapply(seq_along(geom), function(i) as.numeric(st_bbox(geom[i]))))
  bw <- bmat[, 3] - bmat[, 1]
  bh <- bmat[, 4] - bmat[, 2]
  centroid <- st_coordinates(st_centroid(geom))
  vertex_count <- vapply(geom, ring_vertex_count, integer(1))
  data.table(
    building_id = building_ids,
    area = area,
    perimeter = perimeter,
    compactness = ifelse(perimeter > 0, 4 * pi * area / (perimeter^2), NA_real_),
    bbox_aspect_ratio = ifelse(pmin(bw, bh) > 0, pmax(bw, bh) / pmin(bw, bh), NA_real_),
    edge_count = vertex_count,
    vertex_count = vertex_count,
    centroid_x = centroid[, 1],
    centroid_y = centroid[, 2]
  )
}

model_matrix_for <- function(dt, cols) as.matrix(dt[, ..cols])
targets <- c("area", "perimeter", "compactness", "bbox_aspect_ratio", "edge_count", "vertex_count", "centroid_x", "centroid_y")

metric_row <- function(embedding, split_name, target, model, y, pred, n_train, n_test) {
  ok <- is.finite(y) & is.finite(pred)
  y <- y[ok]; pred <- pred[ok]
  ss_res <- sum((y - pred)^2)
  ss_tot <- sum((y - mean(y))^2)
  data.table(
    embedding = embedding,
    split = split_name,
    target = target,
    model = model,
    r2 = ifelse(ss_tot > 0, 1 - ss_res / ss_tot, NA_real_),
    mae = mean(abs(y - pred)),
    train_rows = n_train,
    test_rows = n_test
  )
}

fit_eval <- function(name, dt, cols, split_col) {
  split_name <- sub("^split_", "", split_col)
  if (max_model_rows > 0L && nrow(dt) > max_model_rows) {
    set.seed(seed + nchar(name) + nchar(split_col))
    train_rows <- which(dt[[split_col]] == "train")
    test_rows <- which(dt[[split_col]] == "test")
    train_n <- min(length(train_rows), floor(max_model_rows * 0.8))
    test_n <- min(length(test_rows), max_model_rows - train_n)
    keep <- sort(c(sample(train_rows, train_n), sample(test_rows, test_n)))
    dt <- dt[keep]
  }
  train_idx <- dt[[split_col]] == "train"
  test_idx <- dt[[split_col]] == "test"
  x_train <- model_matrix_for(dt[train_idx], cols)
  x_test <- model_matrix_for(dt[test_idx], cols)
  rows <- list()
  for (target in targets) {
    y_train <- dt[[target]][train_idx]
    y_test <- dt[[target]][test_idx]
    train_df <- data.frame(y = y_train, x_train)
    test_df <- data.frame(x_test)
    lin <- lm(y ~ ., data = train_df)
    rows[[length(rows) + 1L]] <- metric_row(name, split_name, target, "linear_regression", y_test, predict(lin, test_df), sum(train_idx), sum(test_idx))
    if (optional_packages$glmnet) {
      ridge <- glmnet::cv.glmnet(x_train, y_train, alpha = 0, nfolds = 5)
      pred <- as.numeric(predict(ridge, x_test, s = "lambda.min"))
      rows[[length(rows) + 1L]] <- metric_row(name, split_name, target, "ridge_glmnet", y_test, pred, sum(train_idx), sum(test_idx))
    }
    if (optional_packages$ranger) {
      rf <- ranger::ranger(y ~ ., data = train_df, num.trees = 200, max.depth = 12, min.node.size = 3, seed = seed)
      pred <- predict(rf, test_df)$predictions
      rows[[length(rows) + 1L]] <- metric_row(name, split_name, target, "ranger_random_forest", y_test, pred, sum(train_idx), sum(test_idx))
    }
    if (optional_packages$xgboost) {
      dtrain <- xgboost::xgb.DMatrix(x_train, label = y_train)
      dtest <- xgboost::xgb.DMatrix(x_test)
      xgb <- xgboost::xgb.train(
        params = list(
          objective = "reg:squarederror",
          eta = 0.05,
          max_depth = 4,
          subsample = 0.8,
          colsample_bytree = 0.8,
          nthread = nthreads_xgboost
        ),
        data = dtrain,
        nrounds = xgb_rounds,
        verbose = 0
      )
      rows[[length(rows) + 1L]] <- metric_row(name, split_name, target, "xgboost", y_test, predict(xgb, dtest), sum(train_idx), sum(test_idx))
    }
  }
  rbindlist(rows)
}

write_plot <- function(coords, name, method, color_col) {
  fig <- file.path(output_dir, sprintf("%s_%s_%s.png", name, tolower(method), color_col))
  p <- ggplot(coords, aes(x = dim1, y = dim2, color = .data[[color_col]])) +
    geom_point(size = 0.4, alpha = 0.55) +
    scale_color_viridis_c() +
    theme_minimal(base_size = 11) +
    labs(x = paste0(method, "1"), y = paste0(method, "2"), color = color_col)
  ggsave(fig, p, width = 7, height = 5, dpi = 180)
  fig
}

dimension_outputs <- function(name, dt, cols) {
  x <- scale(model_matrix_for(dt, cols))
  pca <- prcomp(x, rank. = 2)
  pca_dt <- data.table(building_id = dt$building_id, dim1 = pca$x[, 1], dim2 = pca$x[, 2], area = dt$area, centroid_x = dt$centroid_x, centroid_y = dt$centroid_y)
  pca_path <- file.path(output_dir, paste0(name, "_pca_coordinates.parquet"))
  write_parquet(pca_dt, pca_path, compression = "zstd")
  out <- list(pca_coordinates = pca_path, pca_area_figure = write_plot(pca_dt, name, "PCA", "area"))
  if (optional_packages$uwot) {
    n <- min(nrow(x), 10000L)
    idx <- sort(sample(seq_len(nrow(x)), n))
    um <- uwot::umap(x[idx, , drop = FALSE], n_neighbors = 30, min_dist = 0.1, n_threads = nthreads_umap, verbose = FALSE)
    um_dt <- data.table(building_id = dt$building_id[idx], dim1 = um[, 1], dim2 = um[, 2], area = dt$area[idx], centroid_x = dt$centroid_x[idx], centroid_y = dt$centroid_y[idx])
    umap_path <- file.path(output_dir, paste0(name, "_umap_coordinates.parquet"))
    write_parquet(um_dt, umap_path, compression = "zstd")
    out$umap_available <- TRUE
    out$umap_coordinates <- umap_path
    out$umap_area_figure <- write_plot(um_dt, name, "UMAP", "area")
  } else {
    out$umap_available <- FALSE
  }
  out
}

retrieval_outputs <- function(name, dt, cols) {
  if (!optional_packages$FNN) return(list(available = FALSE, reason = "FNN unavailable"))
  set.seed(seed)
  x <- scale(model_matrix_for(dt, cols))
  qidx <- sort(sample(seq_len(nrow(dt)), min(25L, nrow(dt))))
  nn <- FNN::get.knnx(x, x[qidx, , drop = FALSE], k = 6)
  rows <- rbindlist(lapply(seq_along(qidx), function(i) {
    qi <- qidx[[i]]
    ni <- nn$nn.index[i, ]
    data.table(
      embedding = name,
      query_building_id = dt$building_id[qi],
      neighbor_rank = seq_along(ni) - 1L,
      neighbor_building_id = dt$building_id[ni],
      embedding_distance = nn$nn.dist[i, ],
      query_area = dt$area[qi],
      neighbor_area = dt$area[ni],
      abs_log_area_delta = abs(log1p(dt$area[qi]) - log1p(dt$area[ni])),
      centroid_distance = sqrt((dt$centroid_x[qi] - dt$centroid_x[ni])^2 + (dt$centroid_y[qi] - dt$centroid_y[ni])^2)
    )
  }))
  path <- file.path(output_dir, paste0(name, "_retrieval_neighbors.parquet"))
  write_parquet(rows, path, compression = "zstd")
  list(available = TRUE, neighbors = path)
}

shape <- read_embedding_dir(shape_dir)
location <- read_embedding_dir(location_dir)
full <- read_embedding_dir(full_dir)
setkey(shape, building_id, geo2vec_internal_id)
setkey(location, building_id, geo2vec_internal_id)
setkey(full, building_id, geo2vec_internal_id)

base <- shape[, .(building_id, geo2vec_internal_id)]
labels <- build_labels(base$building_id)
splits <- as.data.table(read_parquet(split_path))
split_cols <- splits[, .(building_id, split_random, fold_random, split_spatial, fold_spatial)]
dt_base <- Reduce(function(x, y) merge(x, y, by = "building_id"), list(base, labels, split_cols))
setorder(dt_base, geo2vec_internal_id)
missing_targets <- setdiff(targets, names(dt_base))
if (length(missing_targets) > 0) {
  stop(sprintf("Missing evaluation target columns after split join: %s", paste(missing_targets, collapse = ", ")))
}

sets <- list(
  shape = merge(dt_base, shape, by = c("building_id", "geo2vec_internal_id")),
  location = merge(dt_base, location, by = c("building_id", "geo2vec_internal_id")),
  full_geo2vec = merge(dt_base, full, by = c("building_id", "geo2vec_internal_id"))
)
cols <- list(
  shape = embedding_cols(sets$shape, "geo2vec_shp"),
  location = embedding_cols(sets$location, "geo2vec_loc"),
  full_geo2vec = embedding_cols(sets$full_geo2vec)
)

metrics <- rbindlist(unlist(lapply(names(sets), function(nm) {
  list(
    fit_eval(nm, sets[[nm]], cols[[nm]], "split_random"),
    fit_eval(nm, sets[[nm]], cols[[nm]], "split_spatial")
  )
}), recursive = FALSE))
metrics_path <- file.path(output_dir, "r_recoverability_metrics.parquet")
write_parquet(metrics, metrics_path, compression = "zstd")
labels_path <- file.path(output_dir, "r_evaluation_proxy_labels.parquet")
write_parquet(dt_base[, c("building_id", targets, "split_random", "fold_random", "split_spatial", "fold_spatial"), with = FALSE], labels_path, compression = "zstd")

dimensions <- lapply(names(sets), function(nm) dimension_outputs(nm, sets[[nm]], cols[[nm]]))
names(dimensions) <- names(sets)
retrieval <- lapply(names(sets), function(nm) retrieval_outputs(nm, sets[[nm]], cols[[nm]]))
names(retrieval) <- names(sets)

manifest <- list(
  script = "evaluate_geo2vec_embeddings.R",
  complete = TRUE,
  output_dir = output_dir,
  shape_embedding_dir = shape_dir,
  location_embedding_dir = location_dir,
  full_embedding_dir = full_dir,
  split_path = split_path,
  row_count = nrow(dt_base),
  targets = targets,
  optional_packages = optional_packages,
  max_model_rows = max_model_rows,
  xgb_rounds = xgb_rounds,
  nthreads_xgboost = nthreads_xgboost,
  nthreads_umap = nthreads_umap,
  preferred_evaluation_path = "R",
  python_xgboost_umap_required = FALSE,
  geometry_proxies_in_embedding = FALSE,
  recoverability_metrics = metrics_path,
  evaluation_proxy_labels = labels_path,
  dimensions = dimensions,
  retrieval = retrieval
)
jsonlite::write_json(manifest, manifest_path, pretty = TRUE, auto_unbox = TRUE)
cat(jsonlite::toJSON(manifest, pretty = TRUE, auto_unbox = TRUE))
