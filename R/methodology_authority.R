p0_authority_config_file <- function(root = getwd()) {
  file.path(normalizePath(root, mustWork = TRUE), "config/p0_authority.yml")
}

p0_sort_named_objects <- function(value) {
  if (is.list(value)) {
    if (!is.null(names(value)) && all(nzchar(names(value)))) {
      value <- value[order(names(value), method = "radix")]
    }
    return(lapply(value, p0_sort_named_objects))
  }
  value
}

p0_scientific_sha256 <- function(value) {
  canonical_sha256(p0_sort_named_objects(value))
}

p0_short_id <- function(prefix, value, characters = 16L) {
  paste0(prefix, substr(p0_scientific_sha256(value), 1L, as.integer(characters)))
}

load_p0_authority_spec <- function(root = getwd()) {
  root <- normalizePath(root, mustWork = TRUE)
  config_file <- p0_authority_config_file(root)
  value <- yaml::read_yaml(config_file)
  required <- c(
    "schema_version", "implementation_version", "scientific_revision",
    "dissertation", "approved_audit", "publication", "schemas"
  )
  missing <- setdiff(required, names(value))
  if (length(missing)) stop("P0 authority config is incomplete: ", paste(missing, collapse = ", "), call. = FALSE)
  dissertation <- value$dissertation
  audit <- value$approved_audit
  if (!dir.exists(dissertation$repository_path)) stop("Dissertation repository is absent", call. = FALSE)
  if (!file.exists(audit$path)) stop("Approved audit is absent", call. = FALSE)
  actual_audit_hash <- sha256_file(audit$path)
  if (!identical(actual_audit_hash, audit$expected_sha256)) {
    stop("Approved audit checksum mismatch", call. = FALSE)
  }
  schema_files <- vapply(value$schemas, function(path) file.path(root, path), character(1L))
  missing_schemas <- schema_files[!file.exists(schema_files)]
  if (length(missing_schemas)) stop("P0 schema file is absent: ", paste(missing_schemas, collapse = ", "), call. = FALSE)
  implementation_file <- file.path(root, "R/methodology_authority.R")
  revision_file <- file.path(root, value$scientific_revision$contract_file)
  if (!file.exists(revision_file)) stop("P0 scientific revision contract is absent", call. = FALSE)
  implementation_relative_files <- c(
    "R/methodology_authority.R",
    "R/current_methodology.R",
    "targets/s00_methodology.R",
    "config/current_methodology.yml",
    "python/current_methodology.py",
    "config/schemas/current_experiment_plan.schema.json",
    unname(unlist(value$schemas, use.names = FALSE))
  )
  implementation_records <- lapply(implementation_relative_files, function(path) list(
    path = path, sha256 = sha256_file(file.path(root, path))
  ))
  implementation_sha256 <- p0_scientific_sha256(list(
    implementation_version = value$implementation_version,
    files = implementation_records
  ))
  authority_root <- value$publication$authority_root
  list(
    schema_version = value$schema_version,
    implementation_version = value$implementation_version,
    root = root,
    config_file = normalizePath(config_file, mustWork = TRUE),
    config_sha256 = sha256_file(config_file),
    revision_file = normalizePath(revision_file, mustWork = TRUE),
    implementation_file = normalizePath(implementation_file, mustWork = TRUE),
    resolver_implementation_sha256 = sha256_file(implementation_file),
    implementation_sha256 = implementation_sha256,
    dissertation = list(
      repository_path = normalizePath(dissertation$repository_path, mustWork = TRUE),
      repository_identity = dissertation$repository_identity,
      expected_branch = dissertation$expected_branch,
      expected_commit_sha = dissertation$expected_commit_sha,
      entrypoint = dissertation$entrypoint,
      non_scientific_generated_paths = unlist(dissertation$non_scientific_generated_paths),
      non_scientific_external_imports = unlist(dissertation$non_scientific_external_imports)
    ),
    audit = list(path = normalizePath(audit$path, mustWork = TRUE), sha256 = actual_audit_hash),
    authority_root = authority_root,
    predecessor_authority_file = file.path(
      authority_root, value$publication$supersedes$authority_id,
      "reduced_methodology_authority.json"
    ),
    supersedes = value$publication$supersedes,
    schemas = setNames(normalizePath(schema_files, mustWork = TRUE), names(schema_files))
  )
}

p0_revision_token <- function(scientific_contract_sha256) {
  if (!grepl("^[0-9a-f]{64}$", scientific_contract_sha256)) {
    stop("P0 scientific contract SHA-256 is invalid", call. = FALSE)
  }
  paste0("mrev_", substr(scientific_contract_sha256, 1L, 16L))
}

p0_expected_module_records <- function(spec) {
  definitions <- p0_module_definitions()
  lapply(names(definitions), function(module_name) {
    hash <- p0_scientific_sha256(list(
      schema_version = spec$schema_version,
      module_name = module_name,
      canonical_contract = definitions[[module_name]]$contract
    ))
    list(
      module_name = module_name,
      contract_id = paste0("mmc_", substr(hash, 1L, 16L)),
      sha256 = hash
    )
  })
}

