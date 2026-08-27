p1_scene_index_config_file <- function(root = getwd()) {
  file.path(normalizePath(root, mustWork = TRUE), "config/p1_scene_index.yml")
}

p1_scene_index_contract_paths <- function(root = getwd()) {
  root <- normalizePath(root, mustWork = TRUE)
  config <- yaml::read_yaml(p1_scene_index_config_file(root))
  c(
    config = p1_scene_index_config_file(root),
    vapply(config$schemas, function(path) file.path(root, path), character(1L)),
    implementation_helper = file.path(root, "R/research_scene_index_reduced.R"),
    target_declaration = file.path(root, "targets/research_scene_index.R")
  )
}

load_p1_scene_index_spec <- function(contract_files, root = getwd()) {
  root <- normalizePath(root, mustWork = TRUE)
  files <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  config <- yaml::read_yaml(by_name[["p1_scene_index.yml"]])
  schema_names <- vapply(config$schemas, basename, character(1L))
  missing <- setdiff(schema_names, names(by_name))
  if (length(missing)) stop("P1 schema file is absent: ", paste(missing, collapse = ", "), call. = FALSE)
  implementation_rel <- c(
    "R/research_scene_index_reduced.R", "targets/research_scene_index.R",
    "config/p1_scene_index.yml", unname(unlist(config$schemas, use.names = FALSE))
  )
  implementation_files <- file.path(root, implementation_rel)
  implementation_hash <- p0_scientific_sha256(list(
    version = config$implementation_version,
    files = lapply(seq_along(implementation_rel), function(i) list(
      path = implementation_rel[[i]], sha256 = sha256_file(implementation_files[[i]])
    ))
  ))
  list(
    root = root, config = config, files = files,
    schemas = setNames(by_name[schema_names], names(config$schemas)),
    implementation_hash = implementation_hash
  )
}

p1_artifact_record <- function(path, role = basename(path), include_path = FALSE) {
  value <- list(role = role, basename = basename(path), size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path))
  if (include_path) value$path <- normalizePath(path, mustWork = TRUE)
  value
}

p1_publish_immutable_bundle <- function(final_dir, basenames, writer) {
  dir.create(dirname(final_dir), recursive = TRUE, showWarnings = FALSE)
  stage <- tempfile(paste0(".", basename(final_dir), ".stage-"), tmpdir = dirname(final_dir))
  dir.create(stage)
  on.exit(if (dir.exists(stage)) unlink(stage, recursive = TRUE), add = TRUE)
  writer(stage)
  staged <- file.path(stage, basenames)
  if (!all(file.exists(staged)) || any(file.info(staged)$size <= 0)) stop("Incomplete P1 artifact staging bundle", call. = FALSE)
  final <- file.path(final_dir, basenames)
  if (dir.exists(final_dir)) {
    if (!all(file.exists(final))) stop("Immutable P1 artifact is incomplete: ", final_dir, call. = FALSE)
    same <- vapply(seq_along(final), function(i) identical(sha256_file(final[[i]]), sha256_file(staged[[i]])), logical(1L))
    if (!all(same)) stop("Immutable P1 artifact collision: ", final_dir, call. = FALSE)
    return(normalizePath(final, mustWork = TRUE))
  }
  if (!file.rename(stage, final_dir)) stop("Atomic P1 artifact publication failed: ", final_dir, call. = FALSE)
  normalizePath(final, mustWork = TRUE)
}

p1_read_authority <- function(reduced_methodology_authority, scene_methodology_contract, spec) {
  authority_path <- artifact_path(reduced_methodology_authority, "reduced_methodology_authority.json")
  scene_path <- artifact_path(scene_methodology_contract, "scene_methodology_contract.json")
  authority <- jsonlite::read_json(authority_path, simplifyVector = FALSE)
  scene <- jsonlite::read_json(scene_path, simplifyVector = FALSE)
  expected <- spec$config$authority
  if (!identical(authority$overall_status, "PASS") || !identical(authority$authority_id, expected$expected_id)) {
    stop("P0 authority identity/status mismatch", call. = FALSE)
  }
  if (!identical(sha256_file(authority_path), expected$expected_manifest_sha256)) stop("P0 authority checksum mismatch", call. = FALSE)
  if (!identical(scene$status, "PASS") || !identical(scene$source_set_id, authority$source_set_id)) stop("Scene methodology contract is not accepted", call. = FALSE)
  fixed <- spec$config$scene
  canonical <- scene$canonical_contract
  checks <- c(
    identical(as.integer(canonical$crs_epsg), as.integer(fixed$processing_epsg)),
    identical(as.integer(canonical$scene_width_m), as.integer(fixed$width_m)),
    identical(as.integer(canonical$scene_height_m), as.integer(fixed$height_m)),
    identical(as.integer(canonical$training_scene_count), as.integer(fixed$split_counts$training)),
    identical(as.integer(canonical$validation_scene_count), as.integer(fixed$split_counts$validation)),
    identical(as.integer(canonical$evaluation_scene_count), as.integer(fixed$split_counts$evaluation)),
    identical(as.integer(canonical$off_grid_minimum_distance_m), 50L),
    identical(canonical$intermediate_training_centers, FALSE), is.null(canonical$training_sliding_stride_m)
  )
  if (!all(checks)) stop("P0 scene methodology contract differs from P1", call. = FALSE)
  list(authority = authority, authority_path = authority_path, scene = scene, scene_path = scene_path)
}

