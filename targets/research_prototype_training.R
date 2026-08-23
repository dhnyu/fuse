list_research_prototype_training <- list(
  targets::tar_target(
    name = prototype_training_contract_files,
    command = normalizePath(prototype_training_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_training,
    command = run_prototype_training(
      prototype_training_plan, prototype_training_contract_files,
      workers = 40L, threads = 1L
    ),
    format = "file",
    pattern = map(prototype_training_plan),
    resources = controller_gpu_02_resources
  ),
  targets::tar_target(
    name = prototype_training_acceptance,
    command = validate_prototype_training_outputs(
      prototype_training_plan, prototype_training,
      prototype_training_contract_files, workers = 1L, threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  )
)
