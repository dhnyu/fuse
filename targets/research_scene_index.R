controller_05_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05")
)
controller_40_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_40")
)

list_research_scene_index <- list(
  targets::tar_target(
    name = runtime_mirror_contract_files,
    command = normalizePath(runtime_mirror_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_runtime_inputs,
    command = validate_runtime_mirror(runtime_mirror_contract_files),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = research_config_files,
    command = normalizePath(research_config_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = accepted_off_grid_source,
    command = accepted_off_grid_source_files(research_config_files),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = research_implementation_files,
    command = normalizePath(research_implementation_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = study_data_inputs,
    command = study_input_files(research_config_files),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = study_data_inventory,
    command = build_study_data_inventory(
      study_data_inputs = study_data_inputs,
      research_config_files = research_config_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = methodology_contract,
    command = build_methodology_contract(
      study_data_inputs = study_data_inputs,
      study_data_inventory = study_data_inventory,
      accepted_off_grid_source = accepted_off_grid_source,
      research_config_files = research_config_files,
      research_implementation_files = research_implementation_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = spatial_scene_index,
    command = build_spatial_scene_index(
      study_data_inputs = study_data_inputs,
      accepted_off_grid_source = accepted_off_grid_source,
      prototype_runtime_inputs = prototype_runtime_inputs,
      methodology_contract = methodology_contract,
      research_config_files = research_config_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_scene_selection,
    command = build_prototype_scene_selection(
      spatial_scene_index = spatial_scene_index,
      study_data_inputs = study_data_inputs,
      prototype_runtime_inputs = prototype_runtime_inputs,
      methodology_contract = methodology_contract,
      research_config_files = research_config_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  )
)
