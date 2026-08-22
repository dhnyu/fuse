list_research_distributed_joint_model_smoke <- list(
  targets::tar_target(
    name = distributed_joint_model_contract_files,
    command = normalizePath(distributed_joint_model_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_distributed_joint_model_smoke,
    command = run_prototype_distributed_joint_model_smoke(
      prototype_training_dataset_acceptance, prototype_joint_model_smoke,
      distributed_joint_model_contract_files, workers = 1L, threads = 1L
    ),
    format = "file",
    resources = controller_gpu_02_resources
  )
)
