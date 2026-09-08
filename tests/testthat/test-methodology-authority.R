p0_write_fixture <- function(root, relative_path, lines) {
  path <- file.path(root, relative_path)
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  writeLines(lines, path, useBytes = TRUE)
  path
}

p0_fixture_source_set <- function(root, paths) {
  list(
    source_set_id = "mss_0123456789abcdef",
    ordered_files = lapply(paths, function(path) list(path = path))
  )
}

p0_init_git_fixture <- function(branch = "reduced") {
  root <- tempfile("p0-git-")
  dir.create(root)
  system2("git", c("-C", root, "init", "-q", "-b", branch))
  system2("git", c("-C", root, "config", "user.email", "p0@example.invalid"))
  system2("git", c("-C", root, "config", "user.name", "P0 Fixture"))
  p0_write_fixture(root, "template/main.typ", "P0 fixture")
  system2("git", c("-C", root, "add", "template/main.typ"))
  system2("git", c("-C", root, "commit", "-q", "-m", "fixture"))
  sha <- system2("git", c("-C", root, "rev-parse", "HEAD"), stdout = TRUE)
  list(root = root, sha = sha[[1L]])
}

test_that("recursive Typst resolution is deterministic and repository-relative", {
  root <- tempfile("p0-typst-")
  dir.create(root)
  p0_write_fixture(root, "template/main.typ", c('#import "parts/a.typ"', '#include "parts/b.typ"'))
  p0_write_fixture(root, "template/parts/a.typ", '#import "../shared.typ"')
  p0_write_fixture(root, "template/parts/b.typ", '#include "../shared.typ"')
  p0_write_fixture(root, "template/shared.typ", "shared")
  first <- resolve_typst_source_set(root)
  second <- resolve_typst_source_set(root)
  expect_identical(first$status, "PASS")
  expect_identical(names(first$ordered_paths), c(
    "template/main.typ", "template/parts/a.typ", "template/shared.typ", "template/parts/b.typ"
  ))
  expect_identical(first$ordered_files, second$ordered_files)
  expect_length(first$duplicate_diagnostics, 1L)
  expect_length(first$cycle_diagnostics, 0L)
})

test_that("Typst cycles, unresolved imports, dynamic imports, and escapes block", {
  cycle_root <- tempfile("p0-cycle-")
  dir.create(cycle_root)
  p0_write_fixture(cycle_root, "template/main.typ", '#import "a.typ"')
  p0_write_fixture(cycle_root, "template/a.typ", '#import "main.typ"')
  cycle <- resolve_typst_source_set(cycle_root)
  expect_identical(cycle$status, "BLOCKED_BY_MISSING_EVIDENCE")
  expect_length(cycle$cycle_diagnostics, 1L)

  unresolved_root <- tempfile("p0-unresolved-")
  dir.create(unresolved_root)
  p0_write_fixture(unresolved_root, "template/main.typ", '#import "missing.typ"')
  unresolved <- resolve_typst_source_set(unresolved_root)
  expect_identical(unresolved$status, "BLOCKED_BY_MISSING_EVIDENCE")
  expect_length(unresolved$unresolved_imports, 1L)

  dynamic_root <- tempfile("p0-dynamic-")
  dir.create(dynamic_root)
  p0_write_fixture(dynamic_root, "template/main.typ", c("#import target", "#let body = include target"))
  dynamic <- resolve_typst_source_set(dynamic_root)
  expect_identical(dynamic$status, "BLOCKED_BY_MISSING_EVIDENCE")
  expect_length(dynamic$unsupported_dynamic_imports, 2L)

  escape_root <- tempfile("p0-escape-")
  dir.create(escape_root)
  outside <- tempfile("outside-", fileext = ".typ")
  writeLines("outside", outside)
  relative_escape <- file.path("..", "..", basename(outside))
  p0_write_fixture(escape_root, "template/main.typ", sprintf('#import "%s"', relative_escape))
  escape <- resolve_typst_source_set(escape_root)
  expect_identical(escape$status, "BLOCKED_BY_MISSING_EVIDENCE")
  expect_true(any(vapply(escape$unresolved_imports, function(x) identical(x$reason, "repository_escape"), logical(1L))))
})

