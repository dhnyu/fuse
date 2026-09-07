testthat::test_that("P7 deterministic supplement fixes the approved execution contract", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p7_deterministic_training.yml"))

  testthat::expect_identical(config$supplement_name, "p7-deterministic-training-v1")
  testthat::expect_identical(config$training$root_seed, 20260828L)
  testthat::expect_identical(config$training$global_batch_size, 32L)
  testthat::expect_identical(config$training$world_size, 2L)
  testthat::expect_identical(config$training$per_rank_batch_size, 16L)
  testthat::expect_identical(config$training$maximum_updates, 1600L)
  testthat::expect_identical(config$numeric$backend, "nccl")
  testthat::expect_false(config$numeric$amp)
  testthat::expect_false(config$numeric$tf32_matmul)
  testthat::expect_true(config$numeric$deterministic_algorithms)
  testthat::expect_identical(config$queue$capacity, 8192L)
  testthat::expect_identical(config$validation$evaluation_consumption, "prohibited")
})

testthat::test_that("P7 final target ancestry is bounded to the approved gates", {
  manifest <- targets::tar_manifest(
    fields = c(name, command), script = file.path(fuse_test_root, "_targets.R"),
    callr_arguments = list(wd = fuse_test_root)
  )
  required <- c(
    "s07_training_sources", "i05_validation_query_sources", "i06_accepted_model_sources",
    "i07_training_input_sources",
    "s07_pilot_training_authority",
    "s07_training_geometry_cache",
    "s07_ddp_initialization_validation", "s07_ddp_update_validation",
    "s07_ddp_reference_validation", "s07_ddp_resume_validation",
    "s07_pilot_training_execution", "s07_pilot_training_acceptance",
    "s07_pilot_training_acceptance", "s07_pilot_training_acceptance",
    "s07_pilot_training_acceptance"
  )
  testthat::expect_true(all(required %in% manifest$name))
  command <- manifest$command[manifest$name == "s07_pilot_training_acceptance"]
  testthat::expect_length(command, 1L)
  testthat::expect_false(grepl("evaluation|maintenance|p8", command, ignore.case = TRUE))
})
