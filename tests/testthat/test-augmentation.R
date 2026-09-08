testthat::test_that("P4 supplement fixes the approved population and prefixes", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p4_deterministic_augmentation.yml"))
  testthat::expect_identical(config$supplement_version, "p4-augmentation-v2")
  testthat::expect_identical(config$population$split, "training")
  testthat::expect_identical(as.integer(config$population$scenes), 2421L)
  testthat::expect_identical(as.integer(config$banks$physical_k), 16L)
  testthat::expect_identical(as.integer(unlist(config$banks$logical_prefixes)), c(2L, 4L, 8L, 16L))
  testthat::expect_identical(as.integer(config$banks$expected_physical_candidates), 116208L)
  testthat::expect_identical(as.integer(config$banks$expected_default_references), 58104L)
})
testthat::test_that("P4 profile parameters exactly reproduce Appendix B", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p4_deterministic_augmentation.yml"))
  observed <- lapply(config$profiles, function(x) unname(as.numeric(unlist(x[c(
    "scale", "removal_fraction", "jitter_probability", "jitter_displacement_m",
    "simplification_tolerance_m", "categorical_mask_probability",
    "categorical_replacement_probability", "lane_probability",
    "landcover_mask_fraction", "dem_noise_sd_m"
  )]))))
  expected <- list(
    c(.5, .05, .10, .5, .5, .05, .05, .05, .05, .5),
    c(1, .10, .20, 1, 1, .10, .10, .10, .10, 1),
    c(2, .20, .40, 2, 2, .20, .20, .20, .20, 2)
  )
  testthat::expect_identical(observed, expected)
})

testthat::test_that("P4 provenance is bound to the current scientifically identical authority", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p4_deterministic_augmentation.yml"))
  authority_path <- "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/authority/mta_7875c4ba4587e4877ba0be1d/reduced_methodology_authority.json"
  module_path <- "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/authority/mta_7875c4ba4587e4877ba0be1d/augmentation_methodology_contract.json"
  authority <- jsonlite::read_json(authority_path, simplifyVector = FALSE)
  module <- jsonlite::read_json(module_path, simplifyVector = FALSE)
  authority$authority_id <- config$provenance_reconciliation$current_authority_id
  expect_invisible(p4_assert_current_augmentation_contract(authority, module, config))
  stale <- config; stale$dissertation_commit <- "109355b3d744248ca14749c5f74511537970d660"
  expect_error(p4_assert_current_augmentation_contract(authority, module, stale), "scientifically identical")
  expect_identical(config$dissertation_commit, "cbb824f19be8355296603f8426ac241ce587ddcc")
  expect_identical(config$provenance_reconciliation$scientific_change, FALSE)
})

testthat::test_that("P4 target declarations use only the fixed bank interface", {
  path <- testthat::test_path("..", "..", "targets", "s04_augmentation.R")
  text <- paste(readLines(path, warn = FALSE), collapse = "\n")
  expected <- c("s04_bank_profile_plan", "s04_bank_road_validation",
                "s04_bank_geometry_validation", "s04_bank_shard_plan",
                "s04_bank_execution", "s04_bank_validated_shard",
                "s04_bank_acceptance")
  testthat::expect_true(all(vapply(expected, grepl, logical(1L), x = text, fixed = TRUE)))
  testthat::expect_false(grepl("controller_gpu", text, fixed = TRUE))
  testthat::expect_false(grepl("seoul_data_preprocess", text, fixed = TRUE))
  testthat::expect_false(grepl("fixed_validation_query", text, fixed = TRUE))
  testthat::expect_false(grepl("augmentation_bank_shard_validation", text, fixed = TRUE))
})

