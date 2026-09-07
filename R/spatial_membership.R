membership_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/membership.yml",
    "config/membership_runtime.yml",
    "config/schemas/membership_branch.schema.json"
  ))
}

load_membership_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c(
    "membership.yml", "membership_runtime.yml",
    "membership_branch.schema.json"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing membership contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  scientific <- yaml::read_yaml(by_name[["membership.yml"]])
  runtime <- yaml::read_yaml(by_name[["membership_runtime.yml"]])
  repository_root <- dirname(dirname(by_name[["membership.yml"]]))
  implementation_file <- normalizePath(file.path(repository_root, "R/spatial_membership.R"), mustWork = TRUE)
  validate_membership_config(scientific, runtime)
  list(
    scientific = scientific,
    runtime = runtime,
    schema_file = by_name[["membership_branch.schema.json"]],
    implementation_file = implementation_file,
    scientific_hash = sha256_file(by_name[["membership.yml"]]),
    runtime_hash = sha256_file(by_name[["membership_runtime.yml"]]),
    schema_hash = sha256_file(by_name[["membership_branch.schema.json"]]),
    implementation_hash = canonical_sha256(list(
      exact_membership_pairs = paste(deparse(body(exact_membership_pairs)), collapse = "\n"),
      validate_membership_candidates = paste(deparse(body(validate_membership_candidates)), collapse = "\n"),
      read_membership_candidates = paste(deparse(body(read_membership_candidates)), collapse = "\n")
    )),
    implementation_source_hash = sha256_file(implementation_file)
  )
}

validate_membership_config <- function(scientific, runtime) {
  expected <- list(
    epsg = c(scientific$processing_epsg, 5186),
    building = c(scientific$predicates$building$rule, "positive_area_intersection"),
    road = c(scientific$predicates$road$rule, "positive_length_intersection"),
    poi = c(scientific$predicates$poi$rule, "covered_by_closed_scene_footprint"),
    building_touch = c(scientific$predicates$building$boundary_only_contact, "exclude"),
    road_touch = c(scientific$predicates$road$boundary_only_contact, "exclude"),
    poi_touch = c(scientific$predicates$poi$boundary_only_contact, "include"),
    controller = c(runtime$controller, "controller_40"),
    workers = c(runtime$branch_workers, 1),
    threads = c(runtime$threads_per_worker, 1)
  )
  invalid <- names(expected)[vapply(expected, function(x) !identical(as.character(x[[1L]]), as.character(x[[2L]])), logical(1L))]
  if (length(invalid)) stop("Membership contract mismatch: ", paste(invalid, collapse = ", "), call. = FALSE)
  required_columns <- c(
    "scene_id", "scene_footprint_id", "split", "entity_type", "source_entity_id",
    "source_layer", "membership_predicate_version", "branch_id", "source_artifact_id",
    "scene_index_id", "scope_id"
  )
  if (!identical(names(scientific$membership_columns), required_columns)) {
    stop("Membership column contract or order changed", call. = FALSE)
  }
  if (any(vapply(scientific$geometry_policy[c("invalid", "empty", "geometry_collection", "duplicate_source_id")],
                 function(x) !identical(x, "fail_branch"), logical(1L)))) {
    stop("Unsafe membership geometry policy", call. = FALSE)
  }
  invisible(TRUE)
}
membership_thread_state <- function() {
  variables <- c(native_thread_environment_variables(), "ARROW_NUM_THREADS")
  list(environment = Sys.getenv(variables, unset = NA_character_), data_table = data.table::getDTthreads())
}

set_membership_threads <- function(threads = 1L) {
  threads <- assert_positive_integer(threads, "membership threads")
  variables <- c(native_thread_environment_variables(), "ARROW_NUM_THREADS")
  do.call(Sys.setenv, as.list(setNames(rep(as.character(threads), length(variables)), variables)))
  data.table::setDTthreads(threads)
  invisible(threads)
}

