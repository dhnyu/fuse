`%||%` <- function(x, y) if (is.null(x) || !length(x)) y else x

kst_now <- function() {
  format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul")
}

kst_stamp <- function() {
  format(Sys.time(), "%Y%m%d_%H%M", tz = "Asia/Seoul")
}

set_single_thread_environment <- function() {
  set_native_thread_limits(1L)
}

native_thread_environment_variables <- function() {
  c(
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GDAL_NUM_THREADS"
  )
}

assert_positive_integer <- function(value, label) {
  integer <- suppressWarnings(as.integer(value))
  if (length(value) != 1L || is.na(integer) ||
      !identical(as.character(integer), as.character(value)) || integer < 1L) {
    stop(label, " must be a positive integer", call. = FALSE)
  }
  integer
}

fuse_controller_worker_count <- function(variable, default) {
  value <- Sys.getenv(variable, unset = as.character(default))
  assert_positive_integer(value, variable)
}

fuse_parallel_spec <- function(workers, threads, available = parallelly::availableCores()) {
  workers <- assert_positive_integer(workers, "workers")
  threads <- assert_positive_integer(threads, "threads")
  available <- assert_positive_integer(available, "available logical CPUs")
  maximum <- workers * threads
  if (maximum > available) {
    stop(
      "workers x threads (", workers, " x ", threads, " = ", maximum,
      ") exceeds available logical CPUs (", available, ")",
      call. = FALSE
    )
  }
  list(workers = workers, threads = threads, maximum_cores = maximum, available_cores = available)
}

capture_native_thread_state <- function() {
  list(
    environment = Sys.getenv(native_thread_environment_variables(), unset = NA_character_),
    data_table = data.table::getDTthreads()
  )
}

set_native_thread_limits <- function(threads) {
  threads <- assert_positive_integer(threads, "threads")
  values <- setNames(rep(as.character(threads), length(native_thread_environment_variables())),
                     native_thread_environment_variables())
  do.call(Sys.setenv, as.list(values))
  data.table::setDTthreads(threads)
  invisible(threads)
}

restore_native_thread_state <- function(state) {
  missing <- names(state$environment)[is.na(state$environment)]
  present <- state$environment[!is.na(state$environment)]
  if (length(missing)) Sys.unsetenv(missing)
  if (length(present)) do.call(Sys.setenv, as.list(present))
  data.table::setDTthreads(state$data_table)
  invisible(NULL)
}

required_config_paths <- function() {
  list(
    paths = c(
      "canonical.root", "canonical.manifest", "canonical.building", "canonical.road",
      "canonical.poi", "canonical.landcover", "canonical.dem", "administrative.sido",
      "study.root", "study.boundary", "study.buffer400", "study.building", "study.road",
      "study.poi", "study.landcover", "study.dem", "study.manifest", "study.staging",
      "targets.store", "repository.root", "repository.thesis", "repository.reports",
      "repository.logs"
    ),
    methodology = c(
      "study_area.source_code", "study_area.source_name", "study_area.output_crs",
      "study_area.source_buffer_m", "landcover.resolution_m", "landcover.nodata",
      "dem.resolution_m", "dem.resampling", "dem.source_nodata", "dem.output_nodata",
      "dem.grid_anchor_x_m", "dem.grid_anchor_y_m", "road.source_to_output_pipeline",
      "road.endpoint_tolerance_m", "road.node_candidate_padding_m", "contract.study_subset_version",
      "contract.canonical_schema_version", "contract.canonical_snapshot"
    )
  )
}

config_get <- function(x, dotted) {
  Reduce(function(value, key) value[[key]], strsplit(dotted, ".", fixed = TRUE)[[1L]], init = x)
}

assert_config_fields <- function(x, fields, label) {
  missing <- fields[vapply(fields, function(field) {
    value <- tryCatch(config_get(x, field), error = function(e) NULL)
    is.null(value) || !length(value) || (is.character(value) && !nzchar(value))
  }, logical(1L))]
  if (length(missing)) {
    stop(label, " configuration is missing: ", paste(missing, collapse = ", "), call. = FALSE)
  }
}

load_pipeline_config <- function(paths_file, methodology_file) {
  paths <- yaml::read_yaml(paths_file)
  methodology <- yaml::read_yaml(methodology_file)
  required <- required_config_paths()
  assert_config_fields(paths, required$paths, "paths")
  assert_config_fields(methodology, required$methodology, "methodology")
  if (!identical(as.numeric(methodology$study_area$source_buffer_m), 400)) {
    stop("The approved source buffer must be exactly 400 m", call. = FALSE)
  }
  if (!identical(as.numeric(methodology$dem$resolution_m), 30)) {
    stop("The approved derived DEM resolution must be exactly 30 m", call. = FALSE)
  }
  if (!identical(methodology$study_area$output_crs, "EPSG:5186")) {
    stop("The study output CRS must be EPSG:5186", call. = FALSE)
  }
  dirs <- c(paths$study$root, paths$study$staging, paths$targets$store,
            paths$repository$reports, paths$repository$logs)
  vapply(dirs, dir.create, logical(1L), recursive = TRUE, showWarnings = FALSE)
  list(
    paths = paths,
    methodology = methodology,
    config_files = normalizePath(c(paths_file, methodology_file), mustWork = TRUE),
    config_sha256 = digest::digest(
      paste(vapply(c(paths_file, methodology_file), sha256_file, character(1L)), collapse = "|"),
      algo = "sha256", serialize = FALSE
    )
  )
}

read_canonical_manifest <- function(path) {
  value <- jsonlite::read_json(path, simplifyVector = FALSE)
  if (!identical(value$status, "PASS")) stop("Canonical manifest is not PASS", call. = FALSE)
  value
}

validate_canonical_inputs <- function(manifest, files, config) {
  expected_schema <- config$methodology$contract$canonical_schema_version
  expected_snapshot <- config$methodology$contract$canonical_snapshot
  if (!identical(manifest$schema_version, expected_schema)) {
    stop("Canonical schema mismatch: ", manifest$schema_version, call. = FALSE)
  }
  if (!identical(as.character(manifest$snapshot_id), as.character(expected_snapshot))) {
    stop("Canonical snapshot mismatch: ", manifest$snapshot_id, call. = FALSE)
  }
  keys <- c("building", "road", "poi", "landcover", "dem")
  if (length(files) != length(keys)) stop("Canonical file target is incomplete", call. = FALSE)
  result <- setNames(vector("list", length(keys)), keys)
  for (key in keys) {
    item <- manifest$outputs[[key]]
    path <- config$paths$canonical[[key]]
    if (!file.exists(path)) stop("Missing canonical input: ", path, call. = FALSE)
    if (!identical(normalizePath(path), normalizePath(item$path))) {
      stop("Canonical manifest path mismatch for ", key, call. = FALSE)
    }
    size <- unname(file.info(path)$size)
    hash <- sha256_file(path)
    if (!identical(as.numeric(size), as.numeric(item$size_bytes)) || !identical(hash, item$sha256)) {
      stop("Canonical size/checksum mismatch for ", key, call. = FALSE)
    }
    result[[key]] <- list(path = path, size_bytes = size, sha256 = hash)
  }
  result$manifest <- list(
    path = config$paths$canonical$manifest,
    sha256 = sha256_file(config$paths$canonical$manifest),
    schema_version = manifest$schema_version,
    snapshot_id = manifest$snapshot_id
  )
  result
}
