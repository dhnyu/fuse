#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
  library(dplyr)
  library(rlang)
})

sf::sf_use_s2(FALSE)
Sys.setenv(TZ = "Asia/Seoul")

TARGET_EPSG <- 5186L
REGION_ID <- "gwanak_gu"
DEFAULT_CPU_WORKERS <- 40L
WORKERS_USED <- 1L
WORKER_RATIONALE <- paste(
  "The project default is 40 CPU workers. This subset build used one worker",
  "because the dominant operations are GDAL/GeoPackage bounded reads, single-file",
  "GeoPackage writes, and targeted Arrow sidecar lookups against multi-GB sources.",
  "Parallelizing those I/O-bound steps would increase concurrent disk pressure and",
  "memory duplication without a parallel-safe chunk boundary for the requested outputs."
)

root_fusedatalarge <- path.expand("~/fusedatalarge")
root_fusedata <- path.expand("~/fusedata")
root_fuse <- path.expand("~/fuse")

out_dir <- file.path(root_fusedatalarge, "working_data", "gwanak")
report_dir <- file.path(root_fuse, "reports")
timestamp <- format(Sys.time(), "%Y%m%d_%H%M")
report_path <- file.path(report_dir, sprintf("%s_gwanak_working_data_subset_report.md", timestamp))

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(report_dir, recursive = TRUE, showWarnings = FALSE)

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), sprintf(...)))
  flush.console()
}

must_exist <- function(path) {
  if (!file.exists(path)) {
    stop(sprintf("Required path does not exist: %s", path), call. = FALSE)
  }
  path
}

get_layer_feature_count <- function(path, layer) {
  layers <- sf::st_layers(path, do_count = TRUE)
  idx <- match(layer, layers$name)
  if (is.na(idx)) {
    stop(sprintf("Layer '%s' not found in %s. Available layers: %s",
                 layer, path, paste(layers$name, collapse = ", ")), call. = FALSE)
  }
  as.numeric(layers$features[idx])
}

read_with_bbox <- function(path, layer, boundary_5186) {
  bbox_geom <- sf::st_as_sfc(sf::st_bbox(boundary_5186))
  sf::st_crs(bbox_geom) <- sf::st_crs(boundary_5186)
  bbox_wkt <- sf::st_as_text(bbox_geom)
  log_msg("Reading %s layer %s with Gwanak bbox filter", path, layer)
  x <- sf::st_read(path, layer = layer, wkt_filter = bbox_wkt, quiet = TRUE)
  if (is.na(sf::st_crs(x))) {
    stop(sprintf("Missing CRS for %s layer %s", path, layer), call. = FALSE)
  }
  if (sf::st_crs(x)$epsg != TARGET_EPSG) {
    x <- sf::st_transform(x, TARGET_EPSG)
  }
  x
}

make_valid_if_polygonal <- function(x) {
  geom_types <- unique(as.character(sf::st_geometry_type(x, by_geometry = TRUE)))
  if (any(grepl("POLYGON", geom_types))) {
    x <- sf::st_make_valid(x)
  }
  x
}

spatial_filter <- function(x, boundary) {
  if (sf::st_crs(x) != sf::st_crs(boundary)) {
    boundary <- sf::st_transform(boundary, sf::st_crs(x))
  }
  keep <- lengths(sf::st_intersects(x, boundary)) > 0
  x[keep, , drop = FALSE]
}

clip_to_boundary <- function(x, boundary, kind) {
  if (nrow(x) == 0L) {
    return(x)
  }
  if (sf::st_crs(x) != sf::st_crs(boundary)) {
    boundary <- sf::st_transform(boundary, sf::st_crs(x))
  }
  x <- make_valid_if_polygonal(x)
  clipped <- suppressWarnings(sf::st_intersection(x, sf::st_geometry(boundary)))
  if (kind == "polygon") {
    clipped <- suppressWarnings(sf::st_collection_extract(clipped, "POLYGON"))
    if (nrow(clipped) > 0L) {
      clipped <- suppressWarnings(sf::st_cast(clipped, "MULTIPOLYGON", warn = FALSE))
    }
  } else if (kind == "line") {
    clipped <- suppressWarnings(sf::st_collection_extract(clipped, "LINESTRING"))
    if (nrow(clipped) > 0L) {
      clipped <- suppressWarnings(sf::st_cast(clipped, "MULTILINESTRING", warn = FALSE))
    }
  }
  clipped[!sf::st_is_empty(clipped), , drop = FALSE]
}

