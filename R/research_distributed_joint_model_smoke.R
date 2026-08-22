# Dissertation Section 3.6: two-rank DDP numerical and state acceptance.

distributed_joint_model_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/distributed_training.yml", "config/joint_model.yml", "config/model_architecture.yml",
    "config/serialization_shard.yml", "config/schemas/prototype_distributed_joint_model_smoke.schema.json",
    "python/prototype_ddp_joint_model.py", "python/prototype_ddp_joint_objective_smoke.py",
    "python/prototype_ddp_optimizer_smoke.py", "python/prototype_joint_model.py",
    "python/prototype_sparse_reconstruction_smoke.py", "python/run_prototype_ddp_joint_smoke.py",
    "python/run_prototype_training_ddp.py",
    "R/research_distributed_joint_model_smoke.R"
  ))
}

run_prototype_distributed_joint_model_smoke <- function(
    prototype_training_dataset_acceptance, prototype_joint_model_smoke,
    distributed_joint_model_contract_files, workers = 1L, threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("Distributed joint smoke requires one orchestrator worker/thread", call. = FALSE)
  }
  files <- normalizePath(distributed_joint_model_contract_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  manifest <- joint_manifest_path(prototype_training_dataset_acceptance, "accepted_training_dataset_manifest.json")
  parent <- joint_manifest_path(prototype_joint_model_smoke, "prototype_joint_model_manifest.json")
  args <- c(by_name[["run_prototype_ddp_joint_smoke.py"]],
    "--accepted-manifest", manifest,
    "--tensor-contract", by_name[["serialization_shard.yml"]],
    "--encoder-config", by_name[["model_architecture.yml"]],
    "--joint-config", by_name[["joint_model.yml"]],
    "--distributed-config", by_name[["distributed_training.yml"]],
    "--parent-joint-manifest", parent,
    "--schema", by_name[["prototype_distributed_joint_model_smoke.schema.json"]])
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop("Distributed joint smoke failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(result) || !identical(result$status, "PASS")) stop("Distributed joint smoke returned invalid output", call. = FALSE)
  normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
}
