# Dissertation Sections 3.6 and 4.2: read-only prototype embedding/retrieval validation.

prototype_model_validation_contract_paths <- function(
    root = getwd(), thesis_root = path.expand("~/dhnyu-masters-dissertation/template")) {
  c(
    file.path(root, c(
      "config/prototype_model_validation.yml",
      "config/schemas/prototype_model_validation.schema.json",
      "config/model_architecture.yml", "config/augmentation.yml", "config/serialization_shard.yml",
      "python/run_prototype_model_validation.py", "python/run_prototype_model_validation_locked.py",
      "python/prototype_encoder.py", "python/prototype_dataloader.py", "python/prototype_augmentation.py",
      "python/prototype_training_data.py", "python/run_prototype_augmentation_benchmark.py",
      "R/research_prototype_model_validation.R"
    )),
    file.path(thesis_root, c(
      "sections/chapters/methodology/06-model-training.typ",
      "sections/chapters/results/02-spatial-scene-retrieval.typ",
      "sections/chapters/results/03-representation-analysis.typ"
    ))
  )
}

run_prototype_model_validation <- function(
    prototype_training_acceptance,
    prototype_training_dataset_acceptance,
    prototype_scene_selection,
    prototype_model_validation_contract_files,
    workers = 40L,
    threads = 1L) {
  if (!identical(as.integer(workers), 40L) || !identical(as.integer(threads), 1L)) {
    stop("I23 requires 40 process workers and one native thread per worker", call. = FALSE)
  }
  accepted_files <- normalizePath(unlist(prototype_training_acceptance, use.names = FALSE), mustWork = TRUE)
  dataset_files <- normalizePath(unlist(prototype_training_dataset_acceptance, use.names = FALSE), mustWork = TRUE)
  selection_files <- normalizePath(unlist(prototype_scene_selection, use.names = FALSE), mustWork = TRUE)
  contract_files <- normalizePath(prototype_model_validation_contract_files, mustWork = TRUE)
  by_name <- setNames(contract_files, basename(contract_files))
  i22_manifest <- accepted_files[basename(accepted_files) == "prototype_training_acceptance_manifest.json"]
  dataset_manifest <- dataset_files[basename(dataset_files) == "accepted_training_dataset_manifest.json"]
  selection_manifest <- selection_files[basename(selection_files) == "prototype_scene_index_manifest.json"]
  selection_index <- selection_files[basename(selection_files) == "prototype_scene_index.parquet"]
  if (length(i22_manifest) != 1L || length(dataset_manifest) != 1L ||
      length(selection_manifest) != 1L || length(selection_index) != 1L) {
    stop("I23 direct parent manifest/index is missing", call. = FALSE)
  }
  config <- yaml::read_yaml(by_name[["prototype_model_validation.yml"]])
  dataset <- jsonlite::read_json(dataset_manifest, simplifyVector = FALSE)
  if (!identical(dataset$training_dataset_id, config$identity$training_dataset_id)) {
    stop("I23 received a foreign I16 dataset", call. = FALSE)
  }
  i19_manifest <- file.path(
    dirname(dataset_manifest), "benchmark", "augmentation",
    config$identity$augmentation_acceptance_id, "prototype_augmentation_manifest.json"
  )
  i19_manifest <- normalizePath(i19_manifest, mustWork = TRUE)
  if (!identical(digest::digest(file = i19_manifest, algo = "sha256", serialize = FALSE),
                 config$identity$augmentation_manifest_sha256)) {
    stop("I23 approved I19 manifest checksum mismatch", call. = FALSE)
  }
  output_root <- file.path(dirname(dataset_manifest), config$output$subdirectory)
  dir.create(output_root, recursive = TRUE, showWarnings = FALSE)
  args <- c(
    by_name[["run_prototype_model_validation_locked.py"]],
    "--i22-manifest", i22_manifest,
    "--accepted-manifest", dataset_manifest,
    "--prototype-manifest", selection_manifest,
    "--prototype-index", selection_index,
    "--i19-manifest", i19_manifest,
    "--tensor-contract", by_name[["serialization_shard.yml"]],
    "--encoder-config", by_name[["model_architecture.yml"]],
    "--augmentation-config", by_name[["augmentation.yml"]],
    "--config", by_name[["prototype_model_validation.yml"]],
    "--schema", by_name[["prototype_model_validation.schema.json"]],
    "--output-root", output_root
  )
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) {
    stop("I23 prototype model validation failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(result) || !identical(result$status, "PASS") ||
      !grepl("^pmv_[0-9a-f]{24}$", result$model_validation_id)) {
    stop("I23 returned invalid output", call. = FALSE)
  }
  files <- normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
  required <- c(config$output$manifest, config$output$embeddings, config$output$original_rankings,
                config$output$augmented_source_rankings, config$output$qc, config$output$report)
  if (!setequal(basename(files), unlist(required, use.names = FALSE))) {
    stop("I23 returned incomplete output files", call. = FALSE)
  }
  manifest <- jsonlite::read_json(files[basename(files) == config$output$manifest], simplifyVector = FALSE)
  if (!identical(manifest$status, "PASS") ||
      !identical(manifest$checkpoint_state$additional_optimizer_steps, 0L)) {
    stop("I23 immutable manifest failed final QC", call. = FALSE)
  }
  files
}
