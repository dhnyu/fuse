# Bounded independent-source checks; never publishes canonical acceptance.
args <- commandArgs(trailingOnly = TRUE)
source("R/retrieval_gallery.R")
retrieval_source_helpers()
pilot <- jsonlite::read_json(args[[1]], simplifyVector = FALSE)
stopifnot(pilot$status == "SPATIAL_PASS", pilot$count %in% c(100L, 500L, 1000L))
if (file.exists(args[[2]])) stop("Parity output exists")
cfg <- load_relation_config(retrieval_contract_paths(relation_contract_paths()))
records <- list()
for (branch in head(pilot$branches, 4L)) {
  result <- jsonlite::read_json(file.path(branch$root, "spatial_result.json"), simplifyVector = FALSE)
  paths <- lapply(result$files, unlist)
  retrieval_validate_relation_statistics(paths$relations)
  plan_path <- jsonlite::read_json(result$serialization_spec)$source_groups[[1L]]
  spec <- jsonlite::read_json(file.path(plan_path$root, plan_path$members), simplifyVector = FALSE)
  stats <- data.table::as.data.table(arrow::read_parquet(paths$relations[basename(paths$relations) == "scene_relation_statistics.parquet"]))
  eligible <- stats[node_count > 0 & sn_edge_count > 0 & cnt_edge_count > 0 & wit_edge_count > 0 & int_edge_count > 0 & con_edge_count > 0]
  if (!nrow(eligible)) stop("Bounded parity branch lacks all-five-relation support")
  id <- eligible[order(node_count, scene_id)]$scene_id[[1L]]
  scene_spec <- spec$scenes[[match(id, unlist(spec$scene_ids))]]
  brute <- data.table::as.data.table(brute_force_membership_for_scene(scene_spec, spec))
  actual <- data.table::rbindlist(lapply(paths$membership[grepl("_membership.parquet$", paths$membership)], arrow::read_parquet))[scene_id == id]
  key <- c("scene_id", "entity_type", "source_entity_id")
  stopifnot(nrow(data.table::fsetdiff(brute[, ..key], actual[, ..key])) == 0,
            nrow(data.table::fsetdiff(actual[, ..key], brute[, ..key])) == 0)
  vector_paths <- paths$vector[grepl("_observed.parquet$", paths$vector)]
  names(vector_paths) <- sub("_observed.parquet$", "", basename(vector_paths))
  entities <- relation_entity_table(lapply(vector_paths, read_standard_geoparquet))[scene_id == id]
  nodes <- read_relation_node_positions(spec$sources$road$path, c(entities$F_NODE, entities$T_NODE))
  manifest <- jsonlite::read_json(paths$relations[basename(paths$relations) == "branch_manifest.json"])
  reference <- reference_scene_relations(relation_scene_sf(entities), nodes, scene_spec, spec, manifest$relation_dataset_id, cfg)
  observed <- data.table::as.data.table(arrow::read_parquet(paths$relations[basename(paths$relations) == "relation_edges.parquet"]))[scene_id == id]
  comparison <- compare_relation_reference(observed, reference)
  stopifnot(comparison$status == "PASS")
  records[[length(records) + 1L]] <- list(scene_id = id, node_count = nrow(entities), membership_false_positive = 0L,
    membership_false_negative = 0L, relation_reference = comparison, all_five_relations_present = TRUE)
}
write_json_file(list(status = "PASS", sample_count = length(records), records = records,
  relation_implementation_sha256 = sha256_file("R/research_relation.R"), relation_semantics_changed = FALSE), args[[2]])
