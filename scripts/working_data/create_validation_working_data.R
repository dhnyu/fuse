#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
})

sf::sf_use_s2(FALSE)
Sys.setenv(TZ = "Asia/Seoul")

TARGET_EPSG <- 5186L
DEFAULT_WORKERS <- 40L

`%||%` <- function(x, y) if (is.null(x)) y else x
SCRIPT_PATH <- normalizePath("scripts/working_data/create_validation_working_data.R", mustWork = FALSE)

parse_args <- function(args) {
  out <- list(regions = "validation", workers = DEFAULT_WORKERS, symlink_only = FALSE)
  for (arg in args) {
    if (startsWith(arg, "--regions=")) out$regions <- sub("^--regions=", "", arg)
    if (startsWith(arg, "--workers=")) out$workers <- as.integer(sub("^--workers=", "", arg))
    if (arg == "--symlink-only") out$symlink_only <- TRUE
  }
  if (is.na(out$workers)) out$workers <- DEFAULT_WORKERS
  out$workers <- max(1L, min(DEFAULT_WORKERS, out$workers))
  out
}

args <- parse_args(commandArgs(trailingOnly = TRUE))
WORKERS_USED <- 1L
WORKER_RATIONALE <- paste(
  "The server default for this workflow is 40 CPU workers.",
  "This run used one worker because each region performs bounded GDAL reads",
  "from the same large single-file sources and writes independent GeoPackages.",
  "Sequential execution avoids disk contention, duplicated source scans, and",
  "GeoPackage writer pressure while keeping the outputs deterministic."
)

root_fusedatalarge <- path.expand("~/fusedatalarge")
root_fusedata <- path.expand("~/fusedata")
root_fuse <- path.expand("~/fuse")
working_root <- file.path(root_fusedatalarge, "working_data")
source_root <- file.path(working_root, "_sources")
report_dir <- file.path(root_fuse, "reports")
timestamp <- format(Sys.time(), "%Y%m%d_%H%M")
report_path <- file.path(report_dir, sprintf("%s_validation_working_data_subset_report.md", timestamp))
readme_report_path <- file.path(report_dir, sprintf("%s_working_data_reproducibility_readme_report.md", timestamp))

dir.create(working_root, recursive = TRUE, showWarnings = FALSE)
dir.create(source_root, recursive = TRUE, showWarnings = FALSE)
dir.create(report_dir, recursive = TRUE, showWarnings = FALSE)

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), sprintf(...)))
  flush.console()
}

must_exist <- function(path) {
  if (!file.exists(path)) stop(sprintf("Missing required path: %s", path), call. = FALSE)
  path
}

source_paths <- list(
  boundary_sido = file.path(root_fusedatalarge, "geodata", "koreanadm", "bnd_sido_00_2024_2Q.shp"),
  boundary_sigungu = file.path(root_fusedatalarge, "geodata", "koreanadm", "bnd_sigungu_00_2024_2Q.shp"),
  building_gpkg = file.path(root_fusedatalarge, "processed", "korea_buildings_vworld.gpkg"),
  building_attrs = file.path(root_fusedatalarge, "processed", "korea_buildings_vworld_attributes.parquet"),
  osm_point_gpkg = file.path(root_fusedatalarge, "osm", "canonical", "gpkg", "korea_pois_point.gpkg"),
  osm_point_attrs = file.path(root_fusedatalarge, "osm", "canonical", "parquet", "korea_pois_point.parquet"),
  ngii_point_gpkg = file.path(root_fusedatalarge, "processed", "korea_poi_ngii_point.gpkg"),
  ngii_point_attrs = file.path(root_fusedatalarge, "processed", "korea_poi_ngii_attributes.parquet"),
  osm_polygon_gpkg = file.path(root_fusedatalarge, "osm", "canonical", "gpkg", "korea_osm_polygon_poi_cleaned.gpkg"),
  osm_polygon_attrs = file.path(root_fusedatalarge, "osm", "canonical", "parquet", "korea_osm_polygon_poi_cleaned_attributes.parquet"),
  togieeum_polygon_gpkg = file.path(root_fusedatalarge, "processed", "korea_polygon_poi_togieeum_facility.gpkg"),
  togieeum_polygon_attrs = file.path(root_fusedatalarge, "processed", "korea_polygon_poi_togieeum_facility_attributes.parquet"),
  seoul_roads_gpkg = file.path(root_fusedatalarge, "osm", "canonical", "seoul_roads_canonical.gpkg"),
  raw_osm_pbf = file.path(root_fusedatalarge, "osm", "raw", "geofabrik_south-korea-latest.osm.pbf"),
  raw_osm_gpkg = file.path(root_fusedatalarge, "osm", "raw", "geofabrik_south-korea-latest.gpkg"),
  streetview_metadata = file.path(root_fusedata, "streetview", "final", "gsv_seoul_metadata_final_40000.parquet")
)
invisible(lapply(source_paths, must_exist))

