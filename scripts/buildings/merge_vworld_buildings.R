#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
  library(readxl)
  library(digest)
  library(future)
  library(future.mirai)
  library(future.apply)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || all(is.na(x)) || identical(x, "")) y else x
}

env_int <- function(name, default) {
  value <- Sys.getenv(name, unset = "")
  if (!nzchar(value)) return(default)
  as.integer(value)
}

env_flag <- function(name, default = FALSE) {
  value <- Sys.getenv(name, unset = if (default) "true" else "false")
  tolower(value) %in% c("1", "true", "t", "yes", "y")
}

timestamp <- function() format(Sys.time(), "%Y%m%d_%H%M%S")

insert_tag <- function(path, tag) {
  if (!nzchar(tag)) return(path)
  ext <- tools::file_ext(path)
  stem <- sub(paste0("\\.", ext, "$"), "", path)
  paste0(stem, "_", tag, ".", ext)
}

format_bytes <- function(bytes) {
  units <- c("B", "KB", "MB", "GB", "TB")
  value <- as.numeric(bytes)
  unit <- 1L
  while (is.finite(value) && value >= 1024 && unit < length(units)) {
    value <- value / 1024
    unit <- unit + 1L
  }
  sprintf("%.2f %s", value, units[[unit]])
}

raw_dir <- path.expand(Sys.getenv("VWORLD_RAW_DIR", "~/fusedatalarge/raw/Building_vworld"))
output_tag <- Sys.getenv("VWORLD_OUTPUT_TAG", unset = "")
target_epsg <- env_int("VWORLD_TARGET_EPSG", 5186L)
zip_regex <- Sys.getenv("VWORLD_ZIP_REGEX", unset = "^AL_D010_.*[.]zip$")
max_zips <- env_int("VWORLD_MAX_ZIPS", NA_integer_)
chunk_size <- env_int("VWORLD_CHUNK_SIZE", 100000L)
workers <- env_int("VWORLD_WORKERS", max(1L, min(40L, parallelly::availableCores(), 48L)))
layer_name <- Sys.getenv("VWORLD_GPKG_LAYER", unset = "buildings")
assume_target_crs_if_missing <- env_flag("VWORLD_ASSUME_TARGET_CRS_IF_MISSING", FALSE)
keep_temp <- env_flag("VWORLD_KEEP_TEMP", FALSE)

out_gpkg <- insert_tag(path.expand(Sys.getenv(
  "VWORLD_OUTPUT_GPKG",
  "~/fusedatalarge/processed/korea_buildings_vworld.gpkg"
)), output_tag)
out_parquet <- insert_tag(path.expand(Sys.getenv(
  "VWORLD_OUTPUT_PARQUET",
  "~/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet"
)), output_tag)
summary_parquet <- insert_tag(path.expand(Sys.getenv(
  "VWORLD_SUMMARY_PARQUET",
  "~/fusedatalarge/processed/korea_building_merge_summary.parquet"
)), output_tag)
log_file <- insert_tag(path.expand(Sys.getenv(
  "VWORLD_LOG_FILE",
  "~/fusedatalarge/processed/korea_building_merge.log"
)), output_tag)
storage_doc <- insert_tag(path.expand(Sys.getenv(
  "VWORLD_STORAGE_DOC",
  "~/fusedatalarge/processed/korea_building_storage_design.md"
)), output_tag)
temp_root <- path.expand(Sys.getenv(
  "VWORLD_TEMP_ROOT",
  file.path(tempdir(), paste0("korea_vworld_building_merge_", timestamp(), if (nzchar(output_tag)) paste0("_", output_tag) else ""))
))

for (path in c(out_gpkg, out_parquet, summary_parquet, log_file, storage_doc, temp_root)) {
  dir.create(if (grepl("[.][A-Za-z0-9]+$", basename(path))) dirname(path) else path, recursive = TRUE, showWarnings = FALSE)
}

