test_that("I19 augmentation contract fixes the resolved attribute policy", {
  contract <- load_augmentation_benchmark_config(augmentation_benchmark_contract_paths(fuse_test_root))
  expect_equal(contract$config$attributes$geometry_independent_continuous$status, "disabled_no_eligible_fields")
  expect_length(contract$config$attributes$geometry_independent_continuous$eligible_fields, 0)
  expect_equal(contract$config$attributes$road_lanes$probability, 0.10)
  expect_equal(unlist(contract$config$attributes$road_lanes$offset_support), c(-1, 1))
  expect_equal(contract$config$attributes$road_lanes$lower_bound_action, "clamp_without_resampling")
  expect_equal(contract$config$geometry$maximum_attempts, 10)
  expect_equal(contract$config$geometry$scene_boundary_tolerance_m, 1e-8)
})

test_that("I19 Python augmentation fixtures pass", {
  output <- system2(
    "python", c(file.path(fuse_test_root, "tests/python/test_prototype_augmentation.py"), "-v"),
    stdout = TRUE, stderr = TRUE
  )
  expect_null(attr(output, "status"), info = paste(output, collapse = "\n"))
  expect_true(any(grepl("OK", output, fixed = TRUE)), info = paste(output, collapse = "\n"))
})

test_that("I19 is gated by the scoped 320-scene scientific round trip", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  parents <- intersect(
    network$edges$from[network$edges$to == "prototype_augmentation_benchmark"], manifest$name
  )
  expect_setequal(parents, c(
    "prototype_training_dataset_acceptance", "prototype_dataloader_smoke",
    "prototype_scientific_geometry_roundtrip", "augmentation_benchmark_contract_files"
  ))
  gate_parents <- intersect(
    network$edges$from[network$edges$to == "prototype_scientific_geometry_roundtrip"], manifest$name
  )
  expect_setequal(gate_parents, c(
    "prototype_training_dataset_acceptance", "prototype_dataloader_smoke",
    "augmentation_benchmark_contract_files"
  ))
  declaration <- readLines(file.path(fuse_test_root, "targets/research_augmentation_benchmark.R"), warn = FALSE)
  expect_false(any(grepl("/mnt/", declaration, fixed = TRUE)))
})
