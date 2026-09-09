p6_contract_names <- function() {
  c(
    "config/model_inputs.yml",
    "config/spatial_acceptance_aliases.yml",
    "config/schemas/p6_architecture_manifest.schema.json",
    "config/schemas/p6_dataloader_acceptance.schema.json",
    "config/schemas/p6_cpu_smoke.schema.json",
    "config/schemas/p6_model_data_acceptance.schema.json",
    "R/canonical_config.R", "python/canonical_config.py",
    "python/model_data.py", "python/scene_model.py", "scripts/build_model_inputs.py"
  )
}

p6_contract_files <- function(root = ".") {
  files <- p6_contract_names()
  paths <- normalizePath(file.path(root, files), mustWork = TRUE)
  names(paths) <- files
  paths
}

p6_spec <- function(contract_files) {
  if (length(contract_files) != length(p6_contract_names())) {
    stop("P6 tracked contract file count mismatch", call. = FALSE)
  }
  names(contract_files) <- p6_contract_names()
  config_path <- contract_files[["config/model_inputs.yml"]]
  config <- yaml::read_yaml(config_path)
  full_canonical_config_sha256 <- canonical_yaml_sha256(config_path)
  if (!identical(full_canonical_config_sha256,
                 "c105bbb1c013d3351501400409dd127524b145e3d39157a6ec843b254835e489")) {
    stop("P6 committed canonical configuration checksum mismatch", call. = FALSE)
  }
  scientific <- config
  scientific$publication_root <- NULL
  files <- lapply(sort(names(contract_files), method = "radix"), function(name) {
    list(path = name, sha256 = if (name == "config/model_inputs.yml") canonical_yaml_sha256(config_path, "publication_root") else sha256_file(contract_files[[name]]))
  })
  list(config = config, config_path = config_path, files = files,
       full_canonical_config_sha256 = full_canonical_config_sha256,
       implementation_hash = p0_scientific_sha256(list(version = config$implementation_version, files = files)))
}

p6_runtime_config <- function(spec, reduced_methodology_authority,
                              original_scene_dataset_acceptance,
                              augmentation_bank_acceptance,
                              effective_augmentation_bank_index,
                              fixed_query_acceptance,
                              base_spatial_acceptance) {
  authority <- jsonlite::read_json(artifact_path(reduced_methodology_authority, "reduced_methodology_authority.json"), simplifyVector = FALSE)
  p3 <- jsonlite::read_json(artifact_path(original_scene_dataset_acceptance, "original_scene_dataset_acceptance.json"), simplifyVector = FALSE)
  p4 <- jsonlite::read_json(artifact_path(augmentation_bank_acceptance, "augmentation_bank_acceptance.json"), simplifyVector = FALSE)
  p4_index <- jsonlite::read_json(artifact_path(effective_augmentation_bank_index, "effective_bank_index.json"), simplifyVector = FALSE)
  p5 <- jsonlite::read_json(artifact_path(fixed_query_acceptance, "fixed_query_acceptance.json"), simplifyVector = FALSE)
  p2 <- jsonlite::read_json(artifact_path(base_spatial_acceptance, "base_spatial_acceptance.json"), simplifyVector = FALSE)
  if (!all(vapply(list(authority, p3, p4, p4_index, p5, p2), function(x) identical(x$status %||% x$overall_status, "PASS"), logical(1L)))) {
    stop("P6 runtime parent is not accepted", call. = FALSE)
  }
  config <- spec$config
  config$parents <- list(
    authority_id = authority$authority_id,
    scene_index_id = p2$scene_index_id,
    scene_acceptance_id = p2$scene_acceptance_id,
    observation_id = p2$original_observation_id,
    base_spatial_acceptance_id = p2$acceptance_id,
    p3_cache_id = p3$cache_id,
    p3_acceptance_id = p3$acceptance_id,
    p4_master_bank_id = p4$bank_id,
    p4_logical_index_id = p4_index$index_id,
    p5_query_authority_id = p5$query_authority_id,
    p5_acceptance_id = p5$acceptance_id
  )
  path <- tempfile(fileext = ".json")
  write_json_file(config, path)
  path
}

