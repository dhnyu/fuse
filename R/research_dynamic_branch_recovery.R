# Zero-compute metadata rehydration for accepted I11 and I15 dynamic branches.
# This module validates immutable outputs before the scientific command promise is forced.

dynamic_recovery_categories <- function() c(
  "raster_open_crop_read", "cell_polygon", "raster_geometry_intersection",
  "zonal_statistics", "vector_geometry", "parquet_zarr_write",
  "safetensors_encode", "tar_archive", "serialization", "dataloader",
  "augmentation", "model_forward", "backward", "optimizer_scheduler_ema_queue",
  "cuda", "checkpoint_gpu_move", "publication", "compute_fallback",
  "raster_fast_path", "serialization_fast_path", "dataset_fast_path"
)

reset_dynamic_recovery_counts <- function() {
  path <- Sys.getenv("FUSE_DYNAMIC_RECOVERY_COUNTER_LOG", unset = "")
  if (nzchar(path) && file.exists(path)) unlink(path)
  invisible(dynamic_recovery_count_snapshot())
}

dynamic_recovery_count_snapshot <- function() {
  categories <- dynamic_recovery_categories()
  path <- Sys.getenv("FUSE_DYNAMIC_RECOVERY_COUNTER_LOG", unset = "")
  events <- if (nzchar(path) && file.exists(path)) readLines(path, warn = FALSE) else character()
  setNames(vapply(categories, function(name) sum(events == name), integer(1L)), categories)
}

increment_dynamic_recovery_count <- function(name) {
  recovery_assert(name %in% dynamic_recovery_categories(), paste("unknown recovery counter", name))
  path <- Sys.getenv("FUSE_DYNAMIC_RECOVERY_COUNTER_LOG", unset = "")
  if (nzchar(path)) cat(name, "\n", file = path, append = TRUE, sep = "")
  invisible(NULL)
}

dynamic_branch_recovery_enabled <- function() {
  identical(Sys.getenv("FUSE_DYNAMIC_BRANCH_RECOVERY_ONLY", unset = "0"), "1")
}

recovery_validation_error <- function(...) {
  stop("RECOVERY_VALIDATION_FAILED: ", ..., call. = FALSE)
}

recovery_sha256 <- function(path) digest::digest(file = path, algo = "sha256", serialize = FALSE)

recovery_sort_names <- function(value) {
  if (!is.list(value)) return(value)
  if (!is.null(names(value))) value <- value[order(names(value), method = "radix")]
  lapply(value, recovery_sort_names)
}

recovery_identity_sha256 <- function(value) canonical_sha256(recovery_sort_names(value))

recovery_assert <- function(condition, message) {
  if (!isTRUE(condition)) recovery_validation_error(message)
  invisible(TRUE)
}

recovery_normalize <- function(path) normalizePath(path, winslash = "/", mustWork = TRUE)

validate_recovery_file_record <- function(record, root = NULL) {
  path <- record$path
  if (!is.null(root) && !grepl("^/", path)) path <- file.path(root, path)
  recovery_assert(file.exists(path) && !dir.exists(path), paste("missing file", path))
  path <- recovery_normalize(path)
  recovery_assert(identical(as.numeric(file.info(path)$size), as.numeric(record$size_bytes)),
                  paste("size mismatch", path))
  recovery_assert(identical(recovery_sha256(path), record$sha256), paste("checksum mismatch", path))
  path
}

validate_exact_directory_entries <- function(directory, expected) {
  recovery_assert(dir.exists(directory), paste("missing artifact directory", directory))
  actual <- sort(list.files(directory, all.files = TRUE, no.. = TRUE))
  recovery_assert(identical(actual, sort(expected)), paste("foreign or incomplete bundle", directory))
  invisible(TRUE)
}

validate_raster_zarr_members <- function(directory, store_record) {
  store <- basename(store_record$path)
  store_path <- file.path(directory, store)
  recovery_assert(dir.exists(store_path), paste("missing Zarr store", store_path))
  members <- store_record$members
  expected <- sort(vapply(members, function(record) recovery_normalize(record$path), character(1L)))
  actual <- sort(recovery_normalize(list.files(store_path, recursive = TRUE, all.files = TRUE,
                                                full.names = TRUE, include.dirs = FALSE)))
  recovery_assert(identical(actual, expected), paste("Zarr member set mismatch", store_path))
  for (record in members) validate_recovery_file_record(record, root = store_path)
  if (!is.null(store_record$size_bytes)) {
    recovery_assert(identical(as.numeric(sum(unlist(lapply(members, `[[`, "size_bytes")))),
                              as.numeric(store_record$size_bytes)), paste("Zarr size mismatch", store_path))
  }
  invisible(TRUE)
}

