list_s10_evaluation_targets <- list(
  targets::tar_target(s10_evaluation_contract, "config/evaluation.yml", format = "file"),
  targets::tar_target(s10_evaluation_input_cache,
    { s10_evaluation_sources; p10_build_prepared_input(s10_evaluation_contract) }, format = "file"
  ),
  targets::tar_target(s10_evaluation_geometry_cache,
    p10_build_prepared_geometry(s10_evaluation_contract, s10_evaluation_input_cache), format = "file"
  ),
  targets::tar_target(s10_evaluation_acceptance,
    p10_run_evaluation_with_readback(s10_evaluation_contract, s10_evaluation_input_cache,
                                     s10_evaluation_geometry_cache), format = "file"
  )
)
