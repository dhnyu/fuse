controller_20_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_20")
)

list_s02_spatial_observations <- list(
  targets::tar_target(s02_membership_sources, normalizePath(membership_contract_paths(), mustWork = TRUE), format = "file", resources = controller_05_resources),
  targets::tar_target(s02_vector_sources, normalizePath(observation_contract_paths(), mustWork = TRUE), format = "file", resources = controller_05_resources),
  targets::tar_target(s02_raster_sources, normalizePath(raster_observation_contract_paths(), mustWork = TRUE), format = "file", resources = controller_05_resources),
  targets::tar_target(s02_relation_sources, normalizePath(relation_contract_paths(), mustWork = TRUE), format = "file", resources = controller_05_resources),
  targets::tar_target(s02_spatial_sources, normalizePath(p2_base_spatial_contract_paths(), mustWork = TRUE), format = "file", resources = controller_05_resources),
  targets::tar_target(
    s02_membership_plan,
    p2_build_membership_plan(s01_scene_index, s01_scene_acceptance,
      s01_study_inventory_validation, s00_methodology_authority, s00_spatial_methodology_contract,
      s02_membership_sources, s02_spatial_sources),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    s02_membership_shard,
    p2_build_membership_shard(s02_membership_plan, i01_seoul_spatial_sources,
      i01_seoul_spatial_sources, s02_membership_sources, 1L, 1L),
    pattern = map(s02_membership_plan), iteration = "list", format = "file", resources = controller_40_resources
  ),
  targets::tar_target(
    s02_membership_acceptance,
    p2_accept_membership(s02_membership_plan, s02_membership_shard,
      s01_scene_index, s01_study_inventory_validation,
      s02_membership_sources, s02_spatial_sources),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    s02_observation_plan,
    p2_build_observation_plan(s02_membership_plan, s02_membership_acceptance,
      s01_scene_index, s02_vector_sources, s02_raster_sources,
      s02_relation_sources, s02_spatial_sources),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    s02_vector_observation_shard,
    p2_build_vector_shard(s02_observation_plan, s02_membership_acceptance,
      i01_seoul_spatial_sources, i01_seoul_spatial_sources, s02_vector_sources, 1L, 1L),
    pattern = map(s02_observation_plan), iteration = "list", format = "file", resources = controller_20_resources
  ),
  targets::tar_target(
    s02_raster_observation_shard,
    p2_build_raster_shard(s02_observation_plan, s02_vector_observation_shard,
      i01_seoul_spatial_sources, i01_seoul_spatial_sources, s02_raster_sources, 1L, 1L),
    pattern = map(s02_observation_plan, s02_vector_observation_shard), iteration = "list", format = "file", resources = controller_20_resources
  ),
  targets::tar_target(
    s02_relation_execution,
    p2_run_relation_tiered_execution(s02_observation_plan, s02_vector_observation_shard,
      i01_seoul_spatial_sources, s02_relation_sources),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    s02_relation_shard,
    p2_register_tiered_relation_shard(s02_observation_plan, s02_vector_observation_shard, s02_relation_execution),
    pattern = map(s02_observation_plan, s02_vector_observation_shard), iteration = "list", format = "file", resources = controller_20_resources
  ),
  targets::tar_target(
    s02_source_topology_shard,
    p2_build_topology_shard(s02_observation_plan, s02_vector_observation_shard,
      i01_seoul_spatial_sources, s02_spatial_sources, 1L, 1L),
    pattern = map(s02_observation_plan, s02_vector_observation_shard), iteration = "list", format = "file", resources = controller_20_resources
  ),
  targets::tar_target(
    s02_spatial_acceptance,
    p2_build_base_spatial_acceptance(s02_membership_plan, s02_membership_acceptance,
      s02_observation_plan, s02_vector_observation_shard, s02_raster_observation_shard,
      s02_relation_shard, s02_source_topology_shard, s01_scene_index,
      s00_methodology_authority, s01_scene_acceptance, i01_seoul_spatial_sources,
      s02_raster_sources, s02_relation_sources, s02_spatial_sources),
    format = "file", resources = controller_05_resources
  )
)
