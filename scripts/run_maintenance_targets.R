#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(targets))

args <- commandArgs(trailingOnly = TRUE)
unknown_options <- args[grepl("^--", args)]
if (length(unknown_options)) stop("Unknown option: ", paste(unknown_options, collapse = ", "), call. = FALSE)

config <- yaml::read_yaml("config/research_paths.yml")
store <- config$targets$maintenance_store
if (length(args)) {
  selection <- rlang::expr(tidyselect::any_of(!!args))
  rlang::inject(targets::tar_make(
    names = !!selection,
    script = "_targets_maintenance.R",
    store = !!store,
    reporter = "timestamp",
    use_crew = TRUE
  ))
} else {
  targets::tar_make(
    script = "_targets_maintenance.R", store = store,
    reporter = "timestamp", use_crew = TRUE
  )
}
