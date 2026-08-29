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
# Revised-dissertation P7 deterministic prototype training. Legacy helpers below
# remain available for regression tests but are not active P7 target ancestors.
p7_contract_names <- function() {
  c(
    "config/p7_deterministic_training.yml", "config/p6_model_dataloader.yml",
    "config/schemas/p7_deterministic_training_supplement.schema.json",
    "config/schemas/p7_training_authority.schema.json",
    "config/schemas/p7_gpu_gate.schema.json",
    "config/schemas/p7_checkpoint_manifest.schema.json",
    "config/schemas/p7_training_trace.schema.json",
    "config/schemas/p7_selector_result.schema.json",
    "config/schemas/p7_training_execution.schema.json",
    "config/schemas/p7_prototype_training_acceptance.schema.json",
    "python/p7_training.py", "scripts/p7_prototype_training.py"
  )
}

p7_contract_files <- function(root = ".") {
  paths <- normalizePath(file.path(root, p7_contract_names()), mustWork = TRUE)
  names(paths) <- p7_contract_names()
  paths
}

p7_contract_file <- function(files, name) {
  value <- files[endsWith(files, name)]
  if (length(value) != 1L) stop("P7 tracked contract lookup mismatch: ", name, call. = FALSE)
  value[[1L]]
}

p7_resolve_validation_query_reference <- function(p5_contract_files, p7_contract_files) {
  p5_path <- p5_contract_files[endsWith(p5_contract_files, "config/p5_deterministic_queries.yml")]
  if (length(p5_path) != 1L) stop("P7 cannot resolve the tracked P5 configuration", call. = FALSE)
  p5 <- yaml::read_yaml(p5_path[[1L]])
  p7 <- p7_config(p7_contract_files)
  authority_id <- p7$parents$p5_query_authority_id
  acceptance_id <- p7$parents$p5_acceptance_id
  root <- file.path(p5$publication_root, authority_id, "acceptance", acceptance_id)
  files <- file.path(root, c(
    "validation_acceptance.json", "validation_gallery.parquet",
    "validation_query_index.parquet", "validation_query_positive.parquet",
    "fixed_query_acceptance.json", "fixed_query_manifest.json"
  ))
  files <- normalizePath(files, mustWork = TRUE)
  split <- jsonlite::read_json(files[[1L]], simplifyVector = FALSE)
  aggregate <- jsonlite::read_json(files[[5L]], simplifyVector = FALSE)
  manifest <- jsonlite::read_json(files[[6L]], simplifyVector = FALSE)
  if (!identical(split$status, "PASS") || !identical(split$split, "validation") ||
      !identical(split$query_authority_id, authority_id) ||
      !identical(aggregate$status, "PASS") ||
      !identical(aggregate$query_authority_id, authority_id) ||
      !identical(aggregate$acceptance_id, acceptance_id) ||
      !identical(as.integer(split$scene_count), 400L) ||
      !identical(as.integer(split$query_count), 800L) ||
      !identical(as.integer(split$gallery_count), 400L)) {
    stop("P7 validation-only P5 reference failed accepted identity/population checks", call. = FALSE)
  }
  manifest_sha <- setNames(vapply(manifest$files, `[[`, character(1L), "sha256"),
                           vapply(manifest$files, `[[`, character(1L), "filename"))
  if (!all(vapply(files[1:5], function(path) {
    identical(unname(sha256_file(path)), unname(manifest_sha[[basename(path)]]))
  }, logical(1L)))) {
    stop("P7 validation-only P5 reference checksum mismatch", call. = FALSE)
  }
  files
}

