current_research_source_files <- function() {
  c(
    "R/config_paths.R", "R/io_spatial.R", "R/contracts.R",
    "R/canonical_config.R", "R/tracked_sources.R",
    "R/methodology_authority.R", "R/current_methodology.R",
    "R/scene_index_support.R", "R/off_grid_source.R", "R/scene_index.R",
    "R/spatial_membership.R", "R/vector_observations.R",
    "R/raster_observations.R", "R/spatial_relations.R",
    "R/spatial_observations.R", "R/spatial_relation_execution.R",
    "R/scene_cache.R", "R/augmentation.R",
    "R/fixed_queries.R", "R/model_inputs.R",
    "R/experiment_plan.R"
  )
}

current_target_source_files <- function() {
  c(
    "targets/s00_methodology.R", "targets/s01_scene_index.R",
    "targets/s02_spatial_observations.R", "targets/s03_scene_cache.R",
    "targets/s04_augmentation.R", "targets/s05_fixed_queries.R",
    "targets/s06_model_inputs.R", "targets/s08_experiment_plan.R"
  )
}

source_current_research_files <- function(root = ".", envir = parent.frame()) {
  files <- file.path(root, current_research_source_files())
  missing <- files[!file.exists(files)]
  if (length(missing)) stop("Missing current research source: ", paste(missing, collapse = ", "), call. = FALSE)
  invisible(lapply(files, sys.source, envir = envir))
}
