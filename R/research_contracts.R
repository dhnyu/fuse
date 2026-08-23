research_config_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/research_paths.yml",
    "config/scene_construction.yml",
    "config/schemas/methodology_contract.schema.json"
  ))
}

research_implementation_paths <- function(root = getwd()) {
  file.path(root, "R/research_contracts.R")
}

accepted_off_grid_source_files <- function(config_files) {
  config <- load_research_config(config_files)
  source <- config$scene$off_grid$source
  paths <- c(parquet = source$parquet, manifest = source$manifest)
  expected_sizes <- c(parquet = source$parquet_size_bytes, manifest = source$manifest_size_bytes)
  expected_hashes <- c(parquet = source$parquet_sha256, manifest = source$manifest_sha256)
  for (name in names(paths)) {
    if (!file.exists(paths[[name]]) || file.info(paths[[name]])$size != expected_sizes[[name]] ||
        !identical(sha256_file(paths[[name]]), expected_hashes[[name]])) {
      stop("Accepted off-grid source mismatch: ", name, call. = FALSE)
    }
  }
  setNames(normalizePath(paths, mustWork = TRUE), names(paths))
}

named_file_vector <- function(x) {
  unlist(x, use.names = TRUE)
}

load_research_config <- function(config_files) {
  files <- normalizePath(config_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  required <- c(
    "research_paths.yml", "scene_construction.yml",
    "methodology_contract.schema.json"
  )
  missing <- setdiff(required, names(by_name))
  if (length(missing)) {
    stop("Missing research configuration files: ", paste(missing, collapse = ", "), call. = FALSE)
  }
  paths <- yaml::read_yaml(by_name[["research_paths.yml"]])
  scene <- yaml::read_yaml(by_name[["scene_construction.yml"]])
  list(
    paths = paths,
    scene = scene,
    schema_file = by_name[["methodology_contract.schema.json"]],
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

build_study_data_inventory <- function(study_data_inputs, research_config_files, workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- capture_native_thread_state()
  on.exit(restore_native_thread_state(state), add = TRUE)
  set_native_thread_limits(threads)
  config <- load_research_config(research_config_files)
  inputs <- setNames(normalizePath(study_data_inputs, mustWork = TRUE), names(config$paths$inputs))
  manifest <- jsonlite::read_json(inputs[["study_manifest"]], simplifyVector = FALSE)
  manifest_files <- validate_manifest_paths(manifest, inputs)

  layers <- config$paths$layers
  boundary <- sf::st_read(inputs[["boundary"]], layers$boundary, quiet = TRUE)
  buffer <- sf::st_read(inputs[["buffer400"]], layers$buffer400, quiet = TRUE)
  if (sf::st_crs(boundary)$epsg != 5186L || sf::st_crs(buffer)$epsg != 5186L) {
    stop("Boundary and buffer must be EPSG:5186", call. = FALSE)
  }
  if (!all(sf::st_is_valid(boundary)) || !all(sf::st_is_valid(buffer))) {
    stop("Boundary or buffer geometry is invalid", call. = FALSE)
  }
  if (!all(lengths(sf::st_covered_by(boundary, buffer)) > 0L)) {
    stop("The 400 m buffer does not cover the Seoul boundary", call. = FALSE)
  }
  expected_buffer <- sf::st_buffer(sf::st_union(boundary), 400)
  buffer_difference <- as.numeric(sum(sf::st_area(sf::st_sym_difference(sf::st_union(buffer), expected_buffer))))
  if (buffer_difference > 1e-4) stop("Stored buffer differs from the exact 400 m boundary buffer", call. = FALSE)
  buffer_bbox <- sf::st_bbox(buffer)

  vectors <- list(
    boundary = read_vector_sample(inputs[["boundary"]], layers$boundary, 5186, c("POLYGON", "MULTIPOLYGON")),
    buffer400 = read_vector_sample(inputs[["buffer400"]], layers$buffer400, 5186, c("POLYGON", "MULTIPOLYGON")),
    building = read_vector_sample(inputs[["building"]], layers$building, 5186, c("POLYGON", "MULTIPOLYGON")),
    road_links = read_vector_sample(inputs[["road"]], layers$road_links, 5186, c("LINESTRING", "MULTILINESTRING")),
    road_nodes = read_vector_sample(inputs[["road"]], layers$road_nodes, 5186, "POINT"),
    poi = read_vector_sample(inputs[["poi"]], layers$poi, 5186, "POINT"),
    official_grid = read_vector_sample(inputs[["official_grid_shp"]], layers$official_grid, 5179, c("POLYGON", "MULTIPOLYGON"))
  )
  rasters <- list(
    landcover = raster_inventory(inputs[["landcover"]], 5186, buffer_bbox),
    dem = raster_inventory(inputs[["dem"]], 5186, buffer_bbox)
  )
  all_files <- lapply(names(inputs), function(role) list(
    role = role,
    path = inputs[[role]],
    size_bytes = unname(file.info(inputs[[role]])$size),
    sha256 = sha256_file(inputs[[role]])
  ))
  scientific <- list(
    inventory_schema_version = "1.0.0",
    status = "PASS",
    study_manifest_sha256 = sha256_file(inputs[["study_manifest"]]),
    study_manifest_contract_version = manifest$contract_version,
    files = all_files,
    vectors = vectors,
    rasters = rasters,
    spatial_checks = list(
      processing_epsg = 5186L,
      boundary_valid = TRUE,
      buffer_valid = TRUE,
      buffer_covers_boundary = TRUE,
      buffer_distance_m = 400,
      buffer_symmetric_difference_m2 = buffer_difference,
      rasters_cover_buffer = TRUE
    )
  )
  inventory_id <- short_hash_id("inp_", scientific)
  value <- c(list(inventory_id = inventory_id, generated_at = kst_now()), scientific)
  final_dir <- file.path(config$paths$outputs$scene_root, "input_contracts", inventory_id)
  publish_bundle(final_dir, "study_data_inventory.json", function(stage) {
    write_json_file(value, file.path(stage, "study_data_inventory.json"))
  })
}

validate_methodology_contract_list <- function(contract) {
  required <- c(
    "contract_schema_version", "contract_id", "scientific_hash", "input_contract",
    "crs", "scene", "off_grid", "retrieval", "randomness", "identifiers",
    "modes", "implementation"
  )
  missing <- setdiff(required, names(contract))
  if (length(missing)) stop("Methodology contract missing fields: ", paste(missing, collapse = ", "), call. = FALSE)
  fixed <- list(
    processing_epsg = c(contract$crs$processing_epsg, 5186),
    official_grid_epsg = c(contract$crs$official_grid_epsg, 5179),
    width_m = c(contract$scene$width_m, 500),
    validation_count = c(contract$off_grid$validation_count, 300),
    evaluation_count = c(contract$off_grid$evaluation_count, 700),
    query_count = c(contract$retrieval$query_count, 10),
    candidate_count = c(contract$retrieval$unrestricted_candidate_count, 699)
  )
  invalid <- names(fixed)[vapply(fixed, function(pair) !identical(as.numeric(pair[[1L]]), as.numeric(pair[[2L]])), logical(1L))]
  if (length(invalid)) stop("Methodology contract fixed-value mismatch: ", paste(invalid, collapse = ", "), call. = FALSE)
  invisible(TRUE)
}

validate_json_schema_file <- function(json_file, schema_file) {
  executable <- Sys.which("check-jsonschema")
  if (nzchar(executable)) {
    command <- executable
    arguments <- c("--schemafile", shQuote(schema_file), shQuote(json_file))
  } else {
    command <- Sys.which("python")
    if (!nzchar(command)) stop("JSON Schema validation requires check-jsonschema or Python", call. = FALSE)
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

build_methodology_contract <- function(study_data_inputs, study_data_inventory,
                                       accepted_off_grid_source, research_config_files,
                                       research_implementation_files,
                                       workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- capture_native_thread_state()
  on.exit(restore_native_thread_state(state), add = TRUE)
  set_native_thread_limits(threads)
  config <- load_research_config(research_config_files)
  inventory <- jsonlite::read_json(study_data_inventory, simplifyVector = FALSE)
  scene <- config$scene
  root <- config$paths$repository$root
  implementation_files <- normalizePath(research_implementation_files, mustWork = TRUE)
  implementation <- lapply(implementation_files, function(path) list(
    path = path,
    sha256 = sha256_file(path)
  ))
  input_files <- lapply(seq_along(study_data_inputs), function(index) list(
    role = names(config$paths$inputs)[[index]],
    path = normalizePath(study_data_inputs[[index]], mustWork = TRUE),
    sha256 = sha256_file(study_data_inputs[[index]]),
    size_bytes = unname(file.info(study_data_inputs[[index]])$size)
  ))
  scientific <- list(
    contract_schema_version = scene$contract_schema_version,
    input_contract = list(
      inventory_id = inventory$inventory_id,
      study_manifest_sha256 = inventory$study_manifest_sha256,
      files = input_files
    ),
    crs = list(
      processing_epsg = as.integer(scene$crs$processing_epsg),
      official_grid_epsg = as.integer(scene$crs$official_grid_epsg),
      official_centers_transformed_to_processing_crs = TRUE,
      footprints_axis_aligned_in_processing_crs = TRUE
    ),
    scene = list(
      width_m = as.numeric(scene$scene$width_m),
      training_source = scene$scene$training_source,
      official_cell_id_column = scene$scene$official_cell_id_column,
      official_duplicate_policy = scene$scene$official_duplicate_policy,
      footprint_construction = scene$scene$footprint_construction,
      training_center_predicate = scene$scene$training_center_predicate,
      source_buffer_m = as.numeric(scene$scene$source_buffer_m),
      boundary_scene_footprint_preserved = TRUE,
      coordinate_precision_m = as.numeric(scene$scene$coordinate_precision_m)
    ),
    off_grid = list(
      validation_count = as.integer(scene$off_grid$validation_count),
      evaluation_count = as.integer(scene$off_grid$evaluation_count),
      minimum_training_center_distance_m = as.numeric(scene$off_grid$minimum_training_center_distance_m),
      selection = scene$off_grid$selection,
      selection_order = scene$off_grid$selection_order,
      preserve_source_split = isTRUE(scene$off_grid$preserve_source_split),
      source = list(
        scene_index_id = scene$off_grid$source$scene_index_id,
        files = lapply(accepted_off_grid_source, function(path) list(
          path = path, size_bytes = unname(file.info(path)$size), sha256 = sha256_file(path)
        ))
      )
    ),
    retrieval = list(
      query_count = as.integer(scene$retrieval$query_count),
      candidate_rule = "evaluation_scene_id_not_equal_query_scene_id",
      unrestricted_candidate_count = as.integer(scene$retrieval$unrestricted_candidate_count),
      include_other_queries = isTRUE(scene$retrieval$include_other_queries),
      non_local_minimum_distance_m = as.numeric(scene$retrieval$non_local_minimum_distance_m)
    ),
    randomness = list(
      rng_kind = scene$randomness$rng_kind,
      normal_kind = scene$randomness$normal_kind,
      sample_kind = scene$randomness$sample_kind,
      retrieval_query_seed = as.integer(scene$retrieval$query_seed),
      prototype_seed = as.integer(scene$prototype$seed),
      deterministic_draw_order = TRUE
    ),
    identifiers = list(
      scene_id = "scn_ + SHA256(scene_schema_version|split|center_x_5186_mm|center_y_5186_mm)[1:24]",
      scene_footprint_id = "fpt_ + SHA256(scene_schema_version|EPSG:5186|xmin_mm|ymin_mm|xmax_mm|ymax_mm)[1:24]",
      independent_of_input_and_parallel_order = TRUE
    ),
    modes = list(
      production = list(scene_index = "all approved training/validation/evaluation scenes"),
      prototype = list(
        selection_from_production_index = TRUE,
        counts = scene$prototype$counts,
        proxy_definition = scene$prototype$proxy_definition
      )
    ),
    implementation = list(
      config_sha256 = config$config_sha256,
      config_files = lapply(config$config_files, function(path) list(path = path, sha256 = sha256_file(path))),
      source_files = implementation
    )
  )
  scientific_hash <- canonical_sha256(scientific)
  contract_id <- paste0("mth_", substr(scientific_hash, 1L, 24L))
  contract <- c(
    list(
      contract_schema_version = scene$contract_schema_version,
      contract_id = contract_id,
      scientific_hash = scientific_hash,
      created_at = kst_now()
    ),
    scientific[setdiff(names(scientific), "contract_schema_version")]
  )
  validate_methodology_contract_list(contract)
  final_dir <- file.path(config$paths$outputs$scene_root, "contracts", contract_id)
  outputs <- publish_bundle(
    final_dir,
    c("methodology_contract.json", "methodology_provenance.json"),
    function(stage) {
      contract_path <- write_json_file(contract, file.path(stage, "methodology_contract.json"))
      validate_json_schema_file(contract_path, config$schema_file)
      thesis <- config$paths$repository$thesis_template
      pdf <- file.path(thesis, "main.pdf")
      provenance <- list(
        provenance_schema_version = "1.0.0",
        record_only = TRUE,
        excluded_from_scientific_hash = TRUE,
        recorded_at = kst_now(),
        contract_id = contract_id,
        thesis_git_commit = trimws(system2("git", c("-C", shQuote(dirname(thesis)), "rev-parse", "HEAD"), stdout = TRUE)),
        thesis_git_dirty = length(system2("git", c("-C", shQuote(dirname(thesis)), "status", "--porcelain"), stdout = TRUE)) > 0L,
        thesis_pdf_path = normalizePath(pdf, mustWork = TRUE),
        thesis_pdf_sha256 = sha256_file(pdf),
        thesis_pdf_mtime = format(file.info(pdf)$mtime, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul")
      )
      write_json_file(provenance, file.path(stage, "methodology_provenance.json"))
    }
  )
  outputs
}

artifact_path <- function(paths, basename_required) {
  found <- paths[basename(paths) == basename_required]
  if (length(found) != 1L) stop("Expected one artifact named ", basename_required, call. = FALSE)
  found[[1L]]
}
