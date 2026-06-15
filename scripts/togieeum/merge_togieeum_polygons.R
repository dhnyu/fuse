#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
  library(readxl)
  library(digest)
  library(future)
  library(future.apply)
  library(future.mirai)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || all(is.na(x)) || identical(x, "")) y else x
}

cfg <- list(
  root = path.expand(Sys.getenv("TOGIEEUM_ROOT", "/members/dhnyu/fusedatalarge/raw/togieeum")),
  processed_dir = path.expand(Sys.getenv("TOGIEEUM_PROCESSED_DIR", "/members/dhnyu/fusedatalarge/processed")),
  temp_dir = path.expand(Sys.getenv("TOGIEEUM_TEMP_DIR", file.path(tempdir(), "korea_togieeum_polygon_merge"))),
  chunk_size = as.integer(Sys.getenv("TOGIEEUM_CHUNK_SIZE", "1000")),
  workers = as.integer(Sys.getenv("TOGIEEUM_WORKERS", "40")),
  source_encoding = Sys.getenv("TOGIEEUM_SOURCE_ENCODING", "CP949"),
  target_crs = 5186L,
  assumed_raw_crs = 5174L
)

paths <- list(
  inventory = file.path(cfg$processed_dir, "togieeum_inventory.parquet"),
  layer_catalog = file.path(cfg$processed_dir, "togieeum_layer_catalog.parquet"),
  gpkg = file.path(cfg$processed_dir, "korea_togieeum_polygon.gpkg"),
  attributes = file.path(cfg$processed_dir, "korea_togieeum_polygon_attributes.parquet"),
  summary = file.path(cfg$processed_dir, "korea_togieeum_polygon_merge_summary.parquet"),
  dropped_invalid = file.path(cfg$processed_dir, "korea_togieeum_dropped_invalid_geometries.parquet"),
  log = file.path(cfg$processed_dir, "korea_togieeum_polygon_merge.log"),
  storage_design = file.path(cfg$processed_dir, "korea_togieeum_polygon_storage_design.md")
)

dir.create(cfg$processed_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(cfg$temp_dir, "geometry"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(cfg$temp_dir, "attributes"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(cfg$temp_dir, "summary"), recursive = TRUE, showWarnings = FALSE)
dir.create(file.path(cfg$temp_dir, "dropped_invalid"), recursive = TRUE, showWarnings = FALSE)

log_con <- file(paths$log, open = "at", encoding = "UTF-8")
sink(log_con, append = TRUE, split = TRUE)
sink(log_con, append = TRUE, type = "message")
on.exit({
  sink(type = "message")
  sink()
  close(log_con)
}, add = TRUE)

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), paste(..., collapse = " ")))
}

backup_existing <- function(path) {
  if (!file.exists(path)) return(NA_character_)
  backup <- sprintf("%s.bak_%s", path, format(Sys.time(), "%Y%m%d_%H%M%S"))
  ok <- file.rename(path, backup)
  if (!ok) stop("Failed to back up existing output: ", path)
  log_msg("Backed up", path, "to", backup)
  backup
}

write_storage_design <- function(path) {
  text <- c(
    "# Korea Togieeum Polygon Canonical Storage Design",
    "",
    "This pipeline merges KLIP and UPIS Togieeum polygon layers into one nationwide Korea polygon dataset.",
    "",
    "Included source layers are `C_UQ151` through `C_UQ159` from `KLIP_003_*.zip` and `UPIS_003_*.zip`. The `TN_RIVER_BT` source is intentionally excluded.",
    "",
    "Classification is stored in two forms:",
    "",
    "- `uq_code`: original layer family code, such as `C_UQ151`; stored only in the attribute Parquet.",
    "- `uq_number`: numeric family code, such as `151`; stored in both outputs.",
    "",
    "The GeoPackage is intentionally class-light and contains only:",
    "",
    "- `togieeum_id`",
    "- `uq_number`",
    "- `geometry`",
    "",
    "Full non-geometry attributes and source metadata are stored in Parquet. The stable join key between geometry and attributes is `togieeum_id`.",
    "",
    "The final geometry CRS is EPSG:5186. Source CRS is verified from the layer metadata and the source appears to be EPSG:5174.",
    "",
    "Processing uses deterministic layer-chunk tasks, approximately 1,000 features per chunk by default, with the `future.mirai` `mirai_multisession` backend.",
    "",
    "Example R join:",
    "",
    "```r",
    "library(sf)",
    "library(arrow)",
    "library(data.table)",
    "",
    "geom <- st_read(",
    "  \"/members/dhnyu/fusedatalarge/processed/korea_togieeum_polygon.gpkg\",",
    "  layer = \"polygons\",",
    "  quiet = TRUE",
    ")",
    "attrs <- as.data.table(read_parquet(",
    "  \"/members/dhnyu/fusedatalarge/processed/korea_togieeum_polygon_attributes.parquet\"",
    "))",
    "",
    "geom_full <- merge(geom, attrs, by = \"togieeum_id\", all.x = TRUE)",
    "```"
  )
  writeLines(text, path, useBytes = TRUE)
}

