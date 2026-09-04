list_p11_downstream_preprocessing <- list(
  targets::tar_target(
    p11_preprocessing_config,
    "config/p11_downstream_preprocessing.yml",
    format = "file"
  ),
  targets::tar_target(
    p11_methodology_decision,
    "config/p11_methodology_decision.json",
    format = "file"
  ),
  targets::tar_target(
    p11_source_contracts,
    c("config/p11_sgis_source_contract.json", "config/p11_living_population_source_contract.json",
      "config/p11_land_value_source_contract.json", "config/p11_ecostress_source_contract.json"),
    format = "file"
  ),
  targets::tar_target(
    p11_downstream_dataset,
    {
      p11_methodology_decision
      p11_source_contracts
      p11_execute_preprocessing(p11_preprocessing_config)
    }
  )
)
