# Dissertation methodology: Section 2 object-modal geometry and relation graph
# tensors. I15 materializes only the approved prototype training cache branches.

serialization_shard_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/serialization_shard.yml",
    "config/serialization_shard_runtime.yml",
    "config/schemas/prototype_serialization_shard.schema.json",
    "python/serialize_prototype_shard.py",
    "python/validate_prototype_serialization_shards.py",
    "python/requirements-serialization.txt",
    "R/research_serialization_shard.R"
  ))
}

load_serialization_shard_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c(
    "serialization_shard.yml", "serialization_shard_runtime.yml",
    "prototype_serialization_shard.schema.json", "serialize_prototype_shard.py",
    "validate_prototype_serialization_shards.py", "requirements-serialization.txt",
    "research_serialization_shard.R"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing serialization-shard contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  scientific <- yaml::read_yaml(by_name[["serialization_shard.yml"]])
  runtime <- yaml::read_yaml(by_name[["serialization_shard_runtime.yml"]])
  validate_serialization_shard_config(scientific, runtime)
  list(scientific = scientific, runtime = runtime, paths = by_name)
}

validate_serialization_shard_config <- function(scientific, runtime) {
  expected <- list(
    contract = c(scientific$serialization_shard_contract_version, "1.0.0"),
    spatial = c(scientific$identity$spatial_dataset_id, "psa_4e43932fc998fed94385addc"),
    plan = c(scientific$identity$serialization_plan_id, "psp_c3f6659d47486417567d55c1"),
    dataset = c(scientific$identity$serialization_dataset_id, "psd_c3f6659d47486417567d55c1"),
    archive = c(scientific$archive$format, "webdataset_tar"),
    controller = c(runtime$controller, "controller_10"),
    workers = c(runtime$workers, 1), threads = c(runtime$threads_per_worker, 1), gpu = c(runtime$gpu, 0)
  )
  bad <- names(expected)[vapply(expected, function(x) !identical(as.character(x[[1L]]), as.character(x[[2L]])), logical(1L))]
  if (length(bad)) stop("Serialization-shard contract mismatch: ", paste(bad, collapse = ", "), call. = FALSE)
  expected_members <- c("meta.json", "entities.safetensors", "geometry.safetensors", "edges.safetensors", "rasters.safetensors")
  if (!identical(unlist(scientific$archive$member_order, use.names = FALSE), expected_members)) {
    stop("Serialization tar member order changed", call. = FALSE)
  }
  if (!identical(unlist(scientific$tensor$object_raster_features, use.names = FALSE)[c(1L, 22L, 23L, 26L)],
                 c("lc_fraction_01", "lc_fraction_22", "lc_valid_support_ratio", "dem_valid_support_ratio"))) {
    stop("Object-raster feature order changed", call. = FALSE)
  }
  invisible(TRUE)
}

run_prototype_serialization_shard <- function(
    prototype_serialization_plan,
    serialization_shard_contract_files,
    workers = 1L,
    threads = 1L,
    output_directory = NULL) {
  config <- load_serialization_shard_config(serialization_shard_contract_files)
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("I15 branch execution requires exactly 1 worker and 1 thread", call. = FALSE)
  }
  spec_path <- prototype_serialization_plan$.path
  if (is.null(spec_path) || !file.exists(spec_path)) stop("I14 branch spec path is missing", call. = FALSE)
  spec <- jsonlite::read_json(spec_path, simplifyVector = FALSE)
  if (!identical(spec$plan_id, config$scientific$identity$serialization_plan_id) ||
      !identical(spec$serialization_dataset_id, config$scientific$identity$serialization_dataset_id)) {
    stop("I14 branch spec identity does not match I15 contract", call. = FALSE)
  }
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  args <- c(
    config$paths[["serialize_prototype_shard.py"]],
    "--spec", normalizePath(spec_path, mustWork = TRUE),
    "--config", config$paths[["serialization_shard.yml"]],
    "--schema", config$paths[["prototype_serialization_shard.schema.json"]]
  )
  if (!is.null(output_directory)) args <- c(args, "--output-dir", output_directory)
  output <- system2(config$runtime$python, args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop("I15 serializer failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(result) || !identical(result$status, "PASS")) stop("I15 serializer returned invalid result:\n", paste(output, collapse = "\n"), call. = FALSE)
  files <- normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
  required <- c(
    paste0("scenes-", spec$branch_id, ".tar"), paste0("scenes-", spec$branch_id, ".idx"),
    "scene_index.parquet", "branch_qc.json", "branch_log.jsonl", "branch_manifest.json"
  )
  if (!setequal(basename(files), required)) stop("I15 serializer returned incomplete branch outputs", call. = FALSE)
  files
}
