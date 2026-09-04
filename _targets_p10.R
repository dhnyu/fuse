library(targets)
source("R/p10_evaluation_targets.R")

tar_option_set(packages = c("jsonlite"), error = "stop", garbage_collection = TRUE, memory = "transient")
source("targets/p10_targets.R")

list_p10 <- c(list(
  tar_target(p10_source_files,
    c("python/p10_evaluation.py", "python/p10_prepared_input.py",
      "python/requirements-p10.txt", "scripts/p10_evaluation.py",
      "scripts/p10_prepared_input.py", "config/p10_evaluation.yml",
      "config/schemas/p10_evaluation.schema.json"),
    format = "file"),
  tar_target(p10_source_gate, { p10_source_files; TRUE })
), list_p10_targets)

list_p10
