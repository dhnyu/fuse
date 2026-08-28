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
  required <- c("schema_version", "implementation_version", "dissertation", "approved_audit", "publication", "schemas")
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
  implementation_file <- file.path(root, "R/research_methodology_authority.R")
  implementation_relative_files <- c(
    "R/research_methodology_authority.R",
    "targets/research_methodology_authority.R",
    unname(unlist(value$schemas, use.names = FALSE))
  )
  implementation_records <- lapply(implementation_relative_files, function(path) list(
    path = path, sha256 = sha256_file(file.path(root, path))
  ))
  implementation_sha256 <- p0_scientific_sha256(list(
    implementation_version = value$implementation_version,
    files = implementation_records
  ))
  list(
    schema_version = value$schema_version,
    implementation_version = value$implementation_version,
    root = root,
    config_file = normalizePath(config_file, mustWork = TRUE),
    config_sha256 = sha256_file(config_file),
    implementation_file = normalizePath(implementation_file, mustWork = TRUE),
    resolver_implementation_sha256 = sha256_file(implementation_file),
    implementation_sha256 = implementation_sha256,
    dissertation = list(
      repository_path = normalizePath(dissertation$repository_path, mustWork = TRUE),
      repository_identity = dissertation$repository_identity,
      expected_branch = dissertation$expected_branch,
      expected_commit_sha = dissertation$expected_commit_sha,
      entrypoint = dissertation$entrypoint
    ),
    audit = list(path = normalizePath(audit$path, mustWork = TRUE), sha256 = actual_audit_hash),
    authority_root = value$publication$authority_root,
    schemas = setNames(normalizePath(schema_files, mustWork = TRUE), names(schema_files))
  )
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

