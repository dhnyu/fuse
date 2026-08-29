list_research_p7_cold_path_runtime <- list(
  targets::tar_target(
    p7_cold_path_runtime_contract_files,
    p7_cold_path_contract_files(),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p7_cold_path_runtime_contract,
    p7_cold_path_build_contract(
      model_data_acceptance, prototype_training_acceptance,
      p7_geometry_feature_cache, p7_cold_path_runtime_contract_files
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p7_cold_path_runtime_verification_reference,
    p7_cold_path_verification_reference(p7_cold_path_runtime_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p7_cold_path_runtime_acceptance,
    p7_cold_path_build_acceptance(
      p7_cold_path_runtime_contract, p7_cold_path_runtime_verification_reference,
      model_data_acceptance, prototype_training_acceptance,
      p7_geometry_feature_cache, p7_cold_path_runtime_contract_files
    ),
    format = "file", resources = controller_05_resources
  )
)
