# C01 implements the full-membership planning contract in the reconstruction appendix.
full_membership_plan_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/full_membership_plan.yml",
    "config/full_membership_plan_runtime.yml",
    "config/schemas/full_membership_plan.schema.json",
    "R/research_full_membership_plan.R"
  ))
}

fmp_read_artifact <- function(paths, basename_required) {
  path <- artifact_path(paths, basename_required)
  if (!file.exists(path) || file.info(path)$size <= 0) stop("Invalid C01 parent artifact: ", path, call. = FALSE)
  path
}

fmp_hilbert_index <- function(x, y, bits = 16L) {
  n <- 2^as.integer(bits)
  xmin <- min(x); xmax <- max(x); ymin <- min(y); ymax <- max(y)
  scale_axis <- function(v, lo, hi) {
    if (hi == lo) return(rep.int(0L, length(v)))
    as.integer(floor((v - lo) / (hi - lo) * (n - 1) + 0.5))
  }
  xi <- scale_axis(x, xmin, xmax); yi <- scale_axis(y, ymin, ymax)
  one <- function(xx, yy) {
    d <- 0
    s <- n / 2
    while (s >= 1) {
      rx <- as.integer(bitwAnd(xx, as.integer(s)) > 0L)
      ry <- as.integer(bitwAnd(yy, as.integer(s)) > 0L)
      d <- d + s * s * bitwXor(3L * rx, ry)
      if (ry == 0L) {
        if (rx == 1L) { xx <- as.integer(s - 1 - xx); yy <- as.integer(s - 1 - yy) }
        tmp <- xx; xx <- yy; yy <- tmp
      }
      s <- s / 2
    }
    d
  }
  list(
    index = vapply(seq_along(xi), function(i) one(xi[[i]], yi[[i]]), numeric(1L)),
    bounds = list(xmin = xmin, ymin = ymin, xmax = xmax, ymax = ymax), bits = as.integer(bits)
  )
}

fmp_quantile <- function(x, probability) as.numeric(stats::quantile(x, probability, names = FALSE, type = 7))

fmp_flatten_observation_scenes <- function(plan) {
  rows <- unlist(lapply(plan, `[[`, "scenes"), recursive = FALSE)
  values <- data.table::rbindlist(lapply(rows, function(x) data.table::data.table(
    scene_id = x$scene_id,
    source_vertex_count = as.numeric(x$coordinate_count),
    source_geometry_bytes = as.numeric(x$source_geometry_bytes)
  )))
  if (nrow(values) != 320L || anyDuplicated(values$scene_id)) stop("Prototype geometry evidence is incomplete", call. = FALSE)
  values
}

