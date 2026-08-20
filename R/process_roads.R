# Thesis: Section 3.4 spatial relations. Preserve source node topology for the
# later CON relation; no relation edges are constructed in this target.

road_crs_audit <- function(source) {
  sample <- sf::st_read(source, query = "SELECT geom FROM links LIMIT 1", quiet = TRUE)
  source_crs <- sf::st_crs(sample)
  target_crs <- sf::st_crs(5186)
  pipelines <- sf::sf_proj_pipelines(source_crs, target_crs, AOI = c(126.7, 37.4, 127.3, 37.8))
  if (nrow(pipelines) != 1L || !isTRUE(pipelines$instantiable[[1L]])) {
    stop("Road CRS does not have one instantiable operation", call. = FALSE)
  }
  transformed <- sf::st_transform(sample, target_crs)
  coordinate_change <- max(abs(sf::st_coordinates(sample) - sf::st_coordinates(transformed)), na.rm = TRUE)
  list(
    source_wkt = source_crs$wkt,
    target_wkt = target_crs$wkt,
    operation_id = pipelines$id[[1L]],
    operation_description = pipelines$description[[1L]],
    operation_definition = pipelines$definition[[1L]],
    operation_accuracy_m = pipelines$accuracy[[1L]],
    coordinate_change_m = coordinate_change,
    ballpark = grepl("Ballpark", pipelines$description[[1L]], fixed = TRUE)
  )
}

road_required_node_ids <- function(from_node, to_node) {
  sort(unique(c(as.character(from_node), as.character(to_node))))
}

road_layer_bbox <- function(gpkg, layer) {
  values <- c(
    xmin = as.numeric(ogr_scalar(gpkg, sprintf("SELECT MIN(ST_MinX(geom)) AS value FROM %s", layer))),
    ymin = as.numeric(ogr_scalar(gpkg, sprintf("SELECT MIN(ST_MinY(geom)) AS value FROM %s", layer))),
    xmax = as.numeric(ogr_scalar(gpkg, sprintf("SELECT MAX(ST_MaxX(geom)) AS value FROM %s", layer))),
    ymax = as.numeric(ogr_scalar(gpkg, sprintf("SELECT MAX(ST_MaxY(geom)) AS value FROM %s", layer)))
  )
  if (any(!is.finite(values))) stop("Cannot calculate road layer bbox", call. = FALSE)
  values
}

