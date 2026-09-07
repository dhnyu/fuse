test_that("current dissertation semantic selectors resolve fail closed", {
  spec <- load_p0_authority_spec(fuse_test_root)
  resolved <- resolve_typst_source_set(
    spec$dissertation$repository_path, spec$dissertation$entrypoint,
    spec$implementation_version, spec$resolver_implementation_sha256,
    spec$dissertation$non_scientific_generated_paths,
    spec$dissertation$non_scientific_external_imports
  )
  expect_identical(resolved$status, "PASS")
  expect_length(resolved$unresolved_imports, 0L)
  expect_length(resolved$unsupported_dynamic_imports, 0L)
  definitions <- p0_module_definitions()
  expect_setequal(names(definitions), c("scene", "base_spatial", "original_cache", "augmentation",
    "model", "training", "evaluation", "hyperparameter_study", "comparison", "downstream"))
  evidence <- unlist(lapply(definitions, function(definition) lapply(
    definition$citations, p0_extract_semantic_block, source_set=resolved,
    repository_path=spec$dissertation$repository_path)), recursive=FALSE)
  expect_true(length(evidence) >= 10L)
})

test_that("current canonical P0 values match the dissertation migration", {
  definitions <- p0_module_definitions()
  expect_identical(definitions$scene$contract$total_off_grid_scene_count, 10000L)
  expect_identical(definitions$scene$contract$validation_scene_count, 1000L)
  expect_identical(definitions$scene$contract$evaluation_scene_count, 9000L)
  expect_identical(definitions$model$contract$dimensions$d, 128L)
  expect_false(definitions$model$contract$information_preservation_subsystem)
  expect_identical(definitions$training$contract$objective, "symmetric_scene_level_contrastive_only")
  expect_false(definitions$training$contract$reconstruction_decoder_path)
  expect_identical(definitions$hyperparameter_study$contract$unique_configuration_count, 11L)
  expect_identical(definitions$comparison$contract$configuration_count, 17L)
})

test_that("semantic selectors fail closed on duplicate anchors", {
  root <- tempfile("p0-selector-")
  dir.create(root)
  writeLines(c("anchor value", "anchor value"), file.path(root, "source.typ"))
  source_set <- list(ordered_files = list(list(path = "source.typ")))
  selector <- p0_semantic_selector("source.typ", "anchor", "value")
  expect_error(p0_extract_semantic_block(selector, source_set, root), "exactly once")
})

test_that("module scientific hashes exclude source provenance", {
  contract <- list(value = 1L)
  first <- p0_scientific_sha256(list(schema_version = "2.0.0", module_name = "fixture", canonical_contract = contract))
  second <- p0_scientific_sha256(list(schema_version = "2.0.0", module_name = "fixture", canonical_contract = contract))
  changed <- p0_scientific_sha256(list(schema_version = "2.0.0", module_name = "fixture", canonical_contract = list(value = 2L)))
  expect_identical(first, second)
  expect_false(identical(first, changed))
})

test_that("P0 supersession changed and unchanged module claims match the predecessor", {
  predecessor <- "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/authority/mta_f90fecff7bc7bb5d231cc79f"
  skip_if_not(dir.exists(predecessor), "predecessor authority is unavailable")
  definitions <- p0_module_definitions()
  read_contract <- function(name) {
    jsonlite::read_json(file.path(predecessor, paste0(name, "_methodology_contract.json")), simplifyVector = FALSE)$canonical_contract
  }
  canonical <- function(value) canonical_json(p0_sort_named_objects(value))
  for (name in c("base_spatial", "original_cache", "downstream")) {
    expect_identical(canonical(definitions[[name]]$contract), canonical(read_contract(name)), info = name)
  }
  for (name in c("scene", "augmentation", "model", "training", "evaluation")) {
    expect_false(identical(canonical(definitions[[name]]$contract), canonical(read_contract(name))), info = name)
  }
})
