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

final_manifest <- Sys.getenv("GSV_FINAL_MANIFEST", fuse_file("gsv_final_manifest", must_exist = TRUE))
out_html <- Sys.getenv("GSV_COVERAGE_MAP_OUT", fuse_file("gsv_final_coverage_leaflet", create_parent = TRUE))
max_points <- as.integer(Sys.getenv("GSV_COVERAGE_MAX_POINTS", "40000"))

boundary <- read_sf_projected(fuse_file("seoul_boundary", must_exist = TRUE))
grid <- read_sf_projected(fuse_file("seoul_grid_500m", must_exist = TRUE))

samples <- arrow::read_parquet(final_manifest) %>%
  transmute(
    point_id = as.integer(final_rank),
    grid_id = as.integer(grid_id),
    highway_class = as.character(highway_class),
    sampled_rank = as.integer(sampled_rank),
    lon = as.numeric(source_lon),
    lat = as.numeric(source_lat),
    source_road_id = as.integer(source_road_id),
    nearest_neighbor_distance = as.numeric(NA)
  )

make_leaflet_map(
  boundary = boundary,
  grid = grid,
  samples = samples,
  out_html = out_html,
  max_grid_cells = 5000,
  max_points = max_points,
  grid_simplify_tolerance_m = 1,
  boundary_simplify_tolerance_m = 5
)

message("GSV final coverage map written: ", out_html)
