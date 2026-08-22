# Dissertation methodology Section 3: I16 accepts the fixed prototype tensor
# cache as one indexed training dataset without rewriting any I15 payload.

training_dataset_acceptance_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/training_dataset_acceptance.yml",
    "config/schemas/prototype_training_dataset_acceptance.schema.json",
    "config/serialization_shard.yml",
    "config/schemas/prototype_serialization_shard.schema.json",
    "python/accept_prototype_training_dataset.py",
    "python/validate_prototype_serialization_shards.py",
    "python/requirements-serialization.txt",
    "R/research_training_dataset_acceptance.R"
  ))
}

load_training_dataset_acceptance_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c(
    "training_dataset_acceptance.yml",
    "prototype_training_dataset_acceptance.schema.json",
    "serialization_shard.yml", "prototype_serialization_shard.schema.json",
    "accept_prototype_training_dataset.py", "validate_prototype_serialization_shards.py",
    "requirements-serialization.txt", "research_training_dataset_acceptance.R"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing I16 contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  config <- yaml::read_yaml(by_name[["training_dataset_acceptance.yml"]])
  expected <- list(
    spatial = c(config$identity$spatial_dataset_id, "psa_c2155cf081312a31edfdb191"),
    plan = c(config$identity$serialization_plan_id, "psp_72c5e4e5c3e4c84eb47aad85"),
    serialization = c(config$identity$serialization_dataset_id, "psd_72c5e4e5c3e4c84eb47aad85"),
    controller = c(config$execution$controller, "controller_05"),
    workers = c(config$execution$workers, 1), threads = c(config$execution$threads_per_worker, 1),
    gpu = c(config$execution$gpu, 0), branches = c(config$expected$branch_count, 51),
    scenes = c(config$expected$scene_count, 320)
  )
  bad <- names(expected)[vapply(expected, function(x) !identical(as.character(x[[1L]]), as.character(x[[2L]])), logical(1L))]
  if (length(bad)) stop("I16 contract mismatch: ", paste(bad, collapse = ", "), call. = FALSE)
  list(config = config, paths = by_name)
}

run_prototype_training_dataset_acceptance <- function(
    prototype_spatial_acceptance,
    prototype_serialization_plan,
    prototype_serialization_shard,
    training_dataset_acceptance_contract_files,
    workers = 1L,
    threads = 1L,
    output_directory = NULL,
    reverse_inputs = FALSE) {
  contract <- load_training_dataset_acceptance_config(training_dataset_acceptance_contract_files)
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("I16 execution requires exactly 1 worker and 1 thread", call. = FALSE)
  }
  spec_paths <- vapply(prototype_serialization_plan, function(x) x$.path, character(1L))
  branch_files <- unname(unlist(prototype_serialization_shard, use.names = FALSE))
  i13_files <- unname(unlist(prototype_spatial_acceptance, use.names = FALSE))
  if (isTRUE(reverse_inputs)) {
    spec_paths <- rev(spec_paths)
    branch_files <- rev(branch_files)
    i13_files <- rev(i13_files)
  }
  invocation <- tempfile("prototype-training-dataset-acceptance-", fileext = ".json")
  on.exit(unlink(invocation), add = TRUE)
  writeLines(jsonlite::toJSON(list(
    spec_paths = normalizePath(spec_paths, mustWork = TRUE),
    branch_files = normalizePath(branch_files, mustWork = TRUE),
    i13_files = normalizePath(i13_files, mustWork = TRUE)
  ), auto_unbox = TRUE, null = "null", digits = NA), invocation, useBytes = TRUE)
  args <- c(
    contract$paths[["accept_prototype_training_dataset.py"]],
    "--invocation", invocation,
    "--config", contract$paths[["training_dataset_acceptance.yml"]],
    "--schema", contract$paths[["prototype_training_dataset_acceptance.schema.json"]],
    "--i15-config", contract$paths[["serialization_shard.yml"]]
  )
  if (!is.null(output_directory)) args <- c(args, "--output-dir", output_directory)
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop("I16 acceptance failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(result) || !identical(result$status, "READY")) {
    stop("I16 acceptance returned invalid result:\n", paste(output, collapse = "\n"), call. = FALSE)
  }
  files <- normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
  required <- unlist(contract$config$output[c(
    "manifest", "shard_catalog", "global_scene_index", "dataset_index", "qc", "diagnostics", "log"
  )], use.names = FALSE)
  if (!setequal(basename(files), required)) stop("I16 returned incomplete output set", call. = FALSE)
  files
}
