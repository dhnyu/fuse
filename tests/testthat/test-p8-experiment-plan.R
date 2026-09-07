testthat::test_that("P8 target family is exactly two static file replay targets", {
  manifest <- targets::tar_manifest(
    fields = c(name, command, format, pattern), script = file.path(fuse_test_root, "_targets.R"),
    callr_arguments = list(wd = fuse_test_root)
  )
  old <- c(
    "p8_experiment_plan_contract_files", "p8_experiment_plan_bundle",
    "p8_methodology_compatibility", "hyperparameter_configuration_matrix",
    "a5_generic_relation_mapping_contract", "ds_raster_materialization_contract",
    "comparison_variant_template_matrix", "experiment_augmentation_bank_index",
    "formal_hyperparameter_experiment_plan", "comparison_variant_materialization_template",
    "formal_experiment_plan_acceptance"
  )
  required <- c("s08_experiment_sources", "s08_experiment_plan")
  testthat::expect_setequal(grep("^s08_|^p8_", manifest$name, value = TRUE), required)
  testthat::expect_false(any(old %in% manifest$name))
  testthat::expect_equal(nrow(manifest), 154L)
  testthat::expect_true(all(manifest$format[manifest$name %in% required] == "file"))
  testthat::expect_true(all(is.na(manifest$pattern[manifest$name %in% required])))
  commands <- manifest$command[manifest$name %in% required]
  testthat::expect_false(any(grepl("optimizer|p9.*training|p10|p11|evaluation_query|maintenance", commands, ignore.case = TRUE)))
  network <- targets::tar_network(targets_only = TRUE, outdated = FALSE,
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root))
  edges <- network$edges[network$edges$from %in% required | network$edges$to %in% required, c("from", "to")]
  testthat::expect_equal(nrow(edges), 1L)
  testthat::expect_identical(edges$from, "s08_experiment_sources")
  testthat::expect_identical(edges$to, "s08_experiment_plan")
})

testthat::test_that("P8 synthetic replay fixtures fail closed without scientific execution", {
  output <- suppressWarnings(system2(research_python_executable(),
    c("-B", shQuote(file.path(fuse_test_root, "tests/python/test_p8_plan_replay.py"))),
    stdout = TRUE, stderr = TRUE))
  status <- attr(output, "status")
  testthat::expect_true(is.null(status) || status == 0L, info = paste(output, collapse = "\n"))
})

testthat::test_that("P8 R replay orchestration has no builder or publication fallback", {
  env <- new.env(parent = globalenv())
  sys.source(file.path(fuse_test_root, "R/research_p8_experiment_plan.R"), envir = env)
  for (name in c("p8_replay_sources", "p8_replay_bundle", "p8_validate_parent_lineage")) {
    calls <- all.names(body(env[[name]]), functions = TRUE)
    testthat::expect_false(any(c("p8_build_bundle", "publish_deterministic_directory",
      "file.copy", "writeLines", "saveRDS", "eval", "get") %in% calls))
  }
  testthat::expect_match(paste(deparse(body(env$p8_replay_bundle)), collapse = " "),
                        "python/p8_plan_replay.py", fixed = TRUE)
})

testthat::test_that("historical P9 symbols stay outside the active P8 DAG", {
  code <- parse(file.path(fuse_test_root, "targets/research_p9_formal_authorization.R"))
  active <- code[[length(code)]]
  testthat::expect_identical(as.character(active[[2L]]), "list_research_p9_formal_authorization")
  calls <- all.names(active, functions = TRUE)
  testthat::expect_true("p9_v1_retired_stop" %in% calls)
  testthat::expect_false("hyperparameter_configuration_matrix" %in% calls)
  testthat::expect_false("list_research_p9_formal_authorization_historical" %in% calls)
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
