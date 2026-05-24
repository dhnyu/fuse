suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
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

grid <- build_seoul_grid(
  cell_size_m = 500,
  boundary_path = fuse_file("seoul_boundary", must_exist = TRUE),
  grid_path = fuse_file("seoul_grid_500m", create_parent = TRUE),
  map_path = fuse_file("seoul_grid_500m_map", create_parent = TRUE),
  force = identical(tolower(Sys.getenv("SEOUL_FORCE_GRID", "false")), "true")
)

message("500m Seoul grid cells: ", format(nrow(grid), big.mark = ","))
message("Grid written to ", fuse_file("seoul_grid_500m"))
