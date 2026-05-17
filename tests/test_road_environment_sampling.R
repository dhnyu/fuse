suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
  library(arrow)
})

source("R/road_environment_sampling.R")

sf_use_s2(FALSE)

expect_true <- function(x, msg) {
  if (!isTRUE(x)) {
    stop(msg, call. = FALSE)
  }
}

grid <- st_make_grid(
  st_as_sfc(st_bbox(c(xmin = 0, ymin = 0, xmax = 1000, ymax = 1000), crs = PROJECTED_CRS)),
  cellsize = 500
) %>%
  st_sf(grid_id = seq_along(.), geometry = .)

roads <- st_sfc(
  st_linestring(matrix(c(0, 100, 1000, 100), ncol = 2, byrow = TRUE)),
  st_linestring(matrix(c(0, 250, 1000, 250), ncol = 2, byrow = TRUE)),
  st_linestring(matrix(c(0, 400, 1000, 400), ncol = 2, byrow = TRUE)),
  st_linestring(matrix(c(0, 700, 1000, 700), ncol = 2, byrow = TRUE)),
  crs = PROJECTED_CRS
) %>%
  st_sf(
    source_road_id = 1:4,
    highway_class = c("primary", "residential", "residential", "service"),
    sampled_rank = c(3L, 6L, 6L, 7L),
    geometry = .
  )

network <- construct_seoul_road_network(roads)
candidates <- generate_road_candidates(network, spacing_m = 25)
thin_a <- poisson_disk_thin_candidates(candidates, min_spacing_m = 100, target_count = 20, seed = 123)
thin_b <- poisson_disk_thin_candidates(candidates, min_spacing_m = 100, target_count = 20, seed = 123)
samples <- assign_samples_to_grid(thin_a, grid)

expect_true(nrow(network) == 4L, "The constructed road network should preserve test road features.")
expect_true(nrow(candidates) == 160L, "Regular 25 m candidates on four 1 km roads should yield 160 candidates.")
expect_true(nrow(thin_a) <= 20L, "Thinning should respect the requested target count.")
expect_true(identical(thin_a, thin_b), "Poisson-style thinning should be deterministic for the same seed.")
expect_true(identical(names(samples), sample_output_columns), "Unexpected output schema.")
expect_true(all(samples$point_id == seq_len(nrow(samples))), "point_id should be sequential after thinning.")
expect_true(all(!is.na(samples$grid_id)), "All test points should be assigned to a 500 m grid.")
expect_true(all(!is.na(samples$lon) & !is.na(samples$lat)), "Samples should have lon/lat coordinates.")

sample_points <- samples %>%
  st_as_sf(coords = c("lon", "lat"), crs = LONLAT_CRS, remove = FALSE) %>%
  st_transform(PROJECTED_CRS)

dist_matrix <- st_distance(sample_points)
diag(dist_matrix) <- units::set_units(Inf, "m")
expect_true(
  min(as.numeric(dist_matrix)) >= 100 - 1e-7,
  "Accepted sample points should honor the minimum Euclidean spacing."
)

tmp_dir <- tempfile("road_env_test_")
dir.create(tmp_dir)
parquet_path <- file.path(tmp_dir, "samples.parquet")

pipeline_samples <- run_global_road_network_sampling(
  roads = roads,
  grid = grid,
  boundary = NULL,
  final_parquet = parquet_path,
  candidate_spacing_m = 25,
  min_spacing_m = 100,
  target_count = 20,
  seed = 123,
  candidate_workers = 2,
  candidate_chunk_size = 2
)

summary <- summarise_samples(pipeline_samples)

expect_true(file.exists(parquet_path), "Final parquet was not written.")
expect_true(parquet_has_schema(parquet_path), "Final parquet schema check failed.")
expect_true(summary$sampled_points == nrow(pipeline_samples), "Diagnostics should count sampled points.")
expect_true(nrow(summary$class_proportions) >= 2L, "Diagnostics should include highway class proportions.")

message("All road environment sampling tests passed.")
