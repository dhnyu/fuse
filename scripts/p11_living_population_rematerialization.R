#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
config <- if (length(args)) args[[1L]] else "config/p11_downstream_preprocessing_v2.yml"
source("R/p11_downstream_preprocessing.R")
source("R/p11_living_population_rematerialization.R")
result <- p11_execute_living_partial_support_rematerialization(config)
jsonlite::write_json(result, stdout(), auto_unbox = TRUE, pretty = TRUE,
                     null = "null", na = "null", digits = NA)
