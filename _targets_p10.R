library(targets)
source("R/p10_evaluation_targets.R")

tar_option_set(packages = c("jsonlite"), error = "stop", garbage_collection = TRUE, memory = "transient")
source("targets/p10_targets.R")

list_p10 <- c(list(
  tar_target(s10_evaluation_sources,
    c("python/p10_evaluation.py", "python/p10_prepared_input.py",
      "python/requirements-p10.txt", "scripts/p10_evaluation.py",
      "scripts/p10_prepared_input.py", "config/p10_evaluation.yml",
      "config/schemas/p10_evaluation.schema.json"),
    format = "file")
), list_p10_targets)

list_p10
