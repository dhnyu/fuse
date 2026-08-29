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

test_that("Git state rejects branch, commit, and dirty mismatches", {
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
  expect_identical(commit$verification_status, "BLOCKED_BY_REPOSITORY_STATE")
  expect_true("commit_mismatch" %in% unlist(commit$diagnostics))

  writeLines("dirty", file.path(fixture$root, "template/main.typ"))
  dirty <- inspect_p0_git_state(fixture$root, "fixture", "reduced", fixture$sha)
  expect_identical(dirty$verification_status, "BLOCKED_BY_REPOSITORY_STATE")
  expect_true(dirty$working_tree_dirty)
  expect_true(dirty$source_files_locally_modified)
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

test_that("conflict normalization blocks scientific conflict and accepts supporting detail", {
  root <- tempfile("p0-conflict-")
  dir.create(root)
  p0_write_fixture(root, "a.typ", "value 64")
  p0_write_fixture(root, "b.typ", "value 48")
  source_set <- p0_fixture_source_set(root, c("a.typ", "b.typ"))
  conflict <- evaluate_p0_conflicts(list(list(
    module = "model", field = "d", observations = list(
      p0_conflict_observation(64L, "a.typ", 1L, 1L, "64"),
      p0_conflict_observation(48L, "b.typ", 1L, 1L, "48")
    )
  )), source_set, root)
  expect_identical(conflict$status, "BLOCKED_BY_DISSERTATION_CONFLICT")
  expect_identical(conflict$records[[1L]]$classification, "BLOCKED_BY_DISSERTATION_CONFLICT")

  supporting <- evaluate_p0_conflicts(list(list(
    module = "augmentation", field = "detail", relationship = "supporting_detail",
    observations = list(p0_conflict_observation(TRUE, "a.typ", 1L, 1L, "value"))
  )), source_set, root)
  expect_identical(supporting$status, "PASS")
  expect_identical(supporting$records[[1L]]$classification, "SUPPORTING_DETAIL")
  expect_identical(p0_normalize_conflict_value("  VALUE "), "value")
})

test_that("authority identity excludes environment-specific fields", {
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

test_that("actual reduced dissertation produces a complete deterministic P0 authority", {
  spec <- load_p0_authority_spec(fuse_test_root)
  temp_authority <- tempfile("p0-authority-integration-")
  spec$authority_root <- temp_authority
  on.exit(unlink(temp_authority, recursive = TRUE), add = TRUE)

  source_files <- build_reduced_methodology_source_files(spec)
  git_state <- build_reduced_methodology_git_state(source_files, spec)
  git_value <- jsonlite::read_json(git_state, simplifyVector = FALSE)
  if (!identical(git_value$observed_commit_sha, spec$dissertation$expected_commit_sha)) {
    # P8-only methodology revisions are bound by the scoped P8 compatibility
    # record and must not silently republish the repository-wide P0 authority.
    expect_identical(git_value$verification_status, "BLOCKED_BY_REPOSITORY_STATE")
    expect_true("commit_mismatch" %in% unlist(git_value$diagnostics))
    expect_error(build_reduced_methodology_source_set(source_files, git_state, spec),
                 "Dissertation Git state is not accepted")
    return(invisible(NULL))
  }
  source_set <- build_reduced_methodology_source_set(source_files, git_state, spec)
  source_value <- jsonlite::read_json(source_set, simplifyVector = FALSE)
  expect_identical(source_value$status, "PASS")
  expect_length(source_value$ordered_files, 44L)
  expect_length(source_value$import_edges, 64L)
  expect_length(source_value$unresolved_imports, 0L)
  expect_length(source_value$cycle_diagnostics, 0L)

  gate <- build_reduced_methodology_conflict_gate(source_set, spec)
  gate_value <- jsonlite::read_json(gate, simplifyVector = FALSE)
  expect_identical(gate_value$status, "PASS")

  module_names <- names(p0_module_definitions())
  modules <- vapply(module_names, build_p0_module_contract, character(1L),
                    source_set_file = source_set, conflict_gate_file = gate, spec = spec)
  expect_length(modules, 8L)
  invisible(lapply(modules, validate_json_schema_file, schema_file = spec$schemas[["module_contract"]]))

  first <- build_reduced_methodology_authority(git_state, source_set, gate, modules, spec)
  second <- build_reduced_methodology_authority(git_state, source_set, gate, modules, spec)
  expect_identical(first, second)
  manifest <- first[grepl("reduced_methodology_authority[.]json$", first)]
  validate_json_schema_file(manifest, spec$schemas[["authority"]])
  value <- jsonlite::read_json(manifest, simplifyVector = FALSE)
  expect_identical(value$overall_status, "PASS")
  expect_identical(value$authority_id, basename(dirname(manifest)))
  expect_length(value$module_contracts, 8L)
})

test_that("P0 target ancestry contains no P1 or later target", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"),
    callr_arguments = list(wd = fuse_test_root)
  )
  p0 <- c(
    "reduced_methodology_source_files", "reduced_methodology_git_state",
    "reduced_methodology_source_set", "reduced_methodology_conflict_gate",
    "scene_methodology_contract", "base_spatial_methodology_contract",
    "original_cache_methodology_contract", "augmentation_methodology_contract",
    "model_methodology_contract", "training_methodology_contract",
    "evaluation_methodology_contract", "downstream_methodology_contract",
    "reduced_methodology_authority"
  )
  commands <- setNames(manifest$command, manifest$name)
  dependencies <- lapply(p0, function(name) intersect(all.names(parse(text = commands[[name]])[[1L]]), manifest$name))
  names(dependencies) <- p0
  visit <- function(name, seen = character()) {
    if (name %in% seen) return(seen)
    Reduce(function(acc, dependency) visit(dependency, acc), dependencies[[name]], init = c(seen, name))
  }
  ancestry <- unique(visit("reduced_methodology_authority"))
  expect_setequal(ancestry, p0)
  expect_false(any(c("study_data_inputs", "spatial_scene_index", "prototype_scene_selection") %in% ancestry))
})
