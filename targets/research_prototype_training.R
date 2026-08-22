list_research_prototype_training <- list(
  targets::tar_target(
    name = prototype_training_contract_files,
    command = normalizePath(prototype_training_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_training_completed_artifacts,
    command = prototype_completed_run_paths(prototype_training_plan),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_training_acceptance,
    command = recover_prototype_training_acceptance(
      prototype_training_plan, prototype_training_completed_artifacts,
      prototype_training_contract_files, workers = 1L, threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  )
)
