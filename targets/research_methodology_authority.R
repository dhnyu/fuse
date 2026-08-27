p0_authority_spec <- load_p0_authority_spec()
p0_authority_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05")
)

list_research_methodology_authority <- list(
  targets::tar_target(
    reduced_methodology_source_files,
    build_reduced_methodology_source_files(p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    reduced_methodology_git_state,
    build_reduced_methodology_git_state(reduced_methodology_source_files, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    reduced_methodology_source_set,
    build_reduced_methodology_source_set(
      reduced_methodology_source_files,
      reduced_methodology_git_state,
      p0_authority_spec
    ),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    reduced_methodology_conflict_gate,
    build_reduced_methodology_conflict_gate(reduced_methodology_source_set, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    scene_methodology_contract,
    build_p0_module_contract("scene", reduced_methodology_source_set, reduced_methodology_conflict_gate, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    base_spatial_methodology_contract,
    build_p0_module_contract("base_spatial", reduced_methodology_source_set, reduced_methodology_conflict_gate, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    original_cache_methodology_contract,
    build_p0_module_contract("original_cache", reduced_methodology_source_set, reduced_methodology_conflict_gate, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    augmentation_methodology_contract,
    build_p0_module_contract("augmentation", reduced_methodology_source_set, reduced_methodology_conflict_gate, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    model_methodology_contract,
    build_p0_module_contract("model", reduced_methodology_source_set, reduced_methodology_conflict_gate, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    training_methodology_contract,
    build_p0_module_contract("training", reduced_methodology_source_set, reduced_methodology_conflict_gate, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    evaluation_methodology_contract,
    build_p0_module_contract("evaluation", reduced_methodology_source_set, reduced_methodology_conflict_gate, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    downstream_methodology_contract,
    build_p0_module_contract("downstream", reduced_methodology_source_set, reduced_methodology_conflict_gate, p0_authority_spec),
    format = "file",
    resources = p0_authority_resources
  ),
  targets::tar_target(
    reduced_methodology_authority,
    build_reduced_methodology_authority(
      reduced_methodology_git_state,
      reduced_methodology_source_set,
      reduced_methodology_conflict_gate,
      c(
        scene_methodology_contract,
        base_spatial_methodology_contract,
        original_cache_methodology_contract,
        augmentation_methodology_contract,
        model_methodology_contract,
        training_methodology_contract,
        evaluation_methodology_contract,
        downstream_methodology_contract
      ),
      p0_authority_spec
    ),
    format = "file",
    resources = p0_authority_resources
  )
)
