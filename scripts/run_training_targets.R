#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (!identical(args, "campaign")) stop("usage: scripts/run_training_targets.R campaign", call. = FALSE)
store <- Sys.getenv("FUSE_S09_TARGETS_STORE", unset = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-training-s09")
targets::tar_make(names = s09_campaign_acceptance, script = "_targets_training.R", store = store)
