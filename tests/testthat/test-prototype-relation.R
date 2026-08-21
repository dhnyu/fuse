relation_test_config <- function() load_relation_config(relation_contract_paths(fuse_test_root))

relation_test_scene_spec <- function() list(
  scene_id = "scene", scene_footprint_id = "foot", split = "training",
  xmin = 0, ymin = 0, xmax = 200, ymax = 200
)

relation_test_spec <- function() list(
  branch_id = "branch", observation_dataset_id = "vector", prototype_id = "prototype",
  scene_index_id = "index", scene_ids = list("scene"), scenes = list(relation_test_scene_spec())
)

relation_test_sf <- function(types, ids, geometries, areas = rep(NA_real_, length(types)),
                             f_nodes = rep(NA_character_, length(types)),
                             t_nodes = rep(NA_character_, length(types))) {
  sf::st_sf(
    scene_id = "scene", scene_footprint_id = "foot", split = "training",
    entity_type = types, source_entity_id = ids, local_entity_id = seq_along(ids) - 1L,
    observed_area_m2 = areas, F_NODE = f_nodes, T_NODE = t_nodes,
    observed_geometry = sf::st_sfc(geometries, crs = 5186)
  )
}

relation_line <- function(...) sf::st_linestring(matrix(c(...), ncol = 2, byrow = TRUE))
relation_square <- function(xmin, ymin, xmax, ymax) sf::st_polygon(list(matrix(c(
  xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax, xmin, ymin
), ncol = 2, byrow = TRUE)))

test_that("relation contract exactly matches the thesis applicability table", {
  config <- relation_test_config()
  expect_silent(validate_relation_config(config$scientific, config$runtime))
  expected <- relation_expected_applicability()
  for (source in names(expected)) for (destination in names(expected[[source]])) {
    expect_identical(as.character(unlist(config$scientific$applicability[[source]][[destination]])),
                     expected[[source]][[destination]])
  }
  expect_equal(unlist(config$scientific$relations$bits), c(SN = 0, CNT = 1, WIT = 2, INT = 3, CON = 4))
  expect_equal(config$scientific$sn$radius_m, 100)
  expect_equal(config$scientific$sn$top_k, 16)
})

test_that("strict POI containment selects the smallest deterministic host and expands CNT/WIT", {
  config <- relation_test_config()
  scene <- relation_test_sf(
    c("B", "B", "B", "P", "P"), c("large", "small-z", "small-a", "inside", "boundary"),
    list(
      relation_square(0, 0, 20, 20), relation_square(2, 2, 12, 12), relation_square(2, 2, 12, 12),
      sf::st_point(c(5, 5)), sf::st_point(c(0, 10))
    ),
    areas = c(400, 100, 100, NA, NA)
  )
  classification <- classify_relation_pois(scene, config)
  expect_equal(classification$state, c("B", "B", "B", "P_in", "P_out"))
  expect_equal(classification$host$host_building_local_entity_id, 2L)
  expect_true(classification$host$host_tie)
  edges <- scene_containment_edges(classification, config)
  bits <- relation_bit_values(config)
  expect_equal(edges[relation_bit == bits[["CNT"]], .(source_local_entity_id, destination_local_entity_id)],
               data.table::data.table(source_local_entity_id = 2L, destination_local_entity_id = 3L))
  expect_equal(edges[relation_bit == bits[["WIT"]], .(source_local_entity_id, destination_local_entity_id)],
               data.table::data.table(source_local_entity_id = 3L, destination_local_entity_id = 2L))
})

test_that("SN includes POI(out)-POI(out), exact radius, top-16, and union symmetrization", {
  config <- relation_test_config()
  points <- c(
    list(sf::st_point(c(0, 0))),
    lapply(1:18, function(i) sf::st_point(c(i, 0))),
    list(sf::st_point(c(100, 0)), sf::st_point(c(100.0001, 0)))
  )
  ids <- sprintf("p-%02d", seq_along(points))
  scene <- relation_test_sf(rep("P", length(points)), ids, points)
  classification <- classify_relation_pois(scene, config)
  result <- scene_sn_edges(scene, classification$state, config, candidate_block_size = 5L)
  bits <- relation_bit_values(config)
  expect_true(all(result$edges$relation_bit == bits[["SN"]]))
  expect_true(nrow(result$edges[source_local_entity_id == 0L]) >= 16L)
  expect_equal(max(result$edges$sn_source_rank, na.rm = TRUE), 16L)
  expect_false(any(result$edges$distance_m > 100))
  reverse <- paste(result$edges$destination_local_entity_id, result$edges$source_local_entity_id)
  expect_true(all(reverse %in% paste(result$edges$source_local_entity_id, result$edges$destination_local_entity_id)))

  boundary_scene <- relation_test_sf(c("P", "P", "P"), c("origin", "radius", "outside"),
                                     list(sf::st_point(c(0, 0)), sf::st_point(c(100, 0)), sf::st_point(c(100.0001, 0))))
  boundary <- scene_sn_edges(boundary_scene, rep("P_out", 3), config)$edges
  expect_true(any(boundary$distance_m == 100))
  expect_false(any(boundary$distance_m > 100))
})

