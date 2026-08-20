#!/usr/bin/env Rscript

source(file.path(Sys.getenv("FUSE_REPO", "/members/dhnyu/fuse"), "R", "preprocessing_utils.R"))
suppressPackageStartupMessages({
  library(future)
  library(future.apply)
  library(terra)
})
set_single_thread_env()
cli <- parse_cli()
cfg <- load_preprocessing_config(cli$config)
ensure_preprocessing_dirs(cfg)
assert_free_space(cfg)
key <- "dem"

inspect_dem_tile <- function(entry, outer) {
  path <- vsi_zip(outer, entry)
  info <- jsonlite::fromJSON(paste(capture_cmd("gdalinfo", c("-json", path)), collapse = "\n"), simplifyVector = FALSE)
  gt <- as.numeric(unlist(info$geoTransform))
  name <- basename(entry)
  m <- regexec("^([ns])(\\d+)_([ew])(\\d+)_1arc", tolower(name))
  parts <- regmatches(tolower(name), m)[[1L]]
  if (length(parts) != 5L) stop("Unexpected SRTM tile name: ", name, call. = FALSE)
  lat <- as.integer(parts[[3L]]) * ifelse(parts[[2L]] == "s", -1L, 1L)
  lon <- as.integer(parts[[5L]]) * ifelse(parts[[4L]] == "w", -1L, 1L)
  data.table(entry = entry, path = path, tile = name, lat = lat, lon = lon,
             width = as.integer(info$size[[1L]]), height = as.integer(info$size[[2L]]),
             xres = gt[[2L]], yres = abs(gt[[6L]]), datatype = info$bands[[1L]]$type,
             nodata = as.numeric(info$bands[[1L]]$noDataValue),
             xmin = gt[[1L]], ymax = gt[[4L]], xmax = gt[[1L]] + gt[[2L]] * info$size[[1L]],
             ymin = gt[[4L]] + gt[[6L]] * info$size[[2L]],
             unit = info$bands[[1L]]$unit %||% NA_character_)
}

compare_dem_edge <- function(a_path, b_path, direction) {
  a <- terra::rast(a_path); b <- terra::rast(b_path)
  terra::readStart(a); terra::readStart(b)
  on.exit({ terra::readStop(a); terra::readStop(b) }, add = TRUE)
  if (direction == "east") {
    av <- terra::readValues(a, row = 1, nrows = nrow(a), col = ncol(a), ncols = 1, mat = FALSE)
    bv <- terra::readValues(b, row = 1, nrows = nrow(b), col = 1, ncols = 1, mat = FALSE)
  } else {
    av <- terra::readValues(a, row = nrow(a), nrows = 1, col = 1, ncols = ncol(a), mat = FALSE)
    bv <- terra::readValues(b, row = 1, nrows = 1, col = 1, ncols = ncol(b), mat = FALSE)
  }
  valid <- av != cfg$dem$nodata & bv != cfg$dem$nodata
  data.table(compared = sum(valid), mismatch = sum(valid & av != bv), max_abs_difference = if (any(valid)) max(abs(av[valid] - bv[valid])) else NA_real_)
}