regions <- data.table::data.table(
  region_key = c("gwanak", "seoul", "daegu", "jeju", "gangneung", "ganghwa", "sejong",
                 "danyang", "seongnam", "incheon", "daejeon", "changwon", "suwon", "korea"),
  region_name_ko = c("관악구", "서울특별시", "대구광역시", "제주특별자치도", "강릉시", "강화군",
                     "세종특별자치시", "단양군", "성남시", "인천광역시", "대전광역시",
                     "창원시", "수원시", "전국"),
  region_level = c("sigungu", "sido", "sido", "sido", "sigungu", "sigungu", "sido",
                   "sigungu", "sigungu_merged", "sigungu_merged", "sido", "sigungu_merged",
                   "sigungu_merged", "nationwide_alias"),
  source_field = c("SIGUNGU_NM", "SIDO_NM", "SIDO_NM", "SIDO_NM", "SIGUNGU_NM", "SIGUNGU_NM",
                   "SIDO_NM", "SIGUNGU_NM", "SIGUNGU_NM", "SIGUNGU_CD", "SIDO_NM",
                   "SIGUNGU_NM", "SIGUNGU_NM", NA_character_),
  match_type = c("exact", "exact", "exact", "exact", "exact", "exact", "exact",
                 "exact", "prefix", "prefix", "exact", "prefix", "prefix", "alias"),
  match_value = c("관악구", "서울특별시", "대구광역시", "제주특별자치도", "강릉시", "강화군",
                  "세종특별자치시", "단양군", "성남시", "23", "대전광역시",
                  "창원시", "수원시", NA_character_),
  bbox_only = c(FALSE, FALSE, FALSE, TRUE, FALSE, FALSE, FALSE, FALSE,
                FALSE, FALSE, FALSE, FALSE, FALSE, FALSE)
)

validation_region_keys <- c("seoul", "daegu", "jeju", "gangneung", "ganghwa", "sejong",
                            "danyang", "seongnam", "incheon", "daejeon", "changwon",
                            "suwon", "korea")
all_region_keys <- regions$region_key

selected_regions <- function(spec) {
  spec <- trimws(spec)
  if (identical(spec, "validation")) return(validation_region_keys)
  if (identical(spec, "all")) return(all_region_keys)
  keys <- trimws(unlist(strsplit(spec, ",")))
  bad <- setdiff(keys, all_region_keys)
  if (length(bad)) stop(sprintf("Unknown region key(s): %s", paste(bad, collapse = ", ")), call. = FALSE)
  keys
}

requested_keys <- selected_regions(args$regions)
if (args$symlink_only) requested_keys <- intersect(requested_keys, "korea")

layers <- list(
  building = "buildings",
  osm_point = "korea_pois_point",
  ngii_point = "points",
  osm_polygon = "polygon_pois",
  togieeum_polygon = "polygon_pois_facility",
  roads = "korea_osm_roads"
)

get_layer_feature_count <- function(path, layer) {
  stl <- sf::st_layers(path, do_count = TRUE)
  idx <- match(layer, stl$name)
  if (is.na(idx)) stop(sprintf("Layer %s not found in %s", layer, path), call. = FALSE)
  as.numeric(stl$features[idx])
}

sanitize_for_parquet <- function(df) {
  for (nm in names(df)) {
    if (inherits(df[[nm]], "POSIXt")) df[[nm]] <- as.character(df[[nm]])
    if (inherits(df[[nm]], "units")) df[[nm]] <- as.numeric(df[[nm]])
  }
  df
}

write_spatial_pair <- function(x, gpkg_path, parquet_path, layer_name, source_path, method,
                               region_key, region_name_ko, region_level) {
  gpkg_link <- Sys.readlink(gpkg_path)
  pq_link <- Sys.readlink(parquet_path)
  if (file.exists(gpkg_path) || (!is.na(gpkg_link) && nzchar(gpkg_link))) unlink(gpkg_path)
  if (file.exists(parquet_path) || (!is.na(pq_link) && nzchar(pq_link))) unlink(parquet_path)
  x$region_name <- rep(region_key, nrow(x))
  x$region_name_ko <- rep(region_name_ko, nrow(x))
  x$region_level <- rep(region_level, nrow(x))
  x$source_path <- rep(source_path, nrow(x))
  x$subset_method <- rep(method, nrow(x))
  x$subset_created_at <- rep(format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), nrow(x))
  sf::st_write(x, gpkg_path, layer = layer_name, quiet = TRUE)
  attrs <- sf::st_drop_geometry(x)
  attrs$geometry_wkt <- sf::st_as_text(sf::st_geometry(x))
  attrs$geometry_format <- rep(sprintf("WKT_EPSG_%d", TARGET_EPSG), nrow(attrs))
  arrow::write_parquet(sanitize_for_parquet(attrs), parquet_path)
}

