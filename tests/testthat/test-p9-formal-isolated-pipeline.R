testthat::test_that("isolated P9 manifest contains only bindings, authorization, and formal chain", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old <- getwd(); on.exit(setwd(old), add = TRUE); setwd(root)
  manifest <- targets::tar_manifest(script = "_targets_p9_formal.R", fields = c("name", "command"))
  expected_formal <- c("p9_cfg_main_formal_run", "p9_cfg_main_validation_trace",
    "p9_cfg_main_checkpoint_candidates", "p9_cfg_main_selected_checkpoint",
    "p9_cfg_main_terminal_execution", "p9_cfg_main_attempt_acceptance")
  testthat::expect_true(all(expected_formal %in% manifest$name))
  testthat::expect_false(any(c("p9_production_cache_materialization",
    "p7_cold_path_runtime_acceptance", "hyperparameter_configuration_matrix") %in% manifest$name))
  testthat::expect_equal(sum(manifest$name %in% expected_formal), 6L)
})

testthat::test_that("empty-store synthetic bootstrap is bounded and repeats as a no-op", {
  testthat::skip_if_not_installed("targets")
  root <- tempfile("p9-isolated-synthetic-"); dir.create(root)
  store <- file.path(root, "store"); input <- file.path(root, "accepted.json")
  writeLines('{"identity":"accepted","value":3}', input)
  script <- file.path(root, "_targets.R")
  token <- "synthetic-reservation"
  writeLines(c(
    "library(targets)",
    "tar_option_set(error = 'stop')",
    sprintf("root_path <- %s", encodeString(input, quote = '"')),
    "list(",
    "  tar_target(accepted_root, {x <- jsonlite::read_json(root_path); if (x$identity != 'accepted') stop('root mismatch'); root_path}, format='file'),",
    sprintf("  tar_target(authorization, {if (Sys.getenv('FUSE_TEST_TOKEN') != %s) stop('token mismatch'); accepted_root}),", encodeString(token, quote = '"')),
    "  tar_target(synthetic_run, {x <- 0; for (i in seq_len(4)) x <- x + i; list(formal_attempt=FALSE, updates=x)}),",
    "  tar_target(terminal_fixture, {stopifnot(!synthetic_run$formal_attempt); synthetic_run$updates})",
    ")"
  ), script)
  old <- Sys.getenv("FUSE_TEST_TOKEN", unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv("FUSE_TEST_TOKEN") else Sys.setenv(FUSE_TEST_TOKEN = old), add = TRUE)
  Sys.setenv(FUSE_TEST_TOKEN = token)
  targets::tar_make(script = script, store = store, names = terminal_fixture, shortcut = FALSE,
    callr_function = NULL, reporter = "silent")
  target_names <- c("accepted_root", "authorization", "synthetic_run", "terminal_fixture")
  first <- targets::tar_meta(store = store, fields = c("name", "time", "data"))
  first <- first[first$name %in% target_names, , drop = FALSE]
  targets::tar_make(script = script, store = store, names = terminal_fixture, shortcut = TRUE,
    callr_function = NULL, reporter = "silent")
  second <- targets::tar_meta(store = store, fields = c("name", "time", "data"))
  second <- second[second$name %in% target_names, , drop = FALSE]
  testthat::expect_equal(first, second)
  writeLines('{"identity":"mutated","value":3}', input)
  testthat::expect_true("accepted_root" %in% targets::tar_outdated(script = script, store = store,
    callr_function = NULL))
  targets::tar_make(script = script, store = store, names = terminal_fixture,
    shortcut = FALSE, callr_function = NULL, reporter = "silent")
  failed <- targets::tar_meta(store = store, fields = c("name", "error"))
  testthat::expect_false("accepted_root" %in% failed$name)
  after_failure <- targets::tar_meta(store = store, fields = c("name", "time", "data"))
  after_failure <- after_failure[after_failure$name %in% c("authorization", "synthetic_run", "terminal_fixture"), , drop = FALSE]
  testthat::expect_equal(second[second$name != "accepted_root", , drop = FALSE], after_failure)
})