restore_membership_threads <- function(state) {
  missing <- names(state$environment)[is.na(state$environment)]
  present <- state$environment[!is.na(state$environment)]
  if (length(missing)) Sys.unsetenv(missing)
  if (length(present)) do.call(Sys.setenv, as.list(present))
  data.table::setDTthreads(state$data_table)
  invisible(NULL)
}

validate_membership_spec <- function(path, schema_file) {
  validate_json_schema_file(path, schema_file)
  value <- jsonlite::read_json(path, simplifyVector = FALSE)
  if (!identical(sort(unlist(value$scene_ids), method = "radix"), sort(vapply(value$scenes, `[[`, character(1L), "scene_id"), method = "radix"))) {
    stop("Membership spec scene_ids and scenes disagree: ", path, call. = FALSE)
  }
  invisible(TRUE)
}

publish_deterministic_directory <- function(final_dir, required_basenames, writer, compare_basenames = required_basenames) {
  dir.create(dirname(final_dir), recursive = TRUE, showWarnings = FALSE)
  stage <- tempfile(pattern = paste0(".", basename(final_dir), ".stage-"), tmpdir = dirname(final_dir))
  dir.create(stage)
  on.exit(if (dir.exists(stage)) unlink(stage, recursive = TRUE), add = TRUE)
  writer(stage)
  staged <- file.path(stage, required_basenames)
  if (!all(file.exists(staged)) || any(file.info(staged)$size <= 0)) {
    stop("Staged membership bundle is incomplete: ", stage, call. = FALSE)
  }
  final <- file.path(final_dir, required_basenames)
  if (dir.exists(final_dir)) {
    if (!all(file.exists(final))) stop("Existing membership bundle is incomplete: ", final_dir, call. = FALSE)
    stage_compare <- file.path(stage, compare_basenames)
    final_compare <- file.path(final_dir, compare_basenames)
    staged_hashes <- unname(vapply(stage_compare, sha256_file, character(1L)))
    final_hashes <- unname(vapply(final_compare, sha256_file, character(1L)))
    if (!identical(staged_hashes, final_hashes)) {
      stop("Existing content-addressed membership artifact is non-deterministic: ", final_dir, call. = FALSE)
    }
    return(normalizePath(final, mustWork = TRUE))
  }
  if (!file.rename(stage, final_dir)) stop("Atomic membership directory publish failed: ", final_dir, call. = FALSE)
  normalizePath(final, mustWork = TRUE)
}

membership_scene_sf <- function(spec) {
  records <- spec$scenes
  geometry <- lapply(records, function(x) sf::st_polygon(list(matrix(c(
    x$xmin, x$ymin, x$xmax, x$ymin, x$xmax, x$ymax,
    x$xmin, x$ymax, x$xmin, x$ymin
  ), ncol = 2L, byrow = TRUE))))
  sf::st_sf(
    scene_id = vapply(records, `[[`, character(1L), "scene_id"),
    scene_footprint_id = vapply(records, `[[`, character(1L), "scene_footprint_id"),
    split = vapply(records, `[[`, character(1L), "split"),
    geometry = sf::st_sfc(geometry, crs = 5186L)
  )
}

read_membership_candidates <- function(source, scenes) {
  id <- gsub('"', '""', source$source_id_column, fixed = TRUE)
  layer <- gsub('"', '""', source$layer, fixed = TRUE)
  filter <- sf::st_as_text(sf::st_union(sf::st_geometry(scenes)))
  query <- sprintf('SELECT "%s" AS source_entity_id, geom FROM "%s"', id, layer)
  value <- sf::st_read(source$path, query = query, wkt_filter = filter, quiet = TRUE, stringsAsFactors = FALSE)
  value$source_entity_id <- as.character(value$source_entity_id)
  value
}

