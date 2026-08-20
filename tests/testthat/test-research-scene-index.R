test_that("research configuration fixes the approved scene methodology", {
  files <- research_config_paths(fuse_test_root)
  config <- load_research_config(files)
  expect_equal(config$scene$crs$processing_epsg, 5186)
  expect_equal(config$scene$crs$official_grid_epsg, 5179)
  expect_equal(config$scene$scene$width_m, 500)
  expect_equal(config$scene$scene$training_stride_m, 250)
  expect_equal(config$scene$off_lattice$validation_count, 1000)
  expect_equal(config$scene$off_lattice$evaluation_count, 2000)
  expect_equal(config$scene$off_lattice$minimum_training_center_distance_m, 50)
  expect_equal(config$scene$retrieval$query_count, 10)
  expect_equal(config$scene$retrieval$unrestricted_candidate_count, 1999)
  expect_true(config$scene$retrieval$include_other_queries)
})

test_that("study_data_inputs tracks 12 non-empty files without maintenance dependency", {
  files <- study_input_files(research_config_paths(fuse_test_root))
  expect_length(files, 12L)
  expect_named(files, names(yaml::read_yaml(file.path(fuse_test_root, "config/research_paths.yml"))$inputs))
  expect_true(all(file.exists(files)))
  expect_true(all(file.info(files)$size > 0))
})

test_that("scene and footprint identifiers are deterministic and order-independent", {
  split <- c("training", "evaluation", "validation")
  x <- c(200000.125, 200500.25, 201000.375)
  y <- c(550000.125, 550500.25, 551000.375)
  first <- deterministic_scene_ids(split, x, y, "1.0.0", 0.001)
  order <- c(3L, 1L, 2L)
  second <- deterministic_scene_ids(split[order], x[order], y[order], "1.0.0", 0.001)
  expect_identical(first[order], second)
  footprint <- deterministic_footprint_ids(x - 250, y - 250, x + 250, y + 250, "1.0.0", 0.001)
  expect_length(unique(footprint), 3L)
  expect_match(first, "^scn_[0-9a-f]{24}$")
  expect_match(footprint, "^fpt_[0-9a-f]{24}$")
})

test_that("500 m square footprints are valid and exact", {
  geometry <- square_footprints(c(0, 500), c(0, 500), 500, crs = 5186)
  expect_true(all(sf::st_is_valid(geometry)))
  expect_equal(as.numeric(sf::st_area(geometry)), c(250000, 250000))
  expect_equal(as.numeric(sf::st_bbox(geometry[[1L]])), c(-250, -250, 250, 250))
})

test_that("official-grid-derived lattice preserves native 250 m alignment", {
  config <- load_research_config(research_config_paths(fuse_test_root))
  boundary <- sf::st_read(config$paths$inputs$boundary, "research_area", quiet = TRUE)
  contract <- list(
    crs = list(official_grid_epsg = 5179L, processing_epsg = 5186L),
    scene = list(training_stride_m = 250, coordinate_precision_m = 0.001)
  )
  lattice <- derive_training_lattice(boundary, config$paths$inputs$official_grid_shp, contract)
  expect_gt(nrow(lattice$data), 9000L)
  expect_equal(lattice$phase_x_m, 250)
  expect_equal(lattice$phase_y_m, 250)
  expect_true(all(abs(lattice$data$center_x_native / 250 - round(lattice$data$center_x_native / 250)) < 1e-8))
  expect_true(all(abs(lattice$data$center_y_native / 250 - round(lattice$data$center_y_native / 250)) < 1e-8))
})

test_that("balanced prototype selection is deterministic and covers strata", {
  fixture <- data.frame(
    scene_id = sprintf("scene-%03d", 1:48),
    selection_strata = rep(c("low|interior|building", "middle|interior|road", "tail|boundary_near|poi"), each = 16)
  )
  first <- balanced_stratified_indices(fixture, 12L, 42L)
  second <- balanced_stratified_indices(fixture, 12L, 42L)
  expect_identical(first, second)
  expect_setequal(unique(fixture$selection_strata[first]), unique(fixture$selection_strata))
})

test_that("methodology contract schema rejects fixed-value drift", {
  contract <- list(
    contract_schema_version = "1.0.0", contract_id = "mth_123", scientific_hash = "hash",
    input_contract = list(), crs = list(processing_epsg = 5186, official_grid_epsg = 5179),
    scene = list(width_m = 500, training_stride_m = 250),
    off_lattice = list(validation_count = 1000, evaluation_count = 2000),
    retrieval = list(query_count = 10, unrestricted_candidate_count = 1999),
    randomness = list(), identifiers = list(), modes = list(), implementation = list()
  )
  expect_true(validate_methodology_contract_list(contract))
  contract$scene$width_m <- 400
  expect_error(validate_methodology_contract_list(contract), "fixed-value mismatch")
})
