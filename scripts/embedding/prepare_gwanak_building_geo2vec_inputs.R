#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
  library(sf)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)

args <- commandArgs(trailingOnly = TRUE)

get_arg <- function(name, default = NULL) {
  flag <- paste0("--", name)
  idx <- match(flag, args)
  if (is.na(idx)) return(default)
  args[[idx + 1L]]
}

has_flag <- function(name) paste0("--", name) %in% args

input_path <- path.expand(get_arg("input", "~/fusedatalarge/working_data/gwanak/1_Building_vworld.gpkg"))
output_root <- path.expand(get_arg("output-root", "~/fusedata/embeddings/gwanak_building_geo2vec"))
run_id <- get_arg("run-id", "phase0_current")
target_epsg <- as.integer(get_arg("target-epsg", "5186"))
overwrite <- has_flag("overwrite")

stop_if_missing <- function(path, label) {
  if (!file.exists(path)) stop(label, " does not exist: ", path, call. = FALSE)
}

write_json <- function(path, payload) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  tmp <- paste0(path, ".tmp")
  writeLines(jsonlite::toJSON(payload, auto_unbox = TRUE, pretty = TRUE, null = "null"), tmp, useBytes = TRUE)
  file.rename(tmp, path)
}

replace_if_needed <- function(path) {
  if (!file.exists(path)) return(invisible(TRUE))
  if (!overwrite) stop("Output exists; use --overwrite: ", path, call. = FALSE)
  unlink(path, recursive = TRUE, force = TRUE)
  unlink(paste0(path, "-wal"), force = TRUE)
  unlink(paste0(path, "-shm"), force = TRUE)
  invisible(TRUE)
}

ring_vertex_count <- function(g) {
  if (inherits(g, "POLYGON")) {
    return(sum(vapply(g, function(r) max(0L, nrow(r) - 1L), integer(1))))
  }
  if (inherits(g, "MULTIPOLYGON")) {
    return(sum(vapply(g, function(poly) {
      sum(vapply(poly, function(r) max(0L, nrow(r) - 1L), integer(1)))
    }, integer(1))))
  }
  0L
}

polygon_part <- function(x) {
  suppressWarnings(sf::st_collection_extract(x, "POLYGON"))
}

stop_if_missing(input_path, "Input building GeoPackage")

