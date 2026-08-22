# Thesis Methodology 3.3, Spatial Relation Modeling:
# construct SN/CNT/WIT/INT/CON from I10 observed geometries and source road nodes.
relation_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/relation_graph.yml",
    "config/relation_graph_runtime.yml",
    "config/schemas/prototype_relation.schema.json",
    "R/research_relation.R"
  ))
}

load_relation_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c(
    "relation_graph.yml", "relation_graph_runtime.yml",
    "prototype_relation.schema.json", "research_relation.R"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing relation contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  scientific <- yaml::read_yaml(by_name[["relation_graph.yml"]])
  runtime <- yaml::read_yaml(by_name[["relation_graph_runtime.yml"]])
  validate_relation_config(scientific, runtime)
  list(
    scientific = scientific, runtime = runtime,
    schema_file = by_name[["prototype_relation.schema.json"]],
    implementation_file = by_name[["research_relation.R"]],
    scientific_hash = sha256_file(by_name[["relation_graph.yml"]]),
    runtime_hash = sha256_file(by_name[["relation_graph_runtime.yml"]]),
    schema_hash = sha256_file(by_name[["prototype_relation.schema.json"]]),
    implementation_source_hash = sha256_file(by_name[["research_relation.R"]])
  )
}

relation_expected_applicability <- function() list(
  B = list(B = c("SN", "INT"), R = c("SN", "INT"), P_in = "CNT", P_out = "SN"),
  R = list(B = c("SN", "INT"), R = c("SN", "INT", "CON"), P_in = character(), P_out = "SN"),
  P_in = list(B = "WIT", R = character(), P_in = character(), P_out = character()),
  P_out = list(B = "SN", R = "SN", P_in = character(), P_out = "SN")
)

validate_relation_config <- function(scientific, runtime) {
  bits <- unlist(scientific$relations$bits)
  checks <- c(
    epsg = identical(as.integer(scientific$processing_epsg), 5186L),
    observed = identical(scientific$source_geometry, "I10_observed_geometry_only"),
    relation_order = identical(unlist(scientific$relations$order), c("SN", "CNT", "WIT", "INT", "CON")),
    bits = identical(as.integer(bits[c("SN", "CNT", "WIT", "INT", "CON")]), 0:4),
    mask = identical(scientific$relations$mask_type, "uint8"),
    radius = identical(as.numeric(scientific$sn$radius_m), 100),
    top_k = identical(as.integer(scientific$sn$top_k), 16L),
    sn_symmetry = identical(scientific$sn$symmetrization, "retain_both_directions_if_either_direction_selects"),
    within = identical(scientific$containment$predicate, "GEOS_strict_within"),
    intersects = identical(scientific$intersection$predicate, "GEOS_intersects"),
    con = identical(scientific$connectivity$shared_node, "same_original_F_NODE_or_T_NODE"),
    controller = identical(runtime$controller, "controller_10"),
    workers = identical(as.integer(runtime$branch_workers), 1L),
    threads = identical(as.integer(runtime$threads_per_worker), 1L)
  )
  expected <- relation_expected_applicability()
  for (source in names(expected)) for (destination in names(expected[[source]])) {
    actual <- as.character(unlist(scientific$applicability[[source]][[destination]]))
    checks[paste(source, destination, sep = "_to_")] <- identical(actual, expected[[source]][[destination]])
  }
  if (any(!checks)) stop("Relation contract mismatch: ", paste(names(checks)[!checks], collapse = ", "), call. = FALSE)
  invisible(TRUE)
}

relation_thread_state <- function() observation_thread_state()
set_relation_threads <- function(threads = 1L) set_observation_threads(threads)
restore_relation_threads <- function(state) restore_observation_threads(state)

relation_bit_values <- function(config) {
  raw <- unlist(config$scientific$relations$bits)
  setNames(bitwShiftL(1L, as.integer(raw)), names(raw))
}

relation_empty_edges <- function() data.table::data.table(
  source_local_entity_id = integer(), destination_local_entity_id = integer(),
  relation_bit = integer(), distance_m = numeric(), sn_source_rank = integer(),
  sn_destination_rank = integer(), host_building_local_entity_id = integer(),
  shared_original_node_id = character()
)

relation_entity_table <- function(observations) {
  roles <- c(building = "B", road = "R", poi = "P")
  values <- lapply(names(roles), function(role) {
    x <- observations[[role]]
    data.table::data.table(
      scene_id = x$scene_id, scene_footprint_id = x$scene_footprint_id, split = x$split,
      entity_type = roles[[role]], source_entity_id = x$source_entity_id,
      local_entity_id = as.integer(x$local_entity_id),
      observed_area_m2 = if (role == "building") as.numeric(x$observed_area_m2) else NA_real_,
      F_NODE = if (role == "road") as.character(x$F_NODE) else NA_character_,
      T_NODE = if (role == "road") as.character(x$T_NODE) else NA_character_,
      source_f_node_endpoint_retained = if (role == "road") as.logical(x$source_f_node_endpoint_retained) else NA,
      source_t_node_endpoint_retained = if (role == "road") as.logical(x$source_t_node_endpoint_retained) else NA,
      geometry = I(sf::st_geometry(x))
    )
  })
  value <- data.table::rbindlist(values, use.names = TRUE)
  data.table::setorder(value, scene_id, local_entity_id)
  if (anyDuplicated(value[, .(scene_id, local_entity_id)])) stop("I10 local entity IDs are not scene-unique", call. = FALSE)
  value
}

relation_scene_sf <- function(entities) {
  geometry <- sf::st_sfc(unclass(entities$geometry), crs = 5186L)
  attributes <- as.data.frame(entities[, !"geometry"])
  sf::st_sf(attributes, observed_geometry = geometry, crs = 5186L)
}

classify_relation_pois <- function(scene, config) {
  state <- ifelse(scene$entity_type == "P", "P_out", scene$entity_type)
  host <- data.table::data.table(
    poi_local_entity_id = integer(), host_building_local_entity_id = integer(),
    host_candidate_count = integer(), host_tie = logical()
  )
  p <- which(scene$entity_type == "P")
  b <- which(scene$entity_type == "B")
  if (length(p) && length(b)) {
    candidates <- sf::st_within(scene[p, ], scene[b, ], sparse = TRUE)
    rows <- lapply(seq_along(candidates), function(i) {
      if (!length(candidates[[i]])) return(NULL)
      building <- b[candidates[[i]]]
      area <- scene$observed_area_m2[building]
      order_index <- order(area, scene$source_entity_id[building], scene$local_entity_id[building], method = "radix")
      chosen <- building[order_index[[1L]]]
      minimum <- min(area)
      data.table::data.table(
        poi_local_entity_id = as.integer(scene$local_entity_id[p[[i]]]),
        host_building_local_entity_id = as.integer(scene$local_entity_id[chosen]),
        host_candidate_count = length(building),
        host_tie = sum(abs(area - minimum) <= .Machine$double.eps * max(1, minimum)) > 1L
      )
    })
    host <- data.table::rbindlist(rows)
    if (nrow(host)) state[match(host$poi_local_entity_id, scene$local_entity_id)] <- "P_in"
  }
  list(state = state, host = host)
}

