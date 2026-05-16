suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
  library(arrow)
})

source("R/road_environment_sampling.R")

sf_use_s2(FALSE)

grid_path <- "data/grid_1km/seoul_grid_1km.gpkg"
boundary_path <- "data/geodata/seoul_boundary.gpkg"
roads_path <- "data/osm/seoul_roads_filtered.gpkg"
samples_path <- "data/sampling_1km/seoul_road_environment_samples_1km.parquet"

out_html <- Sys.getenv(
  "SEOUL_LEAFLET_OUT",
  "data/sampling_1km/seoul_road_environment_sampling_1km_map.html"
)

grid <- read_sf_projected(grid_path, layer = "seoul_grid_1km")
boundary <- read_sf_projected(boundary_path)
roads <- read_sf_projected(roads_path) %>% normalize_road_schema()
samples <- arrow::read_parquet(samples_path)

make_leaflet_map(
  boundary = boundary,
  grid = grid,
  roads = roads,
  samples = samples,
  out_html = out_html,
  max_grid_cells = as.integer(Sys.getenv("SEOUL_LEAFLET_MAX_GRIDS", "1200")),
  max_roads = as.integer(Sys.getenv("SEOUL_LEAFLET_MAX_ROADS", "20000")),
  max_points = as.integer(Sys.getenv("SEOUL_LEAFLET_MAX_POINTS", "10000")),
  road_simplify_tolerance_m = as.numeric(Sys.getenv("SEOUL_LEAFLET_ROAD_SIMPLIFY_M", "10")),
  grid_simplify_tolerance_m = as.numeric(Sys.getenv("SEOUL_LEAFLET_GRID_SIMPLIFY_M", "1")),
  boundary_simplify_tolerance_m = as.numeric(Sys.getenv("SEOUL_LEAFLET_BOUNDARY_SIMPLIFY_M", "5"))
)

message("Leaflet map rendered: ", out_html)
