observation_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/vector_observation.yml",
    "config/vector_observation_runtime.yml",
    "config/schemas/vector_observation_branch.schema.json",
    "python/write_geoparquet.py",
    "R/vector_observations.R"
  ))
}

load_observation_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c(
    "vector_observation.yml", "vector_observation_runtime.yml",
    "vector_observation_branch.schema.json", "write_geoparquet.py",
    "vector_observations.R"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing vector observation contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  scientific <- yaml::read_yaml(by_name[["vector_observation.yml"]])
  runtime <- yaml::read_yaml(by_name[["vector_observation_runtime.yml"]])
  validate_observation_config(scientific, runtime)
  repository_root <- dirname(dirname(by_name[["vector_observation.yml"]]))
  implementation_file <- normalizePath(file.path(repository_root, "R/vector_observations.R"), mustWork = TRUE)
  list(
    scientific = scientific,
    runtime = runtime,
    schema_file = by_name[["vector_observation_branch.schema.json"]],
    writer_file = by_name[["write_geoparquet.py"]],
    implementation_file = implementation_file,
    scientific_hash = sha256_file(by_name[["vector_observation.yml"]]),
    runtime_hash = sha256_file(by_name[["vector_observation_runtime.yml"]]),
    schema_hash = sha256_file(by_name[["vector_observation_branch.schema.json"]]),
    writer_hash = sha256_file(by_name[["write_geoparquet.py"]]),
    implementation_source_hash = sha256_file(implementation_file)
  )
}

validate_observation_config <- function(scientific, runtime) {
  checks <- c(
    epsg = identical(as.integer(scientific$processing_epsg), 5186L),
    local_id_type = identical(scientific$local_entity_id$type, "int32"),
    local_id_base = identical(as.integer(scientific$local_entity_id$base), 0L),
    local_id_order = identical(unlist(scientific$local_entity_id$entity_type_rank), c("B", "R", "P")),
    buffer = identical(as.numeric(scientific$geometry$scientific_buffer_m), 0),
    writer = identical(scientific$writer$implementation, "python_geopandas_pyarrow"),
    geoparquet = identical(scientific$writer$geoparquet_version, "1.1.0"),
    encoding = identical(scientific$writer$geometry_encoding, "WKB"),
    controller = identical(runtime$controller, "controller_40"),
    workers = identical(as.integer(runtime$branch_workers), 1L),
    threads = identical(as.integer(runtime$threads_per_worker), 1L)
  )
  if (any(!checks)) stop("Vector observation contract mismatch: ", paste(names(checks)[!checks], collapse = ", "), call. = FALSE)
  required_building <- c("A9", "A11", "A14", "A14_source_state")
  required_road <- c("LANES", "ROAD_RANK", "ROAD_TYPE", "F_NODE", "T_NODE")
  required_poi <- unlist(scientific$attributes$poi$preserved)
  if (!all(required_building %in% unlist(scientific$attributes$building$preserved)) ||
      !all(required_road %in% unlist(scientific$attributes$road$preserved)) ||
      length(required_poi) != 19L) {
    stop("Vector observation source attribute contract is incomplete", call. = FALSE)
  }
  invisible(TRUE)
}

observation_thread_state <- function() membership_thread_state()

set_observation_threads <- function(threads = 1L) set_membership_threads(threads)

restore_observation_threads <- function(state) restore_membership_threads(state)

sql_identifier <- function(x) paste0('"', gsub('"', '""', x, fixed = TRUE), '"')

sql_string <- function(x) paste0("'", gsub("'", "''", x, fixed = TRUE), "'")

