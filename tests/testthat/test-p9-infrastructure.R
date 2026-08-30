testthat::test_that("P9 remains infrastructure-only before formal authorization", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  config <- yaml::read_yaml(file.path(root, "config/p9_infrastructure.yml"))
  testthat::expect_false(config$authorization$formal_training)
  testthat::expect_false(config$authorization$hyperparameter_selection)
  testthat::expect_false(config$authorization$comparison_materialization)
  testthat::expect_identical(config$authorization$bounded_pilot_max_updates, 40L)
  testthat::expect_identical(config$population$training_scenes, 2421L)
  testthat::expect_false(config$population$evaluation_ancestry)
  testthat::expect_identical(config$sampler$optimizer_updates_per_epoch, 76L)
})

testthat::test_that("P9 target graph publishes readiness only", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  body <- paste(readLines(file.path(root, "targets/research_p9_infrastructure.R"), warn = FALSE), collapse = "\n")
  testthat::expect_match(body, "p9_infrastructure_readiness")
  testthat::expect_false(grepl("formal_training_run|hyperparameter_selection|comparison_training", body))
})
