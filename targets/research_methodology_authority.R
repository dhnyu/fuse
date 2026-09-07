p0_authority_spec <- load_p0_authority_spec()
p0_authority_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05")
)

list_research_methodology_authority <- list(
  targets::tar_target(
    s00_methodology_sources,
    build_reduced_methodology_source_files(p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_methodology_source_authority,
    p0_build_source_authority(s00_methodology_sources, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_scene_methodology_contract,
    build_p0_module_contract("scene", s00_methodology_source_authority, s00_methodology_source_authority, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_spatial_methodology_contract,
    build_p0_module_contract("base_spatial", s00_methodology_source_authority, s00_methodology_source_authority, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_cache_methodology_contract,
    build_p0_module_contract("original_cache", s00_methodology_source_authority, s00_methodology_source_authority, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_augmentation_methodology_contract,
    build_p0_module_contract("augmentation", s00_methodology_source_authority, s00_methodology_source_authority, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_model_methodology_contract,
    build_p0_module_contract("model", s00_methodology_source_authority, s00_methodology_source_authority, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_evaluation_methodology_contract,
    build_p0_module_contract("evaluation", s00_methodology_source_authority, s00_methodology_source_authority, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_hyperparameter_methodology_contract,
    build_p0_module_contract("hyperparameter_study", s00_methodology_source_authority, s00_methodology_source_authority, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_comparison_methodology_contract,
    build_p0_module_contract("comparison", s00_methodology_source_authority, s00_methodology_source_authority, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    s00_methodology_authority,
    p0_build_final_authority(
      s00_methodology_source_authority,
      c(
        s00_scene_methodology_contract,
        s00_spatial_methodology_contract,
        s00_cache_methodology_contract,
        s00_augmentation_methodology_contract,
        s00_model_methodology_contract,
        s00_evaluation_methodology_contract,
        s00_hyperparameter_methodology_contract,
        s00_comparison_methodology_contract
      ),
      p0_authority_spec
    ),
    format = "file",
    resources = p0_authority_resources
  )
)