build_reduced_study_data_inventory <- function(study_data_inputs, reduced_methodology_authority,
                                               p1_scene_index_contract_files, workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  spec <- load_p1_scene_index_spec(p1_scene_index_contract_files)
  authority_path <- artifact_path(reduced_methodology_authority, "reduced_methodology_authority.json")
  authority <- jsonlite::read_json(authority_path, simplifyVector = FALSE)
  if (!identical(authority$authority_id, spec$config$authority$expected_id) || !identical(authority$overall_status, "PASS")) stop("P0 authority is not accepted", call. = FALSE)
  paths_config <- yaml::read_yaml(file.path(spec$root, "config/research_paths.yml"))
  inputs <- setNames(normalizePath(study_data_inputs, mustWork = TRUE), names(paths_config$inputs))
  source_manifest <- jsonlite::read_json(inputs[["study_manifest"]], simplifyVector = FALSE)
  validate_manifest_paths(source_manifest, inputs)
  layers <- paths_config$layers
  boundary <- sf::st_read(inputs[["boundary"]], layers$boundary, quiet = TRUE)
  buffer <- sf::st_read(inputs[["buffer400"]], layers$buffer400, quiet = TRUE)
  if (sf::st_crs(boundary)$epsg != 5186L || sf::st_crs(buffer)$epsg != 5186L ||
      !all(sf::st_is_valid(boundary)) || !all(sf::st_is_valid(buffer))) stop("Invalid Seoul boundary/buffer", call. = FALSE)
  difference <- as.numeric(sum(sf::st_area(sf::st_sym_difference(sf::st_union(buffer), sf::st_buffer(sf::st_union(boundary), 400)))))
  if (difference > 1e-4) stop("Seoul source buffer is not exactly 400 m", call. = FALSE)
  bbox <- sf::st_bbox(buffer)
  vectors <- list(
    boundary = read_vector_sample(inputs[["boundary"]], layers$boundary, 5186, c("POLYGON", "MULTIPOLYGON")),
    buffer400 = read_vector_sample(inputs[["buffer400"]], layers$buffer400, 5186, c("POLYGON", "MULTIPOLYGON")),
    building = read_vector_sample(inputs[["building"]], layers$building, 5186, c("POLYGON", "MULTIPOLYGON")),
    road_links = read_vector_sample(inputs[["road"]], layers$road_links, 5186, c("LINESTRING", "MULTILINESTRING")),
    road_nodes = read_vector_sample(inputs[["road"]], layers$road_nodes, 5186, "POINT"),
    poi = read_vector_sample(inputs[["poi"]], layers$poi, 5186, "POINT"),
    official_grid = read_vector_sample(inputs[["official_grid_shp"]], layers$official_grid, 5179, c("POLYGON", "MULTIPOLYGON"))
  )
  for (name in names(vectors)) vectors[[name]]$fields <- gpkg_fields(
    if (name == "official_grid") inputs[["official_grid_shp"]] else if (name %in% c("road_links", "road_nodes")) inputs[["road"]] else inputs[[name]],
    layers[[name]]
  )
  rasters <- list(landcover = raster_inventory(inputs[["landcover"]], 5186, bbox), dem = raster_inventory(inputs[["dem"]], 5186, bbox))
  files <- lapply(names(inputs), function(role) p1_artifact_record(inputs[[role]], role))
  scientific <- list(
    authority_id = authority$authority_id,
    accepted_study_manifest_sha256 = sha256_file(inputs[["study_manifest"]]),
    files = files, vectors = vectors, rasters = rasters,
    source_identity = list(official_grid_file_set_sha256 = sha256_file_set(inputs[grep("official_grid", names(inputs))])),
    spatial_checks = list(processing_epsg = 5186L, buffer_distance_m = 400L, buffer_symmetric_difference_m2 = difference, source_coverage = "PASS"),
    implementation_hash = spec$implementation_hash, schema_version = "1.0.0"
  )
  hash <- p0_scientific_sha256(scientific)
  value <- list(
    schema_version = "1.0.0", inventory_id = paste0("rin_", substr(hash, 1L, 24L)), status = "PASS",
    authority_id = authority$authority_id, scientific = scientific, scientific_hash = hash,
    execution = list(input_paths = lapply(names(inputs), function(role) list(role = role, path = inputs[[role]])))
  )
  final_dir <- file.path(spec$config$publication$root, "_inputs", value$inventory_id)
  p1_publish_immutable_bundle(final_dir, "study_data_inventory.json", function(stage) {
    path <- write_json_file(value, file.path(stage, "study_data_inventory.json"))
    validate_json_schema_file(path, spec$schemas[["inventory"]])
  })
}

