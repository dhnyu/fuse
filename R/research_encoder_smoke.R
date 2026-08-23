encoder_smoke_contract_paths <- function(root = getwd(), thesis_root = path.expand("~/dhnyu-masters-dissertation/template")) {
  c(
    file.path(root, c(
      "config/model_architecture.yml",
      "config/schemas/prototype_encoder_smoke.schema.json",
      "config/serialization_shard.yml",
      "python/prototype_encoder.py",
      "python/prototype_encoder_smoke_impl.py",
      "python/run_prototype_encoder_smoke.py",
      "python/prototype_dataloader.py",
      "python/requirements-encoder.txt",
      "R/research_encoder_smoke.R"
    )),
    file.path(thesis_root, c(
      "materials/tables/results-02-model-dimension-table.typ",
      "materials/tables/results-03-model-structural-configuration-table.typ",
      "materials/tables/results-05-model-architecture-table.typ",
      "sections/chapters/methodology/02-object-modal-embeddings.typ",
      "sections/chapters/methodology/03-object-modality-fusion.typ",
      "sections/chapters/methodology/04-spatial-relations.typ",
      "sections/chapters/methodology/05-scene-embedding.typ",
      "sections/appendices/appendix-a.typ"
    ))
  )
}

load_encoder_smoke_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  config <- yaml::read_yaml(by_name[["model_architecture.yml"]])
  expected <- list(
    accepted = c(config$identity$accepted_dataset_id, "ptd_8b3359690ea2d0bef52d63e3"),
    loader = c(config$identity$dataloader_smoke_id, "pdl_361072e3519a91d0aefc9bb9"),
    dissertation = c(config$identity$dissertation_commit, "87990db83f2b30200cc2d64dc160cb41f691e0e7"),
    controller = c(config$execution$controller, "controller_gpu_02"),
    gpu = c(config$execution$requested_gpu_count, 1),
    precision = c(config$execution$precision, "float32"),
    dimension = c(config$dimensions$latent, 128)
  )
  bad <- names(expected)[vapply(expected, function(value) !identical(as.character(value[[1L]]), as.character(value[[2L]])), logical(1L))]
  if (length(bad)) stop("I18 contract mismatch: ", paste(bad, collapse = ", "), call. = FALSE)
  list(config = config, paths = by_name)
}

run_prototype_encoder_smoke <- function(prototype_training_dataset_acceptance,
                                        prototype_dataloader_smoke,
                                        encoder_smoke_contract_files,
                                        workers = 1L,
                                        threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("I18 target orchestration requires exactly 1 worker and 1 thread", call. = FALSE)
  }
  contract <- load_encoder_smoke_config(encoder_smoke_contract_files)
  accepted <- normalizePath(unlist(prototype_training_dataset_acceptance, use.names = FALSE), mustWork = TRUE)
  accepted_manifest <- accepted[basename(accepted) == "accepted_training_dataset_manifest.json"]
  loader <- normalizePath(unlist(prototype_dataloader_smoke, use.names = FALSE), mustWork = TRUE)
  loader_manifest <- loader[basename(loader) == "prototype_dataloader_smoke.json"]
  if (length(accepted_manifest) != 1L || length(loader_manifest) != 1L) {
    stop("I18 upstream manifest is missing", call. = FALSE)
  }
  args <- c(
    contract$paths[["run_prototype_encoder_smoke.py"]],
    "--accepted-manifest", accepted_manifest,
    "--dataloader-smoke", loader_manifest,
    "--config", contract$paths[["model_architecture.yml"]],
    "--schema", contract$paths[["prototype_encoder_smoke.schema.json"]],
    "--tensor-contract", contract$paths[["serialization_shard.yml"]]
  )
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) {
    stop("I18 encoder smoke failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(result) || !identical(result$status, "PASS")) {
    stop("I18 encoder smoke returned invalid result:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  files <- normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
  required <- unlist(contract$config$output[c("manifest", "parameters", "shapes", "qc", "log")], use.names = FALSE)
  if (!setequal(basename(files), required)) stop("I18 returned incomplete outputs", call. = FALSE)
  files
}
