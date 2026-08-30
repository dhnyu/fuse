list_research_p9_infrastructure <- list(
  targets::tar_target(
    p9_infrastructure_contract_files,
    c("config/p9_infrastructure.yml", "config/schemas/p9_infrastructure_readiness.schema.json",
      "python/p9_infrastructure.py", "python/p9_model_families.py", "python/p9_data.py",
      "python/rotating_padding_sampler.py", "scripts/p9_infrastructure.py",
      "scripts/p9_model_family_smoke.py",
      list.files("config/schemas", pattern = "^p9_.*\\.schema\\.json$", full.names = TRUE)),
    format = "file"
  ),
  targets::tar_target(
    p9_infrastructure_readiness,
    build_p9_infrastructure_readiness(
      p9_infrastructure_contract_files[[1]], p9_infrastructure_contract_files[[2]],
      system2("git", c("rev-parse", "HEAD"), stdout = TRUE)
    ),
    format = "file"
  )
)
