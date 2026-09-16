test_that("evaluation target graph is closed and downstream/training-free", {
  script <- readLines(file.path(fuse_test_root, "targets/s11_evaluation.R"), warn = FALSE)
  names <- paste(script, collapse = "\n")
  expect_true(grepl("s11_evaluation_input_cache", names, fixed = TRUE))
  expect_true(grepl("s11_evaluation_geometry_cache", names, fixed = TRUE))
  expect_true(grepl("s11_evaluation_acceptance", names, fixed = TRUE))
  expect_false(grepl("s10_retrieval|s09_training|optimizer|checkpoint", names, ignore.case = TRUE))
})

test_that("evaluation entrypoint manifest and validation remain direct", {
  skip_if_not_installed("targets")
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old <- getwd(); on.exit(setwd(old), add = TRUE); setwd(root)
  manifest <- targets::tar_manifest(
    script = "_targets_evaluation.R",
    fields = c("name", "command")
  )
  expect_length(manifest$name, 5L)
  expect_silent(targets::tar_validate(script = "_targets_evaluation.R"))
})
