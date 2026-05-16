suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
  library(arrow)
  library(future)
  library(future.mirai)
})

source("R/road_environment_sampling.R")

sf_use_s2(FALSE)

grid_path <- "data/grid_1km/seoul_grid_1km.gpkg"
boundary_path <- "data/geodata/seoul_boundary.gpkg"
roads_path <- "data/osm/seoul_roads_filtered.gpkg"
chunk_dir <- "data/sampling_1km/chunks"
final_parquet <- "data/sampling_1km/seoul_road_environment_samples_1km.parquet"
map_html <- "data/sampling_1km/seoul_road_environment_sampling_1km_map.html"

workers <- as.integer(Sys.getenv("SEOUL_SAMPLE_WORKERS", "12"))
chunk_size <- as.integer(Sys.getenv("SEOUL_SAMPLE_CHUNK_SIZE", "200"))
n_samples <- as.integer(Sys.getenv("SEOUL_SAMPLES_PER_GRID", "10"))
force_grid <- identical(tolower(Sys.getenv("SEOUL_FORCE_GRID", "false")), "true")
force_osm <- identical(tolower(Sys.getenv("SEOUL_FORCE_OSM", "false")), "true")
write_debug <- identical(tolower(Sys.getenv("SEOUL_WRITE_DEBUG_GPKG", "true")), "true")

grid <- build_seoul_grid(
  cell_size_m = 1000,
  boundary_path = boundary_path,
  grid_path = grid_path,
  map_path = "data/grid_1km/seoul_grid_1km_map.png",
  force = force_grid
)

boundary <- read_sf_projected(boundary_path)

roads <- download_and_cache_osm_roads(
  grid = grid,
  out_path = roads_path,
  osm_place = "South Korea",
  download_directory = "data/osm/osmextract_downloads",
  buffer_m = 250,
  force = force_osm
)

message("Grid cells: ", format(nrow(grid), big.mark = ","))
message("Filtered road features: ", format(nrow(roads), big.mark = ","))
message("Workers: ", workers, "; chunk size: ", chunk_size, "; samples per grid: ", n_samples)

samples <- run_chunked_sampling(
  grid_path = grid_path,
  roads_path = roads_path,
  output_dir = chunk_dir,
  final_parquet = final_parquet,
  grid_layer = "seoul_grid_1km",
  chunk_size = chunk_size,
  workers = workers,
  n_samples = n_samples,
  seed_base = 100000L
)

summary <- summarise_samples(samples)
message("Rows written: ", format(summary$rows, big.mark = ","))
message("Grids covered: ", format(summary$grids, big.mark = ","))
message("Sampled points: ", format(summary$sampled_points, big.mark = ","))
message("Missing point rows: ", format(summary$missing_points, big.mark = ","))

if (write_debug) {
  write_debug_outputs(samples = samples, roads = roads, output_dir = "data/sampling_1km/debug")
}

make_leaflet_map(
  boundary = boundary,
  grid = grid,
  roads = roads,
  samples = samples,
  out_html = map_html,
  max_grid_cells = 1200,
  max_roads = 20000,
  max_points = 10000,
  road_simplify_tolerance_m = 10,
  grid_simplify_tolerance_m = 1,
  boundary_simplify_tolerance_m = 5
)

message("Parquet written: ", final_parquet)
message("Leaflet map written: ", map_html)
