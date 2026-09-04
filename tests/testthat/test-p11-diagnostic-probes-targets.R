test_that("P11-G graph is isolated and binds the accepted baseline", {
  script <- readLines(file.path(fuse_test_root, "targets/p11_diagnostic_probes.R"), warn = FALSE)
  text <- paste(script, collapse = "\n")
  expect_true(grepl("scripts/p11_diagnostic_probes.py", text, fixed = TRUE))
  expect_true(grepl("p11_ridge_evaluation_acceptance.yml", text, fixed = TRUE))
  expect_false(grepl("training", text, fixed = TRUE))
  expect_false(grepl("inference", text, fixed = TRUE))
})