p7_resolve_p6_parent_reference <- function(p7_contract_files) {
  p7 <- p7_config(p7_contract_files)
  p6 <- yaml::read_yaml(p7_contract_file(p7_contract_files, "config/p6_model_dataloader.yml"))
  ids <- p7$parents
  files <- file.path(p6$publication_root, c(
    file.path("architecture", ids$p6_model_authority_id, "architecture_manifest.json"),
    file.path("preprocessing", ids$p6_preprocessing_id, "preprocessing_contract.json"),
    file.path("dataloader", ids$p6_dataloader_acceptance_id, "dataloader_acceptance.json"),
    file.path("smoke", ids$p6_cpu_smoke_id, "cpu_functional_smoke.json"),
    file.path("acceptance", ids$p6_aggregate_acceptance_id, "model_data_acceptance.json")
  ))
  files <- normalizePath(files, mustWork = TRUE)
  values <- lapply(files, jsonlite::read_json, simplifyVector = FALSE)
  observed <- c(
    values[[1L]]$model_authority_id, values[[2L]]$preprocessing_id,
    values[[3L]]$dataloader_acceptance_id, values[[4L]]$smoke_id,
    values[[5L]]$model_data_acceptance_id
  )
  expected <- unlist(ids[c(
    "p6_model_authority_id", "p6_preprocessing_id", "p6_dataloader_acceptance_id",
    "p6_cpu_smoke_id", "p6_aggregate_acceptance_id"
  )], use.names = FALSE)
  if (!identical(observed, expected) || any(vapply(values, function(value) !identical(value$status, "PASS"), logical(1L)))) {
    stop("P7 read-only P6 parent reference failed active identity/status checks", call. = FALSE)
  }
  files
}

p7_resolve_immutable_parent_reference <- function(p7_contract_files) {
  config <- p7_config(p7_contract_files); ids <- config$parents
  scene_root <- config$parent_roots$scene_data
  files <- c(
    file.path(scene_root, "index", ids$p1_scene_index_id, "prototype", ids$prototype_selection_id,
              c("prototype_scene_selection.parquet", "prototype_scene_selection_manifest.json")),
    file.path(scene_root, "original_scene_cache", ids$p3_cache_id, "acceptance", ids$p3_acceptance_id,
              "original_scene_dataset_acceptance.json"),
    file.path(scene_root, "augmentation_banks", ids$p4_master_bank_id, "acceptance", ids$p4_acceptance_id,
              c("augmentation_bank_acceptance.json", "effective_bank_index.parquet", "effective_bank_index.json")),
    file.path(scene_root, "observations", ids$p2_observation_id, "production", "acceptance", ids$p2_acceptance_id,
              "spatial_categories.json"),
    file.path(config$parent_roots$methodology_authority, "_components", "modules", "training",
              ids$training_contract_id, "training_methodology_contract.json")
  )
  files <- normalizePath(files, mustWork = TRUE)
  prototype <- jsonlite::read_json(artifact_path(files, "prototype_scene_selection_manifest.json"), simplifyVector = FALSE)
  p3 <- jsonlite::read_json(artifact_path(files, "original_scene_dataset_acceptance.json"), simplifyVector = FALSE)
  p4 <- jsonlite::read_json(artifact_path(files, "augmentation_bank_acceptance.json"), simplifyVector = FALSE)
  training <- jsonlite::read_json(artifact_path(files, "training_methodology_contract.json"), simplifyVector = FALSE)
  if (!identical(prototype$status, "PASS") || !identical(prototype$prototype_id, ids$prototype_selection_id) ||
      !identical(p3$status, "PASS") || !identical(p3$cache_id, ids$p3_cache_id) ||
      !identical(p3$acceptance_id, ids$p3_acceptance_id) ||
      !identical(p4$status, "PASS") || !identical(p4$bank_id, ids$p4_master_bank_id) ||
      !identical(p4$acceptance_id, ids$p4_acceptance_id) ||
      !identical(training$status, "PASS") || !identical(training$contract_id, ids$training_contract_id)) {
    stop("P7 immutable P1/P3/P4/methodology parent identity mismatch", call. = FALSE)
  }
  files
}

p7_config <- function(files) {
  value <- yaml::read_yaml(p7_contract_file(files, "config/p7_deterministic_training.yml"))
  schema <- p7_contract_file(files, "config/schemas/p7_deterministic_training_supplement.schema.json")
  temporary <- tempfile(fileext = ".json"); on.exit(unlink(temporary), add = TRUE)
  write_json_file(value, temporary); validate_json_schema_file(temporary, schema)
  value
}

