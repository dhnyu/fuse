#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
source("R/retrieval_gallery.R")
retrieval_source_helpers()
if (args[[1]] == "sample") {
  retrieval_sample(args[[2]], args[[3]])
} else if (args[[1]] == "spatial") {
  retrieval_spatial_branch(args[[2]])
} else stop("Unknown retrieval gallery action")
