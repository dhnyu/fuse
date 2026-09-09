testthat::test_that("P5 supplement fixes namespaces, populations and query indices", {
  config <- yaml::read_yaml(testthat::test_path("..", "..", "config", "p5_deterministic_queries.yml"))
  testthat::expect_identical(config$supplement_id, "p5-fixed-query-v2")
  testthat::expect_identical(config$schema_version, "1.0.0")
  testthat::expect_identical(config$profile$profile_id, "main_1.0x")
  testthat::expect_identical(as.integer(unlist(config$query_indices)), c(0L, 1L))
  testthat::expect_identical(config$namespaces$validation$namespace, "validation-query")
  testthat::expect_identical(config$namespaces$evaluation$namespace, "evaluation-query")
  testthat::expect_identical(as.integer(config$namespaces$validation$queries), 2000L)
  testthat::expect_identical(as.integer(config$namespaces$evaluation$queries), 18000L)
  testthat::expect_identical(config$publication$training_bank_membership, "prohibited")
  testthat::expect_identical(config$p4_supplement_id, "p4-augmentation-v2")
  testthat::expect_identical(config$p4_master_bank_id, "dynamic_from_augmentation_bank_acceptance")
  testthat::expect_identical(config$p4_logical_index_id, "dynamic_from_effective_augmentation_bank_index")
})

testthat::test_that("P5 enforces exact current split, query, gallery, and identity counts", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/p5_deterministic_queries.yml"))
  ids <- sprintf("scene-%05d", seq_len(10000L))
  split <- c(rep("validation", 1000L), rep("evaluation", 9000L))
  expect_silent(p5_validate_population_contract(ids, split, config))
  expect_error(p5_validate_population_contract(ids[1:2000], c(rep("validation", 400), rep("evaluation", 1600)), config), "population contract")
  expect_error(p5_validate_population_contract(ids, c(rep("validation", 999), rep("evaluation", 9001)), config), "population contract")
  bad_queries <- config; bad_queries$namespaces$evaluation$queries <- 17999L
  expect_error(p5_validate_population_contract(ids, split, bad_queries), "population contract")
  duplicate <- ids; duplicate[[1001L]] <- duplicate[[1L]]
  expect_error(p5_validate_population_contract(duplicate, split, config), "population contract")
})

testthat::test_that("P5 target declaration excludes P6, maintenance and GPU dependencies", {
  path <- testthat::test_path("..", "..", "targets", "s05_fixed_queries.R")
  text <- paste(readLines(path, warn = FALSE), collapse = "\n")
  expected <- c("s05_query_contract", "s05_query_shard_plan",
                "s05_query_validated_shard", "s05_query_acceptance")
  testthat::expect_true(all(vapply(expected, grepl, logical(1L), x = text, fixed = TRUE)))
  testthat::expect_false(grepl("controller_gpu", text, fixed = TRUE))
  testthat::expect_false(grepl("seoul_data_preprocess", text, fixed = TRUE))
  testthat::expect_false(grepl("training", text, fixed = TRUE))
  testthat::expect_false(grepl("fixed_query_shard_validation", text, fixed = TRUE))
})

