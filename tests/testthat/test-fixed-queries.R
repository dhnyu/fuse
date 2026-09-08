testthat::test_that("P5 supplement fixes namespaces, populations and query indices", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p5_deterministic_queries.yml"))
  testthat::expect_identical(config$supplement_id, "p5-fixed-query-v2")
  testthat::expect_identical(config$schema_version, "1.0.0")
  testthat::expect_identical(config$profile$profile_id, "main_1.0x")
  testthat::expect_identical(as.integer(unlist(config$query_indices)), c(0L, 1L))
  testthat::expect_identical(config$namespaces$validation$namespace, "validation-query")
  testthat::expect_identical(config$namespaces$evaluation$namespace, "evaluation-query")
  testthat::expect_identical(as.integer(config$namespaces$validation$queries), 2000L)
  testthat::expect_identical(as.integer(config$namespaces$evaluation$queries), 18000L)
  testthat::expect_identical(config$publication$training_bank_membership, "prohibited")
  testthat::expect_identical(config$p4_supplement_id, "p4-augmentation-v2")
  testthat::expect_identical(config$p4_master_bank_id, "dynamic_from_augmentation_bank_acceptance")
  testthat::expect_identical(config$p4_logical_index_id, "dynamic_from_effective_augmentation_bank_index")
})

testthat::test_that("P5 enforces exact current split, query, gallery, and identity counts", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p5_deterministic_queries.yml"))
  ids <- sprintf("scene-%05d", seq_len(10000L))
  split <- c(rep("validation", 1000L), rep("evaluation", 9000L))
  expect_silent(p5_validate_population_contract(ids, split, config))
  expect_error(p5_validate_population_contract(ids[1:2000], c(rep("validation", 400), rep("evaluation", 1600)), config), "population contract")
  expect_error(p5_validate_population_contract(ids, c(rep("validation", 999), rep("evaluation", 9001)), config), "population contract")
  bad_queries <- config; bad_queries$namespaces$evaluation$queries <- 17999L
  expect_error(p5_validate_population_contract(ids, split, bad_queries), "population contract")
  duplicate <- ids; duplicate[[1001L]] <- duplicate[[1L]]
  expect_error(p5_validate_population_contract(duplicate, split, config), "population contract")
})

testthat::test_that("P5 target declaration excludes P6, maintenance and GPU dependencies", {
  path <- testthat::test_path("..", "..", "targets", "s05_fixed_queries.R")
  text <- paste(readLines(path, warn = FALSE), collapse = "\n")
  expected <- c("s05_query_contract", "s05_query_shard_plan",
                "s05_query_validated_shard", "s05_query_acceptance")
  testthat::expect_true(all(vapply(expected, grepl, logical(1L), x = text, fixed = TRUE)))
  testthat::expect_false(grepl("controller_gpu", text, fixed = TRUE))
  testthat::expect_false(grepl("seoul_data_preprocess", text, fixed = TRUE))
  testthat::expect_false(grepl("training", text, fixed = TRUE))
  testthat::expect_false(grepl("fixed_query_shard_validation", text, fixed = TRUE))
})

testthat::test_that("P5 source registry resolves current library, build, and runner roles", {
  paths <- p5_contract_paths(fuse_test_root)
  expected <- c(
    python = "python/fixed_queries.py",
    cli = "scripts/build_fixed_queries.py",
    runner = "scripts/run_fixed_queries.py"
  )

  testthat::expect_length(paths, 13L)
  testthat::expect_true(all(file.exists(paths)))
  testthat::expect_true(all(file.info(paths)$size > 0))
  testthat::expect_identical(
    unname(paths[names(expected)]),
    unname(normalizePath(file.path(fuse_test_root, expected), mustWork = TRUE))
  )
  testthat::expect_false(any(endsWith(paths, "scripts/fixed_queries.py")))

  schema_paths <- paths[grepl("^config/schemas/.*[.]json$", sub(
    paste0("^", normalizePath(fuse_test_root, mustWork = TRUE), "/"), "", paths
  ))]
  testthat::expect_length(schema_paths, 5L)
  testthat::expect_true(all(vapply(schema_paths, function(path) {
    is.list(jsonlite::read_json(path, simplifyVector = FALSE))
  }, logical(1L))))
  testthat::expect_true(is.list(yaml::read_yaml(paths[["config"]])))

  runner <- paste(readLines(paths[["runner"]], warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl('root / "scripts/build_fixed_queries.py"', runner, fixed = TRUE))
  testthat::expect_false(grepl('root / "scripts/fixed_queries.py"', runner, fixed = TRUE))
})

testthat::test_that("P5 scientific implementation hash excludes execution environment", {
  helper <- paste(readLines(testthat::test_path("..", "..", "R", "fixed_queries.R"), warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl("implementation_hash", helper, fixed = TRUE))
  testthat::expect_true(grepl("scientific_config$publication_root <- NULL", helper, fixed = TRUE))
  testthat::expect_true(grepl("scientific_config$execution <- NULL", helper, fixed = TRUE))
  testthat::expect_false(grepl("Sys.info", helper, fixed = TRUE))
  testthat::expect_false(grepl("hostname", helper, fixed = TRUE))
})
