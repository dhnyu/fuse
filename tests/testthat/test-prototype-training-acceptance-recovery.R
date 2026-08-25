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
  training_command <- manifest$command[manifest$name == "prototype_training"]
  expect_match(training_command, "recover_prototype_training_target_metadata", fixed = TRUE)
  expect_match(training_command, "run_prototype_training", fixed = TRUE)
})

test_that("I21 schema keeps identity dynamic and fixes canonical direct outputs", {
  schema <- jsonlite::read_json(
    file.path(fuse_test_root, "config/schemas/prototype_training_acceptance.schema.json"),
    simplifyVector = FALSE
  )
  expect_null(schema$properties$plan_id$const)
  expect_null(schema$properties$run_id$const)
  expect_identical(schema$properties$plan_id$pattern, "^ptp_[0-9a-f]{24}$")
  expect_identical(schema$properties$run_id$pattern, "^ptr_[0-9a-f]{24}$")
  expect_identical(schema$properties$outputs$minItems, 2L)
  expect_identical(schema$properties$outputs$maxItems, 2L)
  expect_setequal(schema$`$defs`$output$properties$relative_path$enum,
                  c("prototype_training_qc.json", "validation_history.json"))
  expect_identical(schema$properties$resources$properties$worker_count$const, 40L)
  expect_identical(schema$properties$resources$properties$workers_per_rank$const, 20L)
})