validate_raster_branch_recovery <- function(spec, vector_files, study_data_inputs,
                                            raster_observation_contract_files) {
  recovery_assert(is.list(spec) && nzchar(spec$branch_id), "invalid raster branch spec")
  observations_root <- dirname(dirname(dirname(dirname(spec$output$directory))))
  accepted_manifest_path <- file.path(dirname(observations_root),
                                      "acceptance", "psa_319c2d2c43cdcfb31478a7d1",
                                      "prototype_spatial_manifest.json")
  accepted <- jsonlite::read_json(accepted_manifest_path, simplifyVector = FALSE)
  recovery_assert(identical(recovery_sha256(accepted_manifest_path),
                            "fe6eb012eee1f92b62f08002de517e9580f9b4073bd2350a82be342291144b07"),
                  "accepted I13 parent manifest checksum mismatch")
  recovery_assert(identical(accepted$status, "PASS") &&
                    identical(accepted$spatial_dataset_id, "psa_319c2d2c43cdcfb31478a7d1"),
                  "accepted I13 parent status or identity mismatch")
  identity <- accepted$artifact_identity
  recovery_assert(identical(identity$raster_observation_dataset_id, "pro_0209ab5b9c50c68f7206bc2b"),
                  "raster dataset identity mismatch")
  recovery_assert(spec$branch_id %in% unlist(accepted$branch_ids, use.names = FALSE),
                  "raster branch is outside accepted scene population")

  final_dir <- file.path(observations_root,
                         identity$raster_observation_dataset_id, "raster", "branches", spec$branch_id)
  expected_names <- raster_output_names()
  validate_exact_directory_entries(final_dir, expected_names)
  manifest_path <- file.path(final_dir, "branch_manifest.json")
  manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  expected_manifest_hash <- identity$raster_branch_manifest_hashes[[spec$branch_id]]
  recovery_assert(!is.null(expected_manifest_hash) && identical(recovery_sha256(manifest_path), expected_manifest_hash),
                  "raster branch manifest is not the accepted parent")
  recovery_assert(identical(manifest$status, "PASS") && identical(manifest$status_final, "PASS"),
                  "raster branch status is not PASS")
  for (field in c("branch_id", "prototype_id", "scene_index_id")) {
    recovery_assert(identical(manifest[[field]], spec[[field]]), paste("raster", field, "mismatch"))
  }
  recovery_assert(identical(manifest$vector_observation_dataset_id, spec$observation_dataset_id),
                  "raster direct parent dataset mismatch")
  expected_scenes <- sort(unlist(spec$scene_ids, use.names = FALSE), method = "radix")
  recovery_assert(identical(unlist(manifest$scene_ids, use.names = FALSE), expected_scenes) &&
                    identical(as.integer(manifest$scene_count), length(expected_scenes)),
                  "raster scene population or order mismatch")
  recovery_assert(identical(recovery_normalize(manifest$inputs$observation_spec_path),
                            recovery_normalize(spec$.path)), "raster plan path mismatch")

  vector_manifest <- vector_files[basename(vector_files) == "branch_manifest.json"]
  recovery_assert(length(vector_manifest) == 1L, "raster vector parent manifest is ambiguous")
  recovery_assert(identical(recovery_normalize(manifest$inputs$vector_branch_manifest_path),
                            recovery_normalize(vector_manifest)), "raster vector parent path mismatch")
  recovery_assert(identical(recovery_sha256(vector_manifest), manifest$inputs$vector_branch_manifest_sha256) &&
                    identical(identity$vector_branch_manifest_hashes[[spec$branch_id]],
                              manifest$inputs$vector_branch_manifest_sha256),
                  "raster vector parent checksum mismatch")

  contract <- setNames(raster_observation_contract_files, basename(raster_observation_contract_files))
  expected_hashes <- c(
    config_hash = recovery_sha256(contract[["raster_observation.yml"]]),
    schema_hash = recovery_sha256(contract[["prototype_raster_observation.schema.json"]]),
    writer_hash = recovery_sha256(contract[["write_raster_zarr.py"]]),
    requirements_hash = recovery_sha256(contract[["requirements-raster.txt"]]),
    implementation_source_hash = recovery_sha256(contract[["research_raster_observation.R"]])
  )
  actual_hashes <- unlist(manifest$inputs[names(expected_hashes)], use.names = TRUE)
  recovery_assert(identical(unname(actual_hashes), unname(expected_hashes)),
                  "raster scientific contract hash mismatch")
  study <- setNames(study_data_inputs, basename(study_data_inputs))
  for (modality in c("landcover", "dem")) {
    required_name <- c(landcover = "seoul_lc.tif", dem = "seoul_dem.tif")[[modality]]
    record <- manifest$inputs$rasters[[modality]]
    path <- study[[required_name]]
    recovery_assert(length(path) == 1L && identical(recovery_normalize(record$path), recovery_normalize(path)),
                    paste("raster input path mismatch", modality))
    validate_recovery_file_record(record)
  }

  for (record in manifest$outputs) {
    if (identical(record$artifact_type, "file")) validate_recovery_file_record(record)
  }
  member_manifest <- jsonlite::read_json(file.path(final_dir, "zarr_member_manifest.json"), simplifyVector = FALSE)
  recovery_assert(identical(member_manifest$branch_id, spec$branch_id) &&
                    identical(member_manifest$raster_observation_dataset_id, identity$raster_observation_dataset_id),
                  "Zarr member manifest lineage mismatch")
  validate_raster_zarr_members(final_dir, member_manifest$stores$landcover)
  validate_raster_zarr_members(final_dir, member_manifest$stores$dem)
  member_sizes <- vapply(member_manifest$stores, function(store) {
    sum(unlist(lapply(store$members, `[[`, "size_bytes")))
  }, numeric(1L))
  output_sizes <- vapply(manifest$outputs[1:2], `[[`, numeric(1L), "size_bytes")
  recovery_assert(identical(unname(member_sizes), unname(output_sizes)), "raster Zarr aggregate size mismatch")
  qc <- jsonlite::read_json(file.path(final_dir, "branch_qc.json"), simplifyVector = FALSE)
  recovery_assert(identical(qc$status, "PASS") && identical(qc$branch_id, spec$branch_id) &&
                    identical(as.integer(qc$scene_count), length(expected_scenes)) &&
                    length(qc$failures) == 0L, "raster branch-local QC mismatch")
  recovery_normalize(file.path(final_dir, expected_names[c(3L, 4L, 5L, 6L, 7L, 8L)]))
}