validate_membership_candidates <- function(value, role, geometry_policy) {
  if (!nrow(value)) return(list(invalid = 0L, empty = 0L, geometry_collection = 0L))
  if (anyNA(value$source_entity_id) || any(!nzchar(value$source_entity_id)) || anyDuplicated(value$source_entity_id)) {
    stop("Missing or duplicate source ID in ", role, " candidate set", call. = FALSE)
  }
  empty <- sf::st_is_empty(value)
  valid <- sf::st_is_valid(value)
  types <- as.character(sf::st_geometry_type(value))
  collection <- types == "GEOMETRYCOLLECTION"
  if (any(empty) || any(!valid) || any(collection)) {
    stop(sprintf("Unsupported %s candidate geometry: empty=%d invalid=%d collection=%d",
                 role, sum(empty), sum(!valid), sum(collection)), call. = FALSE)
  }
  allowed <- switch(role,
    building = c("POLYGON", "MULTIPOLYGON"),
    road = c("LINESTRING", "MULTILINESTRING"),
    poi = c("POINT", "MULTIPOINT")
  )
  if (any(!types %in% allowed)) stop("Unexpected ", role, " geometry type", call. = FALSE)
  list(invalid = 0L, empty = 0L, geometry_collection = 0L)
}

empty_membership_table <- function() {
  data.frame(
    scene_id = character(), scene_footprint_id = character(), split = character(),
    entity_type = character(), source_entity_id = character(), source_layer = character(),
    membership_predicate_version = character(), branch_id = character(),
    source_artifact_id = character(), scene_index_id = character(), scope_id = character(),
    stringsAsFactors = FALSE
  )
}

exact_membership_pairs <- function(scenes, entities, role, spec) {
  if (!nrow(entities)) return(empty_membership_table())
  # DE-9IM interior/interior contact is equivalent to positive retained area
  # for polygons and positive retained length for lines against a polygon scene.
  hits <- if (identical(role, "poi")) {
    sf::st_intersects(scenes, entities)
  } else {
    sf::st_relate(scenes, entities, pattern = "T********")
  }
  scene_index <- rep(seq_along(hits), lengths(hits))
  entity_index <- unlist(hits, use.names = FALSE)
  if (!length(entity_index)) return(empty_membership_table())
  source <- spec$sources[[role]]
  result <- data.frame(
    scene_id = scenes$scene_id[scene_index],
    scene_footprint_id = scenes$scene_footprint_id[scene_index],
    split = scenes$split[scene_index],
    entity_type = source$entity_type,
    source_entity_id = entities$source_entity_id[entity_index],
    source_layer = source$layer,
    membership_predicate_version = spec$membership_contract$version,
    branch_id = spec$branch_id,
    source_artifact_id = source$source_artifact_id,
    scene_index_id = spec$scene_index_id,
    scope_id = spec$scope_id,
    stringsAsFactors = FALSE
  )
  result <- result[order(result$scene_id, result$entity_type, result$source_entity_id, method = "radix"), , drop = FALSE]
  rownames(result) <- NULL
  if (anyDuplicated(result[c("scene_id", "entity_type", "source_entity_id")])) {
    stop("Duplicate exact membership row in ", role, call. = FALSE)
  }
  result
}

proc_io_snapshot <- function() {
  path <- "/proc/self/io"
  if (!file.exists(path)) return(list(read_bytes = NA_real_, write_bytes = NA_real_))
  lines <- readLines(path, warn = FALSE)
  value <- function(key) as.numeric(sub("^[^:]+:[[:space:]]*", "", grep(paste0("^", key, ":"), lines, value = TRUE)))
  list(read_bytes = value("read_bytes"), write_bytes = value("write_bytes"))
}

proc_max_rss_kb <- function() {
  lines <- readLines("/proc/self/status", warn = FALSE)
  line <- grep("^VmHWM:", lines, value = TRUE)
  if (!length(line)) return(NA_real_)
  as.numeric(gsub("[^0-9]", "", line[[1L]]))
}

write_json_lines <- function(records, path) {
  lines <- vapply(records, canonical_json, character(1L))
  writeLines(lines, path, useBytes = TRUE)
  path
}

membership_output_names <- function() c(
  "building_membership.parquet", "road_membership.parquet", "poi_membership.parquet",
  "branch_manifest.json", "branch_qc.json", "branch_log.jsonl"
)

