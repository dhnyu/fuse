# P9 cache/authority gates are orchestration-only and cannot start an optimizer.

p9_formal_contract_files <- function() {
  c(
    "config/p9_formal_authorization.yml",
    list.files("config/schemas", pattern = "^p9_(cache_|production_cache_|formal_training_authority|cfg_main_attempt_reservation).*\\.schema\\.json$", full.names = TRUE),
    "python/p9_formal_authorization.py", "scripts/p9_formal_authorization.py",
    "scripts/p9_production_cache.py", "R/research_p9_formal_authorization.R",
    "targets/research_p9_formal_authorization.R"
  )
}

p9_formal_parent_paths <- function(config_path) {
  cfg <- yaml::read_yaml(config_path)
  c(
    p7_runtime_acceptance = cfg$artifacts$p7_runtime_acceptance,
    p8_formal_plan_acceptance = file.path(cfg$artifacts$p8_bundle_root, "formal_experiment_plan_acceptance.json"),
    p8_hyperparameter_matrix = file.path(cfg$artifacts$p8_bundle_root, "hyperparameter_configuration_matrix.json"),
    p8_comparison_matrix = file.path(cfg$artifacts$p8_bundle_root, "comparison_variant_template_matrix.json"),
    p9_readiness = cfg$artifacts$p9_readiness
  )
}

p9_parse_outputs <- function(output, prefix) {
  line <- output[startsWith(output, prefix)]
  if (length(line) != 1L) stop("P9 command did not report exactly one output record", call. = FALSE)
  jsonlite::fromJSON(sub(paste0("^", prefix), "", line), simplifyVector = TRUE)
}