read_arrow_attrs_by_id <- function(path, id_col, ids, chunk_size = 5000L) {
  if (is.null(path) || !file.exists(path) || !(id_col %in% names(open_dataset(path)$schema))) {
    return(NULL)
  }
  ids <- unique(as.character(ids[!is.na(ids)]))
  if (!length(ids)) {
    return(data.table())
  }
  ds <- arrow::open_dataset(path)
  chunks <- split(ids, ceiling(seq_along(ids) / chunk_size))
  out <- vector("list", length(chunks))
  for (i in seq_along(chunks)) {
    log_msg("Reading %s attributes chunk %d/%d from %s", id_col, i, length(chunks), path)
    expr <- rlang::expr(!!rlang::sym(id_col) %in% !!chunks[[i]])
    out[[i]] <- tryCatch(
      ds %>% dplyr::filter(!!expr) %>% dplyr::collect() %>% data.table::as.data.table(),
      error = function(e) {
        stop(sprintf("Failed to filter %s by %s: %s", path, id_col, conditionMessage(e)), call. = FALSE)
      }
    )
  }
  unique(data.table::rbindlist(out, use.names = TRUE, fill = TRUE), by = id_col)
}

attach_attrs <- function(x, attr_path, id_col) {
  if (is.null(attr_path) || !file.exists(attr_path) || !(id_col %in% names(x))) {
    return(x)
  }
  attrs <- read_arrow_attrs_by_id(attr_path, id_col, x[[id_col]])
  if (is.null(attrs) || !nrow(attrs)) {
    return(x)
  }
  x_dt <- data.table::as.data.table(sf::st_drop_geometry(x))
  x_dt[, .subset_order := .I]
  extra_cols <- setdiff(names(attrs), names(x_dt))
  if (!length(extra_cols)) {
    return(x)
  }
  attrs <- attrs[, c(id_col, extra_cols), with = FALSE]
  joined <- merge(x_dt, attrs, by = id_col, all.x = TRUE, sort = FALSE)
  data.table::setorder(joined, .subset_order)
  joined[, .subset_order := NULL]
  sf::st_sf(as.data.frame(joined), geometry = sf::st_geometry(x), crs = sf::st_crs(x))
}

sanitize_for_parquet <- function(df) {
  for (nm in names(df)) {
    if (inherits(df[[nm]], "Date")) {
      next
    }
    if (inherits(df[[nm]], "POSIXt")) {
      df[[nm]] <- as.character(df[[nm]])
      next
    }
    if (inherits(df[[nm]], "sfc") || inherits(df[[nm]], "units")) {
      df[[nm]] <- as.numeric(df[[nm]])
    }
  }
  df
}

write_spatial_outputs <- function(x, gpkg_path, parquet_path, layer_name, source_path,
                                  method, id_col = NA_character_) {
  if (file.exists(gpkg_path)) {
    log_msg("Replacing existing target output: %s", gpkg_path)
    file.remove(gpkg_path)
  }
  if (file.exists(parquet_path)) {
    log_msg("Replacing existing target output: %s", parquet_path)
    file.remove(parquet_path)
  }
  x$subset_region <- REGION_ID
  x$subset_source_path <- source_path
  x$subset_method <- method
  x$subset_created_at <- format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")

  sf::st_write(x, gpkg_path, layer = layer_name, quiet = TRUE)

  attrs <- sf::st_drop_geometry(x)
  attrs$geometry_wkt <- sf::st_as_text(sf::st_geometry(x))
  attrs$geometry_format <- sprintf("WKT_EPSG_%d", TARGET_EPSG)
  attrs <- sanitize_for_parquet(attrs)
  arrow::write_parquet(attrs, parquet_path)

  list(
    gpkg_path = gpkg_path,
    parquet_path = parquet_path,
    row_count = nrow(x),
    geometry_type = paste(sort(unique(as.character(sf::st_geometry_type(x, by_geometry = TRUE)))), collapse = ", "),
    method = method,
    id_col = id_col
  )
}

source_paths <- list(
  boundary = file.path(root_fusedatalarge, "geodata", "koreanadm", "bnd_sigungu_00_2024_2Q.shp"),
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
  osm_roads_gpkg = file.path(root_fusedatalarge, "osm", "canonical", "seoul_roads_canonical.gpkg"),
  streetview_metadata = file.path(root_fusedata, "streetview", "final", "gsv_seoul_metadata_final_40000.parquet")
)

invisible(lapply(source_paths, must_exist))

layers <- list(
  building = "buildings",
  osm_point = "korea_pois_point",
  ngii_point = "points",
  osm_polygon = "polygon_pois",
  togieeum_polygon = "polygon_pois_facility",
  osm_roads = "seoul_roads_canonical"
)

