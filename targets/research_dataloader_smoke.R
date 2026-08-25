list_research_dataloader_smoke <- list(
  targets::tar_target(
    name = dataloader_smoke_contract_files,
    command = normalizePath(dataloader_smoke_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_dataloader_smoke,
    command = recover_file_target_metadata(
      "prototype_dataloader_smoke",
      file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance),
                "smoke", "dataloader", "pdl_5eb0ccb9951d1015d6d64649"),
      run_prototype_dataloader_smoke(
        prototype_training_dataset_acceptance = prototype_training_dataset_acceptance,
        dataloader_smoke_contract_files = dataloader_smoke_contract_files,
        workers = 1L,
        threads = 1L
      )
    ),
    format = "file",
    resources = controller_05_resources
  )
)