p9_build_cache_plan_bundle <- function(contract_files, parent_files) {
  invisible(parent_files)
  cfg <- yaml::read_yaml("config/p9_formal_authorization.yml")
  execution_commit <- cfg$cache_build_execution_commit
  if (!is.character(execution_commit) || length(execution_commit) != 1L ||
      !grepl("^[0-9a-f]{40}$", execution_commit)) {
    stop("P9 cache build execution commit must be a complete Git SHA", call. = FALSE)
  }
  output <- system2(research_python_executable(), c(
    "scripts/p9_formal_authorization.py", "plan", "--config", contract_files[[1L]],
    "--schema-dir", "config/schemas", "--scientific-commit", cfg$canonical_implementation_commit,
    "--execution-commit", execution_commit
  ), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop(paste(output, collapse = "\n"), call. = FALSE)
  paths <- p9_parse_outputs(output, "P9_OUTPUTS=")
  normalizePath(paths, mustWork = TRUE)
}

p9_plan_artifact <- function(bundle, filename, dependency = NULL) {
  invisible(dependency)
  path <- bundle[basename(bundle) == filename]
  if (length(path) != 1L) stop("P9 plan artifact lookup mismatch: ", filename, call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}

p9_materialize_production_cache <- function(build_authority, contract_files) {
  authority <- jsonlite::read_json(build_authority, simplifyVector = FALSE)
  expected <- authority$artifact_id
  observed <- Sys.getenv("FUSE_P9_CACHE_BUILD_AUTHORITY_ID", unset = "")
  if (!nzchar(observed) || !identical(observed, expected)) {
    stop("P9 heavy cache build requires explicit FUSE_P9_CACHE_BUILD_AUTHORITY_ID=", expected, call. = FALSE)
  }
  output <- system2(research_python_executable(), c(
    "scripts/p9_production_cache.py", "build", "--config", contract_files[[1L]],
    "--authority", build_authority
  ), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop(paste(output, collapse = "\n"), call. = FALSE)
  line <- output[startsWith(output, "P9_CACHE_OUTPUT=")]
  if (length(line) != 1L) stop("P9 cache builder did not report its manifest", call. = FALSE)
  normalizePath(sub("^P9_CACHE_OUTPUT=", "", line), mustWork = TRUE)
}

p9_validate_production_cache <- function(cache_manifest, contract_files) {
  cfg <- yaml::read_yaml(contract_files[[1L]])
  manifest <- jsonlite::read_json(cache_manifest, simplifyVector = FALSE)
  authority_id <- manifest$build_authority_id
  final <- file.path(cfg$roots$publication, authority_id, "production_cache_validation.json")
  if (file.exists(final)) {
    record <- jsonlite::read_json(final, simplifyVector = FALSE)
    zero_fields <- c(
      "missing_identities", "duplicate_identities", "orphan_entries",
      "shard_checksum_failures", "manifest_index_disagreements", "invalid_dem_support",
      "shape_dtype_schema_failures", "p7_overlap_byte_differences",
      "k_subset_overlap_byte_differences", "repeat_build_scientific_byte_differences",
      "rank_dependent_differences"
    )
    execution_zero <- c("optimizer_updates", "formal_validation_runs", "checkpoints", "evaluation_queries_consumed")
    manifest_sha <- digest::digest(file = cache_manifest, algo = "sha256", serialize = FALSE)
    valid <- identical(record$status, "PASS") &&
      identical(record$cache$cache_id, manifest$cache_id) &&
      identical(record$cache$manifest_sha256, manifest_sha) &&
      identical(as.integer(record$cache$entry_count), as.integer(manifest$entry_count)) &&
      all(vapply(zero_fields, function(key) identical(as.integer(record[[key]]), 0L), logical(1))) &&
      all(vapply(execution_zero, function(key) identical(as.integer(record$execution_counts[[key]]), 0L), logical(1)))
    if (!valid) stop("P9 existing cache validation readback failed", call. = FALSE)
    return(normalizePath(final, mustWork = TRUE))
  }
  output <- tempfile("p9-cache-validation-", fileext = ".json")
  status <- system2(research_python_executable(), c(
    "scripts/p9_production_cache.py", "validate", "--config", contract_files[[1L]],
    "--manifest", cache_manifest, "--output", output
  ))
  if (!identical(status, 0L)) stop("P9 production cache validation failed", call. = FALSE)
  payload <- readBin(output, "raw", n = file.info(output)$size)
  dir.create(dirname(final), recursive = TRUE, showWarnings = FALSE)
  temporary <- paste0(final, ".tmp-", Sys.getpid()); writeBin(payload, temporary); file.rename(temporary, final)
  normalizePath(final, mustWork = TRUE)
}

p9_publish_formal_bundle <- function(build_authority, cache_validation, parent_files, contract_files) {
  invisible(parent_files)
  execution_commit <- system2("git", c("rev-parse", "HEAD"), stdout = TRUE)
  output <- system2(research_python_executable(), c(
    "scripts/p9_formal_authorization.py", "finalize", "--config", contract_files[[1L]],
    "--schema-dir", "config/schemas", "--build-authority", build_authority,
    "--validation", cache_validation, "--execution-commit", execution_commit
  ), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop(paste(output, collapse = "\n"), call. = FALSE)
  normalizePath(p9_parse_outputs(output, "P9_OUTPUTS="), mustWork = TRUE)
}

p9_formal_artifact <- function(bundle, filename, dependency = NULL) {
  invisible(dependency)
  path <- bundle[basename(bundle) == filename]
  if (length(path) != 1L) stop("P9 formal artifact lookup mismatch: ", filename, call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}

p9_formal_execution_files <- function() {
  c(
    "config/p9_formal_reauthorization.yml",
    list.files("config/schemas", pattern = "^p9_formal_(execution|attempt|running|resume|validation|terminal).*\\.schema\\.json$", full.names = TRUE),
    "python/p9_formal_execution.py", "python/p9_formal_reauthorization.py",
    "scripts/p9_formal_reauthorization.py", "scripts/p9_formal_training.py",
    "R/research_p9_formal_authorization.R", "targets/research_p9_formal_authorization.R"
  )
}

p9_formal_execution_parent_paths <- function(config_path) {
  cfg <- yaml::read_yaml(config_path)
  unlist(cfg$artifacts[c("p7_runtime_acceptance", "p8_acceptance", "p8_hyperparameter_matrix",
                         "p9_readiness", "production_cache_acceptance")], use.names = TRUE)
}

p9_publish_corrected_execution_bundle <- function(contract_files, parents, cache_acceptance,
                                                   old_authority, old_reservation) {
  invisible(list(parents, cache_acceptance, old_authority, old_reservation))
  output <- system2(research_python_executable(), c(
    "scripts/p9_formal_reauthorization.py", "publish", "--config", contract_files[[1L]]
  ), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop(paste(output, collapse = "\n"), call. = FALSE)
  normalizePath(p9_parse_outputs(output, "P9_OUTPUTS="), mustWork = TRUE)
}

p9_corrected_execution_artifact <- function(bundle, filename, dependency = NULL) {
  invisible(dependency)
  p9_formal_artifact(bundle, filename)
}

p9_execute_reserved_formal_run <- function(authority, reservation, cache_acceptance, matrix,
                                           readiness, runtime_parent) {
  invisible(list(readiness, runtime_parent))
  value <- jsonlite::read_json(reservation, simplifyVector = FALSE)
  token <- Sys.getenv("FUSE_P9_FORMAL_RESERVATION_ID", unset = "")
  if (!nzchar(token) || !identical(token, value$reservation_id)) {
    stop("P9 formal run requires explicit FUSE_P9_FORMAL_RESERVATION_ID=", value$reservation_id,
         call. = FALSE)
  }
  cfg <- yaml::read_yaml("config/p9_formal_reauthorization.yml")
  output_root <- file.path(cfg$roots$formal_attempts, value$attempt_id)
  if (dir.exists(output_root)) stop("P9 formal attempt output already exists", call. = FALSE)
  args <- c(
    "scripts/p9_formal_training.py", "controller", "--authority", authority,
    "--reservation", reservation, "--matrix", matrix, "--cache-acceptance", cache_acceptance,
    "--cache-root", cfg$roots$production_cache, "--categories", cfg$artifacts$categories,
    "--output-root", output_root, "--configuration-id", value$configuration_id,
    "--lock-root", cfg$roots$attempt_locks
  )
  status <- system2(research_python_executable(), args)
  if (!identical(status, 0L)) stop("P9 formal runner failed", call. = FALSE)
  files <- file.path(output_root, c("formal_run.json", "validation_trace.json",
    "checkpoint_candidate_index.json", "selected_checkpoint.json",
    "terminal_execution_record.json", "cfg_main_attempt_acceptance.json"))
  normalizePath(files, mustWork = TRUE)
}

p9_formal_run_artifact <- function(bundle, filename, dependency = NULL) {
  invisible(dependency)
  path <- bundle[basename(bundle) == filename]
  if (length(path) != 1L) stop("P9 formal run artifact lookup mismatch: ", filename, call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}
