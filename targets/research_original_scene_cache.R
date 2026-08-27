controller_40_resources <- targets::tar_resources(crew = targets::tar_resources_crew(controller = "controller_40"))

list_research_original_scene_cache <- list(
  targets::tar_target(
    p3_original_scene_cache_contract_files,
    normalizePath(p3_original_cache_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    original_scene_cache_contract,
    p3_build_contract(original_cache_methodology_contract, reduced_methodology_authority,
                      p3_original_scene_cache_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    original_scene_serialization_plan,
    p3_build_plan(original_scene_cache_contract, base_spatial_acceptance,
                  base_spatial_observation_plan, base_vector_observation_shard,
                  base_raster_observation_shard, base_relation_graph_shard,
                  base_source_topology_shard, base_spatial_membership_acceptance,
                  p3_original_scene_cache_contract_files),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    original_scene_serialization_shard,
    p3_build_shard(original_scene_serialization_plan,
                   p3_original_scene_cache_contract_files),
    pattern = map(original_scene_serialization_plan), iteration = "list",
    format = "file", resources = controller_40_resources, error = "continue"
  ),
  targets::tar_target(
    original_scene_shard_validation,
    p3_validate_shard(original_scene_serialization_shard,
                      p3_original_scene_cache_contract_files),
    pattern = map(original_scene_serialization_shard), iteration = "list",
    format = "rds", resources = controller_40_resources
  ),
  targets::tar_target(
    original_scene_geometry_roundtrip,
    p3_build_roundtrip(original_scene_serialization_plan,
                       original_scene_serialization_shard,
                       original_scene_shard_validation,
                       p3_original_scene_cache_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    original_scene_cache_index,
    p3_build_index(original_scene_serialization_plan,
                   original_scene_serialization_shard,
                   original_scene_geometry_roundtrip,
                   p3_original_scene_cache_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    original_scene_cache_manifest,
    p3_build_cache_manifest(original_scene_serialization_plan,
                            original_scene_serialization_shard,
                            original_scene_cache_index,
                            original_scene_geometry_roundtrip,
                            base_spatial_acceptance,
                            p3_original_scene_cache_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    original_scene_dataset_acceptance,
    p3_accept_dataset(original_scene_serialization_plan,
                      original_scene_serialization_shard,
                      original_scene_geometry_roundtrip,
                      original_scene_cache_index,
                      original_scene_cache_manifest,
                      base_spatial_acceptance,
                      p3_original_scene_cache_contract_files),
    format = "file", resources = controller_05_resources
  )
)