validate_accepted_off_grid_table <- function(source, boundary, training_xy, minimum_m = 50) {
  required <- c("off_grid_order", "center_id", "split", "split_order", "x", "y", "crs_epsg")
  missing <- setdiff(required, names(source))
  if (length(missing)) stop("Accepted off-grid source fields are missing: ", paste(missing, collapse = ", "), call. = FALSE)
  if (nrow(source) != 2000L || anyDuplicated(source$center_id) || anyDuplicated(source[, c("x", "y")]) ||
      !all(is.finite(source$x)) || !all(is.finite(source$y)) || !all(source$crs_epsg == 5186L)) stop("Accepted off-grid source identity contract failed", call. = FALSE)
  expected_split <- c(rep("validation", 400L), rep("evaluation", 1600L))
  ordered <- source[order(source$off_grid_order, method = "radix"), ]
  if (!identical(as.integer(ordered$off_grid_order), seq_len(2000L)) || !identical(as.character(ordered$split), expected_split)) stop("Accepted off-grid deterministic split contract failed", call. = FALSE)
  points <- sf::st_as_sf(source, coords = c("x", "y"), crs = 5186, remove = FALSE)
  outside <- sum(lengths(sf::st_covered_by(points, sf::st_union(boundary))) == 0L)
  training <- sf::st_as_sf(data.frame(x = training_xy[, 1L], y = training_xy[, 2L]), coords = c("x", "y"), crs = 5186)
  nearest <- sf::st_nearest_feature(points, training)
  distances <- as.numeric(sf::st_distance(points, training[nearest, ], by_element = TRUE))
  violations <- sum(distances < minimum_m)
  if (outside || violations) stop("Accepted off-grid source spatial contract failed", call. = FALSE)
  distance_by_id <- setNames(distances, source$center_id)
  list(ordered = ordered, distances = distance_by_id, outside = outside, violations = violations, minimum = min(distances))
}

verify_accepted_off_grid_source <- function(study_data_inputs, scene_methodology_contract,
                                            p1_scene_index_contract_files, workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  spec <- load_p1_scene_index_spec(p1_scene_index_contract_files)
  cfg <- spec$config$off_grid_source
  named <- c(parquet = cfg$parquet$path, manifest = cfg$manifest$path, qc = cfg$qc$path)
  expected <- list(parquet = cfg$parquet, manifest = cfg$manifest, qc = cfg$qc)
  for (role in names(named)) if (!file.exists(named[[role]]) || file.info(named[[role]])$size != expected[[role]]$size_bytes || !identical(sha256_file(named[[role]]), expected[[role]]$sha256)) stop("Accepted off-grid source mismatch: ", role, call. = FALSE)
  manifest <- jsonlite::read_json(named[["manifest"]], simplifyVector = FALSE)
  qc <- jsonlite::read_json(named[["qc"]], simplifyVector = FALSE)
  if (!identical(manifest$artifact_id, cfg$artifact_id) || !identical(manifest$status, "PASS") || !identical(qc$status, "PASS")) stop("Accepted off-grid manifest/QC is not PASS", call. = FALSE)
  paths <- yaml::read_yaml(file.path(spec$root, "config/research_paths.yml"))
  inputs <- setNames(normalizePath(study_data_inputs, mustWork = TRUE), names(paths$inputs))
  boundary <- sf::st_read(inputs[["boundary"]], paths$layers$boundary, quiet = TRUE)
  contract <- jsonlite::read_json(artifact_path(scene_methodology_contract, "scene_methodology_contract.json"), simplifyVector = FALSE)
  training_contract <- list(crs = list(official_grid_epsg = 5179L, processing_epsg = 5186L), scene = list(official_cell_id_column = "SPO_NO_CD", coordinate_precision_m = 0.001))
  training <- derive_official_training_scenes(boundary, inputs[["official_grid_shp"]], training_contract)$data
  source <- arrow::read_parquet(named[["parquet"]], as_data_frame = TRUE)
  check <- validate_accepted_off_grid_table(source, boundary, as.matrix(training[, c("center_x_5186", "center_y_5186")]), contract$canonical_contract$off_grid_minimum_distance_m)
  files <- lapply(names(named), function(role) p1_artifact_record(named[[role]], role))
  scientific <- list(source_artifact_id = cfg$artifact_id, source_content_checksum = manifest$content_checksum,
                     split_seed = cfg$split_seed, split_algorithm = cfg$split_algorithm, files = files,
                     row_identity_hash = p0_scientific_sha256(as.character(check$ordered$center_id)))
  hash <- p0_scientific_sha256(scientific)
  value <- list(schema_version = "1.0.0", source_acceptance_id = paste0("osa_", substr(hash, 1L, 24L)), status = "PASS",
                source_artifact_id = cfg$artifact_id, row_count = 2000L,
                split_counts = list(training = 0L, validation = 400L, evaluation = 1600L), crs_epsg = 5186L,
                minimum_nearest_training_center_m = check$minimum, files = files, scientific_hash = hash,
                execution = list(source_paths = as.list(named)))
  final_dir <- file.path(spec$config$publication$root, "_sources", value$source_acceptance_id)
  p1_publish_immutable_bundle(final_dir, "accepted_off_grid_source.json", function(stage) {
    path <- write_json_file(value, file.path(stage, "accepted_off_grid_source.json"))
    validate_json_schema_file(path, spec$schemas[["off_grid"]])
  })
}

