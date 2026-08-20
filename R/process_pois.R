# Thesis: Section 3.2 hierarchical POI semantics. This target retains all raw
# hierarchy states and defers category encoding and spatial relations.

poi_crs_audit <- function(source) {
  sample <- sf::st_read(source, query = "SELECT geom FROM points LIMIT 1", quiet = TRUE)
  pipelines <- sf::sf_proj_pipelines(sf::st_crs(sample), sf::st_crs(5186), AOI = c(126.7, 37.4, 127.3, 37.8))
  usable <- pipelines[pipelines$instantiable, , drop = FALSE]
  if (!nrow(usable)) stop("No instantiable POI CRS operation", call. = FALSE)
  best <- usable[1L, , drop = FALSE]
  if (!isTRUE(best$accuracy[[1L]] == 0)) stop("POI transform is not the expected 0 m-accuracy projection change", call. = FALSE)
  list(
    source_crs = sf::st_crs(sample),
    definition = best$definition[[1L]],
    description = best$description[[1L]],
    accuracy_m = best$accuracy[[1L]]
  )
}

subset_seoul_poi <- function(canonical_inputs, buffer_file, config, sqlite_helper) {
  source <- canonical_inputs$poi$path
  final <- config$paths$study$poi
  buffer_hash <- sha256_file(buffer_file)
  crs_audit <- poi_crs_audit(source)
  fingerprint <- artifact_fingerprint(
    "seoul_poi", canonical_inputs$poi$sha256, buffer_hash, crs_audit$definition,
    config$methodology$contract$study_subset_version, "INTERSECTS_NO_DEDUP"
  )
  if (existing_gpkg_matches(final, fingerprint)) return(final)
  if (file.exists(final)) stop("Conflicting existing Seoul POI subset: ", final, call. = FALSE)
  work <- file.path(config$paths$study$staging, sprintf("poi_source_%s_%s.gpkg", Sys.getpid(), format(Sys.time(), "%Y%m%d%H%M%S")))
  source_buffer <- file.path(config$paths$study$staging, sprintf("poi_buffer_%s.gpkg", Sys.getpid()))
  stage <- stage_path(final)
  on.exit(unlink(c(work, source_buffer, stage), force = TRUE), add = TRUE)

  buffer <- sf::st_read(buffer_file, layer = "research_area", quiet = TRUE)
  buffer_source <- sf::st_transform(buffer, crs_audit$source_crs)
  sf::st_write(buffer_source, source_buffer, layer = "research_area", quiet = TRUE, layer_options = "SPATIAL_INDEX=YES")
  bbox <- sf::st_bbox(buffer_source)
  run_command("ogr2ogr", c(
    "-f", "GPKG", work, source, "points",
    "-spat", format(bbox[["xmin"]], digits = 15), format(bbox[["ymin"]], digits = 15),
    format(bbox[["xmax"]], digits = 15), format(bbox[["ymax"]], digits = 15),
    "-spat_srs", "EPSG:5179", "-nln", "points",
    "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"
  ))
  candidate_count <- as.numeric(ogr_scalar(work, "SELECT COUNT(*) AS value FROM points"))
  run_command("ogr2ogr", c("-update", "-append", work, source_buffer, "research_area", "-nln", "selection_buffer", "-lco", "SPATIAL_INDEX=NO"))
  ogr_execute(work, "DELETE FROM points WHERE NOT ST_Intersects(geom,(SELECT geom FROM selection_buffer LIMIT 1))")
  selected_count <- as.numeric(ogr_scalar(work, "SELECT COUNT(*) AS value FROM points"))
  outside_count <- as.numeric(ogr_scalar(work, "SELECT COUNT(*) AS value FROM points WHERE NOT ST_Intersects(geom,(SELECT geom FROM selection_buffer LIMIT 1))"))
  if (selected_count <= 0 || outside_count != 0) stop("POI boundary-inclusive selection failed", call. = FALSE)
  run_command("ogrinfo", c(work, "-sql", "DELLAYER:selection_buffer"))

  run_command("ogr2ogr", c(
    "-f", "GPKG", stage, work, "points", "-nln", "points",
    "-t_srs", "EPSG:5186", "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"
  ))
  run_command("python", c(sqlite_helper, "poi", source, stage))
  ensure_spatial_index(stage, "points", "geom")
  unique_count <- as.numeric(ogr_scalar(stage, "SELECT COUNT(DISTINCT NF_ID) AS value FROM points"))
  null_geometry <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM points WHERE geom IS NULL OR ST_IsEmpty(geom)"))
  addresses <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM addresses"))
  foreign_names <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM foreign_names"))
  alias_dangling <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM aliases a LEFT JOIN points p ON a.POIID=p.NF_ID WHERE p.NF_ID IS NULL"))
  category_source <- as.numeric(ogr_scalar(source, "SELECT COUNT(*) AS value FROM category_lookup"))
  category_output <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM category_lookup"))
  required <- c("NF_ID", paste0("CLASS_L", rep(1:6, each = 2L), rep(c("_CODE", "_STATE"), 6L)))
  info <- jsonlite::fromJSON(paste(run_command("ogrinfo", c("-ro", "-json", "-so", "-al", stage), capture = TRUE), collapse = "\n"), simplifyVector = FALSE)
  point_layer <- info$layers[[which(vapply(info$layers, function(x) identical(x$name, "points"), logical(1L)))]]
  fields <- vapply(point_layer$fields, `[[`, character(1L), "name")
  if (!all(required %in% fields)) stop("POI hierarchy fields were not preserved", call. = FALSE)
  if (unique_count != selected_count || null_geometry != 0 || addresses != selected_count ||
      foreign_names != selected_count || alias_dangling != 0 || category_output != category_source) {
    stop("POI identifier/auxiliary-table QC failed", call. = FALSE)
  }
  write_gpkg_metadata(stage, list(
    artifact_fingerprint = fingerprint,
    dataset = "poi",
    canonical_path = source,
    canonical_sha256 = canonical_inputs$poi$sha256,
    buffer_sha256 = buffer_hash,
    spatial_predicate = "ST_Intersects (boundary-inclusive)",
    category_filtering = FALSE,
    fuzzy_deduplication = FALSE,
    hierarchy_raw_state_preserved = TRUE,
    source_crs = "EPSG:5179",
    output_crs = "EPSG:5186",
    proj_operation = crs_audit$definition,
    proj_operation_description = crs_audit$description,
    proj_accuracy_m = crs_audit$accuracy_m,
    candidate_count = candidate_count,
    selected_count = selected_count,
    created_at = kst_now(),
    contract_version = config$methodology$contract$study_subset_version
  ))
  if (!sqlite_integrity(stage)) stop("POI subset GeoPackage integrity failed", call. = FALSE)
  atomic_publish(stage, final)
}