read_source_entities_by_id <- function(source, ids, fields = character(), chunk_size = 1000L) {
  ids <- unique(as.character(ids))
  ids <- ids[order(ids, method = "radix")]
  if (!length(ids)) {
    attributes <- as.data.frame(setNames(rep(list(character()), length(fields)), fields), stringsAsFactors = FALSE)
    empty <- sf::st_sf(cbind(data.frame(source_entity_id = character()), attributes), geometry = sf::st_sfc(crs = 5186L))
    return(empty)
  }
  fields <- unique(as.character(fields))
  select <- c(
    paste0(sql_identifier(source$source_id_column), " AS source_entity_id"),
    vapply(fields, sql_identifier, character(1L)),
    "geom"
  )
  chunks <- split(ids, ceiling(seq_along(ids) / as.integer(chunk_size)))
  values <- lapply(chunks, function(chunk) {
    query <- paste0(
      "SELECT ", paste(select, collapse = ", "), " FROM ", sql_identifier(source$layer),
      " WHERE ", sql_identifier(source$source_id_column), " IN (",
      paste(vapply(chunk, sql_string, character(1L)), collapse = ","), ")"
    )
    sf::st_read(source$path, query = query, quiet = TRUE, stringsAsFactors = FALSE, int64_as_string = TRUE)
  })
  value <- do.call(rbind, values)
  value$source_entity_id <- as.character(value$source_entity_id)
  if (nrow(value) != length(ids) || anyDuplicated(value$source_entity_id) || !setequal(value$source_entity_id, ids)) {
    stop("Source ID lookup was incomplete or duplicated for ", source$role, call. = FALSE)
  }
  value[order(value$source_entity_id, method = "radix"), , drop = FALSE]
}

geometry_coordinate_count <- function(geometry) {
  vapply(geometry, function(x) {
    if (sf::st_is_empty(x)) return(0L)
    nrow(sf::st_coordinates(x))
  }, integer(1L))
}

geometry_component_count <- function(geometry) {
  vapply(geometry, function(x) {
    type <- as.character(sf::st_geometry_type(x))
    if (type %in% c("MULTIPOLYGON", "MULTILINESTRING", "MULTIPOINT")) length(x) else 1L
  }, integer(1L))
}

geometry_hole_count <- function(geometry) {
  vapply(geometry, function(x) {
    type <- as.character(sf::st_geometry_type(x))
    if (type == "POLYGON") return(max(length(x) - 1L, 0L))
    if (type == "MULTIPOLYGON") return(sum(vapply(x, function(p) max(length(p) - 1L, 0L), integer(1L))))
    0L
  }, integer(1L))
}

geometry_wkb <- function(geometry) {
  sf::st_as_binary(geometry, EWKB = FALSE, endian = "little")
}

wkb_fingerprint <- function(wkb) {
  vapply(wkb, digest::digest, character(1L), algo = "sha256", serialize = FALSE)
}

observation_source_fields <- function(config, role) {
  unlist(config$scientific$attributes[[role]]$preserved)
}

validate_observation_spec <- function(path) {
  value <- jsonlite::read_json(path, simplifyVector = FALSE)
  scene_ids <- unlist(value$scene_ids, use.names = FALSE)
  records <- vapply(value$scenes, `[[`, character(1L), "scene_id")
  if (!identical(sort(scene_ids, method = "radix"), sort(records, method = "radix")) || anyDuplicated(scene_ids)) {
    stop("Observation spec scene contract failed: ", path, call. = FALSE)
  }
  required <- c(
    "branch_id", "scope_id", "membership_dataset_id", "scene_index_id",
    "scene_ids", "scenes", "estimated_counts", "estimated_geometry",
    "shared_grouping", "sources", "membership_parquets", "contract", "output", "execution"
  )
  missing <- setdiff(required, names(value))
  if (length(missing)) stop("Observation spec missing fields: ", paste(missing, collapse = ", "), call. = FALSE)
  invisible(TRUE)
}

observation_scene_sf <- function(spec) membership_scene_sf(spec)

read_branch_membership <- function(spec, verify_estimate = TRUE) {
  tables <- lapply(spec$membership_parquets, arrow::read_parquet, as_data_frame = TRUE)
  value <- data.table::rbindlist(tables, use.names = TRUE)
  value <- value[scene_id %in% unlist(spec$scene_ids)]
  data.table::setorder(value, scene_id, entity_type, source_entity_id)
  expected <- unlist(spec$estimated_counts[c("building", "road", "poi")])
  actual <- value[, .N, by = entity_type]
  counts <- setNames(actual$N, actual$entity_type)
  counts <- counts[c(B = "B", R = "R", P = "P")]
  counts[is.na(counts)] <- 0L
  if (isTRUE(verify_estimate) && !identical(as.integer(counts), as.integer(expected))) stop("Observation spec membership count mismatch", call. = FALSE)
  value
}

