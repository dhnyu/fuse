#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
  library(jsonlite)
  library(sf)
  library(targets)
})

invisible(source("_targets.R", local = globalenv()))
args <- commandArgs(trailingOnly = TRUE)
output_path <- if (length(args)) args[[1L]] else tempfile(fileext = ".json")
store <- yaml::read_yaml("config/research_paths.yml")$targets$research_store
plan <- tar_read(prototype_observation_plan, store = store)
vector_paths <- unname(tar_read(prototype_vector_observation_shard, store = store))
relation_paths <- unname(tar_read(prototype_relation_shard, store = store))
study_inputs <- tar_read(study_data_inputs, store = store)
config <- load_relation_config(relation_contract_paths())

scene_ids <- c(
  "scn_312d0408dbb0addca127f9d9",
  "scn_30b22ad87dc370ddb2cae951",
  "scn_16d190ee116931ae54df3f52"
)
vector_by_branch <- setNames(vector_paths, vapply(vector_paths, function(paths) {
  fromJSON(paths[[4L]])$branch_id
}, character(1L)))
relation_by_branch <- setNames(relation_paths, vapply(relation_paths, function(paths) {
  fromJSON(paths[[4L]])$branch_id
}, character(1L)))

equal_nullable <- function(left, right) {
  (is.na(left) & is.na(right)) | (!is.na(left) & !is.na(right) & left == right)
}
results <- lapply(scene_ids, function(requested_scene_id) {
  spec <- plan[[which(vapply(plan, function(value) requested_scene_id %in% unlist(value$scene_ids), logical(1L)))]]
  vector <- read_i10_branch_context(spec, vector_by_branch[[spec$branch_id]])
  observations <- lapply(vector$files, read_standard_geoparquet)
  entities <- relation_entity_table(observations)
  scene <- relation_scene_sf(entities[scene_id == requested_scene_id])
  scene_spec <- spec$scenes[[which(vapply(spec$scenes, `[[`, character(1L), "scene_id") == requested_scene_id)]]
  node_positions <- read_relation_node_positions(relation_road_path(study_inputs), c(scene$F_NODE, scene$T_NODE))
  optimized <- as.data.table(read_parquet(relation_by_branch[[spec$branch_id]][[1L]]))[scene_id == requested_scene_id]
  relation_dataset_id <- unique(optimized$relation_dataset_id)
  reference <- reference_scene_relations(scene, node_positions, scene_spec, spec, relation_dataset_id, config)
  comparison <- compare_relation_reference(optimized, reference)
  key <- c("scene_id", "source_local_entity_id", "destination_local_entity_id")
  evidence <- merge(
    optimized[, .(scene_id, source_local_entity_id, destination_local_entity_id,
                  host_building_local_entity_id, shared_original_node_id, sn_source_rank, sn_destination_rank)],
    reference[, .(scene_id, source_local_entity_id, destination_local_entity_id,
                  reference_host = host_building_local_entity_id,
                  reference_shared_node = shared_original_node_id,
                  reference_source_rank = sn_source_rank, reference_destination_rank = sn_destination_rank)],
    by = key, all = TRUE
  )
  evidence_mismatch <- sum(!equal_nullable(evidence$host_building_local_entity_id, evidence$reference_host)) +
    sum(!equal_nullable(evidence$shared_original_node_id, evidence$reference_shared_node)) +
    sum(!equal_nullable(evidence$sn_source_rank, evidence$reference_source_rank)) +
    sum(!equal_nullable(evidence$sn_destination_rank, evidence$reference_destination_rank))
  list(
    scene_id = requested_scene_id, branch_id = spec$branch_id, node_count = nrow(scene),
    optimized_edge_count = nrow(optimized), reference_edge_count = nrow(reference),
    false_negative_count = comparison$false_negative_count,
    false_positive_count = comparison$false_positive_count,
    mask_mismatch_count = comparison$mask_mismatch_count,
    distance_mismatch_count = comparison$distance_mismatch_count,
    maximum_distance_error_m = comparison$maximum_distance_error_m,
    evidence_mismatch_count = evidence_mismatch,
    status = if (comparison$status == "PASS" && evidence_mismatch == 0L) "PASS" else "FAIL"
  )
})

result <- list(
  status = if (all(vapply(results, `[[`, character(1L), "status") == "PASS")) "PASS" else "FAIL",
  distance_tolerance_m = 1e-9, scenes = results
)
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
write_json(result, output_path, auto_unbox = TRUE, pretty = TRUE, digits = NA)
cat(toJSON(result, auto_unbox = TRUE, pretty = TRUE, digits = NA), "\n")
if (result$status != "PASS") quit(status = 1L)