p0_read_scientific_revision <- function(spec) {
  value <- yaml::read_yaml(spec$revision_file)
  required <- c(
    "schema_version", "revision_token", "material_revision_declared",
    "accepted_authority_id", "accepted_scientific_contract_sha256",
    "invalidation_policy"
  )
  missing <- setdiff(required, names(value))
  if (length(missing)) {
    stop("P0 scientific revision contract is incomplete: ", paste(missing, collapse = ", "), call. = FALSE)
  }
  if (!identical(value$schema_version, "1.0.0") ||
      !identical(value$invalidation_policy, "explicit_revision_only") ||
      !isFALSE(value$material_revision_declared) ||
      !grepl("^mta_[0-9a-f]{24}$", value$accepted_authority_id) ||
      !grepl("^[0-9a-f]{64}$", value$accepted_scientific_contract_sha256)) {
    stop("P0 scientific revision contract is not an accepted current declaration", call. = FALSE)
  }
  expected_token <- p0_revision_token(value$accepted_scientific_contract_sha256)
  if (!identical(value$revision_token, expected_token)) {
    stop("P0 methodology revision token does not match the accepted scientific contract", call. = FALSE)
  }
  value
}

p0_current_authority_file <- function(spec, revision = p0_read_scientific_revision(spec)) {
  file.path(spec$authority_root, revision$accepted_authority_id, "reduced_methodology_authority.json")
}

p0_read_accepted_authority <- function(spec) {
  revision <- p0_read_scientific_revision(spec)
  path <- p0_current_authority_file(spec, revision)
  if (!file.exists(path)) stop("Accepted P0 methodology authority is absent", call. = FALSE)
  validate_json_schema_file(path, spec$schemas[["authority"]])
  authority <- p0_read_single_json(path)
  if (!identical(authority$authority_id, revision$accepted_authority_id) ||
      !identical(authority$scientific_contract_sha256, revision$accepted_scientific_contract_sha256)) {
    stop("Accepted P0 authority disagrees with the explicit scientific revision", call. = FALSE)
  }
  expected <- p0_expected_module_records(spec)
  expected_hashes <- setNames(vapply(expected, `[[`, character(1L), "sha256"),
                              vapply(expected, `[[`, character(1L), "module_name"))
  observed_hashes <- setNames(vapply(authority$module_contracts, `[[`, character(1L), "sha256"),
                              vapply(authority$module_contracts, `[[`, character(1L), "module_name"))
  if (!identical(observed_hashes[sort(names(observed_hashes))], expected_hashes[sort(names(expected_hashes))]) ||
      !identical(p0_scientific_contract_sha256(authority$module_contracts),
                 revision$accepted_scientific_contract_sha256)) {
    stop("Current implementation differs from the explicitly accepted P0 scientific revision", call. = FALSE)
  }
  list(path = normalizePath(path, mustWork = TRUE), value = authority, revision = revision)
}

p0_scientific_revision_source_files <- function(spec) {
  p0_read_accepted_authority(spec)
  normalizePath(c(
    spec$revision_file,
    spec$config_file,
    file.path(spec$root, "config/current_methodology.yml")
  ), mustWork = TRUE)
}

p0_resolve_accepted_source_authority <- function(revision_sources, spec) {
  if (!length(revision_sources) || any(!file.exists(revision_sources))) {
    stop("P0 explicit revision sources are unavailable", call. = FALSE)
  }
  accepted <- p0_read_accepted_authority(spec)
  authority <- accepted$value
  components <- c(
    file.path(spec$authority_root, "_components", "git_state", authority$git_state_id,
              "methodology_git_state.json"),
    file.path(spec$authority_root, "_components", "source_set", authority$source_set_id,
              "methodology_source_set.json"),
    file.path(spec$authority_root, "_components", "conflict_gate", authority$conflict_gate_id,
              "methodology_conflict_gate.json")
  )
  schemas <- spec$schemas[c("git_state", "source_set", "conflict_gate")]
  if (any(!file.exists(components))) stop("Accepted P0 source-authority component is absent", call. = FALSE)
  invisible(Map(validate_json_schema_file, components, schemas))
  normalizePath(components, mustWork = TRUE)
}

p0_accepted_module_publication_path <- function(module_name, accepted, spec) {
  records <- Filter(function(record) identical(record$module_name, module_name),
                    accepted$value$module_contracts)
  if (length(records) != 1L) stop("Accepted P0 module record is missing or duplicated: ", module_name, call. = FALSE)
  record <- records[[1L]]
  path <- file.path(
    spec$authority_root, "_components", "modules", module_name, record$contract_id,
    "publications", record$publication_id, paste0(module_name, "_methodology_contract.json")
  )
  publication <- p0_read_module_publication(path, spec$schemas[["module_contract"]])
  if (!identical(publication$publication_id, record$publication_id) ||
      !identical(publication$publication_identity_sha256, record$publication_identity_sha256) ||
      !identical(sha256_file(path), record$publication_file_sha256) ||
      !identical(publication$value$module_content_sha256, record$sha256)) {
    stop("Accepted P0 module publication identity mismatch: ", module_name, call. = FALSE)
  }
  publication$path
}

p0_resolve_accepted_module_contract <- function(module_name, source_authority, spec) {
  if (length(source_authority) != 3L || any(!file.exists(source_authority))) {
    stop("Accepted P0 source authority is incomplete", call. = FALSE)
  }
  p0_accepted_module_publication_path(module_name, p0_read_accepted_authority(spec), spec)
}

