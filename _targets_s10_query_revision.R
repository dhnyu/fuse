library(targets)
library(crew)
source("R/s10_query_revision.R")
# Registered CPU controller role; the I/O pilot supports one worker, one thread.
workers <- as.integer(Sys.getenv("FUSE_S10_REVISION_WORKERS", "1"))
stopifnot(workers == 1L, workers <= parallel::detectCores())
controller_05 <- crew_controller_local(name = "controller_05", workers = workers)
tar_option_set(packages = "jsonlite", controller = controller_05, error = "stop",
  memory = "transient", garbage_collection = TRUE)
s10_revision_cpu <- tar_resources(crew = tar_resources_crew(controller = "controller_05"))
source("targets/s10_query_revision.R")
list_s10_query_revision