assign_local_entity_ids <- function(membership, config) {
  rank <- setNames(seq_along(config$scientific$local_entity_id$entity_type_rank), unlist(config$scientific$local_entity_id$entity_type_rank))
  value <- data.table::copy(membership)
  value[, type_rank__ := unname(rank[entity_type])]
  data.table::setorder(value, scene_id, type_rank__, source_entity_id)
  value[, local_entity_id := as.integer(seq_len(.N) - 1L), by = scene_id]
  value[, type_rank__ := NULL]
  if (anyDuplicated(value[, .(scene_id, local_entity_id)]) || anyDuplicated(value[, .(scene_id, entity_type, source_entity_id)])) {
    stop("Deterministic local entity ID invariant failed", call. = FALSE)
  }
  value
}

polygonal_only <- function(geometry) {
  type <- as.character(sf::st_geometry_type(geometry))
  if (type == "POLYGON" || type == "MULTIPOLYGON") return(geometry)
  extracted <- suppressWarnings(sf::st_collection_extract(sf::st_sfc(geometry, crs = 5186L), "POLYGON"))
  if (!length(extracted)) return(sf::st_polygon())
  if (length(extracted) == 1L) extracted[[1L]] else sf::st_multipolygon(lapply(extracted, unclass))
}

lineal_only <- function(geometry) {
  type <- as.character(sf::st_geometry_type(geometry))
  if (type == "LINESTRING" || type == "MULTILINESTRING") return(geometry)
  extracted <- suppressWarnings(sf::st_collection_extract(sf::st_sfc(geometry, crs = 5186L), "LINESTRING"))
  if (!length(extracted)) return(sf::st_linestring())
  if (length(extracted) == 1L) extracted[[1L]] else sf::st_multilinestring(lapply(extracted, unclass))
}

clip_geometry_by_scene <- function(source, membership, scenes, role) {
  source_index <- match(membership$source_entity_id, source$source_entity_id)
  if (anyNA(source_index)) stop("Membership source geometry lookup failed for ", role, call. = FALSE)
  output <- vector("list", nrow(membership))
  for (scene_id in unique(membership$scene_id)) {
    rows <- which(membership$scene_id == scene_id)
    footprint <- sf::st_geometry(scenes)[match(scene_id, scenes$scene_id)]
    geometry <- sf::st_geometry(source)[source_index[rows]]
    if (identical(role, "poi")) {
      output[rows] <- as.list(geometry)
    } else {
      clipped <- suppressWarnings(sf::st_intersection(geometry, footprint))
      if (length(clipped) != length(rows)) stop("Clipping result cardinality changed for ", role, call. = FALSE)
      output[rows] <- lapply(clipped, if (role == "building") polygonal_only else lineal_only)
    }
  }
  sf::st_sfc(output, crs = 5186L)
}

geometry_bbox_centers <- function(geometry) {
  if (!length(geometry)) {
    value <- matrix(numeric(), nrow = 0L, ncol = 2L)
    colnames(value) <- c("x", "y")
    return(value)
  }
  value <- t(vapply(geometry, function(x) {
    box <- sf::st_bbox(x)
    c(x = (box[["xmin"]] + box[["xmax"]]) / 2, y = (box[["ymin"]] + box[["ymax"]]) / 2)
  }, numeric(2L)))
  colnames(value) <- c("x", "y")
  value
}

line_endpoint_summary <- function(geometry) {
  if (!length(geometry)) {
    result <- matrix(numeric(), nrow = 0L, ncol = 5L)
    colnames(result) <- c("start_x", "start_y", "end_x", "end_y", "endpoint_count")
    return(result)
  }
  values <- lapply(geometry, function(x) {
    coordinates <- sf::st_coordinates(x)
    if (!nrow(coordinates)) return(c(NA_real_, NA_real_, NA_real_, NA_real_, 0))
    group_columns <- intersect(c("L1", "L2", "L3"), colnames(coordinates))
    if (length(group_columns)) {
      group <- interaction(as.data.frame(coordinates[, group_columns, drop = FALSE]), drop = TRUE, lex.order = TRUE)
      parts <- split(seq_len(nrow(coordinates)), group)
    } else {
      parts <- list(seq_len(nrow(coordinates)))
    }
    endpoints <- do.call(rbind, lapply(parts, function(index) coordinates[c(index[[1L]], tail(index, 1L)), c("X", "Y"), drop = FALSE]))
    c(endpoints[1, 1], endpoints[1, 2], endpoints[nrow(endpoints), 1], endpoints[nrow(endpoints), 2], nrow(endpoints))
  })
  result <- do.call(rbind, values)
  colnames(result) <- c("start_x", "start_y", "end_x", "end_y", "endpoint_count")
  result
}

