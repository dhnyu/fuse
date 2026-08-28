testthat::test_that("P6 config fixes reduced dimensions and populations", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p6_model_dataloader.yml"))
  testthat::expect_identical(as.integer(config$model$d), 64L)
  testthat::expect_identical(as.integer(config$model$d_c), 64L)
  testthat::expect_identical(as.integer(config$model$d_t), 16L)
  testthat::expect_identical(as.integer(config$model$d_r), 32L)
  testthat::expect_identical(as.integer(config$model$relation_layers), 3L)
  testthat::expect_identical(as.integer(config$model$attention_heads), 4L)
  testthat::expect_identical(as.integer(config$model$head_dimension), 16L)
  testthat::expect_identical(as.integer(config$model$ffn_dimension), 128L)
  testthat::expect_equal(config$model$dropout, 0.2)
  testthat::expect_identical(as.integer(config$population$training), 2421L)
  testthat::expect_identical(as.integer(config$population$validation_queries), 800L)
  testthat::expect_identical(as.integer(config$population$evaluation_queries), 3200L)
})

testthat::test_that("P6 active targets stop at bounded CPU acceptance", {
  text <- paste(readLines(testthat::test_path("..", "..", "targets", "research_model_dataloader.R"), warn = FALSE), collapse = "\n")
  expected <- c("p6_model_dataloader_contract_files", "d64_model_architecture_contract",
                "p6_preprocessing_contract", "p6_dataloader_acceptance",
                "d64_encoder_cpu_smoke", "model_data_acceptance")
  testthat::expect_true(all(vapply(expected, grepl, logical(1L), x = text, fixed = TRUE)))
  forbidden <- c("controller_gpu", "seoul_data_preprocess", "optimizer", "checkpoint", "backward")
  testthat::expect_false(any(vapply(forbidden, grepl, logical(1L), x = text, fixed = TRUE)))
})

testthat::test_that("P6 scientific identity excludes execution environment", {
  helper <- paste(readLines(testthat::test_path("..", "..", "R", "research_model_dataloader.R"), warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl("scientific$publication_root <- NULL", helper, fixed = TRUE))
  testthat::expect_false(grepl("Sys.info", helper, fixed = TRUE))
  testthat::expect_false(grepl("hostname", helper, fixed = TRUE))
  testthat::expect_false(grepl("CUDA", helper, fixed = TRUE))
})