test_that("Git state blocks topology violations but records content drift", {
  fixture <- p0_init_git_fixture()
  on.exit(unlink(fixture$root, recursive = TRUE), add = TRUE)
  accepted <- inspect_p0_git_state(fixture$root, "fixture", "reduced", fixture$sha)
  expect_identical(accepted$verification_status, "PASS")
  expect_false(accepted$head_detached)
  expect_false(accepted$working_tree_dirty)

  branch <- inspect_p0_git_state(fixture$root, "fixture", "main", fixture$sha)
  expect_identical(branch$verification_status, "BLOCKED_BY_REPOSITORY_STATE")
  expect_true("branch_mismatch" %in% unlist(branch$diagnostics))

  commit <- inspect_p0_git_state(fixture$root, "fixture", "reduced", paste(rep("0", 40L), collapse = ""))
  expect_identical(commit$verification_status, "PASS")
  expect_true("commit_drift" %in% unlist(commit$diagnostics))

  writeLines("dirty", file.path(fixture$root, "template/main.typ"))
  dirty <- inspect_p0_git_state(fixture$root, "fixture", "reduced", fixture$sha)
  expect_identical(dirty$verification_status, "PASS")
  expect_true(dirty$working_tree_dirty)
  expect_true(dirty$source_files_locally_modified)
  expect_true("working_tree_drift" %in% unlist(dirty$diagnostics))
})

test_that("dissertation prose and bibliography drift is non-blocking", {
  paths <- c(
    "template/sections/chapters/02-literature-review.typ",
    "template/sections/chapters/03-methodology-model.typ",
    "template/sections/chapters/04-methodology-training.typ",
    "template/sections/chapters/05-results.typ",
    "template/bibliography/references.bib"
  )
  for (path in paths) {
    fixture <- p0_init_git_fixture()
    on.exit(unlink(fixture$root, recursive = TRUE), add = TRUE)
    p0_write_fixture(fixture$root, path, "baseline prose")
    system2("git", c("-C", fixture$root, "add", path))
    system2("git", c("-C", fixture$root, "commit", "-q", "-m", "add-source"))
    accepted_sha <- system2("git", c("-C", fixture$root, "rev-parse", "HEAD"), stdout = TRUE)[[1L]]
    p0_write_fixture(fixture$root, path, "edited prose or citation")
    system2("git", c("-C", fixture$root, "add", path))
    system2("git", c("-C", fixture$root, "commit", "-q", "-m", "edit-source"))
    observed <- inspect_p0_git_state(fixture$root, "fixture", "reduced", accepted_sha)
    expect_identical(observed$verification_status, "PASS", info = path)
    expect_true("commit_drift" %in% unlist(observed$diagnostics), info = path)
  }
})

test_that("source and canonical contract hashes are deterministic", {
  root <- tempfile("p0-hash-")
  dir.create(root)
  path <- p0_write_fixture(root, "template/main.typ", "same bytes")
  first <- resolve_typst_source_set(root)
  second <- resolve_typst_source_set(root)
  expect_identical(first$ordered_files[[1L]]$sha256, second$ordered_files[[1L]]$sha256)
  expect_identical(first$ordered_files[[1L]]$sha256, sha256_file(path))
  expect_identical(
    p0_scientific_sha256(list(b = 2L, a = list(y = 2L, x = 1L))),
    p0_scientific_sha256(list(a = list(x = 1L, y = 2L), b = 2L))
  )
})

test_that("authority publication identity excludes environment-specific fields", {
  args <- list(
    schema_version = "1.0.0", dissertation_commit_sha = paste(rep("a", 40L), collapse = ""),
    ordered_source_hashes = list(list(path = "main.typ", sha256 = paste(rep("b", 64L), collapse = ""))),
    module_contract_hashes = list(list(module_name = "scene", sha256 = paste(rep("c", 64L), collapse = ""))),
    conflict_gate_result = list(status = "PASS"), implementation_version = "1.0.0",
    implementation_sha256 = paste(rep("d", 64L), collapse = "")
  )
  first <- do.call(p0_authority_id, c(args, list(environment = list(hostname = "one", path = "/tmp/one", workers = 1L))))
  second <- do.call(p0_authority_id, c(args, list(environment = list(hostname = "two", path = "/tmp/two", workers = 64L))))
  expect_identical(first, second)
})

test_that("immutable artifact collisions are rejected", {
  root <- tempfile("p0-immutable-")
  dir.create(dirname(root), recursive = TRUE, showWarnings = FALSE)
  publish_deterministic_directory(root, "value.txt", function(stage) writeLines("first", file.path(stage, "value.txt")))
  expect_error(
    publish_deterministic_directory(root, "value.txt", function(stage) writeLines("second", file.path(stage, "value.txt"))),
    "non-deterministic"
  )
})

