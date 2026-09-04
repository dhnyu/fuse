test_that("P10 target graph is closed and P11/training-free", {
  script <- readLines(file.path(fuse_test_root, "targets/p10_targets.R"), warn = FALSE)
  names <- paste(script, collapse = "\n")
  expect_true(grepl("p10_prepared_input_cache", names, fixed = TRUE))
  expect_true(grepl("p10_prepared_geometry_cache", names, fixed = TRUE))
  expect_true(grepl("p10_evaluation_acceptance", names, fixed = TRUE))
  expect_false(grepl("p11|optimizer|training|checkpoint", names, ignore.case = TRUE))
})
