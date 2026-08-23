raster_test_config <- function() load_raster_observation_config(raster_observation_contract_paths(fuse_test_root))

raster_test_grid <- function(values, nrows = 4L, ncols = 4L, extent = c(0, 20, 0, 20)) {
  value <- terra::rast(
    nrows = nrows, ncols = ncols, xmin = extent[[1L]], xmax = extent[[2L]],
    ymin = extent[[3L]], ymax = extent[[4L]], crs = "EPSG:5186"
  )
  terra::values(value) <- values
  value
}

raster_context_sf <- function(type, geometries) {
  count <- length(geometries)
  value <- sf::st_sf(
    scene_id = rep("scene", count), scene_footprint_id = rep("footprint", count),
    split = rep("training", count), entity_type = rep(type, count),
    source_entity_id = sprintf("%s-%02d", type, seq_len(count)), local_entity_id = seq_len(count) - 1L,
    geometry = sf::st_sfc(geometries, crs = 5186)
  )
  if (type == "B") value$observed_area_m2 <- as.numeric(sf::st_area(value))
  if (type == "R") value$observed_length_m <- as.numeric(sf::st_length(value))
  value
}

raster_square_polygon <- function(xmin, ymin, xmax, ymax) sf::st_polygon(list(matrix(c(
  xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax, xmin, ymin
), ncol = 2, byrow = TRUE)))

test_that("raster contract fixes scene grids, overlap summaries, and column roles", {
  config <- raster_test_config()
  expect_equal(as.integer(config$scientific$scene_level$landcover$grid_shape), c(100L, 100L))
  expect_equal(as.integer(config$scientific$scene_level$dem$grid_shape), c(17L, 17L))
  expect_equal(config$scientific$scene_level$landcover$class_count, 22)
  expect_equal(unlist(config$scientific$object_level$dem$statistics),
               c("overlap_weighted_mean_m", "overlap_weighted_population_sd_m"))
  expect_true("bbox" %in% unlist(config$scientific$vector_input_column_roles$geoparquet_auxiliary))
  expect_true("bbox" %in% unlist(config$scientific$vector_input_column_roles$explicitly_not_model_features))
  expect_equal(config$runtime$controller, "controller_40")
  expect_equal(config$runtime$branch_workers, 1)
  expect_equal(config$runtime$threads_per_worker, 1)
})

test_that("aligned and off-grid land-cover scenes preserve categorical area composition", {
  config <- raster_test_config()
  aligned <- raster_test_grid(rep(c(1, 2), each = 8L))
  scene <- list(xmin = 0, ymin = 0, xmax = 20, ymax = 20)
  config$scientific$scene_level$landcover$grid_shape <- list(4, 4)
  value <- scene_landcover_observation(aligned, scene, config)
  expect_equal(dim(value$composition), c(22, 4, 4))
  expect_equal(value$valid_support_ratio, matrix(1, 4, 4))
  expect_equal(apply(value$composition, c(2, 3), sum), matrix(1, 4, 4), tolerance = 1e-7)

  off_grid <- raster_test_grid(rep(c(1, 2, 1), 3), 3, 3, c(-2.5, 27.5, -2.5, 27.5))
  config$scientific$scene_level$landcover$grid_shape <- list(2, 2)
  mixed <- scene_landcover_observation(off_grid, list(xmin = 0, ymin = 0, xmax = 20, ymax = 20), config)
  reference <- reference_scene_overlap(off_grid, list(xmin = 0, ymin = 0, xmax = 20, ymax = 20), c(2, 2), "landcover")
  expect_equal(dim(mixed$composition), c(22, 2, 2))
  expect_true(any(mixed$composition[1, , ] > 0 & mixed$composition[2, , ] > 0))
  expect_equal(mixed$composition, reference$composition, tolerance = 1e-7)
  expect_equal(mixed$valid_support_ratio, reference$valid_support_ratio, tolerance = 1e-7)
  terra::values(off_grid)[1] <- 99
  expect_error(scene_landcover_observation(off_grid, list(xmin = 0, ymin = 0, xmax = 20, ymax = 20), config),
               "Unknown land-cover")
})

test_that("DEM scene grid uses area means, fixed orientation, and explicit validity", {
  config <- raster_test_config()
  config$scientific$scene_level$dem$grid_shape <- list(2, 2)
  dem <- raster_test_grid(10, 1, 1, c(0, 20, 0, 20))
  constant <- scene_dem_observation(dem, list(xmin = 0, ymin = 0, xmax = 20, ymax = 20), config)
  expect_equal(constant$value, matrix(10, 2, 2))
  expect_equal(constant$valid_support_ratio, matrix(1, 2, 2))

  gradient <- raster_test_grid(c(30, 40, 10, 20), 2, 2, c(0, 20, 0, 20))
  direct <- scene_dem_observation(gradient, list(xmin = 0, ymin = 0, xmax = 20, ymax = 20), config)
  reference <- reference_scene_overlap(gradient, list(xmin = 0, ymin = 0, xmax = 20, ymax = 20), c(2, 2), "dem")
  expect_equal(direct$value, matrix(c(30, 40, 10, 20), nrow = 2, byrow = TRUE))
  expect_equal(direct$value, reference$value, tolerance = 1e-7)
  terra::values(gradient)[1] <- NA
  partial <- scene_dem_observation(gradient, list(xmin = 0, ymin = 0, xmax = 20, ymax = 20), config)
  expect_false(partial$valid_mask[1, 1])
  expect_equal(partial$value[1, 1], config$scientific$scene_level$dem$invalid_value_fill)
})

