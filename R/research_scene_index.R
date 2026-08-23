with_research_rng <- function(seed, kind, normal_kind, sample_kind, code) {
  old_kind <- RNGkind()
  had_seed <- exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  if (had_seed) old_seed <- get(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  on.exit({
    do.call(RNGkind, as.list(old_kind))
    if (had_seed) {
      assign(".Random.seed", old_seed, envir = .GlobalEnv)
    } else if (exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)) {
      rm(".Random.seed", envir = .GlobalEnv)
    }
  }, add = TRUE)
  RNGkind(kind = kind, normal.kind = normal_kind, sample.kind = sample_kind)
  set.seed(as.integer(seed))
  force(code)
}

round_to_precision <- function(value, precision) {
  round(value / precision) * precision
}

coordinate_token <- function(value, precision) {
  integer <- round(value / precision)
  format(integer, scientific = FALSE, trim = TRUE)
}

deterministic_scene_ids <- function(split, center_x, center_y, schema_version,
                                    precision, prefix = "scn_", characters = 24L) {
  vapply(seq_along(split), function(index) {
    token <- paste(
      schema_version, split[[index]],
      coordinate_token(center_x[[index]], precision),
      coordinate_token(center_y[[index]], precision),
      sep = "|"
    )
    paste0(prefix, substr(digest::digest(token, algo = "sha256", serialize = FALSE), 1L, characters))
  }, character(1L))
}

deterministic_footprint_ids <- function(xmin, ymin, xmax, ymax, schema_version,
                                        precision, prefix = "fpt_", characters = 24L) {
  vapply(seq_along(xmin), function(index) {
    token <- paste(
      schema_version, "EPSG:5186",
      coordinate_token(xmin[[index]], precision), coordinate_token(ymin[[index]], precision),
      coordinate_token(xmax[[index]], precision), coordinate_token(ymax[[index]], precision),
      sep = "|"
    )
    paste0(prefix, substr(digest::digest(token, algo = "sha256", serialize = FALSE), 1L, characters))
  }, character(1L))
}

square_footprints <- function(center_x, center_y, width, crs = 5186L) {
  half <- width / 2
  geometries <- lapply(seq_along(center_x), function(index) {
    x <- center_x[[index]]
    y <- center_y[[index]]
    sf::st_polygon(list(matrix(c(
      x - half, y - half,
      x + half, y - half,
      x + half, y + half,
      x - half, y + half,
      x - half, y - half
    ), ncol = 2L, byrow = TRUE)))
  })
  sf::st_sfc(geometries, crs = crs)
}

geometry_sha256 <- function(geometry) {
  vapply(sf::st_as_binary(geometry, EWKB = TRUE), function(value) {
    digest::digest(value, algo = "sha256", serialize = FALSE)
  }, character(1L))
}

canonicalize_official_grid <- function(official, id_column) {
  if (!id_column %in% names(official)) stop("Official grid ID column is missing", call. = FALSE)
  ids <- as.character(official[[id_column]])
  if (anyNA(ids) || any(!nzchar(ids))) stop("Official grid has missing cell IDs", call. = FALSE)
  geometry_hash <- geometry_sha256(sf::st_geometry(official))
  centers <- suppressWarnings(sf::st_centroid(sf::st_geometry(official)))
  xy <- sf::st_coordinates(centers)
  evidence <- data.table::data.table(
    source_row = seq_len(nrow(official)), official_grid_id = ids,
    geometry_sha256 = geometry_hash, center_x = xy[, "X"], center_y = xy[, "Y"]
  )
  inconsistent <- evidence[, .(
    geometry_count = data.table::uniqueN(geometry_sha256),
    center_count = data.table::uniqueN(paste(format(center_x, digits = 17), format(center_y, digits = 17)))
  ), by = official_grid_id][geometry_count != 1L | center_count != 1L]
  if (nrow(inconsistent)) {
    stop("Official grid same ID has different center or geometry: ", inconsistent$official_grid_id[[1L]], call. = FALSE)
  }
  data.table::setorder(evidence, official_grid_id, geometry_sha256, source_row)
  retained <- evidence[, source_row[[1L]], by = official_grid_id]$V1
  canonical <- official[retained, c(id_column)]
  canonical$official_grid_id <- as.character(canonical[[id_column]])
  canonical <- canonical[order(canonical$official_grid_id, method = "radix"), ]
  list(
    data = canonical,
    source_row_count = nrow(official),
    canonical_cell_count = nrow(canonical),
    identical_duplicate_rows_removed = nrow(official) - nrow(canonical)
  )
}

