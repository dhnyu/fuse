#!/usr/bin/env Rscript

source(file.path(Sys.getenv("FUSE_REPO", "/members/dhnyu/fuse"), "R", "preprocessing_utils.R"))
suppressPackageStartupMessages({
  library(future)
  library(future.apply)
})
set_single_thread_env()
cli <- parse_cli()
cfg <- load_preprocessing_config(cli$config)
ensure_preprocessing_dirs(cfg)
assert_free_space(cfg)

key <- "building"

sql_literal <- function(x) gsub("'", "''", x, fixed = TRUE)
sanitize_name <- function(x) gsub("[^A-Za-z0-9_]+", "_", x)

hex_to_raw <- function(value) {
  starts <- seq.int(1L, nchar(value), by = 2L)
  as.raw(strtoi(substring(value, starts, starts + 1L), base = 16L))
}

write_invalid_geometry_ledger <- function(gpkg, ledger_path) {
  raw_path <- paste0(ledger_path, ".with_wkb_hex.csv")
  if (file.exists(raw_path)) unlink(raw_path)
  sql <- paste0(
    "SELECT building_feature_id, A0 AS source_A0, A1 AS source_A1, ",
    "source_archive, source_region, source_layer, source_record_index, ",
    "'INVALID_GEOMETRY' AS reason_code, ST_IsValidReason(geom) AS ST_IsValidReason, ",
    "HEX(ST_AsBinary(geom)) AS original_wkb_hex ",
    "FROM buildings WHERE NOT ST_IsValid(geom) ORDER BY building_feature_id"
  )
  run_cmd("ogr2ogr", c("-f", "CSV", raw_path, gpkg, "-dialect", "SQLite", "-sql", sql, "-nlt", "NONE"))
  ledger <- fread(raw_path, colClasses = list(character = c("source_A1", "original_wkb_hex")))
  ledger[, original_wkb_sha256 := vapply(
    original_wkb_hex,
    function(value) digest::digest(hex_to_raw(value), algo = "sha256", serialize = FALSE),
    character(1L)
  )]
  ledger[, original_wkb_hex := NULL]
  fwrite(ledger, ledger_path, bom = TRUE)
  unlink(raw_path)
  ledger
}

parse_layers <- function(dataset) {
  out <- capture_cmd("ogrinfo", c("-ro", "-so", "-al", dataset), env = "SHAPE_ENCODING=CP949")
  starts <- grep("^Layer name: ", out)
  if (!length(starts)) stop("No building layers found in ", dataset, call. = FALSE)
  ends <- c(starts[-1L] - 1L, length(out))
  rbindlist(lapply(seq_along(starts), function(i) {
    block <- out[starts[[i]]:ends[[i]]]
    layer <- sub("^Layer name: ", "", block[[1L]])
    count_line <- grep("^Feature Count: ", block, value = TRUE)
    geometry_line <- grep("^Geometry: ", block, value = TRUE)
    data.table(
      layer = layer,
      source_count = as.numeric(sub("^Feature Count: ", "", count_line[[1L]])),
      geometry = sub("^Geometry: ", "", geometry_line[[1L]])
    )
  }))
}