common_observation_columns <- function(membership, source, observed_geometry, scenes, spec, config) {
  source_index <- match(membership$source_entity_id, source$source_entity_id)
  scene_index <- match(membership$scene_id, scenes$scene_id)
  source_geometry <- sf::st_geometry(source)[source_index]
  source_wkb <- geometry_wkb(source_geometry)
  observed_wkb <- geometry_wkb(observed_geometry)
  centers <- geometry_bbox_centers(observed_geometry)
  scene_centers <- geometry_bbox_centers(sf::st_geometry(scenes)[scene_index])
  data.table::data.table(
    scene_id = membership$scene_id,
    scene_footprint_id = membership$scene_footprint_id,
    split = membership$split,
    entity_type = membership$entity_type,
    source_entity_id = membership$source_entity_id,
    local_entity_id = as.integer(membership$local_entity_id),
    source_artifact_id = membership$source_artifact_id,
    membership_dataset_id = spec$membership_dataset_id,
    observation_contract_version = config$scientific$observation_contract_version,
    source_geometry_fingerprint = wkb_fingerprint(source_wkb),
    observed_geometry_fingerprint = wkb_fingerprint(observed_wkb),
    source_geometry_wkb = unclass(source_wkb),
    scene_center_x_5186 = scene_centers[, "x"],
    scene_center_y_5186 = scene_centers[, "y"],
    observed_center_x_5186 = centers[, "x"],
    observed_center_y_5186 = centers[, "y"],
    relative_center_x_m = centers[, "x"] - scene_centers[, "x"],
    relative_center_y_m = centers[, "y"] - scene_centers[, "y"],
    source_coordinate_count = geometry_coordinate_count(source_geometry),
    observed_coordinate_count = geometry_coordinate_count(observed_geometry),
    source_component_count = geometry_component_count(source_geometry),
    observed_component_count = geometry_component_count(observed_geometry),
    source_hole_count = geometry_hole_count(source_geometry),
    observed_hole_count = geometry_hole_count(observed_geometry),
    is_clipped = wkb_fingerprint(source_wkb) != wkb_fingerprint(observed_wkb),
    observed_geometry = unclass(observed_wkb)
  )
}

