list_research_prototype_model_validation <- list(
  targets::tar_target(
    name = prototype_model_validation_contract_files,
    command = normalizePath(prototype_model_validation_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_model_validation,
    command = recover_file_target_metadata(
      "prototype_model_validation",
      file.path(metadata_recovery_dataset_root(prototype_training_dataset_acceptance),
                "validation", "prototype-model", "pmv_1d5412a7b035635a4187fbf6"),
      run_prototype_model_validation(
        prototype_training_acceptance = prototype_training_acceptance,
        prototype_training_dataset_acceptance = prototype_training_dataset_acceptance,
        prototype_scene_selection = prototype_scene_selection,
        prototype_model_validation_contract_files = prototype_model_validation_contract_files,
        workers = 40L,
        threads = 1L
      )
    ),
    format = "file",
    resources = controller_gpu_02_resources
  )
)