recover_raster_observation_branch <- function(spec, vector_files, study_data_inputs,
                                              raster_observation_contract_files, compute,
                                              validator = validate_raster_branch_recovery) {
  if (!dynamic_branch_recovery_enabled()) return(compute)
  result <- validator(spec, vector_files, study_data_inputs, raster_observation_contract_files)
  increment_dynamic_recovery_count("raster_fast_path")
  result
}

validate_serialization_branch_recovery <- function(spec, serialization_shard_contract_files) {
  recovery_assert(is.list(spec) && nzchar(spec$branch_id) && file.exists(spec$.path),
                  "invalid serialization branch spec")
  final_dir <- spec$output$directory
  expected <- c(paste0("scenes-", spec$branch_id, ".tar"), paste0("scenes-", spec$branch_id, ".idx"),
                "scene_index.parquet", "branch_qc.json", "branch_log.jsonl", "branch_manifest.json")
  validate_exact_directory_entries(final_dir, expected)
  manifest_path <- file.path(final_dir, "branch_manifest.json")
  manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  recovery_assert(identical(manifest$status, "PASS") && identical(manifest$branch_id, spec$branch_id),
                  "serialization branch status or identity mismatch")
  for (field in c("plan_id", "serialization_dataset_id", "spatial_dataset_id")) {
    recovery_assert(identical(manifest[[field]], spec[[field]]), paste("serialization", field, "mismatch"))
  }
  recovery_assert(identical(manifest$split, spec$split) &&
                    identical(unlist(manifest$scene_ids, use.names = FALSE), unlist(spec$scene_ids, use.names = FALSE)),
                  "serialization scene population, order, or split mismatch")
  recovery_assert(identical(recovery_normalize(manifest$source_spec$path), recovery_normalize(spec$.path)) &&
                    identical(manifest$source_spec$sha256, recovery_sha256(spec$.path)) &&
                    identical(as.numeric(manifest$source_spec$size_bytes), as.numeric(file.info(spec$.path)$size)),
                  "serialization plan branch parent mismatch")
  recovery_assert(identical(recovery_identity_sha256(manifest$scientific_identity$i14_scientific_identity),
                            recovery_identity_sha256(spec$scientific_identity)),
                  "serialization I14 scientific identity mismatch")
  for (record in spec$accepted_artifacts) validate_recovery_file_record(record)

  contract <- setNames(serialization_shard_contract_files, basename(serialization_shard_contract_files))
  hashes <- manifest$scientific_identity
  recovery_assert(identical(hashes$tensor_contract_sha256,
                            recovery_sha256(contract[["serialization_shard.yml"]])) &&
                    identical(hashes$manifest_schema_sha256,
                              recovery_sha256(contract[["prototype_serialization_shard.schema.json"]])) &&
                    identical(hashes$implementation_sha256,
                              recovery_sha256(contract[["serialize_prototype_shard.py"]])) &&
                    identical(hashes$requirements_sha256,
                              recovery_sha256(contract[["requirements-serialization.txt"]])),
                  "serialization scientific contract hash mismatch")
  output_names <- vapply(manifest$outputs, `[[`, character(1L), "relative_path")
  recovery_assert(identical(sort(output_names), sort(setdiff(expected, "branch_manifest.json"))),
                  "serialization output manifest set mismatch")
  for (record in manifest$outputs) validate_recovery_file_record(record, root = final_dir)
  qc <- jsonlite::read_json(file.path(final_dir, "branch_qc.json"), simplifyVector = FALSE)
  recovery_assert(identical(qc$status, "PASS") && identical(qc$branch_id, spec$branch_id) &&
                    identical(as.integer(qc$error_count), 0L) &&
                    identical(as.integer(qc$round_trip_scene_count), length(spec$scene_ids)),
                  "serialization branch-local QC mismatch")

  dataset_dir <- file.path(dirname(dirname(final_dir)), "acceptance", "ptd_8b3359690ea2d0bef52d63e3")
  dataset_manifest <- file.path(dataset_dir, "accepted_training_dataset_manifest.json")
  recovery_assert(identical(recovery_sha256(dataset_manifest),
                            "7d5f0f66ef792fda94f647c44ddf7a1a7cc378c994e5324aa47dc75a2354359a"),
                  "accepted I16 parent manifest checksum mismatch")
  catalog <- arrow::read_parquet(file.path(dataset_dir, "shard_catalog.parquet"), as_data_frame = TRUE)
  row <- catalog[catalog$branch_id == spec$branch_id, , drop = FALSE]
  recovery_assert(nrow(row) == 1L && identical(row$branch_manifest_sha256[[1L]], recovery_sha256(manifest_path)),
                  "serialization branch manifest is not in accepted I16 lineage")
  recovery_normalize(file.path(final_dir, expected))
}

