args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("Usage: finalize_p2_relation_tiered.R MANIFEST", call. = FALSE)
source("_targets.R")
cat(p2_finalize_relation_tiered(args[[1L]]), "\n")
