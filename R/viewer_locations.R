# Dissertation Experimental Setup: 500 m scenes defined by canonical EPSG:5186 centers.
# Supplemental display only: no research targets, scene preprocessing, or model inputs.
location_assignment <- function(points, boundaries, code_field, name_field) {
  hits <- sf::st_covered_by(points, boundaries)
  lapply(hits, function(indices) {
    indices <- indices[order(as.character(boundaries[[code_field]][indices]))]
    codes <- as.character(boundaries[[code_field]][indices])
    names <- as.character(boundaries[[name_field]][indices])
    list(status = if (!length(indices)) "no_polygon_match" else if (length(indices) == 1L) "unique_match" else "boundary_ambiguous",
         code = if (length(indices) == 1L) codes[[1]] else NULL,
         name = if (length(indices) == 1L) names[[1]] else NULL,
         candidate_codes = unname(as.list(codes)), candidate_names = unname(as.list(names)))
  })
}

location_hierarchy <- function(sigungu, dong) {
  if (dong$status != "unique_match" || sigungu$status != "unique_match") return("not_comparable")
  if (substr(dong$code, 1, 5) != sigungu$code) stop("LOCATION_HIERARCHY_MISMATCH", call. = FALSE)
  "consistent"
}

location_transform <- function(rows) {
  if (anyDuplicated(rows$scene_id) || any(!is.finite(rows$center_x)) ||
      any(!is.finite(rows$center_y)) || any(rows$epsg != 5186L)) stop("LOCATION_INVALID_CENTERS")
  sf::st_axis_order(FALSE)
  points <- sf::st_as_sf(rows, coords = c("center_x", "center_y"), crs = 5186, remove = FALSE)
  coordinates <- sf::st_coordinates(sf::st_transform(points, "OGC:CRS84", allow_ballpark = FALSE))
  if (any(!is.finite(coordinates))) stop("LOCATION_NONFINITE_TRANSFORM")
  list(points = sf::st_transform(points, 5179, allow_ballpark = FALSE), coordinates = coordinates)
}

location_read_boundary <- function(path, code, name) {
  boundaries <- sf::st_read(path, quiet = TRUE)
  if (sf::st_crs(boundaries)$epsg != 5179L ||
      !all(c("BASE_DATE", code, name) %in% names(boundaries))) stop("LOCATION_BOUNDARY_SCHEMA")
  boundaries <- boundaries[substr(as.character(boundaries[[code]]), 1, 2) == "11", ]
  if (!nrow(boundaries) || any(as.character(boundaries$BASE_DATE) != "20250630") ||
      anyDuplicated(boundaries[[code]]) || anyNA(boundaries[[name]]) ||
      any(!nzchar(boundaries[[name]])) || any(!sf::st_is_valid(boundaries)) ||
      any(sf::st_is_empty(boundaries))) stop("LOCATION_BOUNDARY_INVALID")
  boundaries
}

build_location_rows <- function(gallery, sigungu_path, dong_path) {
  transformed <- location_transform(gallery)
  sig <- location_read_boundary(sigungu_path, "SIGUNGU_CD", "SIGUNGU_NM")
  dong <- location_read_boundary(dong_path, "ADM_CD", "ADM_NM")
  districts <- location_assignment(transformed$points, sig, "SIGUNGU_CD", "SIGUNGU_NM")
  dongs <- location_assignment(transformed$points, dong, "ADM_CD", "ADM_NM")
  rows <- lapply(seq_len(nrow(gallery)), function(i) {
    s <- districts[[i]]; d <- dongs[[i]]
    list(scene_id = gallery$scene_id[[i]], longitude = sprintf("%.17g", transformed$coordinates[i, 1]),
         latitude = sprintf("%.17g", transformed$coordinates[i, 2]), sigungu_code = s$code, sigungu_name = s$name,
         eupmyeondong_code = d$code, eupmyeondong_name = d$name,
         sigungu_join_status = s$status, dong_join_status = d$status,
         sigungu_candidate_codes = s$candidate_codes, sigungu_candidate_names = s$candidate_names,
         dong_candidate_codes = d$candidate_codes, dong_candidate_names = d$candidate_names,
         hierarchy_status = location_hierarchy(s, d))
  })
  list(rows = rows, transform = list(library = "R sf", sf_version = as.character(utils::packageVersion("sf")),
       jsonlite_version = as.character(utils::packageVersion("jsonlite")), external_versions = as.list(sf::sf_extSoftVersion()),
       source_crs = "EPSG:5186", geographic_target = "OGC:CRS84", geographic_datum = "WGS84",
       boundary_crs = "EPSG:5179", axis_order = "x=easting,y=northing; output longitude,latitude",
       allow_ballpark = FALSE, network = FALSE, join_predicate = "st_covered_by", nearest_fallback = FALSE))
}
