library(targets)
library(crew)
source("R/evaluation_targets.R")

# S11 is intentionally fail-closed; this controller declaration grants no execution.
controller_05 <- crew::crew_controller_local(name = "controller_05", workers = 1L)
tar_option_set(packages = c("jsonlite"), error = "stop", garbage_collection = TRUE, memory = "transient",
  controller = controller_05,
  resources = tar_resources(crew = tar_resources_crew(controller = "controller_05")))
source("targets/s11_evaluation.R")

list_s11 <- c(list(
  tar_target(s11_evaluation_sources,
    c("python/evaluation.py", "python/evaluation_inputs.py",
      "python/requirements-evaluation.txt", "scripts/evaluate_scene_encoder.py",
      "scripts/prepare_evaluation_inputs.py", "config/evaluation.yml",
      "config/schemas/evaluation.schema.json"),
    format = "file")
), list_s11_evaluation_targets)

list_s11
