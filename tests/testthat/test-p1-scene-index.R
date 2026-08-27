test_that("approved off-grid split is deterministic, without replacement, and disjoint", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p1_scene_index.yml"))
  source <- arrow::read_parquet(config$off_grid_source$parquet$path, as_data_frame = TRUE)
  ordered <- source[order(source$off_grid_order), ]
  expect_equal(nrow(ordered), 2000L)
  expect_identical(as.integer(ordered$off_grid_order), 1:2000)
  expect_identical(as.character(ordered$split), c(rep("validation", 400), rep("evaluation", 1600)))
  expect_equal(anyDuplicated(ordered$center_id), 0L)
  expect_length(intersect(ordered$center_id[ordered$split == "validation"], ordered$center_id[ordered$split == "evaluation"]), 0L)
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
  split <- c(rep("training", 2421), rep("validation", 400), rep("evaluation", 1600))
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

test_that("prototype selection uses only P1 scene-index fields and is deterministic", {
  fixture <- data.frame(scene_id = sprintf("scene-%03d", 1:96),
                        selection_strata = rep(c("boundary|west|grid", "interior|east|grid"), each = 48))
  first <- balanced_stratified_indices(fixture, 32L, 20260824L)
  second <- balanced_stratified_indices(fixture, 32L, 20260824L)
  expect_identical(first, second)
  body <- paste(deparse(body(p1_index_strata)), collapse = " ")
  expect_false(grepl("membership|relation|observation", body))
})

test_that("actual accepted inputs satisfy P1 source-level contracts", {
  p1 <- yaml::read_yaml(file.path(fuse_test_root, "config/p1_scene_index.yml"))
  paths <- yaml::read_yaml(file.path(fuse_test_root, "config/research_paths.yml"))
  source <- arrow::read_parquet(p1$off_grid_source$parquet$path, as_data_frame = TRUE)
  boundary <- sf::st_read(paths$inputs$boundary, paths$layers$boundary, quiet = TRUE)
  contract <- list(crs = list(official_grid_epsg = 5179L, processing_epsg = 5186L),
                   scene = list(official_cell_id_column = "SPO_NO_CD", coordinate_precision_m = 0.001))
  training <- derive_official_training_scenes(boundary, paths$inputs$official_grid_shp, contract)$data
  check <- validate_accepted_off_grid_table(source, boundary, as.matrix(training[, c("center_x_5186", "center_y_5186")]), 50)
  expect_equal(nrow(training), 2421L)
  expect_equal(nrow(check$ordered), 2000L)
  expect_gte(check$minimum, 50)
})
