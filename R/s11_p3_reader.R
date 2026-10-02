# Dissertation 5.4; frozen D1-D5. This process only reads selected original P3
# observations exported losslessly by the authenticated tar reader.
s11_cached_geometry <- function(rows, type) {
  geometry <- sf::st_as_sfc(structure(as.list(rows$observed_geometry), class = "WKB"), crs = 5186)
  if (!nrow(rows)) return(list(geometry = geometry, max_measure_error = 0, max_center_error = 0))
  boxes <- t(vapply(geometry, function(g) as.numeric(sf::st_bbox(g)), numeric(4)))
  centers <- cbind((boxes[, 1] + boxes[, 3]) / 2, (boxes[, 2] + boxes[, 4]) / 2)
  cached <- cbind(rows$observed_center_x_5186, rows$observed_center_y_5186)
  if (any(!is.finite(cached)) || any(abs(centers - cached) > 1e-7)) stop("S11 cached bbox center mismatch")
  if (any(abs(centers[, 1] - rows$scene_center_x_5186 - rows$relative_center_x_m) > 1e-7) ||
      any(abs(centers[, 2] - rows$scene_center_y_5186 - rows$relative_center_y_m) > 1e-7)) stop("S11 relative center mismatch")
  if (any(boxes[, 1] < rows$scene_center_x_5186 - 250 - 1e-7) ||
      any(boxes[, 3] > rows$scene_center_x_5186 + 250 + 1e-7) ||
      any(boxes[, 2] < rows$scene_center_y_5186 - 250 - 1e-7) ||
      any(boxes[, 4] > rows$scene_center_y_5186 + 250 + 1e-7)) stop("S11 geometry outside scene")
  measured <- cached_measure <- numeric()
  if (type == "B") {
    measured <- as.numeric(sf::st_area(geometry)); cached_measure <- rows$observed_area_m2; atol <- 1e-4
  } else if (type == "R") {
    measured <- as.numeric(sf::st_length(geometry)); cached_measure <- rows$observed_length_m; atol <- 1e-7
  }
  if (length(measured) && (any(!is.finite(cached_measure)) ||
      any(abs(measured - cached_measure) > atol + 1e-10 * abs(cached_measure)))) stop("S11 cached geometry measure mismatch")
  list(geometry = geometry, max_measure_error = max(c(0, abs(measured - cached_measure))),
       max_center_error = max(abs(centers - cached)))
}

