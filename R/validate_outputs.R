validate_gpkg_common <- function(path, required_layers, spatial_layers) {
  if (!file.exists(path) || !sqlite_integrity(path)) stop("Invalid or missing GeoPackage: ", path, call. = FALSE)
  layers <- gpkg_layers(path)
  if (!all(required_layers %in% layers)) stop("Missing layers in ", path, call. = FALSE)
  for (layer in spatial_layers) ensure_spatial_index(path, layer, "geom")
  list(layers = layers, integrity = "PASS", spatial_index = "PASS")
}

validate_vector_crs <- function(path, layer, epsg = 5186L) {
  object <- sf::st_read(path, query = sprintf("SELECT geom FROM %s LIMIT 1", layer), quiet = TRUE)
  if (!identical(sf::st_crs(object)$epsg, as.integer(epsg))) stop("Unexpected CRS for ", path, " layer ", layer, call. = FALSE)
  sprintf("EPSG:%d", epsg)
}

validate_boundary_outputs <- function(boundary_file, buffer_file, config) {
  validate_gpkg_common(boundary_file, c("research_area", "metadata"), "research_area")
  validate_gpkg_common(buffer_file, c("research_area", "metadata"), "research_area")
  boundary <- sf::st_read(boundary_file, layer = "research_area", quiet = TRUE)
  buffer <- sf::st_read(buffer_file, layer = "research_area", quiet = TRUE)
  if (nrow(boundary) != 1L || nrow(buffer) != 1L ||
      !identical(sf::st_crs(boundary)$epsg, 5186L) || !identical(sf::st_crs(buffer)$epsg, 5186L)) {
    stop("Boundary/buffer count or CRS QC failed", call. = FALSE)
  }
  expected <- sf::st_buffer(sf::st_union(sf::st_geometry(boundary)), as.numeric(config$methodology$study_area$source_buffer_m))
  symmetric_difference <- sf::st_sym_difference(sf::st_union(sf::st_geometry(buffer)), expected)
  symmetric_difference_area <- if (length(symmetric_difference) == 0L) {
    0
  } else {
    sum(as.numeric(sf::st_area(symmetric_difference)))
  }
  if (!is.finite(symmetric_difference_area) || symmetric_difference_area > 1e-4) {
    stop("Stored 400 m buffer differs from a deterministic recomputation", call. = FALSE)
  }
  list(
    boundary_area_m2 = as.numeric(sf::st_area(boundary)),
    buffer_area_m2 = as.numeric(sf::st_area(buffer)),
    boundary_extent = as.list(sf::st_bbox(boundary)),
    buffer_extent = as.list(sf::st_bbox(buffer)),
    buffer_distance_m = as.numeric(config$methodology$study_area$source_buffer_m),
    symmetric_difference_area_m2 = symmetric_difference_area,
    crs = "EPSG:5186",
    status = "PASS"
  )
}

validate_building_subset <- function(path) {
  common <- validate_gpkg_common(path, c("buildings", "metadata"), "buildings")
  metadata <- read_gpkg_metadata(path)
  count <- gpkg_count(path, "buildings")
  unique <- as.numeric(ogr_scalar(path, "SELECT COUNT(DISTINCT building_feature_id) AS value FROM buildings"))
  invalid <- as.numeric(ogr_scalar(path, "SELECT COUNT(*) AS value FROM buildings WHERE NOT ST_IsValid(geom)"))
  fields <- gpkg_fields(path, "buildings")
  required <- c("building_feature_id", "A9", "A11", "A14", "source_archive", "source_layer", "source_record_index")
  if (count <= 0 || count != unique || invalid != 0 || !all(required %in% fields) ||
      as.numeric(metadata$selected_count) != count || !grepl("NONE", metadata$geometry_operation, fixed = TRUE)) {
    stop("Building subset hard QC failed", call. = FALSE)
  }
  c(common, list(
    count = count, unique_building_feature_id = unique, invalid_geometry = invalid,
    canonical_count = 14388603, candidate_count = as.numeric(metadata$candidate_count),
    geometry_clipped = FALSE, required_fields = required,
    crs = validate_vector_crs(path, "buildings"), status = "PASS"
  ))
}