fmp_prototype_evidence <- function(membership_paths, observation_plan) {
  scene_path <- fmp_read_artifact(membership_paths, "membership_statistics_by_scene.parquet")
  branch_path <- fmp_read_artifact(membership_paths, "branch_index.parquet")
  plan_path <- fmp_read_artifact(membership_paths, "membership_plan.parquet")
  aggregate_path <- fmp_read_artifact(membership_paths, "aggregate_membership_manifest.json")
  qc_path <- fmp_read_artifact(membership_paths, "global_qc.json")
  aggregate <- jsonlite::read_json(aggregate_path, simplifyVector = FALSE)
  qc <- jsonlite::read_json(qc_path, simplifyVector = FALSE)
  if (!identical(aggregate$status, "PASS") || !identical(qc$status, "PASS")) stop("Prototype membership acceptance is not PASS", call. = FALSE)
  long <- data.table::as.data.table(arrow::read_parquet(scene_path))
  counts <- data.table::dcast(long, scene_id + scene_footprint_id + split ~ entity_type,
                              value.var = "membership_count", fill = 0)
  data.table::setnames(counts, c("B", "R", "P"), c("building_count", "road_count", "poi_count"))
  counts <- merge(counts, fmp_flatten_observation_scenes(observation_plan), by = "scene_id", all.x = TRUE)
  if (anyNA(counts)) stop("Prototype cost features are incomplete", call. = FALSE)
  branch <- data.table::as.data.table(arrow::read_parquet(branch_path))
  membership_plan <- data.table::as.data.table(arrow::read_parquet(plan_path))
  map <- data.table::rbindlist(lapply(seq_len(nrow(membership_plan)), function(i) {
    ids <- jsonlite::fromJSON(membership_plan$scene_ids_json[[i]])
    data.table::data.table(branch_id = membership_plan$branch_id[[i]], scene_id = ids)
  }))
  joined <- merge(map, counts, by = "scene_id")
  sums <- joined[, lapply(.SD, sum), by = branch_id,
                 .SDcols = c("building_count", "road_count", "poi_count", "source_vertex_count", "source_geometry_bytes")]
  branch <- merge(branch, sums, by = "branch_id")
  features <- c("building_count", "road_count", "poi_count", "source_vertex_count", "source_geometry_bytes")
  scales <- vapply(features, function(k) stats::median(branch[[k]][branch[[k]] > 0]), numeric(1L))
  raw <- rowSums(sweep(as.matrix(branch[, ..features]), 2L, scales, "/"))
  calibration <- stats::median(branch$wall_time_seconds / raw)
  coefficients <- calibration / scales
  names(coefficients) <- features
  list(
    scenes = counts,
    branch = branch,
    coefficients = coefficients,
    sources = observation_plan[[1L]]$sources,
    artifacts = lapply(c(aggregate_path, qc_path, scene_path, branch_path, plan_path), function(path) list(
      path = normalizePath(path), size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)
    )),
    prototype_ids = list(
      membership_dataset_id = aggregate$membership_dataset_id,
      prototype_id = aggregate$prototype_id
    )
  )
}

fmp_predict <- function(full, prototype, columns, neighbours = 8L) {
  px <- prototype$center_x_5186; py <- prototype$center_y_5186
  result <- matrix(0, nrow(full), length(columns), dimnames = list(NULL, columns))
  for (i in seq_len(nrow(full))) {
    distance2 <- (px - full$center_x_5186[[i]])^2 + (py - full$center_y_5186[[i]])^2
    selected <- order(distance2, prototype$scene_id, method = "radix")[seq_len(min(neighbours, nrow(prototype)))]
    exact <- selected[distance2[selected] == 0]
    if (length(exact)) {
      result[i, ] <- as.numeric(prototype[exact[[1L]], ..columns])
    } else {
      weights <- 1 / distance2[selected]
      result[i, ] <- colSums(as.matrix(prototype[selected, ..columns]) * weights) / sum(weights)
    }
  }
  result
}

fmp_make_bins <- function(scenes, maximum_scenes, caps) {
  metric_names <- names(caps)
  bins <- list(); current <- integer()
  flush <- function() {
    if (length(current)) { bins[[length(bins) + 1L]] <<- current; current <<- integer() }
  }
  oversize <- logical(nrow(scenes))
  for (i in seq_len(nrow(scenes))) {
    row_values <- unlist(scenes[i, ..metric_names], use.names = TRUE)
    is_oversize <- any(row_values > caps)
    oversize[[i]] <- is_oversize
    if (is_oversize) { flush(); bins[[length(bins) + 1L]] <- i; next }
    candidate <- c(current, i)
    totals <- colSums(as.matrix(scenes[candidate, ..metric_names]))
    if (length(candidate) > maximum_scenes || any(totals > caps)) { flush(); current <- i } else current <- candidate
  }
  flush()
  list(bins = bins, oversize = oversize)
}