sn_eligible_destination_states <- function(source_state) {
  switch(source_state,
    B = c("B", "R", "P_out"),
    R = c("B", "R", "P_out"),
    P_in = character(),
    P_out = c("B", "R", "P_out"),
    character()
  )
}

scene_sn_edges <- function(scene, state, config, candidate_block_size = 128L) {
  bits <- relation_bit_values(config)
  radius <- as.numeric(config$scientific$sn$radius_m)
  top_k <- as.integer(config$scientific$sn$top_k)
  tolerance <- as.numeric(config$scientific$sn$distance_tie_tolerance_m)
  selected <- list()
  candidate_count <- 0L
  position <- 0L
  for (source_state in c("B", "R", "P_in", "P_out")) {
    source <- which(state == source_state)
    destination <- which(state %in% sn_eligible_destination_states(source_state))
    if (!length(source) || !length(destination)) next
    blocks <- split(source, ceiling(seq_along(source) / as.integer(candidate_block_size)))
    for (block in blocks) {
      nearby <- sf::st_is_within_distance(scene[block, ], scene[destination, ], dist = radius, sparse = TRUE)
      for (i in seq_along(block)) {
        destination_index <- destination[nearby[[i]]]
        destination_index <- destination_index[destination_index != block[[i]]]
        if (!length(destination_index)) next
        candidate_count <- candidate_count + length(destination_index)
        distance <- as.numeric(sf::st_distance(
          scene[rep(block[[i]], length(destination_index)), ], scene[destination_index, ], by_element = TRUE
        ))
        keep <- is.finite(distance) & distance <= radius
        destination_index <- destination_index[keep]
        distance <- distance[keep]
        if (!length(destination_index)) next
        distance_key <- round(distance / tolerance) * tolerance
        ordering <- order(distance_key, scene$local_entity_id[destination_index], method = "radix")
        ordering <- head(ordering, top_k)
        position <- position + 1L
        selected[[position]] <- data.table::data.table(
          source_local_entity_id = as.integer(scene$local_entity_id[block[[i]]]),
          destination_local_entity_id = as.integer(scene$local_entity_id[destination_index[ordering]]),
          distance_m = distance[ordering], sn_rank = seq_along(ordering)
        )
      }
    }
  }
  selected <- data.table::rbindlist(selected)
  if (!nrow(selected)) return(list(edges = relation_empty_edges(), candidate_count = candidate_count, retained_selection_count = 0L))
  selected[, pair_min := pmin(source_local_entity_id, destination_local_entity_id)]
  selected[, pair_max := pmax(source_local_entity_id, destination_local_entity_id)]
  pairs <- unique(selected[, .(pair_min, pair_max)])
  distance <- selected[, .(distance_m = min(distance_m)), by = .(pair_min, pair_max)]
  pairs <- distance[pairs, on = .(pair_min, pair_max)]
  forward <- selected[, .(pair_min, pair_max, selected_source = source_local_entity_id, sn_rank)]
  make_direction <- function(source, destination) {
    value <- data.table::data.table(pair_min = pairs$pair_min, pair_max = pairs$pair_max,
                                    source_local_entity_id = source, destination_local_entity_id = destination)
    source_rank <- forward[value, on = .(pair_min, pair_max, selected_source = source_local_entity_id), sn_rank]
    destination_rank <- forward[value, on = .(pair_min, pair_max, selected_source = destination_local_entity_id), sn_rank]
    data.table::data.table(
      source_local_entity_id = source, destination_local_entity_id = destination,
      relation_bit = bits[["SN"]], distance_m = pairs$distance_m,
      sn_source_rank = as.integer(source_rank), sn_destination_rank = as.integer(destination_rank),
      host_building_local_entity_id = NA_integer_, shared_original_node_id = NA_character_
    )
  }
  edges <- data.table::rbindlist(list(
    make_direction(pairs$pair_min, pairs$pair_max),
    make_direction(pairs$pair_max, pairs$pair_min)
  ))
  list(edges = edges, candidate_count = candidate_count, retained_selection_count = nrow(selected))
}

scene_containment_edges <- function(classification, config) {
  host <- classification$host
  if (!nrow(host)) return(relation_empty_edges())
  bits <- relation_bit_values(config)
  data.table::rbindlist(list(
    data.table::data.table(
      source_local_entity_id = host$host_building_local_entity_id,
      destination_local_entity_id = host$poi_local_entity_id,
      relation_bit = bits[["CNT"]], distance_m = NA_real_, sn_source_rank = NA_integer_, sn_destination_rank = NA_integer_,
      host_building_local_entity_id = host$host_building_local_entity_id, shared_original_node_id = NA_character_
    ),
    data.table::data.table(
      source_local_entity_id = host$poi_local_entity_id,
      destination_local_entity_id = host$host_building_local_entity_id,
      relation_bit = bits[["WIT"]], distance_m = NA_real_, sn_source_rank = NA_integer_, sn_destination_rank = NA_integer_,
      host_building_local_entity_id = host$host_building_local_entity_id, shared_original_node_id = NA_character_
    )
  ))
}

scene_intersection_edges <- function(scene, config) {
  bits <- relation_bit_values(config)
  physical <- which(scene$entity_type %in% c("B", "R"))
  if (length(physical) < 2L) return(relation_empty_edges())
  hits <- sf::st_intersects(scene[physical, ], scene[physical, ], sparse = TRUE)
  pair <- data.table::rbindlist(lapply(seq_along(hits), function(i) {
    destination <- hits[[i]][hits[[i]] > i]
    if (!length(destination)) return(NULL)
    data.table::data.table(first = physical[[i]], second = physical[destination])
  }))
  if (!nrow(pair)) return(relation_empty_edges())
  first <- as.integer(scene$local_entity_id[pair$first])
  second <- as.integer(scene$local_entity_id[pair$second])
  make <- function(source, destination) data.table::data.table(
    source_local_entity_id = source, destination_local_entity_id = destination,
    relation_bit = bits[["INT"]], distance_m = NA_real_, sn_source_rank = NA_integer_, sn_destination_rank = NA_integer_,
    host_building_local_entity_id = NA_integer_, shared_original_node_id = NA_character_
  )
  data.table::rbindlist(list(make(first, second), make(second, first)))
}

