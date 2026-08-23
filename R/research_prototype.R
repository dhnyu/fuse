read_layer_geometry <- function(path, layer, geometry_column = "geom") {
  query <- sprintf('SELECT "%s" FROM "%s"', geometry_column, layer)
  sf::st_read(path, query = query, quiet = TRUE)
}

intersection_proxy_counts <- function(scenes, features) {
  as.integer(lengths(sf::st_intersects(scenes, features, sparse = TRUE)))
}

classify_density_proxy <- function(total, probabilities) {
  cuts <- as.numeric(stats::quantile(total, probs = probabilities, names = FALSE, type = 8L))
  labels <- rep("tail", length(total))
  labels[total <= cuts[[3L]]] <- "high"
  labels[total <= cuts[[2L]]] <- "middle"
  labels[total <= cuts[[1L]]] <- "low"
  labels
}

dominant_proxy_type <- function(building, road, poi) {
  matrix <- cbind(building = building, road = road, poi = poi)
  totals <- rowSums(matrix)
  shares <- matrix / pmax(totals, 1)
  names <- colnames(matrix)[max.col(shares, ties.method = "first")]
  names[totals == 0] <- "empty"
  names
}

hash_priority <- function(scene_id, seed) {
  vapply(scene_id, function(id) {
    digest::digest(paste(seed, id, sep = "|"), algo = "sha256", serialize = FALSE)
  }, character(1L))
}

balanced_stratified_indices <- function(data, count, seed) {
  if (nrow(data) < count) stop("Prototype split has fewer scenes than requested", call. = FALSE)
  data$priority__ <- hash_priority(data$scene_id, seed)
  groups <- split(seq_len(nrow(data)), data$selection_strata)
  groups <- lapply(groups, function(index) index[order(data$priority__[index], data$scene_id[index], method = "radix")])
  group_names <- sort(names(groups), method = "radix")
  selected <- integer()
  cursor <- setNames(rep(1L, length(groups)), group_names)
  while (length(selected) < count) {
    progressed <- FALSE
    for (group in group_names) {
      position <- cursor[[group]]
      if (position <= length(groups[[group]])) {
        selected <- c(selected, groups[[group]][[position]])
        cursor[[group]] <- position + 1L
        progressed <- TRUE
        if (length(selected) == count) break
      }
    }
    if (!progressed) stop("Prototype balanced selection exhausted unexpectedly", call. = FALSE)
  }
  selected
}

validate_prototype_selection <- function(value, contract, config) {
  expected <- unlist(config$scene$prototype$counts)
  actual <- table(value$split)
  failures <- character()
  if (!all(as.integer(actual[names(expected)]) == as.integer(expected))) failures <- c(failures, "split_counts")
  if (anyDuplicated(value$scene_id) || anyDuplicated(value$scene_footprint_id)) failures <- c(failures, "duplicate_ids")
  if (!all(sf::st_is_valid(value))) failures <- c(failures, "invalid_geometry")
  required_proxy <- c(
    "building_intersection_proxy", "road_intersection_proxy", "poi_within_proxy",
    "road_node_within_proxy", "boundary_distance_m"
  )
  if (any(!stats::complete.cases(sf::st_drop_geometry(value)[, required_proxy]))) failures <- c(failures, "missing_proxy")
  if (!all(value$proxy_is_exact_membership == FALSE)) failures <- c(failures, "proxy_semantics")
  list(
    status = if (length(failures)) "FAIL" else "PASS",
    failures = failures,
    row_count = nrow(value),
    split_counts = as.list(actual),
    scene_id_unique = !anyDuplicated(value$scene_id),
    scene_footprint_id_unique = !anyDuplicated(value$scene_footprint_id),
    density_strata = as.list(table(value$density_stratum)),
    boundary_classes = as.list(table(value$boundary_class)),
    composition_classes = as.list(table(value$dominant_entity_proxy)),
    exact_membership_claimed = FALSE,
    seed = contract$randomness$prototype_seed
  )
}

