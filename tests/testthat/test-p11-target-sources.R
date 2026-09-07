testthat::test_that("P11 families expose one sources and one output target", {
  scripts <- c(
    diagnostics = "_targets_p11_diagnostics.R",
    living = "_targets_p11_living_rematerialization.R",
    dataset = "_targets_p11_preprocessing.R",
    ridge = "_targets_p11_ridge.R",
    readiness = "_targets_p11_spatial_readiness.R"
  )
  expected <- list(
    diagnostics = c("s11_diagnostic_sources", "s11_diagnostic_acceptance"),
    living = c("s11_living_sources", "s11_living_dataset_cache"),
    dataset = c("s11_dataset_sources", "s11_dataset_cache"),
    ridge = c("s11_ridge_sources", "s11_ridge_acceptance"),
    readiness = c("s11_readiness_sources", "s11_readiness_acceptance")
  )
  for (name in names(scripts)) {
    manifest <- targets::tar_manifest(
      script = file.path(fuse_test_root, scripts[[name]]),
      callr_arguments = list(wd = fuse_test_root), fields = c(name, format)
    )
    testthat::expect_identical(manifest$name, expected[[name]])
    testthat::expect_true(all(manifest$format == "file"))
  }
})

testthat::test_that("P11 sources include external payloads and fail on missing input", {
  old <- getwd()
  on.exit(setwd(old), add = TRUE)
  setwd(fuse_test_root)
  bundles <- list(
    p11_diagnostic_source_files(), p11_living_source_files(),
    p11_dataset_source_files(), p11_ridge_source_files(),
    p11_readiness_source_files()
  )
  testthat::expect_true(all(vapply(bundles, function(x) all(file.exists(x)), logical(1L))))
  testthat::expect_true(any(vapply(unlist(bundles), dir.exists, logical(1L))))
  testthat::expect_true(any(grepl("spatial_scene_index[.]parquet$", unlist(bundles))))
  testthat::expect_error(p11_existing_sources("/definitely/missing/p11-input"), "tracked source missing")
})

testthat::test_that("P11 file inputs invalidate a tracked output fixture", {
  root <- tempfile("p11-source-store-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE), add = TRUE)
  input <- file.path(root, "input.txt")
  output <- file.path(root, "output.txt")
  script <- file.path(root, "_targets.R")
  store <- file.path(root, "store")
  writeLines("one", input)
  writeLines(c(
    "library(targets)",
    sprintf("input <- %s", encodeString(input, quote = '"')),
    sprintf("output <- %s", encodeString(output, quote = '"')),
    "list(tar_target(sources, input, format='file'),",
    "     tar_target(cache, {writeLines(readLines(sources), output); output}, format='file'))"
  ), script)
  targets::tar_make(script = script, store = store, callr_function = NULL, reporter = "silent")
  writeLines("two", input)
  outdated <- targets::tar_outdated(script = script, store = store, callr_function = NULL)
  testthat::expect_setequal(outdated, c("sources", "cache"))
})
