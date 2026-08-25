list_research_augmentation_benchmark <- list(
  targets::tar_target(
    name = augmentation_benchmark_contract_files,
    command = normalizePath(augmentation_benchmark_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_scientific_geometry_roundtrip,
    command = recover_file_target_metadata(
      "prototype_scientific_geometry_roundtrip",
      file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance),
                "roundtrip", "scientific-geometry", "pgr_77294c825bf26bf6fce721c3"),
      run_scientific_geometry_roundtrip(
        prototype_training_dataset_acceptance = prototype_training_dataset_acceptance,
        prototype_dataloader_smoke = prototype_dataloader_smoke,
        augmentation_benchmark_contract_files = augmentation_benchmark_contract_files,
        workers = 1L,
        threads = 1L
      )
    ),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_augmentation_benchmark,
    command = recover_file_target_metadata(
      "prototype_augmentation_benchmark",
      file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance),
                "benchmark", "augmentation", "paa_5d2b1f56119e8d5f5050a75d"),
      run_prototype_augmentation_benchmark(
        prototype_training_dataset_acceptance = prototype_training_dataset_acceptance,
        prototype_dataloader_smoke = prototype_dataloader_smoke,
        prototype_scientific_geometry_roundtrip = prototype_scientific_geometry_roundtrip,
        augmentation_benchmark_contract_files = augmentation_benchmark_contract_files,
        workers = 1L,
        threads = 1L
      )
    ),
    format = "file",
    resources = controller_05_resources
  )
)
