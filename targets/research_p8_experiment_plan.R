list_research_p8_experiment_plan <- list(
  targets::tar_target(
    s08_experiment_sources,
    p8_current_sources(), format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    s08_experiment_plan,
    p8_build_current_plan(s08_experiment_sources),
    format = "file", resources = controller_05_resources
  )
)
