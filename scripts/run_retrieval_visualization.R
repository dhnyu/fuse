#!/usr/bin/env Rscript
# Full inference requires a separate operator authorization; never starts S09/S11.
args <- commandArgs(trailingOnly = TRUE)
if (!identical(args, "--authorize-full-inference")) {
  stop("Use --authorize-full-inference only after explicit full S10 authorization.", call. = FALSE)
}
cfg <- yaml::read_yaml("config/retrieval_visualization.yml")
Sys.setenv(FUSE_S10_FULL_AUTHORIZED = "1", FUSE_S10_THREADS = as.character(cfg$threads),
           OMP_NUM_THREADS = as.character(cfg$threads), OPENBLAS_NUM_THREADS = as.character(cfg$threads),
           MKL_NUM_THREADS = as.character(cfg$threads), CUBLAS_WORKSPACE_CONFIG = ":4096:8")
targets::tar_make(s10_retrieval_visualization_acceptance,
  script = "_targets_retrieval_visualization.R", store = cfg$store)
