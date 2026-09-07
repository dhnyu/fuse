research_config_paths <- function(root = getwd()) {
  file.path(root, "config/research_paths.yml")
}

research_implementation_paths <- function(root = getwd()) {
  file.path(root, "R/contracts.R")
}

named_file_vector <- function(x) {
  unlist(x, use.names = TRUE)
}

load_research_config <- function(config_files) {
  files <- normalizePath(config_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  required <- "research_paths.yml"
  missing <- setdiff(required, names(by_name))
  if (length(missing)) {
    stop("Missing research configuration files: ", paste(missing, collapse = ", "), call. = FALSE)
  }
  paths <- yaml::read_yaml(by_name[["research_paths.yml"]])
  list(
    paths = paths,
    config_files = files,
    config_sha256 = sha256_file_set(files)
  )
}

study_input_files <- function(config_files) {
  config <- load_research_config(config_files)
  files <- named_file_vector(config$paths$inputs)
  if (length(files) != 12L) stop("study_data_inputs must track exactly 12 files", call. = FALSE)
  missing <- names(files)[!file.exists(files)]
  if (length(missing)) stop("Missing study input(s): ", paste(missing, collapse = ", "), call. = FALSE)
  empty <- names(files)[is.na(file.info(files)$size) | file.info(files)$size <= 0]
  if (length(empty)) stop("Empty study input(s): ", paste(empty, collapse = ", "), call. = FALSE)
  setNames(normalizePath(files, mustWork = TRUE), names(files))
}

canonical_json <- function(value) {
  jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA, pretty = FALSE)
}

canonical_sha256 <- function(value) {
  digest::digest(canonical_json(value), algo = "sha256", serialize = FALSE)
}

short_hash_id <- function(prefix, value, characters = 24L) {
  paste0(prefix, substr(canonical_sha256(value), 1L, as.integer(characters)))
}

write_json_file <- function(value, path) {
  jsonlite::write_json(
    value, path, auto_unbox = TRUE, pretty = TRUE, null = "null", digits = NA
  )
  path
}

publish_bundle <- function(final_dir, required_basenames, writer) {
  final_paths <- file.path(final_dir, required_basenames)
  if (dir.exists(final_dir)) {
    if (!all(file.exists(final_paths))) {
      stop("Existing artifact bundle is incomplete: ", final_dir, call. = FALSE)
    }
    return(normalizePath(final_paths, mustWork = TRUE))
  }
  dir.create(dirname(final_dir), recursive = TRUE, showWarnings = FALSE)
  stage <- tempfile(pattern = paste0(".", basename(final_dir), ".stage-"), tmpdir = dirname(final_dir))
  dir.create(stage)
  on.exit(if (dir.exists(stage)) unlink(stage, recursive = TRUE), add = TRUE)
  writer(stage)
  staged <- file.path(stage, required_basenames)
  if (!all(file.exists(staged)) || any(file.info(staged)$size <= 0)) {
    stop("Staged artifact bundle failed completeness checks: ", stage, call. = FALSE)
  }
  if (!file.rename(stage, final_dir)) {
    stop("Atomic artifact bundle publish failed: ", final_dir, call. = FALSE)
  }
  normalizePath(final_paths, mustWork = TRUE)
}

read_vector_sample <- function(path, layer, expected_epsg, expected_geometry) {
  available <- sf::st_layers(path)$name
  if (!layer %in% available) stop("Missing layer ", layer, " in ", path, call. = FALSE)
  query <- sprintf('SELECT * FROM "%s" LIMIT 1', gsub('"', '""', layer, fixed = TRUE))
  value <- sf::st_read(path, query = query, quiet = TRUE)
  epsg <- sf::st_crs(value)$epsg
  geometry <- as.character(unique(sf::st_geometry_type(value)))
  if (!identical(as.integer(epsg), as.integer(expected_epsg))) {
    stop("CRS mismatch for ", path, "/", layer, ": ", epsg, call. = FALSE)
  }
  if (!all(geometry %in% expected_geometry)) {
    stop("Geometry mismatch for ", path, "/", layer, ": ", paste(geometry, collapse = ","), call. = FALSE)
  }
  list(layer = layer, epsg = epsg, geometry_type = geometry)
}

