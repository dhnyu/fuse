testthat::test_that("all P9 v1 target entry points expose only retirement guards", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old <- getwd(); on.exit(setwd(old), add = TRUE); setwd(root)
  expected <- c(
    "_targets.R" = "p9_v1_main_execution_retired",
    "_targets_p9_formal.R" = "p9_v1_formal_execution_retired",
    "_targets_p9_recovery.R" = "p9_v1_recovery_execution_retired"
  )
  for (script in names(expected)) {
    manifest <- targets::tar_manifest(script = script, fields = c("name", "command"))
    p9 <- manifest[grepl("^p9", manifest$name), , drop = FALSE]
    testthat::expect_identical(p9$name, unname(expected[[script]]))
    testthat::expect_match(p9$command, "p9_v1_retired_stop", fixed = TRUE)
  }
})

testthat::test_that("retirement guard fails closed with the stable contract", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  source(file.path(root, "R/research_p9_v1_retirement.R"), local = TRUE)
  testthat::expect_error(
    p9_v1_retired_stop("synthetic-v1-entry"),
    "P9_V1_EXECUTION_RETIRED.*historical/read-only.*resolve_accepted_checkpoint"
  )
})
