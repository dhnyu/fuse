testthat::test_that("P5 supplement fixes namespaces, populations and query indices", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p5_deterministic_queries.yml"))
  testthat::expect_identical(config$supplement_id, "p5-fixed-query-v1")
  testthat::expect_identical(config$schema_version, "1.0.0")
  testthat::expect_identical(config$profile$profile_id, "main_1.0x")
  testthat::expect_identical(as.integer(unlist(config$query_indices)), c(0L, 1L))
  testthat::expect_identical(config$namespaces$validation$namespace, "validation-query")
  testthat::expect_identical(config$namespaces$evaluation$namespace, "evaluation-query")
  testthat::expect_identical(as.integer(config$namespaces$validation$queries), 800L)
  testthat::expect_identical(as.integer(config$namespaces$evaluation$queries), 3200L)
  testthat::expect_identical(config$publication$training_bank_membership, "prohibited")
})

testthat::test_that("P5 target declaration excludes P6, maintenance and GPU dependencies", {
  path <- testthat::test_path("..", "..", "targets", "research_fixed_queries.R")
  text <- paste(readLines(path, warn = FALSE), collapse = "\n")
  expected <- c("fixed_query_methodology_contract", "fixed_validation_query_plan",
                "fixed_evaluation_query_plan", "fixed_query_shard",
                "fixed_query_shard_validation", "fixed_validation_query_acceptance",
                "fixed_evaluation_query_acceptance", "fixed_query_acceptance")
  testthat::expect_true(all(vapply(expected, grepl, logical(1L), x = text, fixed = TRUE)))
  testthat::expect_false(grepl("controller_gpu", text, fixed = TRUE))
  testthat::expect_false(grepl("seoul_data_preprocess", text, fixed = TRUE))
  testthat::expect_false(grepl("training", text, fixed = TRUE))
})

testthat::test_that("P5 scientific implementation hash excludes execution environment", {
  helper <- paste(readLines(testthat::test_path("..", "..", "R", "research_fixed_queries.R"), warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl("implementation_hash", helper, fixed = TRUE))
  testthat::expect_true(grepl("scientific_config$publication_root <- NULL", helper, fixed = TRUE))
  testthat::expect_true(grepl("scientific_config$execution <- NULL", helper, fixed = TRUE))
  testthat::expect_false(grepl("Sys.info", helper, fixed = TRUE))
  testthat::expect_false(grepl("hostname", helper, fixed = TRUE))
})
