test_that("P2 deterministic LPT covers every scene once", {
  ids <- sprintf("scene-%03d", 1:25)
  first <- p2_lpt_bins(ids, rev(seq_along(ids)), 5L, 8L)
  second <- p2_lpt_bins(ids, rev(seq_along(ids)), 5L, 8L)
  expect_identical(first, second)
  expect_setequal(unlist(first), seq_along(ids))
  expect_equal(anyDuplicated(unlist(first)), 0L)
  expect_true(all(lengths(first) <= 8L))
})

test_that("P2 current membership capacity covers 12,421 scenes in 96 aligned groups", {
  ids <- sprintf("scene-%05d", seq_len(12421L))
  costs <- as.double((seq_along(ids) * 7919L) %% 1009L)
  first <- p2_lpt_bins(ids, costs, 96L, 130L)
  second <- p2_lpt_bins(ids, costs, 96L, 130L)

  expect_length(first, 96L)
  expect_identical(first, second)
  expect_identical(sort(unlist(first)), seq_along(ids))
  expect_equal(anyDuplicated(unlist(first)), 0L)
  expect_true(all(lengths(first) <= 130L))
  expect_setequal(ids[unlist(first)], ids)
})

test_that("P2 membership packing fails closed when configured capacity is insufficient", {
  ids <- sprintf("scene-%05d", seq_len(12421L))
  expect_error(
    p2_lpt_bins(ids, seq_along(ids), 96L, 64L),
    paste0(
      "P2 membership packing capacity is insufficient for current scene population: ",
      "total scenes=12421, branch count=96, max scenes per branch=64, ",
      "total capacity=6144, minimum required capacity per branch=130"
    ),
    fixed = TRUE
  )
})

test_that("P2 membership packing accepts exact and minimum per-branch capacity boundaries", {
  exact <- p2_lpt_bins(sprintf("scene-%02d", 1:12), rep(1, 12), 3L, 4L)
  minimum <- p2_lpt_bins(sprintf("scene-%05d", seq_len(12421L)), rep(1, 12421L), 96L, 130L)

  expect_equal(lengths(exact), rep(4L, 3L))
  expect_length(minimum, 96L)
  expect_true(all(lengths(minimum) <= 130L))
  expect_identical(sort(unlist(minimum)), seq_len(12421L))
})

test_that("P2 binds runtime current P1 identities and exact content hashes", {
  fixture <- current_parent_fixture(); on.exit(unlink(fixture$root, recursive = TRUE), add = TRUE)
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p2_base_spatial.yml"))
  spec <- list(config = config)
  expect_no_error(p2_assert_upstream(fixture$authority, fixture$contract, fixture$index,
                                     fixture$scene, fixture$inventory, spec))
  scene <- jsonlite::read_json(fixture$scene, simplifyVector = FALSE)
  scene$artifact_checksums[[1L]]$sha256 <- paste(rep("0", 64), collapse = "")
  write_json_file(scene, fixture$scene)
  expect_error(p2_assert_upstream(fixture$authority, fixture$contract, fixture$index,
                                  fixture$scene, fixture$inventory, spec), "identity or acceptance")
  scene$artifact_checksums[[1L]]$sha256 <- sha256_file(fixture$index[basename(fixture$index) == "spatial_scene_index.parquet"])
  scene$authority_id <- "mta_historical"
  write_json_file(scene, fixture$scene)
  expect_error(p2_assert_upstream(fixture$authority, fixture$contract, fixture$index,
                                  fixture$scene, fixture$inventory, spec), "identity or acceptance")
  expect_false(any(grepl("PENDING_CURRENT_RECOMPUTATION", unlist(config), fixed = TRUE)))
})

test_that("P2 relation execution is owned by current target names", {
  target_text <- paste(readLines(file.path(fuse_test_root, "targets/s02_spatial_observations.R")), collapse = "\n")
  helper_text <- paste(readLines(file.path(fuse_test_root, "R/spatial_relation_execution.R")), collapse = "\n")
  worker_text <- paste(readLines(file.path(fuse_test_root, "scripts/run_spatial_relation_branch.R")), collapse = "\n")
  expect_match(target_text, "p2_run_relation_tiered_execution(s02_observation_plan, s02_vector_observation_shard", fixed = TRUE)
  retired <- c("base_spatial_observation_plan", "base_vector_observation_shard", "targets::tar_read(study_data_inputs")
  expect_false(any(vapply(retired, grepl, logical(1L), x = paste(helper_text, worker_text), fixed = TRUE)))
})

test_that("disposable targets store reaches current P2 relation acceptance", {
  skip_if_not_installed("targets")
  root <- tempfile("p2-fixture-store-"); dir.create(root)
  on.exit(unlink(root, recursive = TRUE), add = TRUE)
  script <- file.path(root, "_targets.R"); store <- file.path(root, "store")
  acceptance <- file.path(root, "fixture_spatial_acceptance.json")
  lines <- c(
    "library(targets)",
    sprintf("root <- %s", deparse(root)),
    "list(",
    "tar_target(s02_observation_plan, list(list(branch_id = 'branch-current'))),",
    "tar_target(s02_vector_observation_shard, list(list(branch_id = s02_observation_plan[[1]]$branch_id))),",
    "tar_target(s02_relation_execution, {stopifnot(s02_vector_observation_shard[[1]]$branch_id == s02_observation_plan[[1]]$branch_id); p <- file.path(root, 'fixture_relation_acceptance.json'); jsonlite::write_json(list(status='PASS'), p, auto_unbox=TRUE); p}, format='file'),",
    sprintf("tar_target(s02_spatial_acceptance, {stopifnot(file.exists(s02_relation_execution)); p <- %s; jsonlite::write_json(list(status='PASS', lineage='current'), p, auto_unbox=TRUE); p}, format='file')", deparse(acceptance)),
    ")"
  )
  writeLines(lines, script)
  targets::tar_make(names = s02_spatial_acceptance, script = script, store = store,
                    callr_function = NULL, reporter = "silent")
  expect_identical(jsonlite::read_json(acceptance, simplifyVector = FALSE)$lineage, "current")
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
  spec <- list(branch_id = "b", scene_index_id = "rsi", scope_id = "p", membership_dataset_id = "m",
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
  text <- paste(readLines(file.path(fuse_test_root, "targets/s03_scene_cache.R")), collapse="\n")
  expect_match(text, "s02_spatial_acceptance", fixed=TRUE)
})