p0_resolve_accepted_authority <- function(source_authority, module_contracts, spec) {
  accepted <- p0_read_accepted_authority(spec)
  expected_source_authority <- p0_resolve_accepted_source_authority(
    p0_scientific_revision_source_files(spec), spec
  )
  if (!identical(normalizePath(source_authority, mustWork = TRUE), expected_source_authority)) {
    stop("Active P0 source-authority targets do not match the accepted authority", call. = FALSE)
  }
  expected_active <- c("scene", "base_spatial", "original_cache", "augmentation",
                       "model", "evaluation", "hyperparameter_study", "comparison")
  expected_paths <- vapply(
    expected_active, p0_accepted_module_publication_path, character(1L),
    accepted = accepted, spec = spec
  )
  if (!identical(normalizePath(module_contracts, mustWork = TRUE), unname(expected_paths))) {
    stop("Active P0 module targets do not match the accepted scientific authority", call. = FALSE)
  }
  training <- p0_accepted_module_publication_path("training", accepted, spec)
  downstream <- p0_accepted_module_publication_path("downstream", accepted, spec)
  authority_dir <- dirname(accepted$path)
  copied_components <- file.path(authority_dir, c(
    "reduced_methodology_authority.json", "methodology_git_state.json",
    "methodology_source_set.json", "methodology_conflict_gate.json",
    paste0(names(p0_module_definitions()), "_methodology_contract.json")
  ))
  if (any(!file.exists(copied_components))) stop("Accepted P0 authority bundle is incomplete", call. = FALSE)
  c(training, downstream, normalizePath(copied_components, mustWork = TRUE))
}

p0_dissertation_provenance_snapshot <- function(spec) {
  revision <- p0_read_scientific_revision(spec)
  git_state <- inspect_p0_git_state(
    spec$dissertation$repository_path, spec$dissertation$repository_identity,
    spec$dissertation$expected_branch, spec$dissertation$expected_commit_sha,
    spec$schema_version
  )
  resolved <- resolve_typst_source_set(
    spec$dissertation$repository_path, spec$dissertation$entrypoint,
    spec$implementation_version, spec$resolver_implementation_sha256,
    spec$dissertation$non_scientific_generated_paths,
    spec$dissertation$non_scientific_external_imports
  )
  list(
    schema_version = "1.0.0",
    status = if (identical(resolved$status, "PASS")) "INFORMATIONAL" else resolved$status,
    scientific_revision_token = revision$revision_token,
    accepted_authority_id = revision$accepted_authority_id,
    accepted_scientific_contract_sha256 = revision$accepted_scientific_contract_sha256,
    authority_provenance_commit = spec$dissertation$expected_commit_sha,
    observed_commit = git_state$observed_commit_sha,
    observed_branch = git_state$observed_branch,
    working_tree_dirty = git_state$working_tree_dirty,
    source_drift = !identical(git_state$observed_commit_sha, spec$dissertation$expected_commit_sha) ||
      isTRUE(git_state$working_tree_dirty),
    resolved_source_hashes = lapply(resolved$ordered_files, function(file) file[c("path", "sha256")]),
    blocking = FALSE
  )
}

p0_scientific_contract_sha256 <- function(module_records) {
  records <- lapply(module_records, function(record) list(
    module_name = record$module_name,
    sha256 = record$sha256
  ))
  names(records) <- vapply(records, `[[`, character(1L), "module_name")
  p0_scientific_sha256(records)
}

p0_assert_operational_supersession <- function(module_records, source_set, spec) {
  supersedes <- spec$supersedes
  if (!identical(supersedes$migration_kind, "OPERATIONAL_ONLY")) return(invisible(NULL))

  prior_path <- spec$predecessor_authority_file
  if (!file.exists(prior_path)) stop("Operational supersession predecessor is absent", call. = FALSE)
  prior <- p0_read_single_json(prior_path)
  prior_hashes <- setNames(
    vapply(prior$module_contracts, `[[`, character(1L), "sha256"),
    vapply(prior$module_contracts, `[[`, character(1L), "module_name")
  )
  current_hashes <- setNames(
    vapply(module_records, `[[`, character(1L), "sha256"),
    vapply(module_records, `[[`, character(1L), "module_name")
  )
  if (!identical(current_hashes[sort(names(current_hashes))], prior_hashes[sort(names(prior_hashes))])) {
    stop("Operational supersession changed a scientific module hash", call. = FALSE)
  }
  if (length(unlist(supersedes$changed_modules, use.names = FALSE)) != 0L) {
    stop("Operational supersession cannot declare changed scientific modules", call. = FALSE)
  }
  invisible(prior)
}

p0_strip_line_comment <- function(line) {
  sub("//.*$", "", line, perl = TRUE)
}

