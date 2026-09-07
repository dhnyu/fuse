library(targets)
source("R/evaluation_targets.R")

tar_option_set(packages = c("jsonlite"), error = "stop", garbage_collection = TRUE, memory = "transient")
source("targets/s10_evaluation.R")

list_s10 <- c(list(
  tar_target(s10_evaluation_sources,
    c("python/evaluation.py", "python/evaluation_inputs.py",
      "python/requirements-evaluation.txt", "scripts/evaluate_scene_encoder.py",
      "scripts/prepare_evaluation_inputs.py", "config/evaluation.yml",
      "config/schemas/evaluation.schema.json"),
    format = "file")
), list_s10_evaluation_targets)

list_s10
