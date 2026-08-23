list_research_prototype_model_acceptance <- list(
  targets::tar_target(
    name = prototype_model_acceptance_contract_files,
    command = normalizePath(prototype_model_acceptance_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_model_acceptance,
    command = recover_file_target_metadata(
      "prototype_model_acceptance",
      file.path(dirname(dirname(dirname(dirname(
        prototype_dataloader_smoke[basename(prototype_dataloader_smoke) == "prototype_dataloader_smoke.json"]
      )))), "acceptance", "prototype-model", "pma_6282c9e9f9ebb9348484223a"),
      run_prototype_model_acceptance(
        prototype_dataloader_smoke = prototype_dataloader_smoke,
        prototype_encoder_smoke = prototype_encoder_smoke,
        prototype_augmentation_benchmark = prototype_augmentation_benchmark,
        prototype_training_acceptance = prototype_training_acceptance,
        prototype_model_validation = prototype_model_validation,
        prototype_model_acceptance_contract_files = prototype_model_acceptance_contract_files
      )
    ),
    format = "file",
    resources = controller_05_resources
  )
)