build_reduced_scene_index_plan <- function(study_data_inventory, accepted_off_grid_source,
                                           scene_methodology_contract, reduced_methodology_authority,
                                           p1_scene_index_contract_files) {
  spec <- load_p1_scene_index_spec(p1_scene_index_contract_files)
  p0 <- p1_read_authority(reduced_methodology_authority, scene_methodology_contract, spec)
  inventory <- jsonlite::read_json(artifact_path(study_data_inventory, "study_data_inventory.json"), simplifyVector = FALSE)
  off <- jsonlite::read_json(artifact_path(accepted_off_grid_source, "accepted_off_grid_source.json"), simplifyVector = FALSE)
  if (!identical(inventory$status, "PASS") || !identical(off$status, "PASS") || !identical(inventory$authority_id, p0$authority$authority_id)) stop("P1 plan input is not accepted", call. = FALSE)
  scientific <- list(
    schema_version = "1.0.0", methodology_authority_id = p0$authority$authority_id,
    scene_contract_id = p0$scene$contract_id, scene_contract_hash = p0$scene$module_content_sha256,
    input_inventory_id = inventory$inventory_id, off_grid_source_id = off$source_acceptance_id,
    official_grid_source_id = inventory$scientific$source_identity$official_grid_file_set_sha256,
    crs_epsg = 5186L, scene_width_m = 500L, scene_height_m = 500L,
    split_counts = list(training = 2421L, validation = 400L, evaluation = 1600L, total = 4421L),
    deterministic_split_seed = spec$config$off_grid_source$split_seed,
    deterministic_ordering_rule = spec$config$off_grid_source$split_algorithm,
    expected_ids = list(
      scene_id_pattern = "^scn_[0-9a-f]{24}$",
      source_identity_counts = list(official_grid = 2421L, accepted_off_grid = 2000L),
      algorithm = "SHA256(authority_id|scene-v1|split|source_kind|source_id)"
    ),
    training_rule = "official_500m_grid_centers_within_Seoul_no_intermediate_centers",
    implementation_hash = spec$implementation_hash
  )
  hash <- p0_scientific_sha256(scientific)
  plan_id <- paste0("rsp_", substr(hash, 1L, 24L))
  value <- list(schema_version = "1.0.0", plan_id = plan_id, status = "PASS",
                methodology_authority_id = p0$authority$authority_id, scene_contract_id = p0$scene$contract_id,
                input_inventory_id = inventory$inventory_id, off_grid_source_id = off$source_acceptance_id,
                scientific = scientific, scientific_fingerprint = hash,
                execution = list(output_path = file.path(spec$config$publication$root, paste0("rsi_<content-addressed>"))))
  final_dir <- file.path(spec$config$publication$root, "_plans", plan_id)
  p1_publish_immutable_bundle(final_dir, "reduced_scene_index_plan.json", function(stage) {
    path <- write_json_file(value, file.path(stage, "reduced_scene_index_plan.json"))
    validate_json_schema_file(path, spec$schemas[["plan"]])
  })
}

p1_scene_identity <- function(authority_id, split, source_kind, source_id) {
  tokens <- paste(authority_id, "scene-v1", split, source_kind, source_id, sep = "|")
  hashes <- vapply(tokens, digest::digest, character(1L), algo = "sha256", serialize = FALSE)
  list(scene_id = paste0("scn_", substr(hashes, 1L, 24L)), hashes = hashes)
}