p0_typst_references <- function(path) {
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  references <- list()
  unsupported <- list()
  add_reference <- function(directive, value, line_number, column) {
    references[[length(references) + 1L]] <<- list(
      directive = directive, value = value,
      line = as.integer(line_number), column = as.integer(column)
    )
  }
  for (line_number in seq_along(lines)) {
    line <- p0_strip_line_comment(lines[[line_number]])
    patterns <- list(
      import = "#\\s*import\\s*[\\(]?\\s*\"([^\"]+)\"",
      include = "(?:#\\s*include|^\\s*include|[=,(]\\s*include)\\s*[\\(]?\\s*\"([^\"]+)\"",
      bibliography = "\"([^\"]+[.]bib)\""
    )
    occupied <- integer()
    for (directive in names(patterns)) {
      match <- gregexpr(patterns[[directive]], line, perl = TRUE)[[1L]]
      if (identical(match[[1L]], -1L)) next
      lengths <- attr(match, "match.length")
      captures <- attr(match, "capture.start")
      capture_lengths <- attr(match, "capture.length")
      for (i in seq_along(match)) {
        start <- captures[i, 1L]
        length <- capture_lengths[i, 1L]
        value <- substr(line, start, start + length - 1L)
        if (directive == "bibliography" && any(match[[i]] %in% occupied)) next
        add_reference(directive, value, line_number, match[[i]] + 1L)
        occupied <- c(occupied, seq.int(match[[i]], match[[i]] + lengths[[i]] - 1L))
      }
    }
    code_context <- gsub("\"(?:\\\\.|[^\"])*\"", "\"\"", line, perl = TRUE)
    directives <- gregexpr("#\\s*(?:import|include)\\b|(?:^\\s*|[=,(]\\s*)include\\b", code_context, perl = TRUE)[[1L]]
    if (!identical(directives[[1L]], -1L)) {
      for (position in directives) {
        static_on_line <- any(vapply(references, function(ref) ref$line == line_number && ref$column >= position, logical(1L)))
        if (!static_on_line) {
          unsupported[[length(unsupported) + 1L]] <- list(
            line = as.integer(line_number), column = as.integer(position + 1L),
            expression = trimws(line), reason = "dynamic_or_unsupported_import"
          )
        }
      }
    }
  }
  if (length(references)) {
    key <- vapply(references, function(ref) sprintf("%09d:%09d", ref$line, ref$column), character(1L))
    references <- references[order(key, method = "radix")]
  }
  list(references = references, unsupported = unsupported)
}

p0_repository_relative_path <- function(path, repository_path) {
  repository_path <- normalizePath(repository_path, winslash = "/", mustWork = TRUE)
  normalized <- normalizePath(path, winslash = "/", mustWork = FALSE)
  prefix <- paste0(repository_path, "/")
  if (!identical(normalized, repository_path) && !startsWith(normalized, prefix)) {
    stop("Typst import escapes the dissertation repository: ", path, call. = FALSE)
  }
  if (identical(normalized, repository_path)) "." else substring(normalized, nchar(prefix) + 1L)
}

p0_resolve_reference_path <- function(value, importer_path, repository_path,
                                      generated_paths = character(), external_imports = character()) {
  if (startsWith(value, "@")) {
    if (value %in% external_imports) {
      return(list(status = "ignored", path = NULL, reason = "non_scientific_external_import"))
    }
    return(list(status = "unsupported", path = NULL, reason = "external_package_import"))
  }
  candidate <- if (startsWith(value, "/")) {
    file.path(repository_path, substring(value, 2L))
  } else {
    file.path(dirname(importer_path), value)
  }
  normalized <- normalizePath(candidate, winslash = "/", mustWork = FALSE)
  repository_normalized <- normalizePath(repository_path, winslash = "/", mustWork = TRUE)
  if (!startsWith(paste0(normalized, "/"), paste0(repository_normalized, "/"))) {
    return(list(status = "blocked", path = normalized, reason = "repository_escape"))
  }
  relative <- substring(normalized, nchar(paste0(repository_normalized, "/")) + 1L)
  if (!file.exists(normalized) && basename(normalized) %in% basename(generated_paths)) {
    return(list(status = "ignored", path = normalized, reason = "non_scientific_generated_input"))
  }
  if (!file.exists(normalized)) return(list(status = "unresolved", path = normalized, reason = "file_not_found"))
  list(status = "resolved", path = normalizePath(normalized, winslash = "/", mustWork = TRUE), reason = NULL)
}

p0_source_classification <- function(relative_path) {
  if (grepl("[.]bib$", relative_path)) return("supporting_bibliography")
  if (grepl("template/sections/chapters/(03-methodology-model|04-methodology-training|methodology/)|template/sections/appendices/", relative_path)) {
    return("scientific_methodology")
  }
  if (grepl("template/sections/chapters/results/|template/materials/tables/results-", relative_path)) {
    return("scientific_evaluation")
  }
  "supporting_template"
}

