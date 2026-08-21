#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(arrow)
  library(data.table)
  library(jsonlite)
  library(targets)
})

args <- commandArgs(trailingOnly = TRUE)
output_path <- if (length(args)) args[[1L]] else tempfile(fileext = ".json")
store <- yaml::read_yaml("config/research_paths.yml")$targets$research_store
relation_paths <- unname(tar_read(prototype_relation_shard, store = store))
plan <- tar_read(prototype_observation_plan, store = store)
vector_paths <- unname(tar_read(prototype_vector_observation_shard, store = store))

read_parquet_dt <- function(path) as.data.table(read_parquet(path))
sha256 <- function(path) digest::digest(file = path, algo = "sha256", serialize = FALSE)
json <- function(path) fromJSON(path, simplifyVector = FALSE)
fail <- character()
check <- function(condition, label) {
  if (!isTRUE(condition)) fail <<- c(fail, label)
  invisible(condition)
}

manifests <- lapply(relation_paths, function(paths) json(paths[[4L]]))
qcs <- lapply(relation_paths, function(paths) json(paths[[5L]]))
edges <- rbindlist(lapply(relation_paths, function(paths) read_parquet_dt(paths[[1L]])), use.names = TRUE)
nodes <- rbindlist(lapply(relation_paths, function(paths) read_parquet_dt(paths[[2L]])), use.names = TRUE)
statistics <- rbindlist(lapply(relation_paths, function(paths) read_parquet_dt(paths[[3L]])), use.names = TRUE)

manifest_branch <- vapply(manifests, `[[`, character(1L), "branch_id")
plan_branch <- vapply(plan, `[[`, character(1L), "branch_id")
vector_manifest <- lapply(vector_paths, function(paths) json(paths[[4L]]))
vector_branch <- vapply(vector_manifest, `[[`, character(1L), "branch_id")
check(length(relation_paths) == 15L, "branch_count")
check(all(vapply(manifests, `[[`, character(1L), "status") == "PASS"), "manifest_pass")
check(all(vapply(qcs, `[[`, character(1L), "status") == "PASS"), "qc_pass")
check(setequal(manifest_branch, plan_branch) && setequal(manifest_branch, vector_branch), "branch_alignment")
check(setequal(unique(statistics$scene_id), unlist(lapply(plan, `[[`, "scene_ids"))), "scene_alignment")
check(nrow(statistics) == 320L && anyDuplicated(statistics$scene_id) == 0L, "scene_statistics_completeness")

checksum_mismatch <- 0L
for (manifest in manifests) {
  for (record in manifest$outputs) {
    if (!file.exists(record$path) || sha256(record$path) != record$sha256 || file.info(record$path)$size != record$size_bytes) {
      checksum_mismatch <- checksum_mismatch + 1L
    }
  }
}
check(checksum_mismatch == 0L, "output_checksum")

node_key <- c("scene_id", "local_entity_id")
edge_key <- c("scene_id", "source_local_entity_id", "destination_local_entity_id")
check(anyDuplicated(nodes[, ..node_key]) == 0L, "node_key_unique")
check(anyDuplicated(edges[, ..edge_key]) == 0L, "edge_key_unique")
check(anyDuplicated(edges$edge_id) == 0L, "edge_id_unique")
check(!any(edges$source_local_entity_id == edges$destination_local_entity_id), "self_edge")

source_nodes <- nodes[, .(scene_id, source_local_entity_id = local_entity_id, source_node_type = entity_type)]
destination_nodes <- nodes[, .(scene_id, destination_local_entity_id = local_entity_id, destination_node_type = entity_type)]
joined <- source_nodes[edges, on = .(scene_id, source_local_entity_id)]
joined <- destination_nodes[joined, on = .(scene_id, destination_local_entity_id)]
check(!anyNA(joined$source_node_type) && !anyNA(joined$destination_node_type), "dangling_endpoint")
check(all(joined$source_node_type == joined$source_entity_type) &&
      all(joined$destination_node_type == joined$destination_entity_type), "endpoint_type")

bits <- c(SN = 1L, CNT = 2L, WIT = 4L, INT = 8L, CON = 16L)
check(all(edges$relation_mask > 0L & bitwAnd(edges$relation_mask, 224L) == 0L), "relation_mask")
check(all(edges$distance_m[edges$has_sn] <= 100) && all(is.na(edges$distance_m[!edges$has_sn])), "sn_radius")
check(all(is.na(edges$sn_source_rank) | edges$sn_source_rank %between% c(1L, 16L)) &&
      all(is.na(edges$sn_destination_rank) | edges$sn_destination_rank %between% c(1L, 16L)), "sn_top_k")

