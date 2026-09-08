# Dissertation Section 3.1: deterministic current-lineage off-grid centers.

off_grid_coordinate_token <- function(value) sprintf("%.17g", as.numeric(value))

off_grid_content_checksum <- function(value) {
  required <- c("off_grid_order", "center_id", "split", "split_order", "x", "y")
  if (!all(required %in% names(value))) stop("Off-grid checksum columns are incomplete", call. = FALSE)
  p0_scientific_sha256(lapply(seq_len(nrow(value)), function(i) list(
    off_grid_order = as.integer(value$off_grid_order[[i]]), center_id = value$center_id[[i]],
    split = value$split[[i]], split_order = as.integer(value$split_order[[i]]),
    x = off_grid_coordinate_token(value$x[[i]]), y = off_grid_coordinate_token(value$y[[i]])
  )))
}

with_off_grid_rng <- function(settings, code) {
  old_kind <- RNGkind()
  had_seed <- exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  if (had_seed) old_seed <- get(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  on.exit({
    do.call(RNGkind, as.list(old_kind))
    if (had_seed) assign(".Random.seed", old_seed, envir = .GlobalEnv)
    else if (exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)) rm(".Random.seed", envir = .GlobalEnv)
  }, add = TRUE)
  suppressWarnings(RNGversion(as.character(settings$rng_version)))
  RNGkind(settings$rng_kind, settings$normal_kind, settings$sample_kind)
  set.seed(as.integer(settings$split_seed))
  force(code)
}

sample_current_off_grid_centers <- function(boundary, training, settings) {
  total <- as.integer(settings$total_count)
  batch_size <- as.integer(settings$candidate_batch_size)
  minimum <- as.numeric(settings$minimum_training_center_distance_m)
  boundary_union <- sf::st_union(sf::st_geometry(boundary))
  bbox <- sf::st_bbox(boundary_union)
  training_points <- sf::st_as_sf(training, coords = c("center_x_5186", "center_y_5186"), crs = 5186)
  accepted <- list(); accepted_count <- 0L; batches <- 0L; generated <- 0L
  with_off_grid_rng(settings, {
    while (accepted_count < total) {
      batches <- batches + 1L
      draws <- matrix(stats::runif(2L * batch_size), ncol = 2L, byrow = TRUE)
      xy <- cbind(
        x = bbox[["xmin"]] + draws[, 1L] * (bbox[["xmax"]] - bbox[["xmin"]]),
        y = bbox[["ymin"]] + draws[, 2L] * (bbox[["ymax"]] - bbox[["ymin"]])
      )
      generated <- generated + batch_size
      points <- sf::st_as_sf(data.frame(x = xy[, 1L], y = xy[, 2L]), coords = c("x", "y"), crs = 5186)
      eligible <- which(lengths(sf::st_covered_by(points, boundary_union)) > 0L)
      if (length(eligible)) {
        nearest <- sf::st_nearest_feature(points[eligible, ], training_points)
        distance <- as.numeric(sf::st_distance(points[eligible, ], training_points[nearest, ], by_element = TRUE))
        eligible <- eligible[distance >= minimum]
      }
      if (length(eligible)) {
        take <- eligible[seq_len(min(length(eligible), total - accepted_count))]
        accepted[[length(accepted) + 1L]] <- xy[take, , drop = FALSE]
        accepted_count <- accepted_count + length(take)
      }
    }
  })
  list(xy = do.call(rbind, accepted), batches = batches, candidates_generated = generated)
}

