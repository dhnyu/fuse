testthat::test_that("P4 supplement fixes the approved population and prefixes", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p4_deterministic_augmentation.yml"))
  testthat::expect_identical(config$supplement_version, "p4-determinism-v1")
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
    c(.5, .05, .25, 1, 1, .05, .05, .05, .05, .5),
    c(1, .10, .50, 2, 2, .10, .10, .10, .10, 1),
    c(2, .20, 1, 4, 4, .20, .20, .20, .20, 2)
  )
  testthat::expect_identical(observed, expected)
})

testthat::test_that("P4 target declarations use only the fixed bank interface", {
  path <- testthat::test_path("..", "..", "targets", "research_fixed_augmentation_banks.R")
  text <- paste(readLines(path, warn = FALSE), collapse = "\n")
  expected <- c("augmentation_profile_plan", "road_link_absorption_smoke",
                "geometry_consistency_smoke", "augmentation_bank_plan",
                "augmentation_bank_shard", "augmentation_bank_acceptance",
                "effective_augmentation_bank_index", "augmentation_bank_benchmark")
  testthat::expect_true(all(vapply(expected, grepl, logical(1L), x = text, fixed = TRUE)))
  testthat::expect_false(grepl("controller_gpu", text, fixed = TRUE))
  testthat::expect_false(grepl("seoul_data_preprocess", text, fixed = TRUE))
  testthat::expect_false(grepl("fixed_validation_query", text, fixed = TRUE))
})
