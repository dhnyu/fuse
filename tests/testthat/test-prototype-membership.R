membership_test_spec <- function(scene_ids = c("scene-a", "scene-b")) {
  records <- list(
    list(scene_id = scene_ids[[1L]], scene_footprint_id = "foot-a", split = "training", xmin = 0, ymin = 0, xmax = 10, ymax = 10),
    list(scene_id = scene_ids[[2L]], scene_footprint_id = "foot-b", split = "training", xmin = 10, ymin = 0, xmax = 20, ymax = 10)
  )
  list(
    branch_id = "pmb_000000000000000000000000", prototype_id = "pro_000000000000000000000000",
    scene_index_id = "idx_000000000000000000000000", scene_ids = scene_ids, scenes = records,
    membership_contract = list(version = "1.0.0"),
    sources = list(
      building = list(entity_type = "B", layer = "buildings", source_artifact_id = "src-b"),
      road = list(entity_type = "R", layer = "links", source_artifact_id = "src-r"),
      poi = list(entity_type = "P", layer = "points", source_artifact_id = "src-p")
    )
  )
}

membership_test_sf <- function(ids, geometries) {
  sf::st_sf(source_entity_id = ids, geometry = sf::st_sfc(geometries, crs = 5186))
}

test_that("membership contract fixes positive-measure and closed-point predicates", {
  config <- load_membership_config(membership_contract_paths(fuse_test_root))
  expect_equal(config$scientific$predicates$building$rule, "positive_area_intersection")
  expect_equal(config$scientific$predicates$road$rule, "positive_length_intersection")
  expect_equal(config$scientific$predicates$poi$rule, "covered_by_closed_scene_footprint")
  expect_equal(config$scientific$predicates$building$measure_tolerance, 0)
  expect_equal(config$scientific$predicates$road$measure_tolerance, 0)
  expect_equal(config$runtime$controller, "controller_20")
  expect_equal(config$runtime$branch_workers, 1)
  expect_equal(config$runtime$threads_per_worker, 1)
})

test_that("building membership handles crossing, holes, multipart, and boundary touches", {
  spec <- membership_test_spec()
  scenes <- membership_scene_sf(spec)
  polygon <- function(xmin, ymin, xmax, ymax) sf::st_polygon(list(matrix(c(
    xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax, xmin, ymin
  ), ncol = 2, byrow = TRUE)))
  hole <- sf::st_polygon(list(
    matrix(c(1,1,9,1,9,9,1,9,1,1), ncol = 2, byrow = TRUE),
    matrix(c(3,3,7,3,7,7,3,7,3,3), ncol = 2, byrow = TRUE)
  ))
  multipart <- sf::st_multipolygon(list(
    list(matrix(c(2,2,3,2,3,3,2,3,2,2), ncol = 2, byrow = TRUE)),
    list(matrix(c(12,2,13,2,13,3,12,3,12,2), ncol = 2, byrow = TRUE))
  ))
  entities <- membership_test_sf(
    c("inside", "cross", "edge-line", "edge-point", "hole", "multipart"),
    list(polygon(1,1,2,2), polygon(9,2,11,4), polygon(-2,10,2,11),
         polygon(-1,10,0,11), hole, multipart)
  )
  result <- exact_membership_pairs(scenes, entities, "building", spec)
  expect_true(all(c("inside", "cross", "hole", "multipart") %in% result$source_entity_id))
  expect_false(any(c("edge-line", "edge-point") %in% result$source_entity_id))
  expect_equal(sum(result$source_entity_id == "cross"), 2L)
  expect_equal(sum(result$source_entity_id == "multipart"), 2L)
})

test_that("road membership handles crossing, multipart, and endpoint-only contact", {
  spec <- membership_test_spec()
  scenes <- membership_scene_sf(spec)
  line <- function(x) sf::st_linestring(matrix(x, ncol = 2, byrow = TRUE))
  entities <- membership_test_sf(
    c("inside", "cross", "endpoint", "multipart"),
    list(
      line(c(1,1,9,1)), line(c(8,2,12,2)), line(c(-1,0,0,0)),
      sf::st_multilinestring(list(matrix(c(2,3,4,3), ncol = 2, byrow = TRUE), matrix(c(12,3,14,3), ncol = 2, byrow = TRUE)))
    )
  )
  result <- exact_membership_pairs(scenes, entities, "road", spec)
  expect_true(all(c("inside", "cross", "multipart") %in% result$source_entity_id))
  expect_false("endpoint" %in% result$source_entity_id)
  expect_equal(sum(result$source_entity_id == "cross"), 2L)
  expect_equal(sum(result$source_entity_id == "multipart"), 2L)
})

test_that("point membership uses a closed scene boundary", {
  spec <- membership_test_spec()
  scenes <- membership_scene_sf(spec)
  entities <- membership_test_sf(
    c("inside", "shared-boundary", "outside"),
    list(sf::st_point(c(5,5)), sf::st_point(c(10,5)), sf::st_point(c(-1,5)))
  )
  result <- exact_membership_pairs(scenes, entities, "poi", spec)
  expect_equal(sum(result$source_entity_id == "inside"), 1L)
  expect_equal(sum(result$source_entity_id == "shared-boundary"), 2L)
  expect_false("outside" %in% result$source_entity_id)
})

test_that("invalid, empty, collection, and duplicate source IDs fail explicitly", {
  invalid <- membership_test_sf("invalid", list(sf::st_polygon(list(matrix(c(0,0,2,2,0,2,2,0,0,0), ncol = 2, byrow = TRUE)))))
  expect_error(validate_membership_candidates(invalid, "building", list()), "invalid=1")

  empty <- membership_test_sf("empty", list(sf::st_polygon()))
  expect_error(validate_membership_candidates(empty, "building", list()), "empty=1")

  collection <- membership_test_sf("collection", list(sf::st_geometrycollection(list(sf::st_point(c(1,1))))))
  expect_error(validate_membership_candidates(collection, "building", list()), "collection=1")

  duplicate <- membership_test_sf(c("same", "same"), list(sf::st_point(c(1,1)), sf::st_point(c(2,2))))
  expect_error(validate_membership_candidates(duplicate, "poi", list()), "duplicate source ID")
})

test_that("cost-balanced shard planning is deterministic and complete", {
  prototype <- data.frame(scene_id = sprintf("scene-%03d", 1:40))
  costs <- c(5000, seq(1, 39))
  first <- membership_lpt_shards(prototype, costs, target_shards = 5, maximum_scenes = 12, singleton_cost = 4000)
  second <- membership_lpt_shards(prototype, costs, target_shards = 5, maximum_scenes = 12, singleton_cost = 4000)
  expect_identical(first, second)
  expect_equal(length(first[[which(vapply(first, function(x) 1L %in% x, logical(1L)))]]), 1L)
  expect_setequal(unlist(first), seq_len(40))
  expect_identical(anyDuplicated(unlist(first)), 0L)
  expect_true(all(lengths(first) <= 12L))
})