build_role_observations <- function(role, membership, source, scenes, spec, config) {
  observed <- clip_geometry_by_scene(source, membership, scenes, role)
  common <- common_observation_columns(membership, source, observed, scenes, spec, config)
  source_index <- match(membership$source_entity_id, source$source_entity_id)
  source_geometry <- sf::st_geometry(source)[source_index]
  tolerance <- config$scientific$geometry$numerical_tolerance
  if (any(sf::st_is_empty(observed)) || any(!sf::st_is_valid(observed))) {
    stop("Observed geometry is empty or invalid for ", role, call. = FALSE)
  }
  types <- as.character(sf::st_geometry_type(observed))
  expected <- switch(role,
    building = c("POLYGON", "MULTIPOLYGON"),
    road = c("LINESTRING", "MULTILINESTRING"),
    poi = "POINT"
  )
  if (any(!types %in% expected)) stop("Observed geometry family mismatch for ", role, call. = FALSE)
  source_values <- sf::st_drop_geometry(source)[source_index, , drop = FALSE]
  if (identical(role, "building")) {
    source_area <- as.numeric(sf::st_area(source_geometry))
    observed_area <- as.numeric(sf::st_area(observed))
    if (any(observed_area <= 0) || any(observed_area - source_area > pmax(tolerance$area_absolute_m2, source_area * tolerance$measure_relative))) {
      stop("Observed building area invariant failed", call. = FALSE)
    }
    a14 <- as.numeric(source_values$A14)
    unavailable <- is.na(a14) | a14 <= 0
    gross <- a14 * observed_area / source_area
    gross[unavailable] <- NA_real_
    common[, is_clipped := observed_area < source_area - pmax(tolerance$area_absolute_m2, source_area * tolerance$measure_relative)]
    result <- cbind(common[, setdiff(names(common), "observed_geometry"), with = FALSE], data.table::data.table(
      A9 = as.character(source_values$A9), A11 = as.character(source_values$A11),
      A14 = a14, A14_source_state = as.character(source_values$A14_source_state),
      A14_is_unavailable = unavailable, source_area_m2 = source_area,
      observed_area_m2 = observed_area, observed_area_fraction = observed_area / source_area,
      observed_gross_floor_area_m2 = gross
    ))
  } else if (identical(role, "road")) {
    source_length <- as.numeric(sf::st_length(source_geometry))
    observed_length <- as.numeric(sf::st_length(observed))
    if (any(observed_length <= 0) || any(observed_length - source_length > pmax(tolerance$length_absolute_m, source_length * tolerance$measure_relative))) {
      stop("Observed road length invariant failed", call. = FALSE)
    }
    endpoints <- line_endpoint_summary(observed)
    common[, is_clipped := observed_length < source_length - pmax(tolerance$length_absolute_m, source_length * tolerance$measure_relative)]
    source_endpoints <- line_endpoint_summary(source_geometry)
    f_retained <- sqrt((endpoints[, "start_x"] - source_endpoints[, "start_x"])^2 +
                         (endpoints[, "start_y"] - source_endpoints[, "start_y"])^2) <= tolerance$coordinate_m
    t_retained <- sqrt((endpoints[, "end_x"] - source_endpoints[, "end_x"])^2 +
                         (endpoints[, "end_y"] - source_endpoints[, "end_y"])^2) <= tolerance$coordinate_m
    result <- cbind(common[, setdiff(names(common), "observed_geometry"), with = FALSE], data.table::data.table(
      LANES = as.numeric(source_values$LANES), ROAD_RANK = as.character(source_values$ROAD_RANK),
      ROAD_TYPE = as.character(source_values$ROAD_TYPE), F_NODE = as.character(source_values$F_NODE),
      T_NODE = as.character(source_values$T_NODE), source_length_m = source_length,
      observed_length_m = observed_length,
      observed_start_x_5186 = endpoints[, "start_x"], observed_start_y_5186 = endpoints[, "start_y"],
      observed_end_x_5186 = endpoints[, "end_x"], observed_end_y_5186 = endpoints[, "end_y"],
      observed_endpoint_count = as.integer(endpoints[, "endpoint_count"]),
      source_f_node_endpoint_retained = f_retained, source_t_node_endpoint_retained = t_retained
    ))
  } else {
    common[, is_clipped := FALSE]
    attributes <- observation_source_fields(config, "poi")
    semantic <- data.table::as.data.table(source_values[, attributes, drop = FALSE])
    semantic[, (names(semantic)) := lapply(.SD, as.character)]
    result <- cbind(common[, setdiff(names(common), "observed_geometry"), with = FALSE], semantic)
  }
  result[, observed_geometry := common$observed_geometry]
  data.table::setorder(result, scene_id, local_entity_id)
  result
}

write_standard_geoparquet <- function(value, path, config) {
  intermediate <- tempfile(fileext = ".wkb.parquet", tmpdir = dirname(path))
  on.exit(if (file.exists(intermediate)) unlink(intermediate), add = TRUE)
  arrow::write_parquet(
    value, intermediate, compression = config$scientific$writer$compression,
    use_dictionary = TRUE, chunk_size = as.integer(config$scientific$writer$row_group_size)
  )
  args <- c(
    config$writer_file, "write", "--input", intermediate, "--output", path,
    "--geometry-column", config$scientific$writer$primary_geometry_column,
    "--epsg", as.character(config$scientific$processing_epsg),
    "--compression", config$scientific$writer$compression,
    "--row-group-size", as.character(config$scientific$writer$row_group_size)
  )
  output <- system2(research_python_executable(), args, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status") %||% 0L
  if (status != 0L || !length(output)) stop("GeoParquet writer failed: ", paste(output, collapse = " | "), call. = FALSE)
  jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE)
}