p0_module_publication_fixture <- function(source_set_id = "mss_0123456789abcdef",
                                           implementation_sha256 = paste(rep("a", 64L), collapse = ""),
                                           contract = list(value = 1L),
                                           supersedes_publication_id = NULL) {
  scientific_sha256 <- p0_scientific_sha256(list(
    schema_version = "2.0.0", module_name = "scene", canonical_contract = contract
  ))
  list(
    schema_version = "2.0.0", publication_schema_version = "1.0.0",
    contract_id = paste0("mmc_", substr(scientific_sha256, 1L, 16L)), module_name = "scene",
    authoritative_source_citations = list(list(
      path = "template/main.typ", selector = "anchored_semantic_block", anchor = "fixture",
      end_anchor = NULL, required_tokens = list(), forbidden_tokens = list(),
      evidence_sha256 = paste(rep("b", 64L), collapse = "")
    )),
    canonical_contract = contract, source_set_id = source_set_id,
    extraction_validation_implementation_sha256 = implementation_sha256,
    unresolved_fields = list(), conflicting_fields = list(), status = "PASS",
    module_content_sha256 = scientific_sha256,
    supersedes_publication_id = supersedes_publication_id
  )
}

test_that("module publication identity separates science from operational provenance", {
  spec <- load_p0_authority_spec(fuse_test_root)
  spec$authority_root <- tempfile("p0-publications-")
  on.exit(unlink(spec$authority_root, recursive = TRUE), add = TRUE)

  first_value <- p0_module_publication_fixture()
  first <- p0_publish_module_contract(first_value, spec)
  first_again <- p0_publish_module_contract(first_value, spec)
  first_read <- p0_read_module_publication(first, spec$schemas[["module_contract"]])
  expect_identical(first, first_again)

  changed_provenance <- p0_module_publication_fixture(
    source_set_id = "mss_fedcba9876543210",
    implementation_sha256 = paste(rep("c", 64L), collapse = ""),
    supersedes_publication_id = first_read$publication_id
  )
  second <- p0_publish_module_contract(changed_provenance, spec)
  second_read <- p0_read_module_publication(second, spec$schemas[["module_contract"]])
  expect_identical(first_read$value$contract_id, second_read$value$contract_id)
  expect_identical(first_read$value$module_content_sha256, second_read$value$module_content_sha256)
  expect_false(identical(first_read$publication_id, second_read$publication_id))
  expect_true(all(file.exists(c(first, second))))

  changed_science <- p0_publish_module_contract(
    p0_module_publication_fixture(contract = list(value = 2L)), spec
  )
  changed_read <- p0_read_module_publication(changed_science, spec$schemas[["module_contract"]])
  expect_false(identical(first_read$value$contract_id, changed_read$value$contract_id))
  expect_false(identical(first_read$publication_id, changed_read$publication_id))
})

test_that("legacy module publications are read-only predecessors", {
  root <- tempfile("p0-legacy-publication-")
  dir.create(root, recursive = TRUE)
  path <- file.path(root, "scene_methodology_contract.json")
  legacy <- p0_module_publication_fixture()
  legacy$publication_schema_version <- NULL
  legacy$supersedes_publication_id <- NULL
  write_json_file(legacy, path)
  before <- sha256_file(path)
  read <- p0_read_module_publication(path)
  expect_identical(read$layout, "legacy_read_only")
  expect_match(read$publication_id, "^mmp_[0-9a-f]{64}$")

  spec <- load_p0_authority_spec(fuse_test_root)
  spec$authority_root <- file.path(root, "new")
  current <- p0_module_publication_fixture(
    source_set_id = "mss_fedcba9876543210",
    supersedes_publication_id = read$publication_id
  )
  published <- p0_publish_module_contract(current, spec)
  expect_true(file.exists(published))
  expect_identical(sha256_file(path), before)
  unlink(root, recursive = TRUE)
})

test_that("module publication collision fails closed", {
  spec <- load_p0_authority_spec(fuse_test_root)
  spec$authority_root <- tempfile("p0-publication-collision-")
  on.exit(unlink(spec$authority_root, recursive = TRUE), add = TRUE)
  value <- p0_module_publication_fixture()
  identity <- p0_module_publication_identity(value)
  final_dir <- p0_component_dir(
    spec, file.path("modules", value$module_name, value$contract_id, "publications"),
    identity$publication_id
  )
  dir.create(final_dir, recursive = TRUE)
  writeLines("corrupt", file.path(final_dir, "scene_methodology_contract.json"))
  expect_error(p0_publish_module_contract(value, spec), "non-deterministic")
})