p7_python <- function(arguments, stream = FALSE) {
  executable <- research_python_executable()
  if (stream) {
    status <- system2(executable, arguments, stdout = "", stderr = "")
    if (!identical(status, 0L)) stop("P7 command failed with status ", status, call. = FALSE)
    return(invisible(character()))
  }
  output <- system2(executable, arguments, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status") %||% 0L
  if (status != 0L) stop("P7 command failed: ", paste(output, collapse = " | "), call. = FALSE)
  output
}

p7_common_arguments <- function(model_data_acceptance, d64_model_architecture_contract,
                                p6_preprocessing_contract, prototype_scene_selection,
                                original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                fixed_validation_query_acceptance, base_spatial_acceptance,
                                contract_files) {
  prototype <- artifact_path(prototype_scene_selection, "prototype_scene_selection.parquet")
  prototype_manifest <- artifact_path(prototype_scene_selection, "prototype_scene_selection_manifest.json")
  c(
    "--config", p7_contract_file(contract_files, "config/p7_deterministic_training.yml"),
    "--p6-config", p7_contract_file(contract_files, "config/p6_model_dataloader.yml"),
    "--architecture", artifact_path(d64_model_architecture_contract, "architecture_manifest.json"),
    "--preprocessing", artifact_path(p6_preprocessing_contract, "preprocessing_contract.json"),
    "--p6-acceptance", artifact_path(model_data_acceptance, "model_data_acceptance.json"),
    "--prototype", prototype, "--prototype-manifest", prototype_manifest,
    "--p3-root", p7_root_from_named_artifact(original_scene_dataset_acceptance,
                                               "original_scene_dataset_acceptance.json", 3L),
    "--p4-root", p7_root_from_named_artifact(augmentation_bank_acceptance,
                                               "augmentation_bank_acceptance.json", 3L),
    "--p5-root", p6_root_from_artifact(fixed_validation_query_acceptance, 3L),
    "--categories", artifact_path(base_spatial_acceptance, "spatial_categories.json")
  )
}

p7_root_from_named_artifact <- function(paths, filename, levels) {
  path <- artifact_path(paths, filename)
  for (index in seq_len(levels)) path <- dirname(path)
  path
}

p7_publish_single_json <- function(source, root, filename, schema, id_field) {
  value <- jsonlite::read_json(source, simplifyVector = FALSE)
  if (is.null(value[[id_field]])) stop("P7 output identity is missing", call. = FALSE)
  destination <- file.path(root, value[[id_field]])
  p1_publish_immutable_bundle(destination, filename, function(stage) {
    if (!file.copy(source, file.path(stage, filename))) stop("P7 artifact copy failed", call. = FALSE)
    validate_json_schema_file(file.path(stage, filename), schema)
  })
}

p7_build_authority <- function(model_data_acceptance, d64_model_architecture_contract,
                               p6_preprocessing_contract, prototype_scene_selection,
                               original_scene_dataset_acceptance, augmentation_bank_acceptance,
                               fixed_validation_query_acceptance, base_spatial_acceptance,
                               training_methodology_contract, contract_files) {
  training <- jsonlite::read_json(artifact_path(training_methodology_contract, "training_methodology_contract.json"), simplifyVector = FALSE)
  if (!identical(training$status, "PASS") || !identical(training$contract_id, "mmc_3b3719e274996c7d")) {
    stop("P7 accepted training methodology contract mismatch", call. = FALSE)
  }
  arguments <- c("scripts/p7_prototype_training.py", "authority",
                 p7_common_arguments(model_data_acceptance, d64_model_architecture_contract,
                                     p6_preprocessing_contract, prototype_scene_selection,
                                     original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                     fixed_validation_query_acceptance, base_spatial_acceptance, contract_files))
  output <- tempfile(fileext = ".json"); on.exit(unlink(output), add = TRUE)
  p7_python(c(arguments, "--output", output))
  cfg <- p7_config(contract_files)
  p7_publish_single_json(output, file.path(cfg$publication_root, "authority"), "training_authority.json",
                         p7_contract_file(contract_files, "config/schemas/p7_training_authority.schema.json"),
                         "training_authority_id")
}

p7_gpu_gate <- function(gate, authority, model_data_acceptance, d64_model_architecture_contract,
                        p6_preprocessing_contract, prototype_scene_selection,
                        original_scene_dataset_acceptance, augmentation_bank_acceptance,
                        fixed_validation_query_acceptance, base_spatial_acceptance, contract_files) {
  cfg <- p7_config(contract_files)
  arguments <- c("scripts/p7_prototype_training.py", "gpu-gate",
                 p7_common_arguments(model_data_acceptance, d64_model_architecture_contract,
                                     p6_preprocessing_contract, prototype_scene_selection,
                                     original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                     fixed_validation_query_acceptance, base_spatial_acceptance, contract_files),
                 "--authority", artifact_path(authority, "training_authority.json"),
                 "--gate", gate, "--output-root", cfg$publication_root,
                 "--staging-root", cfg$staging_root)
  p7_python(arguments, stream = TRUE)
  gate_name <- c(init = "ddp_initialization", update = "single_update", reference = "ddp_reference", resume = "resume_equivalence")[[gate]]
  authority_value <- jsonlite::read_json(artifact_path(authority, "training_authority.json"), simplifyVector = FALSE)
  paths <- list.files(file.path(cfg$publication_root, "diagnostics", authority_value$training_authority_id),
                      pattern = "gate[.]json$", recursive = TRUE, full.names = TRUE)
  matches <- paths[vapply(paths, function(path) identical(jsonlite::read_json(path, simplifyVector = FALSE)$gate, gate_name), logical(1L))]
  if (length(matches) != 1L) stop("P7 GPU gate artifact is missing or ambiguous: ", gate_name, call. = FALSE)
  validate_json_schema_file(matches, p7_contract_file(contract_files, "config/schemas/p7_gpu_gate.schema.json"))
  normalizePath(matches, mustWork = TRUE)
}

p7_run_production <- function(authority, resume_gate, model_data_acceptance,
                              d64_model_architecture_contract, p6_preprocessing_contract,
                              prototype_scene_selection, original_scene_dataset_acceptance,
                              augmentation_bank_acceptance, fixed_validation_query_acceptance,
                              base_spatial_acceptance, contract_files) {
  if (!identical(jsonlite::read_json(resume_gate, simplifyVector = FALSE)$status, "PASS")) stop("P7 resume gate did not pass", call. = FALSE)
  cfg <- p7_config(contract_files)
  arguments <- c("scripts/p7_prototype_training.py", "production",
                 p7_common_arguments(model_data_acceptance, d64_model_architecture_contract,
                                     p6_preprocessing_contract, prototype_scene_selection,
                                     original_scene_dataset_acceptance, augmentation_bank_acceptance,
                                     fixed_validation_query_acceptance, base_spatial_acceptance, contract_files),
                 "--authority", artifact_path(authority, "training_authority.json"),
                 "--output-root", cfg$publication_root, "--staging-root", cfg$staging_root)
  p7_python(arguments, stream = TRUE)
  value <- jsonlite::read_json(artifact_path(authority, "training_authority.json"), simplifyVector = FALSE)
  path <- file.path(cfg$publication_root, value$training_authority_id, value$run_id, "run_manifest.json")
  normalizePath(path, mustWork = TRUE)
}

p7_extract_run_artifact <- function(run_manifest, filename, schema, contract_files) {
  arguments <- c("scripts/p7_prototype_training.py", "extract", "--run-manifest", run_manifest,
                 "--filename", filename, "--schema", p7_contract_file(contract_files, schema))
  p7_python(arguments)
  normalizePath(file.path(dirname(run_manifest), filename), mustWork = TRUE)
}

p7_final_acceptance <- function(authority, run_manifest, trace, selector, execution, gates, contract_files) {
  cfg <- p7_config(contract_files); output <- tempfile(fileext = ".json"); on.exit(unlink(output), add = TRUE)
  schema <- p7_contract_file(contract_files, "config/schemas/p7_prototype_training_acceptance.schema.json")
  arguments <- c("scripts/p7_prototype_training.py", "aggregate", "--authority", artifact_path(authority, "training_authority.json"),
                 "--run-manifest", run_manifest, "--trace", trace, "--selector", selector, "--execution", execution,
                 "--gates", gates, "--schema", schema, "--output", output)
  p7_python(arguments)
  p7_publish_single_json(output, file.path(cfg$publication_root, "acceptance"),
                         "prototype_training_acceptance.json", schema, "acceptance_id")
}
