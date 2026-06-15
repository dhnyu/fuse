FUSE_PATH_CONFIG <- list(
  data_root_env = "FUSE_DATA_ROOT",
  large_data_root_env = "FUSE_LARGE_DATA_ROOT",
  repo_root_env = "FUSE_REPO_ROOT",
  data_root_default = "../fusedata",
  large_data_root_default = "../fusedatalarge",
  legacy_data_root = "data",
  large_directory_keys = c(
    "geodata",
    "osm",
    "osm_raw",
    "osm_canonical",
    "osm_canonical_gpkg",
    "osm_canonical_parquet",
    "osm_sampling",
    "osm_metadata",
    "osm_logs",
    "osm_tmp",
    "streetview_panoramas_raw",
    "streetview_crops_front",
    "streetview_crops_right",
    "streetview_crops_rear",
    "streetview_crops_left",
    "streetview_previews",
    "streetview_logs",
    "streetview_manifests",
    "streetview_debug"
  ),
  large_file_keys = c(
    "seoul_boundary",
    "gadm_dir",
    "osm_pbf",
    "osm_roads_canonical",
    "osm_roads_sampling_network",
    "osm_poi_tmp_gpkg",
    "gsv_image_manifest",
    "streetview_manifest_100"
  ),
  directories = list(
    geodata = "geodata",
    grid_500m = "grid_500m",
    osm = "osm",
    osm_raw = "osm/raw",
    osm_canonical = "osm/canonical",
    osm_canonical_gpkg = "osm/canonical/gpkg",
    osm_canonical_parquet = "osm/canonical/parquet",
    osm_sampling = "osm/sampling",
    osm_metadata = "osm/metadata",
    osm_logs = "osm/logs",
    osm_tmp = "osm/tmp",
    sampling_global = "sampling_global",
    sampling_global_debug = "sampling_global/debug",
    streetview = "streetview",
    streetview_final = "streetview/final",
    streetview_metadata = "streetview/metadata",
    streetview_panoramas_raw = "streetview/panoramas/raw",
    streetview_crops_front = "streetview/crops/front",
    streetview_crops_right = "streetview/crops/right",
    streetview_crops_rear = "streetview/crops/rear",
    streetview_crops_left = "streetview/crops/left",
    streetview_previews = "streetview/previews",
    streetview_logs = "streetview/logs",
    streetview_manifests = "streetview/manifests",
    streetview_debug = "streetview/debug"
  ),
  files = list(
    seoul_boundary = "geodata/seoul_boundary.gpkg",
    gadm_dir = "geodata/gadm",
    seoul_grid_500m = "grid_500m/seoul_grid_500m.gpkg",
    seoul_grid_500m_map = "grid_500m/seoul_grid_500m_map.png",
    osm_pbf = "osm/raw/geofabrik_south-korea-latest.osm.pbf",
    osm_roads_canonical = "osm/canonical/seoul_roads_canonical.gpkg",
    osm_roads_sampling_network = "osm/sampling/seoul_roads_sampling_network.gpkg",
    osm_poi_tmp_gpkg = "osm/tmp/seoul_osm_poi_extract.gpkg",
    samples_global_parquet = "sampling_global/seoul_road_network_samples.parquet",
    samples_global_leaflet = "sampling_global/seoul_road_network_sampling_map.html",
    gsv_candidate_pool_parquet = "streetview/metadata/gsv_candidate_pool.parquet",
    gsv_accepted_metadata = "streetview/metadata/gsv_accepted_metadata.parquet",
    gsv_rejected_metadata = "streetview/metadata/gsv_rejected_metadata.parquet",
    gsv_metadata_checkpoint = "streetview/metadata/gsv_metadata_checkpoint.parquet",
    gsv_metadata_rejection_summary = "streetview/metadata/gsv_metadata_rejection_summary.parquet",
    gsv_sampling_network_composition = "streetview/metadata/gsv_sampling_network_composition.parquet",
    gsv_final_manifest = "streetview/final/gsv_seoul_metadata_final_40000.parquet",
    gsv_image_manifest = "streetview/manifests/gsv_large_image_acquisition_manifest.parquet",
    gsv_final_coverage_leaflet = "streetview/metadata/gsv_final_coverage_map.html",
    gsv_diagnostics_report = "streetview/metadata/gsv_diagnostics_report.md",
    streetview_metadata_test = "streetview/metadata/gsv_metadata_test.parquet",
    streetview_metadata_pilot = "streetview/metadata/gsv_metadata_pilot_1000.parquet",
    streetview_metadata_summary = "streetview/metadata/gsv_metadata_pilot_summary.parquet",
    streetview_pano_duplication = "streetview/metadata/gsv_pano_duplication_counts.parquet",
    streetview_capture_year_distribution = "streetview/metadata/gsv_capture_year_distribution.parquet",
    streetview_manifest_100 = "streetview/manifests/gsv_download_manifest_100.parquet"
  )
)

fuse_norm_path <- function(path, must_work = FALSE) {
  normalizePath(path, winslash = "/", mustWork = must_work)
}

