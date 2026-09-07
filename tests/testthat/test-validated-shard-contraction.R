testthat::test_that("P4/P5 validation receipts fail closed on missing or wrong identity", {
  root <- tempfile("validated-shards-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE), add = TRUE)

  make_files <- function(branch_id, receipt) {
    branch <- file.path(root, branch_id)
    dir.create(branch)
    writeBin(charToRaw("payload"), file.path(branch, paste0(branch_id, ".tar")))
    write_json_file(list(branch_id = branch_id), file.path(branch, "branch_manifest.json"))
    write_json_file(receipt, file.path(branch, "validation_receipt.json"))
    list.files(branch, full.names = TRUE)
  }

  p4 <- make_files("p4-a", list(
    status = "PASS", branch_id = "p4-a", validation = list(status = "PASS")
  ))
  testthat::expect_identical(p4_validation_evidence(list(p4))[[1L]]$status, "PASS")
  wrong_p4 <- p4
  write_json_file(list(status = "PASS", branch_id = "foreign",
    validation = list(status = "PASS")), artifact_path(wrong_p4, "validation_receipt.json"))
  testthat::expect_error(p4_validation_evidence(list(wrong_p4)), "identity mismatch")

  p5 <- make_files("p5-a", list(
    status = "PASS", branch_id = "p5-a", split = "validation",
    namespace = "validation-query", seed = 20481217L,
    validation = list(status = "PASS")
  ))
  plan <- list(list(branch_id = "p5-a", split = "validation",
    namespace = "validation-query", config = list(seed = 20481217L)))
  testthat::expect_identical(p5_validation_evidence(list(p5), plan)[[1L]]$status, "PASS")
  plan[[1L]]$config$seed <- 1L
  testthat::expect_error(p5_validation_evidence(list(p5), plan), "identity/split mismatch")
  unlink(artifact_path(p5, "validation_receipt.json"))
  testthat::expect_error(p5_validation_evidence(list(p5), plan), "receipt missing")
})

testthat::test_that("validated dynamic branches retry only failures and track validator config", {
  root <- tempfile("validated-branch-store-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE), add = TRUE)
  script <- file.path(root, "_targets.R")
  store <- file.path(root, "store")
  config <- file.path(root, "validator.txt")
  writeLines("v1", config)
  writeLines(c(
    "library(targets)",
    "tar_option_set(error = 'continue')",
    "validated_fixture_branch <- function(branch, validator_config) {",
    "  counter <- file.path(branch$root, paste0(branch$id, '.count'))",
    "  count <- if (file.exists(counter)) as.integer(readLines(counter)) else 0L",
    "  writeLines(as.character(count + 1L), counter)",
    "  if (branch$id == 'b' && !file.exists(file.path(branch$root, 'permit-b'))) stop('fixture validation failure')",
    "  output <- file.path(branch$root, paste0(branch$id, '-', readLines(validator_config), '.json'))",
    "  writeLines(branch$id, output)",
    "  output",
    "}",
    sprintf("root <- %s", encodeString(root, quote = '"')),
    sprintf("validator <- %s", encodeString(config, quote = '"')),
    "list(",
    "  tar_target(validator_config, validator, format = 'file'),",
    "  tar_target(plan, lapply(c('a','b','c'), function(id) list(id=id, root=root)), iteration='list'),",
    "  tar_target(validated_shard, validated_fixture_branch(plan, validator_config), pattern=map(plan), format='file', error='continue')",
    ")"
  ), script)

  testthat::expect_error(
    targets::tar_make(script = script, store = store, callr_function = NULL, reporter = "silent"),
    NA
  )
  writeLines("allow", file.path(root, "permit-b"))
  targets::tar_make(script = script, store = store, callr_function = NULL, reporter = "silent")
  counts <- vapply(c("a", "b", "c"), function(id) {
    as.integer(readLines(file.path(root, paste0(id, ".count"))))
  }, integer(1L))
  testthat::expect_identical(unname(counts), c(1L, 2L, 1L))

  writeLines("v2", config)
  targets::tar_make(script = script, store = store, callr_function = NULL, reporter = "silent")
  counts <- vapply(c("a", "b", "c"), function(id) {
    as.integer(readLines(file.path(root, paste0(id, ".count"))))
  }, integer(1L))
  testthat::expect_identical(unname(counts), c(2L, 3L, 2L))
})
