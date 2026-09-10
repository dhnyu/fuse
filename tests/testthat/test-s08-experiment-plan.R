s08_fixture_artifacts <- function(root = tempfile("s08-lineage-")) {
  dir.create(file.path(root, "config"), recursive = TRUE)
  authority <- "mta_aaaaaaaaaaaaaaaaaaaaaaaa"
  p1 <- "sia_bbbbbbbbbbbbbbbbbbbbbbbb"
  p2 <- "bsa_cccccccccccccccccccccccc"
  p3 <- "osca_dddddddddddddddddddddddd"
  cache <- "oscache_eeeeeeeeeeeeeeeeeeeeeeee"
  p4 <- "aba_ffffffffffffffffffffffff"
  bank <- "augbank_111111111111111111111111"
  p5 <- "fqaac_222222222222222222222222"
  p6 <- "mda_333333333333333333333333"
  sha <- paste(rep("4", 64L), collapse = "")
  put <- function(name, value) {
    path <- file.path(root, name)
    dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
    write_json_file(value, path)
  }
  yaml::write_yaml(list(
    schema_version = "1.0.0", revision_token = "mrev_4444444444444444",
    material_revision_declared = FALSE, accepted_authority_id = authority,
    accepted_scientific_contract_sha256 = sha,
    invalidation_policy = "explicit_revision_only"
  ), file.path(root, "config/p0_scientific_revision.yml"))
  paths <- list(
    p0 = put("p0/reduced_methodology_authority.json", list(
      overall_status = "PASS", authority_id = authority, scientific_contract_sha256 = sha
    )),
    p1 = put("p1/scene_index_acceptance.json", list(
      status = "PASS", acceptance_id = p1, authority_id = authority
    )),
    p2 = put("p2/base_spatial_acceptance.json", list(
      status = "PASS", acceptance_id = p2, authority_id = authority, scene_acceptance_id = p1
    )),
    p3 = c(
      put("p3/original_scene_dataset_acceptance.json", list(
        status = "PASS", acceptance_id = p3, cache_id = cache,
        authority_id = authority, base_spatial_acceptance_id = p2
      )),
      put("p3/original_scene_cache_manifest.json", list(
        status = "PASS", cache_id = cache, authority_id = authority,
        base_spatial_acceptance_id = p2
      ))
    ),
    p4 = put("p4/augmentation_bank_acceptance.json", list(
      status = "PASS", acceptance_id = p4, bank_id = bank,
      parent_acceptance_id = p3, parent_cache_id = cache
    )),
    p5 = put("p5/fixed_query_acceptance.json", list(
      status = "PASS", acceptance_id = p5, parent_cache_id = cache
    )),
    p6 = put("p6/model_data_acceptance.json", list(
      status = "PASS", model_data_acceptance_id = p6,
      parents = list(
        authority_id = authority, scene_acceptance_id = p1,
        base_spatial_acceptance_id = p2, p3_acceptance_id = p3,
        p3_cache_id = cache, p4_master_bank_id = bank, p5_acceptance_id = p5
      )
    ))
  )
  c(list(root = root), paths)
}

test_that("S08 current lineage is exact and fail closed", {
  fixture <- s08_fixture_artifacts()
  lineage <- s08_current_lineage(
    fixture$p0, fixture$p1, fixture$p2, fixture$p3,
    fixture$p4, fixture$p5, fixture$p6, fixture$root
  )
  expect_identical(lineage$p0_authority_id, "mta_aaaaaaaaaaaaaaaaaaaaaaaa")
  expect_identical(lineage$p6_acceptance_id, "mda_333333333333333333333333")

  missing <- fixture$p1
  unlink(missing)
  expect_error(s08_current_lineage(
    fixture$p0, missing, fixture$p2, fixture$p3,
    fixture$p4, fixture$p5, fixture$p6, fixture$root
  ), "exactly one readable parent artifact")
})

