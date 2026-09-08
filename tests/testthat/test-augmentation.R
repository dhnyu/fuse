testthat::test_that("P4 supplement fixes the approved population and prefixes", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p4_deterministic_augmentation.yml"))
  testthat::expect_identical(config$supplement_version, "p4-augmentation-v2")
  testthat::expect_identical(config$population$split, "training")
  testthat::expect_identical(as.integer(config$population$scenes), 2421L)
  testthat::expect_identical(as.integer(config$banks$physical_k), 16L)
  testthat::expect_identical(as.integer(unlist(config$banks$logical_prefixes)), c(2L, 4L, 8L, 16L))
  testthat::expect_identical(as.integer(config$banks$expected_physical_candidates), 116208L)
  testthat::expect_identical(as.integer(config$banks$expected_default_references), 58104L)
})
testthat::test_that("P4 profile parameters exactly reproduce Appendix B", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p4_deterministic_augmentation.yml"))
  observed <- lapply(config$profiles, function(x) unname(as.numeric(unlist(x[c(
    "scale", "removal_fraction", "jitter_probability", "jitter_displacement_m",
    "simplification_tolerance_m", "categorical_mask_probability",
    "categorical_replacement_probability", "lane_probability",
    "landcover_mask_fraction", "dem_noise_sd_m"
  )]))))
  expected <- list(
    c(.5, .05, .10, .5, .5, .05, .05, .05, .05, .5),
    c(1, .10, .20, 1, 1, .10, .10, .10, .10, 1),
    c(2, .20, .40, 2, 2, .20, .20, .20, .20, 2)
  )
  testthat::expect_identical(observed, expected)
})

testthat::test_that("P4 provenance is bound to the current scientifically identical authority", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p4_deterministic_augmentation.yml"))
  authority_path <- "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/authority/mta_7875c4ba4587e4877ba0be1d/reduced_methodology_authority.json"
  module_path <- "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/authority/mta_7875c4ba4587e4877ba0be1d/augmentation_methodology_contract.json"
  authority <- jsonlite::read_json(authority_path, simplifyVector = FALSE)
  module <- jsonlite::read_json(module_path, simplifyVector = FALSE)
  authority$authority_id <- config$provenance_reconciliation$current_authority_id
  expect_invisible(p4_assert_current_augmentation_contract(authority, module, config))
  stale <- config; stale$dissertation_commit <- "109355b3d744248ca14749c5f74511537970d660"
  expect_error(p4_assert_current_augmentation_contract(authority, module, stale), "scientifically identical")
  expect_identical(config$dissertation_commit, "cbb824f19be8355296603f8426ac241ce587ddcc")
  expect_identical(config$provenance_reconciliation$scientific_change, FALSE)
})

testthat::test_that("P4 target declarations use only the fixed bank interface", {
  path <- testthat::test_path("..", "..", "targets", "s04_augmentation.R")
  text <- paste(readLines(path, warn = FALSE), collapse = "\n")
  expected <- c("s04_bank_profile_plan", "s04_bank_road_validation",
                "s04_bank_geometry_validation", "s04_bank_shard_plan",
                "s04_bank_execution", "s04_bank_validated_shard",
                "s04_bank_acceptance")
  testthat::expect_true(all(vapply(expected, grepl, logical(1L), x = text, fixed = TRUE)))
  testthat::expect_false(grepl("controller_gpu", text, fixed = TRUE))
  testthat::expect_false(grepl("seoul_data_preprocess", text, fixed = TRUE))
  testthat::expect_false(grepl("fixed_validation_query", text, fixed = TRUE))
  testthat::expect_false(grepl("augmentation_bank_shard_validation", text, fixed = TRUE))
})

testthat::test_that("P4 tiered execution is tracked but excluded from scientific identity", {
  helper <- paste(readLines(testthat::test_path("..", "..", "R", "augmentation.R"),
                            warn = FALSE), collapse = "\n")
  targets <- paste(readLines(testthat::test_path("..", "..", "targets", "s04_augmentation.R"),
                             warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl('relative != "scripts/run_augmentation_bank.py"', helper, fixed = TRUE))
  testthat::expect_true(grepl("p4_run_tiered_bank(s04_bank_shard_plan", targets, fixed = TRUE))
  testthat::expect_true(grepl("controller_05", targets, fixed = TRUE))
  testthat::expect_true(grepl("Pass A requires all 288 intended branches",
                              paste(readLines(testthat::test_path("..", "..", "scripts", "run_augmentation_bank.py"),
                                              warn = FALSE), collapse = "\n"), fixed = TRUE))
})