with_failure_result(cfg, key, {
  started <- Sys.time()
  if (cli$mode == "production") assert_no_final_collision(cfg, key)
  outer <- source_path(cfg, key)
  entries <- list_zip_entries(outer, "(?i)\\.tif$")
  if (length(entries) != cfg$dem$expected_tiles) stop("DEM tile inventory mismatch: ", length(entries), call. = FALSE)
  if (cli$mode == "smoke") {
    entries <- entries[grepl("/(n34_e125|n34_e126|n35_e125|n35_e126)_1arc", entries, ignore.case = TRUE)]
    if (length(entries) != 4L) stop("Could not select the 2x2 DEM smoke-test tile block", call. = FALSE)
  }
  workers <- if (cli$mode == "smoke") 1L else min(cfg$runtime$dem_workers, length(entries))
  future::plan(future::multisession, workers = workers)
  on.exit(future::plan(future::sequential), add = TRUE)
  inventory <- rbindlist(future.apply::future_lapply(entries, inspect_dem_tile, outer = outer, future.seed = TRUE,
                                                      future.packages = c("data.table", "jsonlite", "yaml")))
  future::plan(future::sequential)
  if (any(inventory$width != cfg$dem$expected_tile_width | inventory$height != cfg$dem$expected_tile_height)) stop("DEM source dimensions mismatch", call. = FALSE)
  if (any(abs(inventory$xres - cfg$dem$resolution_degrees) > 1e-12 | abs(inventory$yres - cfg$dem$resolution_degrees) > 1e-12)) stop("DEM source resolution mismatch", call. = FALSE)
  if (any(inventory$datatype != cfg$dem$datatype) || any(inventory$nodata != cfg$dem$nodata)) stop("DEM datatype/nodata contract mismatch", call. = FALSE)

  run_tag <- if (cli$mode == "production") "production" else paste0("smoke_", run_id_now())
  stage_dir <- file.path(dataset_stage_dir(cfg, key), run_tag)
  dir.create(stage_dir, recursive = TRUE, showWarnings = FALSE)
  fwrite(inventory, file.path(stage_dir, "dem_tile_inventory.csv"))
  pairs <- list()
  for (i in seq_len(nrow(inventory))) {
    east <- which(inventory$lat == inventory$lat[[i]] & inventory$lon == inventory$lon[[i]] + 1L)
    north <- which(inventory$lon == inventory$lon[[i]] & inventory$lat == inventory$lat[[i]] + 1L)
    if (length(east)) pairs[[length(pairs) + 1L]] <- list(i = i, j = east[[1L]], direction = "east")
    if (length(north)) pairs[[length(pairs) + 1L]] <- list(i = north[[1L]], j = i, direction = "north")
  }
  edge_qc <- if (length(pairs)) rbindlist(lapply(pairs, function(pair) {
    q <- compare_dem_edge(inventory$path[[pair$i]], inventory$path[[pair$j]], pair$direction)
    cbind(data.table(tile_a = inventory$tile[[pair$i]], tile_b = inventory$tile[[pair$j]], direction = pair$direction), q)
  })) else data.table()
  fwrite(edge_qc, file.path(stage_dir, "dem_shared_edge_qc.csv"))
  if (nrow(edge_qc) && sum(edge_qc$mismatch) > 0) stop("DEM shared-edge values are inconsistent", call. = FALSE)

  list_file <- file.path(stage_dir, "tile_list.txt")
  writeLines(inventory$path[order(inventory$tile)], list_file)
  vrt <- file.path(stage_dir, "korea_dem.vrt")
  run_cmd("gdalbuildvrt", c("-input_file_list", list_file, "-srcnodata", as.character(cfg$dem$nodata),
                            "-vrtnodata", as.character(cfg$dem$nodata), "-resolution", "highest", vrt))
  final_stage <- file.path(stage_dir, "korea_dem.staging.tif")
  run_cmd("gdal_translate", c("-of", "COG", "-ot", cfg$dem$datatype, "-a_nodata", as.character(cfg$dem$nodata),
                               "-mo", paste0("UNIT=", cfg$dem$unit), "-mo", paste0("VERTICAL_DATUM=", cfg$dem$vertical_datum),
                               "-mo", "SOURCE_GRID=SRTM_1_ARC_SECOND", "-mo", "SHARED_EDGE_RULE=VALIDATED_EQUAL_SORTED_SOURCE_ORDER",
                               "-co", paste0("COMPRESS=", cfg$dem$compression), "-co", "PREDICTOR=YES",
                               "-co", paste0("BLOCKSIZE=", cfg$dem$blocksize), "-co", "BIGTIFF=YES",
                               "-co", "OVERVIEWS=AUTO", "-co", paste0("RESAMPLING=", cfg$dem$overview_resampling), vrt, final_stage))
  info <- jsonlite::fromJSON(paste(capture_cmd("gdalinfo", c("-json", "-stats", final_stage)), collapse = "\n"), simplifyVector = FALSE)
  gt <- as.numeric(unlist(info$geoTransform))
  resolution <- c(gt[[2L]], abs(gt[[6L]]))
  min_value <- as.numeric(info$bands[[1L]]$minimum); max_value <- as.numeric(info$bands[[1L]]$maximum)
  if (info$bands[[1L]]$type != cfg$dem$datatype || as.numeric(info$bands[[1L]]$noDataValue) != cfg$dem$nodata) stop("DEM output datatype/nodata failure", call. = FALSE)
  if (any(abs(resolution - cfg$dem$resolution_degrees) > 1e-12)) stop("DEM output resolution failure", call. = FALSE)
  if (!grepl("4326", info$coordinateSystem$wkt, fixed = TRUE)) stop("DEM output CRS failure", call. = FALSE)
  if (!identical(info$metadata$`IMAGE_STRUCTURE`$LAYOUT, "COG")) stop("DEM output is not COG", call. = FALSE)
  if (!length(info$bands[[1L]]$overviews)) stop("DEM COG has no overviews", call. = FALSE)
  if (min_value >= 0) stop("DEM negative elevations were unexpectedly lost", call. = FALSE)
  valid_percent <- as.numeric(info$bands[[1L]]$metadata[[1L]]$STATISTICS_VALID_PERCENT %||% NA_real_)
  void_pixels <- if (is.finite(valid_percent)) round(prod(unlist(info$size)) * (100 - valid_percent) / 100) else NA_real_

  qc <- list(source_tiles = nrow(inventory), edge_pairs = nrow(edge_qc), edge_mismatches = if (nrow(edge_qc)) sum(edge_qc$mismatch) else 0,
             dimensions = unlist(info$size), resolution = resolution, datatype = info$bands[[1L]]$type,
             nodata = info$bands[[1L]]$noDataValue, min = min_value, max = max_value,
             valid_percent = valid_percent, void_pixels = void_pixels, overview_count = length(info$bands[[1L]]$overviews),
             crs = "EPSG:4326", unit = cfg$dem$unit, vertical_datum = cfg$dem$vertical_datum, cog = TRUE)
  write_json_atomic(qc, file.path(stage_dir, "dem_qc.json"))
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  details <- list(mode = cli$mode, staging_path = final_stage, elapsed_sec = elapsed, workers = workers, qc = qc)
  if (cli$mode == "production") {
    final <- output_path(cfg, key)
    atomic_publish(final_stage, final)
    details$final_path <- final; details$final_size <- unname(file.info(final)$size); details$final_sha256 <- sha256_file(final)
    write_marker(cfg, key, "production_complete", details)
  }
  write_dataset_result(cfg, key, "PASS", details)
  log_line(sprintf("DEM_COMPLETE mode=%s tiles=%d pixels=%sx%s elapsed_sec=%.3f",
                   cli$mode, nrow(inventory), info$size[[1L]], info$size[[2L]], elapsed))
})
