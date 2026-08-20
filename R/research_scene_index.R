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

derive_training_lattice <- function(boundary, grid_path, contract) {
  native_epsg <- as.integer(contract$crs$official_grid_epsg)
  processing_epsg <- as.integer(contract$crs$processing_epsg)
  stride <- as.numeric(contract$scene$training_stride_m)
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
  centers <- suppressWarnings(sf::st_centroid(sf::st_geometry(official)))
  coordinates <- sf::st_coordinates(centers)
  phase_x <- unique(round(coordinates[, "X"] %% 500, 6L))
  phase_y <- unique(round(coordinates[, "Y"] %% 500, 6L))
  if (length(phase_x) != 1L || length(phase_y) != 1L) {
    stop("Official grid has inconsistent center phases", call. = FALSE)
  }
  widths <- vapply(sf::st_geometry(head(official, 100L)), function(geometry) diff(sf::st_bbox(geometry)[c("xmin", "xmax")]), numeric(1L))
  heights <- vapply(sf::st_geometry(head(official, 100L)), function(geometry) diff(sf::st_bbox(geometry)[c("ymin", "ymax")]), numeric(1L))
  if (any(abs(widths - 500) > 1e-8) || any(abs(heights - 500) > 1e-8)) {
    stop("Official grid cells are not 500 m squares", call. = FALSE)
  }
  bbox <- sf::st_bbox(boundary_native)
  x_start <- floor((bbox[["xmin"]] - phase_x) / stride) * stride + phase_x
  y_start <- floor((bbox[["ymin"]] - phase_y) / stride) * stride + phase_y
  x_values <- seq(x_start, bbox[["xmax"]] + stride, by = stride)
  y_values <- seq(y_start, bbox[["ymax"]] + stride, by = stride)
  lattice <- expand.grid(center_x_native = x_values, center_y_native = y_values)
  native_points <- sf::st_as_sf(
    lattice, coords = c("center_x_native", "center_y_native"), crs = native_epsg, remove = FALSE
  )
  parents <- sf::st_intersects(native_points, official)
  parent_id <- vapply(parents, function(index) {
    if (!length(index)) return(NA_character_)
    sort(as.character(official$SPO_NO_CD[index]), method = "radix")[[1L]]
  }, character(1L))
  if (anyNA(parent_id)) stop("Derived lattice contains centers outside the official grid coverage", call. = FALSE)
  points <- sf::st_transform(native_points, processing_epsg)
  xy <- sf::st_coordinates(points)
  xy[, "X"] <- round_to_precision(xy[, "X"], precision)
  xy[, "Y"] <- round_to_precision(xy[, "Y"], precision)
  points <- sf::st_as_sf(
    data.frame(center_x_5186 = xy[, "X"], center_y_5186 = xy[, "Y"]),
    coords = c("center_x_5186", "center_y_5186"), crs = processing_epsg, remove = FALSE
  )
  retained <- lengths(sf::st_within(points, sf::st_union(boundary))) > 0L
  lattice <- lattice[retained, , drop = FALSE]
  lattice$center_x_5186 <- xy[retained, "X"]
  lattice$center_y_5186 <- xy[retained, "Y"]
  lattice$official_grid_id <- parent_id[retained]
  lattice$lattice_col <- as.integer(round((lattice$center_x_native - phase_x) / stride))
  lattice$lattice_row <- as.integer(round((lattice$center_y_native - phase_y) / stride))
  lattice$phase_x_m <- lattice$center_x_native %% 500
  lattice$phase_y_m <- lattice$center_y_native %% 500
  list(data = lattice, phase_x_m = phase_x, phase_y_m = phase_y)
}

