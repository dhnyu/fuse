args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1L) stop("Usage: prepare_p2_relation_tiered.R STORE [ABORTED_JSON]", call. = FALSE)
source("_targets.R")
aborted <- if (length(args) >= 2L && file.exists(args[[2L]])) {
  jsonlite::read_json(args[[2L]], simplifyVector = FALSE)
} else NULL
cat(p2_prepare_relation_tiered_manifest(args[[1L]], aborted), "\n")