vsi_zip_dsn <- function(zip_path) {
  paste0("/vsizip/", normalizePath(zip_path, mustWork = TRUE))
}

read_sf_chunk <- function(source_path, source_layer, start_feature, end_feature, source_encoding) {
  dsn <- vsi_zip_dsn(source_path)
  n <- end_feature - start_feature + 1L
  offset <- start_feature - 1L
  sql <- sprintf('SELECT * FROM "%s" LIMIT %d OFFSET %d', source_layer, n, offset)
  read_args <- list(dsn = dsn, quiet = TRUE, stringsAsFactors = FALSE)
  if (nzchar(source_encoding)) read_args$options <- paste0("ENCODING=", source_encoding)

  chunk <- try(do.call(sf::st_read, c(read_args, list(query = sql))), silent = TRUE)
  if (!inherits(chunk, "try-error")) return(chunk)

  log_msg("Chunk SQL read failed for", basename(source_path), source_layer, "falling back to layer read")
  all_layer <- do.call(sf::st_read, c(read_args, list(layer = source_layer)))
  all_layer[seq.int(start_feature, min(end_feature, nrow(all_layer))), , drop = FALSE]
}

safe_st_make_valid <- function(x) {
  repaired <- try(sf::st_make_valid(x), silent = TRUE)
  if (inherits(repaired, "try-error")) {
    log_msg("st_make_valid failed; using buffer(0) fallback")
    repaired <- sf::st_buffer(x, 0)
  }
  repaired
}

validity_reason <- function(geom) {
  out <- try(sf::st_is_valid(geom, reason = TRUE), silent = TRUE)
  if (inherits(out, "try-error")) rep(NA_character_, length(geom)) else as.character(out)
}

empty_dropped_invalid_dt <- function() {
  data.table(
    togieeum_id = character(),
    source_system = character(),
    source_zip = character(),
    source_layer = character(),
    source_feature_index = integer(),
    uq_code = character(),
    uq_number = integer(),
    original_validity_reason = character(),
    post_repair_validity_reason = character()
  )
}

hash_geometry <- function(geom) {
  vapply(sf::st_as_binary(geom, EWKB = TRUE), digest, character(1), algo = "xxhash64", serialize = FALSE)
}

make_ids <- function(dt, geom_hash) {
  present_col <- names(dt)[toupper(names(dt)) == "PRESENT_SN"][1]
  present <- if (!is.na(present_col)) as.character(dt[[present_col]]) else rep(NA_character_, nrow(dt))
  id_seed <- paste(
    dt$source_system,
    dt$source_zip,
    dt$source_layer,
    dt$source_feature_index,
    fifelse(is.na(present), "", present),
    geom_hash,
    sep = "|"
  )
  paste0("tog_", vapply(id_seed, digest, character(1), algo = "xxhash64", serialize = FALSE))
}