out_dir <- file.path(output_root, run_id)
prepared_dir <- file.path(out_dir, "prepared")
audit_dir <- file.path(out_dir, "audit")
target_dir <- file.path(out_dir, "targets")
id_dir <- file.path(out_dir, "id_maps")
dir.create(prepared_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(audit_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(target_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(id_dir, recursive = TRUE, showWarnings = FALSE)

prepared_gpkg <- file.path(prepared_dir, "gwanak_buildings_geo2vec_valid.gpkg")
prepared_layer <- "gwanak_buildings_geo2vec_valid"
id_map_path <- file.path(id_dir, "gwanak_buildings_geo2vec_id_map.parquet")
targets_path <- file.path(target_dir, "gwanak_building_geometry_targets.parquet")
exclusions_path <- file.path(audit_dir, "gwanak_building_geo2vec_exclusions.parquet")
audit_json <- file.path(audit_dir, "gwanak_building_geo2vec_phase0_audit.json")

for (path in c(prepared_gpkg, id_map_path, targets_path, exclusions_path, audit_json)) {
  replace_if_needed(path)
}

layers <- sf::st_layers(input_path, do_count = TRUE)
layer <- get_arg("layer", layers$name[[1L]])
if (!layer %in% layers$name) stop("Layer not found in input: ", layer, call. = FALSE)

buildings <- sf::st_read(input_path, layer = layer, quiet = TRUE, stringsAsFactors = FALSE)
input_rows <- nrow(buildings)
input_crs <- sf::st_crs(buildings)
if (is.na(input_crs)) stop("Input buildings have missing CRS.", call. = FALSE)
if (!identical(as.integer(input_crs$epsg), target_epsg)) {
  buildings <- sf::st_transform(buildings, target_epsg)
}
sf::st_crs(buildings) <- sf::st_crs(target_epsg)

if (!"building_id" %in% names(buildings)) {
  stop("Input buildings do not contain required stable key: building_id", call. = FALSE)
}
buildings$building_id <- as.character(buildings$building_id)

missing_id <- is.na(buildings$building_id) | buildings$building_id == ""
duplicate_id <- duplicated(buildings$building_id) | duplicated(buildings$building_id, fromLast = TRUE)
empty_before <- sf::st_is_empty(buildings)
valid_before <- sf::st_is_valid(buildings)
geom_type_before <- as.character(sf::st_geometry_type(buildings, by_geometry = TRUE))
polygon_like_before <- geom_type_before %in% c("POLYGON", "MULTIPOLYGON")

exclusions <- data.table(
  source_row = seq_len(input_rows),
  building_id = buildings$building_id,
  missing_id = missing_id,
  duplicate_id = duplicate_id,
  empty_before = empty_before,
  invalid_before = !valid_before & !empty_before,
  geometry_type_before = geom_type_before,
  non_polygon_before = !polygon_like_before
)

geom <- sf::st_geometry(buildings)
repair_idx <- which(!valid_before & !empty_before)
if (length(repair_idx)) {
  geom[repair_idx] <- sf::st_geometry(sf::st_make_valid(buildings[repair_idx, ]))
}
geom <- polygon_part(geom)
sf::st_geometry(buildings) <- geom

empty_after <- sf::st_is_empty(buildings)
valid_after <- sf::st_is_valid(buildings)
geom_type_after <- as.character(sf::st_geometry_type(buildings, by_geometry = TRUE))
polygon_like_after <- geom_type_after %in% c("POLYGON", "MULTIPOLYGON")

exclude <- missing_id | duplicate_id | empty_after | !valid_after | !polygon_like_after
exclusions[, `:=`(
  empty_after = empty_after,
  invalid_after = !valid_after & !empty_after,
  geometry_type_after = geom_type_after,
  non_polygon_after = !polygon_like_after,
  excluded = exclude,
  exclusion_reason = fifelse(missing_id, "missing_building_id",
    fifelse(duplicate_id, "duplicate_building_id",
      fifelse(empty_after, "empty_geometry_after_repair",
        fifelse(!valid_after, "invalid_geometry_after_repair",
          fifelse(!polygon_like_after, "non_polygon_geometry_after_repair", NA_character_)
        )
      )
    )
  )
)]

valid_buildings <- buildings[!exclude, ]
valid_buildings <- valid_buildings[order(valid_buildings$building_id), ]
valid_buildings$geo2vec_internal_id <- seq_len(nrow(valid_buildings)) - 1L

geom <- sf::st_geometry(valid_buildings)
area <- as.numeric(sf::st_area(geom))
perimeter <- as.numeric(sf::st_length(sf::st_boundary(geom)))
bmat <- do.call(rbind, lapply(seq_along(geom), function(i) as.numeric(sf::st_bbox(geom[i]))))
bw <- bmat[, 3] - bmat[, 1]
bh <- bmat[, 4] - bmat[, 2]
centroid <- sf::st_coordinates(sf::st_centroid(geom))
vertex_count <- vapply(geom, ring_vertex_count, integer(1))
targets <- data.table(
  building_id = valid_buildings$building_id,
  geo2vec_internal_id = as.integer(valid_buildings$geo2vec_internal_id),
  area = area,
  log_area = log1p(area),
  perimeter = perimeter,
  log_perimeter = log1p(perimeter),
  compactness = fifelse(perimeter > 0, 4 * pi * area / (perimeter^2), NA_real_),
  aspect_ratio = fifelse(pmin(bw, bh) > 0, pmax(bw, bh) / pmin(bw, bh), NA_real_),
  bbox_area_ratio = fifelse((bw * bh) > 0, area / (bw * bh), NA_real_),
  vertex_count = as.integer(vertex_count),
  centroid_x = centroid[, 1],
  centroid_y = centroid[, 2],
  bbox_width = bw,
  bbox_height = bh
)

set.seed(20260615)
targets[, random_fold := sample(rep(seq_len(5L), length.out = .N))]
targets[, split_random := fifelse(random_fold == 5L, "test", "train")]
targets[, block_x := floor((centroid_x - min(centroid_x, na.rm = TRUE)) / 500)]
targets[, block_y := floor((centroid_y - min(centroid_y, na.rm = TRUE)) / 500)]
targets[, spatial_block_id := paste(block_x, block_y, sep = "_")]
block_counts <- targets[, .N, by = spatial_block_id][order(-N, spatial_block_id)]
fold_load <- rep(0L, 5L)
block_counts[, spatial_fold := 0L]
for (i in seq_len(nrow(block_counts))) {
  fold <- which.min(fold_load)
  block_counts$spatial_fold[[i]] <- fold
  fold_load[[fold]] <- fold_load[[fold]] + block_counts$N[[i]]
}
targets <- merge(targets, block_counts[, .(spatial_block_id, spatial_fold)], by = "spatial_block_id", all.x = TRUE, sort = FALSE)
targets[, split_spatial := fifelse(spatial_fold == 5L, "test", "train")]
setorder(targets, geo2vec_internal_id)

id_map <- targets[, .(building_id, geo2vec_internal_id)]
valid_buildings <- valid_buildings[, c("building_id", "geo2vec_internal_id")]

sf::st_write(valid_buildings, prepared_gpkg, layer = prepared_layer, quiet = TRUE, delete_dsn = TRUE)
arrow::write_parquet(id_map, id_map_path, compression = "zstd")
arrow::write_parquet(targets, targets_path, compression = "zstd")
arrow::write_parquet(exclusions, exclusions_path, compression = "zstd")

bbox <- sf::st_bbox(valid_buildings)
audit <- list(
  script = "prepare_gwanak_building_geo2vec_inputs.R",
  run_id = run_id,
  input_path = input_path,
  input_layer = layer,
  input_rows = input_rows,
  source_crs = input_crs$input,
  source_epsg = input_crs$epsg,
  target_epsg = target_epsg,
  output_root = output_root,
  prepared_gpkg = prepared_gpkg,
  prepared_layer = prepared_layer,
  id_map_path = id_map_path,
  targets_path = targets_path,
  exclusions_path = exclusions_path,
  audit_json = audit_json,
  valid_rows = nrow(valid_buildings),
  excluded_rows = sum(exclusions$excluded),
  missing_id_count = sum(missing_id),
  duplicate_id_count = sum(duplicate_id),
  empty_before_count = sum(empty_before),
  invalid_before_count = sum(!valid_before & !empty_before),
  repaired_geometry_count = length(repair_idx),
  empty_after_count = sum(empty_after),
  invalid_after_count = sum(!valid_after & !empty_after),
  non_polygon_after_count = sum(!polygon_like_after),
  gwanak_bbox = as.list(as.numeric(bbox)),
  gwanak_bbox_names = names(bbox),
  random_split_counts = as.list(targets[, .N, by = split_random]),
  spatial_split_counts = as.list(targets[, .N, by = split_spatial]),
  generated_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")
)
write_json(audit_json, audit)

cat(jsonlite::toJSON(audit, auto_unbox = TRUE, pretty = TRUE, null = "null"))
cat("\n")