resolve_typst_source_set <- function(repository_path, entrypoint = "template/main.typ",
                                     resolver_version = "1.0.0",
                                     resolver_implementation_sha256 = NULL,
                                     generated_paths = character(), external_imports = character()) {
  repository_path <- normalizePath(repository_path, winslash = "/", mustWork = TRUE)
  entry_path <- p0_resolve_reference_path(entrypoint, file.path(repository_path, "root.typ"), repository_path)
  if (!identical(entry_path$status, "resolved")) stop("Typst entrypoint cannot be resolved", call. = FALSE)
  ordered_paths <- character()
  edges <- list()
  unresolved <- list()
  duplicates <- list()
  cycles <- list()
  unsupported <- list()
  state <- new.env(parent = emptyenv())

  visit <- function(path) {
    relative <- p0_repository_relative_path(path, repository_path)
    assign(relative, 1L, envir = state)
    ordered_paths <<- c(ordered_paths, path)
    if (grepl("[.]bib$", relative)) {
      assign(relative, 2L, envir = state)
      return(invisible(NULL))
    }
    parsed <- p0_typst_references(path)
    if (length(parsed$unsupported)) {
      unsupported <<- c(unsupported, lapply(parsed$unsupported, function(item) c(list(importer = relative), item)))
    }
    for (reference in parsed$references) {
      resolution <- p0_resolve_reference_path(reference$value, path, repository_path,
                                              generated_paths, external_imports)
      if (identical(resolution$status, "ignored")) next
      if (!identical(resolution$status, "resolved")) {
        record <- c(list(importer = relative, imported_expression = reference$value,
                         directive = reference$directive), reference,
                    list(reason = resolution$reason))
        if (resolution$status == "unsupported") unsupported[[length(unsupported) + 1L]] <<- record else unresolved[[length(unresolved) + 1L]] <<- record
        next
      }
      imported_relative <- p0_repository_relative_path(resolution$path, repository_path)
      prior <- if (exists(imported_relative, envir = state, inherits = FALSE)) get(imported_relative, envir = state) else 0L
      duplicate <- prior > 0L
      cycle <- identical(prior, 1L)
      edge <- list(
        order = as.integer(length(edges) + 1L), importer = relative,
        imported_path = imported_relative, directive = reference$directive,
        line = reference$line, column = reference$column,
        duplicate = duplicate, cycle = cycle
      )
      edges[[length(edges) + 1L]] <<- edge
      if (cycle) cycles[[length(cycles) + 1L]] <<- edge
      if (duplicate) duplicates[[length(duplicates) + 1L]] <<- edge
      if (!duplicate) visit(resolution$path)
    }
    assign(relative, 2L, envir = state)
    invisible(NULL)
  }
  visit(entry_path$path)
  files <- lapply(seq_along(ordered_paths), function(i) {
    path <- ordered_paths[[i]]
    relative <- p0_repository_relative_path(path, repository_path)
    list(order = as.integer(i), path = relative, sha256 = sha256_file(path),
         size_bytes = as.integer(file.info(path)$size), classification = p0_source_classification(relative))
  })
  status <- if (length(unresolved) || length(unsupported) || length(cycles)) "BLOCKED_BY_MISSING_EVIDENCE" else "PASS"
  list(
    repository_path = repository_path,
    repository_relative_entrypoint = p0_repository_relative_path(entry_path$path, repository_path),
    ordered_paths = setNames(ordered_paths, vapply(files, `[[`, character(1L), "path")),
    ordered_files = files, import_edges = edges,
    unresolved_imports = unresolved, duplicate_diagnostics = duplicates,
    cycle_diagnostics = cycles, unsupported_dynamic_imports = unsupported,
    resolver_implementation_version = resolver_version,
    resolver_implementation_sha256 = resolver_implementation_sha256,
    status = status
  )
}

p0_git_command <- function(repository_path, args, allow_failure = FALSE) {
  output <- suppressWarnings(system2("git", c("-C", shQuote(repository_path), args), stdout = TRUE, stderr = TRUE))
  status <- attr(output, "status")
  if (is.null(status)) status <- 0L
  if (!allow_failure && status != 0L) stop("Git command failed: ", paste(output, collapse = "\n"), call. = FALSE)
  list(output = output, status = as.integer(status))
}

inspect_p0_git_state <- function(repository_path, repository_identity,
                                 expected_branch, expected_commit_sha,
                                 schema_version = "1.0.0") {
  if (!dir.exists(file.path(repository_path, ".git"))) stop("Dissertation Git repository is absent", call. = FALSE)
  commit <- p0_git_command(repository_path, c("rev-parse", "HEAD"))$output[[1L]]
  branch_result <- p0_git_command(repository_path, c("symbolic-ref", "--short", "-q", "HEAD"), allow_failure = TRUE)
  detached <- branch_result$status != 0L
  branch <- if (detached) NULL else branch_result$output[[1L]]
  porcelain <- p0_git_command(repository_path, c("status", "--porcelain=v1", "--untracked-files=all"))$output
  tracked <- p0_git_command(repository_path, c("diff", "--name-only"))$output
  staged <- p0_git_command(repository_path, c("diff", "--cached", "--name-only"))$output
  untracked <- any(startsWith(porcelain, "??"))
  upstream_result <- p0_git_command(repository_path, c("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"), allow_failure = TRUE)
  upstream <- if (upstream_result$status == 0L) upstream_result$output[[1L]] else NULL
  divergence <- NULL
  if (!is.null(upstream)) {
    counts <- p0_git_command(repository_path, c("rev-list", "--left-right", "--count", paste0("HEAD...", upstream)))$output[[1L]]
    counts <- as.integer(strsplit(trimws(counts), "[[:space:]]+")[[1L]])
    divergence <- list(ahead = counts[[1L]], behind = counts[[2L]])
  }
  blocking_diagnostics <- character()
  provenance_diagnostics <- character()
  if (!identical(branch, expected_branch)) blocking_diagnostics <- c(blocking_diagnostics, "branch_mismatch")
  if (detached) blocking_diagnostics <- c(blocking_diagnostics, "detached_head")
  if (!identical(commit, expected_commit_sha)) provenance_diagnostics <- c(provenance_diagnostics, "commit_drift")
  if (length(porcelain)) provenance_diagnostics <- c(provenance_diagnostics, "working_tree_drift")
  scientific <- list(
    schema_version = schema_version, repository_identity = repository_identity,
    expected_branch = expected_branch, observed_branch = branch,
    expected_commit_sha = expected_commit_sha, observed_commit_sha = commit,
    head_detached = detached, working_tree_dirty = length(porcelain) > 0L,
    tracked_modification = length(tracked) > 0L,
    staged_modification = length(staged) > 0L,
    untracked_files = untracked, source_files_locally_modified = length(tracked) > 0L || length(staged) > 0L,
    verification_status = if (length(blocking_diagnostics)) "BLOCKED_BY_REPOSITORY_STATE" else "PASS"
  )
  content_hash <- p0_scientific_sha256(scientific)
  c(scientific, list(
    git_state_id = paste0("mgs_", substr(content_hash, 1L, 16L)),
    repository_path = normalizePath(repository_path, mustWork = TRUE),
    upstream_ref = upstream, upstream_divergence = divergence,
    diagnostics = as.list(c(blocking_diagnostics, provenance_diagnostics)), content_sha256 = content_hash
  ))
}

