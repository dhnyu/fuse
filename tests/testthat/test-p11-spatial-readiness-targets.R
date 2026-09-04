test_that("P11-C graph materializes readiness without fitting ridge probes", {
  script <- readLines(
    file.path(fuse_test_root, "targets/p11_spatial_readiness.R"),
    warn = FALSE
  )
  graph <- paste(script, collapse = "\n")
  expect_true(grepl("p11_c_contract", graph, fixed = TRUE))
  expect_true(grepl("p11_c_methodology", graph, fixed = TRUE))
  expect_true(grepl("p11_c_acceptance", graph, fixed = TRUE))
  expect_true(grepl("scripts/p11_spatial_readiness.py", graph, fixed = TRUE))
  expect_false(grepl("ridge.*fit|oof.*predict|tar_map", graph, ignore.case = TRUE))
})

test_that("P11-C active pointer authorizes only P11-E", {
  pointer <- yaml::read_yaml(
    file.path(fuse_test_root, "config/p11_spatial_readiness_acceptance.yml")
  )
  expect_identical(pointer$status, "PASS")
  expect_identical(pointer$readiness_id, "p11c_e78d7c740edc49f1f646ebc3")
  expect_identical(
    pointer$next_work_unit,
    "P11_E_SPATIAL_RIDGE_PROBES_AND_OOF_PREDICTIONS"
  )
})