test_that("explicit revision selects the existing scientific authority", {
  spec <- load_p0_authority_spec(fuse_test_root)
  accepted <- p0_read_accepted_authority(spec)
  expect_identical(accepted$value$authority_id, "mta_2142a2914bc5c43ea8d6e312")
  expect_identical(
    accepted$value$scientific_contract_sha256,
    "426b2b6ce011794335d2e6f052e56ef463a7f0022f5733784c60eae9f85425ca"
  )
  expect_length(accepted$value$module_contracts, 10L)
  expect_identical(
    accepted$value$scientific_contract_sha256,
    p0_scientific_contract_sha256(accepted$value$module_contracts)
  )
  expect_identical(
    vapply(accepted$value$module_contracts, `[[`, character(1L), "sha256"),
    vapply(p0_expected_module_records(spec), `[[`, character(1L), "sha256")
  )

  sources <- p0_scientific_revision_source_files(spec)
  expect_false(any(grepl("[.](typ|bib|pdf)$", sources)))
  source_authority <- p0_resolve_accepted_source_authority(sources, spec)
  active_names <- c(
    "scene", "base_spatial", "original_cache", "augmentation",
    "model", "evaluation", "hyperparameter_study", "comparison"
  )
  modules <- vapply(
    active_names, p0_resolve_accepted_module_contract, character(1L),
    source_authority = source_authority, spec = spec
  )
  resolved <- p0_resolve_accepted_authority(source_authority, modules, spec)
  expect_length(resolved, 16L)
  expect_true(all(file.exists(resolved)))
  expect_identical(
    normalizePath(resolved[grepl("reduced_methodology_authority[.]json$", resolved)], mustWork = TRUE),
    normalizePath(accepted$path, mustWork = TRUE)
  )
})

test_that("explicit methodology revision changes invalidate the accepted path", {
  spec <- load_p0_authority_spec(fuse_test_root)
  original <- p0_read_scientific_revision(spec)
  changed_file <- tempfile("p0-scientific-revision-", fileext = ".yml")
  on.exit(unlink(changed_file), add = TRUE)
  changed <- original
  changed$revision_token <- "mrev_material_change"
  changed$material_revision_declared <- TRUE
  yaml::write_yaml(changed, changed_file)
  spec$revision_file <- changed_file
  expect_error(
    p0_read_scientific_revision(spec),
    "not an accepted current declaration|revision token"
  )
  expect_error(p0_read_accepted_authority(spec))
})

test_that("operational supersession fails closed on scientific drift", {
  prior_root <- tempfile("p0-prior-")
  prior_id <- "mta_0123456789abcdef01234567"
  dir.create(file.path(prior_root, prior_id), recursive = TRUE)
  modules <- lapply(c("scene", "model"), function(name) list(
    module_name = name,
    contract_id = paste0("mmc_", name),
    sha256 = paste(rep(if (name == "scene") "a" else "b", 64L), collapse = "")
  ))
  jsonlite::write_json(
    list(commit_sha = paste(rep("c", 40L), collapse = ""), module_contracts = modules),
    file.path(prior_root, prior_id, "reduced_methodology_authority.json"),
    auto_unbox = TRUE
  )
  spec <- list(
    authority_root = prior_root,
    predecessor_authority_file = file.path(prior_root, prior_id, "reduced_methodology_authority.json"),
    supersedes = list(
      migration_kind = "OPERATIONAL_ONLY", authority_id = prior_id,
      dissertation_commit = paste(rep("c", 40L), collapse = ""), changed_modules = list()
    )
  )
  source_set <- list(commit_sha = paste(rep("c", 40L), collapse = ""))
  expect_invisible(p0_assert_operational_supersession(modules, source_set, spec))
  modules[[2L]]$sha256 <- paste(rep("d", 64L), collapse = "")
  expect_error(
    p0_assert_operational_supersession(modules, source_set, spec),
    "changed a scientific module hash"
  )
})

test_that("P0 target ancestry contains no P1 or later target", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"),
    callr_arguments = list(wd = fuse_test_root)
  )
  p0 <- c(
    "s00_methodology_sources", "s00_methodology_source_authority",
    "s00_scene_methodology_contract", "s00_spatial_methodology_contract",
    "s00_cache_methodology_contract", "s00_augmentation_methodology_contract",
    "s00_model_methodology_contract", "s00_evaluation_methodology_contract",
    "s00_hyperparameter_methodology_contract", "s00_comparison_methodology_contract",
    "s00_methodology_authority"
  )
  commands <- setNames(manifest$command, manifest$name)
  dependencies <- lapply(p0, function(name) intersect(all.names(parse(text = commands[[name]])[[1L]]), manifest$name))
  names(dependencies) <- p0
  visit <- function(name, seen = character()) {
    if (name %in% seen) return(seen)
    Reduce(function(acc, dependency) visit(dependency, acc), dependencies[[name]], init = c(seen, name))
  }
  ancestry <- unique(visit("s00_methodology_authority"))
  expect_setequal(ancestry, p0)
  expect_false(any(c("i01_seoul_spatial_sources", "s01_scene_index", "s01_pilot_scene_index") %in% ancestry))
})
