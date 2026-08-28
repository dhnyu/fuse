p5_branch_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_40", seconds_timeout = 7200)
)

list_research_fixed_queries <- list(
  targets::tar_target(
    p5_deterministic_contract_files,
    normalizePath(p5_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_query_methodology_contract,
    p5_build_contract(evaluation_methodology_contract, augmentation_methodology_contract,
                      original_scene_dataset_acceptance, augmentation_profile_plan,
                      augmentation_bank_plan, p5_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_query_shard_plan,
    p5_build_shard_plan(fixed_query_methodology_contract, spatial_scene_index,
                        original_scene_cache_index, original_scene_serialization_shard,
                        original_scene_dataset_acceptance, augmentation_bank_plan,
                        p5_deterministic_contract_files),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_validation_query_plan,
    p5_filter_plan(fixed_query_shard_plan, "validation"),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_evaluation_query_plan,
    p5_filter_plan(fixed_query_shard_plan, "evaluation"),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_query_branch_plan,
    c(fixed_validation_query_plan, fixed_evaluation_query_plan),
    format = "rds", iteration = "list", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_query_shard,
    p5_build_query_shard(fixed_query_branch_plan, p5_deterministic_contract_files),
    pattern = map(fixed_query_branch_plan), iteration = "list", format = "file",
    resources = p5_branch_resources, error = "continue"
  ),
  targets::tar_target(
    fixed_query_shard_validation,
    p5_validate_query_shard(fixed_query_shard, p5_deterministic_contract_files),
    pattern = map(fixed_query_shard), iteration = "list", format = "rds",
    resources = p5_branch_resources, error = "continue"
  ),
  targets::tar_target(
    fixed_query_acceptance_bundle,
    p5_accept_queries(fixed_query_branch_plan, fixed_query_shard,
                      fixed_query_shard_validation, fixed_query_methodology_contract,
                      original_scene_dataset_acceptance, p5_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_validation_query_acceptance,
    p5_select_acceptance(fixed_query_acceptance_bundle, "validation", p5_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_evaluation_query_acceptance,
    p5_select_acceptance(fixed_query_acceptance_bundle, "evaluation", p5_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    fixed_query_acceptance,
    p5_final_acceptance(fixed_query_acceptance_bundle, fixed_validation_query_acceptance,
                        fixed_evaluation_query_acceptance, p5_deterministic_contract_files),
    format = "file", resources = controller_05_resources
  )
)
