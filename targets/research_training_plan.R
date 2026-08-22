list_research_training_plan <- list(
  targets::tar_target(
    name = training_plan_contract_files,
    command = normalizePath(training_plan_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_training_plan,
    command = build_prototype_training_plan(
      prototype_training_dataset_acceptance = prototype_training_dataset_acceptance,
      prototype_encoder_smoke = prototype_encoder_smoke,
      prototype_augmentation_benchmark = prototype_augmentation_benchmark,
      training_plan_contract_files = training_plan_contract_files,
      workers = 1L, threads = 1L
    ),
    format = "rds", iteration = "list",
    resources = controller_05_resources
  )
)
