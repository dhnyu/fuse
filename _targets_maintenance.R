library(targets)
library(crew)

maintenance_function_files <- c(
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
targets::tar_source(maintenance_function_files)

controller_20 <- crew::crew_controller_local(
  name = "controller_20",
  workers = fuse_controller_worker_count("FUSE_CONTROLLER_20_WORKERS", 20L)
)

targets::tar_option_set(
  packages = c("data.table", "digest", "future", "future.apply", "jsonlite", "parallelly", "sf", "yaml"),
  controller = controller_20,
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient",
  storage = "worker"
)

targets::tar_source("targets/seoul_data_preprocess.R")

list_seoul_data_preprocess
