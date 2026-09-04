library(targets)

tar_option_set(
  packages = c("arrow", "data.table", "digest", "exactextractr", "jsonlite", "openssl", "parallel", "sf", "terra", "yaml"),
  error = "stop",
  garbage_collection = TRUE,
  memory = "transient"
)

source("R/research_contracts.R")
source("R/research_scene_index_reduced.R")
source("R/p11_downstream_preprocessing.R")
source("targets/p11_downstream_preprocessing.R")

list_p11_downstream_preprocessing
