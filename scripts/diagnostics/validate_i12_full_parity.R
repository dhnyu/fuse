#!/usr/bin/env Rscript

# Read-only comparison of optimized I12 scene results with the accepted relation artifacts.
source("_targets.R")

option <- function(name, default) {
  prefix <- paste0("--", name, "=")
  value <- grep(paste0("^", prefix), commandArgs(trailingOnly = TRUE), value = TRUE)
  if (!length(value)) default else sub(prefix, "", value[[1L]], fixed = TRUE)
}

output_path <- option("output", "/tmp/fuse_i12_full_parity.json")
workers <- as.integer(option("workers", "13"))
plans <- targets::tar_read(prototype_observation_plan)
vectors <- targets::tar_read(prototype_vector_observation_shard)
accepted_relations <- targets::tar_read(prototype_relation_shard)
runtime <- targets::tar_read(prototype_runtime_inputs)
config <- load_relation_config(targets::tar_read(relation_contract_files))
road_path <- runtime_mirror_path(runtime, "road")

scientific_columns <- c(
  "scene_id", "scene_footprint_id", "split",
  "source_local_entity_id", "destination_local_entity_id",
  "source_entity_type", "destination_entity_type", "relation_mask",
  "has_sn", "has_cnt", "has_wit", "has_int", "has_con", "directed",
  "distance_m", "sn_source_rank", "sn_destination_rank",
  "host_building_local_entity_id", "shared_original_node_id", "relation_contract_version"
)

canonical_table <- function(value) {
  value <- data.table::as.data.table(value)[, ..scientific_columns]
  data.table::setorder(value, scene_id, source_local_entity_id, destination_local_entity_id, relation_mask)
  value
}

table_digest <- function(value) {
  path <- tempfile(fileext = ".rds")
  on.exit(unlink(path), add = TRUE)
  saveRDS(value, path, version = 3, compress = FALSE)
  digest::digest(file = path, algo = "sha256", serialize = FALSE)
}

run_branch <- function(index) {
  started <- Sys.time(); cpu <- proc.time()
  spec <- plans[[index]]
  vector <- read_i10_branch_context(spec, vectors[[index]])
  observations <- lapply(vector$files, read_standard_geoparquet)
  entities <- relation_entity_table(observations)
  node_positions <- read_relation_node_positions(road_path, c(entities$F_NODE, entities$T_NODE))
  scene_specs <- setNames(spec$scenes, vapply(spec$scenes, `[[`, character(1L), "scene_id"))
  scene_ids <- sort(unlist(spec$scene_ids), method = "radix")
  results <- lapply(scene_ids, function(sid) {
    scene <- relation_scene_sf(entities[scene_id == sid])
    build_scene_relations(scene, node_positions, scene_specs[[sid]], spec, "diagnostic", config)$edges
  })
  current <- canonical_table(data.table::rbindlist(results, use.names = TRUE))
  accepted_path <- accepted_relations[[index]][basename(accepted_relations[[index]]) == "relation_edges.parquet"]
  accepted <- canonical_table(arrow::read_parquet(accepted_path, as_data_frame = TRUE))
  equality <- all.equal(current, accepted, tolerance = 0, check.attributes = TRUE)
  cpu <- proc.time() - cpu
  list(
    branch_index = index, branch_id = spec$branch_id, scene_count = length(scene_ids),
    current_rows = nrow(current), accepted_rows = nrow(accepted),
    current_digest = table_digest(current), accepted_digest = table_digest(accepted),
    exact_equal = isTRUE(equality), difference = if (isTRUE(equality)) NULL else as.list(equality),
    wall_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
    user_seconds = unname(cpu[["user.self"]]), system_seconds = unname(cpu[["sys.self"]]),
    maximum_rss_kb = proc_max_rss_kb()
  )
}

started <- Sys.time()
results <- parallel::mclapply(seq_along(plans), run_branch, mc.cores = workers, mc.preschedule = FALSE)
failures <- sum(!vapply(results, `[[`, logical(1L), "exact_equal"))
result <- list(
  status = if (failures == 0L) "PASS" else "FAIL",
  scene_count = sum(vapply(results, `[[`, integer(1L), "scene_count")),
  branch_count = length(results), exact_mismatch_count = failures,
  wall_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")), results = results
)
jsonlite::write_json(result, output_path, auto_unbox = TRUE, pretty = TRUE, digits = 16, na = "null")
cat(normalizePath(output_path, mustWork = TRUE), "\n")
if (failures) quit(status = 1L)
