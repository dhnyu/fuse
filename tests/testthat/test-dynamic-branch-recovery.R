testthat::test_that("dynamic recovery file fixture rejects stale, foreign, and colliding bundles", {
  root <- tempfile("dynamic-recovery-")
  dir.create(root)
  on.exit(unlink(root, recursive = TRUE), add = TRUE)
  payload <- file.path(root, "payload.bin")
  writeBin(charToRaw("accepted"), payload)
  record <- list(path = payload, size_bytes = file.info(payload)$size, sha256 = recovery_sha256(payload))
  testthat::expect_identical(validate_recovery_file_record(record), normalizePath(payload))
  testthat::expect_silent(validate_exact_directory_entries(root, "payload.bin"))

  writeBin(charToRaw("stale"), payload)
  testthat::expect_error(validate_recovery_file_record(record), "RECOVERY_VALIDATION_FAILED.*size mismatch")
  writeBin(charToRaw("accepted"), payload)
  writeLines("foreign", file.path(root, "foreign.bin"))
  testthat::expect_error(validate_exact_directory_entries(root, "payload.bin"),
                         "RECOVERY_VALIDATION_FAILED.*foreign or incomplete")
  unlink(file.path(root, "foreign.bin"))
  collision <- record
  collision$sha256 <- paste(rep("0", 64L), collapse = "")
  testthat::expect_error(validate_recovery_file_record(collision),
                         "RECOVERY_VALIDATION_FAILED.*checksum mismatch")
})

testthat::test_that("dynamic branch recovery fast paths never force compute promises", {
  old <- Sys.getenv("FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY", unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv("FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY") else
    Sys.setenv(FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY = old), add = TRUE)
  Sys.setenv(FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY = "1")
  counter_log <- tempfile("dynamic-recovery-counts-")
  old_log <- Sys.getenv("FUSE_DYNAMIC_RECOVERY_COUNTER_LOG", unset = NA_character_)
  on.exit(if (is.na(old_log)) Sys.unsetenv("FUSE_DYNAMIC_RECOVERY_COUNTER_LOG") else
    Sys.setenv(FUSE_DYNAMIC_RECOVERY_COUNTER_LOG = old_log), add = TRUE)
  on.exit(unlink(counter_log), add = TRUE)
  Sys.setenv(FUSE_DYNAMIC_RECOVERY_COUNTER_LOG = counter_log)
  reset_dynamic_recovery_counts()
  fallback <- 0L

  raster <- recover_raster_observation_branch(
    list(), character(), character(), character(),
    compute = { fallback <- fallback + 1L; stop("compute called") },
    validator = function(...) "raster-path"
  )
  serialization <- recover_serialization_branch(
    list(), character(), compute = { fallback <- fallback + 1L; stop("compute called") },
    validator = function(...) "serialization-path"
  )
  testthat::expect_identical(raster, "raster-path")
  testthat::expect_identical(serialization, "serialization-path")
  testthat::expect_identical(fallback, 0L)
  counts <- dynamic_recovery_count_snapshot()
  testthat::expect_identical(counts[["raster_fast_path"]], 1L)
  testthat::expect_identical(counts[["serialization_fast_path"]], 1L)
  testthat::expect_true(all(counts[setdiff(names(counts), c("raster_fast_path", "serialization_fast_path"))] == 0L))
})

testthat::test_that("validation failure is fail-closed and does not enter compute fallback", {
  old <- Sys.getenv("FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY", unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv("FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY") else
    Sys.setenv(FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY = old), add = TRUE)
  Sys.setenv(FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY = "1")
  fallback <- 0L
  testthat::expect_error(
    recover_raster_observation_branch(
      list(), character(), character(), character(),
      compute = { fallback <- fallback + 1L; "computed" },
      validator = function(...) recovery_validation_error("fixture rejection")
    ),
    "RECOVERY_VALIDATION_FAILED: fixture rejection"
  )
  testthat::expect_identical(fallback, 0L)
})

testthat::test_that("accepted raster and serialization branches pass read-only validation", {
  store <- targets::tar_config_get("store", config = file.path(fuse_test_root, "_targets.yaml"))
  serialization_plan <- targets::tar_read(prototype_serialization_plan, store = store)
  testthat::skip_if_not(
    identical(serialization_plan[[1L]]$serialization_dataset_id, "psd_aa295747ee7814efbd1d177c"),
    "legacy zero-compute recovery integration fixture is not the active scientific lineage"
  )
  raster <- validate_raster_branch_recovery(
    targets::tar_read(prototype_observation_plan, store = store)[[1L]],
    targets::tar_read(prototype_vector_observation_shard, store = store)[[1L]],
    targets::tar_read(study_data_inputs, store = store),
    targets::tar_read(raster_observation_contract_files, store = store)
  )
  serialization <- validate_serialization_branch_recovery(
    serialization_plan[[1L]],
    targets::tar_read(serialization_shard_contract_files, store = store)
  )
  testthat::expect_length(raster, 6L)
  testthat::expect_length(serialization, 6L)
})

testthat::test_that("accepted training dataset passes zero-compute aggregate validation", {
  store <- targets::tar_config_get("store", config = file.path(fuse_test_root, "_targets.yaml"))
  serialization_plan <- targets::tar_read(prototype_serialization_plan, store = store)
  testthat::skip_if_not(
    identical(serialization_plan[[1L]]$serialization_dataset_id, "psd_aa295747ee7814efbd1d177c"),
    "legacy zero-compute recovery integration fixture is not the active scientific lineage"
  )
  files <- validate_training_dataset_recovery(
    serialization_plan,
    targets::tar_read(prototype_serialization_shard, store = store),
    targets::tar_read(prototype_spatial_acceptance, store = store),
    targets::tar_read(training_dataset_acceptance_contract_files, store = store)
  )
  testthat::expect_length(files, 7L)
  fallback <- 0L
  old <- Sys.getenv("FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY", unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv("FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY") else
    Sys.setenv(FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY = old), add = TRUE)
  Sys.setenv(FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY = "1")
  recovered <- recover_training_dataset_acceptance(
    list(), list(), list(), list(),
    compute = { fallback <- fallback + 1L; stop("compute called") },
    validator = function(...) "dataset-path"
  )
  testthat::expect_identical(recovered, "dataset-path")
  testthat::expect_identical(fallback, 0L)
})
