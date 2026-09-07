p5_branch_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05", seconds_timeout = 7200)
)

list_s05_fixed_queries <- list(
  targets::tar_target(s05_query_sources, normalizePath(p5_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s05_query_contract,
    p5_build_contract(s00_evaluation_methodology_contract, s00_augmentation_methodology_contract,
      s03_scene_dataset_acceptance, s04_bank_profile_plan, s04_bank_shard_plan,
      s04_bank_acceptance, s04_bank_acceptance, s00_methodology_authority, s05_query_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s05_query_shard_plan,
    p5_build_shard_plan(s05_query_contract, s01_scene_index,
      s03_scene_cache_index, s03_scene_serialization_shard,
      s03_scene_dataset_acceptance, s04_bank_shard_plan, s05_query_sources),
    format = "rds", iteration = "list", resources = controller_05_resources),
  targets::tar_target(s05_query_execution,
    p5_run_tiered_queries(s05_query_shard_plan, s05_query_sources),
    format = "file", resources = p5_branch_resources),
  targets::tar_target(s05_query_validated_shard,
    p5_validated_query_shard(s05_query_shard_plan, s05_query_sources, s05_query_execution),
    pattern = map(s05_query_shard_plan), iteration = "list", format = "file",
    resources = p5_branch_resources, error = "continue"),
  targets::tar_target(s05_query_acceptance,
    p5_consolidated_acceptance(s05_query_shard_plan, s05_query_validated_shard,
      s05_query_contract,
      s03_scene_dataset_acceptance, s05_query_sources),
    format = "file", resources = controller_05_resources)
)