fuse_find_repo_root <- function(start = getwd()) {
  env_root <- Sys.getenv(FUSE_PATH_CONFIG$repo_root_env, "")
  if (nzchar(env_root)) {
    root <- fuse_norm_path(env_root, must_work = TRUE)
    if (!file.exists(file.path(root, "config", "paths.R"))) {
      stop("FUSE_REPO_ROOT does not look like the fuse repository: ", root, call. = FALSE)
    }
    return(root)
  }

  current <- fuse_norm_path(start, must_work = TRUE)
  repeat {
    if (file.exists(file.path(current, "config", "paths.R")) &&
        file.exists(file.path(current, "R", "road_environment_sampling.R"))) {
      return(current)
    }
    parent <- dirname(current)
    if (identical(parent, current)) {
      break
    }
    current <- parent
  }

  stop("Could not locate the fuse repository root. Set FUSE_REPO_ROOT.", call. = FALSE)
}

fuse_repo_root <- function() {
  fuse_find_repo_root()
}

fuse_data_root <- function(create = FALSE) {
  repo_root <- fuse_repo_root()
  env_root <- Sys.getenv(FUSE_PATH_CONFIG$data_root_env, "")
  candidates <- character()

  if (nzchar(env_root)) {
    candidates <- c(candidates, env_root)
  } else {
    candidates <- c(
      candidates,
      file.path(repo_root, FUSE_PATH_CONFIG$data_root_default),
      file.path(repo_root, FUSE_PATH_CONFIG$legacy_data_root)
    )
  }

  existing <- candidates[dir.exists(candidates)]
  root <- if (length(existing) > 0) existing[[1]] else candidates[[1]]
  root <- fuse_norm_path(root, must_work = FALSE)

  if (create && !dir.exists(root)) {
    dir.create(root, recursive = TRUE, showWarnings = FALSE)
  }
  root
}

fuse_large_data_root <- function(create = FALSE) {
  repo_root <- fuse_repo_root()
  env_root <- Sys.getenv(FUSE_PATH_CONFIG$large_data_root_env, "")

  root <- if (nzchar(env_root)) {
    env_root
  } else {
    file.path(repo_root, FUSE_PATH_CONFIG$large_data_root_default)
  }
  root <- fuse_norm_path(root, must_work = FALSE)

  if (create && !dir.exists(root)) {
    dir.create(root, recursive = TRUE, showWarnings = FALSE)
  }
  root
}

fuse_key_root <- function(key, kind = c("directory", "file"), create = FALSE) {
  kind <- match.arg(kind)
  large_keys <- if (identical(kind, "directory")) {
    FUSE_PATH_CONFIG$large_directory_keys
  } else {
    FUSE_PATH_CONFIG$large_file_keys
  }

  if (key %in% large_keys) {
    fuse_large_data_root(create = create)
  } else {
    fuse_data_root(create = create)
  }
}

fuse_path <- function(..., create_parent = FALSE, must_exist = FALSE) {
  path <- file.path(fuse_data_root(create = create_parent), ...)
  if (create_parent) {
    dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  }
  if (must_exist && !file.exists(path)) {
    stop("Required data path does not exist: ", path, call. = FALSE)
  }
  path
}

fuse_dir <- function(key, create = FALSE, must_exist = FALSE) {
  rel <- FUSE_PATH_CONFIG$directories[[key]]
  if (is.null(rel)) {
    stop("Unknown FUSE data directory key: ", key, call. = FALSE)
  }
  path <- file.path(fuse_key_root(key, "directory", create = create), rel)
  if (create && !dir.exists(path)) {
    dir.create(path, recursive = TRUE, showWarnings = FALSE)
  }
  if (must_exist && !dir.exists(path)) {
    stop("Required data directory does not exist: ", path, call. = FALSE)
  }
  path
}

fuse_file <- function(key, create_parent = FALSE, must_exist = FALSE) {
  rel <- FUSE_PATH_CONFIG$files[[key]]
  if (is.null(rel)) {
    stop("Unknown FUSE data file key: ", key, call. = FALSE)
  }
  path <- file.path(fuse_key_root(key, "file", create = create_parent), rel)
  if (create_parent) {
    dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  }
  if (must_exist && !file.exists(path)) {
    stop("Required data path does not exist: ", path, call. = FALSE)
  }
  path
}

fuse_ensure_core_dirs <- function() {
  invisible(lapply(names(FUSE_PATH_CONFIG$directories), fuse_dir, create = TRUE))
}

fuse_print_environment <- function() {
  repo_root <- fuse_repo_root()
  data_root <- fuse_data_root(create = FALSE)
  large_data_root <- fuse_large_data_root(create = FALSE)
  cat("FUSE path environment\n")
  cat("  repo_root: ", repo_root, "\n", sep = "")
  cat("  data_root: ", data_root, "\n", sep = "")
  cat("  large_data_root: ", large_data_root, "\n", sep = "")
  cat("  FUSE_DATA_ROOT: ", Sys.getenv("FUSE_DATA_ROOT", "<unset>"), "\n", sep = "")
  cat("  FUSE_LARGE_DATA_ROOT: ", Sys.getenv("FUSE_LARGE_DATA_ROOT", "<unset>"), "\n", sep = "")
  cat("  legacy_data_present: ", dir.exists(file.path(repo_root, "data")), "\n", sep = "")
  invisible(list(repo_root = repo_root, data_root = data_root, large_data_root = large_data_root))
}
