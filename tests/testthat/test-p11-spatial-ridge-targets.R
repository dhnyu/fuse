test_that("P11-E graph is an isolated fixed-ridge evaluation closure", {
  script <- paste(
    readLines(file.path(fuse_test_root, "targets/p11_spatial_ridge.R"), warn = FALSE),
    collapse = "\n"
  )
  expect_true(grepl("p11_e_contract", script, fixed = TRUE))
  expect_true(grepl("p11_e_authorized_inputs", script, fixed = TRUE))
  expect_true(grepl("p11_e_acceptance", script, fixed = TRUE))
  expect_true(grepl("scripts/p11_spatial_ridge.py", script, fixed = TRUE))
  expect_false(grepl("inference|fine.?tun|checkpoint|p9_|p10_.*evaluation", script, ignore.case = TRUE))
})

test_that("P11-E pointer fixes fit cardinality and the P11-F boundary", {
  pointer <- yaml::read_yaml(
    file.path(fuse_test_root, "config/p11_ridge_evaluation_acceptance.yml")
  )
  expect_identical(pointer$status, "PASS")
  expect_identical(pointer$acceptance_id, "p11e_047e764ed7467b72ebe846df")
  expect_identical(pointer$fit_count, 2200L)
  expect_identical(pointer$oof_row_count, 128432L)
  expect_identical(
    pointer$next_work_unit,
    "P11_F_FINAL_DOWNSTREAM_COMPARISON_AND_ACCEPTANCE"
  )
})
