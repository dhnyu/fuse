#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(jsonlite)
  library(targets)
})

invisible(source("_targets.R", local = globalenv()))
args <- commandArgs(trailingOnly = TRUE)
output_path <- if (length(args)) args[[1L]] else tempfile(fileext = ".json")
store <- yaml::read_yaml("config/research_paths.yml")$targets$research_store
branch_id <- "pob_ea34022631583b86c74cd6cc"
plan <- tar_read(prototype_observation_plan, store = store)
vector_paths <- unname(tar_read(prototype_vector_observation_shard, store = store))
relation_paths <- unname(tar_read(prototype_relation_shard, store = store))
study_inputs <- tar_read(study_data_inputs, store = store)

spec <- plan[[which(vapply(plan, `[[`, character(1L), "branch_id") == branch_id)]]
vector <- vector_paths[[which(vapply(vector_paths, function(paths) fromJSON(paths[[4L]])$branch_id, character(1L)) == branch_id)]]
published <- relation_paths[[which(vapply(relation_paths, function(paths) fromJSON(paths[[4L]])$branch_id, character(1L)) == branch_id)]]
before <- vapply(published, sha256_file, character(1L))
started <- Sys.time()
rebuilt <- build_prototype_relation_shard(
  prototype_observation_plan = spec,
  prototype_vector_observation_shard = vector,
  study_data_inputs = study_inputs,
  relation_contract_files = relation_contract_paths(),
  workers = 1L, threads = 1L
)
elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
after <- vapply(published, sha256_file, character(1L))
result <- list(
  status = if (identical(published, rebuilt) && identical(before, after)) "PASS" else "FAIL",
  branch_id = branch_id, direct_rebuild_wall_time_seconds = elapsed,
  paths_identical = identical(published, rebuilt), all_file_sha256_identical = identical(before, after),
  scientific_parquet_sha256 = as.list(setNames(before[1:3], basename(published[1:3])))
)
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
write_json(result, output_path, auto_unbox = TRUE, pretty = TRUE, digits = NA)
cat(toJSON(result, auto_unbox = TRUE, pretty = TRUE, digits = NA), "\n")
if (result$status != "PASS") quit(status = 1L)
