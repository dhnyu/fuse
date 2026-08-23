runtime_mirror_contract_paths <- function(root = getwd()) {
  file.path(root, c("config/runtime_mirror.yml", "scripts/prepare_runtime_mirror.py"))
}

runtime_mirror_role_paths <- function(paths) {
  paths <- normalizePath(paths, mustWork = TRUE)
  roles <- basename(dirname(paths))
  official <- roles == "official_grid"
  roles[official] <- paste0("official_grid_", tools::file_ext(paths[official]))
  setNames(paths, roles)
}

validate_runtime_mirror <- function(runtime_mirror_contract_files) {
  files <- normalizePath(runtime_mirror_contract_files, mustWork = TRUE)
  config_path <- files[basename(files) == "runtime_mirror.yml"]
  if (length(config_path) != 1L) stop("Runtime mirror config is not unique", call. = FALSE)
  config <- yaml::read_yaml(config_path)
  marker <- file.path(config$mirror_root, config$activation$marker)
  if (!file.exists(marker)) stop("Runtime mirror READY marker is missing", call. = FALSE)
  ready <- jsonlite::read_json(marker, simplifyVector = FALSE)
  if (!identical(ready$status, "READY") ||
      !identical(ready$scientific_identity, "excluded_execution_only") ||
      !identical(ready$source_mutations, 0L)) {
    stop("Runtime mirror READY contract is invalid", call. = FALSE)
  }
  records <- lapply(ready$files, function(record) {
    source <- normalizePath(record$source_path, mustWork = TRUE)
    mirror <- normalizePath(record$mirror_path, mustWork = TRUE)
    if (!identical(as.numeric(file.info(source)$size), as.numeric(record$size_bytes)) ||
        !identical(as.numeric(file.info(mirror)$size), as.numeric(record$size_bytes)) ||
        !identical(sha256_file(source), record$sha256) ||
        !identical(sha256_file(mirror), record$sha256) ||
        !identical(record$mirror_sha256, record$sha256)) {
      stop("Runtime mirror source/copy mismatch: ", record$role, call. = FALSE)
    }
    c(role = record$role, path = mirror)
  })
  values <- setNames(vapply(records, `[[`, character(1L), "path"),
                     vapply(records, `[[`, character(1L), "role"))
  attr(values, "runtime_execution_only") <- TRUE
  values
}

runtime_mirror_path <- function(runtime_inputs, role) {
  paths <- runtime_mirror_role_paths(runtime_inputs)
  value <- paths[[role]]
  if (is.null(value) || length(value) != 1L) stop("Runtime mirror role is missing: ", role, call. = FALSE)
  value
}

runtime_source_record <- function(source, runtime_inputs, role) {
  value <- source
  value$path <- runtime_mirror_path(runtime_inputs, role)
  if (!identical(as.numeric(file.info(value$path)$size), as.numeric(source$size_bytes)) ||
      !identical(sha256_file(value$path), source$sha256)) {
    stop("Runtime mirror does not match scientific source: ", role, call. = FALSE)
  }
  value
}
