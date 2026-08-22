# Dissertation methodology: object-modal geometry (Section 2) and spatial
# relation graph tensors. I14 only plans immutable I15 branches; it serializes no tensors.

serialization_plan_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/serialization_plan.yml",
    "config/serialization_plan_runtime.yml",
    "config/schemas/prototype_serialization_plan.schema.json",
    "R/research_serialization_plan.R"
  ))
}

load_serialization_plan_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c("serialization_plan.yml", "serialization_plan_runtime.yml",
                "prototype_serialization_plan.schema.json", "research_serialization_plan.R")
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing serialization-plan contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  scientific <- yaml::read_yaml(by_name[["serialization_plan.yml"]])
  runtime <- yaml::read_yaml(by_name[["serialization_plan_runtime.yml"]])
  validate_serialization_plan_config(scientific, runtime)
  list(
    scientific = scientific, runtime = runtime,
    schema_file = by_name[["prototype_serialization_plan.schema.json"]],
    hashes = list(
      estimator = canonical_sha256(scientific$estimator),
      algorithm = canonical_sha256(scientific$sharding),
      scientific = sha256_file(by_name[["serialization_plan.yml"]]),
      runtime = sha256_file(by_name[["serialization_plan_runtime.yml"]]),
      schema = sha256_file(by_name[["prototype_serialization_plan.schema.json"]]),
      implementation = sha256_file(by_name[["research_serialization_plan.R"]])
    )
  )
}

validate_serialization_plan_config <- function(scientific, runtime) {
  expected <- list(
    version = c(scientific$serialization_plan_contract_version, "1.0.0"),
    policy = c(scientific$estimator$policy, "conservative_uncompressed_tensor_bytes"),
    compression = c(scientific$estimator$compression_assumption, "none"),
    algorithm = c(scientific$sharding$algorithm, "deterministic_decreasing_normalized_cost_bin_packing"),
    split = c(scientific$sharding$split_homogeneous, TRUE),
    atomic = c(scientific$sharding$atomic_scene, TRUE),
    controller = c(runtime$controller, "controller_05"), workers = c(runtime$workers, 1),
    threads = c(runtime$threads_per_worker, 1), gpu = c(runtime$gpu, 0)
  )
  bad <- names(expected)[vapply(expected, function(x) !identical(as.character(x[[1L]]), as.character(x[[2L]])), logical(1L))]
  if (length(bad)) stop("Serialization-plan contract mismatch: ", paste(bad, collapse = ", "), call. = FALSE)
  resources <- c("node_count", "ordered_edge_count", "coordinate_count", "estimated_uncompressed_bytes")
  if (!identical(names(scientific$sharding$cap_rounding), resources) ||
      !identical(names(scientific$sharding$system_feasibility_limits), resources)) {
    stop("Serialization resource contract or order changed", call. = FALSE)
  }
  dtypes <- scientific$estimator$dtypes
  if (any(vapply(dtypes, function(x) is.null(x$bytes) || x$bytes <= 0, logical(1L)))) stop("Invalid serialization dtype size", call. = FALSE)
  invisible(TRUE)
}

serialization_named_paths <- function(paths) {
  setNames(normalizePath(paths, mustWork = TRUE), basename(paths))
}

serialization_sha_record <- function(path) {
  list(path = normalizePath(path, mustWork = TRUE), sha256 = sha256_file(path), size_bytes = as.numeric(file.info(path)$size))
}

serialization_verify_record <- function(record, label = basename(record$path)) {
  if (!file.exists(record$path) || !identical(sha256_file(record$path), record$sha256) ||
      !identical(as.numeric(file.info(record$path)$size), as.numeric(record$size_bytes))) {
    stop("Checksum or size mismatch for ", label, call. = FALSE)
  }
  invisible(TRUE)
}