contained <- unique(rbindlist(list(
  edges[has_cnt == TRUE, .(scene_id, local_entity_id = destination_local_entity_id)],
  edges[has_wit == TRUE, .(scene_id, local_entity_id = source_local_entity_id)]
)))
node_state <- nodes[, .(scene_id, local_entity_id, state = fifelse(entity_type == "P", "P_out", entity_type))]
node_state[contained, on = .(scene_id, local_entity_id), state := "P_in"]
source_state <- node_state[, .(scene_id, source_local_entity_id = local_entity_id, source_state = state)]
destination_state <- node_state[, .(scene_id, destination_local_entity_id = local_entity_id, destination_state = state)]
joined <- merge(joined, source_state, by = c("scene_id", "source_local_entity_id"), all.x = TRUE, sort = FALSE)
joined <- merge(joined, destination_state, by = c("scene_id", "destination_local_entity_id"), all.x = TRUE, sort = FALSE)
allowed <- list(
  B = list(B = c("SN", "INT"), R = c("SN", "INT"), P_in = "CNT", P_out = "SN"),
  R = list(B = c("SN", "INT"), R = c("SN", "INT", "CON"), P_in = character(), P_out = "SN"),
  P_in = list(B = "WIT", R = character(), P_in = character(), P_out = character()),
  P_out = list(B = "SN", R = "SN", P_in = character(), P_out = "SN")
)
applicability_violations <- 0L
for (i in seq_len(nrow(joined))) {
  permitted <- allowed[[joined$source_state[[i]]]][[joined$destination_state[[i]]]]
  present <- names(bits)[bitwAnd(joined$relation_mask[[i]], bits) != 0L]
  applicability_violations <- applicability_violations + as.integer(!all(present %in% permitted))
}
check(applicability_violations == 0L, "applicability")

reverse <- edges[, .(scene_id, source_local_entity_id = destination_local_entity_id,
                     destination_local_entity_id = source_local_entity_id,
                     reverse_mask = relation_mask)]
paired <- reverse[edges, on = edge_key]
symmetry_violation <- sum(vapply(c("SN", "INT", "CON"), function(relation) {
  present <- bitwAnd(paired$relation_mask, bits[[relation]]) != 0L
  sum(present & (is.na(paired$reverse_mask) | bitwAnd(paired$reverse_mask, bits[[relation]]) == 0L))
}, integer(1L)))
inverse_violation <- sum(paired$has_cnt & (is.na(paired$reverse_mask) | bitwAnd(paired$reverse_mask, bits[["WIT"]]) == 0L)) +
  sum(paired$has_wit & (is.na(paired$reverse_mask) | bitwAnd(paired$reverse_mask, bits[["CNT"]]) == 0L))
check(symmetry_violation == 0L, "symmetry")
check(inverse_violation == 0L, "containment_inverse")

host_violation <- edges[has_cnt == TRUE, .(host_count = uniqueN(host_building_local_entity_id)),
                              by = .(scene_id, destination_local_entity_id)][host_count != 1L, .N]
check(host_violation == 0L, "single_host")
check(all(edges$source_entity_type[edges$has_con] == "R" & edges$destination_entity_type[edges$has_con] == "R" &
          !is.na(edges$shared_original_node_id[edges$has_con])), "con_contract")

rank_violation <- edges[!is.na(sn_source_rank), {
  expected <- order(round(distance_m / 1e-9) * 1e-9, destination_local_entity_id, method = "radix")
  list(bad = !identical(sn_source_rank[expected], seq_len(.N)))
}, by = .(scene_id, source_local_entity_id)][bad == TRUE, .N]
check(rank_violation == 0L, "sn_tie_order")

relation_counts <- setNames(vapply(names(bits), function(relation) sum(bitwAnd(edges$relation_mask, bits[[relation]]) != 0L), integer(1L)), names(bits))
node_counts <- as.list(nodes[, .N, by = entity_type][match(c("B", "R", "P"), entity_type), N])
names(node_counts) <- c("Building", "Road", "POI")
poi_out_out_sn <- joined[source_state == "P_out" & destination_state == "P_out" & has_sn, .N]
relation_dataset_ids <- unique(vapply(manifests, `[[`, character(1L), "relation_dataset_id"))
check(length(relation_dataset_ids) == 1L, "relation_dataset_identity")

result <- list(
  status = if (length(fail)) "FAIL" else "PASS", failures = as.list(fail),
  branch_count = length(relation_paths), scene_count = nrow(statistics), node_counts = node_counts,
  ordered_pair_count = nrow(edges), relation_counts = as.list(relation_counts),
  multi_relation_pair_count = sum(rowSums(vapply(bits, function(bit) bitwAnd(edges$relation_mask, bit) != 0L, logical(nrow(edges)))) > 1L),
  empty_edge_scene_count = sum(statistics$ordered_pair_count == 0L), poi_out_poi_out_sn_count = poi_out_out_sn,
  contained_poi_count = nrow(contained), outside_poi_count = sum(nodes$entity_type == "P") - nrow(contained),
  checksum_mismatch_count = checksum_mismatch, applicability_violation_count = applicability_violations,
  symmetry_violation_count = symmetry_violation, inverse_violation_count = inverse_violation,
  rank_violation_count = rank_violation,
  scene_edge_count = as.list(quantile(statistics$ordered_pair_count, c(0, 0.5, 0.95, 1), names = FALSE, type = 7)),
  relation_dataset_ids = as.list(relation_dataset_ids)
)
dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
write_json(result, output_path, auto_unbox = TRUE, pretty = TRUE, digits = NA)
cat(toJSON(result, auto_unbox = TRUE, pretty = TRUE, digits = NA), "\n")
if (length(fail)) quit(status = 1L)