testthat::test_that("P4 tiered execution is tracked but excluded from scientific identity", {
  helper <- paste(readLines(testthat::test_path("..", "..", "R", "augmentation.R"),
                            warn = FALSE), collapse = "\n")
  targets <- paste(readLines(testthat::test_path("..", "..", "targets", "s04_augmentation.R"),
                             warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl('relative != "scripts/run_augmentation_bank.py"', helper, fixed = TRUE))
  testthat::expect_true(grepl("p4_run_tiered_bank_current(s04_bank_shard_plan", targets, fixed = TRUE))
  testthat::expect_true(grepl("controller_05", targets, fixed = TRUE))
  testthat::expect_true(grepl("seconds_timeout = 21600", targets, fixed = TRUE))
  testthat::expect_true(grepl("Pass A requires all 288 intended branches",
                              paste(readLines(testthat::test_path("..", "..", "scripts", "run_augmentation_bank.py"),
                                              warn = FALSE), collapse = "\n"), fixed = TRUE))
})

testthat::test_that("P4 tiered execution summary is deterministic and fail-closed", {
  ledger <- function(statuses) {
    branches <- Map(function(id, status) list(branch_id = id, status = status),
                    sprintf("ab_%02d", seq_along(statuses)), statuses)
    levels <- p4_tiered_status_levels()
    list(
      pass = "A", branches = branches,
      status_counts = setNames(lapply(levels, function(x) sum(statuses == x)), levels)
    )
  }
  pass <- ledger(rep("COMPLETED", 3L))
  first <- p4_summarize_tiered_execution(pass, "bank", "plan", "pass_a_ledger.json",
                                         c("ab_01", "ab_02", "ab_03"))
  second <- p4_summarize_tiered_execution(pass, "bank", "plan", "pass_a_ledger.json",
                                          c("ab_01", "ab_02", "ab_03"))
  testthat::expect_identical(first, second)
  testthat::expect_identical(first$status, "PASS")
  testthat::expect_identical(first$final_completed, 3L)
  testthat::expect_error(
    p4_summarize_tiered_execution(ledger(c("COMPLETED", "FAILED_SCIENTIFIC")),
                                  "bank", "plan", "pass_a_ledger.json", c("ab_01", "ab_02")),
    "ab_02"
  )
  testthat::expect_error(
    p4_summarize_tiered_execution(list(pass = "A", branches = list(), status_counts = list()),
                                  "bank", "plan", character(), "ab_01"),
    "no branch results"
  )
})

testthat::test_that("P4 runner status must agree with the published ledger", {
  statuses <- c("COMPLETED", "FAILED_RESOURCE")
  levels <- p4_tiered_status_levels()
  ledger <- list(
    branches = Map(function(id, status) list(branch_id = id, status = status),
                   c("ab_01", "ab_02"), statuses),
    status_counts = setNames(lapply(levels, function(x) sum(statuses == x)), levels)
  )
  testthat::expect_silent(p4_assert_tiered_pass(ledger, 1L, "A", "fixture.log"))
  testthat::expect_error(p4_assert_tiered_pass(ledger, 0L, "A", "fixture.log"),
                         "exit status disagrees")
  failed <- ledger
  failed$branches[[2L]]$status <- "FAILED_SCIENTIFIC"
  failed$status_counts <- setNames(lapply(levels, function(x) {
    sum(vapply(failed$branches, function(row) row$status == x, logical(1L)))
  }), levels)
  testthat::expect_error(p4_assert_tiered_pass(failed, 2L, "A", "fixture.log"), "ab_02")
})

testthat::test_that("P4 existing canonical branch inspection is read-only", {
  root <- tempfile("p4-existing-")
  dir.create(root)
  branch <- list(branch_id = "ab_fixture", bank_id = "bank_fixture", output_directory = root)
  payload <- file.path(root, "ab_fixture.tar")
  writeBin(charToRaw("fixture-payload"), payload)
  write_json_file(list(
    branch_id = branch$branch_id, bank_id = branch$bank_id,
    payload = list(filename = basename(payload), size_bytes = unname(file.info(payload)$size),
                   sha256 = sha256_file(payload)),
    validation = list(schema = "PASS", writer = "PASS", global_invariants = "PASS")
  ), file.path(root, "branch_manifest.json"))
  write_json_file(list(pass = "A", pid = 1L, requested_workers = 40L, threads = 1L,
                       wall_seconds = 1), file.path(root, "execution.json"))
  before <- vapply(list.files(root, full.names = TRUE), sha256_file, character(1L))
  state <- p4_existing_bank_branch_state(branch)
  after <- vapply(list.files(root, full.names = TRUE), sha256_file, character(1L))
  testthat::expect_identical(state$status, "VALID")
  testthat::expect_identical(before, after)
  unlink(payload)
  testthat::expect_identical(p4_existing_bank_branch_state(branch)$status, "INCOMPLETE")
})

testthat::test_that("P4 operational execution changes do not alter scientific implementation identity", {
  old <- setwd(fuse_test_root)
  on.exit(setwd(old), add = TRUE)
  base <- p4_contract_paths(getwd())
  operational <- c(base, file.path(fuse_test_root, "R/bank_execution.R"))
  testthat::expect_identical(p4_load_spec(base, getwd())$implementation_hash,
                             p4_load_spec(operational, getwd())$implementation_hash)
})
