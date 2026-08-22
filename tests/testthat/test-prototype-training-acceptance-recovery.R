test_that("I21 recovery tracks completed evidence and never invokes training", {
  body_text <- paste(deparse(body(recover_prototype_training_acceptance)), collapse = "\n")
  expect_match(body_text, "recover_prototype_training_acceptance.py", fixed = TRUE)
  expect_false(grepl("run_prototype_training_ddp_locked.py", body_text, fixed = TRUE))
  expect_false(grepl("run_prototype_training(", body_text, fixed = TRUE))
  paths_text <- paste(deparse(body(prototype_completed_run_paths)), collapse = "\n")
  expect_match(paths_text, "epoch-%03d.pt", fixed = TRUE)
  expect_match(paths_text, "optimizer_steps.jsonl", fixed = TRUE)
  expect_match(paths_text, "resource_telemetry.jsonl", fixed = TRUE)
})

test_that("I21 recovery schema fixes current plan/run and four logical outputs", {
  schema <- jsonlite::read_json(
    file.path(fuse_test_root, "config/schemas/prototype_training_acceptance.schema.json"),
    simplifyVector = FALSE
  )
  expect_identical(schema$properties$plan_id$const, "ptp_3b100622bdb733351db6e458")
  expect_identical(schema$properties$run_id$const, "ptr_473911a4828ae5540a9d4eb9")
  expect_identical(schema$properties$outputs$minItems, 4L)
  expect_identical(schema$properties$outputs$maxItems, 4L)
  roles <- vapply(schema$properties$outputs$allOf, function(value) value$contains$properties$role$const, character(1L))
  expect_setequal(roles, c("run_completion", "validation_early_stopping_history", "checkpoint_catalog", "publication_recovery_qc"))
})