sample_off_lattice_centers <- function(boundary, training_xy, contract) {
  settings <- contract$off_lattice
  randomness <- contract$randomness
  total <- as.integer(settings$validation_count + settings$evaluation_count)
  precision <- as.numeric(contract$scene$coordinate_precision_m)
  config <- yaml::read_yaml(artifact_path(contract$implementation$config_files |> vapply(function(x) x$path, character(1L)), "scene_construction.yml"))
  batch_size <- as.integer(config$off_lattice$batch_size)
  maximum_draws <- as.integer(config$off_lattice$maximum_draws)
  bbox <- sf::st_bbox(boundary)
  training_points <- sf::st_as_sf(
    data.frame(x = training_xy[, 1L], y = training_xy[, 2L]),
    coords = c("x", "y"), crs = contract$crs$processing_epsg
  )
  accepted <- list()
  accepted_count <- 0L
  drawn <- 0L
  seen <- new.env(hash = TRUE, parent = emptyenv())
  with_research_rng(
    randomness$off_lattice_sampling_seed,
    randomness$rng_kind,
    randomness$normal_kind,
    randomness$sample_kind,
    {
      while (accepted_count < total && drawn < maximum_draws) {
        count <- min(batch_size, maximum_draws - drawn)
        candidate <- data.frame(
          center_x_5186 = round_to_precision(runif(count, bbox[["xmin"]], bbox[["xmax"]]), precision),
          center_y_5186 = round_to_precision(runif(count, bbox[["ymin"]], bbox[["ymax"]]), precision),
          sampling_order = seq.int(drawn + 1L, drawn + count)
        )
        drawn <- drawn + count
        keys <- paste(candidate$center_x_5186, candidate$center_y_5186, sep = "|")
        unique_new <- !duplicated(keys) & !vapply(keys, exists, logical(1L), envir = seen, inherits = FALSE)
        candidate <- candidate[unique_new, , drop = FALSE]
        keys <- keys[unique_new]
        if (!nrow(candidate)) next
        points <- sf::st_as_sf(candidate, coords = c("center_x_5186", "center_y_5186"), crs = contract$crs$processing_epsg, remove = FALSE)
        inside <- lengths(sf::st_within(points, sf::st_union(boundary))) > 0L
        candidate <- candidate[inside, , drop = FALSE]
        points <- points[inside, ]
        keys <- keys[inside]
        if (!nrow(candidate)) next
        nearest <- sf::st_nearest_feature(points, training_points)
        distance <- as.numeric(sf::st_distance(points, training_points[nearest, ], by_element = TRUE))
        eligible <- distance >= as.numeric(settings$minimum_training_center_distance_m)
        candidate <- candidate[eligible, , drop = FALSE]
        candidate$nearest_training_center_m <- distance[eligible]
        keys <- keys[eligible]
        if (!nrow(candidate)) next
        for (key in keys) assign(key, TRUE, envir = seen)
        needed <- total - accepted_count
        candidate <- head(candidate, needed)
        accepted[[length(accepted) + 1L]] <- candidate
        accepted_count <- accepted_count + nrow(candidate)
      }
    }
  )
  if (accepted_count < total) {
    stop("Could not sample enough eligible off-lattice centers within maximum_draws", call. = FALSE)
  }
  result <- data.table::rbindlist(accepted)[seq_len(total)]
  assignment <- with_research_rng(
    randomness$off_lattice_partition_seed,
    randomness$rng_kind,
    randomness$normal_kind,
    randomness$sample_kind,
    sample.int(total, total, replace = FALSE)
  )
  result$split <- "evaluation"
  result$split[assignment[seq_len(as.integer(settings$validation_count))]] <- "validation"
  result$split_assignment_order <- match(seq_len(total), assignment)
  result
}

scene_index_columns <- function() {
  c(
    "scene_id", "scene_footprint_id", "split", "center_x_5186", "center_y_5186",
    "xmin_5186", "ymin_5186", "xmax_5186", "ymax_5186",
    "center_x_native", "center_y_native", "official_grid_id", "lattice_row", "lattice_col",
    "phase_x_m", "phase_y_m", "sampling_order", "split_assignment_order",
    "nearest_training_center_m", "district_code", "is_retrieval_query",
    "retrieval_query_order", "scene_schema_version", "scene_config_hash",
    "study_manifest_hash", "geometry"
  )
}

