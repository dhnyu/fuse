library(targets)
library(crew)
source("R/retrieval_visualization.R")

# Same registered controller roles as _targets.R, isolated graph and store.
# Conservative one worker per controller until the full-gallery I/O pilot.
s10_workers <- as.integer(Sys.getenv("FUSE_S10_CPU_WORKERS", "1"))
s10_threads <- as.integer(Sys.getenv("FUSE_S10_THREADS", "1"))
stopifnot(s10_workers >= 1L, s10_threads >= 1L,
          (s10_workers + 1L) * s10_threads <= parallel::detectCores())
controller_05 <- crew::crew_controller_local(name = "controller_05", workers = s10_workers)
controller_gpu_02 <- crew::crew_controller_local(name = "controller_gpu_02", workers = 1L)
tar_option_set(packages = c("jsonlite", "yaml"),
  controller = crew::crew_controller_group(controller_05, controller_gpu_02),
  error = "stop", memory = "transient", garbage_collection = TRUE)
s10_cpu <- tar_resources(crew = tar_resources_crew(controller = "controller_05"))
s10_gpu <- tar_resources(crew = tar_resources_crew(controller = "controller_gpu_02"))
source("targets/s10_retrieval_visualization.R")
list_s10_retrieval_visualization