p6_contract_file <- function(contract_files, name) {
  matches <- contract_files[endsWith(contract_files, name)]
  if (length(matches) != 1L) stop("P6 tracked contract lookup mismatch: ", name, call. = FALSE)
  matches[[1L]]
}

p6_root_from_identity <- function(paths, identity, label) {
  if (!is.character(paths) || !length(paths) || anyNA(paths) ||
      !is.character(identity) || length(identity) != 1L || is.na(identity) || !nzchar(identity)) {
    stop("P6 ", label, " root identity inputs are invalid", call. = FALSE)
  }
  missing_paths <- paths[!file.exists(paths)]
  if (length(missing_paths)) {
    stop("P6 ", label, " artifact path is missing: ", missing_paths[[1L]], call. = FALSE)
  }
  normalized <- normalizePath(paths, mustWork = TRUE)
  ancestors <- unique(unlist(lapply(normalized, function(path) {
    current <- if (dir.exists(path)) path else dirname(path)
    result <- character()
    repeat {
      result <- c(result, current)
      parent <- dirname(current)
      if (identical(parent, current)) break
      current <- parent
    }
    result
  }), use.names = FALSE))
  candidates <- ancestors[basename(ancestors) == identity & dir.exists(ancestors)]
  if (length(candidates) != 1L) {
    stop("P6 ", label, " root must resolve exactly one generation for identity ",
         identity, "; found ", length(candidates), call. = FALSE)
  }
  root <- normalizePath(candidates[[1L]], mustWork = TRUE)
  prefix <- paste0(root, .Platform$file.sep)
  if (any(!startsWith(normalized, prefix))) {
    stop("P6 ", label, " artifacts do not share the resolved generation root", call. = FALSE)
  }
  root
}

