# Dissertation Appendix B: deterministic spatial-scene augmentation reference.

augmentation_benchmark_contract_paths <- function(
    root = getwd(), thesis_root = path.expand("~/dhnyu-masters-dissertation/template")) {
  c(
    file.path(root, c(
      "config/augmentation.yml",
      "config/schemas/prototype_augmentation_benchmark.schema.json",
      "config/schemas/prototype_scientific_geometry_roundtrip.schema.json",
      "config/serialization_shard.yml",
      "python/prototype_augmentation.py",
      "python/run_scientific_geometry_roundtrip.py",
      "python/run_prototype_augmentation_benchmark.py",
      "python/prototype_dataloader.py",
      "python/requirements-augmentation.txt",
      "R/research_augmentation_benchmark.R"
    )),
    file.path(thesis_root, c(
      "sections/appendices/appendix-b.typ",
      "sections/chapters/methodology/06-model-training.typ",
      "materials/tables/results-04-training-configuration-table.typ",
      "sections/chapters/results/05-hyperparameter-study.typ"
    ))
  )
}

run_scientific_geometry_roundtrip <- function(
    prototype_training_dataset_acceptance,
    prototype_dataloader_smoke,
    augmentation_benchmark_contract_files,
    workers = 1L,
    threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("Scientific geometry gate requires exactly one worker and thread", call. = FALSE)
  }
  contract <- load_augmentation_benchmark_config(augmentation_benchmark_contract_files)
  accepted <- normalizePath(unlist(prototype_training_dataset_acceptance, use.names = FALSE), mustWork = TRUE)
  loader <- normalizePath(unlist(prototype_dataloader_smoke, use.names = FALSE), mustWork = TRUE)
  accepted_manifest <- accepted[basename(accepted) == "accepted_training_dataset_manifest.json"]
  loader_result <- loader[basename(loader) == "prototype_dataloader_smoke.json"]
  if (length(accepted_manifest) != 1L || length(loader_result) != 1L) {
    stop("Scientific geometry gate upstream manifest is missing", call. = FALSE)
  }
  output_root <- file.path(dirname(accepted_manifest), "roundtrip", "scientific-geometry")
  dir.create(dirname(output_root), recursive = TRUE, showWarnings = FALSE)
  args <- c(
    contract$paths[["run_scientific_geometry_roundtrip.py"]],
    "--accepted-manifest", accepted_manifest,
    "--dataloader-result", loader_result,
    "--tensor-contract", contract$paths[["serialization_shard.yml"]],
    "--schema", contract$paths[["prototype_scientific_geometry_roundtrip.schema.json"]],
    "--implementation", contract$paths[["prototype_augmentation.py"]],
    "--requirements", contract$paths[["requirements-augmentation.txt"]],
    "--output-root", output_root
  )
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) {
    stop("Scientific geometry no-op gate failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  files <- normalizePath(output[file.exists(output)], mustWork = TRUE)
  manifest <- files[basename(files) == "scientific_geometry_roundtrip_manifest.json"]
  if (length(manifest) != 1L || !identical(jsonlite::read_json(manifest)$status, "PASS")) {
    stop("Scientific geometry no-op gate returned invalid output", call. = FALSE)
  }
  files
}

load_augmentation_benchmark_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  config <- yaml::read_yaml(by_name[["augmentation.yml"]])
  expected <- list(
    version = c(config$augmentation_contract_version, "1.0.0"),
    dissertation = c(config$dissertation_commit, "87990db83f2b30200cc2d64dc160cb41f691e0e7"),
    continuous = c(config$attributes$geometry_independent_continuous$status, "disabled_no_eligible_fields"),
    gaussian = c(config$attributes$geometry_independent_continuous$gaussian_perturbation, "forbidden"),
    lane_probability = c(config$attributes$road_lanes$probability, 0.10),
    lane_draws = c(config$attributes$road_lanes$draws_per_selected_lane, 1),
    lane_action = c(config$attributes$road_lanes$lower_bound_action, "clamp_without_resampling"),
    boundary = c(config$geometry$scene_boundary_tolerance_m, 1e-8),
    attempts = c(config$geometry$maximum_attempts, 10),
    cuda = c(config$benchmark$require_cuda, TRUE)
  )
  bad <- names(expected)[vapply(expected, function(value) {
    !identical(as.character(value[[1L]]), as.character(value[[2L]]))
  }, logical(1L))]
  if (length(config$attributes$geometry_independent_continuous$eligible_fields) || length(bad)) {
    stop("I19 augmentation contract mismatch: ", paste(c(bad, "eligible_fields"[length(config$attributes$geometry_independent_continuous$eligible_fields) > 0L]), collapse = ", "), call. = FALSE)
  }
  if (!identical(as.integer(unlist(config$attributes$road_lanes$offset_support)), c(-1L, 1L)) ||
      !identical(as.numeric(unlist(config$attributes$road_lanes$offset_probabilities)), c(0.5, 0.5))) {
    stop("I19 lane offset distribution changed", call. = FALSE)
  }
  list(config = config, paths = by_name)
}

run_prototype_augmentation_benchmark <- function(
    prototype_training_dataset_acceptance,
    prototype_dataloader_smoke,
    prototype_scientific_geometry_roundtrip,
    augmentation_benchmark_contract_files,
    workers = 1L,
    threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("I19 target orchestration requires exactly one worker and thread", call. = FALSE)
  }
  contract <- load_augmentation_benchmark_config(augmentation_benchmark_contract_files)
  gate_files <- normalizePath(unlist(prototype_scientific_geometry_roundtrip, use.names = FALSE), mustWork = TRUE)
  gate_manifest <- gate_files[basename(gate_files) == "scientific_geometry_roundtrip_manifest.json"]
  if (length(gate_manifest) != 1L || !identical(jsonlite::read_json(gate_manifest)$status, "PASS")) {
    stop("I19 requires a PASS scientific geometry no-op gate", call. = FALSE)
  }
  accepted <- normalizePath(unlist(prototype_training_dataset_acceptance, use.names = FALSE), mustWork = TRUE)
  loader <- normalizePath(unlist(prototype_dataloader_smoke, use.names = FALSE), mustWork = TRUE)
  accepted_manifest <- accepted[basename(accepted) == "accepted_training_dataset_manifest.json"]
  loader_result <- loader[basename(loader) == "prototype_dataloader_smoke.json"]
  if (length(accepted_manifest) != 1L || length(loader_result) != 1L) {
    stop("I19 upstream manifest is missing", call. = FALSE)
  }
  output_root <- file.path(dirname(accepted_manifest), contract$config$output$subdirectory)
  dir.create(dirname(output_root), recursive = TRUE, showWarnings = FALSE)
  args <- c(
    contract$paths[["run_prototype_augmentation_benchmark.py"]],
    "--accepted-manifest", accepted_manifest,
    "--dataloader-result", loader_result,
    "--tensor-contract", contract$paths[["serialization_shard.yml"]],
    "--config", contract$paths[["augmentation.yml"]],
    "--schema", contract$paths[["prototype_augmentation_benchmark.schema.json"]],
    "--implementation", contract$paths[["prototype_augmentation.py"]],
    "--requirements", contract$paths[["requirements-augmentation.txt"]],
    "--output-root", output_root
  )
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) {
    stop("I19 augmentation benchmark failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(result) || !identical(result$status, "PASS")) {
    stop("I19 returned invalid result:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  files <- normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
  required <- unlist(contract$config$output[c("manifest", "scene_results", "qc", "report", "log")], use.names = FALSE)
  if (!setequal(basename(files), required)) stop("I19 returned incomplete outputs", call. = FALSE)
  files
}
