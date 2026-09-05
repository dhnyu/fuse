library(targets)
library(crew)
source("R/retrieval_gallery_targets.R")

# Each controller owns one orchestration task. Bounded spatial processes and
# one persistent process per GPU are created inside that task, without DDP.
tar_option_set(packages = "jsonlite", error = "stop", memory = "transient",
  garbage_collection = TRUE,
  controller = crew_controller_group(
    crew_controller_local(name = "retrieval_cpu", workers = 1L, seconds_timeout = 86400),
    crew_controller_local(name = "retrieval_gpu_pair", workers = 1L, seconds_timeout = 86400)),
  resources = tar_resources(crew = tar_resources_crew(controller = "retrieval_cpu")))
source("targets/retrieval_gallery_targets.R")
retrieval_gallery_targets
