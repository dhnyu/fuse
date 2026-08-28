list_research_immutable_parent_references <- list(
  targets::tar_target(
    accepted_immutable_parent_config,
    normalizePath(accepted_parent_config_path(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    accepted_p1_scene_index_reference,
    accepted_p1_scene_index_files(accepted_immutable_parent_config),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    accepted_p2_base_spatial_reference,
    accepted_p2_base_spatial_files(accepted_immutable_parent_config),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    accepted_p3_shard_files_reference,
    accepted_p3_shard_files(accepted_immutable_parent_config),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    accepted_p3_shard_reference,
    accepted_p3_shard_groups(accepted_p3_shard_files_reference, accepted_immutable_parent_config),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    accepted_p3_index_reference,
    accepted_p3_index_files(accepted_immutable_parent_config),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    accepted_p3_dataset_acceptance_reference,
    accepted_p3_acceptance_files(accepted_immutable_parent_config),
    format = "file", resources = controller_05_resources
  )
)
