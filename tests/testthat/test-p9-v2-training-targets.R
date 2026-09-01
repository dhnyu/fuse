test_that("P9 v2 training graph is isolated and contains executable lifecycle targets", {
  skip_if_not_installed("targets")
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old <- Sys.getenv("P9_V2_TRAINING_AUTHORITY", unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv("P9_V2_TRAINING_AUTHORITY") else Sys.setenv(P9_V2_TRAINING_AUTHORITY = old))
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/research_p9_v2_training.R", local = TRUE)
  source("targets/research_p9_v2_training.R", local = TRUE)
  names <- vapply(list_p9_v2_training, function(x) x$name, character(1))
  expect_length(names, 9)
  expect_setequal(names, c(
    "p9v2_training_contract", "p9v2_training_authority", "p9v2_startup_preflight", "p9v2_closed_ledger", "p9v2_run_bundle",
    "p9v2_finalization_result", "p9v2_acceptance_commit", "p9v2_eligibility_snapshot", "p9v2_accepted_checkpoint"
  ))
  expect_false(any(grepl("p9_b|p10|p11|evaluation|maintenance|recovery|reservation|attempt", names)))
  manifest <- targets::tar_manifest(script = "_targets_p9_v2_training.R", fields = c("name", "command"))
  command <- manifest$command[manifest$name == "p9v2_accepted_checkpoint"]
  expect_match(command, "p9v2_resolve_accepted_checkpoint")
  commands <- paste(manifest$command, collapse = "\n")
  expect_false(grepl("p9v2_declared_artifact|P9_V2_RUN_BUNDLE_MANIFEST|P9_V2_FINALIZATION_RESULT", commands))
  expect_true(all(vapply(c("p9v2_bundle", "p9v2_finalize", "p9v2_accept", "p9v2_eligibility"),
    function(name) grepl(name, commands, fixed = TRUE), logical(1))))
  functions <- paste(readLines("R/research_p9_v2_training.R", warn = FALSE), collapse = "\n")
  expect_match(functions, "canonical_publication")
  Sys.unsetenv("P9_V2_TRAINING_AUTHORITY")
  expect_error(p9v2_training_authority_path(), "P9_V2_TRAINING_AUTHORITY_REQUIRED")
})

test_that("P9 v2 campaign can supply an explicit external contract", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  source(file.path(root, "R", "research_p9_v2_training.R"), local = TRUE)
  path <- tempfile(fileext = ".yml")
  writeLines("schema_version: '2.0.0'", path)
  withr::local_envvar(P9_V2_TRAINING_CONTRACT = path)
  expect_identical(p9v2_training_contract_path(), normalizePath(path, mustWork = TRUE))
})
