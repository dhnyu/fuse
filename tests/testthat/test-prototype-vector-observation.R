observation_test_config <- function() load_observation_config(observation_contract_paths(fuse_test_root))

observation_test_scenes <- function() {
  membership_scene_sf(list(scenes = list(
    list(scene_id = "scene-a", scene_footprint_id = "foot-a", split = "training", xmin = 0, ymin = 0, xmax = 10, ymax = 10),
    list(scene_id = "scene-b", scene_footprint_id = "foot-b", split = "training", xmin = 10, ymin = 0, xmax = 20, ymax = 10)
  )))
}

observation_test_membership <- function(ids, type, scenes = rep("scene-a", length(ids))) {
  data.table::data.table(
    scene_id = scenes,
    scene_footprint_id = ifelse(scenes == "scene-a", "foot-a", "foot-b"),
    split = "training", entity_type = type, source_entity_id = ids,
    source_layer = switch(type, B = "buildings", R = "links", P = "points"),
    membership_predicate_version = "1.0.0", branch_id = "membership-branch",
    source_artifact_id = paste0("src-", type), scene_index_id = "idx-test", prototype_id = "pro-test"
  )
}

observation_test_spec <- function() list(
  membership_dataset_id = "pmd-test", observation_dataset_id = "pvo-test",
  prototype_id = "pro-test", scene_index_id = "idx-test"
)

square_polygon <- function(xmin, ymin, xmax, ymax) sf::st_polygon(list(matrix(c(
  xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax, xmin, ymin
), ncol = 2, byrow = TRUE)))

observation_test_sf <- function(ids, geometries) {
  sf::st_sf(source_entity_id = ids, geometry = sf::st_sfc(geometries, crs = 5186))
}

observation_membership_spec <- function() list(
  branch_id = "pmb-test", prototype_id = "pro-test", scene_index_id = "idx-test",
  membership_contract = list(version = "1.0.0"),
  sources = list(
    building = list(entity_type = "B", layer = "buildings", source_artifact_id = "src-b"),
    road = list(entity_type = "R", layer = "links", source_artifact_id = "src-r"),
    poi = list(entity_type = "P", layer = "points", source_artifact_id = "src-p")
  )
)

test_that("vector observation contract fixes clipping, A14, local IDs, and writer", {
  config <- observation_test_config()
  expect_equal(config$scientific$processing_epsg, 5186)
  expect_equal(config$scientific$attributes$building$allocation, "A14 * observed_area_m2 / source_area_m2")
  expect_equal(config$scientific$local_entity_id$type, "int32")
  expect_equal(config$scientific$writer$geoparquet_version, "1.1.0")
  expect_equal(config$runtime$controller, "controller_40")
  expect_equal(config$runtime$branch_workers, 1)
  expect_equal(config$runtime$threads_per_worker, 1)
})

