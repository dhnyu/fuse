list_research_serialization_plan <- list(
  targets::tar_target(
    name = serialization_plan_contract_files,
    command = normalizePath(serialization_plan_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_serialization_plan,
    command = build_prototype_serialization_plan(
      prototype_spatial_acceptance = prototype_spatial_acceptance,
      serialization_plan_contract_files = serialization_plan_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "rds",
    iteration = "list",
    resources = controller_05_resources
  )
)
