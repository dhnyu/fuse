#!/usr/bin/env Rscript
# Metadata-only entry point. Invoked by supplemental/build_locations.py, never targets.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 5L) stop("Usage: build_viewer_locations.R repo gallery sigungu dong output")
Sys.setenv(PROJ_NETWORK = "OFF", OMP_NUM_THREADS = "1", OPENBLAS_NUM_THREADS = "1")
suppressPackageStartupMessages(library(sf))
source(file.path(args[[1]], "R", "viewer_locations.R"))
gallery <- jsonlite::fromJSON(args[[2]])$body$rows
result <- build_location_rows(gallery, args[[3]], args[[4]])
# Original XY is copied from the exact Python-parsed gallery by the publisher,
# avoiding JSON round-trip precision loss through R for identity coordinates.
jsonlite::write_json(result, args[[5]], auto_unbox = TRUE, null = "null", digits = NA)
