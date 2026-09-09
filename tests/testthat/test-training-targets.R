test_that("current training graph is isolated and contains executable lifecycle targets", {
  skip_if_not_installed("targets")
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old <- Sys.getenv("FUSE_TRAINING_AUTHORITY", unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv("FUSE_TRAINING_AUTHORITY") else Sys.setenv(FUSE_TRAINING_AUTHORITY = old))
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/training_targets.R", local = TRUE)
  source("targets/s09_training.R", local = TRUE)
  names <- vapply(list_s09_training, function(x) x$name, character(1))
  expect_length(names, 9)
  expect_setequal(names, c(
    "s09_training_contract", "s09_training_authority", "s09_startup_preflight", "s09_closed_ledger", "s09_run_bundle",
    "s09_finalization_result", "s09_acceptance_commit", "s09_eligibility_snapshot", "s09_accepted_checkpoint"
  ))
  expect_false(any(grepl("p9_b|p10|p11|evaluation|maintenance|recovery|reservation|attempt", names)))
  manifest <- targets::tar_manifest(script = "_targets_training.R", fields = c("name", "command"))
  expect_silent(targets::tar_validate(script = "_targets_training.R"))
  command <- manifest$command[manifest$name == "s09_accepted_checkpoint"]
  expect_match(command, "s09_resolve_accepted_checkpoint")
  commands <- paste(manifest$command, collapse = "\n")
  expect_false(grepl("s09_declared_artifact|FUSE_TRAINING_RUN_BUNDLE_MANIFEST|FUSE_TRAINING_FINALIZATION_RESULT", commands))
  expect_true(all(vapply(c("s09_bundle", "s09_finalize", "s09_accept", "s09_eligibility"),
    function(name) grepl(name, commands, fixed = TRUE), logical(1))))
  functions <- paste(readLines("R/training_targets.R", warn = FALSE), collapse = "\n")
  expect_match(functions, "canonical_publication")
  Sys.unsetenv("FUSE_TRAINING_AUTHORITY")
  expect_error(s09_training_authority_path(), "FUSE_TRAINING_AUTHORITY_REQUIRED")
})

test_that("current training can supply an explicit external contract", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  source(file.path(root, "R", "training_targets.R"), local = TRUE)
  path <- tempfile(fileext = ".yml")
  writeLines("schema_version: '2.0.0'", path)
  withr::local_envvar(FUSE_TRAINING_CONTRACT = path)
  expect_identical(s09_training_contract_path(), normalizePath(path, mustWork = TRUE))
})

test_that("current training requires an explicit current experiment plan", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  text <- paste(readLines(file.path(root, "R", "training_targets.R"), warn = FALSE), collapse = "\n")
  expect_match(text, "cfg\\$roots\\$experiment_plan")
  expect_match(text, "CURRENT_EXPERIMENT_PLAN_REQUIRED", fixed = TRUE)
})
