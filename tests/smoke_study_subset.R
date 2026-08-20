#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
})

source("R/config_paths.R")
source("R/io_spatial.R")
source("R/spatial_boundary.R")
source("R/process_roads.R")
source("R/process_pois.R")
source("R/process_rasters.R")

set_single_thread_environment()
config <- load_pipeline_config("config/paths.yml", "config/methodology.yml")
manifest <- read_canonical_manifest(config$paths$canonical$manifest)
boundary_files <- boundary_component_paths(config$paths$administrative$sido)
boundary_info <- inspect_seoul_boundary_source(boundary_files, config, manifest)
seoul <- st_transform(read_selected_seoul(boundary_info, config), 5186)
buffer <- st_buffer(st_union(st_geometry(seoul)), 400)
stopifnot(st_is_valid(buffer), as.numeric(st_area(buffer)) > as.numeric(st_area(seoul)))

center <- st_coordinates(st_centroid(buffer))
smoke_bbox <- c(xmin = center[[1]] - 500, ymin = center[[2]] - 500,
                xmax = center[[1]] + 500, ymax = center[[2]] + 500)

for (item in list(
  c(config$paths$canonical$building, "buildings", "EPSG:5186"),
  c(config$paths$canonical$road, "links", "EPSG:5186")
)) {
  output <- run_command("ogrinfo", c(
    "-ro", "-q", item[[1]], item[[2]], "-spat",
    as.character(smoke_bbox[["xmin"]]), as.character(smoke_bbox[["ymin"]]),
    as.character(smoke_bbox[["xmax"]]), as.character(smoke_bbox[["ymax"]]),
    "-limit", "10"
  ), capture = TRUE)
  stopifnot(length(output) > 0L)
}

road_audit <- road_crs_audit(config$paths$canonical$road)
poi_audit <- poi_crs_audit(config$paths$canonical$poi)
stopifnot(identical(road_audit$coordinate_change_m, 0))
stopifnot(grepl("proj=axisswap", config$methodology$road$source_to_output_pipeline, fixed = TRUE))
stopifnot(road_audit$coordinate_change_m == 0, poi_audit$accuracy_m == 0)

landcover_info <- gdal_json(config$paths$canonical$landcover)
lc_extent <- snap_extent_to_source_raster(smoke_bbox, unlist(landcover_info$geoTransform))
stopifnot(extent_covers_bbox(lc_extent, smoke_bbox))
dem_extent <- snap_extent_to_grid(smoke_bbox, 30, 0, 0)
stopifnot(extent_covers_bbox(dem_extent, smoke_bbox))

cat("STUDY_SUBSET_SMOKE=PASS\n")