build_reduced_spatial_scene_index <- function(study_data_inputs, accepted_off_grid_source,
                                              reduced_scene_index_plan, scene_methodology_contract,
                                              reduced_methodology_authority, p1_scene_index_contract_files,
                                              workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  spec <- load_p1_scene_index_spec(p1_scene_index_contract_files)
  p0 <- p1_read_authority(reduced_methodology_authority, scene_methodology_contract, spec)
  plan <- jsonlite::read_json(artifact_path(reduced_scene_index_plan, "reduced_scene_index_plan.json"), simplifyVector = FALSE)
  paths <- yaml::read_yaml(file.path(spec$root, "config/research_paths.yml"))
  inputs <- setNames(normalizePath(study_data_inputs, mustWork = TRUE), names(paths$inputs))
  boundary <- sf::st_read(inputs[["boundary"]], paths$layers$boundary, quiet = TRUE)
  buffer <- sf::st_read(inputs[["buffer400"]], paths$layers$buffer400, quiet = TRUE)
  contract <- list(crs = list(official_grid_epsg = 5179L, processing_epsg = 5186L), scene = list(official_cell_id_column = "SPO_NO_CD", coordinate_precision_m = 0.001))
  result <- derive_official_training_scenes(boundary, inputs[["official_grid_shp"]], contract)
  training <- data.table::as.data.table(result$data)
  training[, `:=`(split = "training", source_kind = "official_500m_grid", source_id = official_grid_id, nearest_training_center_m = 0)]
  off_record <- jsonlite::read_json(artifact_path(accepted_off_grid_source, "accepted_off_grid_source.json"), simplifyVector = FALSE)
  source_path <- off_record$execution$source_paths$parquet
  off <- data.table::as.data.table(arrow::read_parquet(source_path, as_data_frame = TRUE))
  check <- validate_accepted_off_grid_table(off, boundary, as.matrix(training[, .(center_x_5186, center_y_5186)]), 50)
  off <- data.table::as.data.table(check$ordered)
  off[, `:=`(center_x_5186 = x, center_y_5186 = y, source_kind = "accepted_off_grid", source_id = center_id,
             nearest_training_center_m = unname(check$distances[center_id]))]
  base <- data.table::rbindlist(list(
    training[, .(split, center_x = center_x_5186, center_y = center_y_5186, source_kind, source_id, nearest_training_center_m)],
    off[, .(split, center_x = x, center_y = y, source_kind, source_id, nearest_training_center_m)]
  ))
  base[, split_rank := match(split, c("training", "validation", "evaluation"))]
  data.table::setorder(base, split_rank, source_id)
  base[, deterministic_ordinal := seq_len(.N)]
  identity <- p1_scene_identity(p0$authority$authority_id, base$split, base$source_kind, base$source_id)
  base[, `:=`(scene_id = identity$scene_id, scene_identity_hash = identity$hashes, epsg = 5186L,
              width_m = 500, height_m = 500, xmin = center_x - 250, ymin = center_y - 250,
              xmax = center_x + 250, ymax = center_y + 250, methodology_authority_id = p0$authority$authority_id,
              scene_plan_id = plan$plan_id)]
  points <- sf::st_as_sf(base, coords = c("center_x", "center_y"), crs = 5186, remove = FALSE)
  footprints <- sf::st_sf(geometry = square_footprints(base$center_x, base$center_y, 500), crs = 5186)
  base[, `:=`(seoul_center_flag = lengths(sf::st_covered_by(points, sf::st_union(boundary))) > 0L,
              source_buffer_coverage_flag = lengths(sf::st_covered_by(footprints, sf::st_union(buffer))) > 0L,
              center_wkt = sf::st_as_text(sf::st_geometry(points)))]
  index <- sf::st_sf(as.data.frame(base[, setdiff(names(base), "split_rank"), with = FALSE]), geometry = sf::st_geometry(footprints), crs = 5186)
  scientific_identity <- list(authority_id = p0$authority$authority_id, plan_id = plan$plan_id,
                              ordered_scene_identity_hashes = index$scene_identity_hash,
                              implementation_hash = spec$implementation_hash, schema_version = "1.0.0")
  scientific_hash <- p0_scientific_sha256(scientific_identity)
  scene_index_id <- paste0("rsi_", substr(scientific_hash, 1L, 24L))
  index$scene_index_id <- scene_index_id
  final_dir <- file.path(spec$config$publication$root, scene_index_id)
  p1_publish_immutable_bundle(final_dir, c("spatial_scene_index.parquet", "spatial_scene_index_manifest.json"), function(stage) {
    parquet <- file.path(stage, "spatial_scene_index.parquet")
    write_geo_parquet(index, parquet)
    roundtrip <- suppressWarnings(sfarrow::st_read_parquet(parquet))
    if (nrow(roundtrip) != 4421L || sf::st_crs(roundtrip)$epsg != 5186L) stop("Reduced scene index roundtrip failed", call. = FALSE)
    manifest <- list(schema_version = "1.0.0", scene_index_id = scene_index_id, status = "PASS",
                     authority_id = p0$authority$authority_id, plan_id = plan$plan_id, row_count = nrow(index),
                     split_counts = as.list(table(index$split)), scientific_identity = scientific_identity,
                     scientific_hash = scientific_hash, files = list(p1_artifact_record(parquet, "spatial_scene_index")))
    path <- write_json_file(manifest, file.path(stage, "spatial_scene_index_manifest.json"))
    validate_json_schema_file(path, spec$schemas[["index"]])
  })
}

