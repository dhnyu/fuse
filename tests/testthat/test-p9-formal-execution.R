testthat::test_that("formal P9 target chain is explicit and reservation-gated", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  target_source <- paste(readLines(file.path(root, "targets/research_p9_formal_authorization.R")), collapse = "\n")
  helper_source <- paste(readLines(file.path(root, "R/research_p9_formal_authorization.R")), collapse = "\n")
  required <- c(
    "p9_corrected_formal_training_authority", "p9_corrected_cfg_main_attempt_reservation",
    "p9_cfg_main_formal_run", "p9_cfg_main_validation_trace",
    "p9_cfg_main_checkpoint_candidates", "p9_cfg_main_selected_checkpoint",
    "p9_cfg_main_terminal_execution", "p9_cfg_main_attempt_acceptance"
  )
  testthat::expect_true(all(vapply(required, grepl, logical(1), x = target_source, fixed = TRUE)))
  testthat::expect_match(helper_source, "FUSE_P9_FORMAL_RESERVATION_ID", fixed = TRUE)
  testthat::expect_match(helper_source, "output already exists", fixed = TRUE)
  testthat::expect_false(grepl("tar_make", helper_source, fixed = TRUE))
})

testthat::test_that("formal target dependency direction reaches terminal acceptance", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  source <- paste(readLines(file.path(root, "targets/research_p9_formal_authorization.R")), collapse = "\n")
  positions <- vapply(c("p9_cfg_main_formal_run", "p9_cfg_main_validation_trace",
    "p9_cfg_main_checkpoint_candidates", "p9_cfg_main_selected_checkpoint",
    "p9_cfg_main_terminal_execution", "p9_cfg_main_attempt_acceptance"),
    function(name) regexpr(name, source, fixed = TRUE)[[1L]], integer(1))
  testthat::expect_true(all(diff(positions) > 0L))
})
