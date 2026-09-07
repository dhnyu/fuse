testthat::test_that("downstream families expose one sources and one output target", {
  scripts <- c(
    diagnostics = "_targets_s11_diagnostics.R",
    dataset = "_targets_s11_downstream.R",
    ridge = "_targets_s11_ridge.R",
    readiness = "_targets_s11_readiness.R"
  )
  expected <- list(
    diagnostics = c("s11_diagnostic_sources", "s11_diagnostic_acceptance"),
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

testthat::test_that("tracked downstream sources fail closed on missing input", {
  testthat::expect_error(
    p11_existing_sources("/definitely/missing/downstream-input"),
    "tracked source missing"
  )
})
