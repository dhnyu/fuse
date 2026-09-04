library(targets)

tar_option_set(
  packages = c("arrow", "data.table", "DBI", "digest", "duckdb", "jsonlite",
               "openssl", "sf", "yaml"),
  storage = "worker"
)

source("R/p11_downstream_preprocessing.R")
source("R/p11_living_population_rematerialization.R")
source("targets/p11_living_population_rematerialization.R")

list_p11_living_population_rematerialization