test_that("polygon, hole, multipart, line, and point supports are exact", {
  config <- raster_test_config()
  lc <- raster_test_grid(c(1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2))
  polygon <- raster_square_polygon(1, 1, 9, 9)
  hole <- sf::st_polygon(list(
    matrix(c(1,1,19,1,19,19,1,19,1,1), ncol = 2, byrow = TRUE),
    matrix(c(5,5,15,5,15,15,5,15,5,5), ncol = 2, byrow = TRUE)
  ))
  multipart <- sf::st_multipolygon(list(
    list(matrix(c(1,1,2,1,2,2,1,2,1,1), ncol = 2, byrow = TRUE)),
    list(matrix(c(11,11,12,11,12,12,11,12,11,11), ncol = 2, byrow = TRUE))
  ))
  buildings <- raster_context_sf("B", list(polygon, hole, multipart))
  summary <- summarize_landcover_context(buildings, lc, "building", config)
  expect_equal(rowSums(summary$support), buildings$observed_area_m2, tolerance = 1e-4)
  expect_equal(rowSums(summary$fraction), rep(1, 3), tolerance = 1e-6)

  roads <- raster_context_sf("R", list(
    sf::st_linestring(matrix(c(0, 10, 20, 10), ncol = 2, byrow = TRUE)),
    sf::st_multilinestring(list(
      matrix(c(0, 2, 10, 2), ncol = 2, byrow = TRUE),
      matrix(c(10, 18, 20, 18), ncol = 2, byrow = TRUE)
    ))
  ))
  road_support <- geometry_cell_support(roads, lc, "road")
  expect_equal(road_support[, sum(weight), by = ID]$V1, roads$observed_length_m, tolerance = 1e-7)

  points <- raster_context_sf("P", list(sf::st_point(c(2, 2)), sf::st_point(c(5, 5)), sf::st_point(c(19, 19))))
  point_support <- geometry_cell_support(points, lc, "poi")
  expect_equal(point_support$weight, rep(1, 3))
  expect_equal(nrow(point_support), 3)
})

test_that("object DEM mean and population SD match a manual weighted result", {
  config <- raster_test_config()
  dem <- raster_test_grid(c(1, 3, 1, 3), 2, 2, c(0, 20, 0, 20))
  polygon <- raster_context_sf("B", list(raster_square_polygon(0, 0, 20, 20)))
  value <- summarize_dem_context(polygon, dem, "building", config)
  expect_equal(value$mean, 2, tolerance = 1e-10)
  expect_equal(value$sd, 1, tolerance = 1e-10)
  terra::values(dem) <- NA
  missing <- summarize_dem_context(polygon, dem, "building", config)
  expect_true(is.na(missing$mean))
  expect_true(is.na(missing$sd))
  expect_equal(missing$valid_ratio, 0)
})

test_that("Zarr v2 writer is byte deterministic and Python, GDAL, and R cross-readable", {
  skip_if_not(Sys.which("python") != "")
  skip_if_not(Sys.which("gdalmdiminfo") != "")
  config <- raster_test_config()
  value <- array(as.numeric(1:24), dim = c(2, 3, 4))
  first <- tempfile(pattern = "first-", fileext = ".zarr")
  second <- tempfile(pattern = "second-", fileext = ".zarr")
  one <- write_zarr_store(list(values = list(value = value, dtype = "float32", fill_value = -1)),
                          first, list(schema_version = "1.0.0"), config)
  two <- write_zarr_store(list(values = list(value = value, dtype = "float32", fill_value = -1)),
                          second, list(schema_version = "1.0.0"), config)
  first_hashes <- vapply(file_member_records(first), `[[`, character(1L), "sha256")
  second_hashes <- vapply(file_member_records(second), `[[`, character(1L), "sha256")
  expect_identical(unname(first_hashes), unname(second_hashes))
  expect_null(names(file_member_records(first)))
  expect_equal(one$zarr_format, 2)
  expect_true(one$consolidated_metadata)
  expect_equal(one$arrays[[1L]]$shape, list(2, 3, 4))
  expect_s3_class(stars::read_mdim(first), "stars")
  info <- system2("gdalmdiminfo", first, stdout = TRUE, stderr = TRUE)
  expect_true(any(grepl('"values"', info, fixed = TRUE)))
})
