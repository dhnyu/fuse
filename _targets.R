library(targets)
library(crew)

# R/preprocessing_utils.R belongs to the separate nationwide canonical ingest
# workflow. Keep methodology functions explicit and deterministically ordered.
methodology_function_files <- c(
  "R/config_paths.R",
  "R/io_spatial.R",
  "R/spatial_boundary.R",
  "R/process_buildings.R",
  "R/process_roads.R",
  "R/process_pois.R",
  "R/process_rasters.R",
  "R/validate_outputs.R",
  "R/output_manifest.R",
  "R/pipeline_seoul_data_preprocess.R"
)
targets::tar_source(methodology_function_files)

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
  packages = c("data.table", "digest", "future", "future.apply", "jsonlite", "parallelly", "sf", "yaml"),
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

targets::tar_source("targets/seoul_data_preprocess.R")

list_seoul_data_preprocess
