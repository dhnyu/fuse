suppressPackageStartupMessages({
  library(data.table)
  library(yaml)
  library(jsonlite)
})

`%||%` <- function(x, y) if (is.null(x) || length(x) == 0L) y else x

repo_root <- function() {
  root <- Sys.getenv("FUSE_REPO", "/members/dhnyu/fuse")
  normalizePath(root, mustWork = TRUE)
}

load_preprocessing_config <- function(path = file.path(repo_root(), "config", "preprocessing.yml")) {
  cfg <- yaml::read_yaml(path)
  cfg$config_path <- normalizePath(path, mustWork = TRUE)
  cfg
}

set_single_thread_env <- function() {
  vars <- c(
    OMP_NUM_THREADS = "1",
    OPENBLAS_NUM_THREADS = "1",
    MKL_NUM_THREADS = "1",
    GDAL_NUM_THREADS = "1",
    NUMEXPR_NUM_THREADS = "1"
  )
  do.call(Sys.setenv, as.list(vars))
  invisible(vars)
}

kst_now <- function() format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul")
run_id_now <- function() format(Sys.time(), "%Y%m%d_%H%M%S", tz = "Asia/Seoul")

ensure_preprocessing_dirs <- function(cfg) {
  dirs <- c(
    cfg$paths$staging_dir,
    file.path(cfg$paths$staging_dir, "inventory"),
    file.path(cfg$paths$staging_dir, "markers"),
    file.path(cfg$paths$staging_dir, "qc"),
    file.path(cfg$paths$staging_dir, "publish"),
    cfg$paths$report_dir,
    cfg$paths$log_dir
  )
  for (path in dirs) dir.create(path, recursive = TRUE, showWarnings = FALSE)
  invisible(dirs)
}

log_line <- function(..., level = "INFO") {
  msg <- paste0(..., collapse = "")
  line <- sprintf("[%s] [%s] %s", kst_now(), level, msg)
  cat(line, "\n")
  flush.console()
  invisible(line)
}

quote_command <- function(command, args = character()) {
  paste(c(shQuote(command), vapply(args, shQuote, character(1L))), collapse = " ")
}

run_cmd <- function(command, args = character(), env = character(), check = TRUE) {
  log_line("RUN ", quote_command(command, args))
  started <- Sys.time()
  safe_args <- vapply(args, shQuote, character(1L))
  status <- system2(command, args = safe_args, env = env, stdout = "", stderr = "")
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  log_line(sprintf("EXIT status=%d elapsed_sec=%.3f command=%s", status, elapsed, command))
  if (check && !identical(as.integer(status), 0L)) {
    stop(sprintf("Command failed with status %d: %s", status, quote_command(command, args)), call. = FALSE)
  }
  invisible(list(status = as.integer(status), elapsed_sec = elapsed))
}

capture_cmd <- function(command, args = character(), env = character(), check = TRUE) {
  log_line("CAPTURE ", quote_command(command, args))
  safe_args <- vapply(args, shQuote, character(1L))
  out <- system2(command, args = safe_args, env = env, stdout = TRUE, stderr = TRUE)
  status <- attr(out, "status") %||% 0L
  if (check && !identical(as.integer(status), 0L)) {
    stop(sprintf("Command failed with status %d: %s\n%s", status, quote_command(command, args), paste(out, collapse = "\n")), call. = FALSE)
  }
  out
}

source_path <- function(cfg, key) file.path(cfg$paths$source_dir, cfg$sources[[key]])
output_path <- function(cfg, key) file.path(cfg$paths$output_dir, cfg$outputs[[key]])
dataset_stage_dir <- function(cfg, key) file.path(cfg$paths$staging_dir, key)
marker_path <- function(cfg, key, marker) file.path(cfg$paths$staging_dir, "markers", sprintf("%s_%s.json", key, marker))

assert_no_final_collision <- function(cfg, key) {
  path <- output_path(cfg, key)
  if (file.exists(path)) {
    info <- file.info(path)
    stop(sprintf("FINAL_COLLISION path=%s size=%s mtime=%s", path, info$size, info$mtime), call. = FALSE)
  }
  invisible(path)
}

assert_free_space <- function(cfg, required = cfg$runtime$min_free_bytes) {
  required <- as.numeric(required)
  out <- capture_cmd("df", c("-B1", "--output=avail", cfg$paths$staging_dir))
  avail <- as.numeric(trimws(tail(out, 1L)))
  if (!is.finite(avail) || avail < required) {
    stop(sprintf("Insufficient staging free space: available=%s required=%s", avail, required), call. = FALSE)
  }
  log_line(sprintf("FREE_SPACE available_bytes=%.0f required_bytes=%.0f", avail, required))
  invisible(avail)
}

sha256_file <- function(path) {
  out <- capture_cmd("sha256sum", path)
  strsplit(out[[1L]], "[[:space:]]+")[[1L]][[1L]]
}

write_json_atomic <- function(value, path, pretty = TRUE) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  tmp <- paste0(path, ".tmp.", Sys.getpid())
  jsonlite::write_json(value, tmp, auto_unbox = TRUE, pretty = pretty, null = "null", digits = NA)
  if (!file.rename(tmp, path)) stop("Atomic JSON rename failed: ", path, call. = FALSE)
  invisible(path)
}

