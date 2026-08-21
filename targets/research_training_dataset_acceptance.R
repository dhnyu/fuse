list_research_training_dataset_acceptance <- list(
  targets::tar_target(
    name = training_dataset_acceptance_contract_files,
    command = normalizePath(training_dataset_acceptance_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_training_dataset_acceptance,
    command = run_prototype_training_dataset_acceptance(
      prototype_spatial_acceptance = prototype_spatial_acceptance,
      prototype_serialization_plan = prototype_serialization_plan,
      prototype_serialization_shard = prototype_serialization_shard,
      training_dataset_acceptance_contract_files = training_dataset_acceptance_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  )
)