serialization_i13_context <- function(prototype_spatial_acceptance) {
  paths <- serialization_named_paths(prototype_spatial_acceptance)
  required <- c("prototype_spatial_manifest.json", "prototype_entity_dictionary.parquet",
                "prototype_spatial_qc.json", "prototype_categorical_vocabulary.parquet",
                "prototype_normalization_statistics.parquet", "prototype_missing_mapping.json",
                "prototype_scene_spatial_statistics.parquet", "prototype_categorical_aliases.parquet",
                "prototype_road_topology.parquet")
  missing <- setdiff(required, names(paths))
  if (length(missing)) stop("I13 returned artifact is incomplete: ", paste(missing, collapse = ", "), call. = FALSE)
  manifest <- jsonlite::read_json(paths[["prototype_spatial_manifest.json"]], simplifyVector = FALSE)
  qc <- jsonlite::read_json(paths[["prototype_spatial_qc.json"]], simplifyVector = FALSE)
  if (!identical(manifest$status, "PASS") || !identical(qc$status, "PASS") ||
      !identical(manifest$spatial_dataset_id, "psa_c2155cf081312a31edfdb191")) stop("I13 is not the approved PASS dataset", call. = FALSE)
  recorded <- setNames(manifest$outputs, vapply(manifest$outputs, function(x) basename(x$path), character(1L)))
  for (name in intersect(names(recorded), required)) {
    if (!identical(normalizePath(recorded[[name]]$path, mustWork = TRUE), paths[[name]])) stop("I13 returned path differs from manifest: ", name, call. = FALSE)
    serialization_verify_record(recorded[[name]], paste0("I13 ", name))
  }
  accepted <- setNames(lapply(required[c(1,2,4,5,6,7,8,9)], function(name) serialization_sha_record(paths[[name]])),
                       c("manifest", "dictionary", "vocabulary", "normalization", "missing_mapping", "scene_statistics", "alias", "road_topology"))
  list(paths = paths, manifest = manifest, qc = qc, accepted = accepted)
}

serialization_validate_branch_manifests <- function(dictionary, identity, spatial_root) {
  stage_paths <- list(
    vector = unique(dictionary$vector_artifact_path),
    raster = unique(dictionary$raster_object_context_path),
    relation = unique(dictionary$relation_node_index_path)
  )
  expected_hashes <- list(
    vector = identity$vector_branch_manifest_hashes,
    raster = identity$raster_branch_manifest_hashes,
    relation = identity$relation_branch_manifest_hashes
  )
  records <- list()
  for (stage in names(stage_paths)) {
    manifest_paths <- sort(unique(file.path(dirname(stage_paths[[stage]]), "branch_manifest.json")), method = "radix")
    if (length(manifest_paths) != 15L) stop("I13 does not resolve exactly 15 ", stage, " branch manifests", call. = FALSE)
    stage_records <- lapply(manifest_paths, function(path) {
      branch <- basename(dirname(path))
      expected <- expected_hashes[[stage]][[branch]]
      if (is.null(expected) || !identical(sha256_file(path), expected)) stop("I13 branch manifest checksum mismatch: ", path, call. = FALSE)
      manifest <- jsonlite::read_json(path, simplifyVector = FALSE)
      if (!identical(manifest$status, "PASS")) stop("Non-PASS accepted branch: ", path, call. = FALSE)
      for (output in manifest$outputs) {
        if (identical(output$artifact_type, "zarr_directory")) next
        if (!is.null(output$sha256)) serialization_verify_record(output, paste(stage, branch, basename(output$path)))
      }
      list(branch_id = branch, path = normalizePath(path), sha256 = expected)
    })
    records[[stage]] <- stage_records
  }
  records
}

serialization_geometry_shape <- function(geometry) {
  type <- class(geometry)[[2L]]
  if (identical(type, "POINT")) return(c(coordinate = 1, component = 1, ring = 0, hole = 0))
  if (identical(type, "MULTIPOINT")) return(c(coordinate = nrow(geometry), component = nrow(geometry), ring = 0, hole = 0))
  if (identical(type, "LINESTRING")) return(c(coordinate = nrow(geometry), component = 1, ring = 0, hole = 0))
  if (identical(type, "MULTILINESTRING")) return(c(coordinate = sum(vapply(geometry, nrow, integer(1L))), component = length(geometry), ring = 0, hole = 0))
  if (identical(type, "POLYGON")) return(c(coordinate = sum(vapply(geometry, nrow, integer(1L))), component = 1, ring = length(geometry), hole = max(0, length(geometry) - 1L)))
  if (identical(type, "MULTIPOLYGON")) {
    rings <- lengths(geometry)
    return(c(coordinate = sum(vapply(geometry, function(p) sum(vapply(p, nrow, integer(1L))), integer(1L))),
             component = length(geometry), ring = sum(rings), hole = sum(pmax(0, rings - 1L))))
  }
  stop("Unsupported observed geometry type: ", type, call. = FALSE)
}

