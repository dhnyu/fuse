library(targets)

tar_option_set(packages = c("yaml"), storage = "worker")
source("R/downstream_sources.R")
source("targets/s11_readiness.R")

list_p11_spatial_readiness