output_paths <- list(
  building_gpkg = file.path(out_dir, "1_Building_vworld.gpkg"),
  building_parquet = file.path(out_dir, "1_Building_vworld.parquet"),
  osm_point_gpkg = file.path(out_dir, "2_pointPOI_osm.gpkg"),
  osm_point_parquet = file.path(out_dir, "2_pointPOI_osm.parquet"),
  ngii_point_gpkg = file.path(out_dir, "2_pointPOI_ngii.gpkg"),
  ngii_point_parquet = file.path(out_dir, "2_pointPOI_ngii.parquet"),
  osm_polygon_gpkg = file.path(out_dir, "3_polygonPOI_osm.gpkg"),
  osm_polygon_parquet = file.path(out_dir, "3_polygonPOI_osm.parquet"),
  togieeum_polygon_gpkg = file.path(out_dir, "3_polygonPOI_togi.gpkg"),
  togieeum_polygon_parquet = file.path(out_dir, "3_polygonPOI_togi.parquet"),
  osm_roads_gpkg = file.path(out_dir, "4_road_osm.gpkg"),
  osm_roads_parquet = file.path(out_dir, "4_road_osm.parquet"),
  streetview_parquet = file.path(out_dir, "5_streetview.parquet")
)

log_msg("Reading Gwanak-gu boundary")
boundary_raw <- sf::st_read(source_paths$boundary, quiet = TRUE)
if (!("SIGUNGU_CD" %in% names(boundary_raw))) {
  stop("Administrative boundary source lacks SIGUNGU_CD", call. = FALSE)
}
name_cols <- intersect(c("SIGUNGU_NM", "sigungu_nm", "name", "NAME"), names(boundary_raw))
if (length(name_cols)) {
  name_hit <- Reduce(`|`, lapply(name_cols, function(nm) grepl("관악|Gwanak|GWANAK", as.character(boundary_raw[[nm]]))))
  gwanak <- boundary_raw[name_hit, , drop = FALSE]
} else {
  gwanak <- boundary_raw[FALSE, , drop = FALSE]
}
if (nrow(gwanak) != 1L) {
  gwanak <- boundary_raw[as.character(boundary_raw$SIGUNGU_CD) %in% c("11210", "11620"), , drop = FALSE]
}
if (nrow(gwanak) != 1L) {
  stop(sprintf("Expected one Gwanak-gu boundary, found %d", nrow(gwanak)), call. = FALSE)
}
boundary_source_crs <- sf::st_crs(gwanak)$epsg
boundary_source_code <- as.character(gwanak$SIGUNGU_CD[[1]])
boundary_source_name <- if ("SIGUNGU_NM" %in% names(gwanak)) as.character(gwanak$SIGUNGU_NM[[1]]) else "Gwanak-gu"
gwanak <- sf::st_transform(sf::st_make_valid(gwanak), TARGET_EPSG)
gwanak <- sf::st_sf(SIGUNGU_CD = boundary_source_code, SIGUNGU_NM = boundary_source_name,
                    subset_region = REGION_ID,
                    geometry = sf::st_union(sf::st_geometry(gwanak)),
                    crs = TARGET_EPSG)

manifest <- data.table::data.table(
  dataset = character(),
  source_path = character(),
  source_attr_path = character(),
  output_gpkg = character(),
  output_parquet = character(),
  input_row_count = numeric(),
  subset_row_count = numeric(),
  geometry_type = character(),
  method = character(),
  id_col = character(),
  notes = character()
)

process_spatial <- function(dataset, source_path, source_attr_path, layer, gpkg_out, parquet_out,
                            kind, method, id_col) {
  input_count <- get_layer_feature_count(source_path, layer)
  x <- read_with_bbox(source_path, layer, gwanak)
  x <- spatial_filter(x, gwanak)
  if (kind %in% c("polygon", "line")) {
    x <- clip_to_boundary(x, gwanak, kind)
  }
  if (nrow(x) && !is.null(source_attr_path)) {
    x <- attach_attrs(x, source_attr_path, id_col)
  }
  if (kind == "polygon" && nrow(x)) {
    x$subset_area_m2 <- as.numeric(sf::st_area(x))
  }
  if (kind == "line" && nrow(x)) {
    x$subset_length_m <- as.numeric(sf::st_length(x))
  }
  res <- write_spatial_outputs(
    x = x,
    gpkg_path = gpkg_out,
    parquet_path = parquet_out,
    layer_name = tools::file_path_sans_ext(basename(gpkg_out)),
    source_path = source_path,
    method = method,
    id_col = id_col
  )
  manifest <<- rbind(
    manifest,
    data.table::data.table(
      dataset = dataset,
      source_path = source_path,
      source_attr_path = source_attr_path %||% "",
      output_gpkg = gpkg_out,
      output_parquet = parquet_out,
      input_row_count = input_count,
      subset_row_count = res$row_count,
      geometry_type = res$geometry_type,
      method = method,
      id_col = id_col,
      notes = ""
    ),
    fill = TRUE
  )
  invisible(res)
}