serialization_geometry_metrics <- function(paths) {
  paths <- sort(unique(paths), method = "radix")
  tables <- lapply(paths, function(path) {
    value <- sfarrow::st_read_parquet(path, col_select = c(
      "scene_id", "local_entity_id", "entity_type", "observed_coordinate_count",
      "observed_component_count", "observed_hole_count", "observed_geometry"
    ))
    shapes <- t(vapply(sf::st_geometry(value), serialization_geometry_shape, numeric(4L)))
    if (any(shapes[, "coordinate"] != value$observed_coordinate_count) ||
        any(shapes[, "component"] != value$observed_component_count) ||
        any(shapes[, "hole"] != value$observed_hole_count)) stop("Stored geometry counters differ from observed WKB: ", path, call. = FALSE)
    wkb <- sf::st_as_binary(sf::st_geometry(value), EWKB = FALSE)
    data.table::data.table(
      scene_id = value$scene_id, local_entity_id = value$local_entity_id, entity_type = value$entity_type,
      coordinate_count = as.numeric(shapes[, "coordinate"]), component_count = as.numeric(shapes[, "component"]),
      ring_count = as.numeric(shapes[, "ring"]), hole_count = as.numeric(shapes[, "hole"]),
      geometry_wkb_bytes = as.numeric(lengths(wkb))
    )
  })
  value <- data.table::rbindlist(tables)
  if (anyDuplicated(value[, .(scene_id, local_entity_id)])) stop("Duplicate geometry entity key", call. = FALSE)
  value[, lapply(.SD, sum), by = scene_id, .SDcols = c("coordinate_count", "component_count", "ring_count", "hole_count", "geometry_wkb_bytes")]
}

serialization_coalesce_i13_counts <- function(statistics) {
  value <- data.table::as.data.table(statistics)
  for (name in c("node_count", "building_count", "road_count", "poi_count")) {
    joined <- paste0("i.", name)
    if (!joined %in% names(value)) stop("I13 scene statistics lacks authoritative ", joined, call. = FALSE)
    mismatch <- !is.na(value[[name]]) & value[[name]] != value[[joined]]
    if (any(mismatch)) stop("I13 duplicated scene count columns disagree: ", name, call. = FALSE)
    value[, (name) := get(joined)]
  }
  value
}

serialization_raster_contract <- function(estimator) {
  arrays <- estimator$scene_raster
  elements <- sum(vapply(arrays, function(x) as.numeric(x$elements), numeric(1L)))
  bytes <- sum(vapply(arrays, function(x) as.numeric(x$elements) * as.numeric(x$bytes_per_element), numeric(1L)))
  c(elements = elements, bytes = bytes)
}

