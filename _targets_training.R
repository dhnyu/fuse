library(targets)

tar_option_set(
  packages = c("jsonlite", "yaml"),
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient"
)

source("R/training_targets.R")
source("targets/s09_training.R")

list_s09_training