p1_offgrid_distance_violations <- function(distance_m, minimum_m = 50) sum(!is.finite(distance_m) | distance_m < minimum_m)

p1_split_count_violations <- function(split, expected = c(training = 2421L, validation = 400L, evaluation = 1600L)) {
  actual <- table(factor(split, levels = names(expected)))
  as.integer(length(split) != sum(expected) || any(as.integer(actual) != as.integer(expected)))
}

p1_bounds_violations <- function(data, width_m = 500, height_m = 500, tolerance_m = 1e-6) {
  sum(abs(data$xmax - data$xmin - width_m) > tolerance_m |
        abs(data$ymax - data$ymin - height_m) > tolerance_m)
}

p1_epsg_violations <- function(epsg, expected = 5186L) sum(is.na(epsg) | epsg != expected)

p1_duplicate_identity_violations <- function(split, source_id) sum(duplicated(paste(split, source_id, sep = "|")))

p1_training_source_violations <- function(split, source_kind) {
  sum(split == "training" & source_kind != "official_500m_grid")
}

p1_coverage_violations <- function(geometry, coverage) {
  sum(lengths(sf::st_covered_by(geometry, sf::st_union(coverage))) == 0L)
}

p1_plan_link_violations <- function(data, plan) {
  list(
    plan_fingerprint = as.integer(!all(data$scene_plan_id == plan$plan_id)),
    authority_id = as.integer(!all(data$methodology_authority_id == plan$methodology_authority_id))
  )
}

p1_training_overlap_count <- function(footprints, tolerance_m2 = 1e-8) {
  adjacency <- sf::st_intersects(footprints)
  count <- 0L
  for (i in seq_along(adjacency)) {
    peers <- adjacency[[i]][adjacency[[i]] > i]
    if (!length(peers)) next
    count <- count + sum(vapply(peers, function(j) {
      intersection <- suppressWarnings(sf::st_intersection(sf::st_geometry(footprints)[i], sf::st_geometry(footprints)[j]))
      length(intersection) && as.numeric(sf::st_area(intersection)) > tolerance_m2
    }, logical(1L)))
  }
  as.integer(count)
}

validate_reduced_scene_index_table <- function(index, plan, boundary, buffer, tolerance_m = 1e-6) {
  required <- c("scene_id", "split", "center_x", "center_y", "epsg", "xmin", "ymin", "xmax", "ymax",
                "width_m", "height_m", "source_kind", "source_id", "nearest_training_center_m", "seoul_center_flag",
                "source_buffer_coverage_flag", "deterministic_ordinal", "scene_identity_hash", "methodology_authority_id",
                "scene_plan_id", "scene_index_id")
  data <- sf::st_drop_geometry(index)
  missing <- setdiff(required, names(data))
  split_counts <- table(data$split)
  expected <- c(training = 2421L, validation = 400L, evaluation = 1600L)
  points <- sf::st_as_sf(data, coords = c("center_x", "center_y"), crs = 5186, remove = FALSE)
  training <- data$split == "training"; off <- !training
  overlap <- p1_training_overlap_count(index[training, ], tolerance_m^2)
  violations <- list(
    split_count = p1_split_count_violations(data$split, expected),
    duplicate_scene_id = anyDuplicated(data$scene_id), duplicate_source_identity = p1_duplicate_identity_violations(data$split, data$source_id),
    split_overlap = sum(duplicated(data$scene_identity_hash)), non_finite_center = sum(!is.finite(data$center_x) | !is.finite(data$center_y)),
    seoul_center = p1_coverage_violations(points, boundary), epsg = p1_epsg_violations(data$epsg),
    bounds = p1_bounds_violations(data, tolerance_m = tolerance_m),
    non_official_training = p1_training_source_violations(data$split, data$source_kind),
    intermediate_training_center = p1_training_source_violations(data$split, data$source_kind),
    derived_250m_training_center = p1_training_source_violations(data$split, data$source_kind),
    training_interior_overlap_pair = overlap,
    validation_evaluation_source_overlap = length(intersect(data$source_id[data$split == "validation"], data$source_id[data$split == "evaluation"])),
    off_grid_distance = p1_offgrid_distance_violations(data$nearest_training_center_m[off], 50),
    source_coverage = p1_coverage_violations(index, buffer),
    missing_required_field = length(missing), duplicate_geometry_identity = sum(duplicated(paste(format(data$center_x, digits = 17), format(data$center_y, digits = 17)))),
    plan_fingerprint = p1_plan_link_violations(data, plan)$plan_fingerprint,
    authority_id = p1_plan_link_violations(data, plan)$authority_id
  )
  status <- if (all(unlist(violations) == 0L)) "PASS" else "FAIL"
  list(status = status, split_counts = as.list(split_counts), violation_counts = violations,
       invariants = list(scene_id_unique = violations$duplicate_scene_id == 0L, source_identity_unique = violations$duplicate_source_identity == 0L,
                         splits_disjoint = violations$split_overlap == 0L, centers_finite = violations$non_finite_center == 0L,
                         all_centers_in_Seoul = violations$seoul_center == 0L, epsg_5186 = violations$epsg == 0L,
                         bounds_500m = violations$bounds == 0L, official_grid_only_training = violations$non_official_training == 0L,
                         no_intermediate_or_250m_centers = violations$intermediate_training_center == 0L,
                         no_training_interior_overlap = overlap == 0L, off_grid_distance_at_least_50m = violations$off_grid_distance == 0L,
                         source_buffer_coverage = violations$source_coverage == 0L),
       minimum_off_grid_distance_m = min(data$nearest_training_center_m[off]))
}

