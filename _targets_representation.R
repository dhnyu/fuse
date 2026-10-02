library(targets)
library(crew)
source("R/s11_representation.R")
# Independent entrypoint/store. No training, inference or historical S11 targets.
# Pilot-measured conservative resource setting: 1 worker x 1 internal thread.
workers <- as.integer(Sys.getenv("FUSE_S11_WORKERS", "1"))
stopifnot(workers == 1L, workers <= parallel::detectCores())
controller_05 <- crew_controller_local(name = "controller_05", workers = workers)
tar_option_set(packages = c("jsonlite", "digest"), controller = controller_05,
  error = "stop", memory = "transient", garbage_collection = TRUE)
s11_cpu <- tar_resources(crew = tar_resources_crew(controller = "controller_05"))
source("targets/s11_representation.R")
list_s11_representation
