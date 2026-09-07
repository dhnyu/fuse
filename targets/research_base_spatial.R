controller_20_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_20")
)

list_research_base_spatial <- list(
  targets::tar_target(
    p2_base_spatial_contract_files,
    normalizePath(p2_base_spatial_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    base_spatial_prototype_membership_plan,
    p2_build_membership_plan(
      "prototype", s01_scene_index, s01_pilot_scene_index,
      s01_scene_acceptance, s01_study_inventory_validation, reduced_methodology_authority,
      base_spatial_methodology_contract, membership_contract_files,
      p2_base_spatial_contract_files
    ),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    base_spatial_prototype_membership_shard,
    p2_build_membership_shard(
      base_spatial_prototype_membership_plan, i01_seoul_spatial_sources,
      i01_seoul_spatial_sources, membership_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_prototype_membership_plan), iteration = "list",
    format = "file", resources = controller_40_resources
  ),
  targets::tar_target(
    base_spatial_prototype_membership_acceptance,
    p2_accept_membership(
      "prototype", base_spatial_prototype_membership_plan,
      base_spatial_prototype_membership_shard, s01_scene_index,
      s01_pilot_scene_index, s01_study_inventory_validation, membership_contract_files,
      p2_base_spatial_contract_files
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    base_spatial_prototype_observation_plan,
    p2_build_observation_plan(
      "prototype", base_spatial_prototype_membership_plan,
      base_spatial_prototype_membership_acceptance, s01_scene_index,
      s01_pilot_scene_index, observation_contract_files,
      raster_observation_contract_files, relation_contract_files,
      p2_base_spatial_contract_files
    ),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    base_spatial_prototype_vector_observation_shard,
    p2_build_vector_shard(
      base_spatial_prototype_observation_plan,
      base_spatial_prototype_membership_acceptance, i01_seoul_spatial_sources,
      i01_seoul_spatial_sources, observation_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_prototype_observation_plan), iteration = "list",
    format = "file", resources = controller_40_resources
  ),
  targets::tar_target(
    base_spatial_prototype_raster_observation_shard,
    p2_build_raster_shard(
      base_spatial_prototype_observation_plan,
      base_spatial_prototype_vector_observation_shard, i01_seoul_spatial_sources,
      i01_seoul_spatial_sources, raster_observation_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_prototype_observation_plan, base_spatial_prototype_vector_observation_shard),
    iteration = "list", format = "file", resources = controller_40_resources
  ),
  targets::tar_target(
    base_spatial_prototype_relation_graph_shard,
    p2_build_relation_shard(
      base_spatial_prototype_observation_plan,
      base_spatial_prototype_vector_observation_shard, i01_seoul_spatial_sources,
      i01_seoul_spatial_sources, relation_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_prototype_observation_plan, base_spatial_prototype_vector_observation_shard),
    iteration = "list", format = "file", resources = controller_40_resources
  ),
  targets::tar_target(
    base_spatial_prototype_source_topology_shard,
    p2_build_topology_shard(
      base_spatial_prototype_observation_plan,
      base_spatial_prototype_vector_observation_shard, i01_seoul_spatial_sources,
      p2_base_spatial_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_prototype_observation_plan, base_spatial_prototype_vector_observation_shard),
    iteration = "list", format = "file", resources = controller_40_resources
  ),
  targets::tar_target(
    base_spatial_prototype_acceptance,
    p2_build_base_spatial_acceptance(
      "prototype", base_spatial_prototype_membership_plan,
      base_spatial_prototype_membership_acceptance,
      base_spatial_prototype_observation_plan,
      base_spatial_prototype_vector_observation_shard,
      base_spatial_prototype_raster_observation_shard,
      base_spatial_prototype_relation_graph_shard,
      base_spatial_prototype_source_topology_shard,
      s01_scene_index, s01_pilot_scene_index,
      reduced_methodology_authority, s01_scene_acceptance,
      i01_seoul_spatial_sources, raster_observation_contract_files,
      relation_contract_files, p2_base_spatial_contract_files
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    base_spatial_membership_plan,
    p2_build_membership_plan(
      "production", s01_scene_index, s01_pilot_scene_index,
      s01_scene_acceptance, s01_study_inventory_validation, reduced_methodology_authority,
      base_spatial_methodology_contract, membership_contract_files,
      p2_base_spatial_contract_files, base_spatial_prototype_acceptance
    ),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    base_spatial_membership_shard,
    p2_build_membership_shard(
      base_spatial_membership_plan, i01_seoul_spatial_sources, i01_seoul_spatial_sources,
      membership_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_membership_plan), iteration = "list",
    format = "file", resources = controller_40_resources
  ),
  targets::tar_target(
    base_spatial_membership_acceptance,
    p2_accept_membership(
      "production", base_spatial_membership_plan,
      base_spatial_membership_shard, s01_scene_index,
      s01_pilot_scene_index, s01_study_inventory_validation, membership_contract_files,
      p2_base_spatial_contract_files
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    base_spatial_observation_plan,
    p2_build_observation_plan(
      "production", base_spatial_membership_plan,
      base_spatial_membership_acceptance, s01_scene_index,
      s01_pilot_scene_index, observation_contract_files,
      raster_observation_contract_files, relation_contract_files,
      p2_base_spatial_contract_files
    ),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    base_vector_observation_shard,
    p2_build_vector_shard(
      base_spatial_observation_plan, base_spatial_membership_acceptance,
      i01_seoul_spatial_sources, i01_seoul_spatial_sources, observation_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_observation_plan), iteration = "list",
    format = "file", resources = controller_20_resources
  ),
  targets::tar_target(
    base_raster_observation_shard,
    p2_build_raster_shard(
      base_spatial_observation_plan, base_vector_observation_shard,
      i01_seoul_spatial_sources, i01_seoul_spatial_sources, raster_observation_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_observation_plan, base_vector_observation_shard),
    iteration = "list", format = "file", resources = controller_20_resources
  ),
  targets::tar_target(
    base_relation_tiered_execution_acceptance,
    p2_relation_tiered_acceptance_path(base_spatial_observation_plan),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    base_relation_graph_shard,
    p2_register_tiered_relation_shard(
      base_spatial_observation_plan, base_vector_observation_shard,
      base_relation_tiered_execution_acceptance
    ),
    pattern = map(base_spatial_observation_plan, base_vector_observation_shard),
    iteration = "list", format = "file", resources = controller_20_resources
  ),
  targets::tar_target(
    base_source_topology_shard,
    p2_build_topology_shard(
      base_spatial_observation_plan, base_vector_observation_shard,
      i01_seoul_spatial_sources, p2_base_spatial_contract_files, 1L, 1L
    ),
    pattern = map(base_spatial_observation_plan, base_vector_observation_shard),
    iteration = "list", format = "file", resources = controller_20_resources
  ),
  targets::tar_target(
    base_spatial_acceptance,
    p2_build_base_spatial_acceptance(
      "production", base_spatial_membership_plan,
      base_spatial_membership_acceptance, base_spatial_observation_plan,
      base_vector_observation_shard, base_raster_observation_shard,
      base_relation_graph_shard, base_source_topology_shard,
      s01_scene_index, s01_pilot_scene_index,
      reduced_methodology_authority, s01_scene_acceptance,
      i01_seoul_spatial_sources, raster_observation_contract_files,
      relation_contract_files, p2_base_spatial_contract_files
    ),
    format = "file", resources = controller_05_resources
  )
)
