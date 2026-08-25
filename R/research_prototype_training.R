# Dissertation Section 3.6: I21 is the first optimizer-executing research stage.

prototype_training_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/prototype_training.yml", "config/joint_model.yml", "config/model_architecture.yml",
    "config/augmentation.yml", "config/serialization_shard.yml",
    "config/schemas/prototype_training_acceptance.schema.json",
    "python/prototype_encoder.py", "python/prototype_joint_model.py", "python/prototype_training_data.py",
    "python/prototype_ddp_joint_model.py", "python/run_prototype_training.py",
    "python/run_prototype_training_ddp.py", "python/run_prototype_training_ddp_locked.py",
    "python/recover_prototype_training_acceptance.py", "python/prototype_training_runtime.py",
    "python/prototype_validation.py",
    "python/validate_prototype_checkpoint.py", "python/prototype_augmentation.py",
    "python/run_prototype_augmentation_benchmark.py", "python/prototype_dataloader.py",
    "R/research_prototype_training.R"
  ))
}

prototype_completed_run_paths <- function(prototype_training_plan) {
  plan <- prototype_training_plan[[1L]]
  run_spec_path <- normalizePath(plan$.path, mustWork = TRUE)
  run_spec <- jsonlite::read_json(run_spec_path, simplifyVector = FALSE)
  run_root <- normalizePath(run_spec$output_root, mustWork = TRUE)
  checkpoint_root <- file.path(run_root, "mutable-ddp", "checkpoints")
  epochs <- list.files(checkpoint_root, pattern = "^epoch-[0-9]+\\.pt$", full.names = TRUE)
  checkpoints <- c(file.path(checkpoint_root, c("initial-step-000000.pt", "controlled-step-000001.pt")), epochs)
  ledgers <- file.path(run_root, "mutable-ddp", c("optimizer_steps.jsonl", "resource_telemetry.jsonl"))
  candidates <- list.files(file.path(run_root, "acceptance"), pattern = "^manifest-candidate\\.json$",
                           recursive = TRUE, all.files = TRUE, full.names = TRUE)
  candidates <- candidates[vapply(candidates, function(path) {
    value <- jsonlite::read_json(path, simplifyVector = FALSE)
    identical(value$plan_id, run_spec$plan_id) && identical(value$run_id, run_spec$run_id)
  }, logical(1L))]
  if (length(candidates) != 1L) stop("Expected exactly one matching failed-publication manifest", call. = FALSE)
  diagnostic <- file.path(dirname(candidates), "prototype_training_qc.json")
  normalizePath(c(checkpoints, ledgers, diagnostic), mustWork = TRUE)
}

prototype_training_plan_record <- function(value) {
  if (is.list(value) && !is.null(value$.path)) value else value[[1L]]
}

recover_prototype_training_target_metadata <- function(prototype_training_plan,
                                                       prototype_training_contract_files,
                                                       fallback,
                                                       workers = 1L, threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("I21 metadata recovery requires one CPU worker/thread", call. = FALSE)
  }
  recovered <- tryCatch({
    plan <- prototype_training_plan_record(prototype_training_plan)
    run_spec_path <- normalizePath(plan$.path, mustWork = TRUE)
    run_spec <- jsonlite::read_json(run_spec_path, simplifyVector = FALSE)
    files <- normalizePath(prototype_training_contract_files, mustWork = TRUE)
    by_name <- setNames(files, basename(files))
    acceptance_root <- file.path(run_spec$output_root, "acceptance")
    bundles <- list.dirs(acceptance_root, full.names = TRUE, recursive = FALSE)
    bundles <- bundles[grepl("^pta_[0-9a-f]{24}$", basename(bundles))]
    if (length(bundles) != 1L) {
      stop("I21 recovery requires exactly one accepted bundle for the current run", call. = FALSE)
    }
    bundle <- bundles[[1L]]
    accepted_manifest <- jsonlite::read_json(
      file.path(bundle, "prototype_training_acceptance_manifest.json"), simplifyVector = FALSE
    )
    current_runtime_sha256 <- sha256_file(by_name[["run_prototype_training_ddp.py"]])
    accepted_implementation_sha256 <- accepted_manifest$scientific_identity$training_implementation_sha256
    allowed_implementation_sha256 <- c(
      "9d36c4aa1bc46de1f14984aac6d374ddab156ce41a18d9983870f5dfeff6ea9c",
      current_runtime_sha256
    )
    if (!accepted_implementation_sha256 %in% allowed_implementation_sha256) {
      stop("I21 accepted bundle has an unapproved training implementation hash", call. = FALSE)
    }
    args <- c(
      by_name[["recover_prototype_training_acceptance.py"]],
      "--run-spec", run_spec_path,
      "--training-config", by_name[["prototype_training.yml"]],
      "--schema", by_name[["prototype_training_acceptance.schema.json"]],
      "--training-implementation", by_name[["run_prototype_training_ddp.py"]],
      "--recovery-implementation", by_name[["recover_prototype_training_acceptance.py"]],
      "--accepted-bundle", bundle,
      "--accepted-training-implementation-sha256", accepted_implementation_sha256,
      "--current-runtime-implementation-sha256", current_runtime_sha256
    )
    old <- capture_native_thread_state()
    on.exit(restore_native_thread_state(old), add = TRUE)
    set_native_thread_limits(threads)
    output <- suppressWarnings(system2("python", args = args, stdout = TRUE, stderr = TRUE))
    status <- attr(output, "status")
    if (!is.null(status) && status != 0L) {
      stop("I21 read-only metadata recovery audit failed:\n", paste(output, collapse = "\n"), call. = FALSE)
    }
    result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
    counters <- c(
      "formal_training_process_count", "cuda_operation_count", "optimizer_step_count",
      "dataloader_worker_spawn_count", "new_checkpoint_count", "ledger_append_count",
      "publication_count", "artifact_mutation_count"
    )
    if (is.null(result) || !identical(result$status, "PASS") ||
        !identical(result$mode, "existing_terminal_bundle_read_only") ||
        !identical(result$training_acceptance_id, basename(bundle)) ||
        any(vapply(result[counters], as.integer, integer(1L)) != 0L)) {
      stop("I21 read-only metadata recovery returned invalid zero-compute evidence", call. = FALSE)
    }
    message("Metadata fast path verified: prototype_training (zero compute)")
    normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
  }, error = function(error) {
    if (identical(Sys.getenv("FUSE_METADATA_RECOVERY_ONLY"), "1")) {
      stop("Metadata recovery-only fast path rejected for prototype_training: ", conditionMessage(error), call. = FALSE)
    }
    message("Metadata fast path rejected for prototype_training: ", conditionMessage(error), "; running target normally")
    NULL
  })
  if (!is.null(recovered)) return(recovered)
  fallback
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
