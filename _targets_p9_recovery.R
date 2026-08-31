library(targets)
tar_option_set(packages = c("jsonlite", "digest"), error = "stop")
source("R/research_p9_checkpoint_recovery.R")
source("targets/research_p9_checkpoint_recovery.R")
list_p9_checkpoint_recovery
