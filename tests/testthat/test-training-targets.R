test_that("current training graph encodes OFAT winner and comparison barriers", {
  skip_if_not_installed("targets")
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/training_targets.R", local = TRUE); source("targets/s09_training.R", local = TRUE)
  names <- vapply(list_s09_training, function(x) x$name, character(1))
  expect_setequal(names, c(
    "s09_training_sources", "s09_training_contract", "s09_current_experiment_plan",
    "s09_prepared_cache_acceptance", "s09_resolved_contract", "s09_ofat_authorities",
    "s09_ofat_authority", "s09_ofat_preflight", "s09_ofat_closed_ledger",
    "s09_ofat_run_bundle", "s09_ofat_finalization", "s09_ofat_acceptance",
    "s09_ofat_eligibility", "s09_ofat_accepted_checkpoint", "s09_ofat_result",
    "s09_ofat_winner", "s09_comparison_authorities", "s09_comparison_authority",
    "s09_comparison_preflight", "s09_comparison_closed_ledger", "s09_comparison_run_bundle",
    "s09_comparison_finalization", "s09_comparison_acceptance", "s09_comparison_eligibility",
    "s09_comparison_accepted_checkpoint", "s09_comparison_result",
    "s09_campaign_acceptance"
  ))
  manifest <- targets::tar_manifest(script = "_targets_training.R", fields = c("name", "command", "pattern"))
  expect_silent(targets::tar_validate(script = "_targets_training.R"))
  expect_match(manifest$command[manifest$name == "s09_ofat_winner"], "s09_ofat_result")
  expect_match(manifest$command[manifest$name == "s09_comparison_authorities"], "s09_ofat_winner")
  expect_match(manifest$command[manifest$name == "s09_prepared_cache_acceptance"], "s09_build_prepared_cache")
})

test_that("current training source registry and operator are explicit", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/training_targets.R", local = TRUE)
  expect_true(all(file.exists(s09_training_source_files())))
  expect_identical(s09_training_contract_path(), normalizePath("config/training_controller.yml"))
  operator <- paste(readLines("scripts/run_training_targets.R", warn = FALSE), collapse = "\n")
  expect_match(operator, "fuse-training-s09", fixed = TRUE)
  expect_match(operator, "s09_campaign_acceptance", fixed = TRUE)
})

test_that("worker matrices preserve eleven rows and route comparison authorities", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/training_targets.R", local = TRUE)
  plan <- yaml::read_yaml("config/training_controller.yml")$roots$experiment_plan
  authority <- list(content = list(scientific = list(
    phase = "COMPARISON", configuration_id = "cmp_A1", model_id = "A1",
    plan_configuration_hash = paste(rep("a", 64L), collapse = ""),
    hyperparameters = list(d = 128L, d_c = 128L, K_aug = 8L,
      augmentation_intensity = 1, ema_momentum = 0.999, peak_learning_rate = 0.001))))
  path <- tempfile(fileext = ".json")
  jsonlite::write_json(authority, path, auto_unbox = TRUE)
  matrix <- s09_worker_matrix_value(plan, path)
  expect_length(matrix$hyperparameter_configurations, 11L)
  row <- matrix$hyperparameter_configurations[[1L]]
  expect_identical(row$configuration_id, "cmp_A1")
  expect_identical(row$model_family, "A1")
  expect_identical(row$scientific_hash, authority$content$scientific$plan_configuration_hash)
  expect_equal(row$scientific$ema, 0.999)
})
