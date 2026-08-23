membership_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/membership.yml",
    "config/membership_runtime.yml",
    "config/schemas/prototype_membership.schema.json"
  ))
}

load_membership_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c(
    "membership.yml", "membership_runtime.yml",
    "prototype_membership.schema.json"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing membership contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  scientific <- yaml::read_yaml(by_name[["membership.yml"]])
  runtime <- yaml::read_yaml(by_name[["membership_runtime.yml"]])
  repository_root <- dirname(dirname(by_name[["membership.yml"]]))
  implementation_file <- normalizePath(file.path(repository_root, "R/research_membership.R"), mustWork = TRUE)
  validate_membership_config(scientific, runtime)
  list(
    scientific = scientific,
    runtime = runtime,
    schema_file = by_name[["prototype_membership.schema.json"]],
    implementation_file = implementation_file,
    scientific_hash = sha256_file(by_name[["membership.yml"]]),
    runtime_hash = sha256_file(by_name[["membership_runtime.yml"]]),
    schema_hash = sha256_file(by_name[["prototype_membership.schema.json"]]),
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
    "scene_index_id", "prototype_id"
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

membership_ids_from_prototype <- function(prototype_paths) {
  manifest <- jsonlite::read_json(prototype_paths[grepl("manifest[.]json$", prototype_paths)], simplifyVector = FALSE)
  list(
    prototype_id = manifest$prototype_id,
    scene_index_id = manifest$identity$scene_index_id,
    prototype_root = dirname(prototype_paths[grepl("[.]parquet$", prototype_paths)])
  )
}

membership_source_contract <- function(config, research_config, inventory) {
  roles <- names(config$scientific$sources)
  file_records <- setNames(inventory$files, vapply(inventory$files, `[[`, character(1L), "role"))
  setNames(lapply(roles, function(role) {
    source <- config$scientific$sources[[role]]
    file <- file_records[[source$input_role]]
    list(
      role = role,
      entity_type = config$scientific$predicates[[role]]$entity_type,
      path = file$path,
      layer = source$source_layer,
      source_id_column = source$source_id_column,
      source_artifact_id = paste0("src_", substr(file$sha256, 1L, 24L)),
      sha256 = file$sha256,
      size_bytes = file$size_bytes
    )
  }), roles)
}

membership_scene_cost <- function(prototype, config) {
  weights <- config$scientific$sharding$proxy_weights
  as.numeric(
    prototype$building_intersection_proxy * weights$building +
      prototype$road_intersection_proxy * weights$road +
      prototype$poi_within_proxy * weights$poi
  )
}

membership_lpt_shards <- function(prototype, costs, target_shards, maximum_scenes, singleton_cost) {
  order <- order(-costs, prototype$scene_id, method = "radix")
  singleton <- order[costs[order] >= singleton_cost]
  regular <- setdiff(order, singleton)
  bin_count <- max(
    1L,
    as.integer(target_shards) - length(singleton),
    ceiling(length(regular) / as.integer(maximum_scenes))
  )
  bins <- lapply(seq_len(bin_count), function(x) integer())
  loads <- numeric(bin_count)
  for (index in regular) {
    eligible <- which(lengths(bins) < as.integer(maximum_scenes))
    if (!length(eligible)) {
      bins[[length(bins) + 1L]] <- integer()
      loads <- c(loads, 0)
      eligible <- length(bins)
    }
    chosen <- eligible[order(loads[eligible], lengths(bins)[eligible], eligible)[[1L]]]
    bins[[chosen]] <- c(bins[[chosen]], index)
    loads[[chosen]] <- loads[[chosen]] + costs[[index]]
  }
  bins <- c(lapply(singleton, function(x) x), bins[lengths(bins) > 0L])
  bins <- lapply(bins, function(index) index[order(prototype$scene_id[index], method = "radix")])
  bins[order(vapply(bins, function(index) min(prototype$scene_id[index]), character(1L)), method = "radix")]
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

build_prototype_membership_plan <- function(prototype_scene_selection, study_data_inventory,
                                            membership_contract_files, research_config_files,
                                            workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- membership_thread_state()
  on.exit(restore_membership_threads(state), add = TRUE)
  set_membership_threads(threads)
  config <- load_membership_config(membership_contract_files)
  research <- load_research_config(research_config_files)
  inventory <- jsonlite::read_json(study_data_inventory, simplifyVector = FALSE)
  prototype <- sfarrow::st_read_parquet(prototype_scene_selection[grepl("prototype_scene_index[.]parquet$", prototype_scene_selection)])
  ids <- membership_ids_from_prototype(prototype_scene_selection)
  if (nrow(prototype) != 320L || anyDuplicated(prototype$scene_id) || anyDuplicated(prototype$scene_footprint_id)) {
    stop("Prototype index failed membership-plan prerequisites", call. = FALSE)
  }
  costs <- membership_scene_cost(prototype, config)
  shard <- config$scientific$sharding
  bins <- membership_lpt_shards(
    prototype, costs, shard$target_shards, shard$maximum_scenes_per_shard,
    shard$oversize_singleton_cost
  )
  sources <- membership_source_contract(config, research, inventory)
  scientific_identity <- list(
    prototype_id = ids$prototype_id,
    scene_index_id = ids$scene_index_id,
    inventory_id = inventory$inventory_id,
    membership_config_hash = config$scientific_hash,
    membership_schema_hash = config$schema_hash,
    implementation_hash = config$implementation_hash
  )
  dataset_id <- short_hash_id("pmd_", scientific_identity)
  plan_identity <- list(
    membership_dataset_id = dataset_id,
    sharding = shard,
    runtime_hash = config$runtime_hash
  )
  plan_id <- short_hash_id("pmp_", plan_identity)
  plan_dir <- file.path(ids$prototype_root, "plans", "membership", plan_id)
  geometry <- sf::st_geometry(prototype)
  boxes <- t(vapply(geometry, sf::st_bbox, numeric(4L)))
  colnames(boxes) <- c("xmin", "ymin", "xmax", "ymax")
  spec_values <- lapply(seq_along(bins), function(position) {
    index <- bins[[position]]
    scene_ids <- sort(prototype$scene_id[index], method = "radix")
    branch_scientific <- list(
      stage = "prototype_membership", spec_schema_version = "1.0.0",
      membership_dataset_id = dataset_id, scene_ids = as.list(scene_ids),
      membership_config_hash = config$scientific_hash,
      membership_schema_hash = config$schema_hash,
      implementation_hash = config$implementation_hash
    )
    branch_id <- short_hash_id("pmb_", branch_scientific)
    selected <- match(scene_ids, prototype$scene_id)
    output_dir <- file.path(ids$prototype_root, "membership", dataset_id, "branches", branch_id)
    scenes <- lapply(selected, function(i) list(
      scene_id = prototype$scene_id[[i]],
      scene_footprint_id = prototype$scene_footprint_id[[i]],
      split = prototype$split[[i]],
      xmin = boxes[i, "xmin"], ymin = boxes[i, "ymin"],
      xmax = boxes[i, "xmax"], ymax = boxes[i, "ymax"],
      estimated_cost = costs[[i]]
    ))
    split_counts <- as.list(setNames(as.integer(table(factor(prototype$split[selected], levels = c("training", "validation", "evaluation")))), c("training", "validation", "evaluation")))
    list(
      spec_schema_version = "1.0.0", branch_id = branch_id,
      membership_dataset_id = dataset_id, prototype_id = ids$prototype_id,
      scene_index_id = ids$scene_index_id, scene_ids = as.list(scene_ids), scenes = scenes,
      split_counts = split_counts,
      estimated_counts = list(
        building = sum(prototype$building_intersection_proxy[selected]),
        road = sum(prototype$road_intersection_proxy[selected]),
        poi = sum(prototype$poi_within_proxy[selected])
      ),
      estimated_cost = sum(costs[selected]), sources = sources,
      membership_contract = list(
        version = config$scientific$membership_predicate_version,
        config_hash = config$scientific_hash, schema_hash = config$schema_hash,
        implementation_hash = config$implementation_hash,
        predicates = config$scientific$predicates,
        geometry_policy = config$scientific$geometry_policy
      ),
      output = list(
        directory = output_dir,
        staging_parent = dirname(output_dir),
        files = c("building_membership.parquet", "road_membership.parquet", "poi_membership.parquet",
                  "branch_manifest.json", "branch_qc.json", "branch_log.jsonl")
      ),
      execution = list(
        controller = config$runtime$controller, workers = config$runtime$branch_workers,
        threads = config$runtime$threads_per_worker,
        selected_max_concurrency = config$runtime$selected_max_concurrency,
        retry = config$runtime$retry, atomic_publish = config$runtime$publish
      )
    )
  })
  all_ids <- unlist(lapply(spec_values, `[[`, "scene_ids"), use.names = FALSE)
  if (length(all_ids) != 320L || anyDuplicated(all_ids) || !setequal(all_ids, prototype$scene_id)) {
    stop("Membership plan does not cover every prototype scene exactly once", call. = FALSE)
  }
  basenames <- vapply(spec_values, function(x) paste0("spec-", x$branch_id, ".json"), character(1L))
  outputs <- publish_deterministic_directory(plan_dir, basenames, function(stage) {
    for (i in seq_along(spec_values)) {
      path <- file.path(stage, basenames[[i]])
      write_json_file(spec_values[[i]], path)
      validate_membership_spec(path, config$schema_file)
    }
  })
  outputs <- outputs[order(outputs, method = "radix")]
  lapply(outputs, function(path) {
    value <- jsonlite::read_json(path, simplifyVector = FALSE)
    value$.path <- path
    value
  })
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
    source_artifact_id = character(), scene_index_id = character(), prototype_id = character(),
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
    prototype_id = spec$prototype_id,
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

build_prototype_membership_shard <- function(prototype_membership_plan, study_data_inputs,
                                             prototype_runtime_inputs,
                                             membership_contract_files,
                                             workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- membership_thread_state()
  on.exit(restore_membership_threads(state), add = TRUE)
  set_membership_threads(threads)
  config <- load_membership_config(membership_contract_files)
  spec <- prototype_membership_plan
  validate_membership_spec(spec$.path, config$schema_file)
  started <- Sys.time()
  io_start <- proc_io_snapshot()
  warnings <- character()
  result <- withCallingHandlers({
    scenes <- membership_scene_sf(spec)
    roles <- c("building", "road", "poi")
    runtime_sources <- setNames(lapply(roles, function(role) {
      runtime_source_record(spec$sources[[role]], prototype_runtime_inputs, role)
    }), roles)
    candidates <- setNames(lapply(roles, function(role) read_membership_candidates(runtime_sources[[role]], scenes)), roles)
    geometry_counts <- Map(validate_membership_candidates, candidates, roles, MoreArgs = list(geometry_policy = config$scientific$geometry_policy))
    tables <- Map(exact_membership_pairs, MoreArgs = list(scenes = scenes, spec = spec), entities = candidates, role = roles)
    names(tables) <- roles
    list(scenes = scenes, candidates = candidates, geometry_counts = geometry_counts, tables = tables)
  }, warning = function(w) {
    warnings <<- c(warnings, conditionMessage(w))
    invokeRestart("muffleWarning")
  })
  output_names <- membership_output_names()
  final_dir <- spec$output$directory
  paths <- publish_deterministic_directory(
    final_dir, output_names,
    compare_basenames = output_names[1:3],
    writer = function(stage) {
      parquet_paths <- file.path(stage, output_names[1:3])
      for (i in seq_along(result$tables)) {
        arrow::write_parquet(result$tables[[i]], parquet_paths[[i]], compression = "zstd", use_dictionary = TRUE)
        roundtrip <- arrow::read_parquet(parquet_paths[[i]], as_data_frame = TRUE)
        validate_membership_table(roundtrip, spec, spec$sources[[names(result$tables)[[i]]]]$entity_type)
      }
      io_end <- proc_io_snapshot()
      elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
      counts <- vapply(result$tables, nrow, integer(1L))
      per_scene <- lapply(result$tables, function(x) table(factor(x$scene_id, levels = result$scenes$scene_id)))
      zero <- vapply(per_scene, function(x) sum(x == 0L), integer(1L))
      log_records <- list(
        list(time = format(started, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul"), event = "branch_started", branch_id = spec$branch_id),
        list(time = kst_now(), event = "branch_completed", branch_id = spec$branch_id, status = "PASS", rows = as.list(counts))
      )
      write_json_lines(log_records, file.path(stage, output_names[[6L]]))
      qc <- list(
        qc_schema_version = "1.0.0", branch_id = spec$branch_id, status = "PASS", failures = list(),
        scene_count = nrow(result$scenes), entity_rows = as.list(counts),
        scene_count_distribution = lapply(per_scene, function(x) as.list(stats::setNames(as.integer(stats::quantile(as.numeric(x), c(0, .5, .95, 1), type = 1)), c("min", "median", "p95", "max")))),
        zero_entity_scene_count = as.list(zero), duplicate_membership_rows = 0L,
        invalid_geometry_count = 0L, empty_geometry_count = 0L, geometry_collection_count = 0L,
        warnings = as.list(unique(warnings))
      )
      write_json_file(qc, file.path(stage, output_names[[5L]]))
      hash_targets <- c(parquet_paths, file.path(stage, output_names[c(5L, 6L)]))
      output_records <- lapply(hash_targets, function(path) list(
        path = file.path(final_dir, basename(path)), size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)
      ))
      manifest <- list(
        manifest_schema_version = "1.0.0", branch_id = spec$branch_id,
        membership_dataset_id = spec$membership_dataset_id, prototype_id = spec$prototype_id,
        scene_index_id = spec$scene_index_id, status = "PASS",
        inputs = list(
          spec_path = normalizePath(spec$.path, mustWork = TRUE),
          sources = spec$sources,
          membership_config_hash = config$scientific_hash,
          membership_schema_hash = config$schema_hash,
          implementation_hash = config$implementation_hash,
          implementation_source_hash = config$implementation_source_hash
        ),
        execution = list(
          controller = "controller_40", workers = 1L, threads = 1L,
          wall_time_seconds = elapsed, max_rss_kb = proc_max_rss_kb(),
          read_bytes = io_end$read_bytes - io_start$read_bytes,
          write_bytes = io_end$write_bytes - io_start$write_bytes
        ),
        scene_count = nrow(result$scenes), entity_rows = as.list(counts), outputs = output_records,
        warnings = as.list(unique(warnings)), status_final = "PASS"
      )
      write_json_file(manifest, file.path(stage, output_names[[4L]]))
    }
  )
  paths
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
  output <- system2("python", c("-c", shQuote(code), shQuote(payload)), stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status") %||% 0L
  if (status != 0L || !identical(tail(output, 1L), "0")) stop("Membership source ID validation failed: ", paste(output, collapse = " | "), call. = FALSE)
  invisible(TRUE)
}

build_prototype_membership_acceptance <- function(prototype_membership_plan,
                                                  prototype_membership_shard,
                                                  prototype_scene_selection,
                                                  study_data_inventory,
                                                  membership_contract_files,
                                                  workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- membership_thread_state()
  on.exit(restore_membership_threads(state), add = TRUE)
  set_membership_threads(threads)
  config <- load_membership_config(membership_contract_files)
  specs <- prototype_membership_plan
  branches <- normalize_membership_branch_outputs(prototype_membership_shard)
  manifests <- lapply(branches, function(paths) jsonlite::read_json(paths[grepl("branch_manifest[.]json$", paths)], simplifyVector = FALSE))
  plan_ids <- unname(sort(vapply(specs, `[[`, character(1L), "branch_id"), method = "radix"))
  branch_ids <- unname(sort(vapply(manifests, `[[`, character(1L), "branch_id"), method = "radix"))
  if (!identical(plan_ids, branch_ids) || any(vapply(manifests, function(x) !identical(x$status_final, "PASS"), logical(1L)))) {
    stop("Membership branch set is incomplete or failed", call. = FALSE)
  }
  all_scene_ids <- unlist(lapply(specs, `[[`, "scene_ids"), use.names = FALSE)
  prototype <- sfarrow::st_read_parquet(prototype_scene_selection[grepl("prototype_scene_index[.]parquet$", prototype_scene_selection)])
  if (length(all_scene_ids) != 320L || anyDuplicated(all_scene_ids) || !setequal(all_scene_ids, prototype$scene_id)) {
    stop("Membership aggregate scope is not exactly 320 prototype scenes", call. = FALSE)
  }
  all_paths <- unlist(branches, use.names = FALSE)
  parquet_paths <- all_paths[grepl("_(membership)[.]parquet$", all_paths)]
  tables <- lapply(parquet_paths, arrow::read_parquet, as_data_frame = TRUE)
  combined <- data.table::rbindlist(tables, use.names = TRUE)
  expected_columns <- names(config$scientific$membership_columns)
  if (!identical(names(combined), expected_columns)) stop("Aggregate membership schema mismatch", call. = FALSE)
  key <- c("scene_id", "entity_type", "source_entity_id")
  if (anyDuplicated(combined[, ..key]) || !all(combined$scene_id %in% prototype$scene_id)) {
    stop("Aggregate membership key/reference validation failed", call. = FALSE)
  }
  for (manifest in manifests) {
    for (output in manifest$outputs) {
      if (!file.exists(output$path) || !identical(sha256_file(output$path), output$sha256)) {
        stop("Branch output checksum mismatch: ", output$path, call. = FALSE)
      }
    }
    actual <- combined[branch_id == manifest$branch_id, .N, by = entity_type]
    recorded <- unlist(manifest$entity_rows)
    names(recorded) <- vapply(manifest$inputs$sources, `[[`, character(1L), "entity_type")
    mismatch <- vapply(names(recorded), function(type) {
      count <- actual[entity_type == type, sum(N)]
      if (!length(count) || is.na(count)) count <- 0L
      !identical(as.numeric(count), as.numeric(recorded[[type]]))
    }, logical(1L))
    if (any(mismatch)) {
      stop("Branch manifest row count mismatch", call. = FALSE)
    }
  }
  membership_source_id_check(parquet_paths, specs)
  sample <- membership_brute_force_sample(specs, config$scientific$brute_force_qc$sample_count)
  brute <- lapply(seq_len(nrow(sample)), function(i) {
    spec <- specs[[which(vapply(specs, function(x) sample$scene_id[[i]] %in% unlist(x$scene_ids), logical(1L)))[[1L]]]]
    record_index <- which(vapply(spec$scenes, `[[`, character(1L), "scene_id") == sample$scene_id[[i]])[[1L]]
    record <- spec$scenes[[record_index]]
    brute_force_membership_for_scene(record, spec)
  })
  brute <- data.table::rbindlist(brute, use.names = TRUE)
  optimized <- combined[scene_id %in% sample$scene_id]
  brute_keys <- unique(brute[, ..key]); optimized_keys <- unique(optimized[, ..key])
  false_negative <- data.table::fsetdiff(brute_keys, optimized_keys)
  false_positive <- data.table::fsetdiff(optimized_keys, brute_keys)
  if (nrow(false_negative) || nrow(false_positive)) stop("Brute-force membership comparison failed", call. = FALSE)
  ids <- membership_ids_from_prototype(prototype_scene_selection)
  dataset_id <- specs[[1L]]$membership_dataset_id
  acceptance_id <- short_hash_id("pma_", list(
    membership_dataset_id = dataset_id,
    branch_ids = plan_ids,
    branch_parquet_hashes = sort(vapply(parquet_paths, sha256_file, character(1L)), method = "radix")
  ))
  final_dir <- file.path(ids$prototype_root, "membership", dataset_id, "acceptance", acceptance_id)
  output_names <- c(
    "aggregate_membership_manifest.json", "membership_plan.parquet", "branch_index.parquet",
    "membership_statistics_by_entity_type.parquet", "membership_statistics_by_scene.parquet",
    "shard_cost_model.parquet", "global_qc.json"
  )
  # Runtime telemetry is retained for cost calibration, but it is not part of
  # scientific immutable reuse. Worker count and timing must not change an
  # accepted membership dataset.
  outputs <- publish_deterministic_directory(final_dir, output_names, compare_basenames = output_names[c(2L, 4L, 5L)], writer = function(stage) {
    plan_table <- data.table::rbindlist(lapply(specs, function(x) data.table::data.table(
      branch_id = x$branch_id, membership_dataset_id = x$membership_dataset_id,
      prototype_id = x$prototype_id, scene_index_id = x$scene_index_id,
      scene_count = length(x$scene_ids), scene_ids_json = canonical_json(x$scene_ids),
      estimated_building = x$estimated_counts$building, estimated_road = x$estimated_counts$road,
      estimated_poi = x$estimated_counts$poi, estimated_cost = x$estimated_cost,
      spec_path = paste0("spec-", x$branch_id, ".json")
    )), use.names = TRUE)
    branch_index <- data.table::rbindlist(Map(function(x, paths) data.table::data.table(
      branch_id = x$branch_id, status = x$status_final, scene_count = x$scene_count,
      building_rows = x$entity_rows$building, road_rows = x$entity_rows$road, poi_rows = x$entity_rows$poi,
      wall_time_seconds = x$execution$wall_time_seconds, max_rss_kb = x$execution$max_rss_kb,
      read_bytes = x$execution$read_bytes, write_bytes = x$execution$write_bytes,
      manifest_path = paths[grepl("branch_manifest[.]json$", paths)]
    ), manifests, branches), use.names = TRUE)
    type_stats <- combined[, .(membership_rows = .N, scenes_with_entity = data.table::uniqueN(scene_id)), by = entity_type][order(entity_type)]
    grid <- data.table::CJ(scene_id = prototype$scene_id, entity_type = c("B", "R", "P"), unique = TRUE)
    scene_stats <- combined[, .(membership_count = .N), by = .(scene_id, entity_type)][grid, on = .(scene_id, entity_type)]
    scene_stats[is.na(membership_count), membership_count := 0L]
    scene_meta <- data.table::as.data.table(sf::st_drop_geometry(prototype))[, .(
      scene_id, scene_footprint_id, split, building_intersection_proxy,
      road_intersection_proxy, poi_within_proxy, total_entity_proxy
    )]
    scene_stats <- scene_meta[scene_stats, on = "scene_id"]
    cost_model <- branch_index[plan_table, on = "branch_id"][, .(
      branch_id, scene_count, estimated_cost, actual_rows = building_rows + road_rows + poi_rows,
      wall_time_seconds, max_rss_kb, read_bytes, write_bytes
    )]
    arrow::write_parquet(plan_table, file.path(stage, output_names[[2L]]), compression = "zstd")
    arrow::write_parquet(branch_index, file.path(stage, output_names[[3L]]), compression = "zstd")
    arrow::write_parquet(type_stats, file.path(stage, output_names[[4L]]), compression = "zstd")
    arrow::write_parquet(scene_stats, file.path(stage, output_names[[5L]]), compression = "zstd")
    arrow::write_parquet(cost_model, file.path(stage, output_names[[6L]]), compression = "zstd")
    proxy_cor <- stats::cor(cost_model$estimated_cost, cost_model$actual_rows, method = "spearman")
    qc <- list(
      qc_schema_version = "1.0.0", acceptance_id = acceptance_id, status = "PASS", failures = list(),
      branch_count = length(specs), scene_count = 320L,
      split_counts = as.list(table(factor(prototype$split, levels = c("training", "validation", "evaluation")))),
      checksum_validation = TRUE, schema_consistent = TRUE, source_id_validation = TRUE,
      duplicate_membership_rows = 0L, brute_force_sample_count = nrow(sample),
      brute_force_false_positive = 0L, brute_force_false_negative = 0L,
      deterministic_artifact_id = acceptance_id,
      exact_rows = as.list(setNames(type_stats$membership_rows, type_stats$entity_type)),
      zero_entity_scenes = as.list(setNames(scene_stats[, sum(membership_count == 0L), by = entity_type]$V1,
                                            scene_stats[, sum(membership_count == 0L), by = entity_type]$entity_type)),
      shard_actual_row_imbalance_max_over_median = max(cost_model$actual_rows) / stats::median(cost_model$actual_rows),
      proxy_actual_spearman = proxy_cor
    )
    write_json_file(qc, file.path(stage, output_names[[7L]]))
    manifest <- list(
      manifest_schema_version = "1.0.0", acceptance_id = acceptance_id,
      membership_dataset_id = dataset_id, prototype_id = ids$prototype_id,
      scene_index_id = specs[[1L]]$scene_index_id, status = "PASS",
      branch_ids = plan_ids, branch_manifests = vapply(branches, function(x) x[grepl("branch_manifest[.]json$", x)], character(1L)),
      membership_parquets = parquet_paths,
      outputs = lapply(file.path(stage, output_names[-1L]), function(path) list(
        path = file.path(final_dir, basename(path)), size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)
      ))
    )
    write_json_file(manifest, file.path(stage, output_names[[1L]]))
  })
  outputs
}

proc_iowait_ticks <- function() {
  fields <- strsplit(readLines("/proc/stat", n = 1L, warn = FALSE), "[[:space:]]+")[[1L]]
  fields <- fields[nzchar(fields)]
  if (length(fields) < 6L) return(NA_real_)
  as.numeric(fields[[6L]])
}

membership_pilot_task <- function(task) {
  started <- Sys.time()
  io_start <- proc_io_snapshot()
  error <- NULL
  rows <- tryCatch({
    value <- brute_force_membership_for_scene(task$scene, task$spec)
    nrow(value)
  }, error = function(e) {
    error <<- conditionMessage(e)
    NA_integer_
  })
  io_end <- proc_io_snapshot()
  list(
    scene_id = task$scene$scene_id, rows = rows,
    wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
    max_rss_kb = proc_max_rss_kb(),
    read_bytes = io_end$read_bytes - io_start$read_bytes,
    write_bytes = io_end$write_bytes - io_start$write_bytes,
    error = error
  )
}

benchmark_membership_concurrency <- function(plan_specs, concurrency = c(5L, 10L, 20L), repetitions = 5L) {
  specs <- plan_specs
  records <- do.call(rbind, lapply(seq_along(specs), function(i) {
    do.call(rbind, lapply(seq_along(specs[[i]]$scenes), function(j) data.frame(
      spec_index = i, scene_index = j,
      scene_id = specs[[i]]$scenes[[j]]$scene_id,
      estimated_cost = specs[[i]]$scenes[[j]]$estimated_cost,
      stringsAsFactors = FALSE
    )))
  }))
  records <- records[order(records$estimated_cost, records$scene_id, method = "radix"), ]
  positions <- unique(round(c(1, nrow(records) / 2, nrow(records) * .9, nrow(records))))
  representatives <- records[positions, , drop = FALSE]
  base_tasks <- lapply(seq_len(nrow(representatives)), function(i) {
    row <- representatives[i, ]
    list(spec = specs[[row$spec_index]], scene = specs[[row$spec_index]]$scenes[[row$scene_index]])
  })
  tasks <- rep(base_tasks, as.integer(repetitions))
  invisible(lapply(base_tasks, membership_pilot_task))
  results <- lapply(as.integer(concurrency), function(cores) {
    before <- proc_iowait_ticks()
    started <- Sys.time()
    values <- parallel::mclapply(tasks, membership_pilot_task, mc.cores = cores, mc.preschedule = FALSE)
    elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
    after <- proc_iowait_ticks()
    errors <- Filter(Negate(is.null), lapply(values, `[[`, "error"))
    list(
      concurrency = cores, task_count = length(tasks), wall_time_seconds = elapsed,
      max_worker_rss_kb = max(vapply(values, `[[`, numeric(1L), "max_rss_kb"), na.rm = TRUE),
      aggregate_read_bytes = sum(vapply(values, `[[`, numeric(1L), "read_bytes"), na.rm = TRUE),
      aggregate_write_bytes = sum(vapply(values, `[[`, numeric(1L), "write_bytes"), na.rm = TRUE),
      read_throughput_bytes_per_second = sum(vapply(values, `[[`, numeric(1L), "read_bytes"), na.rm = TRUE) / elapsed,
      system_iowait_ticks_delta = after - before,
      error_count = length(errors), errors = errors
    )
  })
  if (any(vapply(results, `[[`, integer(1L), "error_count") > 0L)) stop("Membership concurrency pilot failed", call. = FALSE)
  list(
    benchmark_schema_version = "1.0.0", generated_at = kst_now(),
    workload = list(
      representative_scene_ids = vapply(base_tasks, function(x) x$scene$scene_id, character(1L)),
      representative_estimated_costs = representatives$estimated_cost,
      repetitions = as.integer(repetitions), task_count = length(tasks), worker_threads = 1L
    ),
    results = results
  )
}