read_with_bbox <- function(path, layer, boundary) {
  bbox <- sf::st_as_sfc(sf::st_bbox(boundary))
  sf::st_crs(bbox) <- sf::st_crs(boundary)
  x <- sf::st_read(path, layer = layer, wkt_filter = sf::st_as_text(bbox), quiet = TRUE)
  if (sf::st_crs(x)$epsg != TARGET_EPSG) x <- sf::st_transform(x, TARGET_EPSG)
  x
}

filter_or_clip <- function(x, boundary, kind, boundary_filter = boundary) {
  if (sf::st_crs(x) != sf::st_crs(boundary)) boundary <- sf::st_transform(boundary, sf::st_crs(x))
  if (sf::st_crs(x) != sf::st_crs(boundary_filter)) boundary_filter <- sf::st_transform(boundary_filter, sf::st_crs(x))
  x <- x[lengths(sf::st_intersects(x, boundary_filter)) > 0, , drop = FALSE]
  if (!nrow(x) || kind == "point") return(x)
  covered <- lengths(sf::st_covered_by(x, boundary_filter)) > 0
  x_keep <- x[covered, , drop = FALSE]
  x_clip <- x[!covered, , drop = FALSE]
  if (!nrow(x_clip)) {
    if (kind == "polygon" && nrow(x_keep)) {
      x_keep <- suppressWarnings(sf::st_cast(x_keep, "MULTIPOLYGON", warn = FALSE))
    }
    if (kind == "line" && nrow(x_keep)) {
      x_keep <- suppressWarnings(sf::st_cast(x_keep, "MULTILINESTRING", warn = FALSE))
    }
    return(x_keep)
  }
  if (kind == "polygon") x_clip <- sf::st_make_valid(x_clip)
  y <- suppressWarnings(sf::st_intersection(x_clip, sf::st_geometry(boundary)))
  if (kind == "polygon") {
    y <- suppressWarnings(sf::st_collection_extract(y, "POLYGON"))
    if (nrow(y)) y <- suppressWarnings(sf::st_cast(y, "MULTIPOLYGON", warn = FALSE))
  }
  if (kind == "line") {
    y <- suppressWarnings(sf::st_collection_extract(y, "LINESTRING"))
    if (nrow(y)) y <- suppressWarnings(sf::st_cast(y, "MULTILINESTRING", warn = FALSE))
  }
  y <- y[!sf::st_is_empty(y), , drop = FALSE]
  if (nrow(x_keep)) {
    if (kind == "polygon") x_keep <- suppressWarnings(sf::st_cast(x_keep, "MULTIPOLYGON", warn = FALSE))
    if (kind == "line") x_keep <- suppressWarnings(sf::st_cast(x_keep, "MULTILINESTRING", warn = FALSE))
    y <- rbind(x_keep, y)
  }
  y
}

boundary_log <- data.table::data.table()
read_boundaries <- function() {
  list(
    sido = sf::st_read(source_paths$boundary_sido, quiet = TRUE),
    sigungu = sf::st_read(source_paths$boundary_sigungu, quiet = TRUE)
  )
}

select_boundary <- function(region, boundaries) {
  if (region$region_level == "sido") src <- boundaries$sido else src <- boundaries$sigungu
  field <- region$source_field
  val <- region$match_value
  if (region$match_type == "exact") hit <- as.character(src[[field]]) == val
  else if (region$match_type == "prefix") hit <- startsWith(as.character(src[[field]]), val)
  else stop("Korea alias has no boundary", call. = FALSE)
  sel <- src[hit, , drop = FALSE]
  if (!nrow(sel)) stop(sprintf("No boundary matched %s", region$region_key), call. = FALSE)
  code_cols <- grep("_CD$", names(sel), value = TRUE)
  source_codes <- paste(unique(unlist(sf::st_drop_geometry(sel)[code_cols])), collapse = ", ")
  name_col <- intersect(c("SIDO_NM", "SIGUNGU_NM"), names(sel))[1]
  source_names <- if (!is.na(name_col)) paste(unique(as.character(sel[[name_col]])), collapse = ", ") else paste(unique(as.character(sel[[field]])), collapse = ", ")
  source_path <- if (region$region_level == "sido") source_paths$boundary_sido else source_paths$boundary_sigungu
  source_crs <- sf::st_crs(sel)$epsg
  sel <- sf::st_transform(sf::st_make_valid(sel), TARGET_EPSG)
  parts <- sf::st_sf(region_name = region$region_key, region_name_ko = region$region_name_ko,
                     region_level = region$region_level, geometry = sf::st_geometry(sel),
                     crs = TARGET_EPSG)
  geom <- sf::st_union(sf::st_geometry(sel))
  out <- sf::st_sf(region_name = region$region_key, region_name_ko = region$region_name_ko,
                   region_level = region$region_level, geometry = geom, crs = TARGET_EPSG)
  list(boundary = out, source_path = source_path, source_crs = source_crs,
       boundary_parts = parts, source_names = source_names, source_codes = source_codes, feature_count = nrow(sel))
}

