p6_contract_names <- function() {
  c(
    "config/p6_model_dataloader.yml",
    "config/spatial_acceptance_aliases.yml",
    "config/schemas/p6_architecture_manifest.schema.json",
    "config/schemas/p6_dataloader_acceptance.schema.json",
    "config/schemas/p6_cpu_smoke.schema.json",
    "config/schemas/p6_model_data_acceptance.schema.json",
    "python/p6_data.py", "python/p6_model.py", "scripts/p6_model_dataloader.py"
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
  config_path <- contract_files[["config/p6_model_dataloader.yml"]]
  config <- yaml::read_yaml(config_path)
  scientific <- config
  scientific$publication_root <- NULL
  files <- lapply(sort(names(contract_files), method = "radix"), function(name) {
    list(path = name, sha256 = if (name == "config/p6_model_dataloader.yml") p0_scientific_sha256(scientific) else sha256_file(contract_files[[name]]))
  })
  list(config = config, config_path = config_path, files = files,
       implementation_hash = p0_scientific_sha256(list(version = config$implementation_version, files = files)))
}

p6_contract_file <- function(contract_files, name) {
  matches <- contract_files[endsWith(contract_files, name)]
  if (length(matches) != 1L) stop("P6 tracked contract lookup mismatch: ", name, call. = FALSE)
  matches[[1L]]
}

p6_root_from_artifact <- function(paths, levels) {
  path <- normalizePath(paths[[1L]], mustWork = TRUE)
  for (index in seq_len(levels)) path <- dirname(path)
  path
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

p6_build_architecture <- function(model_methodology_contract, base_spatial_acceptance, contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  model_contract <- artifact_path(model_methodology_contract, "model_methodology_contract.json")
  category_path <- artifact_path(base_spatial_acceptance, "spatial_categories.json")
  output <- tempfile(fileext = ".json")
  p6_run(c("scripts/p6_model_dataloader.py", "architecture", "--config", spec$config_path,
           "--model-contract", model_contract, "--categories", category_path, "--output", output))
  value <- jsonlite::read_json(output, simplifyVector = FALSE)
  destination <- file.path(cfg$publication_root, "architecture")
  paths <- p6_publish_json(output, destination, "architecture_manifest.json",
                           p6_contract_file(contract_files, "config/schemas/p6_architecture_manifest.schema.json"),
                           "model_authority_id")
  unlink(output); paths
}

p6_build_preprocessing <- function(original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                   fixed_query_acceptance, base_spatial_acceptance,
                                   contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  roots <- c(p3 = p6_root_from_artifact(original_scene_dataset_acceptance, 3L),
             p4 = p6_root_from_artifact(augmentation_bank_acceptance, 3L),
             p5 = p6_root_from_artifact(fixed_query_acceptance, 3L))
  output <- tempfile(fileext = ".json")
  p6_run(c("scripts/p6_model_dataloader.py", "preprocessing", "--config", spec$config_path,
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
                                           fixed_query_acceptance, base_spatial_acceptance,
                                           p6_preprocessing_contract, contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  roots <- c(p3 = p6_root_from_artifact(original_scene_dataset_acceptance, 3L),
             p4 = p6_root_from_artifact(augmentation_bank_acceptance, 3L),
             p5 = p6_root_from_artifact(fixed_query_acceptance, 3L))
  output <- tempfile(fileext = ".json")
  p6_run(c("scripts/p6_model_dataloader.py", "dataloader", "--config", spec$config_path,
           "--p3-root", roots[["p3"]], "--p4-root", roots[["p4"]], "--p5-root", roots[["p5"]],
           "--categories", artifact_path(base_spatial_acceptance, "spatial_categories.json"),
           "--preprocessing", artifact_path(p6_preprocessing_contract, "preprocessing_contract.json"), "--output", output))
  paths <- p6_publish_json(output, file.path(cfg$publication_root, "dataloader"), "dataloader_acceptance.json",
                           p6_contract_file(contract_files, "config/schemas/p6_dataloader_acceptance.schema.json"),
                           "dataloader_acceptance_id")
  unlink(output); paths
}

p6_build_cpu_smoke <- function(original_scene_dataset_acceptance, augmentation_bank_acceptance,
                               fixed_query_acceptance, base_spatial_acceptance,
                               p6_preprocessing_contract, d64_model_architecture_contract,
                               p6_dataloader_acceptance, contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  roots <- c(p3 = p6_root_from_artifact(original_scene_dataset_acceptance, 3L),
             p4 = p6_root_from_artifact(augmentation_bank_acceptance, 3L),
             p5 = p6_root_from_artifact(fixed_query_acceptance, 3L))
  output <- tempfile(fileext = ".json")
  Sys.setenv(OMP_NUM_THREADS = "1", OPENBLAS_NUM_THREADS = "1", MKL_NUM_THREADS = "1",
             BLIS_NUM_THREADS = "1", VECLIB_MAXIMUM_THREADS = "1", NUMEXPR_NUM_THREADS = "1",
             GDAL_NUM_THREADS = "1", ARROW_NUM_THREADS = "1", PYTHONDONTWRITEBYTECODE = "1")
  data.table::setDTthreads(1L)
  p6_run(c("scripts/p6_model_dataloader.py", "smoke", "--config", spec$config_path,
           "--p3-root", roots[["p3"]], "--p4-root", roots[["p4"]], "--p5-root", roots[["p5"]],
           "--categories", artifact_path(base_spatial_acceptance, "spatial_categories.json"),
           "--scene-stats", artifact_path(base_spatial_acceptance, "scene_spatial_statistics.parquet"),
           "--preprocessing", artifact_path(p6_preprocessing_contract, "preprocessing_contract.json"),
           "--architecture", artifact_path(d64_model_architecture_contract, "architecture_manifest.json"), "--output", output))
  paths <- p6_publish_json(output, file.path(cfg$publication_root, "smoke"), "cpu_functional_smoke.json",
                           p6_contract_file(contract_files, "config/schemas/p6_cpu_smoke.schema.json"), "smoke_id")
  unlink(output); paths
}

p6_final_acceptance <- function(d64_model_architecture_contract, p6_dataloader_acceptance,
                                d64_encoder_cpu_smoke, reduced_methodology_authority,
                                fixed_query_acceptance, contract_files) {
  spec <- p6_spec(contract_files); cfg <- spec$config
  output <- tempfile(fileext = ".json")
  p6_run(c("scripts/p6_model_dataloader.py", "aggregate", "--config", spec$config_path,
           "--architecture", artifact_path(d64_model_architecture_contract, "architecture_manifest.json"),
           "--dataloader", artifact_path(p6_dataloader_acceptance, "dataloader_acceptance.json"),
           "--smoke", artifact_path(d64_encoder_cpu_smoke, "cpu_functional_smoke.json"), "--output", output))
  paths <- p6_publish_json(output, file.path(cfg$publication_root, "acceptance"), "model_data_acceptance.json",
                           p6_contract_file(contract_files, "config/schemas/p6_model_data_acceptance.schema.json"),
                           "model_data_acceptance_id")
  unlink(output); paths
}