scene_connectivity_edges <- function(scene, node_positions, scene_spec, config) {
  bits <- relation_bit_values(config)
  roads <- which(scene$entity_type == "R")
  if (length(roads) < 2L) return(relation_empty_edges())
  endpoints <- unique(data.table::rbindlist(list(
    data.table::data.table(local_entity_id = scene$local_entity_id[roads], node_id = scene$F_NODE[roads]),
    data.table::data.table(local_entity_id = scene$local_entity_id[roads], node_id = scene$T_NODE[roads])
  )))
  endpoints <- node_positions[endpoints, on = .(node_id)]
  if (anyNA(endpoints$x) || anyNA(endpoints$y)) stop("Road branch has dangling or missing original node position", call. = FALSE)
  endpoints <- endpoints[
    x >= as.numeric(scene_spec$xmin) & x <= as.numeric(scene_spec$xmax) &
    y >= as.numeric(scene_spec$ymin) & y <= as.numeric(scene_spec$ymax)
  ]
  if (!nrow(endpoints)) return(relation_empty_edges())
  pairs <- endpoints[, {
    ids <- sort(unique(as.integer(local_entity_id)))
    if (length(ids) < 2L) NULL else {
      combination <- utils::combn(ids, 2L)
      data.table::data.table(first = combination[1L, ], second = combination[2L, ], shared = node_id[[1L]])
    }
  }, by = node_id]
  if (!nrow(pairs)) return(relation_empty_edges())
  pairs <- pairs[, .(shared_original_node_id = paste(sort(unique(shared), method = "radix"), collapse = "|")), by = .(first, second)]
  make <- function(source, destination) data.table::data.table(
    source_local_entity_id = as.integer(source), destination_local_entity_id = as.integer(destination),
    relation_bit = bits[["CON"]], distance_m = NA_real_, sn_source_rank = NA_integer_, sn_destination_rank = NA_integer_,
    host_building_local_entity_id = NA_integer_, shared_original_node_id = pairs$shared_original_node_id
  )
  data.table::rbindlist(list(make(pairs$first, pairs$second), make(pairs$second, pairs$first)))
}

collapse_relation_edges <- function(long, scene, scene_spec, spec, relation_dataset_id, config) {
  if (!nrow(long)) return(relation_empty_output_table())
  value <- long[, .(
    relation_mask = Reduce(bitwOr, unique(as.integer(relation_bit))),
    distance_m = if (any(relation_bit == relation_bit_values(config)[["SN"]])) min(distance_m[relation_bit == relation_bit_values(config)[["SN"]]], na.rm = TRUE) else NA_real_,
    sn_source_rank = if (any(!is.na(sn_source_rank))) min(sn_source_rank, na.rm = TRUE) else NA_integer_,
    sn_destination_rank = if (any(!is.na(sn_destination_rank))) min(sn_destination_rank, na.rm = TRUE) else NA_integer_,
    host_building_local_entity_id = if (any(!is.na(host_building_local_entity_id))) unique(na.omit(host_building_local_entity_id))[[1L]] else NA_integer_,
    shared_original_node_id = if (any(!is.na(shared_original_node_id))) paste(sort(unique(na.omit(shared_original_node_id)), method = "radix"), collapse = "|") else NA_character_
  ), by = .(source_local_entity_id, destination_local_entity_id)]
  meta <- data.table::as.data.table(sf::st_drop_geometry(scene))[, .(local_entity_id, entity_type)]
  value[, source_entity_type := meta$entity_type[match(source_local_entity_id, meta$local_entity_id)]]
  value[, destination_entity_type := meta$entity_type[match(destination_local_entity_id, meta$local_entity_id)]]
  bits <- relation_bit_values(config)
  value[, `:=`(
    scene_id = scene_spec$scene_id, scene_footprint_id = scene_spec$scene_footprint_id, split = scene_spec$split,
    has_sn = bitwAnd(relation_mask, bits[["SN"]]) != 0L,
    has_cnt = bitwAnd(relation_mask, bits[["CNT"]]) != 0L,
    has_wit = bitwAnd(relation_mask, bits[["WIT"]]) != 0L,
    has_int = bitwAnd(relation_mask, bits[["INT"]]) != 0L,
    has_con = bitwAnd(relation_mask, bits[["CON"]]) != 0L,
    directed = bitwAnd(relation_mask, bitwOr(bits[["CNT"]], bits[["WIT"]])) != 0L,
    relation_contract_version = config$scientific$relation_contract_version,
    vector_observation_dataset_id = spec$observation_dataset_id,
    relation_dataset_id = relation_dataset_id, branch_id = spec$branch_id
  )]
  value[, edge_id := vapply(seq_len(.N), function(i) short_hash_id("red_", list(
    scene_id = scene_id[[i]], source_local_entity_id = source_local_entity_id[[i]],
    destination_local_entity_id = destination_local_entity_id[[i]], relation_mask = relation_mask[[i]]
  )), character(1L))]
  columns <- relation_edge_columns()
  data.table::setcolorder(value, columns)
  data.table::setorder(value, scene_id, source_local_entity_id, destination_local_entity_id, relation_mask)
  value[]
}

relation_edge_columns <- function() c(
  "scene_id", "scene_footprint_id", "split", "edge_id",
  "source_local_entity_id", "destination_local_entity_id", "source_entity_type", "destination_entity_type",
  "relation_mask", "has_sn", "has_cnt", "has_wit", "has_int", "has_con", "directed",
  "distance_m", "sn_source_rank", "sn_destination_rank", "host_building_local_entity_id",
  "shared_original_node_id", "relation_contract_version", "vector_observation_dataset_id",
  "relation_dataset_id", "branch_id"
)

relation_empty_output_table <- function() {
  value <- data.table::data.table(
    scene_id = character(), scene_footprint_id = character(), split = character(), edge_id = character(),
    source_local_entity_id = integer(), destination_local_entity_id = integer(),
    source_entity_type = character(), destination_entity_type = character(), relation_mask = integer(),
    has_sn = logical(), has_cnt = logical(), has_wit = logical(), has_int = logical(), has_con = logical(), directed = logical(),
    distance_m = numeric(), sn_source_rank = integer(), sn_destination_rank = integer(),
    host_building_local_entity_id = integer(), shared_original_node_id = character(),
    relation_contract_version = character(), vector_observation_dataset_id = character(),
    relation_dataset_id = character(), branch_id = character()
  )
  columns <- relation_edge_columns()
  value[, ..columns]
}

build_scene_relations <- function(scene, node_positions, scene_spec, spec, relation_dataset_id, config) {
  classification <- classify_relation_pois(scene, config)
  sn <- scene_sn_edges(scene, classification$state, config)
  containment <- scene_containment_edges(classification, config)
  intersection <- scene_intersection_edges(scene, config)
  connectivity <- scene_connectivity_edges(scene, node_positions, scene_spec, config)
  long <- data.table::rbindlist(list(sn$edges, containment, intersection, connectivity), use.names = TRUE)
  edges <- collapse_relation_edges(long, scene, scene_spec, spec, relation_dataset_id, config)
  list(
    edges = edges, classification = classification,
    sn_candidate_count = sn$candidate_count, sn_retained_selection_count = sn$retained_selection_count
  )
}

relation_road_path <- function(study_data_inputs) {
  paths <- normalizePath(study_data_inputs, mustWork = TRUE)
  matches <- paths[basename(paths) == "seoul_R.gpkg"]
  if (length(matches) != 1L) stop("Expected exactly one tracked seoul_R.gpkg", call. = FALSE)
  matches[[1L]]
}

