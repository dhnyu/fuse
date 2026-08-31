# Execution-only P9 orchestration. Accepted scientific artifacts are immutable
# file roots; no function in this module calls their historical producers.

p9x_sha256_file <- function(path) {
  digest::digest(file = path, algo = "sha256", serialize = FALSE)
}

p9x_decimal_equal <- function(left, right) {
  identical(format(left, scientific = FALSE, trim = TRUE), as.character(right))
}

p9x_runtime_file_paths <- function() {
  sort(c(
    "_targets_p9_formal.R",
    "R/research_p9_formal_execution_isolated.R",
    "targets/research_p9_formal_execution.R",
    "config/p9_formal_isolated_runtime.yml",
    "config/p6_model_dataloader.yml",
    "config/p7_deterministic_training.yml",
    "config/p9_infrastructure.yml",
    list.files("config/schemas", pattern = "^(p9_formal_|p9_isolated_).*\\.schema\\.json$", full.names = TRUE),
    "python/canonical_config.py",
    "python/p6_data.py", "python/p6_model.py",
    "python/p7_geometry_cache.py", "python/p7_training.py",
    "python/p9_formal_execution.py", "python/p9_formal_isolated_authorization.py",
    "python/p9_infrastructure.py", "python/p9_model_families.py",
    "python/prototype_encoder.py", "python/rotating_padding_sampler.py",
    "scripts/p7_prototype_training.py", "scripts/p9_formal_training.py",
    "scripts/p9_formal_isolated_authorization.py"
  ))
}

p9x_runtime_config_path <- function() {
  path <- "config/p9_formal_isolated_runtime.yml"
  if (!file.exists(path)) stop("isolated P9 runtime configuration is missing", call. = FALSE)
  path
}

p9x_publication_config_path <- function() {
  path <- "config/p9_formal_isolated_publication.yml"
  if (!file.exists(path)) stop("isolated P9 publication configuration is missing", call. = FALSE)
  path
}

p9x_config <- function(runtime_config) yaml::read_yaml(runtime_config)