build_full_membership_plan <- function(spatial_scene_index, prototype_spatial_acceptance,
                                       prototype_model_acceptance, prototype_membership_acceptance,
                                       prototype_observation_plan, full_membership_plan_contract_files) {
  files <- normalizePath(full_membership_plan_contract_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  scientific <- yaml::read_yaml(by_name[["full_membership_plan.yml"]])
  runtime <- yaml::read_yaml(by_name[["full_membership_plan_runtime.yml"]])
  schema <- by_name[["full_membership_plan.schema.json"]]

  index_manifest_path <- fmp_read_artifact(spatial_scene_index, "scene_index_manifest.json")
  index_qc_path <- fmp_read_artifact(spatial_scene_index, "scene_index_qc.json")
  index_path <- fmp_read_artifact(spatial_scene_index, "scene_index.parquet")
  index_manifest <- jsonlite::read_json(index_manifest_path, simplifyVector = FALSE)
  index_qc <- jsonlite::read_json(index_qc_path, simplifyVector = FALSE)
  spatial_path <- fmp_read_artifact(prototype_spatial_acceptance, "prototype_spatial_manifest.json")
  spatial <- jsonlite::read_json(spatial_path, simplifyVector = FALSE)
  i24_path <- fmp_read_artifact(prototype_model_acceptance, "prototype_model_acceptance.json")
  i24 <- jsonlite::read_json(i24_path, simplifyVector = FALSE)
  expected <- scientific$required_parents
  i24_id <- i24$model_acceptance_id
  if (!identical(index_manifest$scene_index_id, expected$spatial_scene_index) ||
      !identical(spatial$spatial_dataset_id, expected$prototype_spatial_acceptance) ||
      !identical(i24_id, expected$prototype_model_acceptance) ||
      !identical(index_qc$status, "PASS") || !identical(spatial$status, "PASS") || !identical(i24$status, "PASS")) {
    stop("C01 parent identity or status mismatch", call. = FALSE)
  }

  evidence <- fmp_prototype_evidence(prototype_membership_acceptance, prototype_observation_plan)
  columns <- c("scene_id", "scene_footprint_id", "split", "center_x_5186", "center_y_5186",
               "xmin_5186", "ymin_5186", "xmax_5186", "ymax_5186")
  full <- data.table::as.data.table(arrow::read_parquet(index_path, col_select = columns))
  if (nrow(full) != 12690L || anyDuplicated(full$scene_id)) stop("Full scene population mismatch", call. = FALSE)
  prototype <- merge(evidence$scenes, full[, .(scene_id, center_x_5186, center_y_5186)], by = "scene_id")
  feature_names <- names(evidence$coefficients)
  predicted <- fmp_predict(full, prototype, feature_names)
  for (name in feature_names) full[, (paste0("estimated_", name)) := pmax(0, predicted[, name])]
  full[, estimated_cost_seconds := rowSums(sweep(predicted, 2L, evidence$coefficients, "*"))]
  hilbert <- fmp_hilbert_index(full$center_x_5186, full$center_y_5186, scientific$ordering$bits)
  full[, hilbert_index := hilbert$index]
  data.table::setorder(full, hilbert_index, scene_id)

  regular <- evidence$branch[scene_count > 1L]
  regular[, estimated_cost_seconds := rowSums(sweep(as.matrix(.SD), 2L, evidence$coefficients, "*")),
          .SDcols = feature_names]
  caps <- c(
    estimated_cost_seconds = max(regular$estimated_cost_seconds),
    estimated_source_vertex_count = max(regular$source_vertex_count),
    estimated_source_geometry_bytes = max(regular$source_geometry_bytes)
  )
  partition <- fmp_make_bins(full, scientific$sharding$initial_maximum_scenes_per_branch, caps)
  spatial_identity <- list(
    scene_index_id = index_manifest$scene_index_id,
    scene_index_sha256 = sha256_file(index_path),
    prototype_spatial_acceptance_id = spatial$spatial_dataset_id,
    prototype_spatial_acceptance_sha256 = sha256_file(spatial_path),
    prototype_membership = evidence$prototype_ids,
    pilot_artifact_sha256 = vapply(evidence$artifacts, `[[`, character(1L), "sha256"),
    contract_hash = sha256_file(by_name[["full_membership_plan.yml"]]),
    schema_hash = sha256_file(schema),
    implementation_hash = sha256_file(by_name[["research_full_membership_plan.R"]]),
    cost_coefficients = as.list(evidence$coefficients),
    hilbert = list(algorithm = scientific$ordering$algorithm, bits = hilbert$bits, bounds = hilbert$bounds)
  )
  dataset_id <- short_hash_id("fmd_", spatial_identity)
  plan_id <- short_hash_id("fmp_", list(spatial_identity = spatial_identity, sharding = scientific$sharding, caps = as.list(caps)))
  root <- file.path(dirname(index_path), "production", dataset_id)
  plan_dir <- file.path(root, "plans", "full_membership", plan_id)

  specs <- lapply(seq_along(partition$bins), function(position) {
    idx <- partition$bins[[position]]; values <- full[idx]
    scientific_branch <- list(plan_id = plan_id, order = position, scene_ids = as.list(values$scene_id),
                              estimates = as.list(colSums(as.matrix(values[, paste0("estimated_", feature_names), with = FALSE]))))
    branch_id <- short_hash_id("fmb_", scientific_branch)
    final <- file.path(root, "membership", dataset_id, "branches", branch_id)
    list(
      schema_version = "1.0.0", stage = "C01", plan_id = plan_id, membership_dataset_id = dataset_id,
      branch_id = branch_id, branch_order = position, ordered_scene_ids = as.list(values$scene_id),
      scene_count = nrow(values), split_counts = as.list(table(factor(values$split, levels = c("training", "validation", "evaluation")))),
      hilbert = list(min = min(values$hilbert_index), max = max(values$hilbert_index), contiguous = TRUE),
      bbox = list(xmin = min(values$xmin_5186), ymin = min(values$ymin_5186), xmax = max(values$xmax_5186), ymax = max(values$ymax_5186), crs = "EPSG:5186"),
      source_references = evidence$sources,
      estimates = list(building_count = sum(values$estimated_building_count), road_count = sum(values$estimated_road_count),
                       poi_count = sum(values$estimated_poi_count), source_geometry_bytes = sum(values$estimated_source_geometry_bytes),
                       source_vertex_count = sum(values$estimated_source_vertex_count), cost_seconds = sum(values$estimated_cost_seconds)),
      oversize_singleton = nrow(values) == 1L && partition$oversize[idx],
      c02_paths = list(staging_directory = paste0(final, ".staging"), final_directory = final),
      execution = list(controller = runtime$c02_recommended_controller, resource_mode = "process_geos_single_native_thread",
                       workers_per_branch = 1L, threads_per_worker = 1L),
      scientific_hash = canonical_sha256(scientific_branch), runtime_hash = sha256_file(by_name[["full_membership_plan_runtime.yml"]])
    )
  })
  all_ids <- unlist(lapply(specs, `[[`, "ordered_scene_ids"), use.names = FALSE)
  split_expected <- c(training = 9690L, validation = 1000L, evaluation = 2000L)
  split_actual <- table(factor(full$split, levels = names(split_expected)))
  cap_fail <- vapply(specs, function(x) x$scene_count > 64L ||
    (!isTRUE(x$oversize_singleton) && (x$estimates$cost_seconds > caps[["estimated_cost_seconds"]] ||
      x$estimates$source_geometry_bytes > caps[["estimated_source_geometry_bytes"]] ||
      x$estimates$source_vertex_count > caps[["estimated_source_vertex_count"]])), logical(1L))
  if (length(all_ids) != nrow(full) || anyDuplicated(all_ids) || !setequal(all_ids, full$scene_id) ||
      !identical(as.integer(split_actual), as.integer(split_expected)) || any(cap_fail)) stop("C01 hard QC failed", call. = FALSE)

  spec_names <- vapply(specs, function(x) paste0("spec-", x$branch_id, ".json"), character(1L))
  output_names <- c(spec_names, "full_membership_cost_model.json", "full_membership_plan_qc.json",
                    "full_membership_plan_manifest.json", "full_membership_plan_summary.md")
  paths <- publish_deterministic_directory(plan_dir, output_names, function(stage) {
    for (i in seq_along(specs)) write_json_file(specs[[i]], file.path(stage, spec_names[[i]]))
    cost_model <- list(algorithm = scientific$cost_model$algorithm, prediction = scientific$cost_model$prediction,
      coefficients_seconds = as.list(evidence$coefficients), prototype_branch_count = nrow(evidence$branch),
      prototype_scene_count = nrow(evidence$scenes), prototype_wall_seconds = list(
        p50 = fmp_quantile(evidence$branch$wall_time_seconds, .5), p95 = fmp_quantile(evidence$branch$wall_time_seconds, .95), max = max(evidence$branch$wall_time_seconds)),
      prototype_rss_bytes = list(p95 = fmp_quantile(evidence$branch$max_rss_kb * 1024, .95), max = max(evidence$branch$max_rss_kb * 1024)),
      caps = as.list(caps), pilot_artifacts = evidence$artifacts)
    write_json_file(cost_model, file.path(stage, "full_membership_cost_model.json"))
    qc <- list(status = "PASS", scene_count = nrow(full), missing_scenes = 0L, duplicate_scenes = 0L,
      split_counts = as.list(split_actual), branch_count = length(specs), oversize_singleton_count = sum(vapply(specs, `[[`, logical(1L), "oversize_singleton")),
      cap_violation_non_singleton = 0L, maximum_scenes = max(vapply(specs, `[[`, integer(1L), "scene_count")),
      full_source_scan_count = 0L, c02_artifact_write_count = 0L)
    write_json_file(qc, file.path(stage, "full_membership_plan_qc.json"))
    outputs <- lapply(spec_names, function(name) list(role = "c02_branch_spec", path = file.path(plan_dir, name),
                                                       size_bytes = unname(file.info(file.path(stage, name))$size), sha256 = sha256_file(file.path(stage, name))))
    manifest <- list(schema_version = "1.0.0", stage = "C01", status = "PASS", plan_id = plan_id,
      membership_dataset_id = dataset_id, scientific_identity = spatial_identity,
      authorization = list(i24_id = i24_id, path = normalizePath(i24_path), size_bytes = unname(file.info(i24_path)$size),
                           sha256 = sha256_file(i24_path), identity_role = "execution_provenance_only", excluded_from_spatial_identity = TRUE),
      population = list(scene_count = nrow(full), split_counts = as.list(split_actual)), cost_model = cost_model,
      sharding = list(branch_count = length(specs), maximum_scenes_per_branch = 64L,
                      oversize_singleton_count = qc$oversize_singleton_count, hilbert_order = scientific$ordering),
      outputs = outputs, qc = qc, execution = list(controller = runtime$controller, orchestration_workers = 1L,
        c02_recommended_parallelism = runtime$c02_selected_max_concurrency, expected_c02_peak_rss_bytes = runtime$c02_selected_max_concurrency * cost_model$prototype_rss_bytes$max,
        io_risk = "concurrent_read_pressure_on_three_shared_geopackage_sources"))
    write_json_file(manifest, file.path(stage, "full_membership_plan_manifest.json"))
    writeLines(c("# C01 Full Membership Plan", "", "Status: PASS", paste0("Plan: `", plan_id, "`"),
      paste0("Scenes: ", nrow(full), "; branches: ", length(specs), "; oversize singletons: ", qc$oversize_singleton_count),
      "", "I24 is an execution authorization gate and is excluded from the spatial identity. C02 was not executed."),
      file.path(stage, "full_membership_plan_summary.md"), useBytes = TRUE)
    validate_json_schema_file(file.path(stage, "full_membership_plan_manifest.json"), schema)
  })
  paths
}
