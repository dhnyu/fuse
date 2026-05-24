suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
  library(arrow)
})

find_repo_root_from <- function(start) {
  current <- normalizePath(start, winslash = "/", mustWork = TRUE)
  repeat {
    if (file.exists(file.path(current, "config", "paths.R"))) return(current)
    parent <- dirname(current)
    if (identical(parent, current)) stop("Could not locate repository root.", call. = FALSE)
    current <- parent
  }
}
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
start_dir <- if (length(script_arg)) dirname(sub("^--file=", "", script_arg[1])) else getwd()
repo_root <- find_repo_root_from(start_dir)
source(file.path(repo_root, "config", "paths.R"))
source(file.path(fuse_repo_root(), "R", "road_environment_sampling.R"))

sf_use_s2(FALSE)

grid_path <- fuse_file("seoul_grid_500m", must_exist = TRUE)
boundary_path <- fuse_file("seoul_boundary", must_exist = TRUE)
samples_path <- Sys.getenv(
  "SEOUL_SAMPLES_PARQUET",
  fuse_file("samples_global_parquet", must_exist = TRUE)
)

out_html <- Sys.getenv(
  "SEOUL_LEAFLET_OUT",
  fuse_file("samples_global_leaflet", create_parent = TRUE)
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
