list_s08_experiment_plan <- list(
  targets::tar_target(
    s08_current_plan_sources,
    current_experiment_plan_sources(), format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    s08_current_experiment_plan,
    build_current_experiment_plan(
      s08_current_plan_sources,
      s00_methodology_authority,
      s01_scene_acceptance,
      s02_spatial_acceptance,
      s03_scene_dataset_acceptance,
      s04_bank_acceptance,
      s05_query_acceptance,
      s06_dataset_acceptance
    ),
    format = "file", resources = controller_05_resources
  )
)
