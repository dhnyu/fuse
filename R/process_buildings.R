# Thesis: Chapter 3 scene construction. This source subset preserves full objects;
# clipping and observed footprint/gross-floor-area are deferred to scene targets.

subset_seoul_buildings <- function(canonical_inputs, buffer_file, config) {
  source <- canonical_inputs$building$path
  final <- config$paths$study$building
  buffer_hash <- sha256_file(buffer_file)
  fingerprint <- artifact_fingerprint(
    "seoul_building", canonical_inputs$building$sha256, buffer_hash,
    config$methodology$contract$study_subset_version, "INTERSECTS_NO_CLIP"
  )
  if (existing_gpkg_matches(final, fingerprint)) return(final)
  if (file.exists(final)) stop("Conflicting existing Seoul building subset: ", final, call. = FALSE)
  stage <- stage_path(final)
  on.exit(if (file.exists(stage)) unlink(stage), add = TRUE)
  bbox <- bbox_from_gpkg(buffer_file, "research_area")
  run_command("ogr2ogr", c(
    "-f", "GPKG", stage, source, "buildings",
    "-spat", format(bbox[["xmin"]], scientific = FALSE, digits = 15),
    format(bbox[["ymin"]], scientific = FALSE, digits = 15),
    format(bbox[["xmax"]], scientific = FALSE, digits = 15),
    format(bbox[["ymax"]], scientific = FALSE, digits = 15),
    "-spat_srs", "EPSG:5186", "-nln", "buildings",
    "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"
  ))
  candidate_count <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM buildings"))
  run_command("ogr2ogr", c(
    "-update", "-append", stage, buffer_file, "research_area",
    "-nln", "selection_buffer", "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO"
  ))
  ogr_execute(stage, paste0(
    "DELETE FROM buildings WHERE NOT ST_Intersects(geom, ",
    "(SELECT geom FROM selection_buffer LIMIT 1))"
  ))
  selected_count <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM buildings"))
  outside_count <- as.numeric(ogr_scalar(stage, paste0(
    "SELECT COUNT(*) AS value FROM buildings WHERE NOT ST_Intersects(geom, ",
    "(SELECT geom FROM selection_buffer LIMIT 1))"
  )))
  if (selected_count <= 0 || outside_count != 0) stop("Building exact spatial selection failed", call. = FALSE)
  run_command("ogrinfo", c(stage, "-sql", "DELLAYER:selection_buffer"))
  ogr_execute(stage, "CREATE UNIQUE INDEX idx_buildings_feature_id ON buildings(building_feature_id)")
  ensure_spatial_index(stage, "buildings", "geom")
  required <- c("building_feature_id", "A9", "A11", "A14", "source_archive", "source_layer", "source_record_index")
  schema <- jsonlite::fromJSON(paste(run_command("ogrinfo", c("-ro", "-json", "-so", "-al", stage), capture = TRUE), collapse = "\n"), simplifyVector = FALSE)
  fields <- vapply(schema$layers[[1L]]$fields, `[[`, character(1L), "name")
  if (!all(required %in% fields)) stop("Building output lost required fields", call. = FALSE)
  unique_count <- as.numeric(ogr_scalar(stage, "SELECT COUNT(DISTINCT building_feature_id) AS value FROM buildings"))
  invalid_count <- as.numeric(ogr_scalar(stage, "SELECT COUNT(*) AS value FROM buildings WHERE NOT ST_IsValid(geom)"))
  if (unique_count != selected_count || invalid_count != 0) stop("Building key/geometry QC failed", call. = FALSE)
  write_gpkg_metadata(stage, list(
    artifact_fingerprint = fingerprint,
    dataset = "building",
    canonical_path = source,
    canonical_sha256 = canonical_inputs$building$sha256,
    buffer_sha256 = buffer_hash,
    spatial_predicate = "ST_Intersects (boundary-inclusive)",
    geometry_operation = "NONE; full canonical geometry retained",
    candidate_count = candidate_count,
    selected_count = selected_count,
    scene_clipping_deferred = TRUE,
    created_at = kst_now(),
    contract_version = config$methodology$contract$study_subset_version
  ))
  if (!sqlite_integrity(stage)) stop("Building subset GeoPackage integrity failed", call. = FALSE)
  atomic_publish(stage, final)
}