build_prototype_scene_selection <- function(spatial_scene_index, study_data_inputs,
                                            prototype_runtime_inputs, methodology_contract,
                                            research_config_files,
                                            workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- capture_native_thread_state()
  on.exit(restore_native_thread_state(state), add = TRUE)
  set_native_thread_limits(threads)
  config <- load_research_config(research_config_files)
  contract <- jsonlite::read_json(
    artifact_path(methodology_contract, "methodology_contract.json"), simplifyVector = FALSE
  )
  index_path <- artifact_path(spatial_scene_index, "scene_index.parquet")
  index_manifest_path <- artifact_path(spatial_scene_index, "scene_index_manifest.json")
  index <- suppressWarnings(sfarrow::st_read_parquet(index_path))
  index_manifest <- jsonlite::read_json(index_manifest_path, simplifyVector = FALSE)
  inputs <- setNames(normalizePath(study_data_inputs, mustWork = TRUE), names(config$paths$inputs))
  runtime <- runtime_mirror_role_paths(prototype_runtime_inputs)

  layers <- config$paths$layers
  buildings <- read_layer_geometry(runtime[["building"]], layers$building)
  roads <- read_layer_geometry(runtime[["road"]], layers$road_links)
  road_nodes <- read_layer_geometry(runtime[["road"]], layers$road_nodes)
  pois <- read_layer_geometry(runtime[["poi"]], layers$poi)
  proxy <- data.table::as.data.table(sf::st_drop_geometry(index))
  proxy[, building_intersection_proxy := intersection_proxy_counts(index, buildings)]
  rm(buildings)
  gc(verbose = FALSE)
  proxy[, road_intersection_proxy := intersection_proxy_counts(index, roads)]
  rm(roads)
  gc(verbose = FALSE)
  proxy[, poi_within_proxy := intersection_proxy_counts(index, pois)]
  rm(pois)
  gc(verbose = FALSE)
  proxy[, road_node_within_proxy := intersection_proxy_counts(index, road_nodes)]
  rm(road_nodes)
  gc(verbose = FALSE)

  boundary <- sf::st_read(runtime[["boundary"]], layers$boundary, quiet = TRUE)
  centers <- sf::st_as_sf(
    proxy, coords = c("center_x_5186", "center_y_5186"), crs = 5186, remove = FALSE
  )
  proxy[, boundary_distance_m := as.numeric(sf::st_distance(
    centers, sf::st_boundary(sf::st_union(boundary)), by_element = FALSE
  )[, 1L])]
  proxy[, total_entity_proxy := building_intersection_proxy + road_intersection_proxy + poi_within_proxy]
  proxy[, density_stratum := classify_density_proxy(
    total_entity_proxy, unlist(config$scene$prototype$density_quantiles)
  ), by = split]
  proxy[, boundary_class := ifelse(
    boundary_distance_m <= config$scene$prototype$boundary_proximity_m,
    "boundary_near", "interior"
  )]
  proxy[, dominant_entity_proxy := dominant_proxy_type(
    building_intersection_proxy, road_intersection_proxy, poi_within_proxy
  )]
  proxy[, selection_strata := paste(density_stratum, boundary_class, dominant_entity_proxy, sep = "|")]
  proxy[, proxy_is_exact_membership := FALSE]

  expected <- unlist(config$scene$prototype$counts)
  selected_rows <- unlist(lapply(names(expected), function(split_name) {
    rows <- which(proxy$split == split_name)
    local <- balanced_stratified_indices(
      proxy[rows], as.integer(expected[[split_name]]),
      as.integer(contract$randomness$prototype_seed) + match(split_name, names(expected)) - 1L
    )
    rows[local]
  }), use.names = FALSE)
  selected_proxy <- proxy[selected_rows]
  selected_proxy[, selection_reason := paste0(
    "balanced_pre_membership_proxy:", selection_strata,
    ";total=", total_entity_proxy,
    ";boundary_m=", format(round(boundary_distance_m, 3), nsmall = 3)
  )]
  selected_proxy[, seed := as.integer(contract$randomness$prototype_seed)]
  selected_proxy[, input_manifest_id := contract$input_contract$inventory_id]
  selected_proxy[, study_manifest_sha256 := contract$input_contract$study_manifest_sha256]
  data.table::setorder(selected_proxy, split, selection_strata, scene_id)
  selected_geometry <- sf::st_geometry(index)[match(selected_proxy$scene_id, index$scene_id)]
  selected <- sf::st_sf(as.data.frame(selected_proxy), geometry = selected_geometry, crs = 5186)
  selected <- selected[, c(
    "scene_id", "scene_footprint_id", "split", "center_x_5186", "center_y_5186",
    "building_intersection_proxy", "road_intersection_proxy", "poi_within_proxy",
    "road_node_within_proxy", "boundary_distance_m", "total_entity_proxy",
    "density_stratum", "boundary_class", "dominant_entity_proxy", "selection_strata",
    "selection_reason", "proxy_is_exact_membership", "seed", "input_manifest_id",
    "study_manifest_sha256", "geometry"
  )]
  qc <- validate_prototype_selection(selected, contract, config)
  if (!identical(qc$status, "PASS")) stop("Prototype selection QC failed: ", paste(qc$failures, collapse = ", "), call. = FALSE)

  identity <- list(
    scene_index_id = index_manifest$scene_index_id,
    scene_index_sha256 = sha256_file(index_path),
    study_manifest_sha256 = contract$input_contract$study_manifest_sha256,
    prototype_schema_version = config$scene$prototype_schema_version,
    prototype_config = config$scene$prototype,
    implementation_sha256 = sha256_file(file.path(config$paths$repository$root, "R/research_prototype.R"))
  )
  prototype_id <- short_hash_id("pro_", identity)
  final_dir <- file.path(
    config$paths$outputs$scene_root, "index", index_manifest$scene_index_id,
    "prototype", prototype_id
  )
  output_names <- c(
    "prototype_scene_index.parquet", "prototype_scene_index_manifest.json",
    "prototype_scene_index_qc.json"
  )
  existing_parquet <- file.path(final_dir, output_names[[1L]])
  if (file.exists(existing_parquet)) {
    existing <- suppressWarnings(sfarrow::st_read_parquet(existing_parquet))
    comparable <- c(
      "scene_id", "scene_footprint_id", "selection_strata",
      "building_intersection_proxy", "road_intersection_proxy", "poi_within_proxy",
      "road_node_within_proxy"
    )
    if (!identical(sf::st_drop_geometry(selected)[, comparable], sf::st_drop_geometry(existing)[, comparable])) {
      stop("Determinism check failed against the existing prototype selection", call. = FALSE)
    }
  }
  publish_bundle(final_dir, output_names, function(stage) {
    parquet <- file.path(stage, output_names[[1L]])
    write_geo_parquet(selected, parquet)
    round_trip <- suppressWarnings(sfarrow::st_read_parquet(parquet))
    if (nrow(round_trip) != 320L || sf::st_crs(round_trip)$epsg != 5186L || anyDuplicated(round_trip$scene_id)) {
      stop("Prototype GeoParquet round-trip validation failed", call. = FALSE)
    }
    manifest <- list(
      manifest_schema_version = "1.0.0",
      prototype_id = prototype_id,
      generated_at = kst_now(),
      status = "PASS",
      identity = identity,
      row_count = nrow(selected),
      split_counts = qc$split_counts,
      proxy_semantics = list(
        exact_membership = FALSE,
        definition = config$scene$prototype$proxy_definition,
        building = "scene-footprint intersection count using one bulk read and a GEOS spatial index",
        road = "scene-footprint link intersection count using one bulk read and a GEOS spatial index",
        poi = "scene-footprint point intersection count using one bulk read and a GEOS spatial index",
        road_node = "scene-footprint endpoint/node intersection count using one bulk read and a GEOS spatial index"
      ),
      parquet_sha256 = sha256_file(parquet)
    )
    write_json_file(manifest, file.path(stage, output_names[[2L]]))
    write_json_file(c(list(prototype_id = prototype_id, generated_at = kst_now()), qc), file.path(stage, output_names[[3L]]))
  })
}