validate_scene_index <- function(index, contract, boundary, buffer) {
  width <- as.numeric(contract$scene$width_m)
  counts <- table(index$split)
  expected <- c(
    validation = as.integer(contract$off_lattice$validation_count),
    evaluation = as.integer(contract$off_lattice$evaluation_count)
  )
  failures <- character()
  if (!all(expected == counts[names(expected)])) failures <- c(failures, "off_lattice_split_counts")
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
  stride <- as.numeric(contract$scene$training_stride_m)
  if (any(abs(index$center_x_native[training] / stride - round(index$center_x_native[training] / stride)) > 1e-8) ||
      any(abs(index$center_y_native[training] / stride - round(index$center_y_native[training] / stride)) > 1e-8)) {
    failures <- c(failures, "training_stride_alignment")
  }
  off <- !training
  if (any(index$nearest_training_center_m[off] + 1e-8 < contract$off_lattice$minimum_training_center_distance_m)) {
    failures <- c(failures, "off_lattice_distance")
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
    native_training_stride_m = stride,
    minimum_observed_off_lattice_distance_m = min(index$nearest_training_center_m[off]),
    retrieval_query_count = query_count,
    unrestricted_candidates_per_query = nrow(index[index$split == "evaluation", ]) - 1L
  )
}

write_geo_parquet <- function(value, path) {
  sfarrow::st_write_parquet(value, path)
  invisible(path)
}

build_spatial_scene_index <- function(study_data_inputs, methodology_contract,
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
  boundary <- sf::st_read(inputs[["boundary"]], config$paths$layers$boundary, quiet = TRUE)
  buffer <- sf::st_read(inputs[["buffer400"]], config$paths$layers$buffer400, quiet = TRUE)
  training_result <- derive_training_lattice(boundary, inputs[["official_grid_shp"]], contract)
  training <- training_result$data
  training$split <- "training"
  training$sampling_order <- NA_integer_
  training$split_assignment_order <- NA_integer_
  training$nearest_training_center_m <- 0

  off <- sample_off_lattice_centers(
    boundary,
    as.matrix(training[, c("center_x_5186", "center_y_5186")]),
    contract
  )
  off_native <- sf::st_transform(
    sf::st_as_sf(off, coords = c("center_x_5186", "center_y_5186"), crs = 5186, remove = FALSE),
    contract$crs$official_grid_epsg
  )
  native_xy <- sf::st_coordinates(off_native)
  off$center_x_native <- round_to_precision(native_xy[, "X"], contract$scene$coordinate_precision_m)
  off$center_y_native <- round_to_precision(native_xy[, "Y"], contract$scene$coordinate_precision_m)
  off$official_grid_id <- NA_character_
  off$lattice_row <- NA_integer_
  off$lattice_col <- NA_integer_
  off$phase_x_m <- NA_real_
  off$phase_y_m <- NA_real_

  columns <- c(
    "split", "center_x_5186", "center_y_5186", "center_x_native", "center_y_native",
    "official_grid_id", "lattice_row", "lattice_col", "phase_x_m", "phase_y_m",
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
    existing <- sfarrow::st_read_parquet(existing_parquet)
    comparable <- c("scene_id", "scene_footprint_id", "split", "is_retrieval_query", "retrieval_query_order")
    if (!identical(sf::st_drop_geometry(index)[, comparable], sf::st_drop_geometry(existing)[, comparable])) {
      stop("Determinism check failed against the existing scene index", call. = FALSE)
    }
  }
  publish_bundle(final_dir, output_names, function(stage) {
    parquet <- file.path(stage, output_names[[1L]])
    write_geo_parquet(index, parquet)
    round_trip <- sfarrow::st_read_parquet(parquet)
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
        phase_x_m = training_result$phase_x_m,
        phase_y_m = training_result$phase_y_m,
        derived_stride_m = contract$scene$training_stride_m
      ),
      columns = scene_index_columns(),
      geometry = list(column = "geometry", type = "Polygon", epsg = 5186),
      parquet_sha256 = sha256_file(parquet)
    )
    write_json_file(manifest, file.path(stage, output_names[[2L]]))
    write_json_file(c(list(scene_index_id = scene_index_id, generated_at = kst_now()), qc), file.path(stage, output_names[[3L]]))
  })
}