p0_component_dir <- function(spec, component, identity) {
  file.path(spec$authority_root, "_components", component, identity)
}

p0_publish_json_component <- function(value, final_dir, basename, schema_file) {
  publish_deterministic_directory(final_dir, basename, function(stage) {
    path <- file.path(stage, basename)
    write_json_file(value, path)
    validate_json_schema_file(path, schema_file)
  })
}

p0_module_publication_identity <- function(value) {
  if (any(c("publication_id", "publication_identity_sha256") %in% names(value))) {
    stop("P0 module payload cannot contain its self-referential publication identity", call. = FALSE)
  }
  serialized <- tempfile("p0-module-publication-", fileext = ".json")
  on.exit(unlink(serialized), add = TRUE)
  write_json_file(value, serialized)
  identity_sha256 <- sha256_file(serialized)
  list(
    publication_id = paste0("mmp_", identity_sha256),
    publication_identity_sha256 = identity_sha256
  )
}

p0_read_module_publication <- function(path, schema_file = NULL) {
  path <- normalizePath(path, mustWork = TRUE)
  value <- p0_read_single_json(path)
  file_sha256 <- sha256_file(path)
  publication_id <- paste0("mmp_", file_sha256)
  current_layout <- identical(basename(dirname(path)), publication_id) &&
    identical(basename(dirname(dirname(path))), "publications")
  if (current_layout && !identical(file_sha256, p0_module_publication_identity(value)$publication_identity_sha256)) {
    stop("P0 module publication bytes are not deterministic: ", path, call. = FALSE)
  }
  if (!current_layout && identical(basename(dirname(dirname(path))), "publications")) {
    stop("P0 module publication path does not match its publication identity: ", path, call. = FALSE)
  }
  if (current_layout && !is.null(schema_file)) validate_json_schema_file(path, schema_file)
  list(
    layout = if (current_layout) "publication_v1" else "legacy_read_only",
    publication_id = publication_id,
    publication_identity_sha256 = file_sha256,
    path = path,
    value = value
  )
}

p0_predecessor_module_publication <- function(spec, module_name, contract_id, scientific_sha256) {
  prior_authority <- spec$predecessor_authority_file
  if (!file.exists(prior_authority)) return(NULL)
  authority <- p0_read_single_json(prior_authority)
  records <- Filter(function(record) identical(record$module_name, module_name), authority$module_contracts)
  prior_path <- file.path(dirname(prior_authority), paste0(module_name, "_methodology_contract.json"))
  if (!file.exists(prior_path)) return(NULL)
  prior <- p0_read_module_publication(prior_path)
  if (!identical(prior$value$contract_id, contract_id) ||
      !identical(prior$value$module_content_sha256, scientific_sha256)) return(NULL)
  if (length(records) == 1L && !is.null(records[[1L]]$publication_id)) {
    prior$publication_id <- records[[1L]]$publication_id
    prior$publication_identity_sha256 <- records[[1L]]$publication_identity_sha256
  }
  prior
}

p0_publish_module_contract <- function(value, spec) {
  identity <- p0_module_publication_identity(value)
  final_dir <- p0_component_dir(
    spec,
    file.path("modules", value$module_name, value$contract_id, "publications"),
    identity$publication_id
  )
  p0_publish_json_component(
    value, final_dir, paste0(value$module_name, "_methodology_contract.json"),
    spec$schemas[["module_contract"]]
  )
}

build_reduced_methodology_source_files <- function(spec) {
  resolved <- resolve_typst_source_set(
    spec$dissertation$repository_path, spec$dissertation$entrypoint,
    spec$implementation_version, spec$resolver_implementation_sha256,
    spec$dissertation$non_scientific_generated_paths,
    spec$dissertation$non_scientific_external_imports
  )
  if (!identical(resolved$status, "PASS")) {
    stop("P0 Typst source resolution blocked: unresolved=", length(resolved$unresolved_imports),
         ", unsupported=", length(resolved$unsupported_dynamic_imports),
         ", cycles=", length(resolved$cycle_diagnostics), call. = FALSE)
  }
  unname(resolved$ordered_paths)
}

build_reduced_methodology_git_state <- function(source_files, spec) {
  if (!length(source_files) || any(!file.exists(source_files))) stop("Resolved dissertation source files are unavailable", call. = FALSE)
  value <- inspect_p0_git_state(
    spec$dissertation$repository_path, spec$dissertation$repository_identity,
    spec$dissertation$expected_branch, spec$dissertation$expected_commit_sha,
    spec$schema_version
  )
  final_dir <- p0_component_dir(spec, "git_state", value$git_state_id)
  p0_publish_json_component(value, final_dir, "methodology_git_state.json", spec$schemas[["git_state"]])
}