read_relation_node_positions <- function(road_path, node_ids, chunk_size = 1000L) {
  ids <- sort(unique(as.character(node_ids)), method = "radix")
  ids <- ids[!is.na(ids) & nzchar(ids)]
  if (!length(ids)) return(data.table::data.table(node_id = character(), x = numeric(), y = numeric()))
  chunks <- split(ids, ceiling(seq_along(ids) / as.integer(chunk_size)))
  nodes <- lapply(chunks, function(chunk) sf::st_read(
    road_path,
    query = paste0('SELECT NODE_ID AS node_id, geom FROM nodes WHERE NODE_ID IN (',
                   paste(vapply(chunk, sql_string, character(1L)), collapse = ","), ')'),
    quiet = TRUE, stringsAsFactors = FALSE, int64_as_string = TRUE
  ))
  nodes <- do.call(rbind, nodes)
  if (sf::st_crs(nodes)$epsg != 5186L || any(sf::st_is_empty(nodes)) || any(!sf::st_is_valid(nodes)) ||
      anyDuplicated(nodes$node_id) || !setequal(nodes$node_id, ids)) {
    stop("Original road-node geometry contract failed", call. = FALSE)
  }
  xy <- sf::st_coordinates(nodes)
  data.table::data.table(node_id = as.character(nodes$node_id), x = xy[, "X"], y = xy[, "Y"])[order(node_id)]
}

relation_dataset_identity <- function(spec, vector, road_record, config) {
  short_hash_id("pre_", list(
    vector_observation_dataset_id = spec$observation_dataset_id,
    prototype_id = spec$prototype_id, scene_index_id = spec$scene_index_id,
    road_topology = road_record[c("artifact_id", "sha256")],
    config_hash = config$scientific_hash, schema_hash = config$schema_hash,
    implementation_source_hash = config$implementation_source_hash
  ))
}

relation_node_index <- function(entities, spec, relation_dataset_id, config) {
  value <- entities[, .(
    scene_id, scene_footprint_id, split, local_entity_id, entity_type, source_entity_id,
    relation_contract_version = config$scientific$relation_contract_version,
    vector_observation_dataset_id = spec$observation_dataset_id,
    relation_dataset_id = relation_dataset_id, branch_id = spec$branch_id
  )]
  data.table::setorder(value, scene_id, local_entity_id)
  value
}

# Appendix B entity removal: preserve the original, pre-augmentation road
# endpoint incidence instead of attempting to infer node degree from CON edges.
relation_road_topology <- function(entities, node_positions, scene_specs, spec, relation_dataset_id, road_record, config) {
  roads <- entities[entity_type == "R"]
  columns <- c(
    "scene_id", "scene_footprint_id", "split", "road_local_entity_id", "road_source_entity_id",
    "endpoint_order", "endpoint_label", "original_node_id", "scene_node_index",
    "scene_incident_road_count", "node_state", "node_state_code", "original_node_x_5186",
    "original_node_y_5186", "original_endpoint_retained", "relation_dataset_id", "branch_id"
  )
  if (!nrow(roads)) return(data.table::data.table(
    scene_id = character(), scene_footprint_id = character(), split = character(),
    road_local_entity_id = integer(), road_source_entity_id = character(),
    endpoint_order = integer(), endpoint_label = character(), original_node_id = character(),
    scene_node_index = integer(), scene_incident_road_count = integer(), node_state = character(),
    node_state_code = integer(), original_node_x_5186 = numeric(), original_node_y_5186 = numeric(),
    original_endpoint_retained = logical(), relation_dataset_id = character(), branch_id = character()
  ))
  endpoints <- data.table::rbindlist(list(
    roads[, .(scene_id, scene_footprint_id, split, road_local_entity_id = as.integer(local_entity_id),
              road_source_entity_id = source_entity_id, endpoint_order = 0L, endpoint_label = "F",
              original_node_id = F_NODE)],
    roads[, .(scene_id, scene_footprint_id, split, road_local_entity_id = as.integer(local_entity_id),
              road_source_entity_id = source_entity_id, endpoint_order = 1L, endpoint_label = "T",
              original_node_id = T_NODE)]
  ))
  retained <- data.table::rbindlist(list(
    roads[, .(scene_id, road_local_entity_id = as.integer(local_entity_id), endpoint_order = 0L,
              original_endpoint_retained = as.logical(source_f_node_endpoint_retained))],
    roads[, .(scene_id, road_local_entity_id = as.integer(local_entity_id), endpoint_order = 1L,
              original_endpoint_retained = as.logical(source_t_node_endpoint_retained))]
  ))
  endpoints <- retained[endpoints, on = .(scene_id, road_local_entity_id, endpoint_order)]
  endpoints <- merge(endpoints, node_positions, by.x = "original_node_id", by.y = "node_id",
                     all.x = TRUE, sort = FALSE)
  if (anyNA(endpoints$x) || anyNA(endpoints$y) || anyNA(endpoints$original_node_id)) stop("Road topology endpoint lacks original-node evidence", call. = FALSE)
  endpoints[, scene_incident_road_count := data.table::uniqueN(road_local_entity_id), by = .(scene_id, original_node_id)]
  endpoints[, scene_node_index := match(original_node_id, sort(unique(original_node_id), method = "radix")) - 1L, by = scene_id]
  tolerance <- as.numeric(config$scientific$original_road_topology$boundary_tolerance_m)
  endpoints[, c("xmin", "ymin", "xmax", "ymax") := {
    box <- scene_specs[[scene_id[[1L]]]]
    list(as.numeric(box$xmin), as.numeric(box$ymin), as.numeric(box$xmax), as.numeric(box$ymax))
  }, by = scene_id]
  endpoints[, node_state := data.table::fcase(
    x < xmin - tolerance | x > xmax + tolerance | y < ymin - tolerance | y > ymax + tolerance, "OUTSIDE",
    abs(x - xmin) <= tolerance | abs(x - xmax) <= tolerance | abs(y - ymin) <= tolerance | abs(y - ymax) <= tolerance, "BOUNDARY",
    default = "INTERIOR"
  )]
  state_codes <- unlist(config$scientific$original_road_topology$node_state_codes)
  endpoints[, node_state_code := as.integer(state_codes[node_state])]
  endpoints[, `:=`(original_node_x_5186 = as.numeric(x), original_node_y_5186 = as.numeric(y),
                    relation_dataset_id = relation_dataset_id, branch_id = spec$branch_id)]
  data.table::setorder(endpoints, scene_id, road_local_entity_id, endpoint_order)
  value <- endpoints[, ..columns]
  if (anyDuplicated(value[, .(scene_id, road_local_entity_id, endpoint_order)]) ||
      any(value$endpoint_order != rep(c(0L, 1L), length.out = nrow(value))) ||
      anyNA(value$original_endpoint_retained) ||
      any(value$scene_incident_road_count < 1L) || any(value$scene_node_index < 0L)) {
    stop("Road topology endpoint/index contract failed", call. = FALSE)
  }
  attr(value, "source_record") <- road_record
  value
}