p0_resolve_reference_path <- function(value, importer_path, repository_path) {
  if (startsWith(value, "@")) {
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
                                     resolver_implementation_sha256 = NULL) {
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
      resolution <- p0_resolve_reference_path(reference$value, path, repository_path)
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
  diagnostics <- character()
  if (!identical(branch, expected_branch)) diagnostics <- c(diagnostics, "branch_mismatch")
  if (!identical(commit, expected_commit_sha)) diagnostics <- c(diagnostics, "commit_mismatch")
  if (detached) diagnostics <- c(diagnostics, "detached_head")
  if (length(porcelain)) diagnostics <- c(diagnostics, "working_tree_dirty")
  scientific <- list(
    schema_version = schema_version, repository_identity = repository_identity,
    expected_branch = expected_branch, observed_branch = branch,
    expected_commit_sha = expected_commit_sha, observed_commit_sha = commit,
    head_detached = detached, working_tree_dirty = length(porcelain) > 0L,
    tracked_modification = length(tracked) > 0L,
    staged_modification = length(staged) > 0L,
    untracked_files = untracked, source_files_locally_modified = length(tracked) > 0L || length(staged) > 0L,
    verification_status = if (length(diagnostics)) "BLOCKED_BY_REPOSITORY_STATE" else "PASS"
  )
  content_hash <- p0_scientific_sha256(scientific)
  c(scientific, list(
    git_state_id = paste0("mgs_", substr(content_hash, 1L, 16L)),
    repository_path = normalizePath(repository_path, mustWork = TRUE),
    upstream_ref = upstream, upstream_divergence = divergence,
    diagnostics = as.list(diagnostics), content_sha256 = content_hash
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

build_reduced_methodology_source_files <- function(spec) {
  resolved <- resolve_typst_source_set(
    spec$dissertation$repository_path, spec$dissertation$entrypoint,
    spec$implementation_version, spec$resolver_implementation_sha256
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
    spec$implementation_version, spec$resolver_implementation_sha256
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

p0_citation <- function(path, start_line, end_line) {
  list(path = path, start_line = as.integer(start_line), end_line = as.integer(end_line))
}

p0_architecture_row <- function(component, input, architecture, output) {
  list(component = component, input_dimension = input, architecture = as.list(architecture), output_dimension = output)
}

p0_module_definitions <- function() {
  architecture <- list(
    p0_architecture_row("relative_position_encoder", 64L, c("Linear(64,64)", "LN", "GELU", "Dropout", "Linear(64,64)", "LN"), 64L),
    p0_architecture_row("fourier_magnitude_encoder", 128L, c("Linear(128,128)", "LN", "GELU", "Dropout", "Linear(128,64)"), 64L),
    p0_architecture_row("fourier_phase_encoder", 256L, c("Linear(256,128)", "LN", "GELU", "Dropout", "Linear(128,64)"), 64L),
    p0_architecture_row("geometry_fusion", 128L, c("Linear(128,128)", "LN", "GELU", "Dropout", "Linear(128,64)", "LN"), 64L),
    p0_architecture_row("building_road_categorical_embedding", "category_id", "Embedding(cardinality+2,32)", 32L),
    p0_architecture_row("building_numerical_encoder", 4L, c("Linear(4,64)", "LN", "GELU", "Dropout", "Linear(64,32)"), 32L),
    p0_architecture_row("building_attribute_fusion", 96L, c("Linear(96,128)", "LN", "GELU", "Dropout", "Linear(128,64)", "LN"), 64L),
    p0_architecture_row("road_numerical_encoder", 2L, c("Linear(2,32)", "LN", "GELU", "Linear(32,32)"), 32L),
    p0_architecture_row("road_attribute_fusion", 96L, c("Linear(96,128)", "LN", "GELU", "Dropout", "Linear(128,64)", "LN"), 64L),
    p0_architecture_row("poi_hierarchy_embedding", "category_id", c("Embedding(cardinality_k+2,d_k)", "d_k=[8,12,16,16,24,32]"), "d_k"),
    p0_architecture_row("poi_hierarchy_projection", "d_k", "Linear(d_k,32)", 32L),
    p0_architecture_row("poi_hierarchy_importance", 32L, c("Linear(32,64)", "Tanh", "Linear(64,1)"), 1L),
    p0_architecture_row("poi_attribute_fusion", 140L, c("Linear(140,128)", "LN", "GELU", "Dropout", "Linear(128,64)", "LN"), 64L),
    p0_architecture_row("entity_environmental_background_encoder", 26L, c("Linear(26,64)", "LN", "GELU", "Dropout", "Linear(64,64)", "LN"), 64L),
    p0_architecture_row("entity_type_embedding", "entity_type_id", "Embedding(3,16)", 16L),
    p0_architecture_row("type_aware_modality_gate", 80L, c("Linear(80,64)", "GELU", "Dropout", "Linear(64,64)"), 64L),
    p0_architecture_row("relation_type_embedding", "relation_type_id", "Embedding(5,32)", 32L),
    p0_architecture_row("relation_aware_multi_head_attention", 64L, "4_heads_x_16", 64L),
    p0_architecture_row("transformer_feed_forward", 64L, c("Linear(64,128)", "GELU", "Dropout", "Linear(128,64)", "layers=3"), 64L),
    p0_architecture_row("type_specific_attention_pooling", 64L, c("Linear(64,32)", "Tanh", "Linear(32,1)"), 1L),
    p0_architecture_row("land_cover_class_embedding", "land_cover_class_id", "Embedding(C_cat+2,16)", 16L),
    p0_architecture_row("land_cover_cnn", "16x100x100", c("Conv(16,32,3x3,s=2,p=1)", "GN(8)", "GELU", "Conv(32,64,3x3,s=2,p=1)", "GN(8)", "GELU", "Conv(64,64,3x3,s=2,p=1)", "GN(8)", "GELU", "GAP"), 64L),
    p0_architecture_row("dem_cnn", "1x17x17", c("Conv(1,32,3x3,s=2,p=1)", "GN(8)", "GELU", "Conv(32,64,3x3,s=2,p=1)", "GN(8)", "GELU", "Conv(64,64,3x3,s=2,p=1)", "GN(8)", "GELU", "GAP"), 64L),
    p0_architecture_row("raster_modality_projection", 64L, c("Linear(64,128)", "LN", "GELU", "Dropout", "Linear(128,64)", "LN"), 64L),
    p0_architecture_row("final_scene_fusion", 320L, c("Linear(320,128)", "LN", "GELU", "Dropout", "Linear(128,64)", "LN"), 64L),
    p0_architecture_row("modality_mask_embeddings", "masked_modality_id", "four_learnable_vectors", "4x64"),
    p0_architecture_row("contrastive_projection", 64L, c("Linear(64,128)", "LN", "GELU", "Linear(128,64)"), 64L),
    p0_architecture_row("relative_position_decoder", 64L, c("Linear(64,64)", "GELU", "Linear(64,2)"), 2L),
    p0_architecture_row("intrinsic_geometry_decoder", 64L, c("Linear(64,128)", "GELU", "magnitude_head(128,128)", "phase_head(128,256)"), "128+256"),
    p0_architecture_row("building_attribute_decoder", 64L, c("Linear(64,64)", "GELU", "field_specific_output_heads"), "target_dependent"),
    p0_architecture_row("road_attribute_decoder", 64L, c("Linear(64,64)", "GELU", "field_specific_output_heads"), "target_dependent"),
    p0_architecture_row("poi_attribute_decoder", 64L, c("Linear(64,64)", "GELU", "six_categorical_output_heads"), "target_dependent"),
    p0_architecture_row("environmental_background_decoder", 64L, c("Linear(64,64)", "GELU", "composition_head(64,22)", "continuous_head(64,4)"), "22+4")
  )
  list(
    scene = list(
      citations = list(
        p0_citation("template/sections/chapters/results/01-experimental-setup.typ", 17L, 21L),
        p0_citation("template/materials/tables/results-03-model-structural-configuration-table.typ", 19L, 21L),
        p0_citation("template/materials/tables/results-03-model-structural-configuration-table.typ", 150L, 153L)
      ),
      contract = list(
        crs_epsg = 5186L, scene_width_m = 500L, scene_height_m = 500L,
        observation_window = "Seoul_boundary_centered", source_coverage_buffer_m = 400L,
        training_center_source = "official_500m_grid_centers",
        training_scene_count = 2421L, validation_scene_count = 400L,
        evaluation_scene_count = 1600L, off_grid_minimum_distance_m = 50L,
        intermediate_training_centers = FALSE, training_sliding_stride_m = NULL,
        field_origins = list(training_scene_count = "approved_blueprint_contract")
      )
    ),
    base_spatial = list(
      citations = list(
        p0_citation("template/sections/chapters/methodology/01-scene-construction.typ", 11L, 24L),
        p0_citation("template/sections/chapters/methodology/04-spatial-relations.typ", 22L, 38L),
        p0_citation("template/materials/tables/results-03-model-structural-configuration-table.typ", 103L, 115L),
        p0_citation("template/sections/appendices/appendix-b.typ", 14L, 24L)
      ),
      contract = list(
        entity_types = as.list(c("B", "R", "P")),
        membership = list(building = "geometry_intersects_scene_window_then_clip", road = "geometry_intersects_scene_window_then_clip", poi = "point_within_scene_window"),
        vector_rule = "observed_geometry_clipped_to_scene_window",
        point_inclusion_rule = "point_membership_in_scene_window",
        raster_roles = list(LC = "land_cover_composition_and_scene_raster", DEM = "elevation_summary_and_scene_raster"),
        relation_types = as.list(c("SN", "CNT", "WIT", "INT", "CON")),
        sn_radius_m = 100L, maximum_sn_neighbors = 16L,
        source_network_topology_identity = "preserve_ordered_source_node_identity",
        road_receiver_compatibility_fields = as.list(c("road_type", "road_hierarchy"))
      )
    ),
    original_cache = list(
      citations = list(
        p0_citation("template/sections/chapters/methodology/01-scene-construction.typ", 19L, 24L),
        p0_citation("template/sections/chapters/methodology/04-spatial-relations.typ", 22L, 38L),
        p0_citation("template/sections/appendices/appendix-b.typ", 16L, 24L)
      ),
      contract = list(
        serialization_role = "serialization-v3_immutable_original_scene_cache",
        scientific_geometry_storage = "float64",
        preserve_original_entity_identity = TRUE,
        source_node_chain = list(order = "ordered", cardinality = "variable_length", offsets_required = TRUE, endpoint_internal_flags_required = TRUE, source_node_vertex_mapping_required = TRUE),
        roundtrip = list(geometry = "lossless_float64", identity = "lossless", topology = "lossless"),
        augmented_provenance_created_in_original_cache = FALSE,
        augmented_provenance_phase = "P4",
        field_origin = "approved_blueprint_engineering_contract_grounded_in_dissertation_topology_requirements"
      )
    ),
    augmentation = list(
      citations = list(
        p0_citation("template/sections/chapters/04-methodology-training.typ", 14L, 71L),
        p0_citation("template/sections/chapters/04-methodology-training.typ", 71L, 94L),
        p0_citation("template/sections/appendices/appendix-b.typ", 7L, 52L),
        p0_citation("template/sections/appendices/appendix-b.typ", 58L, 142L),
        p0_citation("template/sections/chapters/results/05-hyperparameter-study.typ", 8L, 20L)
      ),
      contract = list(
        bank = list(scene_specific = TRUE, pre_generated = TRUE, fixed_during_training = TRUE, main_k_aug = 8L, physical_master_k = 16L, profiles = as.list(c(0.5, 1.0, 2.0))),
        view_sampling = list(count_per_inclusion = 2L, distinct = TRUE, uniform_without_replacement_within_pair = TRUE, later_view_pair_reuse_allowed = TRUE),
        online_scene_level_augmentation = "prohibited",
        dependent_removal = list(building_removes_hosted_poi = TRUE, dependent_poi_not_primary_count = TRUE),
        road_absorption = list(cascade_deletion = FALSE, receiver_requires_shared_source_node = TRUE, receiver_requires_same_road_type = TRUE, receiver_requires_same_hierarchy = TRUE, receiver_id_preserved = TRUE, receiver_attributes_preserved = TRUE, selected_geometry_inherited = TRUE, selected_source_node_ids_inherited = TRUE, invalid_connection_retains_selected_link = TRUE),
        geometry = list(complexity_by_entity_type = TRUE, operations = as.list(c("topology_preserving_simplification", "stochastic_vertex_jitter")), vertex_selection = "independent_bernoulli", protect_all_retained_source_network_nodes = TRUE, protect_internal_absorbed_nodes = TRUE, valid_candidate_required = TRUE, preserved_relation_sets = as.list(c("CNT", "WIT", "INT", "CON")), maximum_attempts_per_entity = 10L, failure_keeps_original_geometry = TRUE, sn_reconstructed_from_final_geometry = TRUE),
        operation_order = as.list(c("entity_removal_and_road_link_absorption", "geometry_perturbation", "attribute_perturbation_and_geometry_dependent_updates", "raster_perturbation", "reconstruct_all_derived_observations")),
        attribute_perturbation = list(geometry_dependent_building_attributes_recomputed = TRUE, road_lane_attribute_synchronized = TRUE),
        raster_perturbation = list(scene_raster_recomputed_after_geometry = TRUE, land_cover = list(method = "eight_neighbor_round_robin_block_growth", maximum_active_fronts = 4L, target_count = "round_fraction_times_valid", intentional_mask_distinct_from_nodata = TRUE, scene_entity_realization_shared = TRUE), dem = list(gaussian_noise = TRUE, scene_entity_realization_shared = TRUE)),
        derived_reconstruction = as.list(c("entity_center", "relative_position", "intrinsic_geometry", "geometry_derived_building_attributes", "road_lane_attribute", "entity_environmental_background", "scene_raster_inputs", "spatial_relation_graph", "SN", "source_node_identity_based_CON"))
      )
    ),
    model = list(
      citations = list(
        p0_citation("template/materials/tables/results-02-model-dimension-table.typ", 19L, 57L),
        p0_citation("template/materials/tables/results-03-model-structural-configuration-table.typ", 122L, 130L),
        p0_citation("template/materials/tables/results-05-model-architecture-table.typ", 34L, 444L),
        p0_citation("template/materials/tables/results-04-training-configuration-table.typ", 147L, 150L)
      ),
      contract = list(
        dimensions = list(d = 64L, d_c = 64L, d_t = 16L, d_r = 32L),
        contextualization = list(relation_layers = 3L, attention_heads = 4L, head_dimension = 16L, ffn = as.list(c(64L, 128L, 64L))),
        dropout = 0.2, architecture_rows = architecture
      )
    ),
    training = list(
      citations = list(
        p0_citation("template/materials/tables/results-04-training-configuration-table.typ", 96L, 190L),
        p0_citation("template/sections/chapters/results/01-experimental-setup.typ", 81L, 83L),
        p0_citation("template/sections/chapters/results/03-representation-analysis.typ", 86L, 137L)
      ),
      contract = list(
        global_effective_batch_size = 32L, optimizer = "AdamW", peak_learning_rate = 1e-3,
        weight_decay = 1e-4, maximum_epochs = 200L, warmup_epochs = 10L,
        post_warmup_schedule = "cosine_decay", gradient_clipping_norm = 1.0,
        lambda_ip = 1.0, ema_momentum = 0.999, queue_capacity = 8192L,
        temperature = 0.1, negative_exclusion_distance_m = 750L,
        modality_masking_probability = 0.30, validation_interval_epochs = 5L,
        early_stopping_patience_validation_events = 4L,
        improvement_threshold_retrieval_loss = 1e-4,
        checkpoint_selection = as.list(c("lower_validation_retrieval_loss", "if_difference_below_1e-4_larger_mean_source_separation_margin", "earlier_epoch")),
        supplementary_only_metrics = as.list(c("MRR", "HIT@K"))
      )
    ),
    evaluation = list(
      citations = list(
        p0_citation("template/sections/chapters/results/01-experimental-setup.typ", 19L, 29L),
        p0_citation("template/sections/chapters/results/03-representation-analysis.typ", 9L, 22L),
        p0_citation("template/sections/chapters/results/03-representation-analysis.typ", 86L, 137L),
        p0_citation("template/sections/chapters/results/02-spatial-scene-retrieval.typ", 6L, 8L)
      ),
      contract = list(
        validation = list(originals = 400L, augmented_queries = 800L, gallery = 400L),
        evaluation = list(originals = 1600L, augmented_queries = 3200L, gallery = 1600L),
        fixed_query_profile = 1.0, fixed_query_identity_configuration_independent = TRUE,
        seed_namespaces = as.list(c("training-bank", "validation-query", "evaluation-query")),
        held_out_evaluation_ancestry = "prohibited_for_training_checkpoint_early_stopping_hyperparameter_selection",
        metrics = list(primary = "retrieval_loss", tie_break = "mean_source_separation_margin", supplementary = as.list(c("MRR", "HIT@K"))),
        qualitative_retrieval = list(query_count = 10L, standard_candidate_count = 1599L, non_local_threshold_m = 2000L),
        representation_analysis = as.list(c("UMAP", "HDBSCAN")),
        controlled_evaluation = as.list(c("ablation", "controlled_baselines", "final_model_comparison"))
      )
    ),
    downstream = list(
      citations = list(
        p0_citation("template/sections/chapters/results/04-downstream-representation-utility.typ", 10L, 71L),
        p0_citation("template/materials/tables/results-06-downstream-datasets.typ", 19L, 42L)
      ),
      contract = list(
        representation = "frozen_scene_embeddings", encoder_fine_tuning = FALSE,
        estimator = "ridge_regression", ridge_penalty = 1.0,
        targets = as.list(c("total_population", "households", "housing_units", "establishments", "workers", "living_population_weekday_daytime", "living_population_weekday_nighttime", "living_population_weekend_daytime", "living_population_weekend_nighttime", "official_land_value", "land_surface_temperature")),
        spatial_folds = list(unit = "Seoul_autonomous_district", count = 25L, protocol = "leave_one_district_out"),
        fitting_scope = "training_folds_only", standardization_scope = "training_folds_only",
        leakage_checks = as.list(c("target_fit_excludes_test_fold", "standardization_excludes_test_fold", "frozen_encoder")),
        coverage_checks = as.list(c("scene_target_join_coverage", "fold_target_coverage")),
        outputs = as.list(c("fold_predictions", "fold_metrics", "aggregate_metrics", "coverage_report", "leakage_report"))
      )
    )
  )
}

p0_extract_citation <- function(citation, source_set, repository_path) {
  known <- vapply(source_set$ordered_files, `[[`, character(1L), "path")
  if (!citation$path %in% known) stop("Methodology citation is outside imported source set: ", citation$path, call. = FALSE)
  path <- file.path(repository_path, citation$path)
  lines <- readLines(path, warn = FALSE, encoding = "UTF-8")
  if (citation$start_line > citation$end_line || citation$end_line > length(lines)) {
    stop("Invalid methodology citation range: ", citation$path, call. = FALSE)
  }
  evidence <- paste(lines[seq.int(citation$start_line, citation$end_line)], collapse = "\n")
  c(citation, list(evidence_sha256 = digest::digest(evidence, algo = "sha256", serialize = FALSE)))
}

build_p0_module_contract <- function(module_name, source_set_file, conflict_gate_file, spec) {
  definitions <- p0_module_definitions()
  if (!module_name %in% names(definitions)) stop("Unknown P0 methodology module: ", module_name, call. = FALSE)
  source_set <- jsonlite::read_json(source_set_file, simplifyVector = FALSE)
  gate <- jsonlite::read_json(conflict_gate_file, simplifyVector = FALSE)
  if (!identical(source_set$status, "PASS")) stop("P0 source set is not accepted", call. = FALSE)
  if (!identical(gate$status, "PASS")) stop("P0 dissertation conflict gate is not accepted", call. = FALSE)
  definition <- definitions[[module_name]]
  citations <- lapply(definition$citations, p0_extract_citation, source_set = source_set,
                      repository_path = spec$dissertation$repository_path)
  scientific <- list(
    schema_version = spec$schema_version, module_name = module_name,
    authoritative_source_citations = citations,
    canonical_contract = definition$contract, source_set_id = source_set$source_set_id,
    extraction_validation_implementation_sha256 = spec$implementation_sha256,
    unresolved_fields = list(), conflicting_fields = list(), status = "PASS"
  )
  content_hash <- p0_scientific_sha256(scientific)
  value <- c(list(
    schema_version = spec$schema_version,
    contract_id = paste0("mmc_", substr(content_hash, 1L, 16L)),
    module_name = module_name
  ), scientific[setdiff(names(scientific), c("schema_version", "module_name"))],
  list(module_content_sha256 = content_hash))
  final_dir <- p0_component_dir(spec, file.path("modules", module_name), value$contract_id)
  p0_publish_json_component(value, final_dir, paste0(module_name, "_methodology_contract.json"), spec$schemas[["module_contract"]])
}

p0_conflict_observation <- function(value, path, start_line, end_line, evidence_contains) {
  list(value = value, citation = p0_citation(path, start_line, end_line),
       evidence_contains = evidence_contains)
}

p0_actual_conflict_checks <- function() {
  list(
    list(module = "scene", field = "scene_dimensions_m", observations = list(
      p0_conflict_observation(c(500L, 500L), "template/sections/chapters/results/01-experimental-setup.typ", 17L, 19L, "500"),
      p0_conflict_observation(c(500L, 500L), "template/materials/tables/results-03-model-structural-configuration-table.typ", 19L, 21L, "500")
    )),
    list(module = "scene", field = "off_grid_minimum_distance_m", observations = list(
      p0_conflict_observation(50L, "template/sections/chapters/results/01-experimental-setup.typ", 21L, 21L, "50"),
      p0_conflict_observation(50L, "template/materials/tables/results-03-model-structural-configuration-table.typ", 150L, 153L, "50")
    )),
    list(module = "base_spatial", field = "sn_radius_m", relationship = "supporting_detail", observations = list(
      p0_conflict_observation(100L, "template/materials/tables/results-03-model-structural-configuration-table.typ", 108L, 111L, "100")
    )),
    list(module = "model", field = "d", observations = list(
      p0_conflict_observation(64L, "template/materials/tables/results-02-model-dimension-table.typ", 19L, 22L, "64"),
      p0_conflict_observation(64L, "template/materials/tables/results-05-model-architecture-table.typ", 34L, 45L, "64")
    )),
    list(module = "model", field = "d_c", observations = list(
      p0_conflict_observation(64L, "template/materials/tables/results-02-model-dimension-table.typ", 54L, 57L, "64"),
      p0_conflict_observation(64L, "template/materials/tables/results-05-model-architecture-table.typ", 368L, 378L, "64")
    )),
    list(module = "model", field = "relation_attention_heads", observations = list(
      p0_conflict_observation(4L, "template/materials/tables/results-03-model-structural-configuration-table.typ", 122L, 130L, "4"),
      p0_conflict_observation(4L, "template/materials/tables/results-05-model-architecture-table.typ", 245L, 250L, "4 heads")
    )),
    list(module = "augmentation", field = "main_k_aug", observations = list(
      p0_conflict_observation(8L, "template/materials/tables/results-04-training-configuration-table.typ", 23L, 26L, "8"),
      p0_conflict_observation(8L, "template/sections/chapters/results/05-hyperparameter-study.typ", 10L, 10L, "=8")
    )),
    list(module = "augmentation", field = "fixed_pre_generated_bank", observations = list(
      p0_conflict_observation(TRUE, "template/sections/chapters/04-methodology-training.typ", 14L, 18L, "generated once before training"),
      p0_conflict_observation(TRUE, "template/sections/appendices/appendix-b.typ", 7L, 7L, "remained fixed throughout training")
    )),
    list(module = "augmentation", field = "road_link_absorption", relationship = "supporting_detail", observations = list(
      p0_conflict_observation(TRUE, "template/sections/appendices/appendix-b.typ", 16L, 16L, "absorption")
    )),
    list(module = "training", field = "peak_learning_rate", observations = list(
      p0_conflict_observation(1e-3, "template/materials/tables/results-04-training-configuration-table.typ", 157L, 160L, "1 times 10^(-3)"),
      p0_conflict_observation(1e-3, "template/sections/chapters/results/05-hyperparameter-study.typ", 19L, 19L, "1 times 10^(-3)")
    )),
    list(module = "training", field = "lambda_ip", observations = list(
      p0_conflict_observation(1.0, "template/materials/tables/results-04-training-configuration-table.typ", 143L, 146L, "$1$"),
      p0_conflict_observation(1.0, "template/sections/chapters/results/05-hyperparameter-study.typ", 17L, 17L, "=1")
    )),
    list(module = "evaluation", field = "validation_evaluation_counts", observations = list(
      p0_conflict_observation(c(400L, 1600L), "template/sections/chapters/results/01-experimental-setup.typ", 21L, 21L, "1,600"),
      p0_conflict_observation(c(400L, 1600L), "template/sections/chapters/results/03-representation-analysis.typ", 22L, 22L, "3,200")
    )),
    list(module = "evaluation", field = "checkpoint_selection_order", observations = list(
      p0_conflict_observation(c("retrieval_loss", "source_separation_margin", "earlier_epoch"), "template/sections/chapters/results/01-experimental-setup.typ", 83L, 83L, "retrieval loss"),
      p0_conflict_observation(c("retrieval_loss", "source_separation_margin", "earlier_epoch"), "template/sections/chapters/results/03-representation-analysis.typ", 135L, 137L, "earlier epoch")
    )),
    list(module = "downstream", field = "frozen_ridge_probe", relationship = "supporting_detail", observations = list(
      p0_conflict_observation(TRUE, "template/sections/chapters/results/04-downstream-representation-utility.typ", 29L, 31L, "frozen scene representations")
    ))
  )
}

p0_normalize_conflict_value <- function(value) {
  if (is.character(value)) return(tolower(trimws(value)))
  if (is.numeric(value)) return(as.numeric(value))
  if (is.logical(value)) return(value)
  if (is.list(value)) return(p0_sort_named_objects(lapply(value, p0_normalize_conflict_value)))
  value
}

evaluate_p0_conflicts <- function(checks, source_set, repository_path,
                                  schema_version = "1.0.0") {
  known <- vapply(source_set$ordered_files, `[[`, character(1L), "path")
  records <- lapply(seq_along(checks), function(i) {
    check <- checks[[i]]
    missing_evidence <- FALSE
    sources <- lapply(check$observations, function(observation) {
      citation <- observation$citation
      if (!citation$path %in% known) {
        missing_evidence <<- TRUE
        return(c(citation, list(evidence_status = "source_not_imported")))
      }
      lines <- readLines(file.path(repository_path, citation$path), warn = FALSE, encoding = "UTF-8")
      if (citation$start_line > citation$end_line || citation$end_line > length(lines)) {
        missing_evidence <<- TRUE
        return(c(citation, list(evidence_status = "invalid_line_range")))
      }
      evidence <- paste(lines[seq.int(citation$start_line, citation$end_line)], collapse = "\n")
      if (!grepl(observation$evidence_contains, evidence, fixed = TRUE)) missing_evidence <<- TRUE
      c(citation, list(evidence_sha256 = digest::digest(evidence, algo = "sha256", serialize = FALSE),
                       evidence_status = if (grepl(observation$evidence_contains, evidence, fixed = TRUE)) "MATCH" else "EXPECTED_TOKEN_ABSENT"))
    })
    normalized <- lapply(check$observations, function(observation) p0_normalize_conflict_value(observation$value))
    distinct <- unique(vapply(normalized, function(value) canonical_json(p0_sort_named_objects(value)), character(1L)))
    relationship <- if (is.null(check$relationship)) "cross_source" else check$relationship
    classification <- if (missing_evidence) {
      "BLOCKED_BY_MISSING_EVIDENCE"
    } else if (length(distinct) > 1L) {
      "BLOCKED_BY_DISSERTATION_CONFLICT"
    } else if (identical(relationship, "supporting_detail") || length(normalized) == 1L) {
      "SUPPORTING_DETAIL"
    } else if (identical(relationship, "non_scientific")) {
      "NON_SCIENTIFIC_DIFFERENCE"
    } else {
      "CONSISTENT"
    }
    blocked <- startsWith(classification, "BLOCKED_BY_")
    list(
      conflict_id = sprintf("p0_conflict_%03d", i), module = check$module,
      scientific_field = check$field, normalized_values = normalized,
      sources = sources, severity = if (blocked) "blocking" else "info",
      classification = classification,
      resolution_status = if (blocked) "BLOCKED" else "RESOLVED"
    )
  })
  blocking <- sum(vapply(records, function(x) identical(x$classification, "BLOCKED_BY_DISSERTATION_CONFLICT"), logical(1L)))
  missing <- sum(vapply(records, function(x) identical(x$classification, "BLOCKED_BY_MISSING_EVIDENCE"), logical(1L)))
  status <- if (blocking > 0L) "BLOCKED_BY_DISSERTATION_CONFLICT" else if (missing > 0L) "BLOCKED_BY_MISSING_EVIDENCE" else "PASS"
  scientific <- list(
    schema_version = schema_version, source_set_id = source_set$source_set_id,
    records = records, blocking_conflict_count = as.integer(blocking),
    missing_evidence_count = as.integer(missing), unclassified_conflict_count = 0L,
    status = status
  )
  content_hash <- p0_scientific_sha256(scientific)
  c(list(schema_version = schema_version,
         conflict_gate_id = paste0("mcg_", substr(content_hash, 1L, 16L))),
    scientific[setdiff(names(scientific), "schema_version")],
    list(content_sha256 = content_hash))
}

build_reduced_methodology_conflict_gate <- function(source_set_file, spec) {
  source_set <- jsonlite::read_json(source_set_file, simplifyVector = FALSE)
  if (!identical(source_set$status, "PASS")) stop("P0 source set is not accepted", call. = FALSE)
  value <- evaluate_p0_conflicts(p0_actual_conflict_checks(), source_set,
                                 spec$dissertation$repository_path, spec$schema_version)
  final_dir <- p0_component_dir(spec, "conflict_gate", value$conflict_gate_id)
  p0_publish_json_component(value, final_dir, "methodology_conflict_gate.json", spec$schemas[["conflict_gate"]])
}

p0_read_single_json <- function(path) {
  jsonlite::read_json(path, simplifyVector = FALSE)
}

p0_authority_id <- function(schema_version, dissertation_commit_sha,
                            ordered_source_hashes, module_contract_hashes,
                            conflict_gate_result, implementation_version,
                            implementation_sha256, environment = NULL) {
  identity_inputs <- list(
    schema_version = schema_version,
    dissertation_commit_sha = dissertation_commit_sha,
    ordered_source_hashes = ordered_source_hashes,
    module_contract_hashes = module_contract_hashes,
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
  modules <- lapply(module_contract_files, p0_read_single_json)
  expected_modules <- names(p0_module_definitions())
  observed_modules <- vapply(modules, `[[`, character(1L), "module_name")
  if (!identical(git_state$verification_status, "PASS")) stop("P0 Git state blocks authority publication", call. = FALSE)
  if (!identical(source_set$status, "PASS")) stop("P0 source set blocks authority publication", call. = FALSE)
  if (!identical(gate$status, "PASS") || gate$unclassified_conflict_count != 0L) stop("P0 conflict gate blocks authority publication", call. = FALSE)
  if (!setequal(observed_modules, expected_modules) || length(modules) != 8L) stop("P0 module contract set is incomplete", call. = FALSE)
  if (any(vapply(modules, function(x) !identical(x$status, "PASS"), logical(1L)))) stop("A P0 module contract is not accepted", call. = FALSE)
  modules <- modules[match(expected_modules, observed_modules)]
  ordered_hashes <- lapply(source_set$ordered_files, function(file) list(path = file$path, sha256 = file$sha256))
  module_records <- lapply(modules, function(module) list(
    module_name = module$module_name, contract_id = module$contract_id,
    sha256 = module$module_content_sha256
  ))
  module_records <- unname(module_records)
  authority_id <- p0_authority_id(
    spec$schema_version, source_set$commit_sha, ordered_hashes,
    lapply(module_records, function(x) list(module_name = x$module_name, sha256 = x$sha256)),
    list(id = gate$conflict_gate_id, status = gate$status, content_sha256 = gate$content_sha256),
    spec$implementation_version, spec$implementation_sha256
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
    aggregate_content_sha256 = aggregate_hash,
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