process_chunk <- function(task) {
  suppressPackageStartupMessages({
    library(sf)
    library(data.table)
    library(arrow)
    library(digest)
  })
  sf::sf_use_s2(FALSE)

  task <- as.list(task)
  chunk_key <- sprintf("%s_%s_%s_chunk%05d", task$source_system, task$region_code %||% "NA", task$uq_code, task$chunk_id)
  geom_out <- file.path(task$temp_geometry_dir, paste0(chunk_key, ".gpkg"))
  attr_out <- file.path(task$temp_attribute_dir, paste0(chunk_key, ".parquet"))
  summary_out <- file.path(task$temp_summary_dir, paste0(chunk_key, ".parquet"))
  dropped_invalid_out <- file.path(task$temp_dropped_invalid_dir, paste0(chunk_key, ".parquet"))

  started_at <- Sys.time()
  x <- read_sf_chunk(task$source_path, task$source_layer, task$start_feature, task$end_feature, task$source_encoding)
  input_n <- nrow(x)
  crs_in <- sf::st_crs(x)$epsg
  if (is.na(crs_in)) {
    sf::st_crs(x) <- task$assumed_raw_crs
    crs_in <- task$assumed_raw_crs
  }

  geom_before <- sf::st_geometry(x)
  invalid_before <- sum(!sf::st_is_valid(geom_before), na.rm = TRUE)
  original_validity_reason <- validity_reason(geom_before)
  empty_before <- sum(sf::st_is_empty(geom_before), na.rm = TRUE)

  x$source_feature_index <- seq.int(task$start_feature, task$start_feature + input_n - 1L)
  x$original_validity_reason <- original_validity_reason
  x <- sf::st_transform(x, task$target_crs)
  x <- safe_st_make_valid(x)
  x <- suppressWarnings(sf::st_collection_extract(x, "POLYGON"))

  geom_type <- as.character(sf::st_geometry_type(x, by_geometry = TRUE))
  keep_poly <- geom_type %chin% c("POLYGON", "MULTIPOLYGON")
  keep_non_empty <- !sf::st_is_empty(x)
  keep_rows <- keep_poly & keep_non_empty
  empty_geometries_dropped <- sum(!keep_non_empty, na.rm = TRUE)
  non_polygon_dropped <- sum(!keep_poly & keep_non_empty, na.rm = TRUE)
  x <- x[keep_rows, , drop = FALSE]
  x <- sf::st_cast(x, "MULTIPOLYGON", warn = FALSE)

  post_repair_validity_reason <- validity_reason(sf::st_geometry(x))
  valid_after_repair <- sf::st_is_valid(sf::st_geometry(x))
  valid_after_repair[is.na(valid_after_repair)] <- FALSE
  invalid_after <- sum(!valid_after_repair, na.rm = TRUE)
  empty_after <- sum(sf::st_is_empty(sf::st_geometry(x)), na.rm = TRUE)
  repaired_feature_count <- nrow(x)

  if (!repaired_feature_count) {
    geom_dt <- sf::st_sf(
      togieeum_id = character(),
      uq_number = integer(),
      geometry = sf::st_sfc(crs = task$target_crs)
    )
    sf::st_write(geom_dt, geom_out, layer = "polygons", delete_dsn = TRUE, quiet = TRUE)
    arrow::write_parquet(data.table(togieeum_id = character()), attr_out)
    arrow::write_parquet(empty_dropped_invalid_dt(), dropped_invalid_out)
  } else {
    attrs <- data.table(sf::st_drop_geometry(x))
    source_feature_index <- attrs$source_feature_index
    attrs[, original_validity_reason := NULL]
    attrs[, `:=`(
      source_system = task$source_system,
      uq_code = task$uq_code,
      uq_number = as.integer(task$uq_number),
      source_zip = task$source_zip,
      source_layer = task$source_layer,
      source_feature_index = source_feature_index
    )]
    if (!"region_code" %in% names(attrs)) attrs[, region_code := task$region_code]
    attrs[, `:=`(
      processing_chunk_id = task$chunk_id,
      processing_started_at = format(started_at, "%Y-%m-%dT%H:%M:%OS%z"),
      processing_finished_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%OS%z"),
      processing_target_crs = task$target_crs,
      processing_source_crs = crs_in
    )]

    geom_hash <- hash_geometry(sf::st_geometry(x))
    attrs[, togieeum_id := make_ids(attrs, geom_hash)]
    x$togieeum_id <- attrs$togieeum_id
    x$uq_number <- as.integer(task$uq_number)

    dropped_invalid <- data.table(
      togieeum_id = attrs$togieeum_id[!valid_after_repair],
      source_system = task$source_system,
      source_zip = task$source_zip,
      source_layer = task$source_layer,
      source_feature_index = attrs$source_feature_index[!valid_after_repair],
      uq_code = task$uq_code,
      uq_number = as.integer(task$uq_number),
      original_validity_reason = x$original_validity_reason[!valid_after_repair],
      post_repair_validity_reason = post_repair_validity_reason[!valid_after_repair]
    )
    if (!nrow(dropped_invalid)) dropped_invalid <- empty_dropped_invalid_dt()
    arrow::write_parquet(dropped_invalid, dropped_invalid_out)

    attrs <- attrs[valid_after_repair]
    x <- x[valid_after_repair, , drop = FALSE]

    dup <- duplicated(attrs$togieeum_id)
    duplicates_dropped <- sum(dup)
    if (duplicates_dropped) {
      attrs <- attrs[!dup]
      x <- x[!dup, c("togieeum_id", "uq_number")]
    } else {
      x <- x[, c("togieeum_id", "uq_number")]
    }

    sf::st_write(x, geom_out, layer = "polygons", delete_dsn = TRUE, quiet = TRUE)
    arrow::write_parquet(attrs, attr_out)
  }

  summary <- data.table(
    source_system = task$source_system,
    source_zip = task$source_zip,
    source_layer = task$source_layer,
    uq_code = task$uq_code,
    uq_number = as.integer(task$uq_number),
    region_code = task$region_code,
    chunk_id = task$chunk_id,
    start_feature = task$start_feature,
    end_feature = task$end_feature,
    input_features = input_n,
    output_features = if (exists("attrs")) nrow(attrs) else 0L,
    invalid_geometries_before = invalid_before,
    invalid_geometries_after = invalid_after,
    empty_geometries_before = empty_before,
    empty_geometries_after = empty_after,
    repaired_feature_count = repaired_feature_count,
    empty_geometries_dropped = empty_geometries_dropped,
    non_polygon_dropped = non_polygon_dropped,
    invalid_geometries_dropped = invalid_after,
    duplicates_dropped = if (exists("duplicates_dropped")) duplicates_dropped else 0L,
    crs_input_epsg = crs_in,
    crs_output_epsg = task$target_crs,
    geometry_chunk_path = geom_out,
    attribute_chunk_path = attr_out,
    dropped_invalid_chunk_path = dropped_invalid_out,
    processing_started_at = format(started_at, "%Y-%m-%dT%H:%M:%OS%z"),
    processing_finished_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%OS%z")
  )
  arrow::write_parquet(summary, summary_out)
  summary
}

