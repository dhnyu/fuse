library(targets)

tar_option_set(
  packages = c("arrow", "data.table", "digest", "exactextractr", "jsonlite", "openssl", "parallel", "sf", "terra", "yaml"),
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient"
)

source("R/contracts.R")
source("R/scene_index.R")
source("R/downstream_preprocessing.R")
source("R/downstream_sources.R")
source("targets/s11_downstream.R")

list_p11_downstream_preprocessing
