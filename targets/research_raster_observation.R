list_research_raster_observation <- list(
  targets::tar_target(
    name = raster_observation_contract_files,
    command = normalizePath(raster_observation_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_raster_observation_shard,
    command = build_prototype_raster_observation_shard(
      prototype_observation_plan = prototype_observation_plan,
      prototype_vector_observation_shard = prototype_vector_observation_shard,
      study_data_inputs = study_data_inputs,
      raster_observation_contract_files = raster_observation_contract_files,
      workers = 1L,
      threads = 1L
    ),
    pattern = map(prototype_observation_plan, prototype_vector_observation_shard),
    iteration = "list",
    format = "file",
    resources = controller_10_resources
  )
)
