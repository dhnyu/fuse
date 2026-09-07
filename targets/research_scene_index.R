controller_05_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05")
)
controller_40_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_40")
)

list_research_scene_index <- list(
  targets::tar_target(
    name = s01_scene_sources,
    command = normalizePath(p1_scene_index_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = runtime_mirror_contract_files,
    command = normalizePath(runtime_mirror_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = prototype_runtime_inputs,
    command = validate_runtime_mirror(runtime_mirror_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = s01_study_sources,
    command = c(normalizePath(research_config_paths(), mustWork = TRUE),
                normalizePath(research_implementation_paths(), mustWork = TRUE)),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = i01_offgrid_scene_sources,
    command = verify_accepted_off_grid_source(
      study_data_inputs = i01_seoul_spatial_sources,
      scene_methodology_contract = scene_methodology_contract,
      p1_scene_index_contract_files = s01_scene_sources,
      workers = 1L, threads = 1L
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = i01_seoul_spatial_sources,
    command = study_input_files(select_study_source_files(s01_study_sources, "config")),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = s01_study_inventory_validation,
    command = build_reduced_study_data_inventory(
      study_data_inputs = i01_seoul_spatial_sources,
      reduced_methodology_authority = reduced_methodology_authority,
      p1_scene_index_contract_files = s01_scene_sources,
      workers = 1L, threads = 1L
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = methodology_contract,
    command = build_methodology_contract(
      study_data_inputs = i01_seoul_spatial_sources,
      study_data_inventory = s01_study_inventory_validation,
      accepted_off_grid_source = i01_offgrid_scene_sources,
      research_config_files = select_study_source_files(s01_study_sources, "config"),
      research_implementation_files = select_study_source_files(s01_study_sources, "implementation"),
      workers = 1L, threads = 1L
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = s01_scene_index,
    command = build_reduced_scene_index_bundle(
      study_data_inputs = i01_seoul_spatial_sources,
      accepted_off_grid_source = i01_offgrid_scene_sources,
      study_data_inventory = s01_study_inventory_validation,
      scene_methodology_contract = scene_methodology_contract,
      reduced_methodology_authority = reduced_methodology_authority,
      contract_files = s01_scene_sources,
      workers = 1L, threads = 1L
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = s01_scene_acceptance,
    command = accept_reduced_scene_index(
      spatial_scene_index = s01_scene_index,
      reduced_scene_index_plan = s01_scene_index,
      study_data_inventory = s01_study_inventory_validation,
      reduced_methodology_authority = reduced_methodology_authority,
      p1_scene_index_contract_files = s01_scene_sources
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = s01_pilot_scene_index,
    command = build_reduced_prototype_scene_selection(
      scene_index_acceptance = s01_scene_acceptance,
      spatial_scene_index = s01_scene_index,
      p1_scene_index_contract_files = s01_scene_sources,
      workers = 1L, threads = 1L
    ),
    format = "file", resources = controller_05_resources
  )
)
