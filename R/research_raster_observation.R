# Thesis Methodology 3.2.4 (entity background) and 3.5.2 (raster scene branch):
# exact observed-geometry support and fixed scene-local overlap grids.
raster_observation_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/raster_observation.yml",
    "config/raster_observation_runtime.yml",
    "config/schemas/prototype_raster_observation.schema.json",
    "python/write_raster_zarr.py",
    "python/requirements-raster.txt",
    "R/research_raster_observation.R"
  ))
}

load_raster_observation_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c(
    "raster_observation.yml", "raster_observation_runtime.yml",
    "prototype_raster_observation.schema.json", "write_raster_zarr.py",
    "requirements-raster.txt",
    "research_raster_observation.R"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing raster observation contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  scientific <- yaml::read_yaml(by_name[["raster_observation.yml"]])
  runtime <- yaml::read_yaml(by_name[["raster_observation_runtime.yml"]])
  validate_raster_observation_config(scientific, runtime)
  list(
    scientific = scientific,
    runtime = runtime,
    schema_file = by_name[["prototype_raster_observation.schema.json"]],
    writer_file = by_name[["write_raster_zarr.py"]],
    requirements_file = by_name[["requirements-raster.txt"]],
    implementation_file = by_name[["research_raster_observation.R"]],
    scientific_hash = sha256_file(by_name[["raster_observation.yml"]]),
    runtime_hash = sha256_file(by_name[["raster_observation_runtime.yml"]]),
    schema_hash = sha256_file(by_name[["prototype_raster_observation.schema.json"]]),
    writer_hash = sha256_file(by_name[["write_raster_zarr.py"]]),
    requirements_hash = sha256_file(by_name[["requirements-raster.txt"]]),
    implementation_source_hash = sha256_file(by_name[["research_raster_observation.R"]])
  )
}

validate_raster_observation_config <- function(scientific, runtime) {
  checks <- c(
    epsg = identical(as.integer(scientific$processing_epsg), 5186L),
    footprint = identical(as.numeric(scientific$scene_footprint_size_m), 500),
    landcover_shape = identical(as.integer(unlist(scientific$scene_level$landcover$grid_shape)), c(100L, 100L)),
    dem_shape = identical(as.integer(unlist(scientific$scene_level$dem$grid_shape)), c(17L, 17L)),
    classes = identical(as.integer(scientific$scene_level$landcover$class_count), 22L),
    class_codes = identical(as.integer(unlist(scientific$scene_level$landcover$class_codes)), 1:22),
    landcover_aggregation = identical(scientific$scene_level$landcover$aggregation, "exact_area_overlap_class_composition"),
    dem_aggregation = identical(scientific$scene_level$dem$aggregation, "exact_area_overlap_valid_mean"),
    dem_statistics = identical(unlist(scientific$object_level$dem$statistics), c("overlap_weighted_mean_m", "overlap_weighted_population_sd_m")),
    observed_geometry = identical(scientific$object_level$source_geometry, "I10_observed_geometry_only"),
    zarr_format = identical(as.integer(scientific$storage$zarr_format), 2L),
    controller = identical(runtime$controller, "controller_40"),
    workers = identical(as.integer(runtime$branch_workers), 1L),
    threads = identical(as.integer(runtime$threads_per_worker), 1L)
  )
  if (any(!checks)) stop("Raster observation contract mismatch: ", paste(names(checks)[!checks], collapse = ", "), call. = FALSE)
  roles <- scientific$vector_input_column_roles
  if (!"bbox" %in% unlist(roles$geoparquet_auxiliary) || !"bbox" %in% unlist(roles$explicitly_not_model_features) ||
      !identical(unlist(roles$geometry), "observed_geometry")) {
    stop("GeoParquet auxiliary column role contract is incomplete", call. = FALSE)
  }
  invisible(TRUE)
}

raster_thread_state <- function() observation_thread_state()

set_raster_threads <- function(threads = 1L) {
  set_observation_threads(threads)
  data.table::setDTthreads(as.integer(threads))
  invisible(TRUE)
}

restore_raster_threads <- function(state) restore_observation_threads(state)

study_raster_path <- function(study_data_inputs, basename_required) {
  matches <- normalizePath(study_data_inputs, mustWork = TRUE)
  matches <- matches[basename(matches) == basename_required]
  if (length(matches) != 1L) stop("Expected exactly one study raster named ", basename_required, call. = FALSE)
  matches[[1L]]
}

raster_epsg <- function(raster) {
  description <- terra::crs(raster, describe = TRUE)
  if (!nrow(description) || !identical(description$authority[[1L]], "EPSG")) return(NA_integer_)
  as.integer(description$code[[1L]])
}

