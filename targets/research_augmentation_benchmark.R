list_research_augmentation_benchmark <- list(
  targets::tar_target(
    name = augmentation_benchmark_contract_files,
    command = normalizePath(augmentation_benchmark_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_scientific_geometry_roundtrip,
    command = run_scientific_geometry_roundtrip(
      prototype_training_dataset_acceptance = prototype_training_dataset_acceptance,
      prototype_dataloader_smoke = prototype_dataloader_smoke,
      augmentation_benchmark_contract_files = augmentation_benchmark_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_augmentation_benchmark,
    command = run_prototype_augmentation_benchmark(
      prototype_training_dataset_acceptance = prototype_training_dataset_acceptance,
      prototype_dataloader_smoke = prototype_dataloader_smoke,
      prototype_scientific_geometry_roundtrip = prototype_scientific_geometry_roundtrip,
      augmentation_benchmark_contract_files = augmentation_benchmark_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  )
)
