test_that("current off-grid publisher is deterministic on a disposable fixture", {
  boundary <- sf::st_sf(geometry = sf::st_sfc(sf::st_polygon(list(matrix(
    c(0, 0, 100, 0, 100, 100, 0, 100, 0, 0), ncol = 2, byrow = TRUE
  ))), crs = 5186))
  training <- data.frame(center_x_5186 = 50, center_y_5186 = 50)
  settings <- list(total_count = 20L, validation_count = 5L, evaluation_count = 15L,
    minimum_training_center_distance_m = 5, candidate_batch_size = 32L,
    split_seed = 26082501L, sampling_algorithm_version = "fixture-v1",
    rng_kind = "Mersenne-Twister", normal_kind = "Inversion", sample_kind = "Rejection", rng_version = "4.0.0")
  first <- build_current_off_grid_table(boundary, training, settings)
  second <- build_current_off_grid_table(boundary, training, settings)
  expect_identical(first$data, second$data)
  expect_identical(off_grid_content_checksum(first$data), off_grid_content_checksum(second$data))
  expect_identical(as.character(first$data$split), c(rep("validation", 5), rep("evaluation", 15)))
  expect_equal(anyDuplicated(first$data$center_id), 0L)
  expect_equal(anyDuplicated(first$data[, c("x", "y")]), 0L)
  expect_error(validate_current_off_grid_table(first$data[-1, ], boundary, training, settings), "row_count")
})

test_that("P1 accepts the current P0 training-center rule without a realized count", {
  root <- tempfile("p1-authority-")
  dir.create(root, recursive = TRUE)
  on.exit(unlink(root, recursive = TRUE), add = TRUE)

  authority <- list(
    authority_id = "mta_current", overall_status = "PASS", source_set_id = "mss_current"
  )
  canonical <- list(
    crs_epsg = 5186L,
    scene_width_m = 500L,
    scene_height_m = 500L,
    observation_window = "Seoul_boundary_centered",
    source_coverage_buffer_m = 400L,
    training_center_source = "official_500m_grid_centers",
    validation_scene_count = 1000L,
    evaluation_scene_count = 9000L,
    total_off_grid_scene_count = 10000L,
    off_grid_minimum_distance_m = 50L,
    intermediate_training_centers = FALSE,
    training_sliding_stride_m = NULL,
    field_origins = list(train_grid = "official_500m_grid_centers_inside_Seoul")
  )
  expect_false("training_scene_count" %in% names(canonical))
  expect_false(identical(as.integer(canonical$training_scene_count), 2421L))
  scene <- list(status = "PASS", source_set_id = "mss_current", canonical_contract = canonical)
  authority_path <- write_json_file(authority, file.path(root, "reduced_methodology_authority.json"))
  scene_path <- write_json_file(scene, file.path(root, "scene_methodology_contract.json"))
  spec <- list(config = list(
    authority = list(expected_id = "mta_current", expected_manifest_sha256 = sha256_file(authority_path)),
    scene = list(processing_epsg = 5186L, width_m = 500L, height_m = 500L,
                 split_counts = list(training = 2421L, validation = 1000L, evaluation = 9000L))
  ))

  expect_no_error(p1_read_authority(authority_path, scene_path, spec))

  canonical$training_scene_count <- 999L
  scene$canonical_contract <- canonical
  historical_dir <- file.path(root, "historical-count")
  dir.create(historical_dir)
  historical_path <- write_json_file(scene, file.path(historical_dir, "scene_methodology_contract.json"))
  expect_no_error(p1_read_authority(authority_path, historical_path, spec))

  reject <- function(field, value) {
    changed <- canonical
    changed[[field]] <- value
    scene$canonical_contract <- changed
    changed_dir <- tempfile("scene-contract-", tmpdir = root)
    dir.create(changed_dir)
    path <- write_json_file(scene, file.path(changed_dir, "scene_methodology_contract.json"))
    expect_error(p1_read_authority(authority_path, path, spec), "differs from P1")
  }
  reject("training_center_source", "derived_250m_lattice")
  reject("intermediate_training_centers", TRUE)
  reject("training_sliding_stride_m", 250L)
  reject("crs_epsg", 5179L)
  reject("scene_width_m", 499L)
  reject("scene_height_m", 501L)
  reject("validation_scene_count", 999L)
  reject("evaluation_scene_count", 9001L)
  reject("off_grid_minimum_distance_m", 49L)
})

test_that("realized official-grid count remains independently fail-closed", {
  expect_silent(p1_require_official_training_count(data.frame(id = seq_len(2421L))))
  expect_error(p1_require_official_training_count(data.frame(id = seq_len(2420L))), "not 2,421")
  expect_error(p1_require_official_training_count(data.frame(id = seq_len(2422L))), "not 2,421")
})

test_that("scene identity is stable and split/source-specific", {
  first <- p1_scene_identity("mta_test", c("training", "validation"), c("official_500m_grid", "accepted_off_grid"), c("A", "A"))
  second <- p1_scene_identity("mta_test", c("training", "validation"), c("official_500m_grid", "accepted_off_grid"), c("A", "A"))
  expect_identical(first, second)
  expect_equal(anyDuplicated(first$scene_id), 0L)
  expect_match(first$scene_id, "^scn_[0-9a-f]{24}$")
})