create_nationwide_road_source <- function() {
  gpkg <- file.path(source_root, "korea_osm_roads_geofabrik_highway.gpkg")
  parquet <- file.path(source_root, "korea_osm_roads_geofabrik_highway.parquet")
  status <- list(
    source_status = "derived_from_raw_pbf_under_working_data",
    raw_input_path = source_paths$raw_osm_pbf,
    gpkg = gpkg,
    parquet = parquet,
    selected_classes = "all non-empty OSM highway tag values",
    crs = sprintf("EPSG:%d", TARGET_EPSG),
    feature_count = NA_real_,
    validation = ""
  )
  if (!file.exists(gpkg)) {
    log_msg("Creating nationwide OSM road working source from %s", source_paths$raw_osm_pbf)
    roads <- sf::st_read(
      source_paths$raw_osm_pbf,
      layer = "lines",
      query = "SELECT osm_id, name, highway, z_order, other_tags FROM lines WHERE highway IS NOT NULL",
      quiet = TRUE
    )
    roads <- roads[!is.na(roads$highway) & nzchar(roads$highway), , drop = FALSE]
    roads <- sf::st_transform(roads, TARGET_EPSG)
    roads <- roads[!sf::st_is_empty(roads), , drop = FALSE]
    roads$road_id <- sprintf("osm_road_%09d", seq_len(nrow(roads)))
    roads$source_path <- source_paths$raw_osm_pbf
    roads$source_layer <- "lines"
    roads$source_filter <- "highway IS NOT NULL"
    roads$geometry_format <- sprintf("native_GPKG_EPSG_%d", TARGET_EPSG)
    roads <- roads[, c("road_id", "osm_id", "name", "highway", "z_order", "other_tags",
                       "source_path", "source_layer", "source_filter", "geometry_format")]
    if (file.exists(gpkg)) unlink(gpkg)
    sf::st_write(roads, gpkg, layer = layers$roads, quiet = TRUE)
  }
  if (!file.exists(parquet)) {
    log_msg("Creating nationwide OSM road attribute parquet from %s", gpkg)
    attrs <- sf::st_read(
      gpkg,
      query = paste(
        "SELECT road_id, osm_id, name, highway, z_order, other_tags,",
        "source_path, source_layer, source_filter FROM korea_osm_roads"
      ),
      quiet = TRUE
    )
    attrs$geometry_format <- sprintf("attribute_only_geometry_in_%s", basename(gpkg))
    arrow::write_parquet(sanitize_for_parquet(attrs), parquet)
  }
  status$feature_count <- get_layer_feature_count(gpkg, layers$roads)
  pq_n <- nrow(arrow::read_parquet(parquet, as_data_frame = TRUE))
  status$validation <- sprintf("GPKG rows %s; attribute parquet rows %s; row counts match: %s",
                               status$feature_count, pq_n, identical(as.numeric(status$feature_count), as.numeric(pq_n)))
  status
}

road_status <- create_nationwide_road_source()
source_paths$roads_gpkg <- road_status$gpkg
source_paths$roads_attrs <- road_status$parquet

