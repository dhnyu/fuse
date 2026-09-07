p5_branch_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05", seconds_timeout = 7200)
)

list_research_fixed_queries <- list(
  targets::tar_target(s05_query_sources, normalizePath(p5_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s05_query_contract,
    p5_build_contract(evaluation_methodology_contract, augmentation_methodology_contract,
      accepted_p3_dataset_acceptance_reference, s04_bank_profile_plan, s04_bank_shard_plan,
      s04_bank_acceptance, s04_bank_acceptance, reduced_methodology_authority, s05_query_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s05_query_shard_plan,
    p5_build_shard_plan(s05_query_contract, accepted_p1_scene_index_reference,
      accepted_p3_index_reference, accepted_p3_shard_reference,
      accepted_p3_dataset_acceptance_reference, s04_bank_shard_plan, s05_query_sources),
    format = "rds", iteration = "list", resources = controller_05_resources),
  targets::tar_target(s05_query_execution,
    p5_run_tiered_queries(s05_query_shard_plan, s05_query_sources),
    format = "file", resources = p5_branch_resources),
  targets::tar_target(fixed_query_shard,
    p5_build_query_shard(s05_query_shard_plan, s05_query_sources, s05_query_execution),
    pattern = map(s05_query_shard_plan), iteration = "list", format = "file",
    resources = p5_branch_resources, error = "continue"),
  targets::tar_target(fixed_query_shard_validation,
    p5_validate_query_shard(fixed_query_shard, s05_query_shard_plan, s05_query_sources),
    pattern = map(fixed_query_shard, s05_query_shard_plan), iteration = "list", format = "rds",
    resources = p5_branch_resources, error = "continue"),
  targets::tar_target(s05_query_acceptance,
    p5_consolidated_acceptance(s05_query_shard_plan, fixed_query_shard,
      fixed_query_shard_validation, s05_query_contract,
      accepted_p3_dataset_acceptance_reference, s05_query_sources),
    format = "file", resources = controller_05_resources)
)
