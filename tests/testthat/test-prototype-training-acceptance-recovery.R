test_that("superseded I21 optimizer target is excluded from the active P7 graph", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  expect_false("prototype_training" %in% manifest$name)
  expect_false("prototype_training_completed_artifacts" %in% manifest$name)
  expect_true(all(c("p7_training_contract_files", "p7_deterministic_training_authority",
                    "prototype_training_run", "prototype_training_acceptance") %in% manifest$name))
  run_command <- manifest$command[manifest$name == "prototype_training_run"]
  expect_match(run_command, "p7_run_production", fixed = TRUE)
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