inspect_standard_geoparquet <- function(path, config) {
  output <- system2(research_python_executable(), c(config$writer_file, "inspect", "--input", path), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status") %||% 0L
  if (status != 0L || !length(output)) stop("GeoParquet inspection failed: ", paste(output, collapse = " | "), call. = FALSE)
  value <- jsonlite::fromJSON(tail(output, 1L), simplifyVector = FALSE)
  if (!identical(value$version, "1.1.0") || !identical(value$encoding, "WKB") ||
      !identical(as.integer(value$crs_epsg), 5186L) || !identical(value$primary_column, "observed_geometry") ||
      is.null(value$covering)) {
    stop("GeoParquet metadata validation failed: ", path, call. = FALSE)
  }
  value
}

read_standard_geoparquet <- function(path, columns = NULL) {
  value <- arrow::read_parquet(path, as_data_frame = TRUE)
  if (!"observed_geometry" %in% names(value)) stop("GeoParquet lacks observed_geometry", call. = FALSE)
  geometry <- sf::st_as_sfc(value$observed_geometry, EWKB = FALSE, crs = 5186L)
  value$observed_geometry <- NULL
  value$bbox <- NULL
  result <- sf::st_sf(value, observed_geometry = geometry, crs = 5186L)
  if (!is.null(columns)) result <- result[, unique(c(columns, attr(result, "sf_column")))]
  result
}

validate_observation_table <- function(value, role, membership, scenes, config) {
  required <- jsonlite::read_json(config$schema_file, simplifyVector = FALSE)$required
  if (!all(unlist(required) %in% names(value))) stop("Observed table schema is incomplete for ", role, call. = FALSE)
  key <- c("scene_id", "entity_type", "source_entity_id")
  if (nrow(value) != nrow(membership) || anyDuplicated(value[, ..key]) ||
      !setequal(do.call(paste, c(value[, ..key], sep = "\r")), do.call(paste, c(membership[, ..key], sep = "\r")))) {
    stop("Observed and membership keys differ for ", role, call. = FALSE)
  }
  if (anyDuplicated(value[, .(scene_id, local_entity_id)])) stop("Observed local_entity_id is not scene-unique", call. = FALSE)
  geometry <- sf::st_as_sfc(value$observed_geometry, EWKB = FALSE, crs = 5186L)
  observed_boxes <- t(vapply(geometry, sf::st_bbox, numeric(4L)))
  colnames(observed_boxes) <- c("xmin", "ymin", "xmax", "ymax")
  scene_boxes <- t(vapply(sf::st_geometry(scenes), sf::st_bbox, numeric(4L)))
  colnames(scene_boxes) <- c("xmin", "ymin", "xmax", "ymax")
  scene_index <- match(value$scene_id, scenes$scene_id)
  outside_distance <- pmax(
    scene_boxes[scene_index, "xmin"] - observed_boxes[, "xmin"],
    scene_boxes[scene_index, "ymin"] - observed_boxes[, "ymin"],
    observed_boxes[, "xmax"] - scene_boxes[scene_index, "xmax"],
    observed_boxes[, "ymax"] - scene_boxes[scene_index, "ymax"],
    0
  )
  inside <- outside_distance <= config$scientific$geometry$numerical_tolerance$coordinate_m
  if (!all(inside)) {
    failed <- which(!inside)
    stop(
      "Observed geometry lies outside its scene for ", role,
      "; count=", length(failed), "; max_outside_m=", max(outside_distance[failed]),
      "; examples=", paste(head(value$scene_id[failed], 3L), head(value$source_entity_id[failed], 3L), sep = "/", collapse = ","),
      call. = FALSE
    )
  }
  invisible(TRUE)
}

observation_output_names <- function() c(
  "building_observed.parquet", "road_observed.parquet", "poi_observed.parquet",
  "branch_manifest.json", "branch_qc.json", "branch_log.jsonl"
)

build_vector_observation_shard <- function(observation_plan,
                                                     membership_acceptance,
                                                     study_data_inputs,
                                                     tracked_inputs,
                                                     observation_contract_files,
                                                     workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- observation_thread_state()
  on.exit(restore_observation_threads(state), add = TRUE)
  set_observation_threads(threads)
  config <- load_observation_config(observation_contract_files)
  spec <- observation_plan
  validate_observation_spec(spec$.path)
  acceptance <- jsonlite::read_json(artifact_path(membership_acceptance, "aggregate_membership_manifest.json"), simplifyVector = FALSE)
  if (!identical(acceptance$membership_dataset_id, spec$membership_dataset_id) || !identical(acceptance$status, "PASS")) {
    stop("Observation branch does not match accepted membership", call. = FALSE)
  }
  started <- Sys.time()
  io_start <- proc_io_snapshot()
  membership <- assign_local_entity_ids(read_branch_membership(spec), config)
  scenes <- observation_scene_sf(spec)
  roles <- c(building = "B", road = "R", poi = "P")
  sources <- lapply(names(roles), function(role) {
    ids <- membership[entity_type == roles[[role]], source_entity_id]
    runtime_source <- validated_source_record(spec$sources[[role]], tracked_inputs, role)
    read_source_entities_by_id(runtime_source, ids, observation_source_fields(config, role))
  })
  names(sources) <- names(roles)
  observations <- lapply(names(roles), function(role) {
    rows <- membership[entity_type == roles[[role]]]
    build_role_observations(role, rows, sources[[role]], scenes, spec, config)
  })
  names(observations) <- names(roles)
  for (role in names(roles)) validate_observation_table(
    observations[[role]], role, membership[entity_type == roles[[role]]], scenes, config
  )
  output_names <- observation_output_names()
  final_dir <- spec$output$directory
  paths <- publish_deterministic_directory(
    final_dir, output_names, compare_basenames = output_names[1:3],
    writer = function(stage) {
      metadata <- Map(function(value, filename) {
        write_standard_geoparquet(value, file.path(stage, filename), config)
      }, observations, output_names[1:3])
      metadata <- Map(function(filename, ignored) inspect_standard_geoparquet(file.path(stage, filename), config), output_names[1:3], metadata)
      io_end <- proc_io_snapshot()
      elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
      counts <- vapply(observations, nrow, integer(1L))
      coordinates <- vapply(observations, function(x) sum(x$observed_coordinate_count), numeric(1L))
      multipart <- vapply(observations, function(x) sum(x$observed_component_count > 1L), integer(1L))
      holes <- vapply(observations, function(x) sum(x$observed_hole_count > 0L), integer(1L))
      clipped <- vapply(observations, function(x) sum(x$is_clipped), integer(1L))
      contained <- counts - clipped
      log_records <- list(
        list(time = format(started, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul"), event = "branch_started", branch_id = spec$branch_id),
        list(time = kst_now(), event = "branch_completed", branch_id = spec$branch_id, status = "PASS", rows = as.list(counts))
      )
      write_json_lines(log_records, file.path(stage, output_names[[6L]]))
      qc <- list(
        qc_schema_version = "1.0.0", branch_id = spec$branch_id, status = "PASS", failures = list(),
        scene_count = nrow(scenes), membership_rows = as.list(counts), output_rows = as.list(counts),
        coordinate_count = as.list(coordinates), multipart_count = as.list(multipart), hole_count = as.list(holes),
        clipped_count = as.list(clipped), fully_contained_count = as.list(contained),
        boundary_contact_exclusion_count = list(building = 0L, road = 0L, poi = 0L),
        invalid_geometry_count = 0L, empty_geometry_count = 0L, zero_dimension_count = 0L,
        membership_key_match = TRUE, local_entity_id_unique = TRUE,
        geoparquet = metadata, warnings = list()
      )
      write_json_file(qc, file.path(stage, output_names[[5L]]))
      hash_targets <- c(file.path(stage, output_names[1:3]), file.path(stage, output_names[c(5L, 6L)]))
      output_records <- lapply(hash_targets, function(path) list(
        path = file.path(final_dir, basename(path)), size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)
      ))
      manifest <- list(
        manifest_schema_version = "1.0.0", branch_id = spec$branch_id,
        observation_dataset_id = spec$observation_dataset_id, membership_dataset_id = spec$membership_dataset_id,
        scope_id = spec$scope_id, scene_index_id = spec$scene_index_id, status = "PASS",
        inputs = list(
          spec_path = normalizePath(spec$.path, mustWork = TRUE),
          membership_acceptance_path = artifact_path(membership_acceptance, "aggregate_membership_manifest.json"),
          membership_acceptance_sha256 = sha256_file(artifact_path(membership_acceptance, "aggregate_membership_manifest.json")),
          sources = spec$sources, observation_config_hash = config$scientific_hash,
          observation_schema_hash = config$schema_hash, writer_hash = config$writer_hash,
          implementation_source_hash = config$implementation_source_hash
        ),
        execution = list(
          controller = spec$execution$controller, workers = 1L, threads = 1L,
          wall_time_seconds = elapsed, max_rss_kb = proc_max_rss_kb(),
          read_bytes = io_end$read_bytes - io_start$read_bytes,
          write_bytes = io_end$write_bytes - io_start$write_bytes
        ),
        scene_count = nrow(scenes), entity_rows = as.list(counts), coordinate_count = as.list(coordinates),
        outputs = output_records, geoparquet = metadata, warnings = list(), status_final = "PASS"
      )
      write_json_file(manifest, file.path(stage, output_names[[4L]]))
    }
  )
  paths
}