testthat::test_that("P5 source registry resolves current library, build, and runner roles", {
  paths <- p5_contract_paths(fuse_test_root)
  expected <- c(
    python = "python/fixed_queries.py",
    cli = "scripts/build_fixed_queries.py",
    runner = "scripts/run_fixed_queries.py"
  )

  testthat::expect_length(paths, 13L)
  testthat::expect_true(all(file.exists(paths)))
  testthat::expect_true(all(file.info(paths)$size > 0))
  testthat::expect_identical(
    unname(paths[names(expected)]),
    unname(normalizePath(file.path(fuse_test_root, expected), mustWork = TRUE))
  )
  testthat::expect_false(any(endsWith(paths, "scripts/fixed_queries.py")))

  schema_paths <- paths[grepl("^config/schemas/.*[.]json$", sub(
    paste0("^", normalizePath(fuse_test_root, mustWork = TRUE), "/"), "", paths
  ))]
  testthat::expect_length(schema_paths, 5L)
  testthat::expect_true(all(vapply(schema_paths, function(path) {
    is.list(jsonlite::read_json(path, simplifyVector = FALSE))
  }, logical(1L))))
  testthat::expect_true(is.list(yaml::read_yaml(paths[["config"]])))

  runner <- paste(readLines(paths[["runner"]], warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl('root / "scripts/build_fixed_queries.py"', runner, fixed = TRUE))
  testthat::expect_false(grepl('root / "scripts/fixed_queries.py"', runner, fixed = TRUE))
})

testthat::test_that("P5 path normalization preserves source roles and order", {
  paths <- p5_contract_paths(fuse_test_root)
  normalized <- p5_normalize_contract_files(paths, fuse_test_root)

  testthat::expect_identical(names(normalized), names(paths))
  testthat::expect_identical(
    unname(normalized),
    unname(normalizePath(paths, mustWork = TRUE))
  )
  testthat::expect_identical(
    normalized[["python"]],
    normalizePath(file.path(fuse_test_root, "python/fixed_queries.py"), mustWork = TRUE)
  )
  testthat::expect_identical(
    normalized[["cli"]],
    normalizePath(file.path(fuse_test_root, "scripts/build_fixed_queries.py"), mustWork = TRUE)
  )
  testthat::expect_identical(
    normalized[["runner"]],
    normalizePath(file.path(fuse_test_root, "scripts/run_fixed_queries.py"), mustWork = TRUE)
  )
})

testthat::test_that("P5 source role validation fails closed", {
  paths <- p5_contract_paths(fuse_test_root)

  unnamed <- p5_normalize_contract_files(unname(paths), fuse_test_root)
  testthat::expect_identical(unnamed, p5_normalize_contract_files(paths, fuse_test_root))
  testthat::expect_identical(
    p5_normalize_contract_files(unname(rev(paths)), fuse_test_root),
    p5_normalize_contract_files(paths, fuse_test_root)
  )

  wrong_names <- paths
  names(wrong_names) <- paste0("wrong_", seq_along(wrong_names))
  testthat::expect_identical(
    p5_normalize_contract_files(wrong_names, fuse_test_root),
    p5_normalize_contract_files(paths, fuse_test_root)
  )
  testthat::expect_error(
    p5_normalize_contract_files(paths[names(paths) != "runner"], fuse_test_root),
    "does not exactly match canonical paths"
  )
  duplicate <- paths
  names(duplicate)[names(duplicate) == "cli"] <- "runner"
  testthat::expect_error(
    p5_normalize_contract_files(duplicate, fuse_test_root),
    "duplicate source roles"
  )
  stale <- paths
  stale[["runner"]] <- file.path(fuse_test_root, "scripts/fixed_queries.py")
  testthat::expect_error(
    p5_normalize_contract_files(stale, fuse_test_root),
    "retired scripts/fixed_queries.py"
  )

  extra <- c(paths, extra = paths[["runner"]])
  testthat::expect_error(
    p5_normalize_contract_files(extra, fuse_test_root),
    "duplicate paths"
  )

  extra_path <- tempfile(fileext = ".txt")
  writeLines("extra", extra_path)
  testthat::expect_error(
    p5_normalize_contract_files(c(paths, extra = extra_path), fuse_test_root),
    "does not exactly match canonical paths"
  )

  ambiguous <- paths
  ambiguous[["runner"]] <- ambiguous[["cli"]]
  testthat::expect_error(
    p5_normalize_contract_files(paths, fuse_test_root, ambiguous),
    "ambiguous paths"
  )

  canonical_without_runner <- paths[names(paths) != "runner"]
  testthat::expect_error(
    p5_normalize_contract_files(canonical_without_runner, fuse_test_root,
                                canonical_without_runner),
    "missing required roles: runner"
  )
})

testthat::test_that("P5 loaded spec retains executable role lookups", {
  withr::local_dir(fuse_test_root)
  paths <- p5_contract_paths(fuse_test_root)
  spec <- p5_load_spec(paths, fuse_test_root)
  representative_branch <- list(
    branch_id = "fqb_fixture", query_authority_id = "fqa_fixture",
    implementation_hash = spec$implementation_hash
  )

  testthat::expect_identical(names(spec$files), names(paths))
  testthat::expect_identical(basename(spec$files[["python"]]), "fixed_queries.py")
  testthat::expect_identical(basename(spec$files[["cli"]]), "build_fixed_queries.py")
  testthat::expect_identical(basename(spec$files[["runner"]]), "run_fixed_queries.py")
  testthat::expect_identical(representative_branch$implementation_hash, spec$implementation_hash)
  testthat::expect_identical(
    spec$implementation_hash,
    "7bf8b45dd687d33aa6bd9d42cd2bad1b447d008577f3eebd73ce1cbe86489c82"
  )
})

testthat::test_that("P5 restores roles after a targets file-vector round trip", {
  fixture_root <- tempfile("p5-file-vector-")
  dir.create(fixture_root)
  script <- file.path(fixture_root, "_targets.R")
  store <- file.path(fixture_root, "_targets")
  writeLines(c(
    "library(targets)",
    sprintf("source(%s)", encodeString(file.path(fuse_test_root, "R/fixed_queries.R"), quote = "\"")),
    sprintf("root <- %s", encodeString(fuse_test_root, quote = "\"")),
    "list(",
    "  tar_target(p5_fixture_sources, p5_contract_paths(root), format = \"file\"),",
    "  tar_target(p5_fixture_roles, {",
    "    names_were_absent <- is.null(names(p5_fixture_sources))",
    "    restored <- p5_normalize_contract_files(p5_fixture_sources, root)",
    "    list(names_were_absent = names_were_absent, files = restored,",
    "         runner = restored[[\"runner\"]])",
    "  })",
    ")"
  ), script)

  targets::tar_make(
    names = p5_fixture_roles, script = script, store = store,
    callr_function = NULL, reporter = "silent"
  )
  restored_sources <- targets::tar_read_raw("p5_fixture_sources", store = store)
  result <- targets::tar_read_raw("p5_fixture_roles", store = store)

  testthat::expect_null(names(restored_sources))
  testthat::expect_true(result$names_were_absent)
  testthat::expect_identical(names(result$files), names(p5_contract_paths(fuse_test_root)))
  testthat::expect_identical(
    result$runner,
    normalizePath(file.path(fuse_test_root, "scripts/run_fixed_queries.py"), mustWork = TRUE)
  )
})

testthat::test_that("P5 canonicalizes JSON-equivalent seed contracts strictly", {
  seed <- yaml::read_yaml(file.path(fuse_test_root, "config/p5_deterministic_queries.yml"))$seed
  path <- tempfile(fileext = ".json")
  jsonlite::write_json(seed, path, auto_unbox = TRUE, pretty = TRUE)
  round_trip <- jsonlite::read_json(path, simplifyVector = FALSE)

  testthat::expect_false(identical(seed, round_trip))
  testthat::expect_identical(
    p5_canonical_seed_contract(seed),
    p5_canonical_seed_contract(round_trip)
  )
  testthat::expect_identical(
    p5_canonical_seed_contract(rev(seed)),
    p5_canonical_seed_contract(seed)
  )

  wrong_root <- round_trip
  wrong_root$root_fields[[1L]] <- "wrong_schema_version"
  testthat::expect_false(identical(
    p5_canonical_seed_contract(wrong_root),
    p5_canonical_seed_contract(seed)
  ))
  missing_root <- round_trip
  missing_root$root_fields <- missing_root$root_fields[-1L]
  testthat::expect_false(identical(
    p5_canonical_seed_contract(missing_root),
    p5_canonical_seed_contract(seed)
  ))
  extra_root <- round_trip
  extra_root$root_fields <- c(extra_root$root_fields, list("extra"))
  testthat::expect_false(identical(
    p5_canonical_seed_contract(extra_root),
    p5_canonical_seed_contract(seed)
  ))
  wrong_operation <- round_trip
  wrong_operation$operation_context_fields[[2L]] <- "wrong_entity_id"
  testthat::expect_false(identical(
    p5_canonical_seed_contract(wrong_operation),
    p5_canonical_seed_contract(seed)
  ))
  reordered_array <- round_trip
  reordered_array$root_fields <- rev(reordered_array$root_fields)
  testthat::expect_false(identical(
    p5_canonical_seed_contract(reordered_array),
    p5_canonical_seed_contract(seed)
  ))
  missing_field <- seed
  missing_field$missing_sentinel <- NULL
  testthat::expect_error(p5_canonical_seed_contract(missing_field), "missing: missing_sentinel")
  extra_field <- seed
  extra_field$unknown <- "value"
  testthat::expect_error(p5_canonical_seed_contract(extra_field), "extra: unknown")

  nested_a <- list(z = list(beta = "b", alpha = "a"), a = "root")
  nested_b <- list(a = "root", z = list(alpha = "a", beta = "b"))
  testthat::expect_identical(
    p5_canonical_json_value(nested_a),
    p5_canonical_json_value(nested_b)
  )
})

testthat::test_that("P5 validation evidence accepts JSON seed shape only", {
  seed <- yaml::read_yaml(file.path(fuse_test_root, "config/p5_deterministic_queries.yml"))$seed
  branch <- list(
    branch_id = "fqb_seed_fixture", split = "validation",
    namespace = "validation-query", config = list(seed = seed)
  )
  write_receipt <- function(receipt) {
    directory <- tempfile("p5-validation-receipt-")
    dir.create(directory)
    path <- file.path(directory, "validation_receipt.json")
    jsonlite::write_json(receipt, path, auto_unbox = TRUE, pretty = TRUE)
    path
  }
  receipt <- list(
    status = "PASS", branch_id = branch$branch_id, split = branch$split,
    namespace = branch$namespace, seed = seed,
    validation = list(status = "PASS")
  )

  path <- write_receipt(receipt)
  testthat::expect_identical(
    p5_validation_evidence(list(path), list(branch)),
    list(list(status = "PASS"))
  )

  wrong_seed <- receipt
  wrong_seed$seed$root_fields[[1L]] <- "wrong_schema_version"
  testthat::expect_error(
    p5_validation_evidence(list(write_receipt(wrong_seed)), list(branch)),
    "seed mismatch"
  )
  missing_root <- receipt
  missing_root$seed$root_fields <- missing_root$seed$root_fields[-1L]
  testthat::expect_error(
    p5_validation_evidence(list(write_receipt(missing_root)), list(branch)),
    "seed mismatch"
  )
  extra_root <- receipt
  extra_root$seed$root_fields <- c(extra_root$seed$root_fields, "extra")
  testthat::expect_error(
    p5_validation_evidence(list(write_receipt(extra_root)), list(branch)),
    "seed mismatch"
  )
  wrong_operation <- receipt
  wrong_operation$seed$operation_context_fields[[1L]] <- "wrong_operation"
  testthat::expect_error(
    p5_validation_evidence(list(write_receipt(wrong_operation)), list(branch)),
    "seed mismatch"
  )
  wrong_namespace <- receipt
  wrong_namespace$namespace <- "evaluation-query"
  testthat::expect_error(
    p5_validation_evidence(list(write_receipt(wrong_namespace)), list(branch)),
    "identity/split mismatch"
  )
})

testthat::test_that("P5 scientific implementation hash excludes execution environment", {
  helper <- paste(readLines(testthat::test_path("..", "..", "R", "fixed_queries.R"), warn = FALSE), collapse = "\n")
  testthat::expect_true(grepl("implementation_hash", helper, fixed = TRUE))
  testthat::expect_true(grepl("scientific_config$publication_root <- NULL", helper, fixed = TRUE))
  testthat::expect_true(grepl("scientific_config$execution <- NULL", helper, fixed = TRUE))
  testthat::expect_false(grepl("Sys.info", helper, fixed = TRUE))
  testthat::expect_false(grepl("hostname", helper, fixed = TRUE))
})