build_current_off_grid_table <- function(boundary, training, settings) {
  sampled <- sample_current_off_grid_centers(boundary, training, settings)
  total <- as.integer(settings$total_count); validation <- as.integer(settings$validation_count)
  value <- data.frame(
    off_grid_order = seq_len(total),
    split = c(rep("validation", validation), rep("evaluation", total - validation)),
    split_order = c(seq_len(validation), seq_len(total - validation)),
    x = as.double(sampled$xy[, "x"]), y = as.double(sampled$xy[, "y"]), stringsAsFactors = FALSE
  )
  value$center_id <- vapply(seq_len(total), function(i) paste0("ogc_", substr(p0_scientific_sha256(list(
    version = settings$sampling_algorithm_version, order = i,
    x = off_grid_coordinate_token(value$x[[i]]), y = off_grid_coordinate_token(value$y[[i]])
  )), 1L, 24L)), character(1L))
  value$crs_epsg <- 5186L
  value <- value[, c("off_grid_order", "center_id", "split", "split_order", "x", "y", "crs_epsg")]
  check <- validate_current_off_grid_table(value, boundary, training, settings)
  list(data = value, check = check, batches = sampled$batches, candidates_generated = sampled$candidates_generated)
}

validate_current_off_grid_table <- function(value, boundary, training, settings) {
  total <- as.integer(settings$total_count); validation <- as.integer(settings$validation_count)
  evaluation <- as.integer(settings$evaluation_count); minimum <- as.numeric(settings$minimum_training_center_distance_m)
  expected_split <- c(rep("validation", validation), rep("evaluation", evaluation))
  points <- sf::st_as_sf(value, coords = c("x", "y"), crs = 5186, remove = FALSE)
  training_points <- sf::st_as_sf(training, coords = c("center_x_5186", "center_y_5186"), crs = 5186)
  nearest <- sf::st_nearest_feature(points, training_points)
  distance <- as.numeric(sf::st_distance(points, training_points[nearest, ], by_element = TRUE))
  failures <- c(
    if (total != validation + evaluation || nrow(value) != total) "row_count",
    if (!identical(as.integer(value$off_grid_order), seq_len(total))) "ordering",
    if (!identical(as.character(value$split), expected_split)) "split",
    if (anyDuplicated(value$center_id)) "duplicate_id",
    if (anyDuplicated(value[, c("x", "y")])) "duplicate_coordinate",
    if (any(!is.finite(value$x) | !is.finite(value$y))) "coordinate",
    if (any(value$crs_epsg != 5186L)) "crs",
    if (any(lengths(sf::st_covered_by(points, sf::st_union(boundary))) == 0L)) "boundary",
    if (any(distance < minimum)) "training_distance"
  )
  if (length(failures)) stop("Current off-grid QC failed: ", paste(failures, collapse = ", "), call. = FALSE)
  list(status = "PASS", row_count = total, split_counts = list(validation = validation, evaluation = evaluation),
       duplicate_scene_ids = 0L, duplicate_coordinates = 0L, outside_boundary = 0L,
       minimum_nearest_training_center_m = min(distance), crs_epsg = 5186L)
}

