suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
  library(arrow)
})

source("R/road_environment_sampling.R")

sf_use_s2(FALSE)

grid_path <- "data/grid_500m/seoul_grid_500m.gpkg"
boundary_path <- "data/geodata/seoul_boundary.gpkg"
samples_path <- Sys.getenv(
  "SEOUL_SAMPLES_PARQUET",
  "data/sampling_global/seoul_road_network_samples.parquet"
)

out_html <- Sys.getenv(
  "SEOUL_LEAFLET_OUT",
  "data/sampling_global/seoul_road_network_sampling_map.html"
)

grid <- read_sf_projected(grid_path, layer = "seoul_grid_500m")
boundary <- read_sf_projected(boundary_path)
samples <- arrow::read_parquet(samples_path)

make_leaflet_map(
  boundary = boundary,
  grid = grid,
  samples = samples,
  out_html = out_html,
  max_grid_cells = as.integer(Sys.getenv("SEOUL_LEAFLET_MAX_GRIDS", "5000")),
  max_points = as.integer(Sys.getenv("SEOUL_LEAFLET_MAX_POINTS", "30000")),
  grid_simplify_tolerance_m = as.numeric(Sys.getenv("SEOUL_LEAFLET_GRID_SIMPLIFY_M", "1")),
  boundary_simplify_tolerance_m = as.numeric(Sys.getenv("SEOUL_LEAFLET_BOUNDARY_SIMPLIFY_M", "5"))
)

message("Leaflet map rendered: ", out_html)
