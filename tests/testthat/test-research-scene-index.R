test_that("reduced P1 configuration fixes the approved scene population", {
  spec <- load_p1_scene_index_spec(p1_scene_index_contract_paths(fuse_test_root), fuse_test_root)
  expect_equal(spec$config$scene$processing_epsg, 5186)
  expect_equal(spec$config$scene$width_m, 500)
  expect_equal(unlist(spec$config$scene$split_counts), c(training = 2421, validation = 400, evaluation = 1600))
  expect_equal(spec$config$scene$total_count, 4421)
  expect_equal(spec$config$off_grid_source$split_seed, 26082501)
  expect_match(spec$config$off_grid_source$split_algorithm, "first_400_validation")
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

test_that("official grid canonicalization yields the 2421 approved training centers", {
  config <- load_research_config(research_config_paths(fuse_test_root))
  boundary <- sf::st_read(config$paths$inputs$boundary, "research_area", quiet = TRUE)
  contract <- list(
    crs = list(official_grid_epsg = 5179L, processing_epsg = 5186L),
    scene = list(official_cell_id_column = "SPO_NO_CD", coordinate_precision_m = 0.001)
  )
  result <- derive_official_training_scenes(boundary, config$paths$inputs$official_grid_shp, contract)
  expect_equal(nrow(result$data), 2421L)
  expect_equal(anyDuplicated(result$data$official_grid_id), 0L)
  expect_gt(result$dedup$identical_duplicate_rows_removed, 0L)
})

test_that("official duplicate IDs with different geometry fail hard", {
  geometry <- sf::st_sfc(
    sf::st_point(c(0, 0)), sf::st_point(c(1, 0)), sf::st_point(c(2, 0)), crs = 5179
  )
  fixture <- sf::st_sf(SPO_NO_CD = c("A", "A", "B"), geometry = geometry)
  expect_error(canonicalize_official_grid(fixture, "SPO_NO_CD"), "different center or geometry")
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

test_that("legacy 300/700 methodology is not the active P1 contract", {
  active <- yaml::read_yaml(file.path(fuse_test_root, "config/p1_scene_index.yml"))
  expect_false(300 %in% unlist(active$scene$split_counts))
  expect_false(700 %in% unlist(active$scene$split_counts))
  expect_false(any(grepl("250", unlist(active$scene), fixed = TRUE)))
})