build_tasks <- function(inventory, chunk_size) {
  x <- inventory[
    source_system %chin% c("KLIP", "UPIS") &
      file_type == "shp" &
      geometry_class == "polygon" &
      grepl("^C_UQ15[1-9]$", layer_family) &
      !grepl("TN_RIVER_BT", source_path, ignore.case = TRUE) &
      !grepl("TN_RIVER_BT", source_zip, ignore.case = TRUE) &
      !grepl("TN_RIVER_BT", layer_name, ignore.case = TRUE)
  ]
  x[, uq_code := layer_family]
  x[, uq_number := as.integer(sub("^C_UQ", "", uq_code))]
  x <- x[order(source_system, source_zip, layer_name)]

  task_list <- vector("list", nrow(x))
  for (i in seq_len(nrow(x))) {
    n <- x$feature_count[[i]]
    starts <- seq.int(1L, n, by = chunk_size)
    ends <- pmin(starts + chunk_size - 1L, n)
    task_list[[i]] <- data.table(
      source_system = x$source_system[[i]],
      source_zip = x$source_zip[[i]],
      source_path = x$source_path[[i]],
      region_code = x$region_code[[i]],
      source_layer = x$layer_name[[i]],
      uq_code = x$uq_code[[i]],
      uq_number = x$uq_number[[i]],
      chunk_id = seq_along(starts),
      start_feature = starts,
      end_feature = ends,
      feature_count = n,
      crs_epsg_catalog = x$crs_epsg[[i]]
    )
  }
  rbindlist(task_list)
}

merge_geometry_chunks <- function(chunk_paths, final_gpkg) {
  backup_existing(final_gpkg)
  first <- TRUE
  for (p in chunk_paths) {
    g <- sf::st_read(p, layer = "polygons", quiet = TRUE)
    if (!nrow(g)) next
    if (first) {
      sf::st_write(g, final_gpkg, layer = "polygons", delete_dsn = TRUE, quiet = TRUE)
      first <- FALSE
    } else {
      sf::st_write(g, final_gpkg, layer = "polygons", append = TRUE, quiet = TRUE)
    }
  }
  if (first) stop("No geometry features were written to final GeoPackage")
}

merge_attribute_chunks <- function(chunk_paths, final_parquet) {
  backup_existing(final_parquet)
  attrs <- rbindlist(lapply(chunk_paths, function(p) as.data.table(arrow::read_parquet(p))), fill = TRUE, use.names = TRUE)
  setcolorder(attrs, c("togieeum_id", setdiff(names(attrs), "togieeum_id")))
  arrow::write_parquet(attrs, final_parquet)
}

