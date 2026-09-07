testthat::test_that("P9 v1 target nodes are absent and retired entrypoints fail immediately", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old <- getwd(); on.exit(setwd(old), add = TRUE); setwd(root)
  manifest <- targets::tar_manifest(script = "_targets.R", fields = c("name", "command"))
  testthat::expect_false(any(grepl("^p9_v1_.*retired$", manifest$name)))
  for (script in c("_targets_p9_formal.R", "_targets_p9_recovery.R")) {
    testthat::expect_error(
      targets::tar_manifest(script = script),
      "TRAINING_V1_EXECUTION_RETIRED.*historical training is read-only"
    )
  }
})

testthat::test_that("retirement guard fails closed with the stable contract", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  source(file.path(root, "R/training_retirement_guard.R"), local = TRUE)
  testthat::expect_error(
    retired_training_stop("synthetic-v1-entry"),
    "TRAINING_V1_EXECUTION_RETIRED.*historical training is read-only.*accepted-checkpoint resolver"
  )
})