raster_inventory <- function(path, expected_epsg, buffer_bbox) {
  raster <- terra::rast(path)
  if (terra::nlyr(raster) < 1L) stop("Raster has no readable band: ", path, call. = FALSE)
  epsg <- sf::st_crs(terra::crs(raster))$epsg
  if (!identical(as.integer(epsg), as.integer(expected_epsg))) {
    stop("Raster CRS mismatch: ", path, call. = FALSE)
  }
  extent <- terra::ext(raster)
  covers <- extent$xmin <= buffer_bbox[["xmin"]] && extent$xmax >= buffer_bbox[["xmax"]] &&
    extent$ymin <= buffer_bbox[["ymin"]] && extent$ymax >= buffer_bbox[["ymax"]]
  if (!covers) stop("Raster does not cover the 400 m study buffer: ", path, call. = FALSE)
  list(
    epsg = epsg,
    bands = terra::nlyr(raster),
    dimensions = c(rows = terra::nrow(raster), columns = terra::ncol(raster)),
    resolution = unname(terra::res(raster)),
    extent = c(xmin = extent$xmin, ymin = extent$ymin, xmax = extent$xmax, ymax = extent$ymax),
    covers_buffer = TRUE
  )
}

validate_manifest_paths <- function(manifest, inputs) {
  if (!identical(manifest$status, "PASS")) stop("Study manifest status is not PASS", call. = FALSE)
  roles <- c("boundary", "buffer400", "building", "road", "poi", "landcover", "dem")
  lapply(roles, function(role) {
    recorded <- manifest$outputs[[role]]
    if (is.null(recorded)) stop("Study manifest lacks output: ", role, call. = FALSE)
    actual <- normalizePath(inputs[[role]], mustWork = TRUE)
    if (!identical(actual, normalizePath(recorded$path, mustWork = TRUE))) {
      stop("Study manifest path mismatch for ", role, call. = FALSE)
    }
    hash <- sha256_file(actual)
    if (!identical(hash, recorded$sha256)) stop("Study manifest checksum mismatch for ", role, call. = FALSE)
    if (!identical(as.numeric(file.info(actual)$size), as.numeric(recorded$size_bytes))) {
      stop("Study manifest size mismatch for ", role, call. = FALSE)
    }
    list(role = role, path = actual, sha256 = hash, size_bytes = unname(file.info(actual)$size))
  })
}

research_python_executable <- function() {
  rscript <- Sys.which("Rscript")
  adjacent <- if (nzchar(rscript)) file.path(dirname(normalizePath(rscript)), "python") else ""
  candidates <- c(file.path(dirname(dirname(R.home())), "bin", "python"), adjacent, Sys.which("python"))
  candidates <- candidates[nzchar(candidates) & file.exists(candidates)]
  if (!length(candidates)) stop("Python executable is unavailable", call. = FALSE)
  normalizePath(candidates[[1L]], mustWork = TRUE)
}

validate_json_schema_file <- function(json_file, schema_file) {
  executable <- Sys.which("check-jsonschema")
  if (nzchar(executable)) {
    command <- executable
    arguments <- c("--schemafile", shQuote(schema_file), shQuote(json_file))
  } else {
    command <- research_python_executable()
    code <- paste0(
      "import json,sys,jsonschema;",
      "schema=json.load(open(sys.argv[1],encoding='utf-8'));",
      "value=json.load(open(sys.argv[2],encoding='utf-8'));",
      "jsonschema.Draft202012Validator.check_schema(schema);",
      "jsonschema.validate(value,schema);print('ok')"
    )
    arguments <- c("-c", shQuote(code), shQuote(schema_file), shQuote(json_file))
  }
  output <- system2(command, arguments, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status") %||% 0L
  if (status != 0L) stop("JSON Schema validation failed:\n", paste(output, collapse = "\n"), call. = FALSE)
  invisible(TRUE)
}