test_that("off-grid threshold is strict at 50 metres", {
  expect_equal(p1_offgrid_distance_violations(c(49.999, 50.000)), 1L)
  expect_equal(p1_offgrid_distance_violations(50.000), 0L)
  expect_equal(p1_offgrid_distance_violations(c(50, Inf)), 1L)
})

test_that("count, EPSG, bounds, duplicate, and training-source drift are rejected", {
  split <- c(rep("training", 2421), rep("validation", 1000), rep("evaluation", 9000))
  expect_equal(p1_split_count_violations(split), 0L)
  expect_equal(p1_split_count_violations(split[-1]), 1L)
  expect_equal(p1_epsg_violations(c(5186L, 5179L, NA_integer_)), 2L)
  bounds <- data.frame(xmin = c(0, 0), xmax = c(500, 499.999), ymin = c(0, 0), ymax = c(500, 500))
  expect_equal(p1_bounds_violations(bounds), 1L)
  expect_equal(p1_duplicate_identity_violations(c("validation", "validation"), c("A", "A")), 1L)
  expect_equal(p1_training_source_violations(c("training", "training"), c("official_500m_grid", "derived_250m")), 1L)
})

test_that("Seoul-center, source-coverage, and plan linkage failures are explicit", {
  area <- sf::st_sf(geometry = sf::st_sfc(sf::st_polygon(list(matrix(c(0,0, 10,0, 10,10, 0,10, 0,0), ncol=2, byrow=TRUE))), crs=5186))
  points <- sf::st_as_sf(data.frame(x = c(5, 11), y = c(5, 5)), coords = c("x", "y"), crs = 5186)
  expect_equal(p1_coverage_violations(points, area), 1L)
  data <- data.frame(scene_plan_id = c("plan", "wrong"), methodology_authority_id = c("authority", "authority"))
  plan <- list(plan_id = "plan", methodology_authority_id = "authority")
  expect_equal(p1_plan_link_violations(data, plan)$plan_fingerprint, 1L)
  data$methodology_authority_id[[2]] <- "wrong"
  expect_equal(p1_plan_link_violations(data, plan)$authority_id, 1L)
})

test_that("500 m bounds and interior overlap are checked", {
  nonoverlap <- sf::st_sf(id = 1:2, geometry = square_footprints(c(0, 500), c(0, 0), 500), crs = 5186)
  overlap <- sf::st_sf(id = 1:2, geometry = square_footprints(c(0, 499.999), c(0, 0), 500), crs = 5186)
  expect_equal(p1_training_overlap_count(nonoverlap), 0L)
  expect_equal(p1_training_overlap_count(overlap), 1L)
  expect_equal(unname(diff(sf::st_bbox(nonoverlap$geometry[[1]])[c("xmin", "xmax")])), 500)
})

test_that("official-grid derivation rejects intermediate and 250 m identities by construction", {
  config <- load_research_config(research_config_paths(fuse_test_root))
  boundary <- sf::st_read(config$paths$inputs$boundary, "research_area", quiet = TRUE)
  contract <- list(crs = list(official_grid_epsg = 5179L, processing_epsg = 5186L),
                   scene = list(official_cell_id_column = "SPO_NO_CD", coordinate_precision_m = 0.001))
  result <- derive_official_training_scenes(boundary, config$paths$inputs$official_grid_shp, contract)$data
  expect_equal(nrow(result), 2421L)
  expect_equal(anyDuplicated(result$official_grid_id), 0L)
})

test_that("P1 scientific hashes exclude environment-specific execution fields", {
  scientific <- list(authority = "mta", scene = c("a", "b"), schema = "1.0.0")
  first <- p0_scientific_sha256(scientific)
  second <- p0_scientific_sha256(scientific)
  execution_a <- list(path = "/host/a", workers = 1L)
  execution_b <- list(path = "/host/b", workers = 99L)
  expect_identical(first, second)
  expect_false(identical(p0_scientific_sha256(c(scientific, execution_a)), p0_scientific_sha256(c(scientific, execution_b))))
})

test_that("P1 immutable publication accepts identity and blocks collision", {
  root <- tempfile("p1-immutable-")
  on.exit(unlink(root, recursive = TRUE), add = TRUE)
  writer <- function(text) function(stage) writeLines(text, file.path(stage, "value.txt"), useBytes = TRUE)
  first <- p1_publish_immutable_bundle(root, "value.txt", writer("same"))
  second <- p1_publish_immutable_bundle(root, "value.txt", writer("same"))
  expect_identical(first, second)
  expect_error(p1_publish_immutable_bundle(root, "value.txt", writer("different")), "collision")
})

test_that("active P1 graph publishes current off-grid input without historical fallback", {
  text <- paste(readLines(file.path(fuse_test_root, "targets/s01_scene_index.R")), collapse = "\n")
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p1_scene_index.yml"))
  expect_match(text, "s01_offgrid_scene_source", fixed = TRUE)
  expect_match(text, "publish_current_off_grid_source", fixed = TRUE)
  expect_false(grepl("i01_offgrid_scene_sources|verify_accepted_off_grid_source", text))
  expect_identical(as.integer(unlist(config$off_grid_source[c("total_count", "validation_count", "evaluation_count")])), c(10000L, 1000L, 9000L))
  expect_false(any(grepl("/scene_data/v1/", unlist(config), fixed = TRUE)))
})
