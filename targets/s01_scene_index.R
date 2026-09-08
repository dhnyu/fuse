controller_05_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_05")
)
controller_40_resources <- targets::tar_resources(
  crew = targets::tar_resources_crew(controller = "controller_40")
)

list_s01_scene_index <- list(
  targets::tar_target(
    name = s01_scene_sources,
    command = normalizePath(p1_scene_index_contract_paths(), mustWork = TRUE),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = s01_study_sources,
    command = c(normalizePath(research_config_paths(), mustWork = TRUE),
                normalizePath(research_implementation_paths(), mustWork = TRUE)),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = s01_offgrid_scene_source,
    command = publish_current_off_grid_source(
      study_data_inputs = i01_seoul_spatial_sources,
      scene_methodology_contract = s00_scene_methodology_contract,
      reduced_methodology_authority = s00_methodology_authority,
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
      reduced_methodology_authority = s00_methodology_authority,
      p1_scene_index_contract_files = s01_scene_sources,
      workers = 1L, threads = 1L
    ),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    name = s01_scene_index,
    command = build_reduced_scene_index_bundle(
      study_data_inputs = i01_seoul_spatial_sources,
      accepted_off_grid_source = s01_offgrid_scene_source,
      study_data_inventory = s01_study_inventory_validation,
      scene_methodology_contract = s00_scene_methodology_contract,
      reduced_methodology_authority = s00_methodology_authority,
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
      reduced_methodology_authority = s00_methodology_authority,
      p1_scene_index_contract_files = s01_scene_sources
    ),
    format = "file", resources = controller_05_resources
  )
)
