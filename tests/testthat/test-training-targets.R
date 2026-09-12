test_that("campaign summary preserves validated model order rather than path order", {
  env <- new.env(parent = globalenv())
  sys.source(file.path("..", "..", "R", "training_targets.R"), envir = env)
  root <- tempfile("ordered-summary-"); dir.create(root)
  on.exit(unlink(root, recursive = TRUE), add = TRUE)
  files <- file.path(root, c("z.json", "a.json"))
  for (path in files) jsonlite::write_json(list(plan_id = "plan", acceptance_id = "cache",
                                              winner_id = "winner"), path)
  contract <- file.path(root, "contract.yml")
  yaml::write_yaml(list(roots = list(canonical_publication = root)), contract)
  env$s09_campaign_cli <- function(mode, ...) {
    if (mode == "campaign-validate") list(comparison_result_paths = as.list(files))
    else list(status = "PASS")
  }
  captured <- NULL
  env$s09_write_json <- function(value, path) { captured <<- value; path }
  env$s09_accept_campaign(files[1], files[1], rev(files), files[1], contract,
                          list(implementation_sha256 = "runtime"))
  expect_identical(captured$comparison_acceptance_records, normalizePath(files))
})

test_that("current training graph encodes OFAT winner and comparison barriers", {
  skip_if_not_installed("targets")
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/training_targets.R", local = TRUE); source("targets/s09_training.R", local = TRUE)
  names <- vapply(list_s09_training, function(x) x$name, character(1))
  expect_setequal(names, c(
    "s09_prepared_cache_sources", "s09_runtime_sources", "s09_runtime_implementation",
    "s09_training_contract", "s09_current_experiment_plan",
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
  expect_match(manifest$command[manifest$name == "s09_ofat_authorities"], "s09_runtime_implementation")
  expect_match(manifest$command[manifest$name == "s09_comparison_authorities"], "s09_runtime_implementation")

  formats <- targets::tar_manifest(script = "_targets_training.R", fields = c("name", "format"))
  expect_identical(formats$format[formats$name == "s09_ofat_authorities"], "rds")
  expect_identical(formats$format[formats$name == "s09_ofat_authority"], "file")
  expect_identical(formats$format[formats$name == "s09_comparison_authorities"], "rds")
  expect_identical(formats$format[formats$name == "s09_comparison_authority"], "file")

  network <- targets::tar_network(script = "_targets_training.R", targets_only = TRUE)$edges
  has_edge <- function(from, to) any(network$from == from & network$to == to)
  expect_true(has_edge("s09_prepared_cache_sources", "s09_prepared_cache_acceptance"))
  expect_false(has_edge("s09_runtime_sources", "s09_prepared_cache_acceptance"))
  expect_true(has_edge("s09_runtime_sources", "s09_runtime_implementation"))
  expect_true(has_edge("s09_runtime_implementation", "s09_ofat_authorities"))
  expect_true(has_edge("s09_prepared_cache_acceptance", "s09_ofat_authorities"))
  expect_true(has_edge("s09_ofat_result", "s09_ofat_winner"))
  expect_true(has_edge("s09_runtime_implementation", "s09_ofat_winner"))
  expect_true(has_edge("s09_ofat_winner", "s09_comparison_authorities"))
  expect_true(has_edge("s09_runtime_implementation", "s09_comparison_authorities"))
  expect_true(has_edge("s09_comparison_result", "s09_campaign_acceptance"))
  expect_true(has_edge("s09_runtime_implementation", "s09_campaign_acceptance"))
  expect_match(paste(deparse(body(s09_select_winner)), collapse = " "),
               "runtime_implementation\\$implementation_sha256")
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

test_that("runtime provenance changes invalidate authorities but not prepared cache", {
  skip_if_not_installed("targets")
  root <- tempfile("s09-cache-currentness-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE, force = TRUE), add = TRUE)
  script <- file.path(root, "_targets.R")
  store <- file.path(root, "store")
  cache <- file.path(root, "cache.json")
  cache_source <- file.path(root, "cache-source.txt")
  runtime_source <- file.path(root, "runtime-source.txt")
  quote_path <- function(path) encodeString(path, quote = "\"")
  writeLines("cache-v1", cache_source)
  writeLines("runtime-v1", runtime_source)

  fixture_script <- c(
    "library(targets)",
    "list(",
    sprintf("  tar_target(prepared_sources, %s, format = 'file'),", quote_path(cache_source)),
    sprintf("  tar_target(runtime_sources, %s, format = 'file'),", quote_path(runtime_source)),
    sprintf("  tar_target(prepared_cache, {readLines(prepared_sources); if (!file.exists(%s)) writeLines('cache', %s); %s}, format = 'file'),",
            quote_path(cache), quote_path(cache), quote_path(cache)),
    "  tar_target(cache_acceptance, {prepared_cache; 'cache-accepted'}),",
    "  tar_target(runtime_implementation, readLines(runtime_sources)),",
    "  tar_target(ofat_authorities, {cache_acceptance; paste0('ofat-', runtime_implementation)}),",
    "  tar_target(ofat_run, paste0(ofat_authorities, '-run')),",
    "  tar_target(winner, paste0(ofat_run, '-winner')),",
    "  tar_target(comparison_authorities, paste0(winner, '-', runtime_implementation)),",
    "  tar_target(comparison_run, paste0(comparison_authorities, '-run'))",
    ")"
  )
  writeLines(fixture_script, script)
  expect_silent(targets::tar_make(
    names = comparison_run,
    script = script,
    store = store,
    callr_function = NULL,
    reporter = "silent"
  ))
  metadata <- targets::tar_meta(store = store, fields = c(name, data))
  cache_hash <- metadata$data[metadata$name == "prepared_cache"]

  writeLines("runtime-v2", runtime_source)
  outdated <- targets::tar_outdated(script = script, store = store)
  expect_false(any(c("prepared_sources", "prepared_cache", "cache_acceptance") %in% outdated))
  expect_true(all(c("runtime_sources", "runtime_implementation", "ofat_authorities",
                    "ofat_run", "winner", "comparison_authorities", "comparison_run") %in% outdated))
  expect_identical(
    targets::tar_meta(store = store, fields = c(name, data))$data[
      targets::tar_meta(store = store, fields = name)$name == "prepared_cache"],
    cache_hash
  )
})

test_that("current training source registry and operator are explicit", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/training_targets.R", local = TRUE)
  cache_sources <- s09_prepared_cache_source_files()
  runtime_sources <- s09_runtime_source_files()
  expect_true(all(file.exists(c(cache_sources, runtime_sources))))
  expect_false(any(basename(cache_sources) %in% c("training_worker.py", "training_runtime_inputs.py")))
  expect_true(any(basename(cache_sources) == "training_progress.py"))
  expect_identical(basename(runtime_sources[[1L]]), "s09_runtime_provenance.yml")
  implementation <- s09_resolve_runtime_implementation(runtime_sources)
  expect_false(identical(implementation$implementation_sha256,
                   "0479d8ae41fb22a4c3c2f82360fa2d12cd0f59fd73d8a50ef0868d2eff1cf66d"))
  expect_length(implementation$source_hashes, 18L)
  expect_true(all(c("python/training_family_inputs.py", "python/training_prepared_cache.py") %in%
                    names(implementation$source_hashes)))
  expect_true(all(c("config/training_controller.yml", "python/training_transport.py",
                    "python/ddp_nccl_transport_preflight.py", "scripts/training_controller.py",
                    "python/training_controller.py") %in%
                  names(implementation$source_hashes)))
  expect_length(implementation$authority_source_hashes, 2L)
  expect_identical(s09_training_contract_path(), normalizePath("config/training_controller.yml"))
  contract <- yaml::read_yaml("config/training_controller.yml")
  expect_identical(contract$execution$progress_log_root, "logs/s09")
  expect_identical(contract$execution$maximum_epochs, 200L)
  expect_identical(contract$execution$maximum_updates, 15200L)
  expect_identical(contract$execution$transport$p2p_disable, "1")
  expect_identical(contract$execution$transport$ib_disable, "1")
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
