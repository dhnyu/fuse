# Thesis: Chapter 4, Experimental Setup; 400 m source buffer in EPSG:5186.

boundary_component_paths <- function(shp) {
  stem <- tools::file_path_sans_ext(shp)
  paths <- paste0(stem, c(".shp", ".shx", ".dbf", ".prj", ".cpg"))
  paths[file.exists(paths)]
}

inspect_seoul_boundary_source <- function(boundary_files, config, canonical_manifest) {
  shp <- config$paths$administrative$sido
  source <- sf::st_read(shp, quiet = TRUE)
  code <- config$methodology$study_area$source_code
  name <- config$methodology$study_area$source_name
  selected <- source[source$SIDO_CD == code, ]
  if (nrow(selected) != 1L) stop("SIDO_CD must select exactly one Seoul feature", call. = FALSE)
  if (!identical(enc2utf8(selected$SIDO_NM[[1L]]), enc2utf8(name))) {
    stop("Seoul name does not match SIDO_CD=", code, call. = FALSE)
  }
  reason <- sf::st_is_valid(selected, reason = TRUE)
  list(
    source_path = normalizePath(shp),
    component_paths = normalizePath(boundary_files),
    component_sha256 = setNames(vapply(boundary_files, sha256_file, character(1L)), basename(boundary_files)),
    source_checksum = sha256_file_set(boundary_files),
    source_feature_identifier = sprintf("SIDO_CD=%s;SIDO_NM=%s", code, name),
    source_crs = sf::st_crs(selected)$input,
    source_epsg = sf::st_crs(selected)$epsg,
    source_geometry_type = as.character(sf::st_geometry_type(selected)[[1L]]),
    source_valid = isTRUE(sf::st_is_valid(selected)[[1L]]),
    source_valid_reason = reason[[1L]],
    repair_applied = FALSE,
    canonical_snapshot = canonical_manifest$snapshot_id
  )
}

read_selected_seoul <- function(source_info, config) {
  source <- sf::st_read(source_info$source_path, quiet = TRUE)
  selected <- source[
    source$SIDO_CD == config$methodology$study_area$source_code &
      enc2utf8(source$SIDO_NM) == enc2utf8(config$methodology$study_area$source_name),
  ]
  if (nrow(selected) != 1L) stop("Deterministic Seoul selection failed", call. = FALSE)
  if (!isTRUE(sf::st_is_valid(selected)[[1L]])) {
    stop("Seoul source geometry is invalid; repair is not pre-approved", call. = FALSE)
  }
  selected
}

study_area_metadata <- function(source_info, config, canonical_manifest, buffer_distance_m, fingerprint) {
  list(
    artifact_fingerprint = fingerprint,
    source_boundary_path = source_info$source_path,
    source_boundary_checksum = source_info$source_checksum,
    source_feature_identifier = source_info$source_feature_identifier,
    source_crs = source_info$source_crs,
    output_crs = config$methodology$study_area$output_crs,
    buffer_distance_m = buffer_distance_m,
    source_geometry_valid = source_info$source_valid,
    geometry_repair_applied = source_info$repair_applied,
    created_at = kst_now(),
    thesis_commit = trimws(run_command("git", c("-C", config$paths$repository$thesis, "rev-parse", "HEAD"), capture = TRUE)[[1L]]),
    canonical_schema_version = canonical_manifest$schema_version,
    canonical_snapshot = canonical_manifest$snapshot_id,
    study_subset_contract = config$methodology$contract$study_subset_version
  )
}

create_seoul_boundary <- function(source_info, config, canonical_manifest) {
  final <- config$paths$study$boundary
  fingerprint <- artifact_fingerprint(
    "seoul_boundary", source_info$source_checksum,
    config$methodology$study_area$output_crs,
    config$methodology$contract$study_subset_version,
    canonical_manifest$snapshot_id
  )
  if (existing_gpkg_matches(final, fingerprint)) return(final)
  if (file.exists(final)) stop("Conflicting existing Seoul boundary: ", final, call. = FALSE)
  stage <- stage_path(final)
  on.exit(if (file.exists(stage)) unlink(stage), add = TRUE)
  selected <- read_selected_seoul(source_info, config)
  transformed <- sf::st_transform(selected, config$methodology$study_area$output_crs)
  geometry <- sf::st_union(sf::st_geometry(transformed))
  boundary <- sf::st_sf(
    area_id = "SEOUL_ADMIN_2025Q2",
    SIDO_CD = config$methodology$study_area$source_code,
    SIDO_NM = config$methodology$study_area$source_name,
    geometry = geometry
  )
  if (!isTRUE(sf::st_is_valid(boundary)[[1L]])) stop("Dissolved Seoul boundary is invalid", call. = FALSE)
  sf::st_write(boundary, stage, layer = "research_area", quiet = TRUE, layer_options = "SPATIAL_INDEX=YES")
  write_gpkg_metadata(stage, study_area_metadata(source_info, config, canonical_manifest, 0, fingerprint))
  if (!sqlite_integrity(stage)) stop("Boundary GeoPackage integrity failed", call. = FALSE)
  ensure_spatial_index(stage, "research_area", "geom")
  atomic_publish(stage, final)
}

create_seoul_buffer <- function(boundary_file, source_info, config, canonical_manifest) {
  final <- config$paths$study$buffer400
  distance <- as.numeric(config$methodology$study_area$source_buffer_m)
  fingerprint <- artifact_fingerprint(
    "seoul_buffer", sha256_file(boundary_file), distance,
    config$methodology$study_area$output_crs,
    config$methodology$contract$study_subset_version
  )
  if (existing_gpkg_matches(final, fingerprint)) return(final)
  if (file.exists(final)) stop("Conflicting existing Seoul buffer: ", final, call. = FALSE)
  stage <- stage_path(final)
  on.exit(if (file.exists(stage)) unlink(stage), add = TRUE)
  boundary <- sf::st_read(boundary_file, layer = "research_area", quiet = TRUE)
  if (!identical(sf::st_crs(boundary)$epsg, 5186L)) stop("Boundary CRS is not EPSG:5186", call. = FALSE)
  geometry <- sf::st_buffer(sf::st_union(sf::st_geometry(boundary)), dist = distance)
  buffer <- sf::st_sf(
    area_id = "SEOUL_SOURCE_BUFFER_400M",
    buffer_distance_m = distance,
    geometry = geometry
  )
  if (!isTRUE(sf::st_is_valid(buffer)[[1L]])) stop("Seoul buffer geometry is invalid", call. = FALSE)
  if (!isTRUE(sf::st_covered_by(boundary, buffer, sparse = FALSE)[[1L]])) stop("Buffer does not cover boundary", call. = FALSE)
  sf::st_write(buffer, stage, layer = "research_area", quiet = TRUE, layer_options = "SPATIAL_INDEX=YES")
  write_gpkg_metadata(stage, study_area_metadata(source_info, config, canonical_manifest, distance, fingerprint))
  if (!sqlite_integrity(stage)) stop("Buffer GeoPackage integrity failed", call. = FALSE)
  ensure_spatial_index(stage, "research_area", "geom")
  atomic_publish(stage, final)
}
