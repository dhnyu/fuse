testthat::test_that("P9 v1 target nodes are absent and retired entrypoints fail immediately", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old <- getwd(); on.exit(setwd(old), add = TRUE); setwd(root)
  manifest <- targets::tar_manifest(script = "_targets.R", fields = c("name", "command"))
  testthat::expect_false(any(grepl("^p9_v1_.*retired$", manifest$name)))
  for (script in c("_targets_p9_formal.R", "_targets_p9_recovery.R")) {
    testthat::expect_error(
      targets::tar_manifest(script = script),
      "P9_V1_EXECUTION_RETIRED.*historical/read-only"
    )
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
