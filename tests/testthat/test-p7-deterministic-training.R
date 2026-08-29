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
    "p7_training_contract_files", "p7_validation_query_reference", "p7_p6_parent_reference",
    "p7_immutable_parent_reference",
    "p7_deterministic_training_authority",
    "p7_geometry_feature_cache",
    "p7_ddp_initialization_smoke", "p7_single_update_smoke",
    "p7_ddp_reference_acceptance", "p7_resume_equivalence",
    "prototype_training_run", "prototype_validation_retrieval",
    "prototype_checkpoint_selection", "prototype_training_execution_record",
    "prototype_training_acceptance"
  )
  testthat::expect_true(all(required %in% manifest$name))
  command <- manifest$command[manifest$name == "prototype_training_acceptance"]
  testthat::expect_length(command, 1L)
  testthat::expect_false(grepl("evaluation|maintenance|p8", command, ignore.case = TRUE))
})