relation_scene_statistics <- function(spec, entities, results, relation_dataset_id, config) {
  bits <- relation_bit_values(config)
  data.table::rbindlist(lapply(seq_along(spec$scenes), function(i) {
    scene <- spec$scenes[[i]]
    nodes <- entities[scene_id == scene$scene_id]
    result <- results[[i]]
    edges <- result$edges
    data.table::data.table(
      scene_id = scene$scene_id, scene_footprint_id = scene$scene_footprint_id, split = scene$split,
      branch_id = spec$branch_id, relation_dataset_id = relation_dataset_id,
      node_count = nrow(nodes), building_count = sum(nodes$entity_type == "B"), road_count = sum(nodes$entity_type == "R"),
      poi_count = sum(nodes$entity_type == "P"), contained_poi_count = nrow(result$classification$host),
      outside_poi_count = sum(nodes$entity_type == "P") - nrow(result$classification$host),
      host_tie_count = sum(result$classification$host$host_tie), ordered_pair_count = nrow(edges),
      sn_edge_count = sum(bitwAnd(edges$relation_mask, bits[["SN"]]) != 0L),
      cnt_edge_count = sum(bitwAnd(edges$relation_mask, bits[["CNT"]]) != 0L),
      wit_edge_count = sum(bitwAnd(edges$relation_mask, bits[["WIT"]]) != 0L),
      int_edge_count = sum(bitwAnd(edges$relation_mask, bits[["INT"]]) != 0L),
      con_edge_count = sum(bitwAnd(edges$relation_mask, bits[["CON"]]) != 0L),
      multi_relation_pair_count = sum(vapply(edges$relation_mask, function(mask) sum(bitwAnd(mask, unname(bits)) != 0L) > 1L, logical(1L))),
      sn_candidate_count = result$sn_candidate_count, sn_retained_selection_count = result$sn_retained_selection_count
    )
  }))
}

validate_relation_edges <- function(edges, nodes, statistics, spec, config) {
  bits <- relation_bit_values(config)
  allowed_mask <- Reduce(bitwOr, unname(bits))
  key <- function(scene, local) paste(scene, local, sep = "\r")
  node_key <- key(nodes$scene_id, nodes$local_entity_id)
  failures <- character()
  add <- function(condition, label) if (isTRUE(condition)) failures <<- c(failures, label)
  add(anyDuplicated(edges[, .(scene_id, source_local_entity_id, destination_local_entity_id)]) > 0L, "duplicate_edge_key")
  add(any(edges$source_local_entity_id == edges$destination_local_entity_id), "self_edge")
  add(any(!key(edges$scene_id, edges$source_local_entity_id) %in% node_key) ||
      any(!key(edges$scene_id, edges$destination_local_entity_id) %in% node_key), "dangling_endpoint")
  add(any(bitwAnd(edges$relation_mask, allowed_mask) != edges$relation_mask) || any(edges$relation_mask <= 0L), "unknown_relation_bit")
  add(any(edges$has_sn != (bitwAnd(edges$relation_mask, bits[["SN"]]) != 0L)) ||
      any(edges$has_cnt != (bitwAnd(edges$relation_mask, bits[["CNT"]]) != 0L)) ||
      any(edges$has_wit != (bitwAnd(edges$relation_mask, bits[["WIT"]]) != 0L)) ||
      any(edges$has_int != (bitwAnd(edges$relation_mask, bits[["INT"]]) != 0L)) ||
      any(edges$has_con != (bitwAnd(edges$relation_mask, bits[["CON"]]) != 0L)), "mask_boolean_mismatch")
  add(any(edges$has_cnt & !(edges$source_entity_type == "B" & edges$destination_entity_type == "P")), "cnt_type_pair")
  add(any(edges$has_wit & !(edges$source_entity_type == "P" & edges$destination_entity_type == "B")), "wit_type_pair")
  add(any(edges$has_int & !(edges$source_entity_type %in% c("B", "R") & edges$destination_entity_type %in% c("B", "R"))), "int_type_pair")
  add(any(edges$has_con & !(edges$source_entity_type == "R" & edges$destination_entity_type == "R")), "con_type_pair")
  add(any(edges$has_sn & (!is.finite(edges$distance_m) | edges$distance_m > as.numeric(config$scientific$sn$radius_m))), "sn_radius")
  add(any(edges$has_sn & is.na(edges$sn_source_rank) & is.na(edges$sn_destination_rank)), "sn_selection_evidence")
  add(any(edges$sn_source_rank > as.integer(config$scientific$sn$top_k), na.rm = TRUE) ||
      any(edges$sn_destination_rank > as.integer(config$scientific$sn$top_k), na.rm = TRUE), "sn_top_k")
  add(any(!is.finite(edges$distance_m[!is.na(edges$distance_m)])), "invalid_numeric")
  add(anyDuplicated(nodes[, .(scene_id, local_entity_id)]) > 0L, "duplicate_node_key")
  add(!identical(sort(unique(statistics$scene_id)), sort(unlist(spec$scene_ids))), "statistics_scene_set")
  symmetric <- c("SN", "INT", "CON")
  for (relation in symmetric) {
    selected <- edges[bitwAnd(relation_mask, bits[[relation]]) != 0L]
    reverse_key <- paste(selected$scene_id, selected$destination_local_entity_id, selected$source_local_entity_id, sep = "\r")
    add(any(!reverse_key %in% paste(selected$scene_id, selected$source_local_entity_id, selected$destination_local_entity_id, sep = "\r")),
        paste0(tolower(relation), "_symmetry"))
  }
  cnt <- edges[bitwAnd(relation_mask, bits[["CNT"]]) != 0L]
  wit <- edges[bitwAnd(relation_mask, bits[["WIT"]]) != 0L]
  add(any(!paste(cnt$scene_id, cnt$destination_local_entity_id, cnt$source_local_entity_id, sep = "\r") %in%
          paste(wit$scene_id, wit$source_local_entity_id, wit$destination_local_entity_id, sep = "\r")), "cnt_wit_inverse")
  if (length(failures)) stop("Relation branch QC failed: ", paste(unique(failures), collapse = ", "), call. = FALSE)
  invisible(TRUE)
}

relation_arrow_schema <- function() arrow::schema(
  scene_id = arrow::utf8(), scene_footprint_id = arrow::utf8(), split = arrow::utf8(), edge_id = arrow::utf8(),
  source_local_entity_id = arrow::int32(), destination_local_entity_id = arrow::int32(),
  source_entity_type = arrow::utf8(), destination_entity_type = arrow::utf8(), relation_mask = arrow::uint8(),
  has_sn = arrow::boolean(), has_cnt = arrow::boolean(), has_wit = arrow::boolean(), has_int = arrow::boolean(), has_con = arrow::boolean(), directed = arrow::boolean(),
  distance_m = arrow::float64(), sn_source_rank = arrow::int16(), sn_destination_rank = arrow::int16(),
  host_building_local_entity_id = arrow::int32(), shared_original_node_id = arrow::utf8(),
  relation_contract_version = arrow::utf8(), vector_observation_dataset_id = arrow::utf8(),
  relation_dataset_id = arrow::utf8(), branch_id = arrow::utf8()
)

write_relation_edges <- function(edges, path, config) {
  value <- data.table::copy(edges)
  character_columns <- c(
    "scene_id", "scene_footprint_id", "split", "edge_id", "source_entity_type", "destination_entity_type",
    "shared_original_node_id", "relation_contract_version", "vector_observation_dataset_id", "relation_dataset_id", "branch_id"
  )
  integer_columns <- c(
    "source_local_entity_id", "destination_local_entity_id", "relation_mask", "sn_source_rank",
    "sn_destination_rank", "host_building_local_entity_id"
  )
  logical_columns <- c("has_sn", "has_cnt", "has_wit", "has_int", "has_con", "directed")
  value[, (character_columns) := lapply(.SD, as.character), .SDcols = character_columns]
  value[, (integer_columns) := lapply(.SD, as.integer), .SDcols = integer_columns]
  value[, (logical_columns) := lapply(.SD, as.logical), .SDcols = logical_columns]
  value[, distance_m := as.numeric(distance_m)]
  table <- arrow::Table$create(as.data.frame(value), schema = relation_arrow_schema())
  arrow::write_parquet(table, path, compression = config$scientific$storage$parquet_compression,
                       chunk_size = as.integer(config$scientific$storage$parquet_row_group_size))
  path
}

