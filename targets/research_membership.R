list_research_membership <- list(
  targets::tar_target(
    name = membership_contract_files,
    command = normalizePath(membership_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_membership_plan,
    command = build_prototype_membership_plan(
      prototype_scene_selection = prototype_scene_selection,
      study_data_inventory = study_data_inventory,
      membership_contract_files = membership_contract_files,
      research_config_files = research_config_files,
      workers = 1L,
      threads = 1L
    ),
    format = "rds",
    iteration = "list",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_membership_shard,
    command = build_prototype_membership_shard(
      prototype_membership_plan = prototype_membership_plan,
      study_data_inputs = study_data_inputs,
      prototype_runtime_inputs = prototype_runtime_inputs,
      membership_contract_files = membership_contract_files,
      workers = 1L,
      threads = 1L
    ),
    pattern = map(prototype_membership_plan),
    iteration = "list",
    format = "file",
    resources = controller_40_resources
  ),
  targets::tar_target(
    name = prototype_membership_acceptance,
    command = build_prototype_membership_acceptance(
      prototype_membership_plan = prototype_membership_plan,
      prototype_membership_shard = prototype_membership_shard,
      prototype_scene_selection = prototype_scene_selection,
      study_data_inventory = study_data_inventory,
      membership_contract_files = membership_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  )
)