raster_gdal_info <- function(path) {
  output <- system2("gdalinfo", c("-json", path), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status") %||% 0L
  if (status != 0L) stop("gdalinfo failed for raster: ", path, call. = FALSE)
  jsonlite::fromJSON(paste(output, collapse = "\n"), simplifyVector = FALSE)
}

raster_grid_record <- function(path, modality, expected_epsg = 5186L) {
  raster <- terra::rast(path)
  gdal <- raster_gdal_info(path)
  band <- gdal$bands[[1L]]
  if (terra::nlyr(raster) != 1L || raster_epsg(raster) != expected_epsg) {
    stop("Raster layer or CRS contract failed: ", path, call. = FALSE)
  }
  extent <- as.vector(terra::ext(raster))
  names(extent) <- c("xmin", "xmax", "ymin", "ymax")
  default_metadata_index <- which(names(gdal$metadata) == "")
  metadata <- if (length(default_metadata_index)) gdal$metadata[[default_metadata_index[[1L]]]] else list()
  legend <- list()
  if (identical(modality, "landcover")) {
    legend_keys <- sprintf("LC_VALUE_%02d", 1:22)
    if (!all(legend_keys %in% names(metadata)) || any(!nzchar(unlist(metadata[legend_keys])))) {
      stop("Land-cover category legend is incomplete", call. = FALSE)
    }
    legend <- metadata[legend_keys]
    source_codes <- sub("\\|.*$", "", unlist(legend))
    if (anyDuplicated(source_codes) || !identical(as.numeric(band$noDataValue), 0) || !identical(band$type, "Byte")) {
      stop("Land-cover dtype, nodata, or category legend contract failed", call. = FALSE)
    }
  } else if (!identical(as.numeric(band$noDataValue), -32767) || !identical(band$type, "Int16")) {
    stop("DEM dtype or nodata contract failed", call. = FALSE)
  }
  record <- list(
    path = normalizePath(path, mustWork = TRUE),
    artifact_id = short_hash_id("src_", sha256_file(path)),
    sha256 = sha256_file(path),
    size_bytes = unname(file.info(path)$size),
    epsg = expected_epsg,
    nrow = terra::nrow(raster), ncol = terra::ncol(raster), bands = terra::nlyr(raster),
    resolution = as.list(as.numeric(terra::res(raster))),
    origin = as.list(as.numeric(terra::origin(raster))),
    extent = as.list(extent), datatype = terra::datatype(raster),
    gdal_datatype = band$type, nodata = band$noDataValue,
    minimum = band$minimum %||% band$min, maximum = band$maximum %||% band$max,
    legend = legend
  )
  record$grid_fingerprint <- digest::digest(record[c("sha256", "epsg", "nrow", "ncol", "resolution", "origin", "extent", "datatype")], algo = "sha256")
  record
}

validate_raster_coverage <- function(raster, scenes, tolerance = 1e-7) {
  source <- terra::ext(raster)
  boxes <- data.table::rbindlist(lapply(scenes, function(scene) data.table::as.data.table(scene[c("xmin", "ymin", "xmax", "ymax")])))
  covered <- boxes$xmin >= terra::xmin(source) - tolerance & boxes$xmax <= terra::xmax(source) + tolerance &
    boxes$ymin >= terra::ymin(source) - tolerance & boxes$ymax <= terra::ymax(source) + tolerance
  if (!all(covered)) stop("Raster does not fully cover every aligned observation scene", call. = FALSE)
  invisible(TRUE)
}

read_i10_branch_context <- function(spec, vector_branch_paths) {
  manifest_path <- artifact_path(vector_branch_paths, "branch_manifest.json")
  qc_path <- artifact_path(vector_branch_paths, "branch_qc.json")
  manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  qc <- jsonlite::read_json(qc_path, simplifyVector = FALSE)
  if (!identical(manifest$branch_id, spec$branch_id) || !identical(manifest$status_final, "PASS") ||
      !identical(qc$status, "PASS") || !identical(manifest$observation_dataset_id, spec$observation_dataset_id)) {
    stop("I10 vector branch is not aligned and PASS: ", spec$branch_id, call. = FALSE)
  }
  expected <- unlist(spec$estimated_counts[c("building", "road", "poi")])
  actual <- unlist(manifest$entity_rows[c("building", "road", "poi")])
  if (!identical(as.integer(actual), as.integer(expected))) stop("I10 branch row counts changed", call. = FALSE)
  for (record in manifest$outputs) {
    if (!file.exists(record$path) || !identical(sha256_file(record$path), record$sha256)) {
      stop("I10 branch checksum mismatch: ", record$path, call. = FALSE)
    }
  }
  files <- setNames(c(
    artifact_path(vector_branch_paths, "building_observed.parquet"),
    artifact_path(vector_branch_paths, "road_observed.parquet"),
    artifact_path(vector_branch_paths, "poi_observed.parquet")
  ), c("building", "road", "poi"))
  for (path in files) {
    physical <- names(arrow::read_parquet(path, as_data_frame = TRUE))
    if (!"bbox" %in% physical) stop("I10 GeoParquet lacks optional bbox struct: ", path, call. = FALSE)
  }
  list(manifest = manifest, qc = qc, manifest_path = manifest_path, files = files)
}

raster_observation_identity <- function(spec, vector_context, rasters, config) {
  scientific <- list(
    vector_observation_dataset_id = spec$observation_dataset_id,
    prototype_id = spec$prototype_id,
    scene_index_id = spec$scene_index_id,
    raster_sources = lapply(rasters, function(value) value[c("artifact_id", "sha256", "grid_fingerprint")]),
    config_hash = config$scientific_hash,
    schema_hash = config$schema_hash,
    writer_hash = config$writer_hash,
    requirements_hash = config$requirements_hash,
    implementation_source_hash = config$implementation_source_hash
  )
  short_hash_id("pro_", scientific)
}

scene_local_raster <- function(scene, shape) {
  terra::rast(
    nrows = as.integer(shape[[1L]]), ncols = as.integer(shape[[2L]]),
    xmin = as.numeric(scene$xmin), xmax = as.numeric(scene$xmax),
    ymin = as.numeric(scene$ymin), ymax = as.numeric(scene$ymax), crs = "EPSG:5186"
  )
}

scene_landcover_observation <- function(source, scene, config) {
  class_codes <- as.integer(unlist(config$scientific$scene_level$landcover$class_codes))
  target <- scene_local_raster(scene, config$scientific$scene_level$landcover$grid_shape)
  local <- terra::crop(source, terra::ext(target), snap = "out")
  observed_codes <- sort(unique(terra::values(local, mat = FALSE)))
  observed_codes <- observed_codes[!is.na(observed_codes)]
  unknown <- setdiff(as.integer(observed_codes), class_codes)
  if (length(unknown)) stop("Unknown land-cover category code: ", paste(unknown, collapse = ", "), call. = FALSE)
  valid_source <- terra::ifel(is.na(local), 0, 1)
  class_layers <- lapply(class_codes, function(code) terra::ifel(is.na(local), 0, terra::ifel(local == code, 1, 0)))
  stack <- c(do.call(c, class_layers), valid_source)
  names(stack) <- c(sprintf("class_%02d", class_codes), "valid_support_ratio")
  transferred <- terra::resample(stack, target, method = "average", threads = FALSE)
  values <- terra::as.array(transferred)
  support <- aperm(values[, , seq_along(class_codes), drop = FALSE], c(3, 1, 2))
  valid <- values[, , length(class_codes) + 1L]
  support[support < 0] <- 0
  support[support > 1] <- 1
  valid[valid < 0] <- 0
  valid[valid > 1] <- 1
  composition <- support
  for (index in seq_along(class_codes)) {
    composition[index, , ] <- ifelse(valid > 0, support[index, , ] / valid, 0)
  }
  sums <- apply(composition, c(2, 3), sum)
  tolerance <- as.numeric(config$scientific$numerical_tolerance$scene_composition_absolute)
  if (any(abs(sums[valid > 0] - 1) > tolerance) || any(composition < -tolerance) || any(composition > 1 + tolerance)) {
    stop("Scene land-cover composition invariant failed", call. = FALSE)
  }
  list(
    composition = composition, valid_support_ratio = valid, valid_mask = valid > 0,
    histogram = apply(support, 1L, sum), unknown_category_count = length(unknown),
    nodata_cell_count = sum(valid <= 0), target = target
  )
}

scene_dem_observation <- function(source, scene, config) {
  target <- scene_local_raster(scene, config$scientific$scene_level$dem$grid_shape)
  local <- terra::crop(source, terra::ext(target), snap = "out")
  valid_source <- terra::ifel(is.na(local), 0, 1)
  mean_raster <- terra::resample(local, target, method = "average", threads = FALSE)
  valid_raster <- terra::resample(valid_source, target, method = "average", threads = FALSE)
  value <- terra::as.matrix(mean_raster, wide = TRUE)
  valid <- terra::as.matrix(valid_raster, wide = TRUE)
  valid[valid < 0] <- 0
  valid[valid > 1] <- 1
  fill <- as.numeric(config$scientific$scene_level$dem$invalid_value_fill)
  value[valid <= 0 | is.na(value)] <- fill
  valid_values <- value[valid > 0]
  list(
    value = value, valid_support_ratio = valid, valid_mask = valid > 0,
    minimum_m = if (length(valid_values)) min(valid_values) else NA_real_,
    maximum_m = if (length(valid_values)) max(valid_values) else NA_real_,
    mean_m = if (length(valid_values)) mean(valid_values) else NA_real_,
    sd_m = if (length(valid_values) > 1L) stats::sd(valid_values) else 0,
    nodata_cell_count = sum(valid <= 0), target = target
  )
}

line_segment_groups <- function(geometry) {
  coordinates <- sf::st_coordinates(geometry)
  if (!nrow(coordinates)) return(list())
  groups <- intersect(c("L1", "L2", "L3"), colnames(coordinates))
  if (!length(groups)) return(list(coordinates[, c("X", "Y"), drop = FALSE]))
  group <- interaction(as.data.frame(coordinates[, groups, drop = FALSE]), drop = TRUE, lex.order = TRUE)
  lapply(split(seq_len(nrow(coordinates)), group), function(index) coordinates[index, c("X", "Y"), drop = FALSE])
}

line_cell_support_one <- function(geometry, raster) {
  resolution <- terra::res(raster)
  source_extent <- terra::ext(raster)
  result <- list()
  position <- 0L
  for (part in line_segment_groups(geometry)) {
    if (nrow(part) < 2L) next
    for (index in seq_len(nrow(part) - 1L)) {
      start <- part[index, ]; end <- part[index + 1L, ]
      delta <- end - start
      length_m <- sqrt(sum(delta^2))
      if (length_m == 0) next
      breaks <- c(0, 1)
      if (delta[["X"]] != 0) {
        lower <- ceiling((min(start[["X"]], end[["X"]]) - terra::xmin(source_extent)) / resolution[[1L]])
        upper <- floor((max(start[["X"]], end[["X"]]) - terra::xmin(source_extent)) / resolution[[1L]])
        if (lower <= upper) {
          k <- seq.int(lower, upper)
          breaks <- c(breaks, (terra::xmin(source_extent) + k * resolution[[1L]] - start[["X"]]) / delta[["X"]])
        }
      }
      if (delta[["Y"]] != 0) {
        lower <- ceiling((min(start[["Y"]], end[["Y"]]) - terra::ymin(source_extent)) / resolution[[2L]])
        upper <- floor((max(start[["Y"]], end[["Y"]]) - terra::ymin(source_extent)) / resolution[[2L]])
        if (lower <= upper) {
          k <- seq.int(lower, upper)
          breaks <- c(breaks, (terra::ymin(source_extent) + k * resolution[[2L]] - start[["Y"]]) / delta[["Y"]])
        }
      }
      breaks <- sort(unique(pmax(0, pmin(1, breaks[is.finite(breaks) & breaks >= 0 & breaks <= 1]))))
      intervals <- diff(breaks)
      if (!length(intervals)) next
      middle <- (head(breaks, -1L) + tail(breaks, -1L)) / 2
      xy <- cbind(start[["X"]] + middle * delta[["X"]], start[["Y"]] + middle * delta[["Y"]])
      cells <- terra::cellFromXY(raster, xy)
      keep <- !is.na(cells) & intervals > 0
      if (any(keep)) {
        position <- position + 1L
        result[[position]] <- data.table::data.table(cell = as.numeric(cells[keep]), weight = intervals[keep] * length_m)
      }
    }
  }
  if (!length(result)) return(data.table::data.table(cell = numeric(), weight = numeric()))
  data.table::rbindlist(result)[, .(weight = sum(weight)), by = cell]
}

geometry_cell_support <- function(observations, raster, role) {
  if (!nrow(observations)) {
    return(data.table::data.table(ID = integer(), cell = numeric(), value = numeric(), weight = numeric()))
  }
  if ("scene_id" %in% names(observations) && data.table::uniqueN(observations$scene_id) > 1L) {
    groups <- split(seq_len(nrow(observations)), observations$scene_id)
    values <- lapply(groups, function(index) {
      value <- geometry_cell_support(observations[index, ], raster, role)
      if (nrow(value)) value[, ID := as.integer(index[ID])]
      value
    })
    result <- data.table::rbindlist(values, use.names = TRUE)
    data.table::setorder(result, ID, cell)
    return(result)
  }
  box <- sf::st_bbox(observations)
  resolution <- terra::res(raster)
  local_extent <- terra::ext(
    box[["xmin"]] - resolution[[1L]], box[["xmax"]] + resolution[[1L]],
    box[["ymin"]] - resolution[[2L]], box[["ymax"]] + resolution[[2L]]
  )
  raster <- terra::crop(raster, local_extent, snap = "out")
  geometry <- sf::st_geometry(observations)
  if (identical(role, "building")) {
    cells <- sf::st_as_sf(terra::as.polygons(
      raster, values = TRUE, aggregate = FALSE, na.rm = FALSE
    ))
    value_column <- setdiff(names(cells), attr(cells, "sf_column"))[[1L]]
    cells$cell <- seq_len(nrow(cells))
    names(cells)[names(cells) == value_column] <- "value"
    entities <- sf::st_sf(ID = seq_len(nrow(observations)), geometry = geometry, crs = 5186L)
    intersections <- suppressWarnings(sf::st_intersection(entities, cells))
    if (!nrow(intersections)) {
      return(data.table::data.table(ID = integer(), cell = numeric(), value = numeric(), weight = numeric()))
    }
    weights <- as.numeric(sf::st_area(intersections))
    keep <- weights > 0
    return(data.table::data.table(
      ID = as.integer(intersections$ID[keep]), cell = as.numeric(intersections$cell[keep]),
      value = as.numeric(intersections$value[keep]), weight = weights[keep]
    ))
  }
  if (identical(role, "road")) {
    pieces <- lapply(seq_along(geometry), function(index) {
      value <- line_cell_support_one(geometry[[index]], raster)
      if (!nrow(value)) return(data.table::data.table(ID = integer(), cell = numeric(), weight = numeric()))
      value[, ID := as.integer(index)]
      value
    })
    result <- data.table::rbindlist(pieces, use.names = TRUE, fill = TRUE)
    if (!nrow(result)) return(data.table::data.table(ID = integer(), cell = numeric(), value = numeric(), weight = numeric()))
    cell_values <- terra::extract(raster, unique(result$cell))[[1L]]
    result[, value := as.numeric(cell_values[match(cell, unique(result$cell))])]
    return(result[, .(ID, cell, value, weight)])
  }
  coordinates <- sf::st_coordinates(geometry)
  cells <- terra::cellFromXY(raster, coordinates[, c("X", "Y"), drop = FALSE])
  values <- terra::extract(raster, cells)[[1L]]
  data.table::data.table(ID = seq_along(geometry), cell = as.numeric(cells), value = as.numeric(values), weight = 1)
}

object_total_support <- function(observations, role) {
  if (identical(role, "building")) return(as.numeric(observations$observed_area_m2))
  if (identical(role, "road")) return(as.numeric(observations$observed_length_m))
  rep(1, nrow(observations))
}

summarize_landcover_context <- function(observations, raster, role, config) {
  support <- geometry_cell_support(observations, raster, role)
  total <- object_total_support(observations, role)
  class_codes <- as.integer(unlist(config$scientific$scene_level$landcover$class_codes))
  unknown <- unique(support$value[!is.na(support$value) & !support$value %in% class_codes])
  if (length(unknown)) stop("Unknown object land-cover category code", call. = FALSE)
  valid <- support[!is.na(value)]
  aggregated <- valid[, .(class_support = sum(weight)), by = .(ID, value)]
  matrix_support <- matrix(0, nrow = nrow(observations), ncol = length(class_codes))
  if (nrow(aggregated)) matrix_support[cbind(aggregated$ID, match(as.integer(aggregated$value), class_codes))] <- aggregated$class_support
  valid_support <- rowSums(matrix_support)
  all_support <- support[, .(cell_support = sum(weight)), by = ID]
  measured <- numeric(nrow(observations)); measured[all_support$ID] <- all_support$cell_support
  tolerance <- pmax(
    if (role == "building") as.numeric(config$scientific$numerical_tolerance$support_absolute_polygon_m2) else
      if (role == "road") as.numeric(config$scientific$numerical_tolerance$support_absolute_line_m) else 0,
    total * as.numeric(config$scientific$numerical_tolerance$support_relative)
  )
  failed <- which(abs(measured - total) > tolerance)
  if (length(failed)) stop(
    "Land-cover object support does not preserve observed geometry measure for ", role,
    "; count=", length(failed), "; max_residual=", max(abs(measured[failed] - total[failed])),
    "; example_source_id=", observations$source_entity_id[failed[[1L]]], call. = FALSE
  )
  residual <- measured - total
  scale <- ifelse(measured > 0, total / measured, 1)
  matrix_support <- matrix_support * scale
  valid_support <- rowSums(matrix_support)
  fractions <- matrix_support
  positive <- valid_support > 0
  fractions[positive, ] <- fractions[positive, , drop = FALSE] / valid_support[positive]
  nodata <- pmax(total - valid_support, 0)
  list(
    support = matrix_support, fraction = fractions, total = total, valid = valid_support, nodata = nodata,
    valid_ratio = ifelse(total > 0, valid_support / total, 0),
    valid_cells = tabulate(valid$ID, nbins = nrow(observations)),
    nodata_cells = tabulate(support[is.na(value), ID], nbins = nrow(observations)),
    residual = residual, unknown_count = length(unknown)
  )
}

summarize_dem_context <- function(observations, raster, role, config) {
  support <- geometry_cell_support(observations, raster, role)
  total <- object_total_support(observations, role)
  valid <- support[!is.na(value)]
  summary <- valid[, {
    weight_sum <- sum(weight)
    mean_value <- sum(weight * value) / weight_sum
    list(valid = weight_sum, mean = mean_value, sd = sqrt(sum(weight * (value - mean_value)^2) / weight_sum), valid_cells = .N)
  }, by = ID]
  output <- data.table::data.table(ID = seq_len(nrow(observations)), total = total)
  output <- summary[output, on = "ID"]
  output[is.na(valid), `:=`(valid = 0, valid_cells = 0L)]
  all_support <- support[, .(cell_support = sum(weight)), by = ID]
  output[, measured := 0]
  output[all_support, on = "ID", measured := i.cell_support]
  tolerance <- pmax(
    if (role == "building") as.numeric(config$scientific$numerical_tolerance$support_absolute_polygon_m2) else
      if (role == "road") as.numeric(config$scientific$numerical_tolerance$support_absolute_line_m) else 0,
    total * as.numeric(config$scientific$numerical_tolerance$support_relative)
  )
  failed <- which(abs(output$measured - total) > tolerance)
  if (length(failed)) stop(
    "DEM object support does not preserve observed geometry measure for ", role,
    "; count=", length(failed), "; max_residual=", max(abs(output$measured[failed] - total[failed])),
    "; example_source_id=", observations$source_entity_id[failed[[1L]]], call. = FALSE
  )
  output[, residual := measured - total]
  output[measured > 0, valid := valid * total / measured]
  output[, `:=`(
    nodata = pmax(total - valid, 0), valid_ratio = ifelse(total > 0, valid / total, 0),
    nodata_cells = tabulate(support[is.na(value), ID], nbins = nrow(observations))
  )]
  output
}

build_object_raster_context <- function(observations, landcover, dem, vector_dataset_id, raster_dataset_id, config) {
  roles <- c(building = "B", road = "R", poi = "P")
  outputs <- lapply(names(roles), function(role) {
    value <- observations[[role]]
    lc <- summarize_landcover_context(value, landcover, role, config)
    de <- summarize_dem_context(value, dem, role, config)
    dropped <- sf::st_drop_geometry(value)
    result <- data.table::data.table(
      scene_id = as.character(dropped$scene_id), scene_footprint_id = as.character(dropped$scene_footprint_id),
      split = as.character(dropped$split), entity_type = as.character(dropped$entity_type),
      source_entity_id = as.character(dropped$source_entity_id), local_entity_id = as.integer(dropped$local_entity_id),
      vector_observation_dataset_id = vector_dataset_id, raster_observation_dataset_id = raster_dataset_id,
      support_measure_unit = if (role == "building") "m2" else if (role == "road") "m" else "point",
      lc_total_support = lc$total, lc_valid_support = lc$valid, lc_nodata_support = lc$nodata,
      lc_valid_support_ratio = lc$valid_ratio, lc_valid_cell_count = as.integer(lc$valid_cells),
      lc_nodata_cell_count = as.integer(lc$nodata_cells), lc_support_residual = lc$residual,
      dem_total_support = de$total, dem_valid_support = de$valid, dem_nodata_support = de$nodata,
      dem_valid_support_ratio = de$valid_ratio, dem_mean_m = de$mean, dem_sd_m = de$sd,
      dem_valid_cell_count = as.integer(de$valid_cells), dem_nodata_cell_count = as.integer(de$nodata_cells),
      dem_support_residual = de$residual
    )
    support_names <- sprintf("lc_support_%02d", seq_len(ncol(lc$support)))
    fraction_names <- sprintf("lc_fraction_%02d", seq_len(ncol(lc$fraction)))
    result[, (support_names) := data.table::as.data.table(lc$support)]
    result[, (fraction_names) := data.table::as.data.table(lc$fraction)]
    data.table::setorder(result, scene_id, local_entity_id)
    result
  })
  result <- data.table::rbindlist(outputs, use.names = TRUE)
  key <- c("scene_id", "entity_type", "source_entity_id", "local_entity_id")
  if (anyDuplicated(result[, ..key])) stop("Object raster context contains duplicate keys", call. = FALSE)
  result
}

write_raw_array <- function(value, path, dtype = "float32") {
  permutation <- rev(seq_along(dim(value)))
  flattened <- as.vector(aperm(value, permutation))
  connection <- file(path, open = "wb")
  on.exit(close(connection), add = TRUE)
  if (identical(dtype, "uint8")) {
    writeBin(as.raw(as.integer(flattened)), connection, endian = "little")
  } else {
    writeBin(as.numeric(flattened), connection, size = 4L, endian = "little")
  }
  invisible(path)
}

write_zarr_store <- function(arrays, output, attributes, config) {
  raw_dir <- tempfile(pattern = "zarr-raw-", tmpdir = dirname(output))
  dir.create(raw_dir)
  on.exit(if (dir.exists(raw_dir)) unlink(raw_dir, recursive = TRUE), add = TRUE)
  attribute_path <- file.path(raw_dir, "attributes.json")
  write_json_file(attributes, attribute_path)
  definitions <- character()
  for (name in names(arrays)) {
    item <- arrays[[name]]
    raw_path <- file.path(raw_dir, paste0(name, ".bin"))
    write_raw_array(item$value, raw_path, item$dtype)
    definitions <- c(definitions, paste(name, raw_path, item$dtype, paste(dim(item$value), collapse = ","), item$fill_value, sep = "::"))
  }
  args <- c(
    config$writer_file, "write", "--output", output, "--attributes", attribute_path,
    unlist(lapply(definitions, function(value) c("--array", value))),
    "--compression-level", as.character(config$scientific$storage$compression_level)
  )
  command_output <- system2(research_python_executable(), args, stdout = TRUE, stderr = TRUE)
  status <- attr(command_output, "status") %||% 0L
  if (status != 0L || !length(command_output)) stop("Zarr writer failed: ", paste(command_output, collapse = " | "), call. = FALSE)
  jsonlite::fromJSON(tail(command_output, 1L), simplifyVector = FALSE)
}

file_member_records <- function(directory, final_directory = directory) {
  members <- list.files(directory, recursive = TRUE, all.files = TRUE, full.names = TRUE, include.dirs = FALSE, no.. = TRUE)
  members <- members[order(sub(paste0("^", normalizePath(directory), "/?"), "", normalizePath(members)), method = "radix")]
  relative <- substring(normalizePath(members), nchar(normalizePath(directory)) + 2L)
  unname(Map(function(path, rel) list(
    path = file.path(final_directory, rel), relative_path = rel,
    size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)
  ), members, relative))
}