validate_membership_table <- function(value, spec, entity_type) {
  expected <- names(load_membership_config(membership_contract_paths())$scientific$membership_columns)
  if (!identical(names(value), expected)) stop("Membership Parquet schema column mismatch", call. = FALSE)
  if (nrow(value) && (!all(value$entity_type == entity_type) || anyDuplicated(value[c("scene_id", "entity_type", "source_entity_id")]))) {
    stop("Membership Parquet content invariant failed", call. = FALSE)
  }
  if (nrow(value) && (!all(value$branch_id == spec$branch_id) || !all(value$scene_id %in% unlist(spec$scene_ids)))) {
    stop("Membership Parquet branch reference mismatch", call. = FALSE)
  }
  invisible(TRUE)
}

normalize_membership_branch_outputs <- function(value) {
  paths <- unlist(value, recursive = TRUE, use.names = FALSE)
  manifests <- paths[grepl("branch_manifest[.]json$", paths)]
  if (!length(manifests)) stop("No membership branch manifests supplied", call. = FALSE)
  split(paths, dirname(paths))[dirname(manifests)]
}

membership_brute_force_sample <- function(specs, sample_count) {
  records <- do.call(rbind, lapply(specs, function(spec) {
    do.call(rbind, lapply(spec$scenes, function(x) data.frame(
      scene_id = x$scene_id, split = x$split, estimated_cost = x$estimated_cost,
      spec_path = spec$.path, stringsAsFactors = FALSE
    )))
  }))
  chosen <- integer()
  allocations <- c(training = sample_count - 4L, validation = 2L, evaluation = 2L)
  for (split in names(allocations)) {
    index <- which(records$split == split)
    index <- index[order(records$estimated_cost[index], records$scene_id[index], method = "radix")]
    positions <- unique(round(seq(1, length(index), length.out = allocations[[split]])))
    chosen <- c(chosen, index[positions])
  }
  chosen <- chosen[order(records$scene_id[chosen], method = "radix")]
  records[chosen, , drop = FALSE]
}

brute_force_membership_for_scene <- function(scene_record, spec) {
  single <- spec
  single$scenes <- list(scene_record)
  single$scene_ids <- scene_record$scene_id
  scenes <- membership_scene_sf(single)
  roles <- c("building", "road", "poi")
  tables <- lapply(roles, function(role) {
    candidates <- read_membership_candidates(spec$sources[[role]], scenes)
    validate_membership_candidates(candidates, role, list())
    exact_membership_pairs(scenes, candidates, role, spec)
  })
  do.call(rbind, tables)
}

membership_source_id_check <- function(parquet_paths, specs) {
  sources <- specs[[1L]]$sources
  python <- research_python_executable()
  payload <- tempfile(fileext = ".json")
  on.exit(unlink(payload), add = TRUE)
  write_json_file(list(parquet_paths = parquet_paths, sources = sources), payload)
  code <- paste0(
    "import json,sqlite3,sys,pyarrow.parquet as pq;",
    "p=json.load(open(sys.argv[1]));",
    "tabs=[pq.read_table(x,columns=['entity_type','source_entity_id']).to_pandas() for x in p['parquet_paths']];",
    "mapping={v['entity_type']:v for v in p['sources'].values()};",
    "bad=[];",
    "exec(\"for t in tabs:\\n for typ,g in t.groupby('entity_type'):\\n  s=mapping[typ]; c=sqlite3.connect('file:'+s['path']+'?mode=ro',uri=True); ids={str(x[0]) for x in c.execute('SELECT \\\"'+s['source_id_column']+'\\\" FROM \\\"'+s['layer']+'\\\"')}; c.close(); bad.extend(set(g.source_entity_id)-ids)\");",
    "print(len(bad));sys.exit(0 if not bad else 2)"
  )
  output <- system2(python, c("-c", shQuote(code), shQuote(payload)), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status") %||% 0L
  if (status != 0L || !identical(tail(output, 1L), "0")) stop("Membership source ID validation failed: ", paste(output, collapse = " | "), call. = FALSE)
  invisible(TRUE)
}
