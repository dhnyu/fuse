test_that("P2 deterministic LPT covers every scene once", {
  ids <- sprintf("scene-%03d", 1:25)
  first <- p2_lpt_bins(ids, rev(seq_along(ids)), 5L, 8L)
  second <- p2_lpt_bins(ids, rev(seq_along(ids)), 5L, 8L)
  expect_identical(first, second)
  expect_setequal(unlist(first), seq_along(ids))
  expect_equal(anyDuplicated(unlist(first)), 0L)
  expect_true(all(lengths(first) <= 8L))
})

test_that("P2 observation identity excludes execution layout", {
  scientific <- list(authority = "mta", index = "rsi", schemas = c("a", "b"), implementation = "hash")
  expect_identical(p2_original_observation_id(scientific), p2_original_observation_id(scientific))
  layout_a <- list(branches = 12L, workers = 1L, path = "/tmp/a")
  layout_b <- list(branches = 96L, workers = 40L, path = "/tmp/b")
  expect_false(identical(p0_scientific_sha256(c(scientific, layout_a)), p0_scientific_sha256(c(scientific, layout_b))))

  config_a <- yaml::read_yaml(file.path(fuse_test_root, "config/p2_base_spatial.yml"))
  config_b <- config_a
  config_b$publication_root <- "/different/runtime/path"
  config_b$branching$controller <- "controller_10"
  config_b$scopes$production$membership_branches <- 48L
  config_b$scopes$production$observation_controller <- "controller_10"
  expect_identical(p2_scientific_config(config_a), p2_scientific_config(config_b))
})

test_that("P2 topology accepts variable chains and blocks corruption", {
  rows <- data.table::data.table(
    scene_id = rep("s", 3), road_local_entity_id = rep(0L, 3), source_node_position = 0:2,
    source_node_id = c("a", "b", "c"), source_node_offset_start = rep(0L, 3),
    source_node_offset_end = rep(3L, 3), chain_length = rep(3L, 3), road_type = rep("1", 3),
    road_hierarchy = rep("2", 3), source_node_x_5186 = 1:3, source_node_y_5186 = 4:6
  )
  expect_silent(p2_validate_topology_table(rows))
  expect_silent(p2_validate_topology_table(rows[0]))
  bad <- data.table::copy(rows); bad$source_node_position[[3]] <- 1L
  expect_error(p2_validate_topology_table(bad), "topology chain")
})

test_that("P2 source-node vertex mapping distinguishes retained and clipped nodes", {
  line <- sf::st_linestring(matrix(c(0, 0, 1, 1, 2, 2), ncol = 2, byrow = TRUE))
  expect_equal(p2_observed_vertex_index(line, 1, 1, 1e-7), 1L)
  expect_true(is.na(p2_observed_vertex_index(line, -1, -1, 1e-7)))
})

test_that("retained membership predicates handle boundaries and empty types", {
  scenes <- sf::st_sf(scene_id = "s", scene_footprint_id = "s", split = "training",
    geometry = sf::st_sfc(sf::st_polygon(list(matrix(c(0,0, 10,0, 10,10, 0,10, 0,0), ncol=2, byrow=TRUE))), crs=5186))
  spec <- list(branch_id = "b", scene_index_id = "rsi", prototype_id = "p", membership_dataset_id = "m",
    membership_contract = list(version = "1"), sources = list(
      building=list(entity_type="B",layer="b",source_artifact_id="x"), road=list(entity_type="R",layer="r",source_artifact_id="x"), poi=list(entity_type="P",layer="p",source_artifact_id="x")))
  points <- sf::st_sf(source_entity_id = c("inside", "boundary"), geometry = sf::st_sfc(sf::st_point(c(5,5)), sf::st_point(c(0,5)), crs=5186))
  membership <- exact_membership_pairs(scenes, points, "poi", spec)
  expect_setequal(membership$source_entity_id, c("inside", "boundary"))
  expect_equal(nrow(exact_membership_pairs(scenes, points[0,], "poi", spec)), 0L)
})

test_that("independent relation comparison blocks a wrong edge set", {
  expected <- data.table::data.table(scene_id="s", source_local_entity_id=0L, destination_local_entity_id=1L,
    relation_mask=1L, distance_m=1, host_building_local_entity_id=NA_integer_, shared_original_node_id=NA_character_)
  actual <- data.table::copy(expected); actual$relation_mask <- 2L
  expect_equal(compare_relation_reference(actual, expected)$status, "FAIL")
})

test_that("P3 serialization has the P2 production hard gate", {
  text <- paste(readLines(file.path(fuse_test_root, "targets/research_serialization_plan.R")), collapse="\n")
  expect_match(text, "base_spatial_acceptance", fixed=TRUE)
})
