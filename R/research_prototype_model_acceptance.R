# Blueprint I24: read-only final gate for the accepted prototype model path.

prototype_model_acceptance_contract_paths <- function(
    root = getwd(), thesis_root = path.expand("~/dhnyu-masters-dissertation/template")) {
  c(
    file.path(root, c(
      "config/prototype_model_acceptance.yml",
      "config/schemas/prototype_model_acceptance.schema.json",
      "config/schemas/prototype_dataloader_smoke.schema.json",
      "config/schemas/prototype_encoder_smoke.schema.json",
      "config/schemas/prototype_augmentation_benchmark.schema.json",
      "config/schemas/prototype_training_acceptance.schema.json",
      "config/schemas/prototype_model_validation.schema.json",
      "python/accept_prototype_model.py",
      "R/research_prototype_model_acceptance.R",
      "blueprint/targets_implementation_blueprint.md"
    )),
    file.path(thesis_root, c(
      "sections/chapters/methodology/06-model-training.typ",
      "sections/chapters/results/02-spatial-scene-retrieval.typ",
      "sections/chapters/results/03-representation-analysis.typ"
    ))
  )
}

run_prototype_model_acceptance <- function(
    prototype_dataloader_smoke,
    prototype_encoder_smoke,
    prototype_augmentation_benchmark,
    prototype_training_acceptance,
    prototype_model_validation,
    prototype_model_acceptance_contract_files) {
  files <- list(
    dataloader = normalizePath(unlist(prototype_dataloader_smoke, use.names = FALSE), mustWork = TRUE),
    encoder = normalizePath(unlist(prototype_encoder_smoke, use.names = FALSE), mustWork = TRUE),
    augmentation = normalizePath(unlist(prototype_augmentation_benchmark, use.names = FALSE), mustWork = TRUE),
    training = normalizePath(unlist(prototype_training_acceptance, use.names = FALSE), mustWork = TRUE),
    validation = normalizePath(unlist(prototype_model_validation, use.names = FALSE), mustWork = TRUE)
  )
  manifests <- c(
    dataloader = files$dataloader[basename(files$dataloader) == "prototype_dataloader_smoke.json"],
    encoder = files$encoder[basename(files$encoder) == "prototype_encoder_manifest.json"],
    augmentation = files$augmentation[basename(files$augmentation) == "prototype_augmentation_manifest.json"],
    training = files$training[basename(files$training) == "prototype_training_acceptance_manifest.json"],
    validation = files$validation[basename(files$validation) == "prototype_model_validation_manifest.json"]
  )
  if (length(manifests) != 5L || any(!file.exists(manifests))) {
    stop("I24 direct parent manifest is missing", call. = FALSE)
  }
  contract_files <- normalizePath(prototype_model_acceptance_contract_files, mustWork = TRUE)
  by_name <- setNames(contract_files, basename(contract_files))
  config <- yaml::read_yaml(by_name[["prototype_model_acceptance.yml"]])
  dataset_root <- dirname(dirname(dirname(dirname(manifests[["dataloader"]]))))
  output_root <- file.path(dataset_root, config$output$subdirectory)
  args <- c(
    by_name[["accept_prototype_model.py"]],
    "--dataloader-manifest", manifests[["dataloader"]],
    "--dataloader-schema", by_name[["prototype_dataloader_smoke.schema.json"]],
    "--encoder-manifest", manifests[["encoder"]],
    "--encoder-schema", by_name[["prototype_encoder_smoke.schema.json"]],
    "--augmentation-manifest", manifests[["augmentation"]],
    "--augmentation-schema", by_name[["prototype_augmentation_benchmark.schema.json"]],
    "--training-manifest", manifests[["training"]],
    "--training-schema", by_name[["prototype_training_acceptance.schema.json"]],
    "--validation-manifest", manifests[["validation"]],
    "--validation-schema", by_name[["prototype_model_validation.schema.json"]],
    "--config", by_name[["prototype_model_acceptance.yml"]],
    "--schema", by_name[["prototype_model_acceptance.schema.json"]],
    "--implementation", by_name[["accept_prototype_model.py"]],
    "--output-root", output_root
  )
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) {
    stop("I24 prototype model acceptance failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(result) || !identical(result$status, "PASS") ||
      !grepl("^pma_[0-9a-f]{24}$", result$model_acceptance_id)) {
    stop("I24 returned invalid output", call. = FALSE)
  }
  outputs <- normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
  required <- c(config$output$manifest, config$output$summary)
  if (!setequal(basename(outputs), unlist(required, use.names = FALSE))) {
    stop("I24 returned incomplete output files", call. = FALSE)
  }
  manifest <- jsonlite::read_json(outputs[basename(outputs) == config$output$manifest], simplifyVector = FALSE)
  if (!identical(manifest$status, "PASS") ||
      !identical(manifest$zero_compute$additional_optimizer_steps, 0L) ||
      !identical(manifest$zero_compute$checkpoint_sha256_before,
                 manifest$zero_compute$checkpoint_sha256_after)) {
    stop("I24 immutable manifest failed final QC", call. = FALSE)
  }
  outputs
}
