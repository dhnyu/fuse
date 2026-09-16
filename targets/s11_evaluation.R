list_s11_evaluation_targets <- list(
  targets::tar_target(s11_evaluation_contract, "config/evaluation.yml", format = "file"),
  targets::tar_target(s11_evaluation_input_cache,
    { s11_evaluation_sources; p11_build_prepared_input(s11_evaluation_contract) }, format = "file"
  ),
  targets::tar_target(s11_evaluation_geometry_cache,
    p11_build_prepared_geometry(s11_evaluation_contract, s11_evaluation_input_cache), format = "file"
  ),
  targets::tar_target(s11_evaluation_acceptance,
    p11_run_evaluation_with_readback(s11_evaluation_contract, s11_evaluation_input_cache,
                                     s11_evaluation_geometry_cache), format = "file"
  )
)
