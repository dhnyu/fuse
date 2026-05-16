suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
})

source("R/road_environment_sampling.R")

sf_use_s2(FALSE)

grid <- build_seoul_grid(
  cell_size_m = 1000,
  boundary_path = "data/geodata/seoul_boundary.gpkg",
  grid_path = "data/grid_1km/seoul_grid_1km.gpkg",
  map_path = "data/grid_1km/seoul_grid_1km_map.png",
  force = identical(tolower(Sys.getenv("SEOUL_FORCE_GRID", "false")), "true")
)

message("1km Seoul grid cells: ", format(nrow(grid), big.mark = ","))
message("Grid written to data/grid_1km/seoul_grid_1km.gpkg")