validate_road_subset <- function(path, config, buffer_bbox) {
  required_layers <- c("links", "nodes", "multilink", "turninfo", "metadata")
  common <- validate_gpkg_common(path, required_layers, c("links", "nodes"))
  metadata <- read_gpkg_metadata(path)
  counts <- setNames(vapply(required_layers[1:4], function(layer) gpkg_count(path, layer), numeric(1L)), required_layers[1:4])
  orphan <- as.numeric(ogr_scalar(path, paste0(
    "SELECT COUNT(*) AS value FROM links l LEFT JOIN nodes f ON l.F_NODE=f.NODE_ID ",
    "LEFT JOIN nodes t ON l.T_NODE=t.NODE_ID WHERE f.NODE_ID IS NULL OR t.NODE_ID IS NULL"
  )))
  dangling_multilink <- as.numeric(ogr_scalar(path, "SELECT COUNT(*) AS value FROM multilink m LEFT JOIN links l ON m.LINK_ID=l.LINK_ID WHERE l.LINK_ID IS NULL"))
  dangling_turn <- as.numeric(ogr_scalar(path, paste0(
    "SELECT COUNT(*) AS value FROM turninfo t LEFT JOIN nodes n ON t.NODE_ID=n.NODE_ID ",
    "LEFT JOIN links s ON t.ST_LINK=s.LINK_ID LEFT JOIN links e ON t.ED_LINK=e.LINK_ID ",
    "WHERE n.NODE_ID IS NULL OR s.LINK_ID IS NULL OR e.LINK_ID IS NULL"
  )))
  endpoint_start <- as.numeric(ogr_scalar(path, "SELECT MAX(ST_Distance(ST_StartPoint(l.geom),n.geom)) AS value FROM links l JOIN nodes n ON l.F_NODE=n.NODE_ID"))
  endpoint_end <- as.numeric(ogr_scalar(path, "SELECT MAX(ST_Distance(ST_EndPoint(l.geom),n.geom)) AS value FROM links l JOIN nodes n ON l.T_NODE=n.NODE_ID"))
  endpoint_max <- max(endpoint_start, endpoint_end)
  extent <- road_layer_bbox(path, "links")
  intersects_buffer <- extent[["xmin"]] <= buffer_bbox[["xmax"]] &&
    extent[["xmax"]] >= buffer_bbox[["xmin"]] &&
    extent[["ymin"]] <= buffer_bbox[["ymax"]] &&
    extent[["ymax"]] >= buffer_bbox[["ymin"]]
  if (counts[["links"]] <= 0 || counts[["nodes"]] <= 0 || orphan != 0 ||
      dangling_multilink != 0 || dangling_turn != 0 ||
      endpoint_max > as.numeric(config$methodology$road$endpoint_tolerance_m) ||
      !intersects_buffer ||
      !identical(metadata$proj_operation, config$methodology$road$source_to_output_pipeline)) {
    stop("Road subset hard QC failed", call. = FALSE)
  }
  c(common, list(
    counts = as.list(counts), canonical_counts = list(links = 1555150, nodes = 1178457, multilink = 18916, turninfo = 44218),
    orphan_node_references = orphan, dangling_multilink = dangling_multilink,
    dangling_turninfo = dangling_turn, endpoint_max_error_m = endpoint_max,
    endpoint_tolerance_m = as.numeric(config$methodology$road$endpoint_tolerance_m),
    extent = as.list(extent), intersects_buffer = intersects_buffer,
    crs = c(links = validate_vector_crs(path, "links"), nodes = validate_vector_crs(path, "nodes")),
    transformation = list(definition = metadata$proj_operation, description = metadata$proj_operation_description,
                          accuracy = metadata$proj_accuracy, coordinate_change_m = as.numeric(metadata$source_target_coordinate_change_m)),
    con_relation_created = FALSE, status = "PASS"
  ))
}