recover_serialization_branch <- function(spec, serialization_shard_contract_files, compute,
                                         validator = validate_serialization_branch_recovery) {
  if (!dynamic_branch_recovery_enabled()) return(compute)
  result <- validator(spec, serialization_shard_contract_files)
  increment_dynamic_recovery_count("serialization_fast_path")
  result
}

validate_training_dataset_recovery <- function(serialization_plan, serialization_branch_files,
                                               spatial_files, contract_files) {
  recovery_assert(length(serialization_plan) == 51L, "I16 serialization plan branch count mismatch")
  first <- serialization_plan[[1L]]
  directory <- file.path(first$output$root, "acceptance", "ptd_8b3359690ea2d0bef52d63e3")
  expected <- c(
    "accepted_training_dataset_manifest.json", "shard_catalog.parquet",
    "global_scene_index.parquet", "dataset_index.json", "aggregate_qc.json",
    "actual_byte_resource_diagnostics.parquet", "acceptance_log.jsonl"
  )
  recovery_assert(dir.exists(directory), paste("missing artifact directory", directory))
  top_level <- list.files(directory, all.files = TRUE, no.. = TRUE, full.names = TRUE)
  actual_files <- sort(basename(top_level[!file.info(top_level)$isdir]))
  recovery_assert(identical(actual_files, sort(expected)), paste("foreign or incomplete bundle", directory))
  recovery_assert(identical(basename(directory), "ptd_8b3359690ea2d0bef52d63e3"),
                  "I16 staging directory cannot be authoritative")
  manifest_path <- file.path(directory, expected[[1L]])
  recovery_assert(identical(recovery_sha256(manifest_path),
                            "7d5f0f66ef792fda94f647c44ddf7a1a7cc378c994e5324aa47dc75a2354359a"),
                  "accepted I16 manifest checksum mismatch")
  manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  recovery_assert(identical(manifest$status, "READY") &&
                    identical(manifest$training_dataset_id, "ptd_8b3359690ea2d0bef52d63e3") &&
                    identical(manifest$serialization_plan_id, first$plan_id) &&
                    identical(manifest$serialization_dataset_id, first$serialization_dataset_id) &&
                    identical(manifest$spatial_dataset_id, first$spatial_dataset_id),
                  "I16 identity or parent lineage mismatch")

  spec_hashes <- setNames(vapply(serialization_plan, function(spec) recovery_sha256(spec$.path), character(1L)),
                          vapply(serialization_plan, `[[`, character(1L), "branch_id"))
  accepted_specs <- setNames(vapply(manifest$scientific_identity$i14_specs, `[[`, character(1L), "sha256"),
                             vapply(manifest$scientific_identity$i14_specs, `[[`, character(1L), "branch_id"))
  recovery_assert(identical(spec_hashes[sort(names(spec_hashes))], accepted_specs[sort(names(accepted_specs))]),
                  "I16 plan branch set or checksum mismatch")
  branch_paths <- unlist(serialization_branch_files, use.names = FALSE)
  branch_manifests <- branch_paths[basename(branch_paths) == "branch_manifest.json"]
  observed_branch_hashes <- setNames(vapply(branch_manifests, recovery_sha256, character(1L)),
                                     basename(dirname(branch_manifests)))
  accepted_branch_hashes <- setNames(
    vapply(manifest$scientific_identity$i15_branch_manifests, `[[`, character(1L), "sha256"),
    vapply(manifest$scientific_identity$i15_branch_manifests, `[[`, character(1L), "branch_id")
  )
  recovery_assert(identical(observed_branch_hashes[sort(names(observed_branch_hashes))],
                            accepted_branch_hashes[sort(names(accepted_branch_hashes))]),
                  "I16 serialization branch lineage mismatch")
  spatial_manifest <- unlist(spatial_files, use.names = FALSE)
  spatial_manifest <- spatial_manifest[basename(spatial_manifest) == "prototype_spatial_manifest.json"]
  recovery_assert(length(spatial_manifest) == 1L &&
                    identical(recovery_sha256(spatial_manifest), manifest$scientific_identity$i13_manifest_sha256),
                  "I16 spatial parent checksum mismatch")
  for (record in manifest$accepted_artifacts) validate_recovery_file_record(record)

  contract <- setNames(contract_files, basename(contract_files))
  scientific <- manifest$scientific_identity
  recovery_assert(identical(scientific$acceptance_config_sha256,
                            recovery_sha256(contract[["training_dataset_acceptance.yml"]])) &&
                    identical(scientific$acceptance_schema_sha256,
                              recovery_sha256(contract[["prototype_training_dataset_acceptance.schema.json"]])) &&
                    identical(scientific$tensor_contract_sha256,
                              recovery_sha256(contract[["serialization_shard.yml"]])) &&
                    identical(scientific$implementation_sha256,
                              recovery_sha256(contract[["accept_prototype_training_dataset.py"]])),
                  "I16 scientific config, schema, tensor, or implementation hash mismatch")
  output_names <- vapply(manifest$outputs, `[[`, character(1L), "relative_path")
  recovery_assert(identical(sort(output_names), sort(setdiff(expected, expected[[1L]]))),
                  "I16 expected output set mismatch")
  for (record in manifest$outputs) validate_recovery_file_record(record, root = directory)
  qc <- jsonlite::read_json(file.path(directory, "aggregate_qc.json"), simplifyVector = FALSE)
  recovery_assert(identical(qc$status, "PASS") && identical(qc$training_dataset_id,
                                                             "ptd_8b3359690ea2d0bef52d63e3") &&
                    identical(as.integer(qc$branch_count), 51L) &&
                    identical(as.integer(qc$scene_count), 320L) &&
                    identical(as.integer(qc$error_count), 0L), "I16 aggregate QC mismatch")
  recovery_normalize(file.path(directory, expected))
}

recover_training_dataset_acceptance <- function(serialization_plan, serialization_branch_files,
                                                spatial_files, contract_files, compute,
                                                validator = validate_training_dataset_recovery) {
  if (!dynamic_branch_recovery_enabled()) return(compute)
  result <- validator(serialization_plan, serialization_branch_files, spatial_files, contract_files)
  increment_dynamic_recovery_count("dataset_fast_path")
  result
}
