testthat::test_that("P6 config fixes reduced dimensions and populations", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "model_inputs.yml"))
  testthat::expect_identical(as.integer(config$model$d), 128L)
  testthat::expect_identical(as.integer(config$model$d_c), 128L)
  testthat::expect_identical(as.integer(config$model$d_t), 16L)
  testthat::expect_identical(as.integer(config$model$d_r), 32L)
  testthat::expect_identical(as.integer(config$model$relation_layers), 3L)
  testthat::expect_identical(as.integer(config$model$attention_heads), 4L)
  testthat::expect_identical(as.integer(config$model$head_dimension), 32L)
  testthat::expect_identical(as.integer(config$model$ffn_dimension), 256L)
  testthat::expect_equal(config$model$dropout, 0.2)
  testthat::expect_identical(as.integer(config$population$training), 2421L)
  testthat::expect_identical(as.integer(config$population$validation_queries), 2000L)
  testthat::expect_identical(as.integer(config$population$evaluation_queries), 18000L)
})

testthat::test_that("P6 active targets stop at bounded CPU acceptance", {
  text <- paste(readLines(testthat::test_path("..", "..", "targets", "s06_model_inputs.R"), warn = FALSE), collapse = "\n")
  expected <- c("s06_dataset_sources", "s06_reference_model_contract",
                "s06_dataset_preprocessing_contract", "s06_dataset_loader_acceptance",
                "s06_reference_encoder_validation", "s06_dataset_acceptance")
  testthat::expect_true(all(vapply(expected, grepl, logical(1L), x = text, fixed = TRUE)))
  forbidden <- c("controller_gpu", "seoul_data_preprocess", "optimizer", "checkpoint", "backward")
  testthat::expect_false(any(vapply(forbidden, grepl, logical(1L), x = text, fixed = TRUE)))
})

testthat::test_that("P6 source registry resolves only current normalized files", {
  stale <- c(
    "config/schemas/model_dataloader_acceptance.schema.json",
    "config/schemas/scene_model_data_acceptance.schema.json"
  )
  current <- c(
    "config/schemas/p6_dataloader_acceptance.schema.json",
    "config/schemas/p6_model_data_acceptance.schema.json"
  )
  names <- p6_contract_names()
  paths <- p6_contract_files(fuse_test_root)

  testthat::expect_length(names, 11L)
  testthat::expect_identical(names(paths), names)
  testthat::expect_true(all(file.exists(paths)))
  testthat::expect_true(all(current %in% names))
  testthat::expect_false(any(stale %in% names))
  testthat::expect_false(any(vapply(stale, function(name) any(endsWith(paths, name)), logical(1L))))

  schema_paths <- paths[grepl("^config/schemas/.*[.]json$", names(paths))]
  testthat::expect_length(schema_paths, 4L)
  testthat::expect_true(all(vapply(schema_paths, function(path) {
    is.list(jsonlite::read_json(path, simplifyVector = FALSE))
  }, logical(1L))))
  testthat::expect_true(is.list(yaml::read_yaml(paths[["config/model_inputs.yml"]])))
  testthat::expect_true(is.list(yaml::read_yaml(paths[["config/spatial_acceptance_aliases.yml"]])))
})

testthat::test_that("P6 scientific identity excludes execution environment", {
  helper <- paste(readLines(testthat::test_path("..", "..", "R", "model_inputs.R"), warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl("scientific$publication_root <- NULL", helper, fixed = TRUE))
  testthat::expect_false(grepl("Sys.info", helper, fixed = TRUE))
  testthat::expect_false(grepl("hostname", helper, fixed = TRUE))
  testthat::expect_false(grepl("CUDA", helper, fixed = TRUE))
})
