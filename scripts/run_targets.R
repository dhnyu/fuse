#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(targets))

args <- commandArgs(trailingOnly = TRUE)
unknown_options <- args[grepl("^--", args)]
if (length(unknown_options)) stop("Unknown option: ", paste(unknown_options, collapse = ", "), call. = FALSE)

if (length(args)) {
  selection <- rlang::expr(tidyselect::any_of(!!args))
  rlang::inject(targets::tar_make(names = !!selection, reporter = "timestamp", use_crew = TRUE))
} else {
  targets::tar_make(reporter = "timestamp", use_crew = TRUE)
}
