list_research_prototype_training <- list(
  targets::tar_target(s07_training_sources, p7_contract_files(), format = "file", resources = controller_05_resources),
  targets::tar_target(i05_validation_query_sources,
    p7_resolve_validation_query_reference(s05_query_sources, s07_training_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(i06_accepted_model_sources,
    p7_resolve_p6_parent_reference(s07_training_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(i07_training_input_sources,
    p7_resolve_immutable_parent_reference(s07_training_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s07_pilot_training_authority,
    p7_build_authority(i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources,
      i07_training_input_sources, i07_training_input_sources, i07_training_input_sources,
      i05_validation_query_sources, i07_training_input_sources, i07_training_input_sources, s07_training_sources),
    format = "file", resources = controller_05_resources),
  targets::tar_target(s07_training_geometry_cache,
    p7_build_geometry_cache(s07_pilot_training_authority, i06_accepted_model_sources,
      i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources,
      i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources,
      i07_training_input_sources, s07_training_sources),
    format = "file", resources = controller_gpu_02_resources),
  targets::tar_target(s07_ddp_initialization_validation,
    p7_gpu_gate("init", s07_pilot_training_authority, i06_accepted_model_sources,
      i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources,
      i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources,
      i07_training_input_sources, s07_training_geometry_cache, s07_training_sources),
    format = "file", resources = controller_gpu_02_resources),
  targets::tar_target(s07_ddp_update_validation, {
    s07_ddp_initialization_validation
    p7_gpu_gate("update", s07_pilot_training_authority, i06_accepted_model_sources,
      i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources,
      i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources,
      i07_training_input_sources, s07_training_geometry_cache, s07_training_sources)
  }, format = "file", resources = controller_gpu_02_resources),
  targets::tar_target(s07_ddp_reference_validation, {
    s07_ddp_update_validation
    p7_gpu_gate("reference", s07_pilot_training_authority, i06_accepted_model_sources,
      i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources,
      i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources,
      i07_training_input_sources, s07_training_geometry_cache, s07_training_sources)
  }, format = "file", resources = controller_gpu_02_resources),
  targets::tar_target(s07_ddp_resume_validation, {
    s07_ddp_reference_validation
    p7_gpu_gate("resume", s07_pilot_training_authority, i06_accepted_model_sources,
      i06_accepted_model_sources, i06_accepted_model_sources, i07_training_input_sources,
      i07_training_input_sources, i07_training_input_sources, i05_validation_query_sources,
      i07_training_input_sources, s07_training_geometry_cache, s07_training_sources)
  }, format = "file", resources = controller_gpu_02_resources),
  targets::tar_target(s07_pilot_training_execution,
    p7_run_production(s07_pilot_training_authority, s07_ddp_resume_validation,
      i06_accepted_model_sources, i06_accepted_model_sources, i06_accepted_model_sources,
      i07_training_input_sources, i07_training_input_sources, i07_training_input_sources,
      i05_validation_query_sources, i07_training_input_sources, s07_training_geometry_cache, s07_training_sources),
    format = "file", resources = controller_gpu_02_resources),
  targets::tar_target(s07_pilot_training_acceptance,
    p7_consolidated_acceptance(s07_pilot_training_authority, s07_pilot_training_execution,
      s07_training_geometry_cache, c(s07_ddp_initialization_validation, s07_ddp_update_validation,
        s07_ddp_reference_validation, s07_ddp_resume_validation), s07_training_sources),
    format = "file", resources = controller_05_resources)
)
