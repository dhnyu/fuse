test_that("I21 is the explicit optimizer boundary and enforces 40 workers", {
  body_text <- paste(deparse(body(run_prototype_training)), collapse = "\n")
  expect_match(body_text, "run_prototype_training_ddp_locked.py", fixed = TRUE)
  expect_match(body_text, "workers), 40L", fixed = TRUE)
  expect_match(body_text, "one-native-thread", fixed = TRUE)

  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  expect_true("prototype_training" %in% manifest$name)
  expect_false("prototype_training_completed_artifacts" %in% manifest$name)
})

test_that("I21 schema fixes current plan/run and direct training outputs", {
  schema <- jsonlite::read_json(
    file.path(fuse_test_root, "config/schemas/prototype_training_acceptance.schema.json"),
    simplifyVector = FALSE
  )
  expect_identical(schema$properties$plan_id$const, "ptp_19ce115adab48c4ff737a44d")
  expect_identical(schema$properties$run_id$const, "ptr_35743175250eaa556102185c")
  expect_identical(schema$properties$outputs$minItems, 2L)
  expect_identical(schema$properties$outputs$maxItems, 2L)
  expect_identical(schema$properties$resources$properties$worker_count$const, 40L)
  expect_identical(schema$properties$resources$properties$workers_per_rank$const, 20L)
})
