test_that("Batch E target surface stays fixed", {
  baseline <- jsonlite::read_json(
    file.path(fuse_test_root, "tests/fixtures/batch_e_target_protection.json"),
    simplifyVector = TRUE
  )
  manifest <- targets::tar_manifest(
    fields = c(name, command, format, iteration, pattern),
    script = file.path(fuse_test_root, "_targets.R"),
    callr_arguments = list(wd = fuse_test_root)
  )
  protected <- manifest[match(baseline$name, manifest$name), ]
  expect_false(anyNA(protected$name))
  expect_identical(nrow(protected), 30L)
  expect_identical(protected$name, baseline$name)
  expect_identical(protected$format, baseline$format)
  expect_identical(protected$iteration, baseline$iteration)
  expect_identical(ifelse(is.na(protected$pattern), NA_character_, protected$pattern), baseline$pattern)

  allowed <- c("methodology_contract", "full_membership_plan",
               "prototype_model_validation", "prototype_model_acceptance")
  unchanged <- !baseline$name %in% allowed
  expect_identical(protected$command[unchanged], baseline$command[unchanged])
  expected_primary <- c(
    methodology_contract = "build_methodology_contract",
    full_membership_plan = "build_full_membership_plan",
    prototype_model_validation = "run_prototype_model_validation",
    prototype_model_acceptance = "run_prototype_model_acceptance"
  )
  for (name in allowed) {
    calls <- all.names(parse(text = protected$command[protected$name == name]), functions = TRUE)
    expect_true(expected_primary[[name]] %in% calls, info = name)
  }
  classifications <- setNames(rep("UNCHANGED", 30L), baseline$name)
  classifications[c("full_membership_plan", "prototype_model_validation",
                    "prototype_model_acceptance")] <- "UPSTREAM_SYMBOL_ONLY"
  classifications["methodology_contract"] <- "UPSTREAM_SELECTION_ONLY"
  expect_identical(unname(table(classifications)),
                   unname(table(c(rep("UNCHANGED", 26), rep("UPSTREAM_SYMBOL_ONLY", 3),
                                  "UPSTREAM_SELECTION_ONLY"))))
})

test_that("merged study sources reconstruct the exact old vectors", {
  withr::local_dir(fuse_test_root)
  old_config <- normalizePath(research_config_paths(), mustWork = TRUE)
  old_implementation <- normalizePath(research_implementation_paths(), mustWork = TRUE)
  merged <- c(old_config, old_implementation)
  for (role in c("config", "implementation")) {
    expected <- if (role == "config") old_config else old_implementation
    selected <- select_study_source_files(merged, role)
    expect_identical(selected, expected)
    expect_identical(basename(selected), basename(expected))
    expect_identical(unname(tools::md5sum(selected)), unname(tools::md5sum(expected)))
    expect_identical(vapply(selected, sha256_file, character(1L)),
                     vapply(expected, sha256_file, character(1L)))
  }
  expect_error(select_study_source_files(rev(merged), "config"), "bundle/order mismatch")
})

test_that("protected upstream substitutions retain artifact selectors and argument names", {
  manifest <- targets::tar_manifest(
    fields = c(name, command), script = file.path(fuse_test_root, "_targets.R"),
    callr_arguments = list(wd = fuse_test_root)
  )
  command <- setNames(manifest$command, manifest$name)
  compact <- gsub("[[:space:]]+", " ", command[["methodology_contract"]])
  expect_match(compact,
               'research_config_files = select_study_source_files\\(s01_study_sources, "config"\\)')
  expect_match(compact,
               'research_implementation_files = select_study_source_files\\(s01_study_sources, "implementation"\\)')
  expect_match(command[["full_membership_plan"]], "spatial_scene_index = s01_scene_index")
  expect_match(command[["prototype_model_validation"]],
               "prototype_training_acceptance = s07_pilot_training_acceptance")
  expect_match(command[["prototype_model_validation"]],
               "prototype_scene_selection = s01_pilot_scene_index")
  expect_match(command[["prototype_model_acceptance"]],
               "prototype_training_acceptance = s07_pilot_training_acceptance")
})