stage_one_part <- function(task, stage_dir, smoke_limit = NULL) {
  set_single_thread_env()
  output <- file.path(stage_dir, "parts", paste0(task$task_id, ".fgb"))
  a14_output <- file.path(stage_dir, "a14", paste0(task$task_id, ".csv"))
  exclusion_output <- file.path(stage_dir, "ledgers", paste0(task$task_id, "_exclusions.csv"))
  done <- paste0(output, ".done.json")
  if (file.exists(output) && file.exists(a14_output) && file.exists(exclusion_output) && file.exists(done)) {
    return(data.table(task_id = task$task_id, output = output, a14_output = a14_output, exclusion_output = exclusion_output,
                      source_count = task$source_count, valid_count = as.numeric(ogr_scalar(output, "SELECT COUNT(*) AS n FROM building_part", "n")),
                      excluded_count = task$source_count - as.numeric(ogr_scalar(output, "SELECT COUNT(*) AS n FROM building_part", "n"))))
  }

  prefix <- sprintf("B20260509_%s_%s_", sanitize_name(task$region), sanitize_name(task$layer))
  limit_clause <- if (is.null(smoke_limit)) "" else sprintf(" LIMIT %d", as.integer(smoke_limit))
  sql <- sprintf(
    paste0(
      "SELECT '%s' || printf('%%010d', ROWID) AS building_feature_id, ",
      "'%s' AS source_archive, '%s' AS source_region, '%s' AS source_layer, ",
      "ROWID AS source_record_index, ",
      "CASE WHEN A14 IS NULL THEN 'NULL' WHEN A14 <= 0 THEN 'NONPOSITIVE' ELSE 'POSITIVE' END AS A14_source_state, ",
      "* FROM \"%s\" WHERE geometry IS NOT NULL AND NOT ST_IsEmpty(geometry)%s"
    ),
    sql_literal(prefix), sql_literal(basename(task$outer)), sql_literal(task$region),
    sql_literal(task$layer), gsub('"', '""', task$layer, fixed = TRUE), limit_clause
  )

  if (file.exists(output)) file.rename(output, paste0(output, ".incomplete.", format(Sys.time(), "%Y%m%d%H%M%S")))
  run_cmd(
    "ogr2ogr",
    c("--config", "SHAPE_ENCODING", cfg$building$source_encoding,
      "-f", "FlatGeobuf", output, task$dataset,
      "-dialect", "SQLite", "-sql", sql, "-nln", "building_part", "-nlt", "POLYGON")
  )
  valid_count <- as.numeric(ogr_scalar(output, "SELECT COUNT(*) AS n FROM building_part", "n"))

  if (file.exists(a14_output)) file.rename(a14_output, paste0(a14_output, ".incomplete.", format(Sys.time(), "%Y%m%d%H%M%S")))
  run_cmd("ogr2ogr", c("-f", "CSV", a14_output, output, "-dialect", "SQLite",
                       "-sql", "SELECT A14 FROM building_part", "-nlt", "NONE"))

  if (is.null(smoke_limit)) {
    exclusion_sql <- sprintf(
      paste0("SELECT '%s' AS source_archive, '%s' AS source_region, '%s' AS source_layer, ",
             "ROWID AS source_record_index, 'NULL_OR_EMPTY_GEOMETRY' AS reason_code FROM \"%s\" ",
             "WHERE geometry IS NULL OR ST_IsEmpty(geometry)"),
      sql_literal(basename(task$outer)), sql_literal(task$region), sql_literal(task$layer),
      gsub('"', '""', task$layer, fixed = TRUE)
    )
    run_cmd("ogr2ogr", c("--config", "SHAPE_ENCODING", cfg$building$source_encoding,
                          "-f", "CSV", exclusion_output, task$dataset, "-dialect", "SQLite", "-sql", exclusion_sql,
                          "-nln", "exclusions", "-nlt", "NONE"))
  } else {
    fwrite(data.table(source_archive = character(), source_region = character(), source_layer = character(),
                      source_record_index = integer(), reason_code = character()), exclusion_output)
  }

  expected_input <- if (is.null(smoke_limit)) task$source_count else min(task$source_count, smoke_limit)
  excluded <- if (is.null(smoke_limit)) task$source_count - valid_count else expected_input - valid_count
  write_json_atomic(
    list(task_id = task$task_id, source_count = task$source_count, valid_count = valid_count,
         excluded_count = excluded, timestamp = kst_now()),
    done
  )
  data.table(task_id = task$task_id, output = output, a14_output = a14_output, exclusion_output = exclusion_output,
             source_count = task$source_count, valid_count = valid_count, excluded_count = excluded)
}

