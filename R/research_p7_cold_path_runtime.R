# P7/P9 execution-only cold-path contract. It is not a P7 scientific parent.

p7_cold_path_runtime_contract_names <- function() {
  c(
    "config/p7_cold_path_runtime.yml",
    "config/schemas/p7_cold_path_runtime_contract.schema.json",
    "config/schemas/p7_cold_path_runtime_acceptance.schema.json",
    "python/p7_cold_path_runtime.py",
    "scripts/p7_cold_path_runtime_cli.py",
    "R/research_p7_cold_path_runtime.R",
    "blueprint/targets_implementation_blueprint.md"
  )
}

p7_cold_path_contract_files <- function(root = ".") {
  paths <- normalizePath(file.path(root, p7_cold_path_runtime_contract_names()), mustWork = TRUE)
  names(paths) <- p7_cold_path_runtime_contract_names()
  paths
}

p7_cold_path_runtime_file <- function(files, name) {
  value <- files[endsWith(files, name)]
  if (length(value) != 1L) stop("P7 cold-path contract lookup mismatch: ", name, call. = FALSE)
  value[[1L]]
}

p7_cold_path_runtime_config <- function(files) {
  yaml::read_yaml(p7_cold_path_runtime_file(files, "config/p7_cold_path_runtime.yml"))
}

p7_cold_path_validate_parents <- function(model_data_acceptance, prototype_training_acceptance,
                                          geometry_cache, files) {
  cfg <- p7_cold_path_runtime_config(files)
  p6 <- jsonlite::read_json(artifact_path(model_data_acceptance, "model_data_acceptance.json"), simplifyVector = FALSE)
  p7 <- jsonlite::read_json(artifact_path(prototype_training_acceptance, "prototype_training_acceptance.json"), simplifyVector = FALSE)
  cache <- jsonlite::read_json(geometry_cache, simplifyVector = FALSE)
  if (!identical(p6$model_data_acceptance_id, cfg$parents$p6_aggregate_acceptance_id) ||
      !identical(p7$acceptance_id, cfg$parents$p7_acceptance_id) ||
      !identical(p7$training_authority_id, cfg$parents$p7_training_authority_id) ||
      !identical(p7$run_id, cfg$parents$p7_run_id) ||
      !identical(cache$cache_id, cfg$parents$p7_geometry_cache_id) ||
      !identical(cache$schema_version, "3.0.0") ||
      !identical(cache$geometry_layout_version, "3.0.0") ||
      !identical(p7$best_checkpoint$checkpoint_id, cfg$parents$p7_best_checkpoint_id) ||
      !identical(p7$latest_checkpoint$checkpoint_id, cfg$parents$p7_latest_checkpoint_id)) {
    stop("P7 cold-path runtime parent lineage mismatch", call. = FALSE)
  }
  invisible(TRUE)
}

p7_cold_path_build_contract <- function(model_data_acceptance, prototype_training_acceptance,
                                         geometry_cache, files) {
  p7_cold_path_validate_parents(model_data_acceptance, prototype_training_acceptance, geometry_cache, files)
  cfg <- p7_cold_path_runtime_config(files)
  output <- tempfile(fileext = ".json"); on.exit(unlink(output), add = TRUE)
  args <- c("scripts/p7_cold_path_runtime_cli.py", "contract",
            "--schema", p7_cold_path_runtime_file(files, "config/schemas/p7_cold_path_runtime_contract.schema.json"),
            "--output", output)
  p7_python(args)
  p7_publish_single_json(output, file.path(cfg$publication_root, "contract"),
                         "cold_path_runtime_contract.json",
                         p7_cold_path_runtime_file(files, "config/schemas/p7_cold_path_runtime_contract.schema.json"),
                         "contract_id")
}

p7_cold_path_verification_reference <- function(files) {
  cfg <- p7_cold_path_runtime_config(files)
  path <- normalizePath(cfg$inputs$verification_record, mustWork = TRUE)
  value <- jsonlite::read_json(path, simplifyVector = FALSE)
  if (!identical(value$status, "PASS") || !identical(value$cache_entry_count, 2144L) ||
      !identical(value$first_40_trace_exact, TRUE) || !identical(value$resume_exact, TRUE)) {
    stop("P7 cold-path production verification is not accepted", call. = FALSE)
  }
  path
}

p7_cold_path_build_acceptance <- function(contract, verification, model_data_acceptance,
                                           prototype_training_acceptance, geometry_cache, files) {
  p7_cold_path_validate_parents(model_data_acceptance, prototype_training_acceptance, geometry_cache, files)
  cfg <- p7_cold_path_runtime_config(files)
  output <- tempfile(fileext = ".json"); on.exit(unlink(output), add = TRUE)
  args <- c("scripts/p7_cold_path_runtime_cli.py", "acceptance",
            "--contract", artifact_path(contract, "cold_path_runtime_contract.json"),
            "--verification", verification,
            "--schema", p7_cold_path_runtime_file(files, "config/schemas/p7_cold_path_runtime_acceptance.schema.json"),
            "--output", output)
  p7_python(args)
  p7_publish_single_json(output, file.path(cfg$publication_root, "acceptance"),
                         "cold_path_runtime_acceptance.json",
                         p7_cold_path_runtime_file(files, "config/schemas/p7_cold_path_runtime_acceptance.schema.json"),
                         "acceptance_id")
}
