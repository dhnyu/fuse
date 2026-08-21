test_that("I14 contract fixes conservative dtypes, caps, and runtime", {
  config <- load_serialization_plan_config(serialization_plan_contract_paths(fuse_test_root))
  expect_identical(config$scientific$estimator$compression_assumption, "none")
  expect_identical(config$scientific$estimator$dtypes$edge_index$name, "int64")
  expect_equal(config$scientific$estimator$object_raster_dimension, 26)
  expect_identical(config$runtime$controller, "controller_05")
  expect_equal(config$runtime$workers, 1)
  expect_equal(config$runtime$gpu, 0)
})

test_that("geometry tuple accounting includes multipart and polygon holes", {
  outer <- matrix(c(0,0, 4,0, 4,4, 0,4, 0,0), ncol = 2, byrow = TRUE)
  hole <- matrix(c(1,1, 2,1, 2,2, 1,2, 1,1), ncol = 2, byrow = TRUE)
  polygon <- sf::st_polygon(list(outer, hole))
  multi <- sf::st_multipolygon(list(list(outer, hole), list(outer)))
  line <- sf::st_multilinestring(list(matrix(c(0,0, 1,1), ncol=2, byrow=TRUE), matrix(c(1,1, 2,2, 3,3), ncol=2, byrow=TRUE)))
  point <- sf::st_point(c(0, 0))
  expect_identical(serialization_geometry_shape(polygon), c(coordinate=10, component=1, ring=2, hole=1))
  expect_identical(serialization_geometry_shape(multi), c(coordinate=15, component=2, ring=3, hole=1))
  expect_identical(serialization_geometry_shape(line), c(coordinate=5, component=2, ring=0, hole=0))
  expect_identical(serialization_geometry_shape(point), c(coordinate=1, component=1, ring=0, hole=0))
  expect_error(serialization_geometry_shape(sf::st_geometrycollection(list(point))), "Unsupported")
})

serialization_fixture_resources <- function() {
  data.table::data.table(
    scene_id = sprintf("scene_%02d", 1:8),
    split = c(rep("training", 4), rep("validation", 2), rep("evaluation", 2)),
    node_count = c(10, 10, 50, 101, 10, 10, 10, 10),
    ordered_edge_count = c(0, 20, 100, 10, 10, 10, 10, 10),
    coordinate_count = c(10, 50, 10, 10, 10, 10, 10, 10),
    estimated_uncompressed_bytes = c(100, 100, 100, 100, 100, 100, 100, 100),
    empty_edge = c(TRUE, rep(FALSE, 7))
  )
}

test_that("packing is split-homogeneous, cap-aware, and shuffle invariant", {
  resources <- serialization_fixture_resources()
  caps <- c(node_count=100, ordered_edge_count=100, coordinate_count=100, estimated_uncompressed_bytes=200)
  limits <- as.list(c(node_count=1000, ordered_edge_count=1000, coordinate_count=1000, estimated_uncompressed_bytes=1000))
  bins <- serialization_pack_all(resources, caps, limits)
  assignment <- setNames(rep(seq_along(bins), lengths(bins)), unlist(lapply(bins, function(i) resources$scene_id[i])))
  shuffled <- resources[c(8,3,6,1,7,2,5,4)]
  bins2 <- serialization_pack_all(shuffled, caps, limits)
  assignment2 <- setNames(rep(seq_along(bins2), lengths(bins2)), unlist(lapply(bins2, function(i) shuffled$scene_id[i])))
  expect_identical(assignment[sort(names(assignment))], assignment2[sort(names(assignment2))])
  expect_true(any(vapply(bins, function(i) length(i) == 1L && resources$scene_id[i] == "scene_04", logical(1))))
  expect_true(all(vapply(bins, function(i) length(unique(resources$split[i])) == 1L, logical(1))))
})

test_that("tie break and exact cap boundary are deterministic", {
  resources <- data.table::data.table(scene_id=c("b","a","d","c"), split="training",
    node_count=50, ordered_edge_count=0, coordinate_count=0, estimated_uncompressed_bytes=50, empty_edge=TRUE)
  caps <- c(node_count=100, ordered_edge_count=100, coordinate_count=100, estimated_uncompressed_bytes=100)
  bins <- serialization_pack_split(resources, caps)
  expect_identical(lapply(bins, function(i) sort(resources$scene_id[i])), list(c("a","b"), c("c","d")))
  expect_true(all(vapply(bins, function(i) sum(resources$node_count[i]) == 100, logical(1))))
})

test_that("coverage QC catches duplicate, missing, and cross-split scenes", {
  resources <- serialization_fixture_resources()
  caps <- c(node_count=1000, ordered_edge_count=1000, coordinate_count=1000, estimated_uncompressed_bytes=1000)
  duplicate <- serialization_plan_qc(resources, list(c(1,1), 2:8), caps)
  expect_gt(duplicate$duplicate_scene_count, 0)
  missing <- serialization_plan_qc(resources, list(1:7), caps)
  expect_equal(missing$missing_scene_count, 1)
  cross <- serialization_plan_qc(resources, list(c(1,5), 2:4, 6, 7:8), caps)
  expect_equal(cross$cross_split_shard_count, 1)
})

test_that("checksum mismatch and feasibility overflow fail hard", {
  path <- tempfile()
  writeLines("content", path)
  record <- serialization_sha_record(path)
  record$sha256 <- paste(rep("0", 64), collapse="")
  expect_error(serialization_verify_record(record), "Checksum")
  resources <- serialization_fixture_resources()
  caps <- c(node_count=100, ordered_edge_count=100, coordinate_count=100, estimated_uncompressed_bytes=200)
  limits <- as.list(c(node_count=100, ordered_edge_count=1000, coordinate_count=1000, estimated_uncompressed_bytes=1000))
  expect_error(serialization_pack_all(resources, caps, limits), "feasibility")
})

test_that("immutable identical reuse passes and different content fails", {
  root <- tempfile()
  writer <- function(text) function(stage) writeLines(text, file.path(stage, "value.txt"), useBytes=TRUE)
  first <- publish_deterministic_directory(root, "value.txt", writer("same"))
  second <- publish_deterministic_directory(root, "value.txt", writer("same"))
  expect_identical(first, second)
  expect_error(publish_deterministic_directory(root, "value.txt", writer("different")), "non-deterministic")
})

test_that("I13 duplicate count columns require exact agreement and preserve zero", {
  stats <- data.table::data.table(node_count=c(NA,2), building_count=c(NA,1), road_count=c(NA,1), poi_count=c(NA,0),
    i.node_count=c(0,2), i.building_count=c(0,1), i.road_count=c(0,1), i.poi_count=c(0,0))
  value <- serialization_coalesce_i13_counts(stats)
  expect_identical(value$node_count, c(0,2))
  stats$node_count[[2]] <- 3
  expect_error(serialization_coalesce_i13_counts(stats), "disagree")
})
