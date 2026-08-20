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
key <- "landcover"

inspect_tile <- function(entry, outer) {
  dataset <- vsi_nested_zip(outer, entry)
  info <- jsonlite::fromJSON(paste(capture_cmd("ogrinfo", c("-json", "-so", "-al", dataset)), collapse = "\n"), simplifyVector = FALSE)
  layer <- info$layers[[1L]]
  extent <- unlist(layer$geometryFields[[1L]]$extent, use.names = FALSE)
  csv <- capture_cmd("ogr2ogr", c("-f", "CSV", "/vsistdout/", dataset, "-dialect", "SQLite", "-sql",
                                  sprintf('SELECT DISTINCT L2_CODE,L2_NAME FROM "%s"', layer$name)))
  legend <- data.table::fread(text = paste(csv, collapse = "\n"), colClasses = "character")
  data.table(entry = entry, tile_id = sub("^.*SG04_([0-9]+)_.*$", "\\1", entry), dataset = dataset,
             layer = layer$name, source_count = as.numeric(layer$featureCount),
             xmin = extent[[1L]], ymin = extent[[2L]], xmax = extent[[3L]], ymax = extent[[4L]],
             legend = list(legend))
}

rasterize_tile <- function(task, stage_dir, code_to_value) {
  set_single_thread_env()
  out <- file.path(stage_dir, "tiles", paste0(task$tile_id, ".tif"))
  dissolved <- file.path(stage_dir, "dissolved", paste0(task$tile_id, ".fgb"))
  done <- paste0(out, ".done.json")
  if (file.exists(out) && file.exists(dissolved) && file.exists(done)) {
    d <- read_json(done, simplifyVector = TRUE)
    return(data.table(tile_id = task$tile_id, raster = out, source_count = d$source_count,
                      unique_count = d$unique_count, duplicate_count = d$duplicate_count,
                      conflict_pixels = d$conflict_pixels, xmin = task$xmin, ymin = task$ymin,
                      xmax = task$xmax, ymax = task$ymax))
  }
  case_sql <- paste(sprintf("WHEN '%s' THEN %d", names(code_to_value), as.integer(code_to_value)), collapse = " ")
  layer <- gsub('"', '""', task$layer, fixed = TRUE)
  sql <- sprintf(paste0("SELECT L2_CODE, MIN(L2_NAME) AS L2_NAME, CASE L2_CODE %s END AS raster_value, ",
                        "ST_Union(geometry) AS geometry FROM (SELECT DISTINCT L2_CODE,L2_NAME,geometry FROM \"%s\") ",
                        "GROUP BY L2_CODE"), case_sql, layer)
  if (file.exists(dissolved)) unlink(dissolved)
  run_cmd("ogr2ogr", c("-f", "FlatGeobuf", dissolved, task$dataset, "--config", "SHAPE_ENCODING", "CP949",
                        "-dialect", "SQLite", "-sql", sql, "-nln", "landcover_dissolved", "-nlt", "MULTIPOLYGON"))
  unique_count <- as.numeric(ogr_scalar(task$dataset,
    sprintf('SELECT COUNT(*) AS n FROM (SELECT DISTINCT L2_CODE,L2_NAME,geometry FROM "%s")', layer), "n"))
  duplicate_count <- task$source_count - unique_count

  conflict <- file.path(stage_dir, "conflicts", paste0(task$tile_id, ".tif"))
  common <- c("-tr", cfg$landcover$resolution, cfg$landcover$resolution,
              "-te", sprintf("%.15f", task$xmin), sprintf("%.15f", task$ymin),
              sprintf("%.15f", task$xmax), sprintf("%.15f", task$ymax),
              "-ot", "Byte", "-init", "0", "-a_nodata", "0",
              "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-co", "BIGTIFF=IF_SAFER")
  run_cmd("gdal_rasterize", c("-burn", "1", "-add", common, dissolved, conflict))
  cinfo <- jsonlite::fromJSON(paste(capture_cmd("gdalinfo", c("-json", "-stats", conflict)), collapse = "\n"), simplifyVector = FALSE)
  cmax <- as.numeric(cinfo$bands[[1L]]$maximum)
  conflict_pixels <- if (cmax <= 1) 0 else {
    r <- terra::rast(conflict)
    as.numeric(terra::global(r > 1, "sum", na.rm = TRUE)[1, 1])
  }
  if (conflict_pixels > 0) stop(sprintf("LANDCOVER_CATEGORY_CONFLICT tile=%s pixels=%d", task$tile_id, conflict_pixels), call. = FALSE)
  if (file.exists(out)) unlink(out)
  run_cmd("gdal_rasterize", c("-a", "raster_value", common, dissolved, out))
  write_json_atomic(list(tile_id = task$tile_id, source_count = task$source_count, unique_count = unique_count,
                         duplicate_count = duplicate_count, conflict_pixels = conflict_pixels, timestamp = kst_now()), done)
  data.table(tile_id = task$tile_id, raster = out, source_count = task$source_count,
             unique_count = unique_count, duplicate_count = duplicate_count, conflict_pixels = conflict_pixels,
             xmin = task$xmin, ymin = task$ymin, xmax = task$xmax, ymax = task$ymax)
}

