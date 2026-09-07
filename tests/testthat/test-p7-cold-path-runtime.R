testthat::test_that("P7 cold-path runtime remains execution-only and fail-closed", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p7_cold_path_runtime.yml"))

  testthat::expect_identical(config$contract_name, "p7-cold-path-runtime-v1")
  testthat::expect_identical(config$cpu_preparation$worker_tiers, c(32L, 24L, 16L))
  testthat::expect_identical(config$cpu_preparation$start_method, "spawn")
  testthat::expect_identical(config$gpu_producers$producer_count, 2L)
  testthat::expect_identical(config$gpu_producers$batch_size, 1L)
  testthat::expect_identical(config$gpu_producers$assignment, "canonical_index_modulo_2")
  testthat::expect_gte(config$memory_admission$safety_margin_fraction, 0.25)
  testthat::expect_identical(config$scientific_invariants$geometry_layout_version, "3.0.0")
  testthat::expect_identical(config$p8$canonical_acceptance_id, "p7acc_3c78cc0e85b93aec6a0cc02c")
  testthat::expect_identical(config$p8$canonical_checkpoint_id, "p7ck_7d25fec7944dc108c5849cd7")
  testthat::expect_true(config$future_p9$runtime_acceptance_required)
  testthat::expect_false(config$future_p9$old_p7_lineage_allowed)
  testthat::expect_false(config$future_p9$latest_checkpoint_fallback_allowed)
})

testthat::test_that("P7 cold-path runtime target has no training or downstream command", {
  manifest <- targets::tar_manifest(
    fields = c(name, command), script = file.path(fuse_test_root, "_targets.R"),
    callr_arguments = list(wd = fuse_test_root)
  )
  required <- c(
    "s07_runtime_sources", "s07_runtime_acceptance",
    "i07_runtime_validation_sources", "s07_runtime_acceptance"
  )
  testthat::expect_true(all(required %in% manifest$name))
  commands <- manifest$command[manifest$name %in% required]
  testthat::expect_false(any(grepl("s07_pilot_training_execution|p8|p9|evaluation|maintenance", commands,
                                  ignore.case = TRUE)))
})