build_reduced_methodology_source_set <- function(source_files, git_state_file, spec) {
  git_state <- jsonlite::read_json(git_state_file, simplifyVector = FALSE)
  if (!identical(git_state$verification_status, "PASS")) stop("Dissertation Git state is not accepted", call. = FALSE)
  resolved <- resolve_typst_source_set(
    spec$dissertation$repository_path, spec$dissertation$entrypoint,
    spec$implementation_version, spec$resolver_implementation_sha256,
    spec$dissertation$non_scientific_generated_paths,
    spec$dissertation$non_scientific_external_imports
  )
  expected <- normalizePath(source_files, mustWork = TRUE)
  if (!identical(unname(resolved$ordered_paths), unname(expected))) stop("Tracked P0 source files differ from resolver output", call. = FALSE)
  source_hashes <- vapply(expected, sha256_file, character(1L))
  manifest_hashes <- vapply(resolved$ordered_files, `[[`, character(1L), "sha256")
  if (!identical(unname(source_hashes), unname(manifest_hashes))) stop("P0 source changed during source-set construction", call. = FALSE)
  scientific <- list(
    schema_version = spec$schema_version,
    repository_identity = spec$dissertation$repository_identity,
    repository_relative_entrypoint = resolved$repository_relative_entrypoint,
    branch = git_state$observed_branch, commit_sha = git_state$observed_commit_sha,
    ordered_files = resolved$ordered_files, import_edges = resolved$import_edges,
    unresolved_imports = resolved$unresolved_imports,
    duplicate_diagnostics = resolved$duplicate_diagnostics,
    cycle_diagnostics = resolved$cycle_diagnostics,
    unsupported_dynamic_imports = resolved$unsupported_dynamic_imports,
    resolver_implementation_version = resolved$resolver_implementation_version,
    resolver_implementation_sha256 = resolved$resolver_implementation_sha256,
    audit_sha256 = spec$audit$sha256, status = resolved$status
  )
  content_hash <- p0_scientific_sha256(scientific)
  value <- list(
    schema_version = spec$schema_version,
    source_set_id = paste0("mss_", substr(content_hash, 1L, 16L)),
    repository_path = spec$dissertation$repository_path,
    repository_relative_entrypoint = resolved$repository_relative_entrypoint,
    repository_identity = spec$dissertation$repository_identity,
    branch = git_state$observed_branch, commit_sha = git_state$observed_commit_sha,
    ordered_files = resolved$ordered_files, import_edges = resolved$import_edges,
    unresolved_imports = resolved$unresolved_imports,
    duplicate_diagnostics = resolved$duplicate_diagnostics,
    cycle_diagnostics = resolved$cycle_diagnostics,
    unsupported_dynamic_imports = resolved$unsupported_dynamic_imports,
    resolver_implementation_version = resolved$resolver_implementation_version,
    resolver_implementation_sha256 = resolved$resolver_implementation_sha256,
    audit = spec$audit, source_set_content_sha256 = content_hash,
    status = resolved$status
  )
  final_dir <- p0_component_dir(spec, "source_set", value$source_set_id)
  p0_publish_json_component(value, final_dir, "methodology_source_set.json", spec$schemas[["source_set"]])
}

p0_read_single_json <- function(path) {
  jsonlite::read_json(path, simplifyVector = FALSE)
}

p0_authority_id <- function(schema_version, dissertation_commit_sha,
                            ordered_source_hashes, module_contract_hashes,
                            conflict_gate_result, implementation_version,
                            implementation_sha256, module_publications = list(),
                            environment = NULL) {
  identity_inputs <- list(
    schema_version = schema_version,
    dissertation_commit_sha = dissertation_commit_sha,
    ordered_source_hashes = ordered_source_hashes,
    module_contract_hashes = module_contract_hashes,
    module_publications = module_publications,
    conflict_gate_result = conflict_gate_result,
    implementation_version = implementation_version,
    implementation_sha256 = implementation_sha256
  )
  paste0("mta_", substr(p0_scientific_sha256(identity_inputs), 1L, 24L))
}

