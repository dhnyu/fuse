p11_existing_sources <- function(paths) {
  paths <- unname(paths)
  missing <- paths[!file.exists(paths)]
  if (length(missing)) stop("P11 tracked source missing: ", missing[[1L]], call. = FALSE)
  normalizePath(paths, mustWork = TRUE)
}

p11_shapefile_sources <- function(path) {
  stem <- tools::file_path_sans_ext(path)
  candidates <- paste0(stem, c(".shp", ".shx", ".dbf", ".prj", ".cpg"))
  p11_existing_sources(candidates[file.exists(candidates)])
}

p11_yaml_pointer_artifact <- function(path, field) {
  value <- yaml::read_yaml(path)[[field]]
  if (!is.character(value) || length(value) != 1L) {
    stop("P11 pointer field mismatch: ", basename(path), "/", field, call. = FALSE)
  }
  value
}

p11_diagnostic_source_files <- function() {
  files <- c(
    "config/p11_diagnostic_probe_matrix.yml",
    "config/p11_ridge_evaluation_acceptance.yml",
    "config/p11_spatial_readiness_acceptance.yml",
    "config/p11_target_transformation_methodology.json",
    "config/p11_downstream_dataset.yml"
  )
  artifacts <- c(
    p11_yaml_pointer_artifact(files[[2L]], "acceptance_path"),
    p11_yaml_pointer_artifact(files[[3L]], "acceptance_path"),
    p11_yaml_pointer_artifact(files[[5L]], "acceptance_path")
  )
  p11_existing_sources(c(files, artifacts))
}

p11_living_source_files <- function() {
  config <- "config/p11_downstream_preprocessing_v2.yml"
  cfg <- yaml::read_yaml(config)
  files <- c(
    config, cfg$dissertation_authority, cfg$methodology_decision,
    cfg$supersedes_execution_contract,
    "config/p11_living_population_source_contract_v2.json"
  )
  external <- c(
    cfg$previous_dataset_root, cfg$scene_index, unname(unlist(cfg$sources)),
    file.path(cfg$output_root, cfg$accepted_output, "downstream_dataset_acceptance.json")
  )
  p11_existing_sources(c(files, p11_shapefile_sources(cfg$district_boundary), external))
}

p11_dataset_source_files <- function() {
  config <- "config/p11_downstream_preprocessing.yml"
  cfg <- yaml::read_yaml(config)
  files <- c(config, cfg$methodology_decision, unname(unlist(cfg$contracts)))
  p11_existing_sources(c(files, cfg$scene_index, unname(unlist(cfg$sources))))
}

p11_ridge_source_files <- function() {
  config <- "config/p11_ridge_evaluation.yml"
  cfg <- yaml::read_yaml(config)
  files <- c(config, cfg$readiness_pointer, cfg$transformation_methodology,
             cfg$downstream_dataset_pointer)
  artifacts <- c(
    p11_yaml_pointer_artifact(cfg$readiness_pointer, "acceptance_path"),
    p11_yaml_pointer_artifact(cfg$downstream_dataset_pointer, "acceptance_path")
  )
  p11_existing_sources(c(files, artifacts))
}

p11_readiness_source_files <- function() {
  config <- "config/p11_spatial_readiness.yml"
  cfg <- yaml::read_yaml(config)
  files <- c(config, cfg$dissertation_authority, cfg$transformation_methodology,
             cfg$downstream_dataset, cfg$p10_contract)
  external <- c(cfg$scene_index,
                p11_yaml_pointer_artifact(cfg$downstream_dataset, "acceptance_path"))
  p11_existing_sources(c(files, p11_shapefile_sources(cfg$district_boundary), external))
}

p11_source_file <- function(sources, basename_required) {
  selected <- sources[basename(sources) == basename_required]
  if (length(selected) != 1L) stop("P11 source selection mismatch: ", basename_required, call. = FALSE)
  selected[[1L]]
}

p11_output_paths <- function(result) {
  paths <- result$paths
  if (!is.character(paths) || !length(paths)) stop("P11 execution returned no tracked paths", call. = FALSE)
  p11_existing_sources(paths)
}
