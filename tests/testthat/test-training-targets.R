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
  expect_identical(manifest$pattern[manifest$name == "s09_ofat_authority"], "map(s09_ofat_authorities)")
  expect_identical(manifest$pattern[manifest$name == "s09_comparison_authority"], "map(s09_comparison_authorities)")
  expect_match(manifest$command[manifest$name == "s09_ofat_winner"], "s09_ofat_result")
  expect_match(manifest$command[manifest$name == "s09_comparison_authorities"], "s09_ofat_winner")
  expect_match(manifest$command[manifest$name == "s09_prepared_cache_acceptance"], "s09_build_prepared_cache")

  formats <- targets::tar_manifest(script = "_targets_training.R", fields = c("name", "format"))
  expect_identical(formats$format[formats$name == "s09_ofat_authorities"], "rds")
  expect_identical(formats$format[formats$name == "s09_ofat_authority"], "file")
  expect_identical(formats$format[formats$name == "s09_comparison_authorities"], "rds")
  expect_identical(formats$format[formats$name == "s09_comparison_authority"], "file")

  network <- targets::tar_network(script = "_targets_training.R", targets_only = TRUE)$edges
  has_edge <- function(from, to) any(network$from == from & network$to == to)
  expect_true(has_edge("s09_prepared_cache_acceptance", "s09_ofat_authorities"))
  expect_true(has_edge("s09_ofat_result", "s09_ofat_winner"))
  expect_true(has_edge("s09_ofat_winner", "s09_comparison_authorities"))
  expect_true(has_edge("s09_comparison_result", "s09_campaign_acceptance"))
})

test_that("training authority collections branch legally through winner and comparison barriers", {
  skip_if_not_installed("targets")
  root <- tempfile("s09-branch-fixture-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE, force = TRUE), add = TRUE)
  script <- file.path(root, "_targets.R")
  store <- file.path(root, "store")
  output <- file.path(root, "output")

  quote_path <- function(path) encodeString(path, quote = "\"")
  writeLines(c(
    "library(targets)",
    sprintf("output <- %s", quote_path(output)),
    "publish <- function(phase, ids) {",
    "  paths <- file.path(output, phase, paste0(ids, '.json'))",
    "  dir.create(dirname(paths[[1L]]), recursive = TRUE, showWarnings = FALSE)",
    "  for (index in seq_along(paths)) writeLines(ids[[index]], paths[[index]])",
    "  paths",
    "}",
    "list(",
    "  tar_target(prepared_cache, 'cache-ready'),",
    "  tar_target(ofat_authorities, {prepared_cache; publish('ofat', sprintf('ofat-%02d', 1:11))}),",
    "  tar_target(ofat_authority, ofat_authorities, pattern = map(ofat_authorities), format = 'file'),",
    "  tar_target(ofat_result, paste0(readLines(ofat_authority), '-accepted'), pattern = map(ofat_authority)),",
    "  tar_target(winner, {stopifnot(length(ofat_result) == 11L); 'winner'}),",
    "  tar_target(comparison_authorities, {winner; publish('comparison', sprintf('comparison-%02d', 1:17))}),",
    "  tar_target(comparison_authority, comparison_authorities, pattern = map(comparison_authorities), format = 'file'),",
    "  tar_target(comparison_result, paste0(readLines(comparison_authority), '-accepted'), pattern = map(comparison_authority)),",
    "  tar_target(campaign, {stopifnot(length(comparison_result) == 17L); 'accepted'})",
    ")"
  ), script)

  expect_silent(targets::tar_validate(script = script))
  expect_silent(targets::tar_make(
    names = campaign,
    script = script,
    store = store,
    callr_function = NULL,
    reporter = "silent"
  ))
  expect_length(targets::tar_read(ofat_authority, store = store, branches = TRUE), 11L)
  expect_length(targets::tar_read(ofat_result, store = store, branches = TRUE), 11L)
  expect_identical(targets::tar_read(winner, store = store), "winner")
  expect_length(targets::tar_read(comparison_authority, store = store, branches = TRUE), 17L)
  expect_length(targets::tar_read(comparison_result, store = store, branches = TRUE), 17L)
  expect_identical(targets::tar_read(campaign, store = store), "accepted")
})

test_that("downstream authority branching changes do not invalidate prepared cache", {
  skip_if_not_installed("targets")
  root <- tempfile("s09-cache-currentness-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE, force = TRUE), add = TRUE)
  script <- file.path(root, "_targets.R")
  store <- file.path(root, "store")
  cache <- file.path(root, "cache.json")
  quote_path <- function(path) encodeString(path, quote = "\"")

  fixture_script <- function(marker) c(
    "library(targets)",
    sprintf("cache <- %s", quote_path(cache)),
    sprintf("marker <- %s", quote_path(marker)),
    "list(",
    "  tar_target(prepared_cache, {if (!file.exists(cache)) writeLines('cache', cache); cache}, format = 'file'),",
    "  tar_target(authorities, {prepared_cache; c('authority-1', 'authority-2')}),",
    "  tar_target(authority, paste0(authorities, marker), pattern = map(authorities))",
    ")"
  )
  writeLines(fixture_script("-v1"), script)
  expect_silent(targets::tar_make(
    names = prepared_cache,
    script = script,
    store = store,
    callr_function = NULL,
    reporter = "silent"
  ))
  cache_hash <- targets::tar_meta(
    prepared_cache,
    store = store,
    fields = data
  )$data

  writeLines(fixture_script("-v2"), script)
  outdated <- targets::tar_outdated(script = script, store = store)
  expect_false("prepared_cache" %in% outdated)
  expect_true(all(c("authorities", "authority") %in% outdated))
  expect_identical(
    targets::tar_meta(prepared_cache, store = store, fields = data)$data,
    cache_hash
  )
})

test_that("current training source registry and operator are explicit", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/training_targets.R", local = TRUE)
  sources <- s09_training_source_files()
  expect_true(all(file.exists(sources)))
  expect_true(any(basename(sources) == "training_progress.py"))
  expect_identical(s09_training_contract_path(), normalizePath("config/training_controller.yml"))
  contract <- yaml::read_yaml("config/training_controller.yml")
  expect_identical(contract$execution$progress_log_root, "logs/s09")
  expect_identical(contract$execution$maximum_epochs, 200L)
  expect_identical(contract$execution$maximum_updates, 15200L)
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
