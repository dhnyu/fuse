testthat::test_that("P9 formal target lineage is explicit and training-free", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  body <- paste(readLines(file.path(root, "targets/research_p9_formal_authorization.R"), warn = FALSE), collapse = "\n")
  required <- c(
    "p9_formal_accepted_parent_references", "p9_cache_reuse_graph", "p9_cache_identity_contract",
    "p9_cache_resource_plan", "p9_cache_shard_plan", "p9_production_cache_build_authority",
    "p9_production_cache_materialization", "p9_production_cache_validation",
    "p9_production_cache_acceptance", "p9_formal_training_authority", "p9_cfg_main_attempt_reservation"
  )
  testthat::expect_true(all(vapply(required, grepl, logical(1), x = body, fixed = TRUE)))
  testthat::expect_false(grepl("optimizer|tar_make|train_update", body))
  testthat::expect_match(body, "p9_formal_artifact\\(p9_formal_publication_bundle, \"p9_formal_training_authority.json\", p9_production_cache_acceptance\\)")
})

testthat::test_that("heavy cache target requires explicit authority", {
  root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
  source(file.path(root, "R/research_p9_formal_authorization.R"), local = TRUE)
  fake <- tempfile(fileext = ".json")
  jsonlite::write_json(list(artifact_id = "p9cba_test"), fake, auto_unbox = TRUE)
  old <- Sys.getenv("FUSE_P9_CACHE_BUILD_AUTHORITY_ID", unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv("FUSE_P9_CACHE_BUILD_AUTHORITY_ID") else Sys.setenv(FUSE_P9_CACHE_BUILD_AUTHORITY_ID = old))
  Sys.unsetenv("FUSE_P9_CACHE_BUILD_AUTHORITY_ID")
  testthat::expect_error(p9_materialize_production_cache(fake, c(file.path(root, "config/p9_formal_authorization.yml"))), "explicit")
})