write_marker <- function(cfg, key, marker, values = list()) {
  payload <- c(list(dataset = key, marker = marker, timestamp = kst_now()), values)
  write_json_atomic(payload, marker_path(cfg, key, marker))
}

read_marker <- function(cfg, key, marker) {
  path <- marker_path(cfg, key, marker)
  if (!file.exists(path)) return(NULL)
  jsonlite::read_json(path, simplifyVector = TRUE)
}

atomic_publish <- function(staged, final) {
  if (!file.exists(staged)) stop("Staged output missing: ", staged, call. = FALSE)
  if (file.exists(final)) stop("Refusing to overwrite final output: ", final, call. = FALSE)
  if (!file.rename(staged, final)) stop("Atomic publish rename failed: ", staged, " -> ", final, call. = FALSE)
  log_line("PUBLISHED ", final)
  invisible(final)
}

vsi_zip <- function(path, entry = NULL) {
  base <- paste0("/vsizip/", path)
  if (is.null(entry)) base else paste0(base, "/", entry)
}

vsi_nested_zip <- function(outer, inner, child = NULL) {
  base <- sprintf("/vsizip/{/vsizip/%s/%s}", outer, inner)
  if (is.null(child)) base else paste0(base, "/", child)
}

list_zip_entries <- function(path, pattern = NULL) {
  entries <- capture_cmd("zipinfo", c("-1", path))
  if (!is.null(pattern)) entries <- entries[grepl(pattern, entries, perl = TRUE)]
  entries
}

sqlite_integrity <- function(path) {
  code <- paste0(
    "import sqlite3,sys;",
    "c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);",
    "r=c.execute('PRAGMA integrity_check').fetchone()[0];",
    "print(r);c.close();",
    "sys.exit(0 if r=='ok' else 2)"
  )
  out <- capture_cmd("python", c("-c", code, path))
  identical(trimws(tail(out, 1L)), "ok")
}

ogr_scalar <- function(dataset, sql, field, dialect = "SQLite") {
  out <- capture_cmd("ogrinfo", c("-ro", "-q", dataset, "-dialect", dialect, "-sql", sql))
  line <- grep(sprintf("^[[:space:]]+%s ", field), out, value = TRUE)
  if (length(line) != 1L) {
    values <- grep("^[[:space:]]+[^=]+ = ", out, value = TRUE)
    if (length(values) == 1L) line <- values
  }
  if (length(line) != 1L) stop("Could not parse OGR scalar field ", field, " from: ", paste(out, collapse = " | "), call. = FALSE)
  sub("^.* = ", "", line)
}

create_attribute_index <- function(gpkg, sql) {
  run_cmd("ogrinfo", c(gpkg, "-dialect", "SQLite", "-sql", sql))
}

add_gpkg_spatial_index <- function(gpkg, layer, geom = "geom") {
  has <- ogr_scalar(gpkg, sprintf("SELECT HasSpatialIndex('%s','%s') AS value", layer, geom), "value")
  if (identical(has, "0")) {
    run_cmd("ogrinfo", c(gpkg, "-dialect", "SQLite", "-sql", sprintf("SELECT CreateSpatialIndex('%s','%s')", layer, geom)))
  }
  has_after <- ogr_scalar(gpkg, sprintf("SELECT HasSpatialIndex('%s','%s') AS value", layer, geom), "value")
  if (!identical(has_after, "1")) stop("Spatial index missing for ", layer, call. = FALSE)
  invisible(TRUE)
}

write_metadata_csv <- function(path, values) {
  dt <- data.table(metadata_key = names(values), value = vapply(values, as.character, character(1L)))
  setnames(dt, "metadata_key", "key")
  data.table::fwrite(dt, path, bom = TRUE)
  invisible(path)
}

append_csv_table_to_gpkg <- function(csv, gpkg, layer, create = FALSE) {
  args <- c()
  if (create) args <- c(args, "-f", "GPKG") else args <- c(args, "-update", "-append")
  args <- c(args, gpkg, csv, "-nln", layer, "-lco", "ASPATIAL_VARIANT=GPKG_ATTRIBUTES")
  run_cmd("ogr2ogr", args)
}

parse_cli <- function(args = commandArgs(trailingOnly = TRUE)) {
  result <- list(mode = "production", config = file.path(repo_root(), "config", "preprocessing.yml"))
  for (arg in args) {
    if (startsWith(arg, "--mode=")) result$mode <- sub("^--mode=", "", arg)
    else if (startsWith(arg, "--config=")) result$config <- sub("^--config=", "", arg)
    else stop("Unknown argument: ", arg, call. = FALSE)
  }
  if (!result$mode %in% c("smoke", "production")) stop("Unsupported mode: ", result$mode, call. = FALSE)
  result
}

dataset_result_path <- function(cfg, key) file.path(cfg$paths$staging_dir, "qc", sprintf("%s_result.json", key))

write_dataset_result <- function(cfg, key, status, details = list()) {
  write_json_atomic(c(list(dataset = key, status = status, timestamp = kst_now()), details), dataset_result_path(cfg, key))
}

with_failure_result <- function(cfg, key, expr) {
  tryCatch(
    force(expr),
    error = function(e) {
      log_line(conditionMessage(e), level = "ERROR")
      write_dataset_result(cfg, key, "FAIL", list(error = conditionMessage(e)))
      stop(e)
    }
  )
}
