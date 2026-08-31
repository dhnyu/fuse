library(targets)

tar_option_set(
  packages = c("jsonlite", "yaml"),
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient"
)

source("R/research_p9_v2_training.R")
source("targets/research_p9_v2_training.R")

list_p9_v2_training
