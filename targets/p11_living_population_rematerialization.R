list_p11_living_population_rematerialization <- list(
  targets::tar_target(
    p11_living_v2_config,
    "config/p11_downstream_preprocessing_v2.yml",
    format = "file"
  ),
  targets::tar_target(
    p11_living_v2_authorities,
    c("config/dissertation_authority_refresh.json", "config/p11_methodology_decision_v2.json",
      "config/p11_living_population_source_contract_v2.json"),
    format = "file"
  ),
  targets::tar_target(
    p11_living_v2_dataset,
    {
      p11_living_v2_authorities
      p11_execute_living_partial_support_rematerialization(p11_living_v2_config)
    }
  )
)