p6_resolve_p3_cache_generation <- function(paths) {
  if (!is.character(paths) || !length(paths) || anyNA(paths)) {
    stop("P6 P3 cache generation artifact paths are invalid", call. = FALSE)
  }
  missing_paths <- paths[!file.exists(paths)]
  if (length(missing_paths)) {
    stop("P6 P3 cache generation artifact path is missing: ", missing_paths[[1L]], call. = FALSE)
  }
  acceptance_path <- artifact_path(paths, "original_scene_dataset_acceptance.json")
  cache_manifest_path <- artifact_path(paths, "original_scene_cache_manifest.json")
  acceptance <- jsonlite::read_json(acceptance_path, simplifyVector = FALSE)
  cache_manifest <- jsonlite::read_json(cache_manifest_path, simplifyVector = FALSE)
  if (!identical(acceptance$status, "PASS") || !identical(cache_manifest$status, "PASS")) {
    stop("P6 P3 cache generation requires PASS acceptance and cache manifest", call. = FALSE)
  }
  cache_id <- acceptance$cache_id
  if (!is.character(cache_id) || length(cache_id) != 1L || is.na(cache_id) || !nzchar(cache_id) ||
      !identical(cache_manifest$cache_id, cache_id)) {
    stop("P6 P3 accepted cache identity mismatch", call. = FALSE)
  }
  acceptance_id <- acceptance$acceptance_id
  index_id <- cache_manifest$index_id
  counts <- list(acceptance$scene_count, cache_manifest$scene_count)
  if (!is.character(acceptance_id) || length(acceptance_id) != 1L || is.na(acceptance_id) ||
      !nzchar(acceptance_id) || !is.character(index_id) || length(index_id) != 1L ||
      is.na(index_id) || !nzchar(index_id) ||
      !all(vapply(counts, function(value) is.numeric(value) && length(value) == 1L &&
                    !is.na(value) && is.finite(value) && value == as.integer(value), logical(1L)))) {
    stop("P6 P3 accepted cache manifest identity fields are invalid", call. = FALSE)
  }
  root <- p6_root_from_identity(paths, cache_id, "P3 cache generation")
  if (!identical(basename(root), cache_id)) {
    stop("P6 P3 cache generation basename does not match accepted cache ID", call. = FALSE)
  }
  if (!identical(basename(dirname(acceptance_path)), acceptance_id)) {
    stop("P6 P3 acceptance path identity mismatch", call. = FALSE)
  }
  index_root <- file.path(root, "index")
  if (!dir.exists(index_root)) {
    stop("P6 P3 accepted cache generation index directory is missing", call. = FALSE)
  }
  index_paths <- list.files(
    index_root, pattern = "^scene_to_shard[.]parquet$",
    recursive = TRUE, full.names = TRUE
  )
  if (length(index_paths) != 1L) {
    stop("P6 P3 accepted cache generation must contain exactly one scene index; found ",
         length(index_paths), call. = FALSE)
  }
  index_path <- normalizePath(index_paths[[1L]], mustWork = TRUE)
  index_dir <- dirname(index_path)
  index_manifest_path <- file.path(index_dir, "index_manifest.json")
  if (!file.exists(index_manifest_path)) {
    stop("P6 P3 accepted scene index manifest is missing", call. = FALSE)
  }
  index_manifest <- jsonlite::read_json(index_manifest_path, simplifyVector = FALSE)
  index_scene_count <- index_manifest$scene_count
  if (!is.numeric(index_scene_count) || length(index_scene_count) != 1L ||
      is.na(index_scene_count) || !is.finite(index_scene_count) ||
      index_scene_count != as.integer(index_scene_count)) {
    stop("P6 P3 accepted scene index identity fields are invalid", call. = FALSE)
  }
  identity_checks <- c(
    identical(index_manifest$status, "PASS"),
    identical(index_manifest$cache_id, cache_id),
    identical(index_manifest$index_id, index_id),
    identical(basename(index_dir), index_manifest$index_id),
    identical(as.integer(index_scene_count), as.integer(acceptance$scene_count)),
    identical(as.integer(cache_manifest$scene_count), as.integer(acceptance$scene_count))
  )
  if (!all(identity_checks)) {
    stop("P6 P3 accepted cache/index identity mismatch", call. = FALSE)
  }
  list(
    root = root, cache_id = cache_id, index_id = index_manifest$index_id,
    index_path = index_path, index_manifest_path = normalizePath(index_manifest_path, mustWork = TRUE)
  )
}

p6_resolve_artifact_roots <- function(original_scene_dataset_acceptance,
                                      augmentation_bank_acceptance,
                                      fixed_query_acceptance) {
  p3 <- p6_resolve_p3_cache_generation(original_scene_dataset_acceptance)
  p4 <- jsonlite::read_json(
    artifact_path(augmentation_bank_acceptance, "augmentation_bank_acceptance.json"),
    simplifyVector = FALSE
  )
  p5 <- jsonlite::read_json(
    artifact_path(fixed_query_acceptance, "fixed_query_acceptance.json"),
    simplifyVector = FALSE
  )
  if (!identical(p4$status, "PASS") || !identical(p5$status, "PASS")) {
    stop("P6 P4/P5 root resolution requires accepted parents", call. = FALSE)
  }
  c(
    p3 = p3$root,
    p4 = p6_root_from_identity(augmentation_bank_acceptance, p4$bank_id, "P4 bank generation"),
    p5 = p6_root_from_identity(fixed_query_acceptance, p5$query_authority_id, "P5 query generation")
  )
}

p6_run <- function(arguments) {
  result <- system2(research_python_executable(), arguments, stdout = TRUE, stderr = TRUE)
  status <- attr(result, "status") %||% 0L
  if (status != 0L) stop("P6 command failed: ", paste(result, collapse = " | "), call. = FALSE)
  invisible(result)
}

p6_publish_json <- function(source, destination, filename, schema, id_field) {
  value <- jsonlite::read_json(source, simplifyVector = FALSE)
  if (is.null(value[[id_field]])) stop("P6 artifact ID field is missing: ", id_field, call. = FALSE)
  root <- file.path(destination, value[[id_field]])
  p1_publish_immutable_bundle(root, filename, function(stage) {
    if (!file.copy(source, file.path(stage, filename))) stop("P6 artifact copy failed", call. = FALSE)
    validate_json_schema_file(file.path(stage, filename), schema)
  })
}

