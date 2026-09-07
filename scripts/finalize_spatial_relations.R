args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("Usage: finalize_spatial_relations.R MANIFEST", call. = FALSE)
source("_targets.R")
cat(p2_finalize_relation_tiered(args[[1L]]), "\n")
