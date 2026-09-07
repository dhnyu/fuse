list_research_p8_experiment_plan <- list(
  targets::tar_target(
    s08_experiment_sources,
    p8_replay_sources(), format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    s08_experiment_plan,
    p8_replay_bundle(s08_experiment_sources),
    format = "file", resources = controller_05_resources
  )
)
