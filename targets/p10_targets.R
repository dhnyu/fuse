list_p10_targets <- list(
  targets::tar_target(p10_evaluation_contract, "config/p10_evaluation.yml", format = "file"),
  targets::tar_target(p10_prepared_input_cache,
    { p10_source_gate; p10_build_prepared_input(p10_evaluation_contract) }, format = "file"
  ),
  targets::tar_target(p10_prepared_geometry_cache,
    p10_build_prepared_geometry(p10_evaluation_contract, p10_prepared_input_cache), format = "file"
  ),
  targets::tar_target(p10_evaluation_acceptance,
    p10_run_evaluation(p10_evaluation_contract, p10_prepared_input_cache,
                       p10_prepared_geometry_cache), format = "file"
  ),
  targets::tar_target(p10_evaluation_acceptance_readback,
    p10_acceptance_readback(p10_evaluation_acceptance), format = "file")
)