derive_official_training_scenes <- function(boundary, grid_path, contract) {
  native_epsg <- as.integer(contract$crs$official_grid_epsg)
  processing_epsg <- as.integer(contract$crs$processing_epsg)
  precision <- as.numeric(contract$scene$coordinate_precision_m)
  boundary_native <- sf::st_transform(boundary, native_epsg)
  filter <- sf::st_as_text(sf::st_as_sfc(sf::st_bbox(sf::st_buffer(boundary_native, 1000))))
  official <- sf::st_read(grid_path, quiet = TRUE, wkt_filter = filter)
  if (!nrow(official) || sf::st_crs(official)$epsg != native_epsg) {
    stop("Official grid subset is empty or has the wrong CRS", call. = FALSE)
  }
  # The Shapefile advertises EPSG:5179 through a BOUNDCRS wrapper. Coordinates
  # are already native EPSG:5179, so normalize metadata without transforming.
  suppressWarnings(sf::st_crs(official) <- sf::st_crs(native_epsg))
  canonical <- canonicalize_official_grid(official, contract$scene$official_cell_id_column)
  official <- canonical$data
  centers <- suppressWarnings(sf::st_centroid(sf::st_geometry(official)))
  coordinates <- sf::st_coordinates(centers)
  widths <- vapply(sf::st_geometry(head(official, 100L)), function(geometry) diff(sf::st_bbox(geometry)[c("xmin", "xmax")]), numeric(1L))
  heights <- vapply(sf::st_geometry(head(official, 100L)), function(geometry) diff(sf::st_bbox(geometry)[c("ymin", "ymax")]), numeric(1L))
  if (any(abs(widths - 500) > 1e-8) || any(abs(heights - 500) > 1e-8)) {
    stop("Official grid cells are not 500 m squares", call. = FALSE)
  }
  native_points <- sf::st_as_sf(
    data.frame(center_x_native = coordinates[, "X"], center_y_native = coordinates[, "Y"],
               official_grid_id = official$official_grid_id),
    coords = c("center_x_native", "center_y_native"), crs = native_epsg, remove = FALSE
  )
  points <- sf::st_transform(native_points, processing_epsg)
  xy <- sf::st_coordinates(points)
  xy[, "X"] <- round_to_precision(xy[, "X"], precision)
  xy[, "Y"] <- round_to_precision(xy[, "Y"], precision)
  points <- sf::st_as_sf(
    data.frame(center_x_5186 = xy[, "X"], center_y_5186 = xy[, "Y"]),
    coords = c("center_x_5186", "center_y_5186"), crs = processing_epsg, remove = FALSE
  )
  retained <- lengths(sf::st_within(points, sf::st_union(boundary))) > 0L
  result <- sf::st_drop_geometry(native_points)[retained, , drop = FALSE]
  result$center_x_5186 <- xy[retained, "X"]
  result$center_y_5186 <- xy[retained, "Y"]
  result$official_grid_row <- as.integer(round(result$center_y_native / 500))
  result$official_grid_column <- as.integer(round(result$center_x_native / 500))
  result <- result[order(result$official_grid_id, method = "radix"), , drop = FALSE]
  list(data = result, dedup = canonical)
}

select_accepted_off_grid_centers <- function(source_path, training_xy, contract) {
  settings <- contract$off_grid
  source <- suppressWarnings(sfarrow::st_read_parquet(source_path))
  source <- data.table::as.data.table(sf::st_drop_geometry(source))
  source <- source[split %in% c("validation", "evaluation")]
  if (anyDuplicated(source$scene_id) || anyDuplicated(source[, .(center_x_5186, center_y_5186)])) {
    stop("Accepted off-grid source contains duplicate IDs or centers", call. = FALSE)
  }
  source[, selection_rank__ := ifelse(is.na(sampling_order), Inf, sampling_order)]
  source[, selection_hash__ := vapply(scene_id, function(id) {
    digest::digest(paste("official-grid-off-grid-subset-v1", id, sep = "|"), algo = "sha256", serialize = FALSE)
  }, character(1L))]
  counts <- c(validation = as.integer(settings$validation_count), evaluation = as.integer(settings$evaluation_count))
  selected <- data.table::rbindlist(lapply(names(counts), function(split_name) {
    values <- source[split == split_name]
    data.table::setorder(values, selection_rank__, selection_hash__, scene_id)
    if (nrow(values) < counts[[split_name]]) stop("Accepted off-grid source split is too small", call. = FALSE)
    values[seq_len(counts[[split_name]])]
  }), use.names = TRUE, fill = TRUE)
  training_points <- sf::st_as_sf(
    data.frame(x = training_xy[, 1L], y = training_xy[, 2L]),
    coords = c("x", "y"), crs = contract$crs$processing_epsg
  )
  points <- sf::st_as_sf(selected, coords = c("center_x_5186", "center_y_5186"), crs = 5186, remove = FALSE)
  nearest <- sf::st_nearest_feature(points, training_points)
  selected$nearest_training_center_m <- as.numeric(sf::st_distance(points, training_points[nearest, ], by_element = TRUE))
  if (any(selected$nearest_training_center_m < as.numeric(settings$minimum_training_center_distance_m))) {
    stop("Accepted off-grid subset violates the new training-center distance", call. = FALSE)
  }
  selected[, c("selection_rank__", "selection_hash__") := NULL]
  selected
}

