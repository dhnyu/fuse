list_research_full_membership_plan <- list(
  targets::tar_target(
    name = full_membership_authorization_contract,
    command = normalizePath(full_membership_authorization_contract_path(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = full_membership_i24_authorization,
    command = validate_full_membership_i24_authorization(full_membership_authorization_contract),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = full_membership_plan_contract_files,
    command = normalizePath(full_membership_plan_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = full_membership_plan,
    command = suppressWarnings(build_full_membership_plan(
      spatial_scene_index = spatial_scene_index,
      prototype_spatial_acceptance = prototype_spatial_acceptance,
      prototype_model_acceptance = full_membership_i24_authorization,
      prototype_membership_acceptance = prototype_membership_acceptance,
      prototype_observation_plan = prototype_observation_plan,
      full_membership_plan_contract_files = full_membership_plan_contract_files
    )),
    format = "file",
    resources = controller_05_resources
  )
)
