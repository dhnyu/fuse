list_research_p7_cold_path_runtime <- list(
  targets::tar_target(s07_runtime_sources, p7_cold_path_contract_files(),
    format = "file", resources = controller_05_resources),
  targets::tar_target(i07_runtime_validation_sources,
    p7_cold_path_verification_reference(s07_runtime_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s07_runtime_acceptance,
    p7_cold_path_consolidated_acceptance(s06_dataset_acceptance, s07_pilot_training_acceptance,
      s07_training_geometry_cache, i07_runtime_validation_sources, s07_runtime_sources),
    format = "file", resources = controller_05_resources)
)
