library(targets)

tar_option_set(packages = c("yaml"), storage = "worker")
source("R/p11_target_sources.R")
source("targets/p11_spatial_readiness.R")

list_p11_spatial_readiness
