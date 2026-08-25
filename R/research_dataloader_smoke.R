# Dissertation methodology Sections 3.2-3.4: I17 validates indexed loading and
# ragged batching only; model and augmentation semantics begin downstream.

dataloader_smoke_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/dataloader_smoke.yml",
    "config/schemas/prototype_dataloader_smoke.schema.json",
    "config/serialization_shard.yml",
    "python/prototype_dataloader.py",
    "python/run_prototype_dataloader_smoke.py",
    "python/serialize_prototype_shard.py",
    "python/requirements-dataloader.txt",
    "R/research_dataloader_smoke.R"
  ))
}

load_dataloader_smoke_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c(
    "dataloader_smoke.yml", "prototype_dataloader_smoke.schema.json",
    "serialization_shard.yml", "prototype_dataloader.py",
    "run_prototype_dataloader_smoke.py", "serialize_prototype_shard.py",
    "requirements-dataloader.txt", "research_dataloader_smoke.R"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing I17 contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  config <- yaml::read_yaml(by_name[["dataloader_smoke.yml"]])
  expected <- list(
    accepted = c(config$identity$accepted_dataset_id, "ptd_bcb9e6a1061ff7ca9c716b20"),
    controller = c(config$execution$controller, "controller_05"),
    gpu = c(config$execution$gpu, 0), scenes = c(config$expected$scenes, 320),
    scale = c(config$coordinates$geometry_scale_to_m, 500)
  )
  bad <- names(expected)[vapply(expected, function(x) !identical(as.character(x[[1L]]), as.character(x[[2L]])), logical(1L))]
  if (length(bad)) stop("I17 contract mismatch: ", paste(bad, collapse = ", "), call. = FALSE)
  if (!identical(as.integer(unlist(config$execution$candidate_workers)), 40L)) {
    stop("I17 full-population smoke requires 40 process workers", call. = FALSE)
  }
  list(config = config, paths = by_name)
}

run_prototype_dataloader_smoke <- function(
    prototype_training_dataset_acceptance,
    dataloader_smoke_contract_files,
    workers = 1L,
    threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("I17 target execution requires exactly 1 worker and 1 orchestration thread", call. = FALSE)
  }
  contract <- load_dataloader_smoke_config(dataloader_smoke_contract_files)
  accepted <- normalizePath(unlist(prototype_training_dataset_acceptance, use.names = FALSE), mustWork = TRUE)
  manifest <- accepted[basename(accepted) == "accepted_training_dataset_manifest.json"]
  if (length(manifest) != 1L) stop("I16 accepted manifest is missing", call. = FALSE)
  args <- c(
    contract$paths[["run_prototype_dataloader_smoke.py"]],
    "--accepted-manifest", manifest,
    "--config", contract$paths[["dataloader_smoke.yml"]],
    "--schema", contract$paths[["prototype_dataloader_smoke.schema.json"]],
    "--tensor-contract", contract$paths[["serialization_shard.yml"]]
  )
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2(
    "python", args = args, stdout = TRUE, stderr = TRUE,
    env = "CUDA_VISIBLE_DEVICES="
  )
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop("I17 smoke failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(result) || !identical(result$status, "READY")) {
    stop("I17 smoke returned invalid result:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  files <- normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
  required_outputs <- unlist(contract$config$output[c("result", "log")], use.names = FALSE)
  if (!setequal(basename(files), required_outputs)) stop("I17 returned incomplete outputs", call. = FALSE)
  files
}