`%||%` <- function(x, y) if (is.null(x)) y else x

process_spatial(
  "VWorld buildings",
  source_paths$building_gpkg,
  source_paths$building_attrs,
  layers$building,
  output_paths$building_gpkg,
  output_paths$building_parquet,
  "polygon",
  "intersected_with_gwanak_and_clipped_to_boundary",
  "building_id"
)

process_spatial(
  "OSM point POIs",
  source_paths$osm_point_gpkg,
  NULL,
  layers$osm_point,
  output_paths$osm_point_gpkg,
  output_paths$osm_point_parquet,
  "point",
  "within_or_touching_gwanak_boundary",
  "poi_id"
)

process_spatial(
  "NGII point POIs",
  source_paths$ngii_point_gpkg,
  source_paths$ngii_point_attrs,
  layers$ngii_point,
  output_paths$ngii_point_gpkg,
  output_paths$ngii_point_parquet,
  "point",
  "within_or_touching_gwanak_boundary",
  "poi_id"
)

process_spatial(
  "OSM polygon POIs",
  source_paths$osm_polygon_gpkg,
  source_paths$osm_polygon_attrs,
  layers$osm_polygon,
  output_paths$osm_polygon_gpkg,
  output_paths$osm_polygon_parquet,
  "polygon",
  "intersected_with_gwanak_and_clipped_to_boundary",
  "polygon_poi_id"
)

process_spatial(
  "Togieeum facility polygon POIs",
  source_paths$togieeum_polygon_gpkg,
  source_paths$togieeum_polygon_attrs,
  layers$togieeum_polygon,
  output_paths$togieeum_polygon_gpkg,
  output_paths$togieeum_polygon_parquet,
  "polygon",
  "intersected_with_gwanak_and_clipped_to_boundary",
  "polygon_poi_id"
)

process_spatial(
  "OSM roads",
  source_paths$osm_roads_gpkg,
  NULL,
  layers$osm_roads,
  output_paths$osm_roads_gpkg,
  output_paths$osm_roads_parquet,
  "line",
  "intersected_with_gwanak_and_clipped_to_boundary",
  "source_road_id"
)

log_msg("Subsetting Street View metadata")
if (file.exists(output_paths$streetview_parquet)) {
  log_msg("Replacing existing target output: %s", output_paths$streetview_parquet)
  file.remove(output_paths$streetview_parquet)
}
sv <- arrow::read_parquet(source_paths$streetview_metadata, as_data_frame = TRUE)
sv$subset_lon <- ifelse(!is.na(sv$pano_lon), sv$pano_lon, sv$lon)
sv$subset_lat <- ifelse(!is.na(sv$pano_lat), sv$pano_lat, sv$lat)
sv$subset_coordinate_source <- ifelse(!is.na(sv$pano_lon) & !is.na(sv$pano_lat), "pano_lon_lat", "lon_lat")
sv_valid <- sv[!is.na(sv$subset_lon) & !is.na(sv$subset_lat), , drop = FALSE]
sv_sf <- sf::st_as_sf(sv_valid, coords = c("subset_lon", "subset_lat"), crs = 4326, remove = FALSE)
sv_sf <- sf::st_transform(sv_sf, TARGET_EPSG)
sv_keep <- lengths(sf::st_intersects(sv_sf, gwanak)) > 0
sv_sub <- sv_sf[sv_keep, , drop = FALSE]
sv_attr <- sf::st_drop_geometry(sv_sub)
sv_attr$subset_region <- REGION_ID
sv_attr$subset_source_path <- source_paths$streetview_metadata
sv_attr$subset_method <- "pano_lon_lat_with_lon_lat_fallback_within_or_touching_gwanak_boundary"
sv_attr$subset_created_at <- format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")
sv_attr$geometry_wkt <- sf::st_as_text(sf::st_geometry(sv_sub))
sv_attr$geometry_format <- sprintf("WKT_EPSG_%d", TARGET_EPSG)
sv_attr <- sanitize_for_parquet(sv_attr)
arrow::write_parquet(sv_attr, output_paths$streetview_parquet)