validate_object_context <- function(context, observations, config) {
  required <- jsonlite::read_json(config$schema_file, simplifyVector = FALSE)$`$defs`$object_context_row$required
  if (!all(unlist(required) %in% names(context))) stop("Object raster context schema is incomplete", call. = FALSE)
  expected <- data.table::rbindlist(lapply(observations, function(value) data.table::as.data.table(sf::st_drop_geometry(value))[
    , .(scene_id, entity_type, source_entity_id, local_entity_id)
  ]))
  key <- c("scene_id", "entity_type", "source_entity_id", "local_entity_id")
  key_string <- function(value) do.call(paste, c(value[, ..key], sep = "\r"))
  if (nrow(context) != nrow(expected) || anyDuplicated(context[, ..key]) || !setequal(key_string(context), key_string(expected))) {
    stop("I10 and I11 object keys differ", call. = FALSE)
  }
  fractions <- as.matrix(context[, sprintf("lc_fraction_%02d", 1:22), with = FALSE])
  valid <- context$lc_valid_support > 0
  tolerance <- as.numeric(config$scientific$numerical_tolerance$fraction_absolute)
  if (any(abs(rowSums(fractions[valid, , drop = FALSE]) - 1) > tolerance) ||
      any(rowSums(abs(fractions[!valid, , drop = FALSE])) > tolerance) ||
      any(!is.finite(context$lc_valid_support_ratio)) || any(!is.finite(context$dem_valid_support_ratio)) ||
      any(context$lc_valid_support_ratio < -tolerance | context$lc_valid_support_ratio > 1 + tolerance) ||
      any(context$dem_valid_support_ratio < -tolerance | context$dem_valid_support_ratio > 1 + tolerance) ||
      any(is.infinite(context$dem_mean_m)) || any(is.infinite(context$dem_sd_m)) ||
      any(is.na(context$dem_mean_m) != (context$dem_valid_support <= 0)) ||
      any(is.na(context$dem_sd_m) != (context$dem_valid_support <= 0))) {
    stop("Object raster context numerical invariant failed", call. = FALSE)
  }
  invisible(TRUE)
}

