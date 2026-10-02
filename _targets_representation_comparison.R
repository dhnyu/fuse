library(targets)
library(crew)
source("R/s12_representation.R")
# Separate store/entrypoint. Worker count is validated against the pilot receipt.
workers <- as.integer(Sys.getenv("FUSE_S12_WORKERS", "4"))
stopifnot(workers %in% c(4L, 8L), workers <= 40L, workers <= parallel::detectCores())
controller_05 <- crew_controller_local(name = "controller_05", workers = workers)
tar_option_set(packages = c("jsonlite", "digest"), controller = controller_05,
  error = "stop", memory = "transient", garbage_collection = TRUE)
s12_cpu <- tar_resources(crew = tar_resources_crew(controller = "controller_05"))
source("targets/s12_representation.R")
list_s12_representation