dataset_specs <- data.table::data.table(
  dataset = c("VWorld buildings", "OSM point POIs", "NGII point POIs",
              "OSM polygon POIs", "Togieeum facility polygon POIs", "OSM roads"),
  kind = c("polygon", "point", "point", "polygon", "polygon", "line"),
  layer = c(layers$building, layers$osm_point, layers$ngii_point,
            layers$osm_polygon, layers$togieeum_polygon, layers$roads),
  source_path = c(source_paths$building_gpkg, source_paths$osm_point_gpkg,
                  source_paths$ngii_point_gpkg, source_paths$osm_polygon_gpkg,
                  source_paths$togieeum_polygon_gpkg, source_paths$roads_gpkg),
  output_gpkg = c("1_Building_vworld.gpkg", "2_pointPOI_osm.gpkg", "2_pointPOI_ngii.gpkg",
                  "3_polygonPOI_osm.gpkg", "3_polygonPOI_togi.gpkg", "4_road_osm.gpkg"),
  output_parquet = c("1_Building_vworld.parquet", "2_pointPOI_osm.parquet",
                     "2_pointPOI_ngii.parquet", "3_polygonPOI_osm.parquet",
                     "3_polygonPOI_togi.parquet", "4_road_osm.parquet"),
  id_col = c("building_id", "poi_id", "poi_id", "polygon_poi_id", "polygon_poi_id", "road_id"),
  method = c("intersected_with_region_and_clipped_to_boundary",
             "within_or_touching_region_boundary",
             "within_or_touching_region_boundary",
             "intersected_with_region_and_clipped_to_boundary",
             "intersected_with_region_and_clipped_to_boundary",
             "intersected_with_region_and_clipped_to_boundary")
)

result_log <- data.table::data.table()
validation_log <- data.table::data.table()
streetview_log <- data.table::data.table()
symlink_log <- data.table::data.table()

process_region <- function(key, boundaries) {
  region <- regions[get("region_key") == key]
  out_dir <- file.path(working_root, key)
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  b <- select_boundary(region, boundaries)
  boundary_log <<- rbind(boundary_log, data.table::data.table(
    region_key = key,
    region_name_ko = region$region_name_ko,
    region_level = region$region_level,
    boundary_source_path = b$source_path,
    boundary_source_crs = b$source_crs,
    selected_boundary_features = b$source_names,
    selected_boundary_codes = b$source_codes,
    selected_feature_count = b$feature_count,
    output_crs = TARGET_EPSG
  ), fill = TRUE)
  for (i in seq_len(nrow(dataset_specs))) {
    spec <- dataset_specs[i]
    log_msg("Processing %s / %s", key, spec$dataset)
    input_rows <- get_layer_feature_count(spec$source_path, spec$layer)
    x <- read_with_bbox(spec$source_path, spec$layer, b$boundary)
    method <- spec$method
    if (isTRUE(region$bbox_only)) {
      method <- paste0(spec$method, "_bbox_only_island_region")
    } else {
      x <- filter_or_clip(x, b$boundary, spec$kind, b$boundary_parts)
    }
    if (spec$kind == "polygon" && nrow(x)) x$subset_area_m2 <- as.numeric(sf::st_area(x))
    if (spec$kind == "line" && nrow(x)) x$subset_length_m <- as.numeric(sf::st_length(x))
    gpkg_out <- file.path(out_dir, spec$output_gpkg)
    pq_out <- file.path(out_dir, spec$output_parquet)
    write_spatial_pair(x, gpkg_out, pq_out, tools::file_path_sans_ext(spec$output_gpkg),
                       spec$source_path, method, key, region$region_name_ko, region$region_level)
    gt <- paste(sort(unique(as.character(sf::st_geometry_type(x, by_geometry = TRUE)))), collapse = ", ")
    result_log <<- rbind(result_log, data.table::data.table(
      region_key = key, dataset = spec$dataset, source_path = spec$source_path,
      output_gpkg = gpkg_out, output_parquet = pq_out, input_row_count = input_rows,
      subset_row_count = nrow(x), crs = TARGET_EPSG, geometry_type = gt, method = method,
      id_col = spec$id_col
    ), fill = TRUE)
    pq <- arrow::read_parquet(pq_out, as_data_frame = TRUE)
    validation_log <<- rbind(validation_log, data.table::data.table(
      region_key = key, dataset = spec$dataset,
      gpkg_rows = get_layer_feature_count(gpkg_out, tools::file_path_sans_ext(spec$output_gpkg)),
      parquet_rows = nrow(pq),
      row_counts_match = get_layer_feature_count(gpkg_out, tools::file_path_sans_ext(spec$output_gpkg)) == nrow(pq),
      id_unique = if (spec$id_col %in% names(pq)) !anyDuplicated(pq[[spec$id_col]][!is.na(pq[[spec$id_col]])]) else NA
    ), fill = TRUE)
  }
  log_msg("Processing %s / Street View metadata", key)
  sv_out <- file.path(out_dir, "5_streetview.parquet")
  sv_link <- Sys.readlink(sv_out)
  if (file.exists(sv_out) || (!is.na(sv_link) && nzchar(sv_link))) unlink(sv_out)
  sv <- arrow::read_parquet(source_paths$streetview_metadata, as_data_frame = TRUE)
  sv$subset_lon <- ifelse(!is.na(sv$pano_lon), sv$pano_lon, sv$lon)
  sv$subset_lat <- ifelse(!is.na(sv$pano_lat), sv$pano_lat, sv$lat)
  sv$subset_coordinate_source <- ifelse(!is.na(sv$pano_lon) & !is.na(sv$pano_lat), "pano_lon_lat", "lon_lat")
  sv <- sv[!is.na(sv$subset_lon) & !is.na(sv$subset_lat), , drop = FALSE]
  sv_sf <- sf::st_as_sf(sv, coords = c("subset_lon", "subset_lat"), crs = 4326, remove = FALSE)
  sv_sf <- sf::st_transform(sv_sf, TARGET_EPSG)
  if (isTRUE(region$bbox_only)) {
    bb <- sf::st_bbox(b$boundary)
    xy <- sf::st_coordinates(sv_sf)
    sv_sf <- sv_sf[xy[, "X"] >= bb["xmin"] & xy[, "X"] <= bb["xmax"] &
                     xy[, "Y"] >= bb["ymin"] & xy[, "Y"] <= bb["ymax"], , drop = FALSE]
    sv_method <- "pano_lon_lat_with_lon_lat_fallback_bbox_only_island_region"
  } else {
    sv_sf <- sv_sf[lengths(sf::st_intersects(sv_sf, b$boundary)) > 0, , drop = FALSE]
    sv_method <- "pano_lon_lat_with_lon_lat_fallback_within_or_touching_region_boundary"
  }
  sv_attr <- sf::st_drop_geometry(sv_sf)
  sv_attr$region_name <- rep(key, nrow(sv_attr))
  sv_attr$region_name_ko <- rep(region$region_name_ko, nrow(sv_attr))
  sv_attr$region_level <- rep(region$region_level, nrow(sv_attr))
  sv_attr$source_path <- rep(source_paths$streetview_metadata, nrow(sv_attr))
  sv_attr$subset_method <- rep(sv_method, nrow(sv_attr))
  sv_attr$subset_created_at <- rep(format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), nrow(sv_attr))
  sv_attr$geometry_wkt <- sf::st_as_text(sf::st_geometry(sv_sf))
  sv_attr$geometry_format <- rep(sprintf("WKT_EPSG_%d", TARGET_EPSG), nrow(sv_attr))
  arrow::write_parquet(sanitize_for_parquet(sv_attr), sv_out)
  images <- list.files(out_dir, pattern = "\\.(jpg|jpeg|png)$", ignore.case = TRUE,
                       recursive = TRUE, full.names = TRUE)
  streetview_log <<- rbind(streetview_log, data.table::data.table(
    region_key = key, source_path = source_paths$streetview_metadata,
    output_parquet = sv_out, input_row_count = 40000L, subset_row_count = nrow(sv_attr),
    id_col = "pano_id", id_unique = if ("pano_id" %in% names(sv_attr)) !anyDuplicated(sv_attr$pano_id[!is.na(sv_attr$pano_id)]) else NA,
    images_copied = length(images), coverage_note = "Current Street View metadata source is Seoul-only."
  ), fill = TRUE)
}