test_that("building clipping handles contained, crossing, holes, multipart, and split output", {
  config <- observation_test_config()
  scenes <- observation_test_scenes()
  hole <- sf::st_polygon(list(
    matrix(c(1,1,9,1,9,9,1,9,1,1), ncol = 2, byrow = TRUE),
    matrix(c(3,3,7,3,7,7,3,7,3,3), ncol = 2, byrow = TRUE)
  ))
  multipart <- sf::st_multipolygon(list(
    list(matrix(c(2,2,3,2,3,3,2,3,2,2), ncol = 2, byrow = TRUE)),
    list(matrix(c(12,2,13,2,13,3,12,3,12,2), ncol = 2, byrow = TRUE))
  ))
  splitter <- sf::st_union(sf::st_sfc(
    square_polygon(1, 1, 3, 11), square_polygon(7, 1, 9, 11),
    square_polygon(1, 10.5, 9, 12), crs = 5186
  ))[[1L]]
  source <- sf::st_sf(
    source_entity_id = c("contained", "crossing", "hole", "multipart", "splitter"),
    A9 = "use", A11 = "structure", A14 = c(100, 100, 100, 100, 100), A14_source_state = "VALUE",
    geometry = sf::st_sfc(
      square_polygon(1,1,2,2), square_polygon(8,2,12,4), hole, multipart, splitter,
      crs = 5186
    )
  )
  membership <- observation_test_membership(source$source_entity_id, "B")
  membership <- assign_local_entity_ids(membership, config)
  value <- build_role_observations("building", membership, source, scenes, observation_test_spec(), config)
  expect_equal(nrow(value), 5)
  expect_equal(value[source_entity_id == "contained", observed_area_fraction], 1, tolerance = 1e-12)
  expect_equal(value[source_entity_id == "crossing", observed_area_fraction], 0.5, tolerance = 1e-12)
  expect_equal(value[source_entity_id == "crossing", observed_gross_floor_area_m2], 50, tolerance = 1e-10)
  expect_equal(value[source_entity_id == "hole", observed_hole_count], 1)
  expect_equal(value[source_entity_id == "multipart", observed_component_count], 1)
  expect_true(value[source_entity_id == "splitter", observed_component_count] >= 2)
})

test_that("boundary-only building and road results are rejected by positive measure membership", {
  scenes <- observation_test_scenes()
  building <- observation_test_sf("touch", list(square_polygon(-2, 10, 2, 11)))
  road <- observation_test_sf("touch", list(sf::st_linestring(matrix(c(-1,0,0,0), ncol = 2, byrow = TRUE))))
  spec <- observation_membership_spec()
  expect_equal(nrow(exact_membership_pairs(scenes, building, "building", spec)), 0)
  expect_equal(nrow(exact_membership_pairs(scenes, road, "road", spec)), 0)
})

test_that("road clipping recomputes length and endpoints for lines and multilines", {
  config <- observation_test_config()
  scenes <- observation_test_scenes()
  line <- function(x) sf::st_linestring(matrix(x, ncol = 2, byrow = TRUE))
  source <- sf::st_sf(
    source_entity_id = c("inside", "cross", "multi", "split"),
    LANES = c(2,4,1,3), ROAD_RANK = "rank", ROAD_TYPE = "type", F_NODE = "f", T_NODE = "t",
    geometry = sf::st_sfc(
      line(c(1,1,9,1)), line(c(8,2,12,2)),
      sf::st_multilinestring(list(matrix(c(1,3,4,3), ncol = 2, byrow = TRUE), matrix(c(12,3,14,3), ncol = 2, byrow = TRUE))),
      sf::st_multilinestring(list(matrix(c(-1,4,3,4), ncol = 2, byrow = TRUE), matrix(c(7,4,11,4), ncol = 2, byrow = TRUE))),
      crs = 5186
    )
  )
  membership <- assign_local_entity_ids(observation_test_membership(source$source_entity_id, "R"), config)
  value <- build_role_observations("road", membership, source, scenes, observation_test_spec(), config)
  expect_equal(value[source_entity_id == "inside", observed_length_m], 8, tolerance = 1e-10)
  expect_equal(value[source_entity_id == "cross", observed_length_m], 2, tolerance = 1e-10)
  expect_true(value[source_entity_id == "split", observed_component_count] >= 2)
  expect_true(all(value$observed_endpoint_count >= 2))
})

test_that("POI preserves inside and boundary points without moving geometry", {
  config <- observation_test_config()
  scenes <- observation_test_scenes()
  fields <- observation_source_fields(config, "poi")
  attributes <- as.data.frame(setNames(rep(list(c("x", "y")), length(fields)), fields), stringsAsFactors = FALSE)
  source <- sf::st_sf(
    cbind(data.frame(source_entity_id = c("inside", "boundary")), attributes),
    geometry = sf::st_sfc(sf::st_point(c(5,5)), sf::st_point(c(10,5)), crs = 5186)
  )
  membership <- assign_local_entity_ids(observation_test_membership(source$source_entity_id, "P"), config)
  value <- build_role_observations("poi", membership, source, scenes, observation_test_spec(), config)
  expect_false(any(value$is_clipped))
  expect_identical(value$source_geometry_fingerprint, value$observed_geometry_fingerprint)
  expect_equal(value[source_entity_id == "boundary", relative_center_x_m], 5)
})

