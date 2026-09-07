list_s08_experiment_plan <- list(
  targets::tar_target(
    s08_current_plan_sources,
    current_experiment_plan_sources(), format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    s08_current_experiment_plan,
    build_current_experiment_plan(s08_current_plan_sources),
    format = "file", resources = controller_05_resources
  )
)