make_link <- function(target, link) {
  dir.create(dirname(link), recursive = TRUE, showWarnings = FALSE)
  existing_link <- Sys.readlink(link)
  if (file.exists(link) || (!is.na(existing_link) && nzchar(existing_link))) unlink(link)
  ok <- file.symlink(target, link)
  resolves <- file.exists(link) && normalizePath(link, mustWork = TRUE) == normalizePath(target, mustWork = TRUE)
  symlink_log <<- rbind(symlink_log, data.table::data.table(
    link_path = link, target_path = target, created = ok, resolves = resolves
  ), fill = TRUE)
}

create_korea_alias <- function() {
  out_dir <- file.path(working_root, "korea")
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  links <- c(
    "1_Building_vworld.gpkg" = source_paths$building_gpkg,
    "1_Building_vworld.parquet" = source_paths$building_attrs,
    "2_pointPOI_osm.gpkg" = source_paths$osm_point_gpkg,
    "2_pointPOI_osm.parquet" = source_paths$osm_point_attrs,
    "2_pointPOI_ngii.gpkg" = source_paths$ngii_point_gpkg,
    "2_pointPOI_ngii.parquet" = source_paths$ngii_point_attrs,
    "3_polygonPOI_osm.gpkg" = source_paths$osm_polygon_gpkg,
    "3_polygonPOI_osm.parquet" = source_paths$osm_polygon_attrs,
    "3_polygonPOI_togi.gpkg" = source_paths$togieeum_polygon_gpkg,
    "3_polygonPOI_togi.parquet" = source_paths$togieeum_polygon_attrs,
    "4_road_osm.gpkg" = source_paths$roads_gpkg,
    "4_road_osm.parquet" = source_paths$roads_attrs,
    "5_streetview.parquet" = source_paths$streetview_metadata
  )
  for (nm in names(links)) {
    if (file.exists(links[[nm]])) make_link(links[[nm]], file.path(out_dir, nm))
    else symlink_log <<- rbind(symlink_log, data.table::data.table(
      link_path = file.path(out_dir, nm), target_path = links[[nm]],
      created = FALSE, resolves = FALSE
    ), fill = TRUE)
  }
}

