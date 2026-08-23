# Dissertation Section 3.6: I21 is the first optimizer-executing research stage.

prototype_training_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/prototype_training.yml", "config/joint_model.yml", "config/model_architecture.yml",
    "config/augmentation.yml", "config/serialization_shard.yml",
    "config/schemas/prototype_training_acceptance.schema.json",
    "python/prototype_encoder.py", "python/prototype_joint_model.py", "python/prototype_training_data.py",
    "python/prototype_ddp_joint_model.py", "python/run_prototype_training.py",
    "python/run_prototype_training_ddp.py", "python/run_prototype_training_ddp_locked.py",
    "python/recover_prototype_training_acceptance.py",
    "python/validate_prototype_checkpoint.py", "python/prototype_augmentation.py",
    "python/run_prototype_augmentation_benchmark.py", "python/prototype_dataloader.py",
    "R/research_prototype_training.R"
  ))
}

prototype_completed_run_paths <- function(prototype_training_plan) {
  plan <- prototype_training_plan[[1L]]
  run_spec_path <- normalizePath(plan$.path, mustWork = TRUE)
  run_spec <- jsonlite::read_json(run_spec_path, simplifyVector = FALSE)
  if (!identical(run_spec$plan_id, "ptp_3b100622bdb733351db6e458") ||
      !identical(run_spec$run_id, "ptr_473911a4828ae5540a9d4eb9")) {
    stop("Completed I21 evidence does not belong to the current I20 run", call. = FALSE)
  }
  run_root <- normalizePath(run_spec$output_root, mustWork = TRUE)
  checkpoints <- file.path(run_root, "mutable-ddp", "checkpoints", c(
    "initial-step-000000.pt", "controlled-step-000001.pt",
    sprintf("epoch-%03d.pt", seq.int(5L, 55L, by = 5L))
  ))
  ledgers <- file.path(run_root, "mutable-ddp", c("optimizer_steps.jsonl", "resource_telemetry.jsonl"))
  diagnostic <- list.files(file.path(run_root, "acceptance"), pattern = "^prototype_training_qc\\.json$",
                           recursive = TRUE, all.files = TRUE, full.names = TRUE)
  diagnostic <- diagnostic[grepl("/\\.pta_[0-9a-f]{24}\\.stage-[^/]+/prototype_training_qc\\.json$", diagnostic)]
  if (length(diagnostic) != 1L) stop("Expected exactly one failed-publication I21 QC artifact", call. = FALSE)
  normalizePath(c(checkpoints, ledgers, diagnostic), mustWork = TRUE)
}

recover_prototype_training_acceptance <- function(prototype_training_plan,
                                                   prototype_training_completed_artifacts,
                                                   prototype_training_contract_files,
                                                   workers = 1L, threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("I21 publication recovery requires one CPU worker/thread", call. = FALSE)
  }
  plan <- prototype_training_plan[[1L]]
  run_spec_path <- normalizePath(plan$.path, mustWork = TRUE)
  files <- normalizePath(prototype_training_contract_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  artifacts <- normalizePath(prototype_training_completed_artifacts, mustWork = TRUE)
  args <- c(by_name[["recover_prototype_training_acceptance.py"]],
            "--run-spec", run_spec_path,
            "--training-config", by_name[["prototype_training.yml"]],
            "--schema", by_name[["prototype_training_acceptance.schema.json"]],
            "--training-implementation", by_name[["run_prototype_training_ddp.py"]],
            "--recovery-implementation", by_name[["recover_prototype_training_acceptance.py"]],
            unlist(lapply(artifacts, function(path) c("--completed-artifact", path)), use.names = FALSE))
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop("I21 publication recovery failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(result) || !identical(result$status, "PASS") || !identical(result$additional_optimizer_steps, 0L)) {
    stop("I21 publication recovery returned invalid output", call. = FALSE)
  }
  normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
}

run_prototype_training <- function(prototype_training_plan, prototype_training_contract_files,
                                   workers = 40L, threads = 1L) {
  if (!identical(as.integer(workers), 40L) || !identical(as.integer(threads), 1L)) {
    stop("I21 requires the accepted 40-process/one-native-thread execution", call. = FALSE)
  }
  plan <- if (!is.null(prototype_training_plan$.path)) prototype_training_plan else prototype_training_plan[[1L]]
  run_spec_path <- normalizePath(plan$.path, mustWork = TRUE)
  run_spec <- jsonlite::read_json(run_spec_path, simplifyVector = FALSE)
  files <- normalizePath(prototype_training_contract_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  training_config <- yaml::read_yaml(by_name[["prototype_training.yml"]])
  if (!identical(run_spec$plan_id, training_config$identity$plan_id) ||
      !identical(run_spec$run_id, training_config$identity$run_id) ||
      !identical(run_spec$joint_model_manifest$path |> basename(), "prototype_joint_model_manifest.json") ||
      !identical(run_spec$distributed_joint_model_manifest$path |> basename(), "distributed_joint_model_manifest.json")) {
    stop("I21 received an unapproved I20 plan/run", call. = FALSE)
  }
  args <- c(by_name[["run_prototype_training_ddp_locked.py"]],
            "--run-spec", run_spec_path,
            "--training-config", by_name[["prototype_training.yml"]],
            "--joint-config", by_name[["joint_model.yml"]],
            "--encoder-config", by_name[["model_architecture.yml"]],
            "--augmentation-config", by_name[["augmentation.yml"]],
            "--tensor-contract", by_name[["serialization_shard.yml"]],
            "--i19-manifest", run_spec$augmentation_manifest$path,
            "--schema", by_name[["prototype_training_acceptance.schema.json"]])
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop("I21 training failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(result) || !identical(result$status, "PASS")) stop("I21 returned invalid acceptance output", call. = FALSE)
  normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
}

validate_prototype_training_outputs <- function(prototype_training_plan, prototype_training,
                                                prototype_training_contract_files,
                                                workers = 1L, threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("I22 validation requires one CPU worker/thread", call. = FALSE)
  }
  plan <- prototype_training_plan[[1L]]
  run_spec <- jsonlite::read_json(normalizePath(plan$.path, mustWork = TRUE), simplifyVector = FALSE)
  files <- normalizePath(unlist(prototype_training, use.names = FALSE), mustWork = TRUE)
  manifest_path <- files[basename(files) == "prototype_training_acceptance_manifest.json"]
  if (length(manifest_path) != 1L) stop("I22 training manifest is not unique", call. = FALSE)
  manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  if (!identical(manifest$status, "PASS") ||
      !identical(manifest$plan_id, run_spec$plan_id) ||
      !identical(manifest$run_id, run_spec$run_id) ||
      !identical(manifest$resources$optimizer_step_performed, TRUE) ||
      !identical(manifest$resources$worker_count, 40L) ||
      as.integer(manifest$completion$optimizer_steps) < 1L) {
    stop("I22 training output contract failed", call. = FALSE)
  }
  normalizePath(files, mustWork = TRUE)
}