test_that("S08 plan rejects every altered accepted parent identity", {
  lineage <- list(
    scientific_revision_token = "mrev_426b2b6ce0117943",
    scientific_contract_sha256 = paste(rep("4", 64L), collapse = ""),
    p0_authority_id = "mta_aaaaaaaaaaaaaaaaaaaaaaaa",
    p1_acceptance_id = "sia_bbbbbbbbbbbbbbbbbbbbbbbb",
    p2_acceptance_id = "bsa_cccccccccccccccccccccccc",
    p3_acceptance_id = "osca_dddddddddddddddddddddddd",
    p3_cache_id = "oscache_eeeeeeeeeeeeeeeeeeeeeeee",
    p4_acceptance_id = "aba_ffffffffffffffffffffffff",
    p5_acceptance_id = "fqaac_222222222222222222222222",
    p6_acceptance_id = "mda_333333333333333333333333"
  )
  plan <- s08_plan_value(lineage, fuse_test_root)
  for (field in grep("^(p[0-6]|scientific_revision)", names(lineage), value = TRUE)) {
    changed <- plan
    changed$lineage[[field]] <- paste0(changed$lineage[[field]], "x")
    expect_error(s08_validate_plan(changed, lineage, fuse_test_root), "contract validation")
  }
})

test_that("S08 freezes training and selection semantics", {
  lineage <- list(
    scientific_revision_token = "mrev_426b2b6ce0117943",
    scientific_contract_sha256 = paste(rep("4", 64L), collapse = ""),
    p0_authority_id = "mta_aaaaaaaaaaaaaaaaaaaaaaaa",
    p1_acceptance_id = "sia_bbbbbbbbbbbbbbbbbbbbbbbb",
    p2_acceptance_id = "bsa_cccccccccccccccccccccccc",
    p3_acceptance_id = "osca_dddddddddddddddddddddddd",
    p3_cache_id = "oscache_eeeeeeeeeeeeeeeeeeeeeeee",
    p4_acceptance_id = "aba_ffffffffffffffffffffffff",
    p5_acceptance_id = "fqaac_222222222222222222222222",
    p6_acceptance_id = "mda_333333333333333333333333"
  )
  plan <- s08_plan_value(lineage, fuse_test_root)
  expect_length(plan$hyperparameter_configurations, 11L)
  expect_length(unique(vapply(plan$hyperparameter_configurations, `[[`, character(1L), "configuration_id")), 11L)
  expect_identical(
    vapply(plan$comparison_configurations, `[[`, character(1L), "name"),
    c("FM", "A1", "A2", "A3", "A4", "A5", paste0("B", 1:9), "SSV", "DS")
  )

  changes <- list(
    function(x) { x$training_inheritance$prohibited$information_preservation_objective <- TRUE; x },
    function(x) { x$training_inheritance$prohibited$reconstruction_decoder <- TRUE; x },
    function(x) { x$training_inheritance$fifo_queue$discipline <- "LIFO"; x },
    function(x) { x$training_inheritance$online_branch$gradient_mode <- "disabled"; x },
    function(x) { x$training_inheritance$target_branch$gradient_mode <- "enabled"; x },
    function(x) { x$selection_protocol$primary_metric <- "validation_margin"; x },
    function(x) { x$selection_protocol$equivalence_tolerance <- 0.001; x },
    function(x) { x$selection_protocol$final_tiebreaker <- "later_completed_epoch"; x }
  )
  for (change in changes) expect_error(s08_validate_plan(change(plan), lineage, fuse_test_root), "contract validation")
})

