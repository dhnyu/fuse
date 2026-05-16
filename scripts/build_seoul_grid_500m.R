suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
})

source("R/road_environment_sampling.R")

sf_use_s2(FALSE)

grid <- build_seoul_grid(
  cell_size_m = 500,
  boundary_path = "data/geodata/seoul_boundary.gpkg",
  grid_path = "data/grid_500m/seoul_grid_500m.gpkg",
  map_path = "data/grid_500m/seoul_grid_500m_map.png",
  force = identical(tolower(Sys.getenv("SEOUL_FORCE_GRID", "false")), "true")
)

message("500m Seoul grid cells: ", format(nrow(grid), big.mark = ","))
message("Grid written to data/grid_500m/seoul_grid_500m.gpkg")