serialization_estimate_resources <- function(statistics, geometry, estimator, topology = NULL) {
  value <- serialization_coalesce_i13_counts(statistics)
  value <- merge(value, geometry, by = "scene_id", all.x = TRUE, sort = FALSE)
  topology_counts <- if (is.null(topology) || !nrow(topology)) data.table::data.table(scene_id = character(), topology_node_count = integer()) else
    data.table::as.data.table(topology)[, .(topology_node_count = data.table::uniqueN(scene_node_index)), by = scene_id]
  value <- merge(value, topology_counts, by = "scene_id", all.x = TRUE, sort = FALSE)
  value[is.na(topology_node_count), topology_node_count := 0L]
  geometry_columns <- c("coordinate_count", "component_count", "ring_count", "hole_count", "geometry_wkb_bytes")
  value[is.na(coordinate_count), (geometry_columns) := 0]
  value[is.na(object_context_row_count), object_context_row_count := 0]
  slots <- estimator$per_entity_slots
  bytes <- estimator$dtypes
  raster <- serialization_raster_contract(estimator)
  category_slots <- value$building_count * slots$B$category + value$road_count * slots$R$category + value$poi_count * slots$P$category
  numerical_slots <- value$building_count * slots$B$numerical + value$road_count * slots$R$numerical + value$poi_count * slots$P$numerical
  missing_slots <- value$building_count * slots$B$missing_indicator + value$road_count * slots$R$missing_indicator + value$poi_count * slots$P$missing_indicator
  value[, `:=`(
    raster_element_count = raster[["elements"]], raster_expected_bytes = raster[["bytes"]],
    node_type_bytes = node_count * bytes$node_type$bytes,
    category_bytes = category_slots * bytes$category_index$bytes,
    numerical_bytes = numerical_slots * bytes$numerical_value$bytes,
    missing_indicator_bytes = missing_slots * bytes$missing_indicator$bytes,
    object_raster_bytes = object_context_row_count * estimator$object_raster_dimension * bytes$object_raster_value$bytes,
    geometry_offset_bytes = (node_count + 1 + component_count + 1 + ring_count + 1) * bytes$geometry_offset$bytes + node_count * bytes$geometry_type$bytes,
    coordinate_bytes = coordinate_count * (
      bytes$coordinate$bytes * bytes$coordinate$dimensions +
        bytes$scientific_absolute_coordinate$bytes * bytes$scientific_absolute_coordinate$dimensions
    ),
    scientific_center_bytes = node_count *
      bytes$scientific_absolute_center$bytes * bytes$scientific_absolute_center$dimensions,
    building_area_reference_bytes = building_count * bytes$building_observed_area_reference$bytes,
    edge_index_bytes = ordered_pair_count * bytes$edge_index$bytes * bytes$edge_index$dimensions,
    relation_mask_bytes = ordered_pair_count * bytes$relation_mask$bytes,
    topology_bytes = road_count * 2 * (bytes$topology_endpoint_index$bytes + bytes$topology_endpoint_retained$bytes) +
      topology_node_count * (bytes$topology_incident_count$bytes + bytes$topology_node_state$bytes + 2 * bytes$topology_node_xy$bytes),
    metadata_bytes = estimator$fixed_scene_overhead_bytes
  )]
  value[, estimated_uncompressed_bytes := node_type_bytes + category_bytes + numerical_bytes + missing_indicator_bytes +
          object_raster_bytes + geometry_offset_bytes + coordinate_bytes + scientific_center_bytes +
          building_area_reference_bytes +
          edge_index_bytes + relation_mask_bytes + topology_bytes +
          raster_expected_bytes + metadata_bytes]
  data.table::setnames(value, c("ordered_pair_count", "empty_edge"), c("ordered_edge_count", "empty_edge"), skip_absent = TRUE)
  required <- c("building_count", "road_count", "poi_count", "node_count", "ordered_edge_count", "coordinate_count",
                "geometry_wkb_bytes", "raster_element_count", "raster_expected_bytes", "object_context_row_count",
                "estimated_uncompressed_bytes")
  if (anyNA(value[, ..required]) || any(unlist(value[, ..required], use.names = FALSE) < 0)) stop("Negative or null serialization resource count", call. = FALSE)
  value[, empty_edge := ordered_edge_count == 0]
  data.table::setorder(value, scene_id)
  value
}

serialization_distribution <- function(values) {
  probs <- c(min = 0, median = 0.5, p90 = 0.9, p95 = 0.95, p99 = 0.99, max = 1)
  as.list(stats::quantile(values, probs = probs, names = FALSE, type = 7))
}

