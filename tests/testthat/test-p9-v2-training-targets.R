test_that("P9 v2 training graph is isolated and contains eight coarse targets", {
  skip_if_not_installed("targets")
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  old <- Sys.getenv("P9_V2_TRAINING_AUTHORITY", unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv("P9_V2_TRAINING_AUTHORITY") else Sys.setenv(P9_V2_TRAINING_AUTHORITY = old))
  old_wd <- getwd(); on.exit(setwd(old_wd), add = TRUE); setwd(root)
  source("R/research_p9_v2_training.R", local = TRUE)
  source("targets/research_p9_v2_training.R", local = TRUE)
  names <- vapply(list_p9_v2_training, function(x) x$name, character(1))
  expect_length(names, 8)
  expect_setequal(names, c(
    "p9v2_training_contract", "p9v2_training_authority", "p9v2_closed_ledger", "p9v2_run_bundle",
    "p9v2_finalization_result", "p9v2_acceptance_commit", "p9v2_eligibility_snapshot", "p9v2_accepted_checkpoint"
  ))
  expect_false(any(grepl("p9_b|p10|p11|evaluation|maintenance|recovery|reservation|attempt", names)))
  manifest <- targets::tar_manifest(script = "_targets_p9_v2_training.R", fields = c("name", "command"))
  command <- manifest$command[manifest$name == "p9v2_accepted_checkpoint"]
  expect_match(command, "p9v2_resolve_accepted_checkpoint")
  Sys.unsetenv("P9_V2_TRAINING_AUTHORITY")
  expect_error(p9v2_training_authority_path(), "P9_V2_TRAINING_AUTHORITY_REQUIRED")
})
