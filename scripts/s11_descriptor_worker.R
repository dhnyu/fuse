#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3L)
arrow::set_cpu_count(1L)
data.table::setDTthreads(1L)
source("R/scene_descriptors.R")
source("R/s11_p3_reader.R")
result <- s11_read_selected_p3(args[[1]], args[[2]])
jsonlite::write_json(result, args[[3]], auto_unbox = TRUE, null = "null", na = "null", digits = NA)
