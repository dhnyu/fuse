controller_gpu_02_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_gpu_02")
)

list_research_encoder_smoke <- list(
  targets::tar_target(
    name = encoder_smoke_contract_files,
    command = normalizePath(encoder_smoke_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_encoder_smoke,
    command = run_prototype_encoder_smoke(
      prototype_training_dataset_acceptance = prototype_training_dataset_acceptance,
      prototype_dataloader_smoke = prototype_dataloader_smoke,
      encoder_smoke_contract_files = encoder_smoke_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_gpu_02_resources
  )
)
