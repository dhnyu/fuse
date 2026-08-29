# P8 is a plan-only gate. It cannot construct an optimizer or consume evaluation queries.

p8_contract_names <- function() {
  c(
    "config/p8_formal_experiment_plan.yml",
    "config/schemas/p8_methodology_compatibility.schema.json",
    "config/schemas/p8_hyperparameter_configuration_matrix.schema.json",
    "config/schemas/p8_comparison_variant_template_matrix.schema.json",
    "config/schemas/p8_experiment_augmentation_bank_index.schema.json",
    "config/schemas/p8_formal_hyperparameter_experiment_plan.schema.json",
    "config/schemas/p8_comparison_variant_materialization_template.schema.json",
    "config/schemas/p8_formal_experiment_plan_acceptance.schema.json",
    "python/p8_experiment_plan.py", "scripts/p8_formal_experiment_plan.py",
    "R/research_p8_experiment_plan.R", "targets/research_p8_experiment_plan.R",
    "blueprint/targets_implementation_blueprint.md"
  )
}

p8_contract_files <- function(root = ".", dissertation_root = path.expand("~/dhnyu-masters-dissertation")) {
  cfg <- yaml::read_yaml(file.path(root, "config/p8_formal_experiment_plan.yml"))
  local <- normalizePath(file.path(root, p8_contract_names()), mustWork = TRUE)
  thesis <- normalizePath(file.path(dissertation_root, unlist(cfg$methodology$modules)), mustWork = TRUE)
  parents <- normalizePath(unlist(cfg$parent_artifacts), mustWork = TRUE)
  c(local, thesis, parents)
}

p8_read_artifact <- function(value, filename) {
  jsonlite::read_json(artifact_path(value, filename), simplifyVector = FALSE)
}

p8_validate_parent_lineage <- function(config_path) {
  cfg <- yaml::read_yaml(config_path)
  expected <- cfg$parents
  paths <- cfg$parent_artifacts
  p6 <- jsonlite::read_json(paths$p6_acceptance, simplifyVector = FALSE)
  p7 <- jsonlite::read_json(paths$p7_acceptance, simplifyVector = FALSE)
  runtime_contract <- jsonlite::read_json(paths$p7_runtime_contract, simplifyVector = FALSE)
  runtime_acceptance <- jsonlite::read_json(paths$p7_runtime_acceptance, simplifyVector = FALSE)
  p4 <- jsonlite::read_json(paths$p4_acceptance, simplifyVector = FALSE)
  p4_index <- jsonlite::read_json(paths$p4_index, simplifyVector = FALSE)
  validation <- jsonlite::read_json(paths$p5_validation_acceptance, simplifyVector = FALSE)
  observed <- list(
    p6_acceptance_id = p6$model_data_acceptance_id,
    p7_acceptance_id = p7$acceptance_id,
    p7_best_checkpoint_id = p7$best_checkpoint$checkpoint_id,
    p7_latest_checkpoint_id = p7$latest_checkpoint$checkpoint_id,
    p7_runtime_contract_id = runtime_contract$contract_id,
    p7_runtime_acceptance_id = runtime_acceptance$acceptance_id,
    p4_bank_id = p4$bank_id,
    p4_acceptance_id = p4$acceptance_id,
    p4_index_id = p4_index$index_id,
    p5_validation_acceptance_id = validation$acceptance_id,
    p5_validation_query_index_id = validation$query_index_id,
    p5_validation_gallery_id = validation$gallery_id
  )
  if (!identical(observed, expected[names(observed)]) ||
      !identical(p7$status, "PASS") || !identical(runtime_acceptance$status, "PASS") ||
      !identical(p4$status, "PASS") || !identical(p4_index$status, "PASS") ||
      !identical(validation$status, "PASS") || !identical(validation$namespace, "validation-query")) {
    stop("P8 canonical parent lineage mismatch", call. = FALSE)
  }
  invisible(TRUE)
}

p8_build_bundle <- function(contract_files) {
  config_path <- normalizePath("config/p8_formal_experiment_plan.yml", mustWork = TRUE)
  p8_validate_parent_lineage(config_path)
  cfg <- yaml::read_yaml(config_path)
  stage <- tempfile("p8-plan-"); dir.create(stage)
  on.exit(unlink(stage, recursive = TRUE), add = TRUE)
  status <- system2(research_python_executable(), c(
    "scripts/p8_formal_experiment_plan.py", "build", "--config", config_path,
    "--dissertation-root", normalizePath(path.expand("~/dhnyu-masters-dissertation"), mustWork = TRUE),
    "--output", stage
  ))
  if (!identical(status, 0L)) stop("P8 plan builder failed", call. = FALSE)
  acceptance <- jsonlite::read_json(file.path(stage, "formal_experiment_plan_acceptance.json"), simplifyVector = FALSE)
  filenames <- paste0(c(
    "methodology_compatibility", "hyperparameter_configuration_matrix",
    "comparison_variant_template_matrix", "experiment_augmentation_bank_index",
    "formal_hyperparameter_experiment_plan", "comparison_variant_materialization_template",
    "formal_experiment_plan_acceptance"
  ), ".json")
  final_dir <- file.path(cfg$publication_root, acceptance$authority_id, acceptance$acceptance_id)
  publish_deterministic_directory(final_dir, filenames, writer = function(destination) {
    file.copy(file.path(stage, filenames), file.path(destination, filenames), overwrite = FALSE)
  })
}

p8_bundle_artifact <- function(bundle, name, dependency = NULL) {
  invisible(dependency)
  path <- bundle[basename(bundle) == paste0(name, ".json")]
  if (length(path) != 1L) stop("P8 bundle artifact lookup mismatch: ", name, call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}
