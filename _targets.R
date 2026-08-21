library(targets)
library(crew)

# Research pipeline only. Seoul study-data maintenance is declared in
# _targets_maintenance.R and uses a separate targets store.
research_function_files <- c(
  "R/config_paths.R",
  "R/io_spatial.R",
  "R/research_contracts.R",
  "R/research_scene_index.R",
  "R/research_prototype.R",
  "R/research_membership.R",
  "R/research_observation.R",
  "R/research_raster_observation.R",
  "R/research_relation.R"
)
targets::tar_source(research_function_files)

controller_05 <- crew::crew_controller_local(
  name = "controller_05",
  workers = fuse_controller_worker_count("FUSE_CONTROLLER_05_WORKERS", 5L)
)
controller_10 <- crew::crew_controller_local(
  name = "controller_10",
  workers = fuse_controller_worker_count("FUSE_CONTROLLER_10_WORKERS", 10L)
)
controller_20 <- crew::crew_controller_local(
  name = "controller_20",
  workers = fuse_controller_worker_count("FUSE_CONTROLLER_20_WORKERS", 20L)
)
controller_40 <- crew::crew_controller_local(
  name = "controller_40",
  workers = fuse_controller_worker_count("FUSE_CONTROLLER_40_WORKERS", 40L)
)

targets::tar_option_set(
  packages = c("arrow", "data.table", "digest", "jsonlite", "sf", "sfarrow", "terra", "yaml"),
  controller = crew::crew_controller_group(
    controller_05,
    controller_10,
    controller_20,
    controller_40
  ),
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient",
  storage = "worker"
)

targets::tar_source("targets/research_scene_index.R")
targets::tar_source("targets/research_membership.R")
targets::tar_source("targets/research_observation.R")
targets::tar_source("targets/research_raster_observation.R")
targets::tar_source("targets/research_relation.R")

c(
  list_research_scene_index,
  list_research_membership,
  list_research_observation,
  list_research_raster_observation,
  list_research_relation
)
