list_research_spatial_acceptance <- list(
  targets::tar_target(
    name = spatial_acceptance_contract_files,
    command = normalizePath(spatial_acceptance_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_spatial_acceptance,
    command = build_prototype_spatial_acceptance(
      prototype_observation_plan = prototype_observation_plan,
      prototype_vector_observation_shard = prototype_vector_observation_shard,
      prototype_raster_observation_shard = prototype_raster_observation_shard,
      prototype_relation_shard = prototype_relation_shard,
      methodology_contract = methodology_contract,
      spatial_acceptance_contract_files = spatial_acceptance_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  )
)
