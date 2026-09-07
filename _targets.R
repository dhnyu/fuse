library(targets)
library(crew)

# Research pipeline only. Seoul study-data maintenance is declared in
# _targets_maintenance.R and uses a separate targets store.
source("R/current_source_registry.R", local = TRUE)
targets::tar_source(current_research_source_files())

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
  workers = fuse_controller_worker_count("FUSE_CONTROLLER_20_WORKERS", 20L),
  seconds_timeout = 3600
)
controller_40 <- crew::crew_controller_local(
  name = "controller_40",
  workers = fuse_controller_worker_count("FUSE_CONTROLLER_40_WORKERS", 40L),
  seconds_timeout = 3600,
  crashes_max = fuse_controller_crash_limit("FUSE_CONTROLLER_40_CRASHES_MAX", 0L)
)
controller_gpu_02 <- crew::crew_controller_local(
  name = "controller_gpu_02",
  workers = 2L
)

targets::tar_option_set(
  packages = c("arrow", "data.table", "digest", "jsonlite", "sf", "sfarrow", "terra", "yaml"),
  controller = crew::crew_controller_group(
    controller_05,
    controller_10,
    controller_20,
    controller_40,
    controller_gpu_02
  ),
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient",
  storage = "worker"
)

targets::tar_source(current_target_source_files())

c(
  list_s00_methodology,
  list_s01_scene_index,
  list_s02_spatial_observations,
  list_s03_scene_cache,
  list_s04_augmentation,
  list_s05_fixed_queries,
  list_s06_model_inputs,
  list_s08_experiment_plan
)