subset_seoul_roads <- function(canonical_inputs, buffer_file, config, sqlite_helper) {
  source <- canonical_inputs$road$path
  final <- config$paths$study$road
  buffer_hash <- sha256_file(buffer_file)
  crs_audit <- road_crs_audit(source)
  approved_pipeline <- config$methodology$road$source_to_output_pipeline
  if (!identical(crs_audit$coordinate_change_m, 0)) {
    stop("The PROJ-selected road operation unexpectedly changes coordinates", call. = FALSE)
  }
  if (!grepl("proj=axisswap", approved_pipeline, fixed = TRUE)) {
    stop("The explicit GDAL road pipeline must preserve GIS data-axis order", call. = FALSE)
  }
  fingerprint <- artifact_fingerprint(
    "seoul_road", canonical_inputs$road$sha256, buffer_hash, approved_pipeline,
    config$methodology$contract$study_subset_version
  )
  if (existing_gpkg_matches(final, fingerprint)) return(final)
  if (file.exists(final)) stop("Conflicting existing Seoul road subset: ", final, call. = FALSE)
  work <- file.path(config$paths$study$staging, sprintf("road_source_%s_%s.gpkg", Sys.getpid(), format(Sys.time(), "%Y%m%d%H%M%S")))
  source_buffer <- file.path(config$paths$study$staging, sprintf("road_buffer_%s.gpkg", Sys.getpid()))
  stage <- stage_path(final)
  on.exit(unlink(c(work, source_buffer, stage), force = TRUE), add = TRUE)

  buffer <- sf::st_read(buffer_file, layer = "research_area", quiet = TRUE)
  source_sample <- sf::st_read(source, query = "SELECT geom FROM links LIMIT 1", quiet = TRUE)
  buffer_source <- sf::st_transform(buffer, sf::st_crs(source_sample))
  sf::st_write(buffer_source, source_buffer, layer = "research_area", quiet = TRUE, layer_options = "SPATIAL_INDEX=YES")
  bbox <- sf::st_bbox(buffer_source)
  run_command("ogr2ogr", c(
    "-f", "GPKG", work, source, "links",
    "-spat", format(bbox[["xmin"]], digits = 15), format(bbox[["ymin"]], digits = 15),
    format(bbox[["xmax"]], digits = 15), format(bbox[["ymax"]], digits = 15),
    "-nln", "links", "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"
  ))
  candidate_links <- as.numeric(ogr_scalar(work, "SELECT COUNT(*) AS value FROM links"))
  run_command("ogr2ogr", c("-update", "-append", work, source_buffer, "research_area", "-nln", "selection_buffer", "-lco", "SPATIAL_INDEX=NO"))
  ogr_execute(work, "DELETE FROM links WHERE NOT ST_Intersects(geom,(SELECT geom FROM selection_buffer LIMIT 1))")
  selected_links <- as.numeric(ogr_scalar(work, "SELECT COUNT(*) AS value FROM links"))
  outside_links <- as.numeric(ogr_scalar(work, "SELECT COUNT(*) AS value FROM links WHERE NOT ST_Intersects(geom,(SELECT geom FROM selection_buffer LIMIT 1))"))
  if (selected_links <= 0 || outside_links != 0) stop("Road exact spatial selection failed", call. = FALSE)

  link_bbox <- road_layer_bbox(work, "links")
  node_padding <- as.numeric(config$methodology$road$node_candidate_padding_m)
  if (!is.finite(node_padding) || node_padding <= 0) stop("Road node candidate padding must be positive", call. = FALSE)
  run_command("ogr2ogr", c(
    "-update", "-append", work, source, "nodes",
    "-spat", format(link_bbox[["xmin"]] - node_padding, digits = 15), format(link_bbox[["ymin"]] - node_padding, digits = 15),
    format(link_bbox[["xmax"]] + node_padding, digits = 15), format(link_bbox[["ymax"]] + node_padding, digits = 15),
    "-nln", "nodes", "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"
  ))
  ogr_execute(work, paste0(
    "DELETE FROM nodes WHERE NODE_ID NOT IN (SELECT F_NODE FROM links UNION SELECT T_NODE FROM links)"
  ))
  orphan_source <- as.numeric(ogr_scalar(work, paste0(
    "SELECT COUNT(*) AS value FROM links l LEFT JOIN nodes f ON l.F_NODE=f.NODE_ID ",
    "LEFT JOIN nodes t ON l.T_NODE=t.NODE_ID WHERE f.NODE_ID IS NULL OR t.NODE_ID IS NULL"
  )))
  if (orphan_source != 0) stop("Road node closure failed before transformation", call. = FALSE)
  run_command("python", c(sqlite_helper, "road", source, work))
  run_command("ogrinfo", c(work, "-sql", "DELLAYER:selection_buffer"))

  run_command("ogr2ogr", c(
    "-f", "GPKG", stage, work, "links", "-nln", "links",
    "-s_srs", crs_audit$source_wkt, "-t_srs", "EPSG:5186", "-ct", approved_pipeline,
    "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"
  ))
  run_command("ogr2ogr", c(
    "-update", "-append", stage, work, "nodes", "-nln", "nodes",
    "-s_srs", crs_audit$source_wkt, "-t_srs", "EPSG:5186", "-ct", approved_pipeline,
    "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"
  ))
  for (layer in c("multilink", "turninfo")) {
    run_command("ogr2ogr", c("-update", "-append", stage, work, layer, "-nln", layer, "-lco", "ASPATIAL_VARIANT=GPKG_ATTRIBUTES"))
  }
  ogr_execute(stage, "CREATE UNIQUE INDEX idx_links_link_id ON links(LINK_ID)")
  ogr_execute(stage, "CREATE UNIQUE INDEX idx_nodes_node_id ON nodes(NODE_ID)")
  ensure_spatial_index(stage, "links", "geom")
  ensure_spatial_index(stage, "nodes", "geom")
  orphan_output <- as.numeric(ogr_scalar(stage, paste0(
    "SELECT COUNT(*) AS value FROM links l LEFT JOIN nodes f ON l.F_NODE=f.NODE_ID ",
    "LEFT JOIN nodes t ON l.T_NODE=t.NODE_ID WHERE f.NODE_ID IS NULL OR t.NODE_ID IS NULL"
  )))
  endpoint_start <- as.numeric(ogr_scalar(stage, "SELECT MAX(ST_Distance(ST_StartPoint(l.geom),n.geom)) AS value FROM links l JOIN nodes n ON l.F_NODE=n.NODE_ID"))
  endpoint_end <- as.numeric(ogr_scalar(stage, "SELECT MAX(ST_Distance(ST_EndPoint(l.geom),n.geom)) AS value FROM links l JOIN nodes n ON l.T_NODE=n.NODE_ID"))
  endpoint_max <- max(endpoint_start, endpoint_end)
  tolerance <- as.numeric(config$methodology$road$endpoint_tolerance_m)
  dangling_multilink <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM multilink m LEFT JOIN links l ON m.LINK_ID=l.LINK_ID WHERE l.LINK_ID IS NULL"))
  dangling_turn <- as.numeric(ogr_scalar(stage, paste0(
    "SELECT COUNT(*) AS value FROM turninfo t LEFT JOIN nodes n ON t.NODE_ID=n.NODE_ID ",
    "LEFT JOIN links s ON t.ST_LINK=s.LINK_ID LEFT JOIN links e ON t.ED_LINK=e.LINK_ID ",
    "WHERE n.NODE_ID IS NULL OR s.LINK_ID IS NULL OR e.LINK_ID IS NULL"
  )))
  output_bbox <- road_layer_bbox(stage, "links")
  analysis_bbox <- sf::st_bbox(buffer)
  intersects_buffer <- output_bbox[["xmin"]] <= analysis_bbox[["xmax"]] &&
    output_bbox[["xmax"]] >= analysis_bbox[["xmin"]] &&
    output_bbox[["ymin"]] <= analysis_bbox[["ymax"]] &&
    output_bbox[["ymax"]] >= analysis_bbox[["ymin"]]
  if (orphan_output != 0 || endpoint_max > tolerance || dangling_multilink != 0 ||
      dangling_turn != 0 || !intersects_buffer) {
    stop("Road topology or endpoint QC failed", call. = FALSE)
  }
  write_gpkg_metadata(stage, list(
    artifact_fingerprint = fingerprint,
    dataset = "road",
    canonical_path = source,
    canonical_sha256 = canonical_inputs$road$sha256,
    buffer_sha256 = buffer_hash,
    spatial_predicate = "ST_Intersects (boundary-inclusive)",
    geometry_operation = "explicit PROJ coordinate operation; no clipping",
    source_crs_wkt = crs_audit$source_wkt,
    output_crs = "EPSG:5186",
    proj_operation = approved_pipeline,
    proj_selected_datum_operation = crs_audit$operation_definition,
    proj_operation_description = paste0(
      crs_audit$operation_description,
      "; explicit axis-order adaptation for GDAL coordinate-operation semantics"
    ),
    proj_accuracy = "unknown; PROJ labels ITRF2000-to-KGD2002 step ballpark",
    source_target_coordinate_change_m = crs_audit$coordinate_change_m,
    candidate_links = candidate_links,
    selected_links = selected_links,
    endpoint_max_error_m = endpoint_max,
    endpoint_tolerance_m = tolerance,
    node_candidate_bbox_padding_m = node_padding,
    outside_comparison_dataset = "not available at execution; canonical endpoint and administrative alignment used",
    con_relation_created = FALSE,
    created_at = kst_now(),
    contract_version = config$methodology$contract$study_subset_version
  ))
  if (!sqlite_integrity(stage)) stop("Road subset GeoPackage integrity failed", call. = FALSE)
  atomic_publish(stage, final)
}