scene_index_columns <- function() {
  c(
    "scene_id", "scene_footprint_id", "split", "center_x_5186", "center_y_5186",
    "xmin_5186", "ymin_5186", "xmax_5186", "ymax_5186",
    "center_x_native", "center_y_native", "official_grid_id", "official_grid_row", "official_grid_column",
    "source_scene_id", "sampling_order", "split_assignment_order",
    "nearest_training_center_m", "district_code", "is_retrieval_query",
    "retrieval_query_order", "scene_schema_version", "scene_config_hash",
    "study_manifest_hash", "geometry"
  )
}

validate_scene_index <- function(index, contract, boundary, buffer) {
  width <- as.numeric(contract$scene$width_m)
  counts <- table(index$split)
  expected <- c(
    validation = as.integer(contract$off_grid$validation_count),
    evaluation = as.integer(contract$off_grid$evaluation_count)
  )
  failures <- character()
  if (!all(expected == counts[names(expected)])) failures <- c(failures, "split_counts")
  if (anyDuplicated(index$scene_id)) failures <- c(failures, "duplicate_scene_id")
  if (anyDuplicated(index$scene_footprint_id)) failures <- c(failures, "duplicate_scene_footprint_id")
  if (!all(sf::st_is_valid(index))) failures <- c(failures, "invalid_footprint")
  if (any(abs(index$xmax_5186 - index$xmin_5186 - width) > 1e-8) ||
      any(abs(index$ymax_5186 - index$ymin_5186 - width) > 1e-8)) {
    failures <- c(failures, "footprint_size")
  }
  centers <- sf::st_as_sf(
    sf::st_drop_geometry(index), coords = c("center_x_5186", "center_y_5186"),
    crs = contract$crs$processing_epsg, remove = FALSE
  )
  if (!all(lengths(sf::st_within(centers, sf::st_union(boundary))) > 0L)) failures <- c(failures, "center_outside_boundary")
  if (!all(lengths(sf::st_covered_by(index, sf::st_union(buffer))) > 0L)) failures <- c(failures, "footprint_outside_buffer")
  training <- index$split == "training"
  if (anyDuplicated(index$official_grid_id[training]) || anyNA(index$official_grid_id[training])) failures <- c(failures, "official_grid_id")
  training_center_keys <- paste(index$center_x_5186[training], index$center_y_5186[training], sep = "|")
  if (anyDuplicated(training_center_keys)) failures <- c(failures, "duplicate_training_center")
  training_intersections <- sf::st_intersects(index[training, ], sparse = TRUE)
  interior_overlap <- any(vapply(seq_along(training_intersections), function(i) {
    peers <- training_intersections[[i]][training_intersections[[i]] > i]
    any(vapply(peers, function(j) as.numeric(sf::st_area(sf::st_intersection(index$geometry[which(training)[i]], index$geometry[which(training)[j]]))) > 0, logical(1L)))
  }, logical(1L)))
  if (interior_overlap) failures <- c(failures, "training_footprint_interior_overlap")
  off <- !training
  if (any(index$nearest_training_center_m[off] < contract$off_grid$minimum_training_center_distance_m)) {
    failures <- c(failures, "off_grid_distance")
  }
  query_count <- sum(index$is_retrieval_query)
  if (query_count != contract$retrieval$query_count) failures <- c(failures, "retrieval_query_count")
  if (nrow(index[index$split == "evaluation", ]) - 1L != contract$retrieval$unrestricted_candidate_count) {
    failures <- c(failures, "retrieval_candidate_count")
  }
  list(
    status = if (length(failures)) "FAIL" else "PASS",
    failures = failures,
    row_count = nrow(index),
    split_counts = as.list(counts),
    scene_id_unique = !anyDuplicated(index$scene_id),
    scene_footprint_id_unique = !anyDuplicated(index$scene_footprint_id),
    geometry_valid = all(sf::st_is_valid(index)),
    footprint_width_m = width,
    centers_within_boundary = !"center_outside_boundary" %in% failures,
    footprints_covered_by_buffer = !"footprint_outside_buffer" %in% failures,
    canonical_official_grid_id_unique = !anyDuplicated(index$official_grid_id[training]),
    training_center_unique = !anyDuplicated(training_center_keys),
    training_footprint_interior_overlap_count = as.integer(interior_overlap),
    intermediate_center_count = 0L,
    minimum_observed_off_grid_distance_m = min(index$nearest_training_center_m[off]),
    retrieval_query_count = query_count,
    unrestricted_candidates_per_query = nrow(index[index$split == "evaluation", ]) - 1L
  )
}

