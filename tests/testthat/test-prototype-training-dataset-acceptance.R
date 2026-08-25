test_that("I16 aggregate acceptance contract is fixed", {
  contract <- load_training_dataset_acceptance_config(training_dataset_acceptance_contract_paths(fuse_test_root))
  expect_equal(contract$config$identity$spatial_dataset_id, "psa_495cd109e72ec45bf2b8e7fa")
  expect_equal(contract$config$identity$serialization_plan_id, "psp_e82f7a94708626c722544505")
  expect_equal(contract$config$identity$serialization_dataset_id, "psd_e82f7a94708626c722544505")
  expect_equal(contract$config$execution$controller, "controller_05")
  expect_equal(unname(unlist(contract$config$expected$split_counts)), c(256, 32, 32))
  expect_equal(contract$config$expected$actual_payload_bytes, 421433195)
  expect_equal(contract$config$expected$tar_bytes, 423168000)
})

test_that("I16 Python corruption and determinism fixtures pass", {
  output <- system2(
    "python", c(file.path(fuse_test_root, "tests/python/test_accept_prototype_training_dataset.py"), "-v"),
    stdout = TRUE, stderr = TRUE
  )
  expect_null(attr(output, "status"), info = paste(output, collapse = "\n"))
  expect_true(any(grepl("OK", output, fixed = TRUE)), info = paste(output, collapse = "\n"))
})

test_that("I16 is a static file target with only scoped direct dependencies", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  target <- manifest[manifest$name == "prototype_training_dataset_acceptance", ]
  expect_true(is.na(target$pattern) || target$pattern == "")
  declaration <- readLines(file.path(fuse_test_root, "targets/research_training_dataset_acceptance.R"), warn = FALSE)
  expect_true(any(grepl('format = "file"', declaration, fixed = TRUE)))
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  parents <- intersect(
    network$edges$from[network$edges$to == "prototype_training_dataset_acceptance"], manifest$name
  )
  expect_setequal(parents, c(
    "prototype_spatial_acceptance", "prototype_serialization_plan", "prototype_serialization_shard",
    "training_dataset_acceptance_contract_files"
  ))
  expect_false(any(c("prototype_observation_plan", "prototype_vector_observation_shard",
                     "prototype_raster_observation_shard", "prototype_relation_shard") %in% parents))
})
