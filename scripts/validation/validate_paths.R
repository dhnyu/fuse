#!/usr/bin/env Rscript

find_repo_root_from <- function(start) {
  current <- normalizePath(start, winslash = "/", mustWork = TRUE)
  repeat {
    if (file.exists(file.path(current, "config", "paths.R"))) return(current)
    parent <- dirname(current)
    if (identical(parent, current)) stop("Could not locate repository root.", call. = FALSE)
    current <- parent
  }
}
script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
start_dir <- if (length(script_arg)) dirname(sub("^--file=", "", script_arg[1])) else getwd()
repo_root <- find_repo_root_from(start_dir)
source(file.path(repo_root, "config", "paths.R"))

expected_discoverable_files <- c(
  "seoul_boundary",
  "osm_roads_canonical",
  "samples_global_parquet",
  "gsv_final_manifest",
  "gsv_image_manifest"
)

required_directory_keys <- c(
  "geodata",
  "osm",
  "osm_raw",
  "osm_canonical",
  "osm_sampling",
  "sampling_global",
  "streetview",
  "streetview_final",
  "streetview_metadata",
  "streetview_panoramas_raw",
  "streetview_crops_front",
  "streetview_crops_right",
  "streetview_crops_rear",
  "streetview_crops_left",
  "streetview_manifests"
)

can_write <- function(directory) {
  dir.create(directory, recursive = TRUE, showWarnings = FALSE)
  probe <- file.path(directory, ".fuse_write_test")
  ok <- tryCatch({
    writeLines("ok", probe)
    unlink(probe)
    TRUE
  }, error = function(e) FALSE)
  ok
}

if (tolower(Sys.getenv("FUSE_VALIDATE_CREATE_DIRS", "false")) == "true") {
  fuse_ensure_core_dirs()
}
env <- fuse_print_environment()

missing_required_dirs <- required_directory_keys[
  !vapply(required_directory_keys, function(key) dir.exists(fuse_dir(key)), logical(1))
]
optional_directory_keys <- setdiff(names(FUSE_PATH_CONFIG$directories), required_directory_keys)
optional_missing_dirs <- optional_directory_keys[
  !vapply(optional_directory_keys, function(key) dir.exists(fuse_dir(key)), logical(1))
]
unwritable_dirs <- required_directory_keys[
  !vapply(required_directory_keys, function(key) dir.exists(fuse_dir(key)) && can_write(fuse_dir(key)), logical(1))
]
missing_files <- expected_discoverable_files[
  !vapply(expected_discoverable_files, function(key) file.exists(fuse_file(key)), logical(1))
]

cat("  data_root_writable: ", can_write(env$data_root), "\n", sep = "")
cat("  large_data_root_writable: ", can_write(env$large_data_root), "\n", sep = "")
cat("  configured_directories: ", length(FUSE_PATH_CONFIG$directories), "\n", sep = "")
cat("  configured_files: ", length(FUSE_PATH_CONFIG$files), "\n", sep = "")
cat("  missing_required_directories: ", if (length(missing_required_dirs)) paste(missing_required_dirs, collapse = ", ") else "none", "\n", sep = "")
cat("  optional_missing_directories: ", if (length(optional_missing_dirs)) paste(optional_missing_dirs, collapse = ", ") else "none", "\n", sep = "")
cat("  unwritable_directories: ", if (length(unwritable_dirs)) paste(unwritable_dirs, collapse = ", ") else "none", "\n", sep = "")
cat("  missing_expected_files: ", if (length(missing_files)) paste(missing_files, collapse = ", ") else "none", "\n", sep = "")

if (length(missing_required_dirs) || length(unwritable_dirs)) {
  quit(status = 1)
}
