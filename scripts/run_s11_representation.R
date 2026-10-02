#!/usr/bin/env Rscript
# Sole operator full-run wrapper: exact external store; never the research store.
# This script is implemented in the no-full-execution phase, not executed there.
stopifnot(length(commandArgs(trailingOnly = TRUE)) == 0L)
execution <- jsonlite::read_json("config/s11_execution.json")
if (!identical(Sys.getenv(execution$authorization_env), execution$authorization_value))
  stop("S11 full execution is not authorized")
receipt <- Sys.getenv(execution$pilot_receipt_env)
if (!nzchar(receipt) || !file.exists(receipt)) stop("S11 current pilot receipt required")
targets::tar_make(names = s11_scientific_acceptance,
  script = "_targets_representation.R", store = execution$store)