test_that("contained POIs have no SN while boundary POIs remain eligible", {
  config <- relation_test_config()
  scene <- relation_test_sf(
    c("B", "P", "P", "R"), c("building", "inside", "boundary", "road"),
    list(relation_square(0, 0, 20, 20), sf::st_point(c(10, 10)), sf::st_point(c(0, 10)), relation_line(0, 30, 20, 30)),
    areas = c(400, NA, NA, NA), f_nodes = c(NA, NA, NA, "f"), t_nodes = c(NA, NA, NA, "t")
  )
  classification <- classify_relation_pois(scene, config)
  sn <- scene_sn_edges(scene, classification$state, config)$edges
  expect_false(any(sn$source_local_entity_id == 1L | sn$destination_local_entity_id == 1L))
  expect_true(any(sn$source_local_entity_id == 2L | sn$destination_local_entity_id == 2L))
})

test_that("INT includes polygon boundary contact, road endpoint contact, crossing, and overlap", {
  config <- relation_test_config()
  scene <- relation_test_sf(
    c("B", "B", "R", "R", "R"), c("b1", "b2", "r1", "r2", "r3"),
    list(
      relation_square(0, 0, 10, 10), relation_square(10, 0, 20, 10),
      relation_line(0, 20, 10, 20), relation_line(10, 20, 20, 20), relation_line(5, 20, 15, 20)
    ), areas = c(100, 100, NA, NA, NA),
    f_nodes = c(NA, NA, "a", "b", "c"), t_nodes = c(NA, NA, "b", "c", "d")
  )
  edges <- scene_intersection_edges(scene, config)
  pairs <- paste(edges$source_local_entity_id, edges$destination_local_entity_id)
  expect_true(all(c("0 1", "1 0", "2 3", "3 2", "2 4", "4 2") %in% pairs))
})

test_that("CON uses only shared original nodes inside the closed scene", {
  config <- relation_test_config()
  spec <- relation_test_scene_spec()
  scene <- relation_test_sf(
    rep("R", 5), paste0("r", 1:5),
    list(
      relation_line(0, 20, 20, 20), relation_line(20, 20, 20, 40),
      relation_line(200, 20, 180, 20), relation_line(50, 50, 60, 60), relation_line(50, 50, 40, 40)
    ),
    f_nodes = c("a", "shared-in", "shared-boundary", "same-coordinate-a", "same-coordinate-b"),
    t_nodes = c("shared-in", "b", "c", "d", "e")
  )
  nodes <- data.table::data.table(
    node_id = c("a", "shared-in", "b", "shared-boundary", "c", "same-coordinate-a", "same-coordinate-b", "d", "e"),
    x = c(0, 20, 20, 200, 180, 50, 50, 60, 40),
    y = c(20, 20, 40, 20, 20, 50, 50, 60, 40)
  )
  edges <- scene_connectivity_edges(scene, nodes, spec, config)
  expect_setequal(paste(edges$source_local_entity_id, edges$destination_local_entity_id), c("0 1", "1 0"))
  expect_true(all(edges$shared_original_node_id == "shared-in"))
  expect_false(any(grepl("same-coordinate", edges$shared_original_node_id)))
})

test_that("INT and CON survive in one deterministic pair mask", {
  config <- relation_test_config()
  spec <- relation_test_spec()
  scene_spec <- relation_test_scene_spec()
  scene <- relation_test_sf(
    c("R", "R"), c("r-a", "r-b"),
    list(relation_line(0, 20, 20, 20), relation_line(20, 20, 20, 40)),
    f_nodes = c("a", "shared"), t_nodes = c("shared", "b")
  )
  nodes <- data.table::data.table(node_id = c("a", "shared", "b"), x = c(0, 20, 20), y = c(20, 20, 40))
  first <- build_scene_relations(scene, nodes, scene_spec, spec, "relation", config)$edges
  second <- build_scene_relations(scene[2:1, ], nodes[sample(.N)], scene_spec, spec, "relation", config)$edges
  bits <- relation_bit_values(config)
  expected <- bitwOr(bits[["INT"]], bits[["CON"]])
  expect_true(all(bitwAnd(first$relation_mask, expected) == expected))
  expect_identical(first, second)
  expect_equal(anyDuplicated(first[, .(scene_id, source_local_entity_id, destination_local_entity_id)]), 0L)
})

test_that("relation edge Parquet fixes uint8 mask and is byte deterministic", {
  config <- relation_test_config()
  edges <- relation_empty_output_table()
  row <- as.list(setNames(rep(NA, length(relation_edge_columns())), relation_edge_columns()))
  row[c("scene_id", "scene_footprint_id", "split", "edge_id", "source_entity_type", "destination_entity_type",
        "relation_contract_version", "vector_observation_dataset_id", "relation_dataset_id", "branch_id")] <-
    list("scene", "foot", "training", paste0("red_", strrep("0", 24)), "B", "R", "1.0.0", "vector", "relation", "branch")
  row[c("source_local_entity_id", "destination_local_entity_id", "relation_mask", "sn_source_rank")] <- list(0L, 1L, 1L, 1L)
  row[c("has_sn", "has_cnt", "has_wit", "has_int", "has_con", "directed")] <- list(TRUE, FALSE, FALSE, FALSE, FALSE, FALSE)
  row$distance_m <- 10
  columns <- relation_edge_columns()
  edges <- data.table::rbindlist(list(row))[, ..columns]
  first <- tempfile(fileext = ".parquet"); second <- tempfile(fileext = ".parquet")
  write_relation_edges(edges, first, config); write_relation_edges(edges, second, config)
  expect_identical(sha256_file(first), sha256_file(second))
  schema <- arrow::ParquetFileReader$create(first)$GetSchema()
  expect_equal(schema$GetFieldByName("relation_mask")$type$ToString(), "uint8")
})