validate_poi_subset <- function(path) {
  required_layers <- c("points", "addresses", "foreign_names", "aliases", "category_lookup", "metadata")
  common <- validate_gpkg_common(path, required_layers, "points")
  metadata <- read_gpkg_metadata(path)
  counts <- setNames(vapply(required_layers[1:5], function(layer) gpkg_count(path, layer), numeric(1L)), required_layers[1:5])
  unique <- as.numeric(ogr_scalar(path, "SELECT COUNT(DISTINCT NF_ID) AS value FROM points"))
  aux_dangling <- c(
    addresses = as.numeric(ogr_scalar(path, "SELECT COUNT(*) AS value FROM addresses a LEFT JOIN points p ON a.NF_ID=p.NF_ID WHERE p.NF_ID IS NULL")),
    foreign_names = as.numeric(ogr_scalar(path, "SELECT COUNT(*) AS value FROM foreign_names a LEFT JOIN points p ON a.NF_ID=p.NF_ID WHERE p.NF_ID IS NULL")),
    aliases = as.numeric(ogr_scalar(path, "SELECT COUNT(*) AS value FROM aliases a LEFT JOIN points p ON a.POIID=p.NF_ID WHERE p.NF_ID IS NULL"))
  )
  hierarchy <- c("NF_ID", paste0("CLASS_L", rep(1:6, each = 2L), rep(c("_CODE", "_STATE"), 6L)))
  if (counts[["points"]] <= 0 || unique != counts[["points"]] ||
      counts[["addresses"]] != counts[["points"]] || counts[["foreign_names"]] != counts[["points"]] ||
      any(aux_dangling != 0) || !all(hierarchy %in% gpkg_fields(path, "points")) ||
      !identical(metadata$category_filtering, "FALSE") || !identical(metadata$fuzzy_deduplication, "FALSE")) {
    stop("POI subset hard QC failed", call. = FALSE)
  }
  c(common, list(
    counts = as.list(counts), canonical_count = 9801999, unique_nf_id = unique,
    auxiliary_dangling = as.list(aux_dangling), hierarchy_fields = hierarchy,
    crs = validate_vector_crs(path, "points"), transformation = metadata$proj_operation,
    status = "PASS"
  ))
}

validate_landcover_subset <- function(path, buffer_bbox, source_path) {
  info <- gdal_json(path)
  source <- gdal_json(source_path)
  gt <- unlist(info$geoTransform)
  source_gt <- unlist(source$geoTransform)
  extent <- raster_extent(info)
  band <- info$bands[[1L]]
  metadata <- gdal_default_metadata(info)
  band_metadata <- gdal_default_metadata(band)
  categories <- paste0("LC_VALUE_", sprintf("%02d", 1:22))
  if (!identical(info$metadata$IMAGE_STRUCTURE$LAYOUT, "COG") || !identical(band$type, "Byte") ||
      as.numeric(band$noDataValue) != 0 || abs(gt[[2L]] - 5) > 1e-9 || abs(gt[[6L]] + 5) > 1e-9 ||
      abs((gt[[1L]] - source_gt[[1L]]) / 5 - round((gt[[1L]] - source_gt[[1L]]) / 5)) > 1e-8 ||
      abs((source_gt[[4L]] - gt[[4L]]) / 5 - round((source_gt[[4L]] - gt[[4L]]) / 5)) > 1e-8 ||
      !extent_covers_bbox(extent, buffer_bbox) || !all(categories %in% names(metadata)) ||
      !identical(info$metadata$IMAGE_STRUCTURE$OVERVIEW_RESAMPLING, "NEAREST")) {
    stop("Land-cover subset hard QC failed", call. = FALSE)
  }
  list(
    dimensions = unlist(info$size), extent = as.list(extent), resolution = c(5, 5),
    crs = "EPSG:5186", datatype = band$type, nodata = band$noDataValue,
    min = as.numeric(band_metadata$STATISTICS_MINIMUM),
    max = as.numeric(band_metadata$STATISTICS_MAXIMUM),
    source_lattice_aligned = TRUE, resampling = "none", overview_resampling = "nearest",
    category_metadata_count = 22, buffer_covered = TRUE, cog = "PASS", status = "PASS"
  )
}