boundaries <- read_boundaries()
for (key in requested_keys) {
  if (key == "korea") create_korea_alias() else process_region(key, boundaries)
}

write_working_data_readme <- function() {
  path <- file.path(working_root, "README.md")
  txt <- sprintf(
"# FUSE Working Data

`working_data` contains standardized regional subsets for spatial scene representation, validation, and downstream embedding workflows.

Current region directories are `gwanak`, `seoul`, `daegu`, `jeju`, `gangneung`, `ganghwa`, `sejong`, `danyang`, `seongnam`, `incheon`, `daejeon`, `changwon`, `suwon`, and `korea`.

## Directory Convention

Regional subsets live under:

```text
~/fusedatalarge/working_data/<region_key>/
```

Example region keys are `gwanak`, `seoul`, `daegu`, `jeju`, `gangneung`, `ganghwa`, `danyang`, `seongnam`, `incheon`, `daejeon`, `changwon`, `suwon`, and `korea`.

## File Naming Convention

Each regional subset should contain:

```text
1_Building_vworld.gpkg
1_Building_vworld.parquet
2_pointPOI_osm.gpkg
2_pointPOI_osm.parquet
2_pointPOI_ngii.gpkg
2_pointPOI_ngii.parquet
3_polygonPOI_osm.gpkg
3_polygonPOI_osm.parquet
3_polygonPOI_togi.gpkg
3_polygonPOI_togi.parquet
4_road_osm.gpkg
4_road_osm.parquet
5_streetview.parquet
```

Street View stores metadata only. Image files are never copied into `working_data`.

## Source Datasets

- VWorld buildings: `~/fusedatalarge/processed/korea_buildings_vworld.gpkg` and `~/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet`
- OSM point POIs: `~/fusedatalarge/osm/canonical/gpkg/korea_pois_point.gpkg` and `~/fusedatalarge/osm/canonical/parquet/korea_pois_point.parquet`
- NGII point POIs: `~/fusedatalarge/processed/korea_poi_ngii_point.gpkg` and `~/fusedatalarge/processed/korea_poi_ngii_attributes.parquet`
- OSM polygon POIs: `~/fusedatalarge/osm/canonical/gpkg/korea_osm_polygon_poi_cleaned.gpkg` and `~/fusedatalarge/osm/canonical/parquet/korea_osm_polygon_poi_cleaned_attributes.parquet`
- Togieeum facility-filtered polygon POIs: `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility.gpkg` and `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility_attributes.parquet`
- OSM roads: `%s` and `%s`
- Street View metadata: `~/fusedata/streetview/final/gsv_seoul_metadata_final_40000.parquet`

Togieeum polygon POI subsets must use the facility-filtered files listed above. Do not use the broader legacy Togieeum polygon POI files for working-data generation.

## Geometry Rules

- Output CRS is EPSG:5186.
- Polygon and road layers are intersected with the regional boundary and clipped to that boundary.
- Point layers are filtered within or touching the regional boundary.
- Spatial parquet outputs store geometry as `geometry_wkt` with `geometry_format = WKT_EPSG_5186`.
- Stable IDs such as `building_id`, `poi_id`, `polygon_poi_id`, `road_id`, and `pano_id` are preserved.

## Korea Directory

`korea` is a nationwide alias directory. It uses symbolic links to canonical nationwide datasets and should not duplicate large source files. All symlinks must be validated after generation. The nationwide road parquet is an attribute companion to the nationwide road GPKG; regional clipped road parquet outputs include `geometry_wkt`.

## Adding a New Region

1. Add a new `region_key` and Korean region name to the region configuration in `~/fuse/scripts/working_data/create_validation_working_data.R`.
2. Specify `region_level` as `sido`, `sigungu`, `sigungu_merged`, or another explicit custom level.
3. Specify the boundary matching field and matching rule, such as exact name match or prefix match.
4. Run the script for the new region.
5. Inspect the dated report under `~/fuse/reports`.
6. Validate row counts and inspect representative GPKG outputs in QGIS.

## Script Usage

Script path:

```text
~/fuse/scripts/working_data/create_validation_working_data.R
```

Supported examples:

```bash
Rscript scripts/working_data/create_validation_working_data.R
Rscript scripts/working_data/create_validation_working_data.R --regions=seoul,jeju,suwon
Rscript scripts/working_data/create_validation_working_data.R --regions=all
Rscript scripts/working_data/create_validation_working_data.R --regions=korea --symlink-only
Rscript scripts/working_data/create_validation_working_data.R --regions=seoul --workers=40
```

Default `--regions=validation` creates Seoul, Daegu, Jeju, Gangneung, Ganghwa, Sejong, Danyang, Seongnam, Incheon, Daejeon, Changwon, Suwon, and Korea. `--regions=all` also includes Gwanak.

## Parallel Processing

Server default: 48 CPU cores, 768 GB RAM, and 2 x NVIDIA RTX A6000 48GB VRAM.

Working-data generation may use up to 40 CPU workers where useful. Region-level parallelism is allowed when safe, but single-file GDAL reads and GeoPackage writes may be run sequentially to avoid I/O contention and writer pressure.

## Validation and Reports

Each run must create a dated report under `~/fuse/reports`. The report must include source paths, boundary paths, row counts, CRS, geometry type, clipping/filtering method, ID uniqueness, GPKG/parquet row matching, Street View handling, symlink validation, and worker counts.

## Source Data Policy

Source datasets must not be modified. `working_data` outputs may be regenerated. Raw files must never be changed.
",
    source_paths$roads_gpkg,
    source_paths$roads_attrs
  )
  writeLines(txt, path, useBytes = TRUE)
  path
}

