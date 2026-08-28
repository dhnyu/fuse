accepted_parent_config_path <- function(root = getwd()) {
  file.path(normalizePath(root, mustWork = TRUE), "config/accepted_immutable_parents.yml")
}

accepted_parent_config <- function(path) yaml::read_yaml(normalizePath(path, mustWork = TRUE))

accepted_sha256_file <- function(path) digest::digest(file = path, algo = "sha256", serialize = FALSE)

accepted_existing_files <- function(paths, label) {
  paths <- sort(normalizePath(paths, mustWork = TRUE), method = "radix")
  if (!length(paths) || any(file.info(paths)$size <= 0)) stop("Incomplete accepted ", label, " reference", call. = FALSE)
  paths
}

accepted_p1_scene_index_files <- function(config_file) {
  cfg <- accepted_parent_config(config_file)$p1
  paths <- accepted_existing_files(file.path(cfg$root, c("spatial_scene_index.parquet", "spatial_scene_index_manifest.json")), "P1 scene index")
  manifest <- jsonlite::read_json(paths[basename(paths) == "spatial_scene_index_manifest.json"], simplifyVector = FALSE)
  if (manifest$scene_index_id != cfg$scene_index_id || manifest$status != "PASS" || manifest$row_count != 4421L)
    stop("Accepted P1 scene-index identity mismatch", call. = FALSE)
  paths
}

accepted_p2_base_spatial_files <- function(config_file) {
  cfg <- accepted_parent_config(config_file)$p2
  paths <- accepted_existing_files(list.files(cfg$root, full.names = TRUE), "P2 base-spatial acceptance")
  manifest <- jsonlite::read_json(paths[basename(paths) == "base_spatial_acceptance.json"], simplifyVector = FALSE)
  if (manifest$acceptance_id != cfg$acceptance_id || manifest$original_observation_id != cfg$observation_id ||
      manifest$status != "PASS" || manifest$scene_count != 4421L)
    stop("Accepted P2 base-spatial identity mismatch", call. = FALSE)
  paths
}

accepted_p3_shard_files <- function(config_file) {
  cfg <- accepted_parent_config(config_file)$p3
  manifests <- sort(list.files(file.path(cfg$root, "shards"), "^shard_manifest[.]json$", recursive = TRUE, full.names = TRUE), method = "radix")
  if (length(manifests) != cfg$shard_count) stop("Accepted P3 shard-count mismatch", call. = FALSE)
  groups <- lapply(manifests, function(path) {
    manifest <- jsonlite::read_json(path, simplifyVector = FALSE)
    payload <- file.path(dirname(path), manifest$payload$filename)
    execution <- file.path(dirname(path), "execution.json")
    if (manifest$cache_id != cfg$cache_id || manifest$status != "PASS" ||
        accepted_sha256_file(payload) != manifest$payload$sha256) stop("Accepted P3 shard identity/checksum mismatch", call. = FALSE)
    accepted_existing_files(c(payload, path, execution), paste("P3 shard", manifest$branch_id))
  })
  unname(unlist(groups, use.names = FALSE))
}

accepted_p3_shard_groups <- function(flat_files, config_file) {
  cfg <- accepted_parent_config(config_file)$p3
  groups <- split(normalizePath(flat_files, mustWork = TRUE), dirname(normalizePath(flat_files, mustWork = TRUE)))
  groups <- groups[order(names(groups), method = "radix")]
  if (length(groups) != cfg$shard_count || any(vapply(groups, length, integer(1L)) != 3L))
    stop("Accepted P3 shard reference grouping mismatch", call. = FALSE)
  unname(groups)
}

accepted_p3_index_files <- function(config_file) {
  cfg <- accepted_parent_config(config_file)$p3
  paths <- accepted_existing_files(list.files(file.path(cfg$root, "index"), recursive = TRUE, full.names = TRUE), "P3 cache index")
  manifest_path <- paths[basename(paths) == "index_manifest.json"]
  manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  if (length(manifest_path) != 1L || manifest$cache_id != cfg$cache_id || manifest$status != "PASS" || manifest$scene_count != cfg$scene_count)
    stop("Accepted P3 cache-index identity mismatch", call. = FALSE)
  paths
}

accepted_p3_acceptance_files <- function(config_file) {
  cfg <- accepted_parent_config(config_file)$p3
  path <- file.path(cfg$root, "acceptance", cfg$acceptance_id, "original_scene_dataset_acceptance.json")
  paths <- accepted_existing_files(path, "P3 dataset acceptance")
  manifest <- jsonlite::read_json(paths, simplifyVector = FALSE)
  if (manifest$cache_id != cfg$cache_id || manifest$acceptance_id != cfg$acceptance_id ||
      manifest$status != "PASS" || manifest$scene_count != cfg$scene_count || manifest$shard_count != cfg$shard_count)
    stop("Accepted P3 dataset identity mismatch", call. = FALSE)
  paths
}