accept_reduced_scene_index <- function(spatial_scene_index, reduced_scene_index_plan, study_data_inventory,
                                       reduced_methodology_authority, p1_scene_index_contract_files) {
  spec <- load_p1_scene_index_spec(p1_scene_index_contract_files)
  authority <- jsonlite::read_json(artifact_path(reduced_methodology_authority, "reduced_methodology_authority.json"), simplifyVector = FALSE)
  plan <- jsonlite::read_json(artifact_path(reduced_scene_index_plan, "reduced_scene_index_plan.json"), simplifyVector = FALSE)
  inventory <- jsonlite::read_json(artifact_path(study_data_inventory, "study_data_inventory.json"), simplifyVector = FALSE)
  index_path <- artifact_path(spatial_scene_index, "spatial_scene_index.parquet")
  manifest_path <- artifact_path(spatial_scene_index, "spatial_scene_index_manifest.json")
  manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  index <- suppressWarnings(sfarrow::st_read_parquet(index_path))
  paths <- yaml::read_yaml(file.path(spec$root, "config/research_paths.yml"))
  boundary <- sf::st_read(paths$inputs$boundary, paths$layers$boundary, quiet = TRUE)
  buffer <- sf::st_read(paths$inputs$buffer400, paths$layers$buffer400, quiet = TRUE)
  qc <- validate_reduced_scene_index_table(index, plan, boundary, buffer, spec$config$scene$geometry_tolerance_m)
  if (!identical(manifest$status, "PASS") || !identical(authority$authority_id, plan$methodology_authority_id) ||
      !identical(inventory$inventory_id, plan$input_inventory_id) || !identical(manifest$plan_id, plan$plan_id)) qc$status <- "FAIL"
  checksums <- list(p1_artifact_record(index_path, "spatial_scene_index"), p1_artifact_record(manifest_path, "spatial_scene_index_manifest"))
  scientific <- list(authority_id = authority$authority_id, plan_id = plan$plan_id, scene_index_id = manifest$scene_index_id,
                     scene_index_scientific_hash = manifest$scientific_hash, checksums = checksums,
                     invariants = qc$invariants, violation_counts = qc$violation_counts, implementation_hash = spec$implementation_hash)
  hash <- p0_scientific_sha256(scientific)
  value <- list(schema_version = "1.0.0", acceptance_id = paste0("sia_", substr(hash, 1L, 24L)), status = qc$status,
                authority_id = authority$authority_id, plan_id = plan$plan_id, scene_index_id = manifest$scene_index_id,
                split_counts = qc$split_counts, invariants = qc$invariants, violation_counts = qc$violation_counts,
                source_input_ids = list(inventory_id = inventory$inventory_id, off_grid_source_id = plan$off_grid_source_id),
                implementation_hash = spec$implementation_hash, content_hash = hash, artifact_checksums = checksums)
  if (!identical(value$status, "PASS")) stop("Reduced scene index acceptance failed: ", paste(names(qc$violation_counts)[unlist(qc$violation_counts) != 0], collapse = ", "), call. = FALSE)
  final_dir <- file.path(spec$config$publication$root, manifest$scene_index_id, "acceptance", value$acceptance_id)
  p1_publish_immutable_bundle(final_dir, "scene_index_acceptance.json", function(stage) {
    path <- write_json_file(value, file.path(stage, "scene_index_acceptance.json"))
    validate_json_schema_file(path, spec$schemas[["acceptance"]])
  })
}

