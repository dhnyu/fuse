test_that("C01 is plan-only and has declared scientific evidence", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/full_membership_plan.yml"))
  expect_identical(config$stage, "C01")
  expect_identical(config$processing_epsg, 5186L)
  expect_true(config$authorization_gate$excluded_from_spatial_identity)
  expect_identical(config$sharding$initial_maximum_scenes_per_branch, 64L)

  manifest <- targets::tar_manifest(script = file.path(fuse_test_root, "_targets.R"),
                                    callr_arguments = list(wd = fuse_test_root))
  network <- targets::tar_network(script = file.path(fuse_test_root, "_targets.R"),
                                  callr_arguments = list(wd = fuse_test_root))
  parents <- network$edges$from[network$edges$to == "full_membership_plan"]
  expect_setequal(intersect(parents, manifest$name), c(
    "spatial_scene_index", "prototype_spatial_acceptance", "full_membership_i24_authorization",
    "prototype_membership_acceptance", "prototype_observation_plan", "full_membership_plan_contract_files"
  ))
  expect_false(any(grepl("^full_membership_shard$|^C02$", manifest$name)))
  expect_false("prototype_model_acceptance" %in% parents)
  authorization <- yaml::read_yaml(file.path(fuse_test_root, "config/full_membership_authorization.yml"))
  expect_true(authorization$excluded_from_spatial_identity)
  expect_identical(authorization$identity_role, "execution_authorization_only")
  pipeline <- readLines(file.path(fuse_test_root, "_targets.R"), warn = FALSE)
  function_block <- pipeline[seq_len(which(pipeline == ")")[[1L]])]
  expect_false(any(grepl("research_full_membership_plan.R", function_block, fixed = TRUE)))
})

test_that("Hilbert ordering and contiguous cap partition are deterministic", {
  points <- data.table::data.table(scene_id = sprintf("s%02d", 1:8), x = c(0, 1, 1, 0, 2, 3, 3, 2), y = c(0, 0, 1, 1, 0, 0, 1, 1))
  first <- fmp_hilbert_index(points$x, points$y, bits = 4L)$index
  second <- fmp_hilbert_index(points$x, points$y, bits = 4L)$index
  expect_identical(first, second)
  scenes <- data.table::data.table(estimated_cost_seconds = c(2, 2, 9, 2),
    estimated_source_vertex_count = c(2, 2, 9, 2), estimated_source_geometry_bytes = c(2, 2, 9, 2))
  result <- fmp_make_bins(scenes, maximum_scenes = 2L,
                          caps = c(estimated_cost_seconds = 5, estimated_source_vertex_count = 5,
                                   estimated_source_geometry_bytes = 5))
  expect_identical(result$bins, list(1:2, 3L, 4L))
  expect_identical(result$oversize, c(FALSE, FALSE, TRUE, FALSE))
})

test_that("C01 schema fixes I24 to authorization-only provenance", {
  schema <- jsonlite::read_json(file.path(fuse_test_root, "config/schemas/full_membership_plan.schema.json"), simplifyVector = FALSE)
  expect_true(schema$properties$authorization$properties$excluded_from_spatial_identity$const)
  expect_identical(schema$properties$authorization$properties$i24_id$const, "pma_6282c9e9f9ebb9348484223a")
})
