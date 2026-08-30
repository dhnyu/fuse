list_research_p9_formal_authorization <- list(
  targets::tar_target(
    p9_formal_authorization_contract_files,
    p9_formal_contract_files(), format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_formal_accepted_parent_references,
    p9_formal_parent_paths(p9_formal_authorization_contract_files[[1L]]),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_production_cache_plan_bundle,
    p9_build_cache_plan_bundle(p9_formal_authorization_contract_files, p9_formal_accepted_parent_references),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_cache_reuse_graph,
    p9_plan_artifact(p9_production_cache_plan_bundle, "cache_reuse_graph.json"),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_cache_identity_contract,
    p9_plan_artifact(p9_production_cache_plan_bundle, "cache_identity_contract.json", p9_cache_reuse_graph),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_cache_resource_plan,
    p9_plan_artifact(p9_production_cache_plan_bundle, "cache_resource_plan.json", p9_cache_identity_contract),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_cache_shard_plan,
    p9_plan_artifact(p9_production_cache_plan_bundle, "cache_shard_plan.json", p9_cache_resource_plan),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_production_cache_build_authority,
    p9_plan_artifact(p9_production_cache_plan_bundle, "production_cache_build_authority.json", p9_cache_shard_plan),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_production_cache_materialization,
    p9_materialize_production_cache(p9_production_cache_build_authority, p9_formal_authorization_contract_files),
    format = "file", resources = controller_gpu_02_resources
  ),
  targets::tar_target(
    p9_production_cache_validation,
    p9_validate_production_cache(p9_production_cache_materialization, p9_formal_authorization_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_formal_publication_bundle,
    p9_publish_formal_bundle(p9_production_cache_build_authority, p9_production_cache_validation,
                             p9_formal_accepted_parent_references, p9_formal_authorization_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_production_cache_acceptance,
    p9_formal_artifact(p9_formal_publication_bundle, "production_cache_acceptance.json"),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_formal_training_authority,
    p9_formal_artifact(p9_formal_publication_bundle, "p9_formal_training_authority.json", p9_production_cache_acceptance),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p9_cfg_main_attempt_reservation,
    p9_formal_artifact(p9_formal_publication_bundle, "cfg_main_attempt_reservation.json", p9_formal_training_authority),
    format = "file", resources = controller_05_resources
  )
)
