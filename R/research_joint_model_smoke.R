# Dissertation Sections 3.6 and Appendix C: joint contrastive/reconstruction gate.

joint_model_smoke_contract_paths <- function(
    root = getwd(), thesis_root = path.expand("~/dhnyu-masters-dissertation/template")) {
  c(file.path(root, c(
    "config/joint_model.yml", "config/model_architecture.yml", "config/serialization_shard.yml",
    "config/schemas/prototype_joint_model_smoke.schema.json",
    "python/prototype_encoder.py", "python/prototype_joint_model.py",
    "python/prototype_joint_model_smoke_impl.py", "python/run_prototype_joint_model_smoke.py",
    "python/prototype_dataloader.py", "python/run_prototype_encoder_smoke.py",
    "python/requirements-encoder.txt", "R/research_joint_model_smoke.R"
  )), file.path(thesis_root, c(
    "sections/chapters/methodology/02-object-modal-embeddings.typ",
    "sections/chapters/methodology/03-object-modality-fusion.typ",
    "sections/chapters/methodology/06-model-training.typ",
    "sections/appendices/appendix-c.typ",
    "materials/tables/results-04-training-configuration-table.typ",
    "materials/tables/results-05-model-architecture-table.typ"
  )))
}

joint_manifest_path <- function(paths, name) {
  values <- normalizePath(unlist(paths, use.names = FALSE), mustWork = TRUE)
  selected <- values[basename(values) == name]
  if (length(selected) != 1L) stop("Joint smoke upstream missing: ", name, call. = FALSE)
  selected
}

run_prototype_joint_model_smoke <- function(
    prototype_training_dataset_acceptance, prototype_dataloader_smoke,
    prototype_scientific_geometry_roundtrip, prototype_encoder_smoke,
    prototype_augmentation_benchmark, joint_model_smoke_contract_files,
    workers = 1L, threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) {
    stop("Joint-model smoke target requires one orchestrator worker/thread", call. = FALSE)
  }
  paths <- normalizePath(joint_model_smoke_contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  config <- yaml::read_yaml(by_name[["joint_model.yml"]])
  expected <- list(dataset = "ptd_8b3359690ea2d0bef52d63e3", loader = "pdl_361072e3519a91d0aefc9bb9",
                   encoder = "pea_bb192d9b73c6189d36c452fa", augmentation = "paa_f561eea03b05c47375b7198e",
                   gate = "pgr_60bc6b2cbd0864272308d18e")
  observed <- list(dataset = config$identity$accepted_dataset_id, loader = config$identity$dataloader_smoke_id,
                   encoder = config$identity$encoder_acceptance_id, augmentation = config$identity$augmentation_acceptance_id,
                   gate = config$identity$no_op_gate_id)
  if (!identical(observed, expected)) stop("Joint-model scoped identity contract mismatch", call. = FALSE)
  args <- c(by_name[["run_prototype_joint_model_smoke.py"]],
    "--accepted-manifest", joint_manifest_path(prototype_training_dataset_acceptance, "accepted_training_dataset_manifest.json"),
    "--dataloader-smoke", joint_manifest_path(prototype_dataloader_smoke, "prototype_dataloader_smoke.json"),
    "--encoder-manifest", joint_manifest_path(prototype_encoder_smoke, "prototype_encoder_manifest.json"),
    "--augmentation-manifest", joint_manifest_path(prototype_augmentation_benchmark, "prototype_augmentation_manifest.json"),
    "--gate-manifest", joint_manifest_path(prototype_scientific_geometry_roundtrip, "scientific_geometry_roundtrip_manifest.json"),
    "--joint-config", by_name[["joint_model.yml"]], "--encoder-config", by_name[["model_architecture.yml"]],
    "--tensor-contract", by_name[["serialization_shard.yml"]],
    "--schema", by_name[["prototype_joint_model_smoke.schema.json"]])
  old <- capture_native_thread_state()
  on.exit(restore_native_thread_state(old), add = TRUE)
  set_native_thread_limits(threads)
  output <- system2("python", args = args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop("Joint-model smoke failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  result <- tryCatch(jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE), error = function(error) NULL)
  if (is.null(result) || !identical(result$status, "PASS")) stop("Joint-model smoke returned invalid output", call. = FALSE)
  normalizePath(unlist(result$output_files, use.names = FALSE), mustWork = TRUE)
}