with_failure_result(cfg, key, {
  started <- Sys.time()
  if (cli$mode == "production") assert_no_final_collision(cfg, key)
  outer <- source_path(cfg, key)
  run_tag <- if (cli$mode == "production") "production" else paste0("smoke_", run_id_now())
  stage_dir <- file.path(dataset_stage_dir(cfg, key), run_tag)
  dir.create(file.path(stage_dir, "parts"), recursive = TRUE, showWarnings = FALSE)
  dir.create(file.path(stage_dir, "a14"), recursive = TRUE, showWarnings = FALSE)
  dir.create(file.path(stage_dir, "ledgers"), recursive = TRUE, showWarnings = FALSE)

  nested <- list_zip_entries(outer, "(?i)\\.zip$")
  if (cli$mode == "smoke") nested <- nested[1L]
  tasks <- rbindlist(lapply(nested, function(entry) {
    dataset <- vsi_nested_zip(outer, entry)
    layers <- parse_layers(dataset)
    region <- sub("^.*AL_D010_([0-9]+)_.*$", "\\1", basename(entry))
    layers[, `:=`(
      outer = outer,
      entry = entry,
      dataset = dataset,
      region = region,
      task_id = sanitize_name(paste(region, layer, sep = "__"))
    )]
    layers
  }))
  if (cli$mode == "smoke") tasks <- tasks[1L]
  fwrite(tasks, file.path(stage_dir, "building_source_parts.csv"))
  if (cli$mode == "production") {
    if (nrow(tasks) != 24L) stop("Expected 24 building source parts, found ", nrow(tasks), call. = FALSE)
    if (sum(tasks$source_count) != cfg$building$expected_source_records) {
      stop("Building source count mismatch: ", sum(tasks$source_count), call. = FALSE)
    }
  }

  workers <- if (cli$mode == "smoke") 1L else min(cfg$runtime$building_workers, nrow(tasks))
  future::plan(future::multisession, workers = workers)
  on.exit(future::plan(future::sequential), add = TRUE)
  rows <- split(tasks, seq_len(nrow(tasks)))
  results <- future.apply::future_lapply(
    rows,
    function(x) stage_one_part(x, stage_dir, if (cli$mode == "smoke") 5000L else NULL),
    future.seed = TRUE,
    future.packages = c("data.table", "jsonlite", "yaml")
  )
  staged <- rbindlist(results)
  future::plan(future::sequential)
  fwrite(staged, file.path(stage_dir, "building_staging_qc.csv"))

  a14 <- unlist(lapply(staged$a14_output, function(path) data.table::fread(path, select = "A14")$A14), use.names = FALSE)
  positive <- a14[is.finite(a14) & a14 > 0]
  log_positive <- log1p(positive)
  q <- quantile(log_positive, c(0.25, 0.5, 0.75, 0.95, 0.99, 0.999), na.rm = TRUE, names = FALSE, type = 7)
  threshold <- exp(q[[3L]] + 3 * (q[[3L]] - q[[1L]])) - 1
  a14_qc <- list(
    n = length(a14), null = sum(is.na(a14)), zero = sum(a14 == 0, na.rm = TRUE),
    negative = sum(a14 < 0, na.rm = TRUE), positive = length(positive),
    min = min(a14, na.rm = TRUE), max = max(a14, na.rm = TRUE),
    positive_log_quantiles = as.list(setNames(q, c("q25", "q50", "q75", "q95", "q99", "q999"))),
    positive_extreme_threshold = threshold,
    positive_extreme_count = sum(positive > threshold)
  )
  write_json_atomic(a14_qc, file.path(stage_dir, "building_a14_qc.json"))

  gpkg <- file.path(stage_dir, "korea_B.staging.gpkg")
  progress_path <- file.path(stage_dir, "merge_progress.json")
  progress <- if (file.exists(progress_path)) read_json(progress_path, simplifyVector = TRUE)$appended else character()
  if (file.exists(gpkg) && !file.exists(progress_path)) stop("Ambiguous partial building GPKG without merge progress: ", gpkg, call. = FALSE)

  for (i in seq_len(nrow(staged))) {
    task_id <- staged$task_id[[i]]
    if (task_id %in% progress) next
    sql <- sprintf("SELECT *, CASE WHEN A14 > %.17g THEN 1 ELSE 0 END AS A14_positive_extreme_flag FROM building_part", threshold)
    if (!file.exists(gpkg)) {
      run_cmd("ogr2ogr", c("-f", "GPKG", gpkg, staged$output[[i]], "-dialect", "SQLite", "-sql", sql,
                           "-nln", "buildings", "-nlt", "POLYGON", "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"))
    } else {
      run_cmd("ogr2ogr", c("-update", "-append", gpkg, staged$output[[i]], "-dialect", "SQLite", "-sql", sql,
                           "-nln", "buildings", "-nlt", "POLYGON"))
    }
    progress <- c(progress, task_id)
    write_json_atomic(list(appended = progress, timestamp = kst_now()), progress_path)
  }

  metadata_csv <- file.path(stage_dir, "metadata.csv")
  write_metadata_csv(metadata_csv, list(
    schema_version = cfg$schema_version,
    snapshot_id = cfg$snapshot_id,
    source_archive = basename(outer),
    source_sha256 = sha256_file(outer),
    source_crs = "EPSG:5186",
    source_encoding = cfg$building$source_encoding,
    a14_preserved_raw = TRUE,
    a14_model_unavailable_rule = "NULL or <= 0",
    a14_positive_extreme_method = cfg$building$a14_outlier_method,
    a14_positive_extreme_threshold = threshold,
    created_at = kst_now()
  ))
  metadata_exists <- as.numeric(ogr_scalar(
    gpkg,
    "SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name='metadata'",
    "n"
  )) == 1
  if (!metadata_exists) append_csv_table_to_gpkg(metadata_csv, gpkg, "metadata")

  add_gpkg_spatial_index(gpkg, "buildings", "geom")
  create_attribute_index(gpkg, "CREATE UNIQUE INDEX IF NOT EXISTS idx_buildings_feature_id ON buildings(building_feature_id)")
  if (!sqlite_integrity(gpkg)) stop("Building GeoPackage integrity check failed", call. = FALSE)
  invalid_geometry_count <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM buildings WHERE NOT ST_IsValid(geom)", "n"))
  invalid_ledger_path <- file.path(stage_dir, "building_invalid_geometry_ledger.csv")
  if (invalid_geometry_count > 0) {
    if (file.exists(invalid_ledger_path)) {
      backup <- paste0(invalid_ledger_path, ".pre_policy_", run_id_now())
      if (!file.rename(invalid_ledger_path, backup)) stop("Could not preserve prior invalid ledger", call. = FALSE)
    }
    invalid_ledger <- write_invalid_geometry_ledger(gpkg, invalid_ledger_path)
    if (nrow(invalid_ledger) != invalid_geometry_count) stop("Invalid building ledger count mismatch", call. = FALSE)
    if (cli$mode == "production" && nrow(invalid_ledger) != cfg$building$expected_invalid_geometry_records) {
      stop("Expected ", cfg$building$expected_invalid_geometry_records,
           " invalid building geometries, found ", nrow(invalid_ledger), call. = FALSE)
    }
    run_cmd("ogrinfo", c(gpkg, "-dialect", "SQLite", "-sql", "DELETE FROM buildings WHERE NOT ST_IsValid(geom)"))
  } else {
    if (file.exists(invalid_ledger_path)) {
      invalid_ledger <- fread(invalid_ledger_path)
    } else if (cli$mode == "smoke") {
      invalid_ledger <- data.table(
        building_feature_id = character(), source_A0 = character(), source_A1 = character(),
        source_archive = character(), source_region = character(), source_layer = character(),
        source_record_index = integer(), reason_code = character(), ST_IsValidReason = character(),
        original_wkb_sha256 = character()
      )
      fwrite(invalid_ledger, invalid_ledger_path, bom = TRUE)
    } else {
      stop("Invalid geometry ledger missing after resumed exclusion", call. = FALSE)
    }
  }
  required_ledger_fields <- c(
    "building_feature_id", "source_A0", "source_A1", "source_archive", "source_layer",
    "source_record_index", "ST_IsValidReason", "original_wkb_sha256"
  )
  if (!all(required_ledger_fields %in% names(invalid_ledger))) stop("Invalid geometry ledger schema mismatch", call. = FALSE)
  if (cli$mode == "production" && nrow(invalid_ledger) != cfg$building$expected_invalid_geometry_records) {
    stop("Invalid geometry ledger count changed after resume", call. = FALSE)
  }

  invalid_after <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM buildings WHERE NOT ST_IsValid(geom)", "n"))
  if (invalid_after != 0) stop("Invalid building geometry exclusion failed", call. = FALSE)
  output_count <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM buildings", "n"))
  unique_count <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(DISTINCT building_feature_id) AS n FROM buildings", "n"))
  if (output_count != unique_count) stop("building_feature_id is not unique", call. = FALSE)
  if (cli$mode == "production" && output_count != cfg$building$expected_valid_records) {
    stop(sprintf("Building accepted count mismatch: %d", output_count), call. = FALSE)
  }

  null_exclusions <- rbindlist(lapply(staged$exclusion_output, fread), fill = TRUE)
  if (cli$mode == "production" && nrow(null_exclusions) != cfg$building$expected_null_or_empty_records) {
    stop("Expected ", cfg$building$expected_null_or_empty_records,
         " null/empty building geometries, found ", nrow(null_exclusions), call. = FALSE)
  }
  exclusions <- rbindlist(list(null_exclusions, invalid_ledger), fill = TRUE, use.names = TRUE)
  fwrite(exclusions, file.path(stage_dir, "building_exclusion_ledger.csv"), bom = TRUE)
  if (!sqlite_integrity(gpkg)) stop("Building GeoPackage integrity check failed after exclusion", call. = FALSE)
  if (file.exists(paste0(gpkg, "-wal")) || file.exists(paste0(gpkg, "-shm"))) stop("Building GPKG has WAL/SHM sidecar", call. = FALSE)

  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  details <- list(mode = cli$mode, source_records = sum(tasks$source_count), output_records = output_count,
                  excluded_records = nrow(exclusions), null_or_empty_excluded = nrow(null_exclusions),
                  invalid_geometry_excluded = nrow(invalid_ledger), invalid_geometry_records_after_exclusion = invalid_after,
                  invalid_geometry_ledger = invalid_ledger_path,
                  invalid_geometry_ledger_sha256 = sha256_file(invalid_ledger_path),
                  exclusion_ledger = file.path(stage_dir, "building_exclusion_ledger.csv"), workers = workers,
                  staging_path = gpkg, elapsed_sec = elapsed, a14_qc = a14_qc)
  if (cli$mode == "production") {
    final <- output_path(cfg, key)
    atomic_publish(gpkg, final)
    details$final_path <- final
    details$final_size <- unname(file.info(final)$size)
    details$final_sha256 <- sha256_file(final)
    write_marker(cfg, key, "production_complete", details)
  }
  write_dataset_result(cfg, key, "PASS", details)
  log_line(sprintf("BUILDING_COMPLETE mode=%s records=%d elapsed_sec=%.3f", cli$mode, output_count, elapsed))
})