serialization_derive_caps <- function(resources, sharding) {
  columns <- c("node_count", "ordered_edge_count", "coordinate_count", "estimated_uncompressed_bytes")
  setNames(vapply(columns, function(name) {
    raw <- as.numeric(stats::quantile(resources[[name]], probs = sharding$cap_quantile, names = FALSE, type = 7)) * sharding$cap_multiplier
    round_to <- as.numeric(sharding$cap_rounding[[name]])
    ceiling(raw / round_to) * round_to
  }, numeric(1L)), columns)
}

serialization_pack_split <- function(resources, caps) {
  columns <- names(caps)
  normalized <- sweep(as.matrix(resources[, ..columns]), 2L, caps, "/")
  score <- apply(normalized, 1L, max)
  order_index <- order(-score, resources$scene_id, method = "radix")
  bins <- list()
  for (index in order_index) {
    scene_load <- as.numeric(resources[index, ..columns])
    oversize <- any(scene_load > caps)
    if (oversize) {
      bins[[length(bins) + 1L]] <- index
      next
    }
    eligible <- which(vapply(bins, function(bin) {
      if (length(bin) == 1L && any(as.numeric(resources[bin, ..columns]) > caps)) return(FALSE)
      all(colSums(as.matrix(resources[bin, ..columns])) + scene_load <= caps)
    }, logical(1L)))
    if (!length(eligible)) {
      bins[[length(bins) + 1L]] <- index
    } else {
      load_matrix <- t(vapply(eligible, function(bin_index) colSums(as.matrix(resources[bins[[bin_index]], ..columns])) / caps, numeric(length(columns))))
      max_load <- apply(load_matrix, 1L, max)
      sum_load <- rowSums(load_matrix)
      stable_key <- vapply(eligible, function(bin_index) min(resources$scene_id[bins[[bin_index]]]), character(1L))
      chosen <- eligible[order(max_load, sum_load, stable_key, method = "radix")[[1L]]]
      bins[[chosen]] <- c(bins[[chosen]], index)
    }
  }
  lapply(bins, function(bin) bin[order(resources$scene_id[bin], method = "radix")])
}

serialization_pack_all <- function(resources, caps, limits) {
  columns <- names(caps)
  exceeded <- vapply(columns, function(name) any(resources[[name]] > as.numeric(limits[[name]])), logical(1L))
  if (any(exceeded)) stop("Serialization system feasibility limit exceeded: ", paste(columns[exceeded], collapse = ", "), call. = FALSE)
  splits <- c("training", "validation", "evaluation")
  bins <- unlist(lapply(splits, function(split) {
    index <- which(resources$split == split)
    local <- serialization_pack_split(resources[index], caps)
    lapply(local, function(i) index[i])
  }), recursive = FALSE)
  bins
}

serialization_reconcile_branch_count <- function(resources, bins, caps, expected_count) {
  expected_count <- as.integer(expected_count)
  if (length(bins) > expected_count) {
    stop("Serialization cap packing exceeds the prescribed branch count", call. = FALSE)
  }
  columns <- names(caps)
  while (length(bins) < expected_count) {
    eligible <- which(lengths(bins) > 1L)
    if (!length(eligible)) stop("Cannot reach prescribed serialization branch count", call. = FALSE)
    bin_score <- vapply(eligible, function(index) {
      max(colSums(as.matrix(resources[bins[[index]], ..columns])) / caps)
    }, numeric(1L))
    stable_key <- vapply(eligible, function(index) min(resources$scene_id[bins[[index]]]), character(1L))
    chosen <- eligible[order(-bin_score, stable_key, method = "radix")[[1L]]]
    rows <- bins[[chosen]]
    scene_cost <- apply(sweep(as.matrix(resources[rows, ..columns]), 2L, caps, "/"), 1L, max)
    split_row <- rows[order(-scene_cost, resources$scene_id[rows], method = "radix")[[1L]]]
    bins[[chosen]] <- setdiff(rows, split_row)
    bins[[length(bins) + 1L]] <- split_row
  }
  bins
}