preopen_log_backup <- NA_character_
if (file.exists(log_file)) {
  preopen_log_backup <- paste0(log_file, ".bak_", timestamp())
  if (!file.rename(log_file, preopen_log_backup)) {
    stop("Failed to back up existing log before opening: ", log_file)
  }
  message("Backed up existing log before opening: ", log_file, " -> ", preopen_log_backup)
}

log_con <- file(log_file, open = "at", encoding = "UTF-8")
on.exit(close(log_con), add = TRUE)

log_msg <- function(...) {
  line <- sprintf("[%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), paste(..., collapse = " "))
  cat(line, "\n")
  writeLines(line, log_con, useBytes = TRUE)
  flush(log_con)
}

backup_if_exists <- function(path) {
  if (!file.exists(path)) return(NA_character_)
  backup_path <- paste0(path, ".bak_", timestamp())
  if (!file.rename(path, backup_path)) stop("Failed to back up existing output: ", path)
  log_msg("Backed up existing output:", path, "->", backup_path)
  backup_path
}

list_metadata_files <- function(root) {
  files <- list.files(root, recursive = TRUE, full.names = TRUE, all.files = FALSE)
  files[
    grepl("[.](xlsx|xls|csv|txt)$", files, ignore.case = TRUE) |
      grepl("readme|metadata|codebook|definition|정의|코드", basename(files), ignore.case = TRUE)
  ]
}

read_column_definition <- function(files) {
  xlsx_files <- files[grepl("[.]xlsx?$", files, ignore.case = TRUE)]
  out <- list()
  for (xlsx in xlsx_files) {
    sheets <- readxl::excel_sheets(xlsx)
    if (!"테이블정의서(전체)" %in% sheets) next
    raw <- readxl::read_excel(xlsx, sheet = "테이블정의서(전체)", skip = 4, col_names = FALSE)
    dt <- as.data.table(raw)
    if (ncol(dt) < 17L) next
    setnames(dt, paste0("V", seq_len(ncol(dt))))
    dt <- dt[V4 == "AL_D010"]
    if (!nrow(dt)) next
    out[[length(out) + 1L]] <- dt[, .(
      metadata_file = basename(xlsx),
      dataset_group = as.character(V2),
      dataset_name = as.character(V3),
      file_code = as.character(V4),
      field_order = suppressWarnings(as.integer(V6)),
      field_name = as.character(V7),
      field_label_ko = as.character(V8),
      field_length = as.character(V9),
      required = as.character(V10),
      notes = as.character(V17)
    )]
  }
  rbindlist(out, fill = TRUE)
}

safe_name <- function(x) gsub("[^A-Za-z0-9_]+", "_", x)

unzip_archives <- function(zip_files, unzip_root) {
  rows <- vector("list", length(zip_files))
  for (i in seq_along(zip_files)) {
    zip_path <- zip_files[[i]]
    source_zip <- basename(zip_path)
    extract_dir <- file.path(unzip_root, tools::file_path_sans_ext(source_zip))
    dir.create(extract_dir, recursive = TRUE, showWarnings = FALSE)
    inv <- as.data.table(utils::unzip(zip_path, list = TRUE))
    inv[, `:=`(
      source_zip = source_zip,
      source_zip_path = zip_path,
      extract_dir = extract_dir,
      extension = tolower(tools::file_ext(Name)),
      is_shapefile = tolower(tools::file_ext(Name)) == "shp"
    )]
    utils::unzip(zip_path, exdir = extract_dir)
    rows[[i]] <- inv
    log_msg("Unzipped", source_zip, "to", extract_dir)
  }
  rbindlist(rows, fill = TRUE)
}

inspect_layers <- function(inventory) {
  shp <- inventory[is_shapefile == TRUE]
  rows <- vector("list", nrow(shp))
  for (i in seq_len(nrow(shp))) {
    source_zip <- shp$source_zip[[i]]
    member <- shp$Name[[i]]
    layer_path <- file.path(shp$extract_dir[[i]], member)
    source_layer <- tools::file_path_sans_ext(basename(layer_path))
    info <- try(sf::st_layers(dirname(layer_path), do_count = TRUE), silent = TRUE)
    if (inherits(info, "try-error") || !source_layer %in% info$name) {
      rows[[i]] <- data.table(
        source_zip = source_zip,
        source_layer = source_layer,
        layer_path = layer_path,
        geometry_type = NA_character_,
        feature_count = NA_integer_,
        crs_input = NA_character_,
        inspect_status = "failed",
        inspect_error = as.character(info)
      )
      next
    }
    idx <- match(source_layer, info$name)
    geometry_type <- as.character(info$geomtype[[idx]])
    is_polygon <- grepl("POLYGON", geometry_type, ignore.case = TRUE)
    rows[[i]] <- data.table(
      source_zip = source_zip,
      source_layer = source_layer,
      layer_path = layer_path,
      geometry_type = geometry_type,
      feature_count = as.integer(info$features[[idx]]),
      crs_input = as.character(info$crs$name[[idx]] %||% NA_character_),
      inspect_status = if (is_polygon) "ok_polygon" else "skipped_non_polygon",
      inspect_error = NA_character_
    )
  }
  rbindlist(rows, fill = TRUE)
}

create_task_table <- function(layers, chunk_size, chunk_root) {
  polygon_layers <- layers[inspect_status == "ok_polygon" & !is.na(feature_count) & feature_count > 0L]
  tasks <- list()
  task_id <- 0L
  for (i in seq_len(nrow(polygon_layers))) {
    n <- polygon_layers$feature_count[[i]]
    starts <- seq.int(1L, n, by = chunk_size)
    ends <- pmin(starts + chunk_size - 1L, n)
    for (j in seq_along(starts)) {
      task_id <- task_id + 1L
      chunk_key <- sprintf("%05d_%s_%s_%04d", task_id, safe_name(polygon_layers$source_zip[[i]]), safe_name(polygon_layers$source_layer[[i]]), j)
      chunk_dir <- file.path(chunk_root, chunk_key)
      tasks[[task_id]] <- data.table(
        task_id = task_id,
        source_zip = polygon_layers$source_zip[[i]],
        source_layer = polygon_layers$source_layer[[i]],
        layer_path = polygon_layers$layer_path[[i]],
        geometry_type = polygon_layers$geometry_type[[i]],
        chunk_id = j,
        start_feature = starts[[j]],
        end_feature = ends[[j]],
        chunk_size = ends[[j]] - starts[[j]] + 1L,
        chunk_dir = chunk_dir,
        chunk_gpkg = file.path(chunk_dir, "geometry.gpkg"),
        chunk_parquet = file.path(chunk_dir, "attributes.parquet"),
        chunk_summary = file.path(chunk_dir, "summary.parquet")
      )
    }
  }
  rbindlist(tasks, fill = TRUE)
}

make_building_id <- function(source_zip, source_layer, source_feature_index, geometry) {
  geom_hash <- vapply(
    sf::st_as_binary(geometry, EWKB = TRUE),
    digest::digest,
    character(1),
    algo = "xxhash64",
    serialize = FALSE
  )
  key <- paste(source_zip, source_layer, source_feature_index, geom_hash, sep = "|")
  paste0("vworld_", vapply(key, digest::digest, character(1), algo = "xxhash64", serialize = FALSE))
}

safe_attributes <- function(x) {
  dt <- as.data.table(sf::st_drop_geometry(x))
  for (nm in names(dt)) {
    if (inherits(dt[[nm]], "POSIXt")) dt[, (nm) := as.character(get(nm))]
    if (inherits(dt[[nm]], "Date")) dt[, (nm) := as.character(get(nm))]
  }
  dt
}

process_chunk <- function(task, target_epsg, assume_target_crs_if_missing, layer_name) {
  started_at <- Sys.time()
  task <- as.data.table(task)
  dir.create(task$chunk_dir, recursive = TRUE, showWarnings = FALSE)

  summary <- data.table(
    task_id = task$task_id,
    source_zip = task$source_zip,
    source_layer = task$source_layer,
    geometry_type = task$geometry_type,
    chunk_id = task$chunk_id,
    start_feature = task$start_feature,
    end_feature = task$end_feature,
    input_feature_count = NA_integer_,
    output_feature_count = 0L,
    invalid_geometry_count_before = NA_integer_,
    invalid_geometry_count_after = NA_integer_,
    duplicate_count_dropped = 0L,
    empty_geometry_count_dropped = NA_integer_,
    crs_input = NA_character_,
    crs_output = as.character(target_epsg),
    processing_status = "started",
    error_message = NA_character_,
    chunk_gpkg = task$chunk_gpkg,
    chunk_parquet = task$chunk_parquet,
    chunk_summary = task$chunk_summary,
    started_at = as.character(started_at),
    finished_at = NA_character_
  )

  tryCatch({
    layer <- task$source_layer
    start0 <- task$start_feature - 1L
    end0 <- task$end_feature - 1L
    query <- sprintf("SELECT * FROM \"%s\" WHERE FID >= %d AND FID <= %d", layer, start0, end0)
    x <- sf::st_read(
      dirname(task$layer_path),
      query = query,
      quiet = TRUE,
      options = c("ENCODING=CP949"),
      stringsAsFactors = FALSE
    )
    n_input <- nrow(x)
    crs_in <- sf::st_crs(x)
    if (is.na(crs_in) && assume_target_crs_if_missing) {
      sf::st_crs(x) <- target_epsg
      crs_in <- sf::st_crs(x)
    }
    if (is.na(crs_in)) stop("Input CRS is missing")

    x$source_feature_index <- seq.int(task$start_feature, length.out = nrow(x))
    valid_before <- sf::st_is_valid(x)
    valid_before[is.na(valid_before)] <- FALSE
    invalid_before <- sum(!valid_before)
    if (!identical(sf::st_crs(x)$epsg, target_epsg)) {
      x <- sf::st_transform(x, target_epsg)
    }
    if (invalid_before > 0L) {
      x[!valid_before, ] <- sf::st_make_valid(x[!valid_before, ])
    }
    if (any(sf::st_geometry_type(x, by_geometry = TRUE) == "GEOMETRYCOLLECTION", na.rm = TRUE)) {
      x <- suppressWarnings(sf::st_collection_extract(x, "POLYGON"))
    }
    x <- x[grepl("POLYGON", as.character(sf::st_geometry_type(x, by_geometry = TRUE))), , drop = FALSE]
    if (nrow(x)) {
      x <- suppressWarnings(sf::st_cast(x, "MULTIPOLYGON", warn = FALSE))
      empty <- sf::st_is_empty(x)
      if (any(empty)) x <- x[!empty, , drop = FALSE]
    } else {
      empty <- logical()
    }

    valid_after <- if (nrow(x)) sf::st_is_valid(x) else logical()
    valid_after[is.na(valid_after)] <- FALSE
    invalid_after <- sum(!valid_after)
    x <- x[valid_after, , drop = FALSE]

    if (!nrow(x)) {
      summary[, `:=`(
        input_feature_count = n_input,
        invalid_geometry_count_before = invalid_before,
        invalid_geometry_count_after = invalid_after,
        empty_geometry_count_dropped = sum(empty),
        crs_input = as.character(crs_in$epsg %||% crs_in$input %||% crs_in$wkt),
        processing_status = "ok_empty_after_cleaning",
        finished_at = as.character(Sys.time())
      )]
      arrow::write_parquet(summary, task$chunk_summary)
      return(summary)
    }

    x$source_zip <- task$source_zip
    x$source_layer <- task$source_layer
    x$building_id <- make_building_id(task$source_zip, task$source_layer, x$source_feature_index, sf::st_geometry(x))

    attrs <- safe_attributes(x)
    attrs[, `:=`(
      processed_at = as.character(Sys.time()),
      target_epsg = target_epsg,
      geometry_layer = layer_name
    )]
    setcolorder(attrs, c("building_id", setdiff(names(attrs), "building_id")))

    geom <- x[, c("building_id", attr(x, "sf_column")), drop = FALSE]
    names(geom)[names(geom) == attr(x, "sf_column")] <- "geometry"
    sf::st_geometry(geom) <- "geometry"

    sf::st_write(geom, task$chunk_gpkg, layer = layer_name, delete_layer = TRUE, quiet = TRUE)
    arrow::write_parquet(attrs, task$chunk_parquet)

    summary[, `:=`(
      input_feature_count = n_input,
      output_feature_count = nrow(geom),
      invalid_geometry_count_before = invalid_before,
      invalid_geometry_count_after = invalid_after,
      empty_geometry_count_dropped = sum(empty),
      crs_input = as.character(crs_in$epsg %||% crs_in$input %||% crs_in$wkt),
      crs_output = as.character(sf::st_crs(geom)$epsg %||% target_epsg),
      processing_status = "ok",
      finished_at = as.character(Sys.time())
    )]
    arrow::write_parquet(summary, task$chunk_summary)
    summary
  }, error = function(e) {
    summary[, `:=`(
      processing_status = "failed",
      error_message = conditionMessage(e),
      finished_at = as.character(Sys.time())
    )]
    arrow::write_parquet(summary, task$chunk_summary)
    summary
  })
}

write_storage_doc <- function(path, gpkg_path, parquet_path, summary_path, target_epsg, chunk_size) {
  lines <- c(
    "# Korea VWorld Building Storage Design",
    "",
    "The canonical nationwide VWorld building output uses split storage so geometry-heavy spatial reads stay small and analytical attribute reads remain columnar.",
    "",
    "## Files",
    "",
    paste0("- Geometry GeoPackage: `", gpkg_path, "`"),
    "- Layer: `buildings`",
    "- GeoPackage columns: `building_id`, `geometry`",
    paste0("- Attribute Parquet: `", parquet_path, "`"),
    "- Attribute Parquet columns: `building_id`, original non-geometry VWorld attributes, `source_zip`, `source_layer`, `source_feature_index`, and processing metadata columns.",
    paste0("- Summary Parquet: `", summary_path, "`"),
    "",
    "## Processing",
    "",
    paste0("Raw archives are unzipped into a controlled temporary directory, polygon layers are split into chunks of about ", chunk_size, " features, and chunks are processed in parallel with `future_mirai`. Each chunk writes temporary geometry-only and attribute outputs before the final canonical outputs are merged."),
    "",
    "## Join Key",
    "",
    "`building_id` is the stable join key between the GeoPackage and Parquet outputs. It is generated deterministically from the source archive, source layer, source feature index, and final geometry WKB hash.",
    "",
    "## CRS",
    "",
    paste0("Final geometry CRS: EPSG:", target_epsg, "."),
    "",
    "## Example R Join",
    "",
    "```r",
    "library(sf)",
    "library(arrow)",
    "library(dplyr)",
    "",
    paste0("buildings_geom <- st_read(\"", gpkg_path, "\", layer = \"buildings\", quiet = TRUE)"),
    paste0("building_attrs <- read_parquet(\"", parquet_path, "\")"),
    "",
    "buildings <- buildings_geom %>%",
    "  left_join(building_attrs, by = \"building_id\")",
    "```"
  )
  writeLines(lines, path, useBytes = TRUE)
}

merge_geometry_chunks <- function(chunk_files, out_gpkg, layer_name) {
  first <- TRUE
  for (chunk_file in chunk_files) {
    g <- sf::st_read(chunk_file, layer = layer_name, quiet = TRUE)
    sf::st_write(g, out_gpkg, layer = layer_name, append = !first, delete_layer = first, quiet = TRUE)
    first <- FALSE
  }
}

merge_attribute_chunks <- function(chunk_files, out_parquet) {
  attrs <- rbindlist(lapply(chunk_files, function(path) {
    as.data.table(arrow::read_parquet(path, as_data_frame = TRUE))
  }), fill = TRUE)
  arrow::write_parquet(attrs, out_parquet)
  invisible(nrow(attrs))
}

validate_outputs <- function(gpkg_path, parquet_path, layer_name, target_epsg) {
  if (!file.exists(gpkg_path)) stop("GeoPackage missing: ", gpkg_path)
  if (!file.exists(parquet_path)) stop("Attribute Parquet missing: ", parquet_path)
  layers <- sf::st_layers(gpkg_path, do_count = TRUE)
  if (!layer_name %in% layers$name) stop("GeoPackage layer missing: ", layer_name)

  geom <- sf::st_read(gpkg_path, layer = layer_name, quiet = TRUE)
  geom_cols <- names(sf::st_drop_geometry(geom))
  if (!identical(geom_cols, "building_id")) {
    stop("GeoPackage must contain only building_id plus geometry; found: ", paste(geom_cols, collapse = ", "))
  }
  if (anyDuplicated(geom$building_id)) stop("Duplicate building_id values in GeoPackage")
  if (!identical(sf::st_crs(geom)$epsg, target_epsg)) stop("Unexpected GeoPackage CRS")
  geom_types <- unique(as.character(sf::st_geometry_type(geom, by_geometry = TRUE)))
  bad_types <- setdiff(geom_types, c("POLYGON", "MULTIPOLYGON"))
  if (length(bad_types)) stop("Unexpected geometry types: ", paste(bad_types, collapse = ", "))

  attrs <- as.data.table(arrow::read_parquet(parquet_path, as_data_frame = TRUE))
  if (!"building_id" %in% names(attrs)) stop("building_id missing from Attribute Parquet")
  if (anyDuplicated(attrs$building_id)) stop("Duplicate building_id values in Attribute Parquet")
  if (nrow(attrs) != nrow(geom)) stop("GeoPackage and Attribute Parquet row counts differ")
  if (!setequal(attrs$building_id, geom$building_id)) stop("GeoPackage and Attribute Parquet building_id sets differ")

  list(
    feature_count = nrow(geom),
    crs = sf::st_crs(geom)$epsg,
    geometry_types = paste(sort(unique(geom_types)), collapse = ";"),
    gpkg_size_bytes = file.info(gpkg_path)$size,
    parquet_size_bytes = file.info(parquet_path)$size,
    attribute_columns = ncol(attrs)
  )
}

log_msg("Starting nationwide VWorld building merge")
log_msg("Raw directory:", raw_dir)
log_msg("Target EPSG:", target_epsg)
log_msg("Chunk size:", chunk_size)
log_msg("Workers requested:", workers)
log_msg("Temporary root:", temp_root)
log_msg("Output GeoPackage:", out_gpkg)
log_msg("Output Attribute Parquet:", out_parquet)
log_msg("Output Summary Parquet:", summary_parquet)
log_msg("Output log:", log_file)

if (!dir.exists(raw_dir)) stop("Raw directory does not exist: ", raw_dir)

metadata_files <- list_metadata_files(raw_dir)
metadata_definition <- read_column_definition(metadata_files)
log_msg("Metadata/codebook files found:", if (length(metadata_files)) paste(basename(metadata_files), collapse = "; ") else "none")
log_msg("AL_D010 metadata rows:", nrow(metadata_definition))

zip_files <- list.files(raw_dir, pattern = "[.]zip$", full.names = TRUE, ignore.case = TRUE)
zip_files <- sort(zip_files[grepl(zip_regex, basename(zip_files), ignore.case = TRUE)])
if (!length(zip_files)) stop("No raw VWorld archives matched regex: ", zip_regex)
if (!is.na(max_zips)) zip_files <- head(zip_files, max_zips)

start_time <- Sys.time()
inventory <- unzip_archives(zip_files, file.path(temp_root, "unzipped"))
layers <- inspect_layers(inventory)
tasks <- create_task_table(layers, chunk_size, file.path(temp_root, "chunks"))
if (!nrow(tasks)) stop("No polygon layer chunk tasks were created")

workers <- max(1L, min(workers, nrow(tasks)))
log_msg("Raw zip files selected:", length(zip_files))
log_msg("Building polygon layers:", layers[inspect_status == "ok_polygon", .N])
log_msg("Skipped layers:", layers[inspect_status != "ok_polygon", .N])
log_msg("Chunk tasks:", nrow(tasks))
log_msg("Using future.mirai chunk-level parallelism with workers:", workers)

existing_outputs <- c(out_gpkg, out_parquet, summary_parquet, log_file, storage_doc)
existing_outputs <- existing_outputs[file.exists(existing_outputs)]
if (length(existing_outputs)) {
  log_msg("Existing outputs before run:", paste(existing_outputs, collapse = "; "))
} else {
  log_msg("Existing outputs before run: none")
}

future::plan(future.mirai::mirai_multisession, workers = workers)
options(future.globals.maxSize = Inf)
on.exit(future::plan(future::sequential), add = TRUE)

chunk_results <- future.apply::future_lapply(
  split(tasks, tasks$task_id),
  process_chunk,
  target_epsg = target_epsg,
  assume_target_crs_if_missing = assume_target_crs_if_missing,
  layer_name = layer_name,
  future.seed = TRUE
)
end_time <- Sys.time()

summary_dt <- rbindlist(chunk_results, fill = TRUE)
failures <- summary_dt[processing_status == "failed"]
if (nrow(failures)) {
  arrow::write_parquet(summary_dt, summary_parquet)
  log_msg("Processing failed for", nrow(failures), "chunk(s). Summary written:", summary_parquet)
  stop("One or more chunks failed; see summary parquet and log.")
}

ok_chunks <- summary_dt[processing_status == "ok"]
if (!nrow(ok_chunks)) stop("No non-empty building chunks were produced")

backup_gpkg <- backup_if_exists(out_gpkg)
backup_parquet <- backup_if_exists(out_parquet)
backup_summary <- backup_if_exists(summary_parquet)
backup_doc <- backup_if_exists(storage_doc)

log_msg("Merging", nrow(ok_chunks), "geometry chunk GeoPackages")
merge_geometry_chunks(ok_chunks$chunk_gpkg, out_gpkg, layer_name)

log_msg("Merging", nrow(ok_chunks), "attribute chunk Parquets")
merge_attribute_chunks(ok_chunks$chunk_parquet, out_parquet)

summary_dt[, `:=`(
  run_started_at = as.character(start_time),
  run_finished_at = as.character(end_time),
  workers_used = workers,
  chunk_size_config = chunk_size,
  raw_archives_selected = length(zip_files),
  polygon_layers_processed = layers[inspect_status == "ok_polygon", .N],
  skipped_layers = layers[inspect_status != "ok_polygon", .N],
  final_feature_count = sum(summary_dt$output_feature_count, na.rm = TRUE),
  output_gpkg = out_gpkg,
  output_parquet = out_parquet,
  output_summary = summary_parquet,
  metadata_files = paste(basename(metadata_files), collapse = "; "),
  metadata_al_d010_rows = nrow(metadata_definition),
  backup_gpkg = backup_gpkg,
  backup_parquet = backup_parquet,
  backup_summary = backup_summary,
  backup_storage_doc = backup_doc,
  backup_log = preopen_log_backup
)]

layer_summary <- layers[, .(
  task_id = NA_integer_,
  source_zip,
  source_layer,
  geometry_type,
  chunk_id = NA_integer_,
  start_feature = NA_integer_,
  end_feature = NA_integer_,
  input_feature_count = feature_count,
  output_feature_count = NA_integer_,
  invalid_geometry_count_before = NA_integer_,
  invalid_geometry_count_after = NA_integer_,
  duplicate_count_dropped = NA_integer_,
  empty_geometry_count_dropped = NA_integer_,
  crs_input,
  crs_output = as.character(target_epsg),
  processing_status = inspect_status,
  error_message = inspect_error,
  chunk_gpkg = NA_character_,
  chunk_parquet = NA_character_,
  chunk_summary = NA_character_,
  started_at = NA_character_,
  finished_at = NA_character_
)]

inventory_summary <- inventory[, .(
  task_id = NA_integer_,
  source_zip,
  source_layer = NA_character_,
  geometry_type = NA_character_,
  chunk_id = NA_integer_,
  start_feature = NA_integer_,
  end_feature = NA_integer_,
  input_feature_count = NA_integer_,
  output_feature_count = NA_integer_,
  invalid_geometry_count_before = NA_integer_,
  invalid_geometry_count_after = NA_integer_,
  duplicate_count_dropped = NA_integer_,
  empty_geometry_count_dropped = NA_integer_,
  crs_input = NA_character_,
  crs_output = as.character(target_epsg),
  processing_status = ifelse(is_shapefile, "archive_shapefile_member", "archive_aux_member"),
  error_message = paste0("member=", Name, "; length_bytes=", Length),
  chunk_gpkg = NA_character_,
  chunk_parquet = NA_character_,
  chunk_summary = NA_character_,
  started_at = NA_character_,
  finished_at = NA_character_
)]

metadata_summary <- metadata_definition[, .(
  task_id = NA_integer_,
  source_zip = NA_character_,
  source_layer = NA_character_,
  geometry_type = NA_character_,
  chunk_id = NA_integer_,
  start_feature = NA_integer_,
  end_feature = NA_integer_,
  input_feature_count = NA_integer_,
  output_feature_count = NA_integer_,
  invalid_geometry_count_before = NA_integer_,
  invalid_geometry_count_after = NA_integer_,
  duplicate_count_dropped = NA_integer_,
  empty_geometry_count_dropped = NA_integer_,
  crs_input = NA_character_,
  crs_output = as.character(target_epsg),
  processing_status = "metadata_field",
  error_message = paste(field_name, field_label_ko, required, notes, sep = " | "),
  chunk_gpkg = NA_character_,
  chunk_parquet = NA_character_,
  chunk_summary = NA_character_,
  started_at = NA_character_,
  finished_at = NA_character_
)]

for (dt in list(layer_summary, inventory_summary, metadata_summary)) {
  dt[, `:=`(
    run_started_at = as.character(start_time),
    run_finished_at = as.character(end_time),
    workers_used = workers,
    chunk_size_config = chunk_size,
    raw_archives_selected = length(zip_files),
    polygon_layers_processed = layers[inspect_status == "ok_polygon", .N],
    skipped_layers = layers[inspect_status != "ok_polygon", .N],
    final_feature_count = sum(summary_dt$output_feature_count, na.rm = TRUE),
    output_gpkg = out_gpkg,
    output_parquet = out_parquet,
    output_summary = summary_parquet,
    metadata_files = paste(basename(metadata_files), collapse = "; "),
    metadata_al_d010_rows = nrow(metadata_definition),
    backup_gpkg = backup_gpkg,
    backup_parquet = backup_parquet,
    backup_summary = backup_summary,
    backup_storage_doc = backup_doc,
    backup_log = preopen_log_backup
  )]
}

summary_out <- rbindlist(list(summary_dt, layer_summary, inventory_summary, metadata_summary), fill = TRUE)
arrow::write_parquet(summary_out, summary_parquet)
write_storage_doc(storage_doc, out_gpkg, out_parquet, summary_parquet, target_epsg, chunk_size)

validation <- validate_outputs(out_gpkg, out_parquet, layer_name, target_epsg)
previous_all_attribute_size <- if (!is.na(backup_gpkg) && file.exists(backup_gpkg)) file.info(backup_gpkg)$size else NA_real_
smaller_than_previous <- if (is.na(previous_all_attribute_size)) NA else validation$gpkg_size_bytes < previous_all_attribute_size

log_msg("Validation feature count:", validation$feature_count)
log_msg("Validation CRS:", validation$crs)
log_msg("Validation geometry types:", validation$geometry_types)
log_msg("GeoPackage size:", format_bytes(validation$gpkg_size_bytes))
log_msg("Attribute Parquet size:", format_bytes(validation$parquet_size_bytes))
log_msg("Previous backed-up GeoPackage size:", if (is.na(previous_all_attribute_size)) "not available" else format_bytes(previous_all_attribute_size))
log_msg("Geometry-only GeoPackage smaller than previous backed-up design:", as.character(smaller_than_previous))
log_msg("Finished nationwide VWorld building merge")

if (!keep_temp) {
  unlink(temp_root, recursive = TRUE, force = TRUE)
  log_msg("Removed temporary root:", temp_root)
} else {
  log_msg("Kept temporary root:", temp_root)
}
