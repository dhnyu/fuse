list_research_prototype_training <- list(
  targets::tar_target(
    p7_training_contract_files, p7_contract_files(), format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    p7_validation_query_reference,
    p7_resolve_validation_query_reference(p5_deterministic_contract_files, p7_training_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p7_p6_parent_reference,
    p7_resolve_p6_parent_reference(p7_training_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p7_immutable_parent_reference,
    p7_resolve_immutable_parent_reference(p7_training_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p7_deterministic_training_authority,
    p7_build_authority(
      p7_p6_parent_reference, p7_p6_parent_reference, p7_p6_parent_reference,
      p7_immutable_parent_reference, p7_immutable_parent_reference,
      p7_immutable_parent_reference, p7_validation_query_reference,
      p7_immutable_parent_reference, p7_immutable_parent_reference,
      p7_training_contract_files
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p7_geometry_feature_cache,
    p7_build_geometry_cache(
      p7_deterministic_training_authority, p7_p6_parent_reference,
      p7_p6_parent_reference, p7_p6_parent_reference,
      p7_immutable_parent_reference, p7_immutable_parent_reference,
      p7_immutable_parent_reference,
      p7_validation_query_reference, p7_immutable_parent_reference,
      p7_training_contract_files
    ),
    format = "file", resources = controller_gpu_02_resources
  ),
  targets::tar_target(
    p7_ddp_initialization_smoke,
    p7_gpu_gate(
      "init", p7_deterministic_training_authority, p7_p6_parent_reference,
      p7_p6_parent_reference, p7_p6_parent_reference,
      p7_immutable_parent_reference, p7_immutable_parent_reference,
      p7_immutable_parent_reference, p7_validation_query_reference,
      p7_immutable_parent_reference, p7_geometry_feature_cache, p7_training_contract_files
    ),
    format = "file", resources = controller_gpu_02_resources
  ),
  targets::tar_target(
    p7_single_update_smoke,
    {
      p7_ddp_initialization_smoke
      p7_gpu_gate(
        "update", p7_deterministic_training_authority, p7_p6_parent_reference,
        p7_p6_parent_reference, p7_p6_parent_reference,
        p7_immutable_parent_reference, p7_immutable_parent_reference,
        p7_immutable_parent_reference, p7_validation_query_reference,
        p7_immutable_parent_reference, p7_geometry_feature_cache, p7_training_contract_files
      )
    },
    format = "file", resources = controller_gpu_02_resources
  ),
  targets::tar_target(
    p7_ddp_reference_acceptance,
    {
      p7_single_update_smoke
      p7_gpu_gate(
        "reference", p7_deterministic_training_authority, p7_p6_parent_reference,
        p7_p6_parent_reference, p7_p6_parent_reference,
        p7_immutable_parent_reference, p7_immutable_parent_reference,
        p7_immutable_parent_reference, p7_validation_query_reference,
        p7_immutable_parent_reference, p7_geometry_feature_cache, p7_training_contract_files
      )
    },
    format = "file", resources = controller_gpu_02_resources
  ),
  targets::tar_target(
    p7_resume_equivalence,
    {
      p7_ddp_reference_acceptance
      p7_gpu_gate(
        "resume", p7_deterministic_training_authority, p7_p6_parent_reference,
        p7_p6_parent_reference, p7_p6_parent_reference,
        p7_immutable_parent_reference, p7_immutable_parent_reference,
        p7_immutable_parent_reference, p7_validation_query_reference,
        p7_immutable_parent_reference, p7_geometry_feature_cache, p7_training_contract_files
      )
    },
    format = "file", resources = controller_gpu_02_resources
  ),
  targets::tar_target(
    prototype_training_run,
    p7_run_production(
      p7_deterministic_training_authority, p7_resume_equivalence,
      p7_p6_parent_reference, p7_p6_parent_reference,
      p7_p6_parent_reference, p7_immutable_parent_reference,
      p7_immutable_parent_reference, p7_immutable_parent_reference,
      p7_validation_query_reference, p7_immutable_parent_reference, p7_geometry_feature_cache,
      p7_training_contract_files
    ),
    format = "file", resources = controller_gpu_02_resources
  ),
  targets::tar_target(
    prototype_validation_retrieval,
    p7_extract_run_artifact(prototype_training_run, "training_trace.json",
                            "config/schemas/p7_training_trace.schema.json", p7_training_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    prototype_checkpoint_selection,
    p7_extract_run_artifact(prototype_training_run, "selector_result.json",
                            "config/schemas/p7_selector_result.schema.json", p7_training_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    prototype_training_execution_record,
    p7_extract_run_artifact(prototype_training_run, "execution_record.json",
                            "config/schemas/p7_training_execution.schema.json", p7_training_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    prototype_training_acceptance,
    p7_final_acceptance(
      p7_deterministic_training_authority, prototype_training_run,
      prototype_validation_retrieval, prototype_checkpoint_selection,
      prototype_training_execution_record,
      p7_geometry_feature_cache,
      c(p7_ddp_initialization_smoke, p7_single_update_smoke,
        p7_ddp_reference_acceptance, p7_resume_equivalence),
      p7_training_contract_files
    ),
    format = "file", resources = controller_05_resources
  )
)