p1_index_strata <- function(index, boundary, config) {
  data <- data.table::as.data.table(sf::st_drop_geometry(index))
  points <- sf::st_as_sf(data, coords = c("center_x", "center_y"), crs = 5186, remove = FALSE)
  data[, boundary_distance_m := as.numeric(sf::st_distance(points, sf::st_boundary(sf::st_union(boundary)), by_element = FALSE)[, 1L])]
  data[, boundary_class := ifelse(boundary_distance_m <= config$boundary_proximity_m, "boundary_near", "interior")]
  data[, coordinate_quadrant := paste(ifelse(center_x <= stats::median(center_x), "west", "east"), ifelse(center_y <= stats::median(center_y), "south", "north"), sep = "_") , by = split]
  data[, distance_class := ifelse(split == "training", "grid", ifelse(nearest_training_center_m < 100, "near_grid", "far_grid"))]
  data[, selection_strata := paste(boundary_class, coordinate_quadrant, distance_class, source_kind, sep = "|")]
  data
}

build_reduced_prototype_scene_selection <- function(scene_index_acceptance, spatial_scene_index,
                                                     p1_scene_index_contract_files,
                                                     workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  spec <- load_p1_scene_index_spec(p1_scene_index_contract_files)
  acceptance <- jsonlite::read_json(artifact_path(scene_index_acceptance, "scene_index_acceptance.json"), simplifyVector = FALSE)
  if (!identical(acceptance$status, "PASS")) stop("Prototype selection requires accepted full scene index", call. = FALSE)
  index_path <- artifact_path(spatial_scene_index, "spatial_scene_index.parquet")
  index <- suppressWarnings(sfarrow::st_read_parquet(index_path))
  paths <- yaml::read_yaml(file.path(spec$root, "config/research_paths.yml"))
  boundary <- sf::st_read(paths$inputs$boundary, paths$layers$boundary, quiet = TRUE)
  strata <- p1_index_strata(index, boundary, spec$config$prototype)
  counts <- unlist(spec$config$prototype$counts)
  selected_rows <- unlist(lapply(names(counts), function(split_name) {
    rows <- which(strata$split == split_name)
    local <- balanced_stratified_indices(strata[rows], as.integer(counts[[split_name]]), as.integer(spec$config$prototype$seed) + match(split_name, names(counts)) - 1L)
    rows[local]
  }), use.names = FALSE)
  selected_data <- strata[selected_rows]
  selected_data[, `:=`(prototype_scope = "prototype", selection_seed = as.integer(spec$config$prototype$seed),
                       selection_algorithm = "balanced_scene_index_only_strata_v1",
                       p2_dependent_features_used = FALSE)]
  selected_data[, split_rank__ := match(split, c("training", "validation", "evaluation"))]
  data.table::setorder(selected_data, split_rank__, selection_strata, scene_id)
  selected_data[, split_rank__ := NULL]
  selected <- sf::st_sf(as.data.frame(selected_data), geometry = sf::st_geometry(index)[match(selected_data$scene_id, index$scene_id)], crs = 5186)
  actual <- table(selected$split)
  if (nrow(selected) != 320L || anyDuplicated(selected$scene_id) || !all(as.integer(actual[names(counts)]) == as.integer(counts))) stop("Prototype selection acceptance failed", call. = FALSE)
  scientific <- list(authority_id = acceptance$authority_id, scene_index_id = acceptance$scene_index_id,
                     scene_index_sha256 = sha256_file(index_path), counts = as.list(counts), seed = spec$config$prototype$seed,
                     algorithm = "balanced_scene_index_only_strata_v1", ordered_scene_ids = selected$scene_id,
                     implementation_hash = spec$implementation_hash, schema_version = "1.0.0")
  hash <- p0_scientific_sha256(scientific); id <- paste0("rps_", substr(hash, 1L, 24L))
  final_dir <- file.path(spec$config$publication$root, acceptance$scene_index_id, "prototype", id)
  p1_publish_immutable_bundle(final_dir, c("prototype_scene_selection.parquet", "prototype_scene_selection_manifest.json"), function(stage) {
    parquet <- file.path(stage, "prototype_scene_selection.parquet")
    write_geo_parquet(selected, parquet)
    manifest <- list(schema_version = "1.0.0", prototype_id = id, status = "PASS", scope = "prototype",
                     authority_id = acceptance$authority_id, scene_index_id = acceptance$scene_index_id,
                     row_count = nrow(selected), split_counts = as.list(actual),
                     selection = list(seed = spec$config$prototype$seed, algorithm = "balanced_scene_index_only_strata_v1",
                                      fields = c("boundary_class", "coordinate_quadrant", "distance_class", "source_kind"),
                                      p2_dependent_features_used = FALSE,
                                      unavailable_until_p2 = c("sparse", "dense", "road_free", "empty_relation")),
                     scientific_hash = hash, files = list(p1_artifact_record(parquet, "prototype_scene_selection")))
    path <- write_json_file(manifest, file.path(stage, "prototype_scene_selection_manifest.json"))
    validate_json_schema_file(path, spec$schemas[["prototype"]])
  })
}
