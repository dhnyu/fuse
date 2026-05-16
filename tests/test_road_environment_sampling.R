suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
})

source("R/road_environment_sampling.R")

sf_use_s2(FALSE)

expect_true <- function(x, msg) {
  if (!isTRUE(x)) {
    stop(msg, call. = FALSE)
  }
}

cell <- st_as_sfc(st_bbox(c(xmin = 0, ymin = 0, xmax = 1000, ymax = 1000), crs = PROJECTED_CRS)) %>%
  st_sf(grid_id = 7L, geometry = .)

roads <- st_sfc(
  st_linestring(matrix(c(0, 100, 1000, 100), ncol = 2, byrow = TRUE)),
  st_linestring(matrix(c(0, 200, 1000, 200), ncol = 2, byrow = TRUE)),
  st_linestring(matrix(c(0, 300, 500, 300), ncol = 2, byrow = TRUE)),
  crs = PROJECTED_CRS
) %>%
  st_sf(
    highway_class = c("primary", "residential", "residential"),
    sampled_rank = c(3L, 6L, 6L),
    geometry = .
  )

sample_a <- process_one_grid_probabilistic(cell, roads, n_samples = 10L, seed_base = 100000L)
sample_b <- process_one_grid_probabilistic(cell, roads, n_samples = 10L, seed_base = 100000L)

expect_true(nrow(sample_a) == 10L, "A road grid must return exactly 10 sample rows.")
expect_true(identical(names(sample_a), sample_output_columns), "Unexpected output schema.")
expect_true(all(sample_a$sample_id == seq_len(10)), "sample_id should run from 1 to 10 per grid.")
expect_true(all(sample_a$class_proportion >= 0 & sample_a$class_proportion <= 1), "Class proportions are not bounded.")
expect_true(abs(unique(sample_a$total_road_length_m)[[1]] - 2500) < 1e-9, "Unexpected total clipped length.")
expect_true(all(sample_a$class_length_m[sample_a$highway_class == "primary"] == 1000), "Primary class length is wrong.")
expect_true(all(sample_a$class_length_m[sample_a$highway_class == "residential"] == 1500), "Residential class length is wrong.")
expect_true(all(!is.na(sample_a$lon) & !is.na(sample_a$lat)), "Road samples should have coordinates.")
expect_true(identical(sample_a, sample_b), "Sampling should be deterministic for the same seed/grid.")

empty <- process_one_grid_probabilistic(cell, roads[0, ], n_samples = 10L, seed_base = 100000L)
expect_true(nrow(empty) == 10L, "A no-road grid must still return exactly 10 rows.")
expect_true(all(empty$sample_id == seq_len(10)), "No-road sample_id should run from 1 to 10.")
expect_true(all(is.na(empty$highway_class)), "No-road grid should have NA highway_class.")
expect_true(all(empty$total_road_length_m == 0), "No-road total length should be zero.")

tmp_dir <- tempfile("road_env_test_")
dir.create(tmp_dir)
grid_path <- file.path(tmp_dir, "seoul_grid_1km.gpkg")
roads_path <- file.path(tmp_dir, "roads.gpkg")
chunk_path <- file.path(tmp_dir, "chunk.parquet")

st_write(cell, grid_path, layer = "seoul_grid_1km", quiet = TRUE)
st_write(roads, roads_path, quiet = TRUE)

chunk_result <- process_grid_chunk(
  grid_ids = 7L,
  grid_path = grid_path,
  roads_path = roads_path,
  out_path = chunk_path,
  grid_layer = "seoul_grid_1km",
  n_samples = 10L,
  seed_base = 100000L
)

expect_true(file.exists(chunk_path), "Chunk parquet was not written.")
expect_true(nrow(chunk_result) == 10L, "Chunk processor should return 10 rows per grid.")
expect_true(parquet_has_schema(chunk_path), "Chunk parquet schema check failed.")

message("All road environment sampling tests passed.")