compare_tile_overlap <- function(pair, paths) {
  set_single_thread_env()
  a <- terra::rast(paths[[pair$i]])
  b <- terra::rast(paths[[pair$j]])
  overlap <- terra::intersect(terra::ext(a), terra::ext(b))
  if (is.null(overlap) || overlap$xmax <= overlap$xmin || overlap$ymax <= overlap$ymin) return(c(conflict = 0, same = 0))
  res <- cfg$landcover$resolution
  offsets <- c((overlap$xmin - terra::xmin(a)) / res, (overlap$xmin - terra::xmin(b)) / res,
               (terra::ymax(a) - overlap$ymax) / res, (terra::ymax(b) - overlap$ymax) / res,
               (overlap$xmax - overlap$xmin) / res, (overlap$ymax - overlap$ymin) / res)
  if (any(abs(offsets - round(offsets)) > 1e-6)) {
    stop(sprintf("Land-cover overlap is off the 5 m source lattice: tile_a=%s tile_b=%s residual=%g",
                 pair$i, pair$j, max(abs(offsets - round(offsets)))), call. = FALSE)
  }
  ncols <- as.integer(round((overlap$xmax - overlap$xmin) / res))
  nrows <- as.integer(round((overlap$ymax - overlap$ymin) / res))
  if (ncols < 1L || nrows < 1L) return(c(conflict = 0, same = 0))
  read_window <- function(r) {
    col <- as.integer(round((overlap$xmin - terra::xmin(r)) / res)) + 1L
    row <- as.integer(round((terra::ymax(r) - overlap$ymax) / res)) + 1L
    terra::readStart(r)
    on.exit(terra::readStop(r), add = TRUE)
    terra::readValues(r, row = row, nrows = nrows, col = col, ncols = ncols, mat = FALSE)
  }
  av <- read_window(a)
  bv <- read_window(b)
  if (length(av) != length(bv)) stop("Land-cover overlap pixel-window size mismatch", call. = FALSE)
  both <- av != 0 & bv != 0
  c(conflict = sum(both & av != bv, na.rm = TRUE), same = sum(both & av == bv, na.rm = TRUE))
}