test_that("local IDs and multi-scene observations are input-order independent", {
  config <- observation_test_config()
  membership <- data.table::rbindlist(list(
    observation_test_membership(c("z", "a"), "B"),
    observation_test_membership("road", "R"),
    observation_test_membership("poi", "P"),
    observation_test_membership("z", "B", "scene-b")
  ))
  first <- assign_local_entity_ids(membership, config)
  second <- assign_local_entity_ids(membership[sample(.N)], config)
  data.table::setorder(first, scene_id, entity_type, source_entity_id)
  data.table::setorder(second, scene_id, entity_type, source_entity_id)
  expect_identical(first$local_entity_id, second$local_entity_id)
  expect_equal(sum(first$source_entity_id == "z"), 2)
})

test_that("invalid, empty, collection and zero-dimension inputs fail", {
  invalid <- observation_test_sf("invalid", list(sf::st_polygon(list(matrix(c(0,0,2,2,0,2,2,0,0,0), ncol = 2, byrow = TRUE)))))
  empty <- observation_test_sf("empty", list(sf::st_polygon()))
  collection <- observation_test_sf("collection", list(sf::st_geometrycollection(list(sf::st_point(c(1,1))))))
  expect_error(validate_membership_candidates(invalid, "building", list()), "invalid=1")
  expect_error(validate_membership_candidates(empty, "building", list()), "empty=1")
  expect_error(validate_membership_candidates(collection, "building", list()), "collection=1")
})

test_that("GeoParquet 1.1 writer is byte deterministic and cross-readable", {
  skip_if_not(Sys.which("python") != "")
  config <- observation_test_config()
  value <- data.frame(
    scene_id = c("a", "b"), observed_geometry = I(sf::st_as_binary(sf::st_sfc(
      square_polygon(0,0,1,1), square_polygon(2,2,3,3), crs = 5186
    ), EWKB = FALSE, endian = "little"))
  )
  first <- tempfile(fileext = ".parquet")
  second <- tempfile(fileext = ".parquet")
  write_standard_geoparquet(value, first, config)
  write_standard_geoparquet(value, second, config)
  expect_identical(sha256_file(first), sha256_file(second))
  info <- inspect_standard_geoparquet(first, config)
  expect_equal(info$version, "1.1.0")
  expect_equal(info$crs_epsg, 5186)
  roundtrip <- read_standard_geoparquet(first)
  expect_equal(nrow(roundtrip), 2)
  expect_equal(sf::st_crs(roundtrip)$epsg, 5186)
  expect_true(all(sf::st_equals_exact(sf::st_geometry(roundtrip), sf::st_as_sfc(value$observed_geometry, crs = 5186), par = 0, sparse = FALSE)[cbind(1:2,1:2)]))
})

test_that("observation cost sharding is deterministic, capped, and complete", {
  config <- observation_test_config()
  scene <- data.table::data.table(
    scene_id = sprintf("s-%03d", 1:100), estimated_cost = c(15000, rep(100, 99)),
    entity_count = c(21000, rep(100, 99)), source_geometry_bytes = c(1e6, rep(1e5, 99))
  )
  first <- observation_cost_shards(scene, config)
  second <- observation_cost_shards(scene, config)
  expect_identical(first, second)
  expect_equal(length(first[[which(vapply(first, function(x) 1L %in% x, logical(1L)))]]), 1)
  expect_setequal(unlist(first), seq_len(100))
  expect_equal(anyDuplicated(unlist(first)), 0)
  expect_true(all(lengths(first) <= config$scientific$sharding$maximum_scenes_per_shard))
})