raster_output_names <- function() c(
  "scene_landcover.zarr", "scene_dem.zarr", "scene_raster_index.parquet",
  "object_raster_context.parquet", "zarr_member_manifest.json",
  "branch_manifest.json", "branch_qc.json", "branch_log.jsonl"
)

build_prototype_raster_observation_shard <- function(prototype_observation_plan,
                                                      prototype_vector_observation_shard,
                                                      study_data_inputs,
                                                      prototype_runtime_inputs,
                                                      raster_observation_contract_files,
                                                      workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- raster_thread_state()
  on.exit(restore_raster_threads(state), add = TRUE)
  set_raster_threads(threads)
  config <- load_raster_observation_config(raster_observation_contract_files)
  spec <- prototype_observation_plan
  vector <- read_i10_branch_context(spec, prototype_vector_observation_shard)
  landcover_path <- runtime_mirror_path(prototype_runtime_inputs, "landcover")
  dem_path <- runtime_mirror_path(prototype_runtime_inputs, "dem")
  raster_records <- list(
    landcover = raster_grid_record(landcover_path, "landcover"),
    dem = raster_grid_record(dem_path, "dem")
  )
  raster_records$landcover$path <- study_raster_path(study_data_inputs, "seoul_lc.tif")
  raster_records$dem$path <- study_raster_path(study_data_inputs, "seoul_dem.tif")
  landcover <- terra::rast(landcover_path)
  dem <- terra::rast(dem_path)
  validate_raster_coverage(landcover, spec$scenes)
  validate_raster_coverage(dem, spec$scenes)
  raster_dataset_id <- raster_observation_identity(spec, vector, raster_records, config)
  observations <- lapply(vector$files, read_standard_geoparquet)
  if (!identical(unname(vapply(observations, nrow, integer(1L))), as.integer(unlist(spec$estimated_counts[c("building", "road", "poi")]))) ) {
    stop("I10 row counts changed while reading observed geometry", call. = FALSE)
  }
  scene_ids <- vapply(spec$scenes, `[[`, character(1L), "scene_id")
  scene_order <- order(scene_ids, method = "radix")
  scenes <- spec$scenes[scene_order]
  scene_ids <- scene_ids[scene_order]
  started <- Sys.time()
  io_start <- proc_io_snapshot()
  scene_started <- Sys.time()
  scene_lc <- lapply(scenes, function(scene) scene_landcover_observation(landcover, scene, config))
  lc_seconds <- as.numeric(difftime(Sys.time(), scene_started, units = "secs"))
  dem_started <- Sys.time()
  scene_dem <- lapply(scenes, function(scene) scene_dem_observation(dem, scene, config))
  dem_seconds <- as.numeric(difftime(Sys.time(), dem_started, units = "secs"))
  lc_composition <- simplify2array(lapply(scene_lc, `[[`, "composition"))
  lc_composition <- aperm(lc_composition, c(4, 1, 2, 3))
  lc_valid <- aperm(simplify2array(lapply(scene_lc, `[[`, "valid_support_ratio")), c(3, 1, 2))
  lc_mask <- aperm(simplify2array(lapply(scene_lc, `[[`, "valid_mask")), c(3, 1, 2))
  dem_value <- aperm(simplify2array(lapply(scene_dem, `[[`, "value")), c(3, 1, 2))
  dem_valid <- aperm(simplify2array(lapply(scene_dem, `[[`, "valid_support_ratio")), c(3, 1, 2))
  dem_mask <- aperm(simplify2array(lapply(scene_dem, `[[`, "valid_mask")), c(3, 1, 2))
  context_started <- Sys.time()
  context <- build_object_raster_context(observations, landcover, dem, spec$observation_dataset_id, raster_dataset_id, config)
  context_seconds <- as.numeric(difftime(Sys.time(), context_started, units = "secs"))
  validate_object_context(context, observations, config)
  index <- data.table::rbindlist(lapply(seq_along(scenes), function(index) {
    scene <- scenes[[index]]
    data.table::data.table(
      scene_id = scene$scene_id, scene_footprint_id = scene$scene_footprint_id, split = scene$split,
      branch_id = spec$branch_id, zarr_index = as.integer(index - 1L),
      xmin = as.numeric(scene$xmin), ymin = as.numeric(scene$ymin), xmax = as.numeric(scene$xmax), ymax = as.numeric(scene$ymax),
      lc_height = 100L, lc_width = 100L, lc_pixel_width_m = 5, lc_pixel_height_m = -5,
      dem_height = 17L, dem_width = 17L, dem_pixel_width_m = 500 / 17, dem_pixel_height_m = -500 / 17,
      row_order = "north_to_south", column_order = "west_to_east",
      raster_observation_dataset_id = raster_dataset_id
    )
  }))
  if (anyDuplicated(index$scene_id) || !identical(index$scene_id, scene_ids)) stop("Scene raster index ordering failed", call. = FALSE)
  observations_root <- dirname(dirname(dirname(dirname(spec$output$directory))))
  final_dir <- file.path(observations_root, raster_dataset_id, "raster", "branches", spec$branch_id)
  output_names <- raster_output_names()
  paths <- publish_deterministic_directory(
    final_dir, output_names,
    compare_basenames = c("scene_raster_index.parquet", "object_raster_context.parquet", "zarr_member_manifest.json"),
    writer = function(stage) {
      zarr_started <- Sys.time()
      common_attributes <- list(
        schema_version = config$scientific$raster_observation_contract_version,
        raster_observation_dataset_id = raster_dataset_id, branch_id = spec$branch_id,
        scene_ids = as.list(scene_ids), crs = "EPSG:5186",
        orientation = config$scientific$scene_level$orientation
      )
      lc_zarr <- write_zarr_store(list(
        class_fraction = list(value = lc_composition, dtype = "float32", fill_value = -1),
        valid_support_ratio = list(value = lc_valid, dtype = "float32", fill_value = -1),
        valid_mask = list(value = lc_mask, dtype = "uint8", fill_value = 255)
      ), file.path(stage, output_names[[1L]]), c(common_attributes, list(modality = "landcover", class_codes = as.list(1:22))), config)
      dem_zarr <- write_zarr_store(list(
        raw_mean_m = list(value = dem_value, dtype = "float32", fill_value = config$scientific$scene_level$dem$invalid_value_fill),
        valid_support_ratio = list(value = dem_valid, dtype = "float32", fill_value = -1),
        valid_mask = list(value = dem_mask, dtype = "uint8", fill_value = 255)
      ), file.path(stage, output_names[[2L]]), c(common_attributes, list(modality = "dem", unit = "m")), config)
      zarr_seconds <- as.numeric(difftime(Sys.time(), zarr_started, units = "secs"))
      parquet_started <- Sys.time()
      arrow::write_parquet(index, file.path(stage, output_names[[3L]]), compression = config$scientific$storage$parquet_compression)
      arrow::write_parquet(context, file.path(stage, output_names[[4L]]), compression = config$scientific$storage$parquet_compression,
                           chunk_size = as.integer(config$scientific$storage$parquet_row_group_size))
      parquet_seconds <- as.numeric(difftime(Sys.time(), parquet_started, units = "secs"))
      zarr_members <- list(
        schema_version = "1.0.0", raster_observation_dataset_id = raster_dataset_id, branch_id = spec$branch_id,
        stores = list(
          landcover = list(path = file.path(final_dir, output_names[[1L]]), members = file_member_records(file.path(stage, output_names[[1L]]), file.path(final_dir, output_names[[1L]]))),
          dem = list(path = file.path(final_dir, output_names[[2L]]), members = file_member_records(file.path(stage, output_names[[2L]]), file.path(final_dir, output_names[[2L]])))
        )
      )
      write_json_file(zarr_members, file.path(stage, output_names[[5L]]))
      elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
      io_end <- proc_io_snapshot()
      type_counts <- context[, .N, by = entity_type]
      counts <- as.list(setNames(type_counts$N, c(B = "building", R = "road", P = "poi")[type_counts$entity_type]))
      lc_nodata_scenes <- sum(vapply(scene_lc, function(x) x$nodata_cell_count > 0, logical(1L)))
      dem_nodata_scenes <- sum(vapply(scene_dem, function(x) x$nodata_cell_count > 0, logical(1L)))
      lc_nodata_entities <- sum(context$lc_valid_support_ratio < 1)
      dem_nodata_entities <- sum(context$dem_valid_support_ratio < 1)
      failures <- character()
      if (any(!unique(context$scene_id) %in% scene_ids)) failures <- c(failures, "object_scene_set")
      if (anyDuplicated(context[, .(scene_id, local_entity_id)])) failures <- c(failures, "duplicate_object_key")
      if (length(failures)) stop("Raster branch QC failed: ", paste(failures, collapse = ", "), call. = FALSE)
      log_records <- list(
        list(time = format(started, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul"), event = "branch_started", branch_id = spec$branch_id),
        list(time = kst_now(), event = "branch_completed", branch_id = spec$branch_id, status = "PASS", scenes = length(scenes), entities = nrow(context))
      )
      write_json_lines(log_records, file.path(stage, output_names[[8L]]))
      qc <- list(
        qc_schema_version = "1.0.0", branch_id = spec$branch_id, status = "PASS", failures = as.list(failures),
        scene_count = length(scenes), scene_set_aligned = TRUE, scene_index_unique = TRUE,
        entity_rows = counts, object_key_match = TRUE, object_duplicate_keys = 0L,
        landcover = list(
          shape = as.list(dim(lc_composition)), dtype = "float32", category_dimension = 22L,
          unknown_category_count = sum(vapply(scene_lc, `[[`, numeric(1L), "unknown_category_count")),
          nodata_scene_count = lc_nodata_scenes, nodata_entity_count = lc_nodata_entities,
          histogram = as.list(Reduce(`+`, lapply(scene_lc, `[[`, "histogram")))
        ),
        dem = list(
          shape = as.list(dim(dem_value)), dtype = "float32", feature_dimension = 2L,
          minimum_m = min(vapply(scene_dem, `[[`, numeric(1L), "minimum_m"), na.rm = TRUE),
          maximum_m = max(vapply(scene_dem, `[[`, numeric(1L), "maximum_m"), na.rm = TRUE),
          nodata_scene_count = dem_nodata_scenes, nodata_entity_count = dem_nodata_entities
        ),
        zarr = list(landcover = lc_zarr, dem = dem_zarr), warnings = list()
      )
      write_json_file(qc, file.path(stage, output_names[[7L]]))
      output_records <- c(
        list(list(path = file.path(final_dir, output_names[[1L]]), artifact_type = "zarr_directory", size_bytes = lc_zarr$size_bytes,
                  member_manifest = file.path(final_dir, output_names[[5L]]))),
        list(list(path = file.path(final_dir, output_names[[2L]]), artifact_type = "zarr_directory", size_bytes = dem_zarr$size_bytes,
                  member_manifest = file.path(final_dir, output_names[[5L]]))),
        lapply(file.path(stage, output_names[c(3L, 4L, 5L, 7L, 8L)]), function(path) list(
          path = file.path(final_dir, basename(path)), artifact_type = "file", size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)
        ))
      )
      manifest <- list(
        manifest_schema_version = "1.0.0", branch_id = spec$branch_id,
        raster_observation_dataset_id = raster_dataset_id, vector_observation_dataset_id = spec$observation_dataset_id,
        prototype_id = spec$prototype_id, scene_index_id = spec$scene_index_id, status = "PASS",
        inputs = list(
          observation_spec_path = normalizePath(spec$.path, mustWork = TRUE),
          vector_branch_manifest_path = vector$manifest_path, vector_branch_manifest_sha256 = sha256_file(vector$manifest_path),
          rasters = raster_records, config_hash = config$scientific_hash, schema_hash = config$schema_hash,
          writer_hash = config$writer_hash, requirements_hash = config$requirements_hash,
          implementation_source_hash = config$implementation_source_hash
        ),
        execution = list(
          controller = spec$execution$controller, workers = 1L, threads = 1L,
          wall_time_seconds = elapsed, max_rss_kb = proc_max_rss_kb(),
          read_bytes = io_end$read_bytes - io_start$read_bytes, write_bytes = io_end$write_bytes - io_start$write_bytes,
          landcover_scene_seconds = lc_seconds, dem_scene_seconds = dem_seconds,
          object_context_seconds = context_seconds, zarr_write_seconds = zarr_seconds, parquet_write_seconds = parquet_seconds
        ),
        scene_ids = as.list(scene_ids), scene_count = length(scenes), entity_rows = counts,
        arrays = list(landcover = lc_zarr, dem = dem_zarr), object_context_schema = names(context),
        outputs = output_records, warnings = list(), status_final = "PASS"
      )
      write_json_file(manifest, file.path(stage, output_names[[6L]]))
    }
  )
  normalizePath(paths[c(3L, 4L, 5L, 6L, 7L, 8L)], mustWork = TRUE)
}