with_failure_result(cfg, key, {
  started <- Sys.time()
  if (cli$mode == "production") assert_no_final_collision(cfg, key)
  outer <- source_path(cfg, key)
  entries <- list_zip_entries(outer, "(?i)\\.zip$")
  if (length(entries) != cfg$landcover$expected_tiles) stop("Land-cover tile inventory mismatch: ", length(entries), call. = FALSE)
  if (cli$mode == "smoke") entries <- entries[1:2]
  workers <- if (cli$mode == "smoke") 1L else min(cfg$runtime$landcover_workers, length(entries))
  future::plan(future::multisession, workers = workers)
  on.exit(future::plan(future::sequential), add = TRUE)
  inspected <- future.apply::future_lapply(entries, inspect_tile, outer = outer, future.seed = TRUE,
                                            future.packages = c("data.table", "jsonlite", "yaml"))
  inventory <- rbindlist(inspected)
  legend <- unique(rbindlist(inventory$legend, fill = TRUE))
  legend[, L2_CODE := trimws(as.character(L2_CODE))]
  legend[, code_order__ := as.numeric(L2_CODE)]
  setorder(legend, code_order__)
  legend[, code_order__ := NULL]
  if (uniqueN(legend$L2_CODE) > cfg$landcover$expected_classes) stop("Unexpected land-cover class cardinality", call. = FALSE)
  all_codes <- sprintf("%03d", c(110,120,130,140,150,160,210,220,230,240,250,310,320,330,410,420,510,520,610,620,710,720))
  code_to_value <- setNames(seq_along(all_codes), all_codes)
  if (!all(legend$L2_CODE %in% all_codes)) stop("Unexpected L2_CODE in source", call. = FALSE)

  run_tag <- if (cli$mode == "production") "production" else paste0("smoke_", run_id_now())
  stage_dir <- file.path(dataset_stage_dir(cfg, key), run_tag)
  for (sub in c("tiles", "dissolved", "conflicts", "ledgers")) dir.create(file.path(stage_dir, sub), recursive = TRUE, showWarnings = FALSE)
  rows <- split(inventory, seq_len(nrow(inventory)))
  staged_list <- future.apply::future_lapply(rows, rasterize_tile, stage_dir = stage_dir, code_to_value = code_to_value,
                                              future.seed = TRUE, future.packages = c("data.table", "jsonlite", "terra", "yaml"))
  future::plan(future::sequential)
  staged <- rbindlist(staged_list)
  fwrite(staged, file.path(stage_dir, "landcover_tile_qc.csv"))
  if (cli$mode == "production") {
    if (sum(staged$source_count) != cfg$landcover$expected_source_records) stop("Land-cover source feature count mismatch", call. = FALSE)
    if (sum(staged$duplicate_count) != cfg$landcover$expected_within_tile_duplicates) stop("Land-cover exact duplicate count mismatch", call. = FALSE)
  }
  fwrite(staged[, .(tile_id, source_count, unique_count, duplicate_count, reason_code = "EXACT_SAME_GEOMETRY_AND_CATEGORY")],
         file.path(stage_dir, "ledgers", "landcover_exact_duplicate_ledger.csv"))

  pairs <- list()
  for (i in seq_len(nrow(staged) - 1L)) {
    js <- which(seq_len(nrow(staged)) > i & staged$xmin < staged$xmax[[i]] & staged$xmax > staged$xmin[[i]] &
                  staged$ymin < staged$ymax[[i]] & staged$ymax > staged$ymin[[i]])
    if (length(js)) pairs <- c(pairs, lapply(js, function(j) list(i = i, j = j)))
  }
  overlap_qc <- if (length(pairs)) rbindlist(lapply(pairs, function(pair) {
    q <- compare_tile_overlap(pair, staged$raster)
    data.table(tile_a = staged$tile_id[[pair$i]], tile_b = staged$tile_id[[pair$j]],
               conflict_pixels = q[["conflict"]], same_pixels = q[["same"]])
  })) else data.table(tile_a = character(), tile_b = character(), conflict_pixels = numeric(), same_pixels = numeric())
  fwrite(overlap_qc, file.path(stage_dir, "landcover_cross_tile_overlap_qc.csv"))
  if (sum(overlap_qc$conflict_pixels) > 0) stop("LANDCOVER_CROSS_TILE_CATEGORY_CONFLICT", call. = FALSE)

  list_file <- file.path(stage_dir, "tile_list.txt")
  writeLines(sort(staged$raster), list_file)
  vrt <- file.path(stage_dir, "korea_lc.vrt")
  run_cmd("gdalbuildvrt", c("-input_file_list", list_file, "-srcnodata", "0", "-vrtnodata", "0", "-resolution", "highest", vrt))
  final_stage <- file.path(stage_dir, "korea_lc.staging.tif")
  mapping <- data.table(raster_value = unname(code_to_value), L2_CODE = names(code_to_value))
  mapping <- merge(mapping, legend, by = "L2_CODE", all.x = TRUE, sort = FALSE)
  setorder(mapping, raster_value)
  mapping_csv <- file.path(stage_dir, "korea_lc_categories.csv")
  fwrite(mapping, mapping_csv, bom = TRUE)
  metadata_args <- unlist(lapply(seq_len(nrow(mapping)), function(i) c("-mo", sprintf("LC_VALUE_%02d=%s|%s", mapping$raster_value[[i]], mapping$L2_CODE[[i]], mapping$L2_NAME[[i]]))))
  run_cmd("gdal_translate", c("-of", "COG", "-ot", "Byte", "-a_nodata", "0", metadata_args,
                               "-co", paste0("COMPRESS=", cfg$landcover$compression),
                               "-co", paste0("BLOCKSIZE=", cfg$landcover$blocksize), "-co", "BIGTIFF=YES",
                               "-co", "OVERVIEWS=AUTO", "-co", paste0("RESAMPLING=", cfg$landcover$overview_resampling),
                               vrt, final_stage))
  info <- jsonlite::fromJSON(paste(capture_cmd("gdalinfo", c("-json", "-stats", final_stage)), collapse = "\n"), simplifyVector = FALSE)
  values_min <- as.numeric(info$bands[[1L]]$minimum); values_max <- as.numeric(info$bands[[1L]]$maximum)
  resolution <- c(as.numeric(info$geoTransform[[2L]]), abs(as.numeric(info$geoTransform[[6L]])))
  if (any(abs(resolution - cfg$landcover$resolution) > 1e-9)) stop("Land-cover output resolution mismatch", call. = FALSE)
  if (values_min < 0 || values_max > 22) stop("Land-cover raster value range failure", call. = FALSE)
  if (!identical(as.numeric(info$bands[[1L]]$noDataValue), 0)) stop("Land-cover nodata mismatch", call. = FALSE)
  if (!grepl("5186", info$coordinateSystem$wkt, fixed = TRUE)) stop("Land-cover CRS mismatch", call. = FALSE)
  image_structure <- info$metadata$`IMAGE_STRUCTURE`
  if (!identical(image_structure$LAYOUT, "COG")) stop("Land-cover output is not COG", call. = FALSE)
  if (!length(info$bands[[1L]]$overviews)) stop("Land-cover COG has no overviews", call. = FALSE)

  qc <- list(source_tiles = nrow(staged), source_records = sum(staged$source_count),
             unique_records = sum(staged$unique_count), exact_duplicates_removed = sum(staged$duplicate_count),
             within_tile_conflict_pixels = sum(staged$conflict_pixels), cross_tile_conflict_pixels = sum(overlap_qc$conflict_pixels),
             dimensions = unlist(info$size), resolution = resolution, extent = unlist(info$cornerCoordinates),
             min = values_min, max = values_max, nodata = info$bands[[1L]]$noDataValue,
             overview_count = length(info$bands[[1L]]$overviews), cog = TRUE)
  write_json_atomic(qc, file.path(stage_dir, "landcover_qc.json"))
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  details <- list(mode = cli$mode, staging_path = final_stage, category_manifest = mapping_csv,
                  elapsed_sec = elapsed, workers = workers, qc = qc)
  if (cli$mode == "production") {
    final <- output_path(cfg, key)
    atomic_publish(final_stage, final)
    details$final_path <- final; details$final_size <- unname(file.info(final)$size); details$final_sha256 <- sha256_file(final)
    write_marker(cfg, key, "production_complete", details)
  }
  write_dataset_result(cfg, key, "PASS", details)
  log_line(sprintf("LANDCOVER_COMPLETE mode=%s tiles=%d pixels=%sx%s elapsed_sec=%.3f",
                   cli$mode, nrow(staged), info$size[[1L]], info$size[[2L]], elapsed))
})