p9x_validate_root <- function(name, runtime_config) {
  cfg <- p9x_config(runtime_config)
  spec <- cfg$roots[[name]]
  if (is.null(spec)) stop("unknown isolated P9 immutable root: ", name, call. = FALSE)
  path <- spec$path
  if (!file.exists(path)) stop("missing isolated P9 immutable root: ", name, call. = FALSE)
  info <- file.info(path)
  if (!identical(as.numeric(info$size), as.numeric(spec$expected_size))) {
    stop("isolated P9 immutable root size mismatch: ", name, call. = FALSE)
  }
  if (!identical(p9x_sha256_file(path), spec$sha256)) {
    stop("isolated P9 immutable root SHA-256 mismatch: ", name, call. = FALSE)
  }
  value <- jsonlite::read_json(path, simplifyVector = FALSE)
  if (!is.null(spec$identity_field)) {
    if (!identical(value[[spec$identity_field]], spec$expected_identity)) {
      stop("isolated P9 immutable root identity mismatch: ", name, call. = FALSE)
    }
  }
  if (!is.null(value$status) && !identical(value$status, "PASS")) {
    stop("isolated P9 immutable root is not accepted: ", name, call. = FALSE)
  }
  if (is.null(value$schema_version)) stop("isolated P9 immutable root schema is missing: ", name, call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}

p9x_validate_cache_manifests <- function(runtime_config, cache_acceptance) {
  cfg <- p9x_config(runtime_config)
  acceptance <- jsonlite::read_json(cache_acceptance, simplifyVector = FALSE)
  if (!identical(acceptance$cache$cache_id, cfg$cache$cache_id) ||
      !identical(as.integer(acceptance$cache$entry_count), as.integer(cfg$cache$entry_count)) ||
      !p9x_decimal_equal(acceptance$cache$total_disk_bytes, cfg$cache$physical_bytes)) {
    stop("isolated P9 cache acceptance contract mismatch", call. = FALSE)
  }
  paths <- vapply(cfg$cache$manifests, function(spec) {
    path <- file.path(cfg$cache$root, spec$path)
    if (!file.exists(path)) stop("missing isolated P9 cache manifest: ", spec$path, call. = FALSE)
    if (!identical(as.numeric(file.info(path)$size), as.numeric(spec$expected_size)) ||
        !identical(p9x_sha256_file(path), spec$sha256)) {
      stop("isolated P9 cache manifest identity mismatch: ", spec$path, call. = FALSE)
    }
    normalizePath(path, mustWork = TRUE)
  }, character(1L))
  production <- jsonlite::read_json(paths[basename(paths) == "production_cache_manifest.json"], simplifyVector = FALSE)
  if (!identical(production$cache_id, cfg$cache$cache_id) ||
      !identical(as.integer(production$entry_count), as.integer(cfg$cache$entry_count))) {
    stop("isolated P9 production cache manifest mismatch", call. = FALSE)
  }
  sort(paths)
}

p9x_parse_outputs <- function(output, prefix) {
  line <- output[startsWith(output, prefix)]
  if (length(line) != 1L) stop("isolated P9 command output mismatch", call. = FALSE)
  jsonlite::fromJSON(sub(paste0("^", prefix), "", line), simplifyVector = TRUE)
}

p9x_publish_authorization <- function(runtime_files, publication_config, immutable_roots,
                                      cache_manifests) {
  invisible(list(runtime_files, immutable_roots, cache_manifests))
  output <- system2(Sys.which("python"), c(
    "scripts/p9_formal_isolated_authorization.py", "publish",
    "--runtime-config", "config/p9_formal_isolated_runtime.yml",
    "--publication-config", publication_config
  ), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop(paste(output, collapse = "\n"), call. = FALSE)
  normalizePath(p9x_parse_outputs(output, "P9_ISOLATED_OUTPUTS="), mustWork = TRUE)
}

p9x_bundle_artifact <- function(bundle, filename, dependency = NULL) {
  invisible(dependency)
  path <- bundle[basename(bundle) == filename]
  if (length(path) != 1L) stop("isolated P9 bundle artifact mismatch: ", filename, call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}

p9x_execute_formal_run <- function(authority, reservation, authorization_acceptance,
                                   matrix, cache_acceptance, cache_manifests, categories,
                                   runtime_files) {
  invisible(list(cache_manifests, runtime_files))
  accepted <- jsonlite::read_json(authorization_acceptance, simplifyVector = FALSE)
  value <- jsonlite::read_json(reservation, simplifyVector = FALSE)
  if (!identical(accepted$status, "PASS") ||
      !identical(accepted$authority_id, jsonlite::read_json(authority)$authority_id) ||
      !identical(accepted$reservation_id, value$reservation_id)) {
    stop("isolated P9 execution authorization acceptance mismatch", call. = FALSE)
  }
  token <- Sys.getenv("FUSE_P9_FORMAL_RESERVATION_ID", unset = "")
  if (!nzchar(token) || !identical(token, value$reservation_id)) {
    stop("isolated P9 formal run requires exact reservation token", call. = FALSE)
  }
  cfg <- yaml::read_yaml("config/p9_formal_isolated_runtime.yml")
  output_root <- file.path(cfg$execution$formal_attempt_root, value$attempt_id)
  if (dir.exists(output_root)) stop("isolated P9 formal attempt output already exists", call. = FALSE)
  args <- c(
    "scripts/p9_formal_training.py", "controller", "--authority", authority,
    "--reservation", reservation, "--matrix", matrix,
    "--cache-acceptance", cache_acceptance, "--cache-root", cfg$cache$root,
    "--categories", categories, "--output-root", output_root,
    "--configuration-id", cfg$execution$configuration_id,
    "--lock-root", cfg$execution$lock_root
  )
  status <- system2(Sys.which("python"), args)
  if (!identical(status, 0L)) stop("isolated P9 formal runner failed", call. = FALSE)
  files <- file.path(output_root, c(
    "formal_run.json", "validation_trace.json", "checkpoint_candidate_index.json",
    "selected_checkpoint.json", "terminal_execution_record.json",
    "cfg_main_attempt_acceptance.json"
  ))
  normalizePath(files, mustWork = TRUE)
}

p9x_run_artifact <- function(bundle, filename, dependency = NULL) {
  invisible(dependency)
  path <- bundle[basename(bundle) == filename]
  if (length(path) != 1L) stop("isolated P9 formal artifact mismatch: ", filename, call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}
