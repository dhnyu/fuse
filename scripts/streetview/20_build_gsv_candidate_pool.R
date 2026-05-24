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

candidate_pool_path <- fuse_file("gsv_candidate_pool_parquet", create_parent = TRUE)
sampling_network_path <- fuse_file("osm_roads_sampling_network", create_parent = TRUE)
composition_path <- fuse_file("gsv_sampling_network_composition", create_parent = TRUE)

target_candidates <- as.integer(Sys.getenv("GSV_CANDIDATE_POOL_SIZE", "150000"))
candidate_spacing_m <- as.numeric(Sys.getenv("GSV_CANDIDATE_SPACING_M", "8"))
min_spacing_m <- as.numeric(Sys.getenv("GSV_CANDIDATE_MIN_SPACING_M", "25"))
seed <- as.integer(Sys.getenv("GSV_CANDIDATE_SEED", "20260524"))
candidate_workers <- as.integer(Sys.getenv("GSV_CANDIDATE_WORKERS", "40"))
candidate_chunk_size <- as.integer(Sys.getenv("GSV_CANDIDATE_CHUNK_SIZE", "2000"))
force_grid <- identical(tolower(Sys.getenv("SEOUL_FORCE_GRID", "false")), "true")
force_osm <- identical(tolower(Sys.getenv("SEOUL_FORCE_OSM", "false")), "true")

grid <- build_seoul_grid(
  cell_size_m = 500,
  boundary_path = fuse_file("seoul_boundary", must_exist = TRUE),
  grid_path = fuse_file("seoul_grid_500m"),
  map_path = fuse_file("seoul_grid_500m_map", create_parent = TRUE),
  force = force_grid
)
boundary <- read_sf_projected(fuse_file("seoul_boundary", must_exist = TRUE))
roads <- download_and_cache_osm_roads(
  grid = grid,
  out_path = fuse_file("osm_roads_canonical", create_parent = TRUE),
  osm_place = "South Korea",
  download_directory = fuse_dir("osm_raw", create = TRUE),
  buffer_m = 250,
  force = force_osm
)

operational_network <- construct_seoul_road_network(roads = roads, boundary = boundary)
ensure_dir(dirname(sampling_network_path))
st_write(operational_network, sampling_network_path, delete_dsn = TRUE, quiet = TRUE)

composition <- network_composition(operational_network, label = "operational_no_tunnel_no_service")
arrow::write_parquet(composition, composition_path)

message("Operational network excludes tunnel=yes/true/1 roads and highway=service.")
message("Operational network features: ", format(nrow(operational_network), big.mark = ","))
message("Operational network length m: ", format(round(sum(operational_network$length_m, na.rm = TRUE)), big.mark = ","))
message("Generating oversampled GSV candidate pool; target candidates: ", format(target_candidates, big.mark = ","))

candidates <- generate_road_candidates(
  operational_network,
  spacing_m = candidate_spacing_m,
  workers = candidate_workers,
  chunk_size = candidate_chunk_size
)
message("Regular road candidates: ", format(nrow(candidates), big.mark = ","))

thinned <- poisson_disk_thin_candidates(
  candidates = candidates,
  min_spacing_m = min_spacing_m,
  target_count = target_candidates,
  seed = seed
)

candidate_pool <- assign_samples_to_grid(thinned, grid = grid) %>%
  rename(candidate_id = point_id) %>%
  mutate(
    candidate_rank = row_number(),
    candidate_seed = seed,
    candidate_spacing_m = candidate_spacing_m,
    candidate_min_spacing_m = min_spacing_m
  ) %>%
  select(
    candidate_id,
    candidate_rank,
    grid_id,
    highway_class,
    sampled_rank,
    lon,
    lat,
    source_road_id,
    nearest_neighbor_distance,
    candidate_seed,
    candidate_spacing_m,
    candidate_min_spacing_m
  )

arrow::write_parquet(candidate_pool, candidate_pool_path)
message("GSV candidate pool rows: ", format(nrow(candidate_pool), big.mark = ","))
message("Candidate pool written: ", candidate_pool_path)
message("Network composition written: ", composition_path)
