p4_branch_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_40", seconds_timeout = 7200)
)

list_research_fixed_augmentation_banks <- list(
  targets::tar_target(
    p4_deterministic_contract_files,
    normalizePath(p4_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    augmentation_profile_plan,
    p4_build_profile_plan(augmentation_methodology_contract, reduced_methodology_authority,
                          p4_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    road_link_absorption_smoke,
    p4_run_smoke("road", augmentation_profile_plan, original_scene_dataset_acceptance,
                 p4_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    geometry_consistency_smoke,
    p4_run_smoke("geometry", augmentation_profile_plan, original_scene_dataset_acceptance,
                 p4_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    augmentation_bank_plan,
    p4_build_bank_plan(augmentation_profile_plan, road_link_absorption_smoke,
                       geometry_consistency_smoke, original_scene_serialization_shard,
                       original_scene_dataset_acceptance, p4_deterministic_contract_files),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    augmentation_bank_shard,
    p4_build_bank_shard(augmentation_bank_plan, p4_deterministic_contract_files),
    pattern = map(augmentation_bank_plan), iteration = "list", format = "file",
    resources = p4_branch_resources, error = "continue"
  ),
  targets::tar_target(
    augmentation_bank_shard_validation,
    p4_validate_bank_shard(augmentation_bank_shard, p4_deterministic_contract_files),
    pattern = map(augmentation_bank_shard), iteration = "list", format = "rds",
    resources = p4_branch_resources, error = "continue"
  ),
  targets::tar_target(
    augmentation_bank_acceptance,
    p4_accept_bank(augmentation_bank_plan, augmentation_bank_shard,
                   augmentation_bank_shard_validation, original_scene_dataset_acceptance,
                   p4_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    effective_augmentation_bank_index,
    p4_publish_effective_index(augmentation_bank_acceptance,
                               p4_deterministic_contract_files),
    format = "rds", resources = controller_05_resources
  ),
  targets::tar_target(
    augmentation_bank_benchmark,
    p4_benchmark_bank(augmentation_bank_acceptance, effective_augmentation_bank_index,
                      p4_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  )
)