s11_read_selected_p3 <- function(directory, categories_path) {
  selection <- jsonlite::read_json(file.path(directory, "selection.json"), simplifyVector = TRUE)
  entries <- jsonlite::read_json(categories_path)$entries
  read <- function(name) as.data.frame(arrow::read_parquet(file.path(directory, paste0(name, ".parquet"))))
  tables <- lapply(c("building", "road", "poi", "edges", "nodes", "statistics"), read)
  names(tables) <- c("B", "R", "P", "edges", "nodes", "statistics")
  for (table in tables) {
    if (anyNA(table$scene_id) || any(!table$scene_id %in% selection$scene_ids) ||
        anyNA(table$split) || any(table$split != "evaluation")) stop("S11 non-original evaluation input")
  }
  result <- lapply(selection$scene_ids, function(scene) {
    rows <- lapply(tables, function(x) x[x$scene_id == scene, , drop = FALSE])
    geometry <- Map(s11_cached_geometry, rows[c("B", "R", "P")], c("B", "R", "P"))
    all_nodes <- do.call(rbind, lapply(rows[c("B", "R", "P")], function(x) x[, c("local_entity_id", "entity_type", "source_entity_id")]))
    nodes <- rows$nodes
    if (anyDuplicated(all_nodes$local_entity_id) || anyDuplicated(nodes$local_entity_id) ||
        !setequal(all_nodes$local_entity_id, nodes$local_entity_id)) stop("S11 node inventory mismatch")
    matched <- nodes[match(all_nodes$local_entity_id, nodes$local_entity_id), ]
    if (!identical(all_nodes$entity_type, matched$entity_type) ||
        !identical(all_nodes$source_entity_id, matched$source_entity_id)) stop("S11 node identities mismatch")
    edges <- rows$edges
    src <- all_nodes$entity_type[match(edges$source_local_entity_id, all_nodes$local_entity_id)]
    dst <- all_nodes$entity_type[match(edges$destination_local_entity_id, all_nodes$local_entity_id)]
    if (anyNA(src) || anyNA(dst) || any(src != edges$source_entity_type | dst != edges$destination_entity_type) ||
        anyNA(edges$directed) || any(edges$directed != (bitwAnd(edges$relation_mask, 6L) != 0))) stop("S11 edge endpoint/direction mismatch")
    bits <- c(sn = 1L, cnt = 2L, wit = 4L, int = 8L, con = 16L)
    for (name in names(bits)) {
      present <- bitwAnd(edges$relation_mask, bits[[name]]) != 0
      if (anyNA(edges[[paste0("has_", name)]]) || any(present != edges[[paste0("has_", name)]])) stop("S11 relation bit flag mismatch")
      admissible <- switch(name, cnt = src == "B" & dst == "P", wit = src == "P" & dst == "B",
                          int = src %in% c("B", "R") & dst %in% c("B", "R"),
                          con = src == "R" & dst == "R", sn = rep(TRUE, nrow(edges)))
      if (any(present & !admissible)) stop("S11 relation endpoint semantics")
    }
    contained <- edges$destination_local_entity_id[edges$has_cnt]
    if (any(edges$has_sn & (edges$source_local_entity_id %in% contained | edges$destination_local_entity_id %in% contained))) stop("S11 contained POI SN")
    relation <- s11_relation_descriptors(edges[, c("source_local_entity_id", "destination_local_entity_id", "relation_mask")], all_nodes$local_entity_id)
    stats <- rows$statistics
    actual <- c(node_count = nrow(all_nodes), building_count = nrow(rows$B), road_count = nrow(rows$R),
                poi_count = nrow(rows$P), ordered_pair_count = nrow(edges),
                contained_poi_count = length(contained), outside_poi_count = nrow(rows$P) - length(contained),
                multi_relation_pair_count = sum(vapply(edges$relation_mask, function(m) sum(bitwAnd(m, bits) != 0) > 1, logical(1))))
    counts <- relation$qc$directed_counts
    actual <- c(actual, setNames(unname(counts), paste0(tolower(names(counts)), "_edge_count")))
    if (nrow(stats) != 1L || any(vapply(names(actual), function(k) is.na(stats[[k]]) || stats[[k]] != actual[[k]], logical(1)))) stop("S11 cached relation statistics mismatch")
    descriptors <- s11_geometry_descriptors(geometry$B$geometry, geometry$R$geometry, geometry$P$geometry)
    descriptors <- c(descriptors, relation[c("relation_composition", "mean_relational_degree")], list(
      building_use_composition = s11_resolve_categories(rows$B$A9, entries, "A9"),
      building_structure_composition = s11_resolve_categories(rows$B$A11, entries, "A11"),
      road_type_composition = s11_resolve_categories(rows$R$ROAD_TYPE, entries, "ROAD_TYPE"),
      road_hierarchy_composition = s11_resolve_categories(rows$R$ROAD_RANK, entries, "ROAD_RANK"),
      mean_lane_count = s11_mean(rows$R$LANES, positive = TRUE),
      poi_l2_composition = s11_resolve_categories(s11_poi_l2_keys(rows$P), entries, "CLASS_L2")))
    list(scene_id = scene, descriptors = descriptors,
         qc = list(geometry = lapply(geometry, function(g) g[c("max_measure_error", "max_center_error")]),
                   relations = relation$qc, counts = as.list(actual)))
  })
  result
}
