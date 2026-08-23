list_research_relation <- list(
  targets::tar_target(
    name = relation_contract_files,
    command = normalizePath(relation_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_relation_shard,
    command = build_prototype_relation_shard(
      prototype_observation_plan = prototype_observation_plan,
      prototype_vector_observation_shard = prototype_vector_observation_shard,
      study_data_inputs = study_data_inputs,
      prototype_runtime_inputs = prototype_runtime_inputs,
      relation_contract_files = relation_contract_files,
      workers = 1L,
      threads = 1L
    ),
    pattern = map(prototype_observation_plan, prototype_vector_observation_shard),
    iteration = "list",
    format = "file",
    resources = controller_40_resources
  )
)