test_that("dissertation source drift is provenance-only and plan identity is deterministic", {
  lineage <- list(
    scientific_revision_token = "mrev_426b2b6ce0117943",
    scientific_contract_sha256 = paste(rep("4", 64L), collapse = ""),
    p0_authority_id = "mta_aaaaaaaaaaaaaaaaaaaaaaaa",
    p1_acceptance_id = "sia_bbbbbbbbbbbbbbbbbbbbbbbb",
    p2_acceptance_id = "bsa_cccccccccccccccccccccccc",
    p3_acceptance_id = "osca_dddddddddddddddddddddddd",
    p3_cache_id = "oscache_eeeeeeeeeeeeeeeeeeeeeeee",
    p4_acceptance_id = "aba_ffffffffffffffffffffffff",
    p5_acceptance_id = "fqaac_222222222222222222222222",
    p6_acceptance_id = "mda_333333333333333333333333"
  )
  first <- s08_plan_value(lineage, fuse_test_root)
  second <- s08_plan_value(lineage, fuse_test_root)
  expect_identical(first$plan_id, second$plan_id)
  expect_identical(first$content_sha256, second$content_sha256)
  expect_false(first$dissertation_provenance$source_drift_blocking)
  expect_false(any(grepl("rev-parse|dissertation commit mismatch", readLines(file.path(fuse_test_root, "R/experiment_plan.R")))))

  revised <- lineage
  revised$scientific_revision_token <- "mrev_5555555555555555"
  expect_false(identical(first$plan_id, s08_plan_value(revised, fuse_test_root)$plan_id))
})

test_that("S09 operational implementation drift does not change S08 identity", {
  root <- tempfile("s08-contract-hash-")
  dir.create(file.path(root, "config"), recursive = TRUE)
  file.copy(file.path(fuse_test_root, "config/s08_plan_identity.yml"),
            file.path(root, "config/s08_plan_identity.yml"))
  training <- list(objective = "symmetric_scene_level_contrastive", queue = "FIFO")
  selection <- list(primary = "validation_retrieval_loss", tolerance = 0.0001)
  first <- s08_contract_hashes(training, selection, root)
  dir.create(file.path(root, "python"))
  writeLines("runtime implementation v1", file.path(root, "python/training_worker.py"))
  second <- s08_contract_hashes(training, selection, root)
  writeLines("runtime implementation v2", file.path(root, "python/training_worker.py"))
  third <- s08_contract_hashes(training, selection, root)
  expect_identical(first, second)
  expect_identical(second, third)
  expect_false(identical(
    first$training_inheritance_sha256,
    s08_contract_hashes(c(training, list(masking = TRUE)), selection, root)$training_inheritance_sha256
  ))
  expect_false(identical(
    first$selection_protocol_sha256,
    s08_contract_hashes(training, c(selection, list(minimum_delta = 0.001)), root)$selection_protocol_sha256
  ))
})

test_that("S08 source registration excludes S09 operational provenance", {
  paths <- current_experiment_plan_sources(fuse_test_root)
  relative <- sub(paste0("^", normalizePath(fuse_test_root), "/"), "", paths)
  expect_true("config/s08_plan_identity.yml" %in% relative)
  expect_false(any(relative %in% c(
    "python/training_worker.py", "python/training_runtime_inputs.py",
    "python/training_progress.py", "python/training_controller.py",
    "scripts/run_training_targets.R", "scripts/training_controller.py"
  )))
})

test_that("OFAT and comparison changes remain S08 identity-bearing", {
  lineage <- list(
    scientific_revision_token = "mrev_426b2b6ce0117943",
    scientific_contract_sha256 = paste(rep("4", 64L), collapse = ""),
    p0_authority_id = "mta_aaaaaaaaaaaaaaaaaaaaaaaa",
    p1_acceptance_id = "sia_bbbbbbbbbbbbbbbbbbbbbbbb",
    p2_acceptance_id = "bsa_cccccccccccccccccccccccc",
    p3_acceptance_id = "osca_dddddddddddddddddddddddd",
    p3_cache_id = "oscache_eeeeeeeeeeeeeeeeeeeeeeee",
    p4_acceptance_id = "aba_ffffffffffffffffffffffff",
    p5_acceptance_id = "fqaac_222222222222222222222222",
    p6_acceptance_id = "mda_333333333333333333333333"
  )
  plan <- s08_plan_value(lineage, fuse_test_root)
  changed_ofat <- plan
  changed_ofat$hyperparameter_configurations[[1L]]$K_aug <- 4L
  expect_error(s08_validate_plan(changed_ofat, lineage, fuse_test_root), "contract validation")
  changed_comparison <- plan
  changed_comparison$comparison_configurations[[1L]]$name <- "OLD"
  expect_error(s08_validate_plan(changed_comparison, lineage, fuse_test_root), "contract validation")
})