write_geo_parquet <- function(value, path) {
  suppressWarnings(sfarrow::st_write_parquet(value, path))
  invisible(path)
}

build_spatial_scene_index <- function(study_data_inputs, accepted_off_grid_source,
                                      prototype_runtime_inputs, methodology_contract,
                                      research_config_files, workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- capture_native_thread_state()
  on.exit(restore_native_thread_state(state), add = TRUE)
  set_native_thread_limits(threads)
  config <- load_research_config(research_config_files)
  contract_path <- artifact_path(methodology_contract, "methodology_contract.json")
  contract <- jsonlite::read_json(contract_path, simplifyVector = FALSE)
  validate_methodology_contract_list(contract)
  inputs <- setNames(normalizePath(study_data_inputs, mustWork = TRUE), names(config$paths$inputs))
  boundary <- sf::st_read(runtime_mirror_path(prototype_runtime_inputs, "boundary"), config$paths$layers$boundary, quiet = TRUE)
  buffer <- sf::st_read(runtime_mirror_path(prototype_runtime_inputs, "buffer400"), config$paths$layers$buffer400, quiet = TRUE)
  training_result <- derive_official_training_scenes(
    boundary, runtime_mirror_path(prototype_runtime_inputs, "official_grid_shp"), contract
  )
  training <- training_result$data
  training$split <- "training"
  training$sampling_order <- NA_integer_
  training$split_assignment_order <- NA_integer_
  training$nearest_training_center_m <- 0
  training$source_scene_id <- NA_character_

  source_parquet <- runtime_mirror_path(prototype_runtime_inputs, "accepted_off_grid_parquet")
  off <- select_accepted_off_grid_centers(
    source_parquet,
    as.matrix(training[, c("center_x_5186", "center_y_5186")]),
    contract
  )
  off$source_scene_id <- off$scene_id
  off_native <- sf::st_transform(
    sf::st_as_sf(off, coords = c("center_x_5186", "center_y_5186"), crs = 5186, remove = FALSE),
    contract$crs$official_grid_epsg
  )
  native_xy <- sf::st_coordinates(off_native)
  off$center_x_native <- round_to_precision(native_xy[, "X"], contract$scene$coordinate_precision_m)
  off$center_y_native <- round_to_precision(native_xy[, "Y"], contract$scene$coordinate_precision_m)
  off$official_grid_id <- NA_character_
  off$official_grid_row <- NA_integer_
  off$official_grid_column <- NA_integer_

  columns <- c(
    "split", "center_x_5186", "center_y_5186", "center_x_native", "center_y_native",
    "official_grid_id", "official_grid_row", "official_grid_column", "source_scene_id",
    "sampling_order", "split_assignment_order", "nearest_training_center_m"
  )
  training_columns <- training[, columns, drop = FALSE]
  off_columns <- off[, ..columns]
  combined <- data.table::rbindlist(list(training_columns, off_columns), fill = TRUE)
  data.table::setorder(combined, split, center_y_5186, center_x_5186)
  half <- contract$scene$width_m / 2
  combined[, `:=`(
    xmin_5186 = center_x_5186 - half,
    ymin_5186 = center_y_5186 - half,
    xmax_5186 = center_x_5186 + half,
    ymax_5186 = center_y_5186 + half
  )]
  id_settings <- config$scene$ids
  combined[, scene_id := deterministic_scene_ids(
    split, center_x_5186, center_y_5186, contract$scene_schema_version %||% config$scene$scene_schema_version,
    contract$scene$coordinate_precision_m, id_settings$scene_prefix, id_settings$digest_characters
  )]
  combined[, scene_footprint_id := deterministic_footprint_ids(
    xmin_5186, ymin_5186, xmax_5186, ymax_5186,
    config$scene$scene_schema_version, contract$scene$coordinate_precision_m,
    id_settings$footprint_prefix, id_settings$digest_characters
  )]
  evaluation_rows <- which(combined$split == "evaluation")
  selected_queries <- with_research_rng(
    contract$randomness$retrieval_query_seed,
    contract$randomness$rng_kind,
    contract$randomness$normal_kind,
    contract$randomness$sample_kind,
    sample(evaluation_rows, contract$retrieval$query_count, replace = FALSE)
  )
  combined[, `:=`(is_retrieval_query = FALSE, retrieval_query_order = NA_integer_)]
  combined$is_retrieval_query[selected_queries] <- TRUE
  combined$retrieval_query_order[selected_queries] <- seq_along(selected_queries)
  combined[, `:=`(
    district_code = NA_character_,
    scene_schema_version = config$scene$scene_schema_version,
    scene_config_hash = contract$scientific_hash,
    study_manifest_hash = contract$input_contract$study_manifest_sha256
  )]
  geometry <- square_footprints(combined$center_x_5186, combined$center_y_5186, contract$scene$width_m)
  index <- sf::st_sf(as.data.frame(combined), geometry = geometry, crs = contract$crs$processing_epsg)
  index <- index[, scene_index_columns()]
  qc <- validate_scene_index(index, contract, boundary, buffer)
  if (!identical(qc$status, "PASS")) stop("Scene index QC failed: ", paste(qc$failures, collapse = ", "), call. = FALSE)

  scientific_identity <- list(
    contract_id = contract$contract_id,
    contract_scientific_hash = contract$scientific_hash,
    boundary_sha256 = sha256_file(inputs[["boundary"]]),
    official_grid_sha256 = sha256_file(inputs[["official_grid_shp"]]),
    scene_schema_version = config$scene$scene_schema_version,
    implementation_sha256 = sha256_file(file.path(config$paths$repository$root, "R/research_scene_index.R"))
  )
  scene_index_id <- short_hash_id("idx_", scientific_identity)
  final_dir <- file.path(config$paths$outputs$scene_root, "index", scene_index_id)
  output_names <- c("scene_index.parquet", "scene_index_manifest.json", "scene_index_qc.json")
  existing_parquet <- file.path(final_dir, output_names[[1L]])
  if (file.exists(existing_parquet)) {
    existing <- suppressWarnings(sfarrow::st_read_parquet(existing_parquet))
    comparable <- c("scene_id", "scene_footprint_id", "split", "is_retrieval_query", "retrieval_query_order")
    if (!identical(sf::st_drop_geometry(index)[, comparable], sf::st_drop_geometry(existing)[, comparable])) {
      stop("Determinism check failed against the existing scene index", call. = FALSE)
    }
  }
  publish_bundle(final_dir, output_names, function(stage) {
    parquet <- file.path(stage, output_names[[1L]])
    write_geo_parquet(index, parquet)
    round_trip <- suppressWarnings(sfarrow::st_read_parquet(parquet))
    if (nrow(round_trip) != nrow(index) || sf::st_crs(round_trip)$epsg != 5186L || anyDuplicated(round_trip$scene_id)) {
      stop("Scene index GeoParquet round-trip validation failed", call. = FALSE)
    }
    manifest <- list(
      manifest_schema_version = "1.0.0",
      scene_index_id = scene_index_id,
      generated_at = kst_now(),
      status = "PASS",
      scientific_identity = scientific_identity,
      row_count = nrow(index),
      split_counts = qc$split_counts,
      ordered_retrieval_query_scene_ids = index$scene_id[order(index$retrieval_query_order, na.last = NA)],
      official_grid = list(
        native_epsg = contract$crs$official_grid_epsg,
        source_row_count = training_result$dedup$source_row_count,
        canonical_cell_count_before_boundary_filter = training_result$dedup$canonical_cell_count,
        identical_duplicate_rows_removed = training_result$dedup$identical_duplicate_rows_removed,
        retained_training_cells = sum(index$split == "training"),
        intermediate_centers = 0,
        footprint = "500m EPSG:5186 axis-aligned square around transformed official center"
      ),
      accepted_off_grid_source = list(
        scene_index_id = contract$off_grid$source$scene_index_id,
        files = contract$off_grid$source$files
      ),
      columns = scene_index_columns(),
      geometry = list(column = "geometry", type = "Polygon", epsg = 5186),
      parquet_sha256 = sha256_file(parquet)
    )
    write_json_file(manifest, file.path(stage, output_names[[2L]]))
    write_json_file(c(list(scene_index_id = scene_index_id, generated_at = kst_now()), qc), file.path(stage, output_names[[3L]]))
  })
}