merge_dropped_invalid_chunks <- function(chunk_paths, final_parquet) {
  backup_existing(final_parquet)
  dropped <- rbindlist(lapply(chunk_paths, function(p) as.data.table(arrow::read_parquet(p))), fill = TRUE, use.names = TRUE)
  if (!nrow(dropped)) {
    arrow::write_parquet(empty_dropped_invalid_dt(), final_parquet)
    return(invisible(dropped))
  }
  setcolorder(dropped, c("togieeum_id", setdiff(names(dropped), "togieeum_id")))
  arrow::write_parquet(dropped, final_parquet)
  invisible(dropped)
}

validate_outputs <- function(summary_dt, tasks) {
  stopifnot(file.exists(paths$gpkg))
  layers <- sf::st_layers(paths$gpkg)$name
  if (!"polygons" %in% layers) stop("GeoPackage layer 'polygons' is missing")

  geom <- sf::st_read(paths$gpkg, layer = "polygons", quiet = TRUE)
  geom_cols <- names(sf::st_drop_geometry(geom))
  expected_geom_cols <- c("togieeum_id", "uq_number")
  if (!identical(geom_cols, expected_geom_cols)) {
    stop("Unexpected GeoPackage columns: ", paste(geom_cols, collapse = ", "))
  }
  if (sf::st_crs(geom)$epsg != cfg$target_crs) stop("GeoPackage CRS is not EPSG:", cfg$target_crs)
  if (any(!as.character(sf::st_geometry_type(geom, by_geometry = TRUE)) %chin% c("POLYGON", "MULTIPOLYGON"))) {
    stop("GeoPackage contains non-polygon geometries")
  }
  final_invalid_geometry_count <- sum(!sf::st_is_valid(sf::st_geometry(geom)), na.rm = TRUE)
  if (final_invalid_geometry_count != 0L) stop("Final GeoPackage contains invalid geometries: ", final_invalid_geometry_count)

  attrs <- as.data.table(arrow::read_parquet(paths$attributes))
  needed <- c("togieeum_id", "source_system", "uq_code", "uq_number", "source_zip", "source_layer", "source_feature_index")
  missing <- setdiff(needed, names(attrs))
  if (length(missing)) stop("Attribute Parquet is missing columns: ", paste(missing, collapse = ", "))

  if (anyDuplicated(geom$togieeum_id)) stop("Duplicate togieeum_id values in GeoPackage")
  if (anyDuplicated(attrs$togieeum_id)) stop("Duplicate togieeum_id values in attribute Parquet")
  if (!setequal(geom$togieeum_id, attrs$togieeum_id)) stop("togieeum_id sets do not match")
  if (any(grepl("TN_RIVER_BT", attrs$source_zip, ignore.case = TRUE) | grepl("TN_RIVER_BT", attrs$source_layer, ignore.case = TRUE))) {
    stop("TN_RIVER_BT records are present")
  }
  if (!all(c("KLIP", "UPIS") %chin% attrs$source_system)) stop("Both KLIP and UPIS are not present in attributes")
  if (sum(summary_dt$invalid_geometries_dropped, na.rm = TRUE) > 0L && !file.exists(paths$dropped_invalid)) {
    stop("Dropped invalid geometry diagnostic Parquet is missing")
  }

  expected_uq <- sort(unique(tasks$uq_number))
  actual_uq <- sort(unique(geom$uq_number))
  missing_uq <- setdiff(expected_uq, actual_uq)
  if (length(missing_uq)) log_msg("Expected uq_number values absent after processing:", paste(missing_uq, collapse = ", "))

  list(
    final_feature_count = nrow(geom),
    gpkg_size = file.info(paths$gpkg)$size,
    attributes_size = file.info(paths$attributes)$size,
    dropped_invalid_size = if (file.exists(paths$dropped_invalid)) file.info(paths$dropped_invalid)$size else NA_real_,
    crs = sf::st_crs(geom)$epsg,
    final_invalid_geometry_count = final_invalid_geometry_count,
    uq_counts = as.data.table(sf::st_drop_geometry(geom))[, .N, by = uq_number][order(uq_number)],
    source_counts = attrs[, .N, by = source_system][order(source_system)],
    unique_geom_ids = uniqueN(geom$togieeum_id),
    unique_attr_ids = uniqueN(attrs$togieeum_id)
  )
}