publish_current_off_grid_source <- function(study_data_inputs, scene_methodology_contract,
                                            reduced_methodology_authority,
                                            p1_scene_index_contract_files, workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  spec <- load_p1_scene_index_spec(p1_scene_index_contract_files)
  p0 <- p1_read_authority(reduced_methodology_authority, scene_methodology_contract, spec)
  settings <- spec$config$off_grid_source
  if (!identical(as.integer(c(settings$total_count, settings$validation_count, settings$evaluation_count)), c(10000L, 1000L, 9000L)) ||
      !identical(as.integer(settings$minimum_training_center_distance_m), 50L)) {
    stop("Current off-grid configuration differs from P0 scene authority", call. = FALSE)
  }
  paths <- yaml::read_yaml(file.path(spec$root, "config/research_paths.yml"))
  inputs <- setNames(normalizePath(study_data_inputs, mustWork = TRUE), names(paths$inputs))
  boundary <- sf::st_read(inputs[["boundary"]], paths$layers$boundary, quiet = TRUE)
  training_contract <- list(crs = list(official_grid_epsg = 5179L, processing_epsg = 5186L),
                            scene = list(official_cell_id_column = "SPO_NO_CD", coordinate_precision_m = 0.001))
  training <- derive_official_training_scenes(boundary, inputs[["official_grid_shp"]], training_contract)$data
  if (nrow(training) != 2421L) stop("Official training-center count is not 2,421", call. = FALSE)
  generated <- build_current_off_grid_table(boundary, training, settings)
  official_roles <- c("official_grid_shp", "official_grid_shx", "official_grid_dbf", "official_grid_prj")
  source_identity <- list(
    methodology_authority_id = p0$authority$authority_id,
    scene_contract_id = p0$scene$contract_id,
    scene_contract_hash = p0$scene$module_content_sha256,
    boundary_sha256 = sha256_file(inputs[["boundary"]]),
    official_grid_sha256 = sha256_file_set(inputs[official_roles]),
    official_training_center_hash = p0_scientific_sha256(training[, c("official_grid_id", "center_x_5186", "center_y_5186")]),
    content_checksum = off_grid_content_checksum(generated$data),
    contract = settings, implementation_hash = spec$implementation_hash
  )
  artifact_id <- paste0("ogs_", substr(p0_scientific_sha256(source_identity), 1L, 24L))
  final_dir <- file.path(spec$config$publication$root, "_off_grid", artifact_id)
  basenames <- c("approved_off_grid_scene_centers.parquet", "approved_off_grid_scene_source_manifest.json",
                 "approved_off_grid_scene_source_qc.json", "accepted_off_grid_source.json")
  p1_publish_immutable_bundle(final_dir, basenames, function(stage) {
    parquet <- file.path(stage, basenames[[1L]])
    arrow::write_parquet(generated$data, parquet, compression = "zstd")
    files <- list(parquet = p1_artifact_record(parquet, "parquet"))
    manifest <- list(schema_version = "1.0.0", artifact_id = artifact_id, status = "PASS",
                     methodology_authority_id = p0$authority$authority_id,
                     content_checksum = source_identity$content_checksum, row_count = 10000L,
                     split_counts = list(validation = 1000L, evaluation = 9000L), crs_epsg = 5186L,
                     minimum_training_center_distance_m = 50L, scientific_identity = source_identity, files = files)
    manifest_path <- write_json_file(manifest, file.path(stage, basenames[[2L]]))
    validate_json_schema_file(manifest_path, spec$schemas[["off_grid_manifest"]])
    qc_path <- write_json_file(c(list(artifact_id = artifact_id), generated$check,
                               list(candidate_batches = generated$batches, candidates_generated = generated$candidates_generated)),
                               file.path(stage, basenames[[3L]]))
    source_files <- c(parquet = parquet, manifest = manifest_path, qc = qc_path)
    records <- lapply(names(source_files), function(role) p1_artifact_record(source_files[[role]], role))
    scientific <- list(source_artifact_id = artifact_id, source_content_checksum = source_identity$content_checksum,
                       methodology_authority_id = p0$authority$authority_id, files = records,
                       row_identity_hash = p0_scientific_sha256(as.character(generated$data$center_id)))
    hash <- p0_scientific_sha256(scientific)
    acceptance <- list(schema_version = "1.0.0", source_acceptance_id = paste0("osa_", substr(hash, 1L, 24L)),
                       status = "PASS", source_artifact_id = artifact_id, row_count = 10000L,
                       split_counts = list(training = 0L, validation = 1000L, evaluation = 9000L), crs_epsg = 5186L,
                       minimum_nearest_training_center_m = generated$check$minimum_nearest_training_center_m,
                       files = records, scientific_hash = hash,
                       execution = list(source_paths = as.list(file.path(final_dir, basenames[1:3]))))
    names(acceptance$execution$source_paths) <- c("parquet", "manifest", "qc")
    acceptance_path <- write_json_file(acceptance, file.path(stage, basenames[[4L]]))
    validate_json_schema_file(acceptance_path, spec$schemas[["off_grid"]])
  })
}
