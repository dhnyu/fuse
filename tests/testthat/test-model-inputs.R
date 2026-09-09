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

p6_cache_fixture <- function(root = tempfile("p6-cache-root-"), cache_id = "oscache_fixture",
                             index_id = "oci_fixture", nested = FALSE) {
  generation <- file.path(root, cache_id)
  acceptance_dir <- if (nested) {
    file.path(generation, "arbitrary", "nested", "acceptance", "osca_fixture")
  } else {
    file.path(generation, "acceptance", "osca_fixture")
  }
  manifest_dir <- if (nested) file.path(generation, "arbitrary", "manifests") else file.path(generation, "manifests")
  index_dir <- file.path(generation, "index", index_id)
  dir.create(acceptance_dir, recursive = TRUE)
  dir.create(manifest_dir, recursive = TRUE)
  dir.create(index_dir, recursive = TRUE)
  acceptance <- file.path(acceptance_dir, "original_scene_dataset_acceptance.json")
  manifest <- file.path(manifest_dir, "original_scene_cache_manifest.json")
  index <- file.path(index_dir, "scene_to_shard.parquet")
  index_manifest <- file.path(index_dir, "index_manifest.json")
  write_json_file(list(
    status = "PASS", acceptance_id = "osca_fixture", cache_id = cache_id,
    scene_count = 12421L
  ), acceptance)
  write_json_file(list(
    status = "PASS", cache_id = cache_id, index_id = index_id,
    scene_count = 12421L
  ), manifest)
  writeLines("fixture-index", index)
  write_json_file(list(
    status = "PASS", cache_id = cache_id, index_id = index_id,
    scene_count = 12421L
  ), index_manifest)
  list(
    root = root, generation = generation, paths = c(manifest, acceptance),
    acceptance = acceptance, manifest = manifest, index = index,
    index_manifest = index_manifest
  )
}

testthat::test_that("P6 resolves the explicit accepted P3 cache generation", {
  fixture <- p6_cache_fixture()
  dir.create(file.path(fixture$root, "oscache_historical_sibling"))
  resolved <- p6_resolve_p3_cache_generation(fixture$paths)

  testthat::expect_identical(resolved$root, normalizePath(fixture$generation))
  testthat::expect_identical(resolved$cache_id, "oscache_fixture")
  testthat::expect_identical(resolved$index_id, "oci_fixture")
  testthat::expect_identical(resolved$index_path, normalizePath(fixture$index))
})

testthat::test_that("P6 P3 root resolution is independent of acceptance nesting depth", {
  fixture <- p6_cache_fixture(nested = TRUE)
  resolved <- p6_resolve_p3_cache_generation(fixture$paths)
  testthat::expect_identical(resolved$root, normalizePath(fixture$generation))
})

testthat::test_that("P6 P3 cache generation resolution fails closed", {
  fixture <- p6_cache_fixture()

  acceptance <- jsonlite::read_json(fixture$acceptance, simplifyVector = FALSE)
  acceptance$cache_id <- "oscache_wrong"
  write_json_file(acceptance, fixture$acceptance)
  testthat::expect_error(
    p6_resolve_p3_cache_generation(fixture$paths),
    "accepted cache identity mismatch"
  )

  fixture <- p6_cache_fixture()
  unlink(fixture$generation, recursive = TRUE)
  testthat::expect_error(
    p6_resolve_p3_cache_generation(fixture$paths),
    "artifact path is missing"
  )

  first <- p6_cache_fixture()
  second <- p6_cache_fixture(cache_id = "oscache_fixture")
  mixed <- c(first$acceptance, second$manifest)
  testthat::expect_error(
    p6_resolve_p3_cache_generation(mixed),
    "resolve exactly one generation"
  )

  fixture <- p6_cache_fixture()
  unlink(dirname(dirname(fixture$index)), recursive = TRUE)
  testthat::expect_error(
    p6_resolve_p3_cache_generation(fixture$paths),
    "index directory is missing"
  )

  fixture <- p6_cache_fixture()
  unlink(fixture$index)
  testthat::expect_error(
    p6_resolve_p3_cache_generation(fixture$paths),
    "exactly one scene index"
  )

  fixture <- p6_cache_fixture()
  unlink(fixture$index_manifest)
  testthat::expect_error(
    p6_resolve_p3_cache_generation(fixture$paths),
    "scene index manifest is missing"
  )

  fixture <- p6_cache_fixture()
  duplicate_dir <- file.path(fixture$generation, "index", "oci_duplicate")
  dir.create(duplicate_dir, recursive = TRUE)
  writeLines("duplicate", file.path(duplicate_dir, "scene_to_shard.parquet"))
  testthat::expect_error(
    p6_resolve_p3_cache_generation(fixture$paths),
    "exactly one scene index"
  )

  fixture <- p6_cache_fixture()
  index_manifest <- jsonlite::read_json(fixture$index_manifest, simplifyVector = FALSE)
  index_manifest$cache_id <- "oscache_wrong"
  write_json_file(index_manifest, fixture$index_manifest)
  testthat::expect_error(
    p6_resolve_p3_cache_generation(fixture$paths),
    "cache/index identity mismatch"
  )
})