main <- function() {
  log_msg("Starting Korea Togieeum polygon merge")
  log_msg("Workers:", cfg$workers, "Chunk size:", cfg$chunk_size)
  backup_existing(paths$storage_design)
  write_storage_design(paths$storage_design)

  if (!file.exists(paths$inventory)) stop("Missing inventory: ", paths$inventory)
  inventory <- as.data.table(arrow::read_parquet(paths$inventory))
  tasks <- build_tasks(inventory, cfg$chunk_size)
  if (!nrow(tasks)) stop("No KLIP/UPIS C_UQ151-C_UQ159 polygon layer tasks found")

  tasks[, `:=`(
    temp_geometry_dir = file.path(cfg$temp_dir, "geometry"),
    temp_attribute_dir = file.path(cfg$temp_dir, "attributes"),
    temp_summary_dir = file.path(cfg$temp_dir, "summary"),
    temp_dropped_invalid_dir = file.path(cfg$temp_dir, "dropped_invalid"),
    source_encoding = cfg$source_encoding,
    assumed_raw_crs = cfg$assumed_raw_crs,
    target_crs = cfg$target_crs
  )]

  task_path <- file.path(cfg$temp_dir, "korea_togieeum_polygon_layer_chunk_tasks.parquet")
  arrow::write_parquet(tasks, task_path)
  log_msg("Task table written:", task_path)
  log_msg("Chunk tasks:", nrow(tasks), "Zip files:", uniqueN(tasks$source_zip), "Polygon layers:", uniqueN(paste(tasks$source_zip, tasks$source_layer)))
  log_msg("Input feature count:", sum(tasks[, .SD[1L], by = .(source_zip, source_layer)]$feature_count))

  future::plan(future.mirai::mirai_multisession, workers = cfg$workers)
  on.exit(future::plan(future::sequential), add = TRUE)
  summaries <- future.apply::future_lapply(
    seq_len(nrow(tasks)),
    function(i) process_chunk(tasks[i]),
    future.seed = TRUE,
    future.packages = c("sf", "data.table", "arrow", "digest")
  )
  summary_dt <- rbindlist(summaries, fill = TRUE, use.names = TRUE)
  backup_existing(paths$summary)
  arrow::write_parquet(summary_dt, paths$summary)
  log_msg("Summary written:", paths$summary)

  merge_geometry_chunks(summary_dt$geometry_chunk_path, paths$gpkg)
  merge_attribute_chunks(summary_dt$attribute_chunk_path, paths$attributes)
  merge_dropped_invalid_chunks(summary_dt$dropped_invalid_chunk_path, paths$dropped_invalid)

  validation <- validate_outputs(summary_dt, tasks)
  log_msg("Validation passed")

  if (isTRUE(as.logical(Sys.getenv("TOGIEEUM_KEEP_TEMP", "FALSE")))) {
    log_msg("Keeping temp files because TOGIEEUM_KEEP_TEMP=TRUE")
  } else {
    unlink(cfg$temp_dir, recursive = TRUE)
    log_msg("Temporary files cleaned:", cfg$temp_dir)
  }

  log_msg("Final feature count:", validation$final_feature_count)
  log_msg("Input feature count:", sum(summary_dt$input_features))
  log_msg("Repaired feature count:", sum(summary_dt$repaired_feature_count))
  log_msg("Empty geometries dropped:", sum(summary_dt$empty_geometries_dropped))
  log_msg("Non-polygon geometries dropped:", sum(summary_dt$non_polygon_dropped))
  log_msg("Invalid geometries before/drop:", sum(summary_dt$invalid_geometries_before), "/", sum(summary_dt$invalid_geometries_dropped))
  log_msg("Final invalid geometry count:", validation$final_invalid_geometry_count)
  log_msg("Duplicates dropped:", sum(summary_dt$duplicates_dropped))
  log_msg("GeoPackage bytes:", validation$gpkg_size)
  log_msg("Attribute Parquet bytes:", validation$attributes_size)
  log_msg("CRS EPSG:", validation$crs)
  log_msg("uq_number counts:", paste(sprintf("%s=%s", validation$uq_counts$uq_number, validation$uq_counts$N), collapse = ", "))
  log_msg("source_system counts:", paste(sprintf("%s=%s", validation$source_counts$source_system, validation$source_counts$N), collapse = ", "))
  log_msg("togieeum_id unique counts geom/parquet:", validation$unique_geom_ids, "/", validation$unique_attr_ids)
  log_msg("Outputs:", paths$gpkg, paths$attributes, paths$summary, paths$log, paths$storage_design)

  invisible(list(tasks = tasks, summary = summary_dt, validation = validation))
}

if (isTRUE(as.logical(Sys.getenv("TOGIEEUM_RUN_MAIN", "TRUE")))) {
  main()
}