build_reduced_methodology_authority <- function(git_state_file, source_set_file,
                                                conflict_gate_file, module_contract_files,
                                                spec) {
  git_state <- p0_read_single_json(git_state_file)
  source_set <- p0_read_single_json(source_set_file)
  gate <- p0_read_single_json(conflict_gate_file)
  publications <- lapply(module_contract_files, p0_read_module_publication,
                         schema_file = spec$schemas[["module_contract"]])
  modules <- lapply(publications, `[[`, "value")
  expected_modules <- names(p0_module_definitions())
  observed_modules <- vapply(modules, `[[`, character(1L), "module_name")
  if (!identical(git_state$verification_status, "PASS")) stop("P0 Git state blocks authority publication", call. = FALSE)
  if (!identical(source_set$status, "PASS")) stop("P0 source set blocks authority publication", call. = FALSE)
  if (!identical(gate$status, "PASS") || gate$unclassified_conflict_count != 0L) stop("P0 conflict gate blocks authority publication", call. = FALSE)
  if (!setequal(observed_modules, expected_modules) || length(modules) != length(expected_modules)) stop("P0 module contract set is incomplete", call. = FALSE)
  if (any(vapply(modules, function(x) !identical(x$status, "PASS"), logical(1L)))) stop("A P0 module contract is not accepted", call. = FALSE)
  order <- match(expected_modules, observed_modules)
  modules <- modules[order]
  publications <- publications[order]
  ordered_hashes <- lapply(source_set$ordered_files, function(file) list(path = file$path, sha256 = file$sha256))
  module_records <- lapply(seq_along(modules), function(index) list(
    module_name = modules[[index]]$module_name,
    contract_id = modules[[index]]$contract_id,
    sha256 = modules[[index]]$module_content_sha256,
    publication_id = publications[[index]]$publication_id,
    publication_identity_sha256 = publications[[index]]$publication_identity_sha256,
    publication_file_sha256 = sha256_file(publications[[index]]$path)
  ))
  module_records <- unname(module_records)
  p0_assert_operational_supersession(module_records, source_set, spec)
  scientific_contract_sha256 <- p0_scientific_contract_sha256(module_records)
  authority_id <- p0_authority_id(
    spec$schema_version, source_set$commit_sha, ordered_hashes,
    lapply(module_records, function(x) list(module_name = x$module_name, sha256 = x$sha256)),
    list(id = gate$conflict_gate_id, status = gate$status, content_sha256 = gate$content_sha256),
    spec$implementation_version, spec$implementation_sha256,
    lapply(module_records, function(x) list(
      module_name = x$module_name, publication_id = x$publication_id,
      publication_identity_sha256 = x$publication_identity_sha256,
      publication_file_sha256 = x$publication_file_sha256
    ))
  )
  scientific <- list(
    schema_version = spec$schema_version, authority_id = authority_id,
    dissertation_repository_identity = spec$dissertation$repository_identity,
    branch = source_set$branch, commit_sha = source_set$commit_sha,
    git_state_id = git_state$git_state_id, source_set_id = source_set$source_set_id,
    ordered_source_hashes = ordered_hashes, audit_sha256 = spec$audit$sha256,
    module_contracts = module_records,
    conflict_gate_id = gate$conflict_gate_id, conflict_gate_status = gate$status,
    implementation_version = spec$implementation_version,
    implementation_sha256 = spec$implementation_sha256,
    scientific_contract_sha256 = scientific_contract_sha256,
    supersession = list(
      prior_authority_id = spec$supersedes$authority_id,
      prior_dissertation_commit = spec$supersedes$dissertation_commit,
      new_dissertation_commit = source_set$commit_sha,
      migration_kind = spec$supersedes$migration_kind,
      reason = spec$supersedes$reason,
      changed_modules = as.list(unlist(spec$supersedes$changed_modules, use.names = FALSE)),
      unchanged_modules = as.list(unlist(spec$supersedes$unchanged_modules, use.names = FALSE)),
      downstream_artifact_default = spec$supersedes$downstream_artifact_default
    ),
    downstream_scope_mapping = list(
      P1 = "scene", P2 = "base_spatial", P3 = "original_cache", P4 = "augmentation",
      P5 = "evaluation", P6 = "model", P7 = "training", P8 = "training",
      P9 = "training", P10 = "evaluation", P11 = "downstream"
    ),
    overall_status = "PASS"
  )
  aggregate_hash <- p0_scientific_sha256(scientific)
  value <- list(
    schema_version = spec$schema_version, authority_id = authority_id,
    dissertation_repository_identity = spec$dissertation$repository_identity,
    branch = source_set$branch, commit_sha = source_set$commit_sha,
    git_state_id = git_state$git_state_id, source_set_id = source_set$source_set_id,
    ordered_source_hashes = ordered_hashes, audit = spec$audit,
    module_contracts = module_records,
    conflict_gate_id = gate$conflict_gate_id, conflict_gate_status = gate$status,
    implementation_version = spec$implementation_version,
    implementation_sha256 = spec$implementation_sha256,
    scientific_contract_sha256 = scientific_contract_sha256,
    aggregate_content_sha256 = aggregate_hash,
    supersession = scientific$supersession,
    downstream_scope_mapping = scientific$downstream_scope_mapping,
    overall_status = "PASS"
  )
  final_dir <- file.path(spec$authority_root, authority_id)
  component_paths <- c(git_state_file, source_set_file, conflict_gate_file, module_contract_files)
  component_names <- c("methodology_git_state.json", "methodology_source_set.json", "methodology_conflict_gate.json",
                       paste0(expected_modules, "_methodology_contract.json"))
  output_names <- c("reduced_methodology_authority.json", component_names)
  publish_deterministic_directory(final_dir, output_names, function(stage) {
    authority_path <- file.path(stage, output_names[[1L]])
    write_json_file(value, authority_path)
    validate_json_schema_file(authority_path, spec$schemas[["authority"]])
    copied <- file.copy(component_paths, file.path(stage, component_names), overwrite = FALSE)
    if (!all(copied)) stop("Failed to stage P0 authority component files", call. = FALSE)
    validate_json_schema_file(file.path(stage, "methodology_git_state.json"), spec$schemas[["git_state"]])
    validate_json_schema_file(file.path(stage, "methodology_source_set.json"), spec$schemas[["source_set"]])
    validate_json_schema_file(file.path(stage, "methodology_conflict_gate.json"), spec$schemas[["conflict_gate"]])
    invisible(lapply(file.path(stage, paste0(expected_modules, "_methodology_contract.json")),
                     validate_json_schema_file, schema_file = spec$schemas[["module_contract"]]))
  })
}
p0_build_source_authority <- function(source_files, spec) {
  git_state <- build_reduced_methodology_git_state(source_files, spec)
  source_set <- build_reduced_methodology_source_set(source_files, git_state, spec)
  conflict_gate <- build_reduced_methodology_conflict_gate(source_set, spec)
  c(git_state, source_set, conflict_gate)
}

p0_build_final_authority <- function(source_authority, module_contracts, spec) {
  training <- build_p0_module_contract("training", source_authority, source_authority, spec)
  downstream <- build_p0_module_contract("downstream", source_authority, source_authority, spec)
  authority <- build_reduced_methodology_authority(
    source_authority, source_authority, source_authority,
    c(module_contracts, training, downstream), spec
  )
  c(training, downstream, authority)
}