serialization_plan_qc <- function(resources, bins, caps, specs = NULL) {
  cap_names <- names(caps)
  ids <- unlist(lapply(bins, function(bin) resources$scene_id[bin]), use.names = FALSE)
  branch_split <- vapply(bins, function(bin) length(unique(resources$split[bin])), integer(1L))
  violations <- vapply(bins, function(bin) {
    totals <- colSums(as.matrix(resources[bin, ..cap_names]))
    any(totals > caps) && length(bin) != 1L
  }, logical(1L))
  list(
    status = "PASS", scene_count = length(ids), split_counts = as.list(table(factor(resources$split, levels = c("training", "validation", "evaluation")))),
    duplicate_scene_count = sum(duplicated(ids)), missing_scene_count = sum(!resources$scene_id %in% ids),
    cross_split_shard_count = sum(branch_split != 1L), empty_edge_scene_count = sum(resources$empty_edge),
    node_total = sum(resources$node_count), edge_total = sum(resources$ordered_edge_count), unsupported_geometry_count = 0L,
    negative_or_null_resource_count = 0L, non_singleton_cap_violation_count = sum(violations)
  )
}

serialization_output_records <- function(stage, final_dir, names) {
  lapply(names, function(name) list(path = file.path(final_dir, name), size_bytes = as.numeric(file.info(file.path(stage, name))$size), sha256 = sha256_file(file.path(stage, name))))
}