manifest <- rbind(
  manifest,
  data.table::data.table(
    dataset = "Street View metadata",
    source_path = source_paths$streetview_metadata,
    source_attr_path = "",
    output_gpkg = "",
    output_parquet = output_paths$streetview_parquet,
    input_row_count = nrow(sv),
    subset_row_count = nrow(sv_attr),
    geometry_type = "POINT WKT in parquet only",
    method = "pano_lon_lat_with_lon_lat_fallback_within_or_touching_gwanak_boundary",
    id_col = "pano_id",
    notes = "No image files copied."
  ),
  fill = TRUE
)

image_files <- list.files(out_dir, pattern = "\\.(jpg|jpeg|png)$", ignore.case = TRUE,
                          recursive = TRUE, full.names = TRUE)

log_msg("Validating output row counts")
validation <- data.table::data.table(
  dataset = manifest$dataset,
  output_gpkg_rows = NA_real_,
  output_parquet_rows = NA_real_,
  id_unique = NA,
  notes = ""
)
for (i in seq_len(nrow(manifest))) {
  if (nzchar(manifest$output_gpkg[i])) {
    layer <- tools::file_path_sans_ext(basename(manifest$output_gpkg[i]))
    validation$output_gpkg_rows[i] <- get_layer_feature_count(manifest$output_gpkg[i], layer)
  }
  validation$output_parquet_rows[i] <- nrow(arrow::read_parquet(manifest$output_parquet[i], as_data_frame = TRUE))
  id_col <- manifest$id_col[i]
  attrs <- arrow::read_parquet(manifest$output_parquet[i], as_data_frame = TRUE)
  if (id_col %in% names(attrs)) {
    validation$id_unique[i] <- !anyDuplicated(attrs[[id_col]][!is.na(attrs[[id_col]])])
  }
}

manifest_md <- paste(capture.output(print(manifest)), collapse = "\n")
validation_md <- paste(capture.output(print(validation)), collapse = "\n")
source_md <- paste(capture.output(print(data.table::as.data.table(source_paths))), collapse = "\n")
output_md <- paste(capture.output(print(data.table::as.data.table(output_paths))), collapse = "\n")

report <- sprintf(
"# Gwanak Working Data Subset Report

Generated: %s

## Boundary

- Boundary source path: `%s`
- Boundary selector: district name matched Gwanak/관악, with `SIGUNGU_CD` fallback accepting `11210` or `11620`
- Boundary source feature: `%s` / `%s`
- Boundary source CRS: EPSG:%s
- Output/subset CRS: EPSG:%d

The source administrative boundary was transformed to EPSG:5186 before all spatial filtering. Polygon and road datasets were first read with a GDAL bounding-box filter, then exactly intersected with the Gwanak-gu boundary. Polygon and road geometries were clipped to the boundary. Point datasets were filtered by intersection with the boundary, preserving points within or touching Gwanak-gu.

## Source Paths

```text
%s
```

## Output Paths

```text
%s
```

## Worker Count

- Default CPU workers: `%d`
- Workers used by this run: `%d`
- Rationale: %s

## Dataset Results

```text
%s
```

## Validation

```text
%s
```

## Street View Handling

Street View metadata was subset from `%s` using `pano_lon`/`pano_lat` when available and `lon`/`lat` as fallback. The output is parquet only: `%s`.

No Street View image files were copied. Image files found under the Gwanak working-data output directory after the run: `%d`.

## Notes

- The Togieeum polygon POI subset uses the facility-filtered canonical source, not the broader legacy cleaned Togieeum file.
- Spatial parquet outputs include `geometry_wkt` and `geometry_format = WKT_EPSG_5186` rather than a native GeoParquet geometry column.
- Source datasets were not modified. Existing target subset files, if present, were replaced only at the exact required output paths.
",
  format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  source_paths$boundary,
  boundary_source_name,
  boundary_source_code,
  ifelse(is.na(boundary_source_crs), "unknown", as.character(boundary_source_crs)),
  TARGET_EPSG,
  source_md,
  output_md,
  DEFAULT_CPU_WORKERS,
  WORKERS_USED,
  WORKER_RATIONALE,
  manifest_md,
  validation_md,
  source_paths$streetview_metadata,
  output_paths$streetview_parquet,
  length(image_files)
)

writeLines(report, report_path, useBytes = TRUE)

log_msg("Report written: %s", report_path)
log_msg("Gwanak working data outputs written under: %s", out_dir)
