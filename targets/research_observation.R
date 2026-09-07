list_research_observation <- list(
  targets::tar_target(
    name = observation_contract_files,
    command = normalizePath(observation_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_observation_plan,
    command = build_prototype_observation_plan(
      prototype_scene_selection = s01_pilot_scene_index,
      prototype_membership_acceptance = prototype_membership_acceptance,
      observation_contract_files = observation_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "rds",
    iteration = "list",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_vector_observation_shard,
    command = build_prototype_vector_observation_shard(
      prototype_observation_plan = prototype_observation_plan,
      prototype_membership_acceptance = prototype_membership_acceptance,
      study_data_inputs = i01_seoul_spatial_sources,
      prototype_runtime_inputs = prototype_runtime_inputs,
      observation_contract_files = observation_contract_files,
      workers = 1L,
      threads = 1L
    ),
    pattern = map(prototype_observation_plan),
    iteration = "list",
    format = "file",
    resources = controller_40_resources
  )
)