readme_path <- write_working_data_readme()

fmt_table <- function(x) paste(capture.output(print(x)), collapse = "\n")
report <- sprintf(
"# Validation Working Data Subset Report

Generated: %s

## Requested Regions

```text
%s
```

## Source Paths

```text
%s
```

## Boundary Selections

```text
%s
```

## Dataset Results

```text
%s
```

## Validation Checks

```text
%s
```

## Street View

```text
%s
```

Street View metadata is currently Seoul-only. Non-Seoul validation regions can therefore have zero Street View rows. No Street View image files were copied.

## Korea Symlinks

```text
%s
```

## Road Source Status

- Status: `%s`
- Raw input path: `%s`
- Selected OSM road/highway classes: `%s`
- CRS: `%s`
- Output GPKG: `%s`
- Output parquet: `%s`
- Feature count: `%s`
- Validation: `%s`

No existing nationwide canonical OSM road dataset was found under the documented canonical paths. A nationwide highway-tagged OSM road working source was derived from the raw Geofabrik PBF under `~/fusedatalarge/working_data/_sources` so source data and canonical OSM files remain unmodified.

## Worker Count

- Server default workers for this workflow: `%d`
- CLI requested workers: `%d`
- Actual workers used: `%d`
- Rationale: %s

## README

Working-data README written to `%s`.
",
  format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  paste(requested_keys, collapse = ", "),
  fmt_table(data.table::as.data.table(source_paths)),
  fmt_table(boundary_log),
  fmt_table(result_log),
  fmt_table(validation_log),
  fmt_table(streetview_log),
  fmt_table(symlink_log),
  road_status$source_status,
  road_status$raw_input_path,
  road_status$selected_classes,
  road_status$crs,
  road_status$gpkg,
  road_status$parquet,
  road_status$feature_count,
  road_status$validation,
  DEFAULT_WORKERS,
  args$workers,
  WORKERS_USED,
  WORKER_RATIONALE,
  readme_path
)
writeLines(report, report_path, useBytes = TRUE)

readme_report <- sprintf(
"# Working Data Reproducibility README Report

Generated: %s

- README created: `%s`
- Script path: `%s`
- Supported regions: `%s`
- Documentation files updated by this script: `~/fusedatalarge/working_data/README.md`
- CLI options implemented: `--regions=<validation|all|comma-separated keys>`, `--workers=<1-40>`, `--symlink-only`
- Validation report: `%s`

The README documents purpose, directory convention, standard filenames, canonical sources, geometry rules, Korea symlink behavior, adding new regions, script usage, parallel-processing policy, validation requirements, and the source-data no-modification policy.
",
  format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  readme_path,
  SCRIPT_PATH,
  paste(all_region_keys, collapse = ", "),
  report_path
)
writeLines(readme_report, readme_report_path, useBytes = TRUE)

log_msg("Validation report written: %s", report_path)
log_msg("README report written: %s", readme_report_path)
