list_research_serialization_shard <- list(
  targets::tar_target(
    name = serialization_shard_contract_files,
    command = normalizePath(serialization_shard_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_40_resources
  ),
  targets::tar_target(
    name = prototype_serialization_shard,
    command = run_prototype_serialization_shard(
      prototype_serialization_plan = prototype_serialization_plan,
      serialization_shard_contract_files = serialization_shard_contract_files,
      workers = 1L,
      threads = 1L
    ),
    pattern = map(prototype_serialization_plan),
    format = "file",
    resources = controller_40_resources
  )
)