p6_build_architecture <- function(model_methodology_contract, reduced_methodology_authority,
                                  original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                  effective_augmentation_bank_index, fixed_query_acceptance,
                                  base_spatial_acceptance, contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  runtime_config <- p6_runtime_config(spec, reduced_methodology_authority, original_scene_dataset_acceptance,
                                      augmentation_bank_acceptance, effective_augmentation_bank_index,
                                      fixed_query_acceptance, base_spatial_acceptance)
  on.exit(unlink(runtime_config), add = TRUE)
  model_contract <- artifact_path(model_methodology_contract, "model_methodology_contract.json")
  category_path <- artifact_path(base_spatial_acceptance, "spatial_categories.json")
  output <- tempfile(fileext = ".json")
  p6_run(c("scripts/build_model_inputs.py", "architecture", "--config", runtime_config,
           "--model-contract", model_contract, "--categories", category_path, "--output", output))
  value <- jsonlite::read_json(output, simplifyVector = FALSE)
  destination <- file.path(cfg$publication_root, "architecture")
  paths <- p6_publish_json(output, destination, "architecture_manifest.json",
                           p6_contract_file(contract_files, "config/schemas/p6_architecture_manifest.schema.json"),
                           "model_authority_id")
  unlink(output); paths
}

p6_build_preprocessing <- function(original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                   effective_augmentation_bank_index, fixed_query_acceptance,
                                   reduced_methodology_authority, base_spatial_acceptance,
                                   contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  runtime_config <- p6_runtime_config(spec, reduced_methodology_authority, original_scene_dataset_acceptance,
                                      augmentation_bank_acceptance, effective_augmentation_bank_index,
                                      fixed_query_acceptance, base_spatial_acceptance)
  on.exit(unlink(runtime_config), add = TRUE)
  roots <- p6_resolve_artifact_roots(
    original_scene_dataset_acceptance, augmentation_bank_acceptance, fixed_query_acceptance
  )
  output <- tempfile(fileext = ".json")
  p6_run(c("scripts/build_model_inputs.py", "preprocessing", "--config", runtime_config,
           "--p3-root", roots[["p3"]], "--p4-root", roots[["p4"]], "--p5-root", roots[["p5"]],
           "--categories", artifact_path(base_spatial_acceptance, "spatial_categories.json"), "--output", output))
  value <- jsonlite::read_json(output, simplifyVector = FALSE)
  destination <- file.path(cfg$publication_root, "preprocessing", value$preprocessing_id)
  paths <- p1_publish_immutable_bundle(destination, "preprocessing_contract.json", function(stage) {
    if (!file.copy(output, file.path(stage, "preprocessing_contract.json"))) stop("P6 preprocessing copy failed", call. = FALSE)
  })
  unlink(output); paths
}

p6_build_dataloader_acceptance <- function(original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                           effective_augmentation_bank_index, fixed_query_acceptance,
                                           reduced_methodology_authority, base_spatial_acceptance,
                                           p6_preprocessing_contract, contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  runtime_config <- p6_runtime_config(spec, reduced_methodology_authority, original_scene_dataset_acceptance,
                                      augmentation_bank_acceptance, effective_augmentation_bank_index,
                                      fixed_query_acceptance, base_spatial_acceptance)
  on.exit(unlink(runtime_config), add = TRUE)
  roots <- p6_resolve_artifact_roots(
    original_scene_dataset_acceptance, augmentation_bank_acceptance, fixed_query_acceptance
  )
  output <- tempfile(fileext = ".json")
  p6_run(c("scripts/build_model_inputs.py", "dataloader", "--config", runtime_config,
           "--p3-root", roots[["p3"]], "--p4-root", roots[["p4"]], "--p5-root", roots[["p5"]],
           "--categories", artifact_path(base_spatial_acceptance, "spatial_categories.json"),
           "--preprocessing", artifact_path(p6_preprocessing_contract, "preprocessing_contract.json"), "--output", output))
  paths <- p6_publish_json(output, file.path(cfg$publication_root, "dataloader"), "dataloader_acceptance.json",
                           p6_contract_file(contract_files, "config/schemas/p6_dataloader_acceptance.schema.json"),
                           "dataloader_acceptance_id")
  unlink(output); paths
}

