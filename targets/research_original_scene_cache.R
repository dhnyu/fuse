controller_40_resources <- targets::tar_resources(crew = targets::tar_resources_crew(controller = "controller_40"))

list_research_original_scene_cache <- list(
  targets::tar_target(
    s03_dataset_sources,
    normalizePath(p3_original_cache_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    s03_scene_serialization_plan,
    p3_build_serialization_plan(original_cache_methodology_contract, reduced_methodology_authority,
                  base_spatial_acceptance,
                  base_spatial_observation_plan, base_vector_observation_shard,
                  base_raster_observation_shard, base_relation_graph_shard,
                  base_source_topology_shard, base_spatial_membership_acceptance,
                  s03_dataset_sources),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    s03_scene_serialization_shard,
    p3_build_shard(s03_scene_serialization_plan, s03_dataset_sources),
    pattern = map(s03_scene_serialization_plan), iteration = "list",
    format = "file", resources = controller_40_resources, error = "continue"
  ),
  targets::tar_target(
    s03_scene_shard_validation,
    p3_validate_shard(s03_scene_serialization_shard, s03_dataset_sources),
    pattern = map(s03_scene_serialization_shard), iteration = "list",
    format = "rds", resources = controller_40_resources
  ),
  targets::tar_target(
    s03_scene_cache_index,
    p3_build_scene_cache_index(s03_scene_serialization_plan,
      s03_scene_serialization_shard, s03_scene_shard_validation, s03_dataset_sources),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    s03_scene_dataset_acceptance,
    p3_build_dataset_acceptance(s03_scene_serialization_plan,
      s03_scene_serialization_shard, s03_scene_cache_index,
      base_spatial_acceptance, s03_dataset_sources),
    format = "file", resources = controller_05_resources
  )
)