validate_dem_subset <- function(path, buffer_bbox, config) {
  info <- gdal_json(path)
  gt <- unlist(info$geoTransform)
  extent <- raster_extent(info)
  band <- info$bands[[1L]]
  metadata <- gdal_default_metadata(info)
  band_metadata <- gdal_default_metadata(band)
  resolution <- as.numeric(config$methodology$dem$resolution_m)
  anchor_x <- as.numeric(config$methodology$dem$grid_anchor_x_m)
  anchor_y <- as.numeric(config$methodology$dem$grid_anchor_y_m)
  if (!identical(info$metadata$IMAGE_STRUCTURE$LAYOUT, "COG") || !identical(band$type, "Int16") ||
      as.numeric(band$noDataValue) != -32767 || abs(gt[[2L]] - resolution) > 1e-9 || abs(gt[[6L]] + resolution) > 1e-9 ||
      abs((gt[[1L]] - anchor_x) / resolution - round((gt[[1L]] - anchor_x) / resolution)) > 1e-8 ||
      abs((gt[[4L]] - anchor_y) / resolution - round((gt[[4L]] - anchor_y) / resolution)) > 1e-8 ||
      !extent_covers_bbox(extent, buffer_bbox) || !identical(metadata$WARP_RESAMPLING, "BILINEAR") ||
      !identical(info$metadata$IMAGE_STRUCTURE$OVERVIEW_RESAMPLING, "AVERAGE")) {
    stop("DEM subset hard QC failed", call. = FALSE)
  }
  list(
    dimensions = unlist(info$size), extent = as.list(extent), resolution = c(resolution, resolution),
    grid_anchor = c(anchor_x, anchor_y), crs = "EPSG:5186", datatype = band$type,
    nodata = band$noDataValue, min = as.numeric(band_metadata$STATISTICS_MINIMUM),
    max = as.numeric(band_metadata$STATISTICS_MAXIMUM),
    valid_percent = as.numeric(band_metadata$STATISTICS_VALID_PERCENT),
    negative_elevation_policy = "preserved; no clamping", resampling = "bilinear",
    overview_resampling = "average excluding nodata", buffer_covered = TRUE, cog = "PASS", status = "PASS"
  )
}

validate_seoul_subset <- function(config, canonical_manifest, canonical_inputs, boundary_source,
                                  boundary_file, buffer_file, building_file, road_file, poi_file,
                                  landcover_file, dem_file) {
  boundary <- validate_boundary_outputs(boundary_file, buffer_file, config)
  buffer_bbox <- unlist(boundary$buffer_extent)
  files <- list(boundary = boundary_file, buffer400 = buffer_file, building = building_file,
                road = road_file, poi = poi_file, landcover = landcover_file, dem = dem_file)
  outputs <- lapply(files, function(path) list(path = path, size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)))
  qc <- list(
    boundary = boundary,
    building = validate_building_subset(building_file),
    road = validate_road_subset(road_file, config, buffer_bbox),
    poi = validate_poi_subset(poi_file),
    landcover = validate_landcover_subset(landcover_file, buffer_bbox, canonical_inputs$landcover$path),
    dem = validate_dem_subset(dem_file, buffer_bbox, config)
  )
  if (any(vapply(qc, function(x) !identical(x$status, "PASS"), logical(1L)))) stop("At least one subset QC failed", call. = FALSE)
  list(
    status = "PASS", generated_at = kst_now(), config_sha256 = config$config_sha256,
    canonical = list(schema_version = canonical_manifest$schema_version, snapshot_id = canonical_manifest$snapshot_id,
                     manifest = canonical_inputs$manifest, inputs = canonical_inputs[c("building", "road", "poi", "landcover", "dem")]),
    boundary_source = boundary_source, outputs = outputs, qc = qc,
    contract_version = config$methodology$contract$study_subset_version,
    git_commit = trimws(run_command("git", c("-C", config$paths$repository$root, "rev-parse", "HEAD"), capture = TRUE)[[1L]]),
    thesis_commit = trimws(run_command("git", c("-C", config$paths$repository$thesis, "rev-parse", "HEAD"), capture = TRUE)[[1L]]),
    software = software_versions(),
    execution = list(
      backend = if (as.integer(config$methodology$runtime$workers) > 1L) {
        "single targets target + future multisession"
      } else {
        "single targets target + sequential lapply"
      },
      workers = as.integer(config$methodology$runtime$workers),
      threads_per_worker = as.integer(config$methodology$runtime$threads_per_worker)
    ),
    deferred = c("500 m scenes", "250 m lattice", "scene clipping", "observed attributes", "spatial relations", "model training")
  )
}