p6_build_cpu_smoke <- function(original_scene_dataset_acceptance, augmentation_bank_acceptance,
                               effective_augmentation_bank_index, fixed_query_acceptance,
                               reduced_methodology_authority, base_spatial_acceptance,
                               p6_preprocessing_contract, model_architecture_contract,
                               model_dataloader_acceptance, contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  runtime_config <- p6_runtime_config(spec, reduced_methodology_authority, original_scene_dataset_acceptance,
                                      augmentation_bank_acceptance, effective_augmentation_bank_index,
                                      fixed_query_acceptance, base_spatial_acceptance)
  on.exit(unlink(runtime_config), add = TRUE)
  roots <- p6_resolve_artifact_roots(
    original_scene_dataset_acceptance, augmentation_bank_acceptance, fixed_query_acceptance
  )
  output <- tempfile(fileext = ".json")
  Sys.setenv(OMP_NUM_THREADS = "1", OPENBLAS_NUM_THREADS = "1", MKL_NUM_THREADS = "1",
             BLIS_NUM_THREADS = "1", VECLIB_MAXIMUM_THREADS = "1", NUMEXPR_NUM_THREADS = "1",
             GDAL_NUM_THREADS = "1", ARROW_NUM_THREADS = "1", PYTHONDONTWRITEBYTECODE = "1")
  data.table::setDTthreads(1L)
  p6_run(c("scripts/build_model_inputs.py", "smoke", "--config", runtime_config,
           "--p3-root", roots[["p3"]], "--p4-root", roots[["p4"]], "--p5-root", roots[["p5"]],
           "--categories", artifact_path(base_spatial_acceptance, "spatial_categories.json"),
           "--scene-stats", artifact_path(base_spatial_acceptance, "scene_spatial_statistics.parquet"),
           "--preprocessing", artifact_path(p6_preprocessing_contract, "preprocessing_contract.json"),
           "--architecture", artifact_path(model_architecture_contract, "architecture_manifest.json"), "--output", output))
  paths <- p6_publish_json(output, file.path(cfg$publication_root, "smoke"), "cpu_functional_smoke.json",
                           p6_contract_file(contract_files, "config/schemas/p6_cpu_smoke.schema.json"), "smoke_id")
  unlink(output); paths
}

p6_final_acceptance <- function(model_architecture_contract, model_dataloader_acceptance,
                                encoder_cpu_smoke, reduced_methodology_authority,
                                original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                effective_augmentation_bank_index, fixed_query_acceptance,
                                base_spatial_acceptance, contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  runtime_config <- p6_runtime_config(spec, reduced_methodology_authority, original_scene_dataset_acceptance,
                                      augmentation_bank_acceptance, effective_augmentation_bank_index,
                                      fixed_query_acceptance, base_spatial_acceptance)
  on.exit(unlink(runtime_config), add = TRUE)
  output <- tempfile(fileext = ".json")
  p6_run(c("scripts/build_model_inputs.py", "aggregate", "--config", runtime_config,
           "--architecture", artifact_path(model_architecture_contract, "architecture_manifest.json"),
           "--dataloader", artifact_path(model_dataloader_acceptance, "dataloader_acceptance.json"),
           "--smoke", artifact_path(encoder_cpu_smoke, "cpu_functional_smoke.json"), "--output", output))
  paths <- p6_publish_json(output, file.path(cfg$publication_root, "acceptance"), "model_data_acceptance.json",
                           p6_contract_file(contract_files, "config/schemas/p6_model_data_acceptance.schema.json"),
                           "model_data_acceptance_id")
  unlink(output); paths
}
