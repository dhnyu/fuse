#!/usr/bin/env Rscript

setwd(normalizePath(file.path(dirname(sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE)[[1L]])), ".."), mustWork = TRUE))
source("_targets.R")
store <- yaml::read_yaml("config/research_paths.yml")$targets$research_store
plans <- targets::tar_read(prototype_membership_plan, store = store)
result <- benchmark_membership_concurrency(plans, concurrency = c(5L, 10L, 20L), repetitions = 5L)
spec <- plans[[1L]]
prototype_root <- dirname(dirname(dirname(dirname(spec$output$directory))))
output_dir <- file.path(prototype_root, "qc", "pilots")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
output <- file.path(output_dir, paste0(kst_stamp(), "_membership_concurrency_pilot.json"))
write_json_atomic(result, output)
cat(normalizePath(output, mustWork = TRUE), "\n")
