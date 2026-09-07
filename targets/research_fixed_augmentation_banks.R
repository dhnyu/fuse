p4_branch_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05", seconds_timeout = 7200)
)

list_research_fixed_augmentation_banks <- list(
  targets::tar_target(s04_bank_sources, normalizePath(p4_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s04_bank_profile_plan,
    p4_build_profile_plan(augmentation_methodology_contract, reduced_methodology_authority, s04_bank_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s04_bank_road_validation,
    p4_run_smoke("road", s04_bank_profile_plan, accepted_p3_dataset_acceptance_reference, s04_bank_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s04_bank_geometry_validation,
    p4_run_smoke("geometry", s04_bank_profile_plan, accepted_p3_dataset_acceptance_reference, s04_bank_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s04_bank_shard_plan,
    p4_build_bank_plan(s04_bank_profile_plan, s04_bank_road_validation, s04_bank_geometry_validation,
      accepted_p3_shard_reference, accepted_p3_dataset_acceptance_reference, s04_bank_sources),
    format = "rds", iteration = "list", resources = controller_05_resources),
  targets::tar_target(s04_bank_execution,
    p4_run_tiered_bank(s04_bank_shard_plan, s04_bank_sources),
    format = "file", resources = p4_branch_resources),
  targets::tar_target(s04_bank_validated_shard,
    p4_validated_bank_shard(s04_bank_shard_plan, s04_bank_sources, s04_bank_execution),
    pattern = map(s04_bank_shard_plan), iteration = "list", format = "file",
    resources = p4_branch_resources, error = "continue"),
  targets::tar_target(s04_bank_acceptance,
    p4_consolidated_acceptance(s04_bank_shard_plan, s04_bank_validated_shard,
      accepted_p3_dataset_acceptance_reference, s04_bank_sources),
    format = "file", resources = controller_05_resources)
)
