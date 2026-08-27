controller_05_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05")
)
controller_40_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_40")
)

list_research_scene_index <- list(
  targets::tar_target(
    name = p1_scene_index_contract_files,
    command = normalizePath(p1_scene_index_contract_paths(), mustWork = TRUE),
    format = "file",
    resources = controller_05_resources
  ),
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
    command = verify_accepted_off_grid_source(
      study_data_inputs = study_data_inputs,
      scene_methodology_contract = scene_methodology_contract,
      p1_scene_index_contract_files = p1_scene_index_contract_files,
      workers = 1L,
      threads = 1L
    ),
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
    command = build_reduced_study_data_inventory(
      study_data_inputs = study_data_inputs,
      reduced_methodology_authority = reduced_methodology_authority,
      p1_scene_index_contract_files = p1_scene_index_contract_files,
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
    name = reduced_scene_index_plan,
    command = build_reduced_scene_index_plan(
      study_data_inventory = study_data_inventory,
      accepted_off_grid_source = accepted_off_grid_source,
      scene_methodology_contract = scene_methodology_contract,
      reduced_methodology_authority = reduced_methodology_authority,
      p1_scene_index_contract_files = p1_scene_index_contract_files
    ),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = spatial_scene_index,
    command = build_reduced_spatial_scene_index(
      study_data_inputs = study_data_inputs,
      accepted_off_grid_source = accepted_off_grid_source,
      reduced_scene_index_plan = reduced_scene_index_plan,
      scene_methodology_contract = scene_methodology_contract,
      reduced_methodology_authority = reduced_methodology_authority,
      p1_scene_index_contract_files = p1_scene_index_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = scene_index_acceptance,
    command = accept_reduced_scene_index(
      spatial_scene_index = spatial_scene_index,
      reduced_scene_index_plan = reduced_scene_index_plan,
      study_data_inventory = study_data_inventory,
      reduced_methodology_authority = reduced_methodology_authority,
      p1_scene_index_contract_files = p1_scene_index_contract_files
    ),
    format = "file",
    resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_scene_selection,
    command = build_reduced_prototype_scene_selection(
      scene_index_acceptance = scene_index_acceptance,
      spatial_scene_index = spatial_scene_index,
      p1_scene_index_contract_files = p1_scene_index_contract_files,
      workers = 1L,
      threads = 1L
    ),
    format = "file",
    resources = controller_05_resources
  )
)
