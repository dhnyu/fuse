#!/usr/bin/env Rscript

suppressPackageStartupMessages(library(targets))

source("R/config_paths.R")
source("R/io_spatial.R")
source("R/research_contracts.R")
source("R/research_membership.R")
source("R/research_observation.R")

store <- yaml::read_yaml("config/research_paths.yml")$targets$research_store
plan <- targets::tar_read(prototype_observation_plan, store = store)
config <- load_observation_config(observation_contract_paths())
result <- benchmark_observation_concurrency(plan, config, c(5L, 10L), repetitions = 2L)
output <- file.path(tempdir(), "prototype_observation_concurrency_pilot.json")
write_json_file(result, output)
cat(output, "\n")
for (run in result$runs) {
  cat(sprintf(
    "workers=%d tasks=%d wall=%.3f rss_kb=%.0f read_bytes=%.0f write_bytes=%.0f iowait_ticks=%.0f errors=%d\n",
    run$workers, run$task_count, run$wall_time_seconds, run$maximum_worker_rss_kb,
    run$read_bytes, run$write_bytes, run$iowait_ticks, run$errors
  ))
}