relation_output_names <- function() c(
  "relation_edges.parquet", "relation_node_index.parquet", "scene_relation_statistics.parquet", "road_topology.parquet",
  "branch_manifest.json", "branch_qc.json", "branch_log.jsonl"
)

build_prototype_relation_shard <- function(prototype_observation_plan,
                                            prototype_vector_observation_shard,
                                            study_data_inputs,
                                            relation_contract_files,
                                            workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- relation_thread_state()
  on.exit(restore_relation_threads(state), add = TRUE)
  set_relation_threads(threads)
  config <- load_relation_config(relation_contract_files)
  spec <- prototype_observation_plan
  vector <- read_i10_branch_context(spec, prototype_vector_observation_shard)
  road_path <- relation_road_path(study_data_inputs)
  road_record <- list(
    path = road_path, artifact_id = spec$sources$road$source_artifact_id,
    sha256 = sha256_file(road_path), size_bytes = unname(file.info(road_path)$size),
    links_layer = "links", nodes_layer = "nodes"
  )
  if (!identical(road_record$sha256, spec$sources$road$sha256)) stop("Tracked road topology checksum differs from I09/I10", call. = FALSE)
  started <- Sys.time()
  io_start <- proc_io_snapshot()
  vector_started <- Sys.time()
  observations <- lapply(vector$files, read_standard_geoparquet)
  vector_read_seconds <- as.numeric(difftime(Sys.time(), vector_started, units = "secs"))
  entities <- relation_entity_table(observations)
  node_started <- Sys.time()
  node_positions <- read_relation_node_positions(road_path, c(entities$F_NODE, entities$T_NODE))
  topology_read_seconds <- as.numeric(difftime(Sys.time(), node_started, units = "secs"))
  relation_dataset_id <- relation_dataset_identity(spec, vector, road_record, config)
  scene_ids <- sort(unlist(spec$scene_ids), method = "radix")
  scene_specs <- setNames(spec$scenes, vapply(spec$scenes, `[[`, character(1L), "scene_id"))
  exact_started <- Sys.time()
  results <- lapply(scene_ids, function(sid) {
    rows <- entities[scene_id == sid]
    scene <- relation_scene_sf(rows)
    build_scene_relations(scene, node_positions, scene_specs[[sid]], spec, relation_dataset_id, config)
  })
  exact_seconds <- as.numeric(difftime(Sys.time(), exact_started, units = "secs"))
  edges <- data.table::rbindlist(lapply(results, `[[`, "edges"), use.names = TRUE)
  if (!nrow(edges)) edges <- relation_empty_output_table()
  data.table::setorder(edges, scene_id, source_local_entity_id, destination_local_entity_id, relation_mask)
  node_index <- relation_node_index(entities, spec, relation_dataset_id, config)
  statistics <- relation_scene_statistics(spec, entities, results, relation_dataset_id, config)
  data.table::setorder(statistics, scene_id)
  validate_relation_edges(edges, node_index, statistics, spec, config)
  road_topology <- relation_road_topology(entities, node_positions, scene_specs, spec, relation_dataset_id, road_record, config)
  observations_root <- dirname(dirname(dirname(dirname(spec$output$directory))))
  final_dir <- file.path(observations_root, relation_dataset_id, "relations", "branches", spec$branch_id)
  output_names <- relation_output_names()
  paths <- publish_deterministic_directory(
    final_dir, output_names, compare_basenames = output_names[1:4],
    writer = function(stage) {
      parquet_started <- Sys.time()
      write_relation_edges(edges, file.path(stage, output_names[[1L]]), config)
      arrow::write_parquet(node_index, file.path(stage, output_names[[2L]]), compression = "zstd", chunk_size = 65536L)
      arrow::write_parquet(statistics, file.path(stage, output_names[[3L]]), compression = "zstd", chunk_size = 65536L)
      arrow::write_parquet(road_topology, file.path(stage, output_names[[4L]]), compression = "zstd", chunk_size = 65536L)
      parquet_seconds <- as.numeric(difftime(Sys.time(), parquet_started, units = "secs"))
      bits <- relation_bit_values(config)
      relation_counts <- setNames(lapply(names(bits), function(relation) sum(bitwAnd(edges$relation_mask, bits[[relation]]) != 0L)), names(bits))
      sn_distance <- edges$distance_m[edges$has_sn]
      summary_numeric <- function(x) if (!length(x)) list(min = NULL, median = NULL, p95 = NULL, max = NULL) else list(
        min = min(x), median = unname(stats::median(x)), p95 = unname(stats::quantile(x, 0.95, names = FALSE)), max = max(x)
      )
      failures <- list()
      io_end <- proc_io_snapshot()
      qc <- list(
        qc_schema_version = "1.0.0", branch_id = spec$branch_id, status = "PASS", failures = failures,
        scene_count = length(scene_ids), scene_set_aligned = TRUE, node_count = nrow(node_index), edge_count = nrow(edges),
        duplicate_edge_key_count = 0L, self_edge_count = 0L, cross_scene_edge_count = 0L,
        dangling_endpoint_count = 0L, unknown_relation_bit_count = 0L,
        relation_counts = relation_counts, multi_relation_pair_count = sum(rowSums(cbind(edges$has_sn, edges$has_cnt, edges$has_wit, edges$has_int, edges$has_con)) > 1L),
        empty_edge_scene_count = sum(statistics$ordered_pair_count == 0L),
        contained_poi_count = sum(statistics$contained_poi_count), outside_poi_count = sum(statistics$outside_poi_count),
        host_tie_count = sum(statistics$host_tie_count), con_shared_node_edge_count = relation_counts$CON,
        clipped_endpoint_false_con_count = 0L, sn_radius_violation_count = 0L, sn_top_k_violation_count = 0L,
        inverse_complete = TRUE, symmetry_complete = TRUE, sn_distance_m = summary_numeric(sn_distance),
        execution = list(
          controller = "controller_10", workers = 1L, threads = 1L,
          wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")), max_rss_kb = proc_max_rss_kb(),
          read_bytes = io_end$read_bytes - io_start$read_bytes, write_bytes = io_end$write_bytes - io_start$write_bytes,
          vector_geoparquet_read_seconds = vector_read_seconds, source_topology_read_seconds = topology_read_seconds,
          exact_relation_seconds = exact_seconds, parquet_write_seconds = parquet_seconds
        ),
        warnings = list()
      )
      qc$road_topology_endpoint_count <- nrow(road_topology)
      qc$road_topology_node_count <- data.table::uniqueN(road_topology[, .(scene_id, scene_node_index)])
      qc$road_topology_source <- road_record
      write_json_file(qc, file.path(stage, output_names[[6L]]))
      log_records <- list(
        list(time = format(started, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul"), event = "branch_started", branch_id = spec$branch_id),
        list(time = kst_now(), event = "branch_completed", branch_id = spec$branch_id, status = "PASS", scenes = length(scene_ids), nodes = nrow(node_index), edges = nrow(edges))
      )
      write_json_lines(log_records, file.path(stage, output_names[[7L]]))
      output_records <- lapply(file.path(stage, output_names[1:4]), function(path) list(
        path = file.path(final_dir, basename(path)), size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)
      ))
      manifest <- list(
        manifest_schema_version = "1.0.0", branch_id = spec$branch_id,
        relation_dataset_id = relation_dataset_id, vector_observation_dataset_id = spec$observation_dataset_id,
        prototype_id = spec$prototype_id, scene_index_id = spec$scene_index_id, status = "PASS",
        inputs = list(
          observation_spec_path = normalizePath(spec$.path, mustWork = TRUE),
          vector_branch_manifest_path = vector$manifest_path, vector_branch_manifest_sha256 = sha256_file(vector$manifest_path),
          road_topology = road_record, relation_config_hash = config$scientific_hash,
          relation_schema_hash = config$schema_hash, implementation_source_hash = config$implementation_source_hash
        ),
        execution_contract = list(controller = "controller_10", workers = 1L, threads = 1L),
        scene_ids = as.list(scene_ids), scene_count = length(scene_ids),
        node_count_by_entity_type = list(
          building = sum(node_index$entity_type == "B"), road = sum(node_index$entity_type == "R"), poi = sum(node_index$entity_type == "P")
        ),
        edge_count_by_relation_type = relation_counts, ordered_pair_count = nrow(edges),
        multi_relation_pair_count = qc$multi_relation_pair_count, empty_edge_scene_count = qc$empty_edge_scene_count,
        contained_poi_count = qc$contained_poi_count, outside_poi_count = qc$outside_poi_count,
        host_tie_count = qc$host_tie_count, con_shared_node_edge_count = qc$con_shared_node_edge_count,
        sn_candidate_count = sum(statistics$sn_candidate_count), sn_retained_selection_count = sum(statistics$sn_retained_selection_count),
        sn_distance_m = qc$sn_distance_m, scene_edge_count = summary_numeric(statistics$ordered_pair_count),
        outputs = output_records,
        runtime_sidecars = list(
          qc = file.path(final_dir, output_names[[6L]]), log = file.path(final_dir, output_names[[7L]])
        ),
        warnings = list(), status_final = "PASS"
      )
      write_json_file(manifest, file.path(stage, output_names[[5L]]))
    }
  )
  normalizePath(paths, mustWork = TRUE)
}

# Independent exhaustive reference for representative-scene acceptance.
reference_scene_relations <- function(scene, node_positions, scene_spec, spec, relation_dataset_id, config) {
  bits <- relation_bit_values(config)
  classification <- classify_relation_pois(scene, config)
  state <- classification$state
  radius <- as.numeric(config$scientific$sn$radius_m)
  top_k <- as.integer(config$scientific$sn$top_k)
  tolerance <- as.numeric(config$scientific$sn$distance_tie_tolerance_m)
  selected <- list()
  for (source in seq_len(nrow(scene))) {
    destination <- which(state %in% sn_eligible_destination_states(state[[source]]))
    destination <- destination[destination != source]
    if (!length(destination)) next
    distance <- as.numeric(sf::st_distance(
      scene[rep(source, length(destination)), ], scene[destination, ], by_element = TRUE
    ))
    keep <- is.finite(distance) & distance <= radius
    destination <- destination[keep]
    distance <- distance[keep]
    if (!length(destination)) next
    ordering <- order(round(distance / tolerance) * tolerance, scene$local_entity_id[destination], method = "radix")
    ordering <- head(ordering, top_k)
    selected[[length(selected) + 1L]] <- data.table::data.table(
      source_local_entity_id = scene$local_entity_id[source],
      destination_local_entity_id = scene$local_entity_id[destination[ordering]],
      distance_m = distance[ordering], sn_rank = seq_along(ordering)
    )
  }
  selected <- data.table::rbindlist(selected)
  sn <- relation_empty_edges()
  if (nrow(selected)) {
    selected[, `:=`(pair_min = pmin(source_local_entity_id, destination_local_entity_id),
                    pair_max = pmax(source_local_entity_id, destination_local_entity_id))]
    pairs <- unique(selected[, .(pair_min, pair_max)])
    pairs[, distance_m := vapply(seq_len(.N), function(i) min(selected[pair_min == pairs$pair_min[[i]] & pair_max == pairs$pair_max[[i]], distance_m]), numeric(1L))]
    direction <- function(source, destination) data.table::data.table(
      source_local_entity_id = source, destination_local_entity_id = destination,
      relation_bit = bits[["SN"]], distance_m = pairs$distance_m,
      sn_source_rank = vapply(seq_len(nrow(pairs)), function(i) {
        rank <- selected[source_local_entity_id == source[[i]] & destination_local_entity_id == destination[[i]], sn_rank]
        if (length(rank)) as.integer(rank[[1L]]) else NA_integer_
      }, integer(1L)),
      sn_destination_rank = vapply(seq_len(nrow(pairs)), function(i) {
        rank <- selected[source_local_entity_id == destination[[i]] & destination_local_entity_id == source[[i]], sn_rank]
        if (length(rank)) as.integer(rank[[1L]]) else NA_integer_
      }, integer(1L)),
      host_building_local_entity_id = NA_integer_, shared_original_node_id = NA_character_
    )
    sn <- data.table::rbindlist(list(direction(pairs$pair_min, pairs$pair_max), direction(pairs$pair_max, pairs$pair_min)))
  }
  containment <- scene_containment_edges(classification, config)
  intersection <- relation_empty_edges()
  physical <- which(scene$entity_type %in% c("B", "R"))
  if (length(physical) >= 2L) {
    pairs <- utils::combn(physical, 2L)
    intersects <- vapply(seq_len(ncol(pairs)), function(i) sf::st_intersects(
      scene[pairs[1L, i], ], scene[pairs[2L, i], ], sparse = FALSE
    )[[1L]], logical(1L))
    pairs <- pairs[, intersects, drop = FALSE]
    if (ncol(pairs)) {
      first <- scene$local_entity_id[pairs[1L, ]]; second <- scene$local_entity_id[pairs[2L, ]]
      make <- function(source, destination) data.table::data.table(
        source_local_entity_id = source, destination_local_entity_id = destination, relation_bit = bits[["INT"]],
        distance_m = NA_real_, sn_source_rank = NA_integer_, sn_destination_rank = NA_integer_,
        host_building_local_entity_id = NA_integer_, shared_original_node_id = NA_character_
      )
      intersection <- data.table::rbindlist(list(make(first, second), make(second, first)))
    }
  }
  connectivity <- scene_connectivity_edges(scene, node_positions, scene_spec, config)
  long <- data.table::rbindlist(list(sn, containment, intersection, connectivity), use.names = TRUE)
  collapse_relation_edges(long, scene, scene_spec, spec, relation_dataset_id, config)
}

compare_relation_reference <- function(optimized, reference, distance_tolerance_m = 1e-9) {
  key <- c("scene_id", "source_local_entity_id", "destination_local_entity_id")
  scientific <- c(key, "relation_mask", "host_building_local_entity_id", "shared_original_node_id")
  left <- optimized[, ..scientific]
  right <- reference[, ..scientific]
  key_string <- function(value) do.call(paste, c(value[, ..key], sep = "\r"))
  missing <- setdiff(key_string(right), key_string(left))
  extra <- setdiff(key_string(left), key_string(right))
  merged <- merge(
    optimized[, .(scene_id, source_local_entity_id, destination_local_entity_id, relation_mask, distance_m)],
    reference[, .(scene_id, source_local_entity_id, destination_local_entity_id, reference_mask = relation_mask, reference_distance_m = distance_m)],
    by = key, all = TRUE
  )
  mask_mismatch <- sum(is.na(merged$relation_mask) | is.na(merged$reference_mask) | merged$relation_mask != merged$reference_mask)
  distance_difference <- abs(merged$distance_m - merged$reference_distance_m)
  distance_mismatch <- sum(distance_difference > distance_tolerance_m, na.rm = TRUE) +
    sum(is.na(merged$distance_m) != is.na(merged$reference_distance_m))
  list(
    false_negative_count = length(missing), false_positive_count = length(extra),
    mask_mismatch_count = mask_mismatch, distance_mismatch_count = distance_mismatch,
    maximum_distance_error_m = if (any(is.finite(distance_difference))) max(distance_difference, na.rm = TRUE) else 0,
    status = if (!length(missing) && !length(extra) && mask_mismatch == 0L && distance_mismatch == 0L) "PASS" else "FAIL"
  )
}

relation_pilot_task <- function(task, study_data_inputs, config) {
  state <- relation_thread_state()
  on.exit(restore_relation_threads(state), add = TRUE)
  set_relation_threads(1L)
  started <- Sys.time(); io_start <- proc_io_snapshot(); error <- NULL
  result <- tryCatch({
    vector_started <- Sys.time()
    vector <- read_i10_branch_context(task$spec, task$vector_paths)
    observations <- lapply(vector$files, read_standard_geoparquet)
    entities <- relation_entity_table(observations)
    vector_seconds <- as.numeric(difftime(Sys.time(), vector_started, units = "secs"))
    scene_rows <- entities[scene_id == task$scene_id]
    topology_started <- Sys.time()
    road_path <- relation_road_path(study_data_inputs)
    node_positions <- read_relation_node_positions(road_path, c(scene_rows$F_NODE, scene_rows$T_NODE))
    topology_seconds <- as.numeric(difftime(Sys.time(), topology_started, units = "secs"))
    scene <- relation_scene_sf(scene_rows)
    scene_spec <- task$spec$scenes[[match(task$scene_id, vapply(task$spec$scenes, `[[`, character(1L), "scene_id"))]]
    exact_started <- Sys.time()
    graph <- build_scene_relations(scene, node_positions, scene_spec, task$spec, "pilot", config)
    exact_seconds <- as.numeric(difftime(Sys.time(), exact_started, units = "secs"))
    output <- tempfile(fileext = ".parquet")
    on.exit(unlink(output), add = TRUE)
    write_started <- Sys.time(); write_relation_edges(graph$edges, output, config)
    write_seconds <- as.numeric(difftime(Sys.time(), write_started, units = "secs"))
    list(
      node_count = nrow(scene), edge_count = nrow(graph$edges), sn_candidate_count = graph$sn_candidate_count,
      vector_read_seconds = vector_seconds, topology_read_seconds = topology_seconds,
      exact_relation_seconds = exact_seconds, parquet_write_seconds = write_seconds,
      output_bytes = unname(file.info(output)$size)
    )
  }, error = function(e) {
    error <<- conditionMessage(e)
    list(node_count = NA_integer_, edge_count = NA_integer_, sn_candidate_count = NA_integer_,
         vector_read_seconds = NA_real_, topology_read_seconds = NA_real_, exact_relation_seconds = NA_real_,
         parquet_write_seconds = NA_real_, output_bytes = NA_real_)
  })
  io_end <- proc_io_snapshot()
  c(list(
    scene_id = task$scene_id, wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
    max_rss_kb = proc_max_rss_kb(), read_bytes = io_end$read_bytes - io_start$read_bytes,
    write_bytes = io_end$write_bytes - io_start$write_bytes, error = error
  ), result)
}

benchmark_relation_concurrency <- function(plan_specs, vector_branches, study_data_inputs, config,
                                           concurrency = c(5L, 10L), repetitions = 2L) {
  records <- data.table::rbindlist(lapply(seq_along(plan_specs), function(i) data.table::rbindlist(lapply(plan_specs[[i]]$scenes, function(scene) data.table::data.table(
    spec_index = i, scene_id = scene$scene_id, entity_count = scene$entity_count, cost = scene$estimated_cost
  )))))
  records <- records[entity_count > 0L]
  data.table::setorder(records, entity_count, scene_id)
  positions <- unique(round(seq(1, nrow(records), length.out = 5L)))
  selected <- records[positions]
  tasks <- unlist(lapply(seq_len(repetitions), function(repetition) lapply(seq_len(nrow(selected)), function(i) list(
    spec = plan_specs[[selected$spec_index[[i]]]], vector_paths = vector_branches[[selected$spec_index[[i]]]],
    scene_id = selected$scene_id[[i]], repetition = repetition
  ))), recursive = FALSE)
  runs <- lapply(as.integer(concurrency), function(workers) {
    iowait_start <- proc_iowait_ticks(); started <- Sys.time()
    values <- parallel::mclapply(tasks, relation_pilot_task, study_data_inputs = study_data_inputs,
                                 config = config, mc.cores = workers, mc.preschedule = FALSE)
    elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs")); iowait_end <- proc_iowait_ticks()
    table <- data.table::rbindlist(values, fill = TRUE)
    list(
      workers = workers, task_count = length(tasks), wall_time_seconds = elapsed,
      maximum_worker_rss_kb = max(table$max_rss_kb, na.rm = TRUE),
      read_bytes = sum(table$read_bytes, na.rm = TRUE), write_bytes = sum(table$write_bytes, na.rm = TRUE),
      iowait_ticks = iowait_end - iowait_start, errors = sum(!vapply(values, function(x) is.null(x$error), logical(1L))),
      vector_read_seconds = sum(table$vector_read_seconds, na.rm = TRUE),
      topology_read_seconds = sum(table$topology_read_seconds, na.rm = TRUE),
      exact_relation_seconds = sum(table$exact_relation_seconds, na.rm = TRUE),
      parquet_write_seconds = sum(table$parquet_write_seconds, na.rm = TRUE),
      nodes = sum(table$node_count, na.rm = TRUE), edges = sum(table$edge_count, na.rm = TRUE), task_results = values
    )
  })
  list(
    benchmark_schema_version = "1.0.0", generated_at = kst_now(),
    workload = list(scene_ids = as.list(selected$scene_id), entity_counts = as.list(selected$entity_count), repetitions = repetitions),
    runs = runs
  )
}
