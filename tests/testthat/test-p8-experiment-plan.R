testthat::test_that("P8 target family is plan-only and ordered", {
  manifest <- targets::tar_manifest(
    fields = c(name, command), script = file.path(fuse_test_root, "_targets.R"),
    callr_arguments = list(wd = fuse_test_root)
  )
  required <- c(
    "p8_methodology_compatibility", "hyperparameter_configuration_matrix",
    "comparison_variant_template_matrix", "experiment_augmentation_bank_index",
    "formal_hyperparameter_experiment_plan", "comparison_variant_materialization_template",
    "formal_experiment_plan_acceptance"
  )
  testthat::expect_true(all(required %in% manifest$name))
  commands <- manifest$command[manifest$name %in% required]
  testthat::expect_false(any(grepl("optimizer|p9.*training|p10|p11|evaluation_query|maintenance", commands, ignore.case = TRUE)))
})

testthat::test_that("P8 config binds canonical lineage and attempt accounting", {
  cfg <- yaml::read_yaml(file.path(fuse_test_root, "config/p8_formal_experiment_plan.yml"))
  testthat::expect_identical(cfg$parents$p7_acceptance_id, "p7acc_3c78cc0e85b93aec6a0cc02c")
  testthat::expect_identical(cfg$parents$p7_best_checkpoint_id, "p7ck_7d25fec7944dc108c5849cd7")
  testthat::expect_identical(cfg$parents$p7_runtime_acceptance_id, "p7rta_c780441a553abe26772827d0")
  testthat::expect_identical(cfg$run_accounting$hyperparameter_attempts, 13L)
  testthat::expect_identical(cfg$run_accounting$comparison_attempts, 7L)
  testthat::expect_identical(cfg$run_accounting$total_attempts, 20L)
  testthat::expect_identical(cfg$run_accounting$main_training_duplication, 0L)
  testthat::expect_false(cfg$execution_prohibitions$evaluation_ancestry)
  testthat::expect_identical(cfg$execution_prohibitions$optimizer_updates, 0L)
})
