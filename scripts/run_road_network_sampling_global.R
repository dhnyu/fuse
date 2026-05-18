suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
  library(arrow)
  library(future)
  library(future.mirai)
})

source("R/road_environment_sampling.R")

sf_use_s2(FALSE)

grid_path <- "data/grid_500m/seoul_grid_500m.gpkg"
boundary_path <- "data/geodata/seoul_boundary.gpkg"
roads_path <- "data/osm/canonical/seoul_roads_canonical.gpkg"
final_parquet <- "data/sampling_global/seoul_road_network_samples.parquet"
map_html <- "data/sampling_global/seoul_road_network_sampling_map.html"
sampling_network_path <- "data/osm/sampling/seoul_roads_sampling_network.gpkg"

target_count <- as.integer(Sys.getenv("SEOUL_TARGET_SAMPLE_COUNT", "40000"))
candidate_spacing_m <- as.numeric(Sys.getenv("SEOUL_CANDIDATE_SPACING_M", "10"))
min_spacing_m <- as.numeric(Sys.getenv("SEOUL_MIN_SAMPLE_SPACING_M", "50"))
seed <- as.integer(Sys.getenv("SEOUL_SAMPLE_SEED", "20260517"))
candidate_workers <- as.integer(Sys.getenv("SEOUL_CANDIDATE_WORKERS", "40"))
candidate_chunk_size <- as.integer(Sys.getenv("SEOUL_CANDIDATE_CHUNK_SIZE", "2000"))
force_grid <- identical(tolower(Sys.getenv("SEOUL_FORCE_GRID", "false")), "true")
force_osm <- identical(tolower(Sys.getenv("SEOUL_FORCE_OSM", "false")), "true")
write_debug <- identical(tolower(Sys.getenv("SEOUL_WRITE_DEBUG_GPKG", "true")), "true")

grid <- build_seoul_grid(
  cell_size_m = 500,
  boundary_path = boundary_path,
  grid_path = grid_path,
  map_path = "data/grid_500m/seoul_grid_500m_map.png",
  force = force_grid
)

boundary <- read_sf_projected(boundary_path)

roads <- download_and_cache_osm_roads(
  grid = grid,
  out_path = roads_path,
  osm_place = "South Korea",
  download_directory = "data/osm/raw",
  buffer_m = 250,
  force = force_osm
)

sampling_network <- construct_seoul_road_network(roads = roads, boundary = boundary)
ensure_dir(dirname(sampling_network_path))
st_write(sampling_network, sampling_network_path, delete_dsn = TRUE, quiet = TRUE)

message("Grid cells: ", format(nrow(grid), big.mark = ","))
message("Canonical road features: ", format(nrow(roads), big.mark = ","))
message("Sampling-network road features: ", format(nrow(sampling_network), big.mark = ","))
message(
  "Target points: ", format(target_count, big.mark = ","),
  "; candidate spacing: ", candidate_spacing_m, " m",
  "; minimum sample spacing: ", min_spacing_m, " m",
  "; seed: ", seed,
  "; candidate workers: ", candidate_workers,
  "; candidate chunk size: ", candidate_chunk_size
)

samples <- run_global_road_network_sampling(
  roads = sampling_network,
  grid = grid,
  boundary = NULL,
  final_parquet = final_parquet,
  candidate_spacing_m = candidate_spacing_m,
  min_spacing_m = min_spacing_m,
  target_count = target_count,
  seed = seed,
  candidate_workers = candidate_workers,
  candidate_chunk_size = candidate_chunk_size
)

summary <- summarise_samples(samples)
message("Candidate points: ", format(attr(samples, "candidate_count"), big.mark = ","))
message("Network road features: ", format(attr(samples, "network_road_count"), big.mark = ","))
message("Network length m: ", format(round(attr(samples, "network_length_m")), big.mark = ","))
print_sample_diagnostics(summary)

if (write_debug) {
  write_debug_outputs(samples = samples, output_dir = "data/sampling_global/debug")
}

make_leaflet_map(
  boundary = boundary,
  grid = grid,
  samples = samples,
  out_html = map_html,
  max_grid_cells = 5000,
  max_points = 30000,
  grid_simplify_tolerance_m = 1,
  boundary_simplify_tolerance_m = 5
)

message("Parquet written: ", final_parquet)
message("Leaflet map written: ", map_html)