build_prototype_serialization_plan <- function(prototype_spatial_acceptance,
                                               serialization_plan_contract_files,
                                               workers = 1L, threads = 1L,
                                               input_order = NULL) {
  fuse_parallel_spec(workers, threads)
  config <- load_serialization_plan_config(serialization_plan_contract_files)
  context <- serialization_i13_context(prototype_spatial_acceptance)
  dictionary <- data.table::as.data.table(arrow::read_parquet(context$paths[["prototype_entity_dictionary.parquet"]], as_data_frame = TRUE))
  branch_records <- serialization_validate_branch_manifests(dictionary, context$manifest$artifact_identity, dirname(context$paths[["prototype_spatial_manifest.json"]]))
  vector_paths <- unique(dictionary$vector_artifact_path)
  geometry <- serialization_geometry_metrics(vector_paths)
  statistics <- arrow::read_parquet(context$paths[["prototype_scene_spatial_statistics.parquet"]], as_data_frame = TRUE)
  topology <- arrow::read_parquet(context$paths[["prototype_road_topology.parquet"]], as_data_frame = TRUE)
  if (!is.null(input_order)) statistics <- statistics[input_order, , drop = FALSE]
  resources <- serialization_estimate_resources(statistics, geometry, config$scientific$estimator, topology)
  if (nrow(resources) != 320L || anyDuplicated(resources$scene_id)) stop("I14 requires exactly 320 unique scenes", call. = FALSE)
  caps <- serialization_derive_caps(resources, config$scientific$sharding)
  bins <- serialization_pack_all(resources, caps, config$scientific$sharding$system_feasibility_limits)
  bins <- serialization_reconcile_branch_count(
    resources, bins, caps, config$scientific$sharding$expected_branch_count
  )
  diagnostics_identity <- canonical_sha256(resources[, .(scene_id, split, node_count, ordered_edge_count, coordinate_count, estimated_uncompressed_bytes)])
  scientific_identity <- list(
    spatial_dataset_id = context$manifest$spatial_dataset_id,
    i13_manifest_sha256 = sha256_file(context$paths[["prototype_spatial_manifest.json"]]),
    i13_scene_statistics_sha256 = sha256_file(context$paths[["prototype_scene_spatial_statistics.parquet"]]),
    resource_diagnostics_identity = diagnostics_identity,
    estimator_hash = config$hashes$estimator, dtype_assumptions = config$scientific$estimator$dtypes,
    algorithm_hash = config$hashes$algorithm, algorithm = config$scientific$sharding$algorithm,
    caps = as.list(caps), tie_break = config$scientific$sharding$tie_break,
    schema_hash = config$hashes$schema, implementation_hash = config$hashes$implementation
  )
  serialization_dataset_id <- short_hash_id("psd_", scientific_identity)
  plan_id <- short_hash_id("psp_", scientific_identity)
  prototype_root <- dirname(dirname(dirname(context$paths[["prototype_spatial_manifest.json"]])))
  plan_dir <- file.path(prototype_root, "plans", "serialization", plan_id)
  i15_root <- file.path(config$scientific$output$training_root, context$manifest$artifact_identity$prototype_id,
                        config$scientific$output$i15_directory, serialization_dataset_id)
  split_order <- c(training = 1L, validation = 2L, evaluation = 3L)
  specs <- lapply(bins, function(bin) {
    selected <- resources[bin]
    scene_ids <- sort(selected$scene_id, method = "radix")
    selected <- selected[match(scene_ids, scene_id)]
    cap_names <- names(caps)
    totals <- c(scene_count = nrow(selected), colSums(as.matrix(selected[, ..cap_names])))
    oversize <- nrow(selected) == 1L && any(totals[names(caps)] > caps)
    branch_identity <- list(plan_id = plan_id, split = selected$split[[1L]], scene_ids = as.list(scene_ids), scientific_identity = scientific_identity)
    branch_id <- short_hash_id("psb_", branch_identity)
    list(
      spec_schema_version = "1.0.0", plan_id = plan_id, serialization_dataset_id = serialization_dataset_id,
      branch_id = branch_id, split = selected$split[[1L]], scene_ids = as.list(scene_ids), totals = as.list(totals),
      caps = as.list(caps), utilization = as.list(totals[names(caps)] / caps), oversize_singleton = oversize,
      spatial_dataset_id = context$manifest$spatial_dataset_id, accepted_artifacts = context$accepted,
      upstream_datasets = list(
        vector = context$manifest$artifact_identity$vector_observation_dataset_id,
        raster = context$manifest$artifact_identity$raster_observation_dataset_id,
        relation = context$manifest$artifact_identity$relation_dataset_id,
        branch_manifests = branch_records
      ),
      scientific_identity = scientific_identity,
      output = list(root = i15_root, directory = file.path(i15_root, "branches", branch_id)),
      execution = list(controller = config$runtime$controller, workers = config$runtime$workers,
                       threads = config$runtime$threads_per_worker, gpu = config$runtime$gpu)
    )
  })
  specs <- specs[order(vapply(specs, function(x) split_order[[x$split]], integer(1L)),
                       vapply(specs, `[[`, character(1L), "branch_id"), method = "radix")]
  qc <- serialization_plan_qc(resources, bins, caps)
  qc$branch_count <- length(specs)
  qc$oversize_singleton_count <- sum(vapply(specs, `[[`, logical(1L), "oversize_singleton"))
  qc$branch_id_duplicate_count <- sum(duplicated(vapply(specs, `[[`, character(1L), "branch_id")))
  expected <- c(scene_count = 320, duplicate_scene_count = 0, missing_scene_count = 0, cross_split_shard_count = 0,
                empty_edge_scene_count = 59, node_total = 237121, edge_total = 2756444,
                unsupported_geometry_count = 0, negative_or_null_resource_count = 0, non_singleton_cap_violation_count = 0,
                branch_id_duplicate_count = 0, branch_count = config$scientific$sharding$expected_branch_count)
  failed <- names(expected)[vapply(names(expected), function(name) !identical(as.numeric(qc[[name]]), as.numeric(expected[[name]])), logical(1L))]
  if (!identical(as.integer(unlist(qc$split_counts)), c(256L, 32L, 32L))) failed <- c(failed, "split_counts")
  if (length(failed)) stop("Serialization plan QC failed: ", paste(failed, collapse = ", "), call. = FALSE)
  spec_names <- vapply(specs, function(x) paste0("spec-", x$branch_id, ".json"), character(1L))
  fixed_names <- c("serialization_plan_manifest.json", "scene_to_shard_plan.parquet", "planning_qc.json",
                   "resource_diagnostics.parquet", "serialization_plan_log.jsonl")
  output_names <- c(fixed_names, spec_names)
  published <- publish_deterministic_directory(plan_dir, output_names, writer = function(stage) {
    for (i in seq_along(specs)) {
      write_json_file(specs[[i]], file.path(stage, spec_names[[i]]))
      validate_json_schema_file(file.path(stage, spec_names[[i]]), config$schema_file)
    }
    mapping <- data.table::rbindlist(lapply(specs, function(spec) data.table::data.table(
      plan_id = plan_id, serialization_dataset_id = serialization_dataset_id, branch_id = spec$branch_id,
      split = spec$split, scene_order = seq_along(spec$scene_ids), scene_id = unlist(spec$scene_ids),
      oversize_singleton = spec$oversize_singleton
    )))
    mapping[, split_rank := match(split, c("training", "validation", "evaluation"))]
    data.table::setorder(mapping, split_rank, branch_id, scene_order)
    mapping[, split_rank := NULL]
    arrow::write_parquet(mapping, file.path(stage, fixed_names[[2L]]), compression = config$scientific$output$parquet_compression,
                         chunk_size = config$scientific$output$parquet_row_group_size)
    diagnostics <- resources[, .(scene_id, split, building_count, road_count, poi_count, node_count,
      ordered_edge_count, empty_edge, coordinate_count, component_count, ring_count, hole_count,
      geometry_wkb_bytes, raster_element_count, raster_expected_bytes, object_context_row_count,
      node_type_bytes, category_bytes, numerical_bytes, missing_indicator_bytes, object_raster_bytes,
      geometry_offset_bytes, coordinate_bytes, edge_index_bytes, relation_mask_bytes, topology_node_count,
      topology_bytes, metadata_bytes,
      estimated_uncompressed_bytes)]
    data.table::setorder(diagnostics, scene_id)
    arrow::write_parquet(diagnostics, file.path(stage, fixed_names[[4L]]), compression = config$scientific$output$parquet_compression,
                         chunk_size = config$scientific$output$parquet_row_group_size)
    distributions <- setNames(lapply(names(caps), function(name) serialization_distribution(resources[[name]])), names(caps))
    qc$plan_id <- plan_id; qc$serialization_dataset_id <- serialization_dataset_id; qc$caps <- as.list(caps); qc$resource_distributions <- distributions
    qc$load_imbalance <- setNames(lapply(names(caps), function(name) {
      loads <- vapply(specs, function(spec) spec$totals[[name]] / caps[[name]], numeric(1L))
      list(min = min(loads), median = stats::median(loads), max = max(loads), coefficient_of_variation = stats::sd(loads) / mean(loads))
    }), names(caps))
    write_json_file(qc, file.path(stage, fixed_names[[3L]]))
    log <- list(event = "prototype_serialization_plan_complete", status = "PASS", plan_id = plan_id,
                serialization_dataset_id = serialization_dataset_id, controller = config$runtime$controller,
                workers = config$runtime$workers, threads = config$runtime$threads_per_worker, gpu = config$runtime$gpu)
    write_json_file(log, file.path(stage, fixed_names[[5L]]))
    scientific_files <- c(fixed_names[2:5], spec_names)
    manifest <- list(
      manifest_schema_version = "1.0.0", status = "PASS", plan_id = plan_id,
      serialization_dataset_id = serialization_dataset_id, spatial_dataset_id = context$manifest$spatial_dataset_id,
      scientific_identity = scientific_identity, caps = as.list(caps), scene_count = 320L,
      split_counts = qc$split_counts, branch_count = length(specs), i15_output_root = i15_root,
      accepted_artifacts = context$accepted, outputs = serialization_output_records(stage, plan_dir, scientific_files)
    )
    write_json_file(manifest, file.path(stage, fixed_names[[1L]]))
  })
  spec_paths <- published[match(spec_names, basename(published))]
  result <- lapply(spec_paths, function(path) {
    value <- jsonlite::read_json(path, simplifyVector = FALSE)
    value$.path <- path
    value
  })
  mapping <- arrow::read_parquet(published[basename(published) == "scene_to_shard_plan.parquet"], as_data_frame = TRUE)
  list_ids <- unlist(lapply(result, `[[`, "scene_ids"), use.names = FALSE)
  if (!identical(list_ids, mapping$scene_id)) stop("Spec JSON, plan Parquet and R list scene order differ", call. = FALSE)
  result
}
