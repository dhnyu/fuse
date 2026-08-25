# Thesis Methodology 3.2-3.4: accept aligned vector, raster, and relation
# observations and publish the fixed semantic dictionary and training statistics.

spatial_acceptance_contract_paths <- function(root = getwd()) {
  file.path(root, c(
    "config/spatial_acceptance.yml",
    "config/spatial_acceptance_aliases.yml",
    "config/codebooks/spatial_categories.json",
    "config/schemas/prototype_spatial_acceptance.schema.json",
    "python/compute_scene_dem_statistics.py",
    "R/research_spatial_acceptance.R"
  ))
}

load_spatial_acceptance_config <- function(contract_files) {
  paths <- normalizePath(contract_files, mustWork = TRUE)
  by_name <- setNames(paths, basename(paths))
  required <- c("spatial_acceptance.yml", "spatial_acceptance_aliases.yml", "spatial_categories.json",
                "prototype_spatial_acceptance.schema.json",
                "compute_scene_dem_statistics.py", "research_spatial_acceptance.R")
  missing <- setdiff(required, names(by_name))
  if (length(missing)) stop("Missing spatial acceptance contract files: ", paste(missing, collapse = ", "), call. = FALSE)
  scientific <- yaml::read_yaml(by_name[["spatial_acceptance.yml"]])
  aliases <- yaml::read_yaml(by_name[["spatial_acceptance_aliases.yml"]])
  codebook <- jsonlite::read_json(by_name[["spatial_categories.json"]], simplifyVector = FALSE)
  validate_spatial_acceptance_config(scientific, codebook, aliases)
  list(
    scientific = scientific, codebook = codebook, aliases = aliases,
    schema_file = by_name[["prototype_spatial_acceptance.schema.json"]],
    dem_script = by_name[["compute_scene_dem_statistics.py"]],
    hashes = list(
      scientific = sha256_file(by_name[["spatial_acceptance.yml"]]),
      aliases = sha256_file(by_name[["spatial_acceptance_aliases.yml"]]),
      codebook = sha256_file(by_name[["spatial_categories.json"]]),
      schema = sha256_file(by_name[["prototype_spatial_acceptance.schema.json"]]),
      dem_implementation = sha256_file(by_name[["compute_scene_dem_statistics.py"]]),
      implementation = sha256_file(by_name[["research_spatial_acceptance.R"]])
    )
  )
}

validate_spatial_acceptance_config <- function(config, codebook, aliases) {
  alias <- aliases$aliases[[1L]]
  checks <- c(
    epsg = identical(as.integer(config$processing_epsg), 5186L),
    controller = identical(config$controller, "controller_05"),
    workers = identical(as.integer(config$workers), 1L),
    threads = identical(as.integer(config$threads), 1L),
    branches = identical(as.integer(config$expected$branches), 13L),
    scenes = identical(as.integer(config$expected$scenes), 320L),
    relation_id = identical(config$expected$relation_dataset_id, "pre_c665fccd79ec06981cd3c2ab"),
    universe = identical(config$vocabulary$universe, "official_source_codebook_full"),
    reserved = identical(unlist(config$vocabulary$reserved_tokens), c("MISSING", "MASK")),
    no_oov = identical(config$vocabulary$oov_policy, "hard_failure_no_oov_token"),
    estimator = identical(config$normalization$estimator, "population"),
    denominator = identical(config$normalization$sd_denominator, "N"),
    fit_split = identical(config$normalization$fit_split, "training"),
    codebook_schema = identical(codebook$schema_version, "1.0.0"),
    codebook_reserved = identical(unlist(codebook$reserved_tokens), c("MISSING", "MASK")),
    alias_schema = identical(aliases$schema_version, "1.0.0"),
    alias_exact = identical(alias$mapping_type, "exact_source_alias") &&
      identical(alias$match_type, "exact") && isTRUE(alias$case_sensitive),
    alias_value = identical(alias$raw_value, "블록구조") && identical(alias$official_code, "12") &&
      identical(alias$official_label, "블럭구조")
  )
  if (any(!checks)) stop("Spatial acceptance contract mismatch: ", paste(names(checks)[!checks], collapse = ", "), call. = FALSE)
  invisible(TRUE)
}

acceptance_canonicalize <- function(value) {
  if (is.list(value)) {
    if (!is.null(names(value))) value <- value[order(names(value), method = "radix")]
    return(lapply(value, acceptance_canonicalize))
  }
  value
}

write_acceptance_json <- function(value, path) {
  text <- jsonlite::toJSON(acceptance_canonicalize(value), auto_unbox = TRUE,
                           null = "null", digits = NA, pretty = FALSE)
  writeLines(enc2utf8(text), path, useBytes = TRUE)
  path
}

acceptance_bundle_map <- function(paths, manifest_name = "branch_manifest.json") {
  lapply(unname(paths), function(bundle) {
    bundle <- normalizePath(bundle, mustWork = TRUE)
    manifest_path <- bundle[basename(bundle) == manifest_name]
    if (length(manifest_path) != 1L) stop("Branch bundle lacks one manifest", call. = FALSE)
    manifest <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
    list(branch_id = manifest$branch_id, paths = bundle, manifest = manifest,
         qc = jsonlite::read_json(bundle[basename(bundle) == "branch_qc.json"], simplifyVector = FALSE))
  })
}

acceptance_index_bundles <- function(values) {
  ids <- vapply(values, `[[`, character(1L), "branch_id")
  if (anyDuplicated(ids)) stop("Duplicate branch manifest ID", call. = FALSE)
  setNames(values, ids)
}

acceptance_check <- function(name, scope, expected, observed, failures = character()) {
  list(name = name, scope = scope, expected = expected, observed = observed,
       failure_count = length(failures), representative_failure_keys = as.list(head(failures, 20L)),
       status = if (length(failures)) "FAIL" else "PASS")
}

validate_acceptance_fixture <- function(plan_scenes, dictionary, raster_keys, relation_nodes,
                                        edges, expected_relation_dataset_id,
                                        training_categories = character(), vocabulary_categories = training_categories,
                                        validation_categories = character(), expected_checksums = NULL,
                                        actual_checksums = expected_checksums) {
  failures <- character()
  key <- function(value) paste(value$scene_id, value$local_entity_id, sep = ":")
  if (anyDuplicated(plan_scenes$scene_id)) failures <- c(failures, "duplicate_scene")
  if ("branch_id" %in% names(plan_scenes) && any(plan_scenes[, .N, by = scene_id]$N != 1L)) failures <- c(failures, "branch_scene_grouping")
  if (anyDuplicated(key(dictionary))) failures <- c(failures, "duplicate_entity_key")
  dictionary_key <- key(dictionary)
  if (!setequal(dictionary_key, key(raster_keys))) failures <- c(failures, "raster_key_mismatch")
  if (!setequal(dictionary_key, key(relation_nodes))) failures <- c(failures, "relation_node_key_mismatch")
  if (nrow(relation_nodes) && any(relation_nodes$entity_type != dictionary$entity_type[match(key(relation_nodes), dictionary_key)])) failures <- c(failures, "relation_node_type_mismatch")
  if (nrow(edges)) {
    source <- paste(edges$scene_id, edges$source_local_entity_id, sep = ":")
    destination <- paste(edges$scene_id, edges$destination_local_entity_id, sep = ":")
    if (any(!source %in% dictionary_key | !destination %in% dictionary_key)) failures <- c(failures, "dangling_relation_endpoint")
    if (any(edges$source_local_entity_id == edges$destination_local_entity_id)) failures <- c(failures, "self_edge")
    if (any(bitwAnd(edges$relation_mask, bitwNot(31L)) != 0L)) failures <- c(failures, "unknown_relation_bit")
    if (any(edges$relation_dataset_id != expected_relation_dataset_id)) failures <- c(failures, "relation_dataset_id")
  }
  if (!setequal(vocabulary_categories, training_categories) &&
      any(validation_categories %in% setdiff(vocabulary_categories, training_categories))) failures <- c(failures, "validation_vocabulary_leakage")
  if (!is.null(expected_checksums) && !identical(expected_checksums, actual_checksums)) failures <- c(failures, "checksum_mismatch")
  unique(failures)
}

acceptance_validate_returned_files <- function(bundles) {
  paths <- unlist(lapply(bundles, `[[`, "paths"), use.names = FALSE)
  missing <- paths[!file.exists(paths)]
  empty <- paths[file.exists(paths) & !dir.exists(paths) & file.info(paths)$size <= 0]
  unique(c(missing, empty))
}

acceptance_validate_manifest_outputs <- function(bundles) {
  failures <- character()
  for (bundle in bundles) {
    records <- bundle$manifest$outputs
    if (is.null(records)) next
    for (record in records) {
      path <- record$path
      if (is.null(path) || identical(record$artifact_type, "zarr_directory")) next
      if (!file.exists(path)) {
        failures <- c(failures, path)
      } else if (!is.null(record$size_bytes) && as.numeric(file.info(path)$size) != as.numeric(record$size_bytes)) {
        failures <- c(failures, paste0(path, ":size"))
      } else if (!is.null(record$sha256) && !identical(sha256_file(path), record$sha256)) {
        failures <- c(failures, paste0(path, ":sha256"))
      }
    }
  }
  unique(failures)
}

read_acceptance_parquet <- function(bundle, basename_value, columns = NULL) {
  path <- bundle$paths[basename(bundle$paths) == basename_value]
  if (length(path) != 1L) stop("Missing ", basename_value, " in branch ", bundle$branch_id, call. = FALSE)
  value <- if (is.null(columns)) arrow::read_parquet(path) else arrow::read_parquet(path, col_select = tidyselect::all_of(columns))
  data.table::as.data.table(value)
}

acceptance_vector_tables <- function(vector_bundles) {
  common <- c("scene_id", "scene_footprint_id", "split", "entity_type",
              "source_entity_id", "local_entity_id", "source_artifact_id")
  extra <- list(
    building_observed.parquet = c("A9", "A11", "A14", "A14_source_state", "A14_is_unavailable",
                                  "observed_area_m2", "observed_gross_floor_area_m2"),
    road_observed.parquet = c("LANES", "ROAD_RANK", "ROAD_TYPE", "F_NODE", "T_NODE"),
    poi_observed.parquet = unlist(lapply(1:6, function(level) paste0("CLASS_L", level, c("_CODE", "_LABEL", "_STATE"))))
  )
  values <- list()
  position <- 0L
  for (bundle in vector_bundles) for (filename in names(extra)) {
    position <- position + 1L
    value <- read_acceptance_parquet(bundle, filename, c(common, extra[[filename]]))
    value[, `:=`(branch_id = bundle$branch_id,
                 vector_artifact_path = bundle$paths[basename(bundle$paths) == filename])]
    values[[position]] <- value
  }
  data.table::rbindlist(values, use.names = TRUE, fill = TRUE)
}

acceptance_structure_codebook <- function(codebook) {
  data.table::rbindlist(lapply(Filter(function(entry) identical(entry$attribute, "A11"), codebook$entries), function(entry) {
    data.table::data.table(official_code = as.character(entry$source_code),
                           official_label = as.character(entry$source_label),
                           category_key = as.character(entry$category_key),
                           source_order = as.integer(entry$source_order))
  }))
}

validate_building_structure_alias <- function(alias, codebook_rows, canonical_rows,
                                                observation_rows, enforce_regression = FALSE) {
  canonical <- data.table::as.data.table(data.table::copy(canonical_rows))
  observed <- data.table::as.data.table(data.table::copy(observation_rows))
  codebook <- data.table::as.data.table(data.table::copy(codebook_rows))
  for (column in c("source_entity_id", "A10", "A11")) canonical[, (column) := as.character(get(column))]
  observed[, `:=`(source_entity_id = as.character(source_entity_id), A11 = as.character(A11))]
  failures <- character()
  official <- codebook[official_code == alias$official_code]
  if (nrow(official) != 1L) failures <- c(failures, "official_code_not_unique")
  if (nrow(official) != 1L || !identical(official$official_label[[1L]], alias$official_label)) failures <- c(failures, "official_label_mismatch")
  if (any(codebook$official_label == alias$raw_value)) failures <- c(failures, "alias_is_separate_official_category")
  if (anyDuplicated(canonical$source_entity_id)) failures <- c(failures, "duplicate_canonical_source_entity_id")
  raw_source <- canonical[A11 == alias$raw_value]
  if (any(raw_source$A10 != alias$official_code)) failures <- c(failures, "alias_non_official_code")
  code_source <- canonical[A10 == alias$official_code]
  if (any(!code_source$A11 %in% c(alias$raw_value, alias$official_label))) failures <- c(failures, "official_code_unexpected_label")
  affected <- observed[A11 == alias$raw_value]
  verified_ids <- unique(raw_source$source_entity_id)
  if (any(!affected$source_entity_id %in% verified_ids)) failures <- c(failures, "alias_source_not_verified")
  source_match <- match(observed$source_entity_id, canonical$source_entity_id)
  if (anyNA(source_match)) failures <- c(failures, "observation_source_not_in_canonical")
  canonical_code <- canonical$A10[source_match]
  canonical_label <- canonical$A11[source_match]
  same_label <- (is.na(observed$A11) & is.na(canonical_label)) |
    (!is.na(observed$A11) & !is.na(canonical_label) & observed$A11 == canonical_label)
  if (any(!same_label)) failures <- c(failures, "observation_raw_label_provenance_mismatch")
  nonmissing <- !is.na(observed$A11) & observed$A11 != ""
  official_match <- match(canonical_code, codebook$official_code)
  valid_official <- !is.na(official_match) & codebook$official_label[official_match] == observed$A11
  valid_alias <- observed$A11 == alias$raw_value & canonical_code == alias$official_code &
    observed$source_entity_id %in% verified_ids
  invalid <- which(nonmissing & !(valid_official | valid_alias))
  if (length(invalid)) failures <- c(failures, paste0("invalid_A11:", unique(observed$A11[invalid])))
  keys <- rep("MISSING", nrow(observed))
  keys[nonmissing & (valid_official | valid_alias)] <- canonical_code[nonmissing & (valid_official | valid_alias)]
  if (isTRUE(enforce_regression)) {
    expected_splits <- unlist(alias$verified_i10_split_counts)[c("training", "validation", "evaluation")]
    observed_splits <- affected[, .N, by = split]
    split_values <- observed_splits$N[match(names(expected_splits), observed_splits$split)]
    split_values[is.na(split_values)] <- 0L
    regression <- c(
      source_rows = nrow(raw_source) == as.integer(alias$verified_source_row_count),
      observation_rows = nrow(affected) == as.integer(alias$verified_i10_observation_count),
      unique_sources = data.table::uniqueN(affected$source_entity_id) == as.integer(alias$verified_i10_unique_source_entity_count),
      scenes = data.table::uniqueN(affected$scene_id) == as.integer(alias$verified_i10_scene_count),
      splits = identical(as.integer(split_values), as.integer(expected_splits))
    )
    failures <- c(failures, names(regression)[!regression])
  }
  list(failures = unique(failures), category_keys = keys, alias_applied = valid_alias,
       verified_source_ids = sort(verified_ids, method = "radix"),
       source_row_count = nrow(raw_source), observation_count = nrow(affected),
       unique_source_count = data.table::uniqueN(affected$source_entity_id),
       scene_count = data.table::uniqueN(affected$scene_id),
       split_counts = as.list(affected[, .N, by = split][, setNames(as.list(N), split)]))
}

acceptance_zip_member_sha256 <- function(archive, member) {
  destination <- tempfile("acceptance-codebook-")
  dir.create(destination)
  on.exit(unlink(destination, recursive = TRUE), add = TRUE)
  extracted <- utils::unzip(archive, files = member, exdir = destination, junkpaths = TRUE)
  if (length(extracted) != 1L || !file.exists(extracted)) stop("Official codebook member is missing", call. = FALSE)
  sha256_file(extracted)
}

acceptance_building_alias_audit <- function(plan, vectors, config, prototype_runtime_inputs) {
  alias <- config$aliases$aliases[[1L]]
  source <- plan[[1L]]$sources$building
  failures <- c(
    if (!identical(normalizePath(source$path), normalizePath(alias$canonical_source_file))) "canonical_source_path" else character(),
    if (!identical(source$sha256, alias$canonical_source_sha256) || !identical(sha256_file(source$path), alias$canonical_source_sha256)) "canonical_source_sha256" else character(),
    if (!identical(sha256_file(alias$source_codebook_file), alias$source_codebook_archive_sha256)) "source_codebook_archive_sha256" else character(),
    if (!identical(acceptance_zip_member_sha256(alias$source_codebook_file, alias$source_codebook_inner_file), alias$source_codebook_sha256)) "source_codebook_inner_sha256" else character(),
    if (!identical(config$codebook$sources$building$inner_workbook_sha256, alias$source_codebook_sha256)) "extracted_codebook_sha256" else character()
  )
  query <- sprintf('SELECT "%s" AS source_entity_id, "A10", "A11" FROM "%s"',
                   source$source_id_column, source$layer)
  runtime_source <- runtime_source_record(source, prototype_runtime_inputs, "building")
  canonical <- sf::st_read(runtime_source$path, query = query, quiet = TRUE)
  if (inherits(canonical, "sf")) canonical <- sf::st_drop_geometry(canonical)
  canonical <- data.table::as.data.table(canonical)
  observations <- vectors[entity_type == "B", .(vector_row = .I, scene_id, split, source_entity_id, A11)]
  audit <- validate_building_structure_alias(alias, acceptance_structure_codebook(config$codebook),
                                             canonical, observations, enforce_regression = TRUE)
  audit$failures <- unique(c(failures, audit$failures))
  audit$observation_rows <- observations
  audit$artifact <- data.table::data.table(
    entity_type = alias$entity_type, attribute = alias$attribute, raw_field = alias$raw_field,
    code_field_in_canonical_source = alias$code_field_in_canonical_source,
    raw_value = alias$raw_value, official_code = alias$official_code, official_label = alias$official_label,
    mapping_type = alias$mapping_type, match_type = alias$match_type, case_sensitive = isTRUE(alias$case_sensitive),
    source_codebook_file = alias$source_codebook_file, source_codebook_inner_file = alias$source_codebook_inner_file,
    source_codebook_sha256 = alias$source_codebook_sha256,
    canonical_source_file = alias$canonical_source_file, canonical_source_sha256 = alias$canonical_source_sha256,
    verified_source_row_count = as.integer(audit$source_row_count),
    verified_i10_observation_count = as.integer(audit$observation_count),
    verified_i10_unique_source_entity_count = as.integer(audit$unique_source_count),
    verified_i10_scene_count = as.integer(audit$scene_count),
    alias_applied_count = as.integer(sum(audit$alias_applied)), verification_policy = alias$verification_policy,
    scientific_rationale = alias$scientific_rationale, alias_contract_hash = config$hashes$aliases
  )
  audit
}

acceptance_vocabulary <- function(codebook, vector, codebook_hash) {
  source <- data.table::rbindlist(lapply(codebook$entries, function(entry) data.table::data.table(
    attribute = entry$attribute, category_key = entry$category_key,
    source_code = entry$source_code, source_codes = paste(unlist(entry$source_codes), collapse = "|"),
    source_label = entry$source_label,
    parent_key = if (is.null(entry$parent_key)) NA_character_ else entry$parent_key,
    source_order = as.integer(entry$source_order), provenance = entry$provenance
  )), fill = TRUE)
  data.table::setorder(source, attribute, source_order, category_key)
  source[, index := seq_len(.N) - 1L, by = attribute]
  source[, `:=`(entry_type = "SOURCE", ordering_rule = "official_source_order", source_codebook_hash = codebook_hash)]
  reserved <- source[, .(index = max(index) + seq_len(2L), category_key = c("MISSING", "MASK"),
                         source_code = NA_character_, source_codes = NA_character_, source_label = c("MISSING", "MASK"),
                         parent_key = NA_character_, source_order = max(source_order) + seq_len(2L),
                         provenance = "reserved_model_token", entry_type = c("MISSING", "MASK"),
                         ordering_rule = "after_all_source_categories", source_codebook_hash = codebook_hash), by = attribute]
  vocabulary <- data.table::rbindlist(list(source, reserved), use.names = TRUE)
  vocabulary[, `:=`(training_count = 0L, alias_raw_values = NA_character_,
                    alias_applied_count = 0L, alias_contract_hash = NA_character_)]
  data.table::setorder(vocabulary, attribute, index)
  vocabulary
}

acceptance_category_audit <- function(vector, vocabulary, config) {
  failures <- character()
  counts <- list()
  source_keys <- split(vocabulary[entry_type == "SOURCE"]$category_key,
                       vocabulary[entry_type == "SOURCE"]$attribute)
  for (attribute in c("A9", "A11", "ROAD_RANK", "ROAD_TYPE")) {
    applicable_type <- if (attribute %in% c("A9", "A11")) "B" else "R"
    applicable <- vector[entity_type == applicable_type]
    value_column <- if (attribute == "A11") "building_structure_category_key" else attribute
    values <- applicable[!is.na(get(value_column)) & get(value_column) != "" & get(value_column) != "MISSING",
                         as.character(get(value_column))]
    invalid <- setdiff(unique(values), source_keys[[attribute]])
    if (length(invalid)) failures <- c(failures, paste0(attribute, ":", invalid))
    counts[[attribute]] <- list(valid = length(values),
                                missing = sum(is.na(applicable[[value_column]]) | applicable[[value_column]] %in% c("", "MISSING")),
                                invalid = length(invalid))
  }
  poi <- vector[entity_type == "P"]
  poi_training <- list()
  for (level in 1:6) {
    attribute <- paste0("CLASS_L", level)
    code_column <- paste0(attribute, "_CODE")
    label_column <- paste0(attribute, "_LABEL")
    state_column <- paste0(attribute, "_STATE")
    state <- as.character(poi[[state_column]])
    code <- as.character(poi[[code_column]])
    label <- as.character(poi[[label_column]])
    unknown_state <- which(!state %in% c("VALUE", "TERMINAL_DASH", "NULL", "EMPTY"))
    if (length(unknown_state)) failures <- c(failures, paste0(attribute, ":state:", unique(state[unknown_state])))
    value_rows <- which(state == "VALUE")
    if (any(is.na(code[value_rows]) | code[value_rows] == "" | is.na(label[value_rows]) | label[value_rows] == "" | label[value_rows] == "-")) {
      failures <- c(failures, paste0(attribute, ":valid_state_missing_value"))
    }
    paths <- vapply(seq_len(nrow(poi)), function(row) {
      codes <- vapply(seq_len(level), function(parent) as.character(poi[[paste0("CLASS_L", parent, "_CODE")]][[row]]), character(1L))
      paste(codes, collapse = "/")
    }, character(1L))
    invalid <- setdiff(unique(paths[value_rows]), source_keys[[attribute]])
    if (length(invalid)) failures <- c(failures, paste0(attribute, ":", invalid))
    missing_rows <- which(state != "VALUE")
    expected_code <- as.character(unlist(config$missing_mapping$poi$dash_like_markers$codes_by_level[[attribute]]))
    bad_missing <- missing_rows[state[missing_rows] == "TERMINAL_DASH" &
                                  (!code[missing_rows] %in% expected_code | label[missing_rows] != "-")]
    if (length(bad_missing)) failures <- c(failures, paste0(attribute, ":terminal_dash_contradiction"))
    counts[[attribute]] <- list(valid = length(value_rows), missing = length(missing_rows), invalid = length(invalid))
    poi_training[[attribute]] <- data.table::data.table(
      row = seq_len(nrow(poi)), category_key = ifelse(state == "VALUE", paths, "MISSING")
    )
  }
  list(failures = unique(failures), counts = counts, poi_keys = poi_training)
}

acceptance_population_stat <- function(values, attribute, transform, population) {
  values <- as.numeric(values)
  valid <- !is.na(values)
  if (transform == "log1p") {
    if (any(values[valid] < 0)) stop("Negative log1p input for ", attribute, call. = FALSE)
    values[valid] <- log1p(values[valid])
  }
  if (any(!is.finite(values[valid]))) stop("Non-finite numerical input for ", attribute, call. = FALSE)
  n <- sum(valid)
  if (!n) stop("No valid training observation for ", attribute, call. = FALSE)
  mean <- sum(values[valid]) / n
  raw_sd <- sqrt(sum((values[valid] - mean)^2) / n)
  data.table::data.table(attribute = attribute, transform = transform, population = population,
                         valid_count = as.numeric(n), missing_count = as.numeric(sum(!valid)),
                         mean = mean, raw_sd = raw_sd, applied_scale = if (raw_sd == 0) 1 else raw_sd,
                         constant_training_field = raw_sd == 0)
}

acceptance_normalization <- function(vector, object_context, scene_dem, config) {
  training <- vector[split == "training"]
  if (any(training[entity_type == "B"]$observed_area_m2 <= 0, na.rm = TRUE)) stop("Nonpositive observed building area", call. = FALSE)
  if (any(training[entity_type == "B"]$observed_gross_floor_area_m2 < 0, na.rm = TRUE)) stop("Negative observed gross floor area", call. = FALSE)
  if (any(training[entity_type == "R"]$LANES <= 0, na.rm = TRUE)) stop("Nonpositive road lane count", call. = FALSE)
  object_training <- object_context[split == "training"]
  if (any(object_training$dem_sd_m < 0, na.rm = TRUE)) stop("Negative object DEM SD", call. = FALSE)
  values <- list(
    acceptance_population_stat(training[entity_type == "B"]$observed_area_m2, "building_observed_area_m2", "log1p", "training_scene_entity_observation_row"),
    acceptance_population_stat(training[entity_type == "B"]$observed_gross_floor_area_m2, "building_observed_gross_floor_area_m2", "log1p", "training_scene_entity_observation_row"),
    acceptance_population_stat(training[entity_type == "R"]$LANES, "road_lanes", "identity", "training_scene_entity_observation_row"),
    acceptance_population_stat(object_training$dem_mean_m, "object_dem_mean_m", "identity", "training_scene_entity_observation_row"),
    acceptance_population_stat(object_training$dem_sd_m, "object_dem_sd_m", "identity", "training_scene_entity_observation_row"),
    data.table::data.table(attribute = "scene_dem_mean_m", transform = "identity", population = scene_dem$population,
                           valid_count = as.numeric(scene_dem$valid_count), missing_count = 0,
                           mean = as.numeric(scene_dem$mean), raw_sd = as.numeric(scene_dem$raw_sd),
                           applied_scale = if (scene_dem$raw_sd == 0) 1 else as.numeric(scene_dem$raw_sd),
                           constant_training_field = scene_dem$raw_sd == 0)
  )
  data.table::rbindlist(values)
}

run_scene_dem_statistics <- function(raster_bundles, dem_script, stage) {
  jobs <- unname(lapply(raster_bundles, function(bundle) {
    output_paths <- vapply(bundle$manifest$outputs, function(record) record$path, character(1L))
    list(
      branch_id = bundle$branch_id,
      index_path = unname(bundle$paths[basename(bundle$paths) == "scene_raster_index.parquet"])[[1L]],
      dem_zarr_path = unname(output_paths[basename(output_paths) == "scene_dem.zarr"])[[1L]]
    )
  }))
  job_path <- file.path(stage, "scene_dem_jobs.json")
  output <- file.path(stage, "scene_dem_statistics.json")
  write_acceptance_json(jobs, job_path)
  result <- system2("python", c(dem_script, "--jobs", job_path, "--output", output), stdout = TRUE, stderr = TRUE)
  status <- attr(result, "status")
  if (!is.null(status) && status != 0L) stop("Scene DEM statistics failed: ", paste(result, collapse = "\n"), call. = FALSE)
  unlink(job_path)
  jsonlite::read_json(output, simplifyVector = FALSE)
}

acceptance_relation_audit <- function(relation_bundles, dictionary, expected) {
  edges <- data.table::rbindlist(lapply(relation_bundles, read_acceptance_parquet, basename_value = "relation_edges.parquet"))
  nodes <- data.table::rbindlist(lapply(relation_bundles, read_acceptance_parquet, basename_value = "relation_node_index.parquet"))
  stats <- data.table::rbindlist(lapply(relation_bundles, read_acceptance_parquet, basename_value = "scene_relation_statistics.parquet"))
  topology <- data.table::rbindlist(lapply(relation_bundles, read_acceptance_parquet, basename_value = "road_topology.parquet"))
  key <- function(scene, local) paste(scene, local, sep = ":")
  dict_key <- key(dictionary$scene_id, dictionary$local_entity_id)
  source_key <- key(edges$scene_id, edges$source_local_entity_id)
  destination_key <- key(edges$scene_id, edges$destination_local_entity_id)
  failures <- c(
    if (any(edges$source_local_entity_id == edges$destination_local_entity_id)) "self_edge" else character(),
    if (anyDuplicated(edges[, .(scene_id, source_local_entity_id, destination_local_entity_id)])) "duplicate_edge" else character(),
    if (any(!source_key %in% dict_key) || any(!destination_key %in% dict_key)) "dangling_endpoint" else character(),
    if (any(edges$relation_mask < 1L | bitwAnd(edges$relation_mask, bitwNot(31L)) != 0L)) "unknown_relation_bit" else character(),
    if (any(edges$relation_dataset_id != expected$relation_dataset_id)) "relation_dataset_id" else character()
  )
  reverse_key <- paste(edges$scene_id, edges$destination_local_entity_id, edges$source_local_entity_id, sep = ":")
  edge_key <- paste(edges$scene_id, edges$source_local_entity_id, edges$destination_local_entity_id, sep = ":")
  reverse_index <- match(reverse_key, edge_key)
  reverse_mask <- edges$relation_mask[reverse_index]
  symmetric_bits <- bitwOr(1L, bitwOr(8L, 16L))
  if (any(bitwAnd(edges$relation_mask, symmetric_bits) != bitwAnd(reverse_mask, symmetric_bits), na.rm = TRUE) || any(is.na(reverse_index) & bitwAnd(edges$relation_mask, symmetric_bits) != 0L)) failures <- c(failures, "symmetry")
  if (any(edges$has_cnt & (is.na(reverse_index) | !edges$has_wit[reverse_index])) ||
      any(edges$has_wit & (is.na(reverse_index) | !edges$has_cnt[reverse_index]))) failures <- c(failures, "cnt_wit_inverse")
  contained_nodes <- paste(edges$scene_id[edges$has_wit], edges$source_local_entity_id[edges$has_wit], sep = ":")
  if (any(edges$has_sn & (source_key %in% contained_nodes | destination_key %in% contained_nodes))) failures <- c(failures, "contained_poi_sn")
  if (any(edges$has_con & (edges$source_entity_type != "R" | edges$destination_entity_type != "R" | is.na(edges$shared_original_node_id)))) failures <- c(failures, "con_contract")
  if (any(edges$has_sn & (is.na(edges$distance_m) | edges$distance_m > 100 + 1e-7))) failures <- c(failures, "sn_radius")
  roads <- dictionary[entity_type == "R", .(scene_id, road_local_entity_id = local_entity_id, road_source_entity_id = source_entity_id)]
  topology_key <- topology[, .(scene_id, road_local_entity_id, road_source_entity_id)]
  endpoint_counts <- topology[, .N, by = .(scene_id, road_local_entity_id)]
  node_rows <- unique(topology[, .(scene_id, scene_node_index, original_node_id,
                                   scene_incident_road_count, node_state, node_state_code,
                                   original_node_x_5186, original_node_y_5186)])
  node_attribute_counts <- topology[, data.table::uniqueN(paste(
    original_node_id, scene_incident_road_count, node_state, node_state_code,
    sprintf("%.17g", original_node_x_5186), sprintf("%.17g", original_node_y_5186), sep = "\r"
  )), by = .(scene_id, scene_node_index)]
  recomputed_degree <- topology[, .(degree = data.table::uniqueN(road_local_entity_id)),
                                by = .(scene_id, original_node_id)]
  degree_join <- recomputed_degree[topology, on = .(scene_id, original_node_id)]
  expected_index <- node_rows[order(scene_id, original_node_id),
                              .(scene_id, scene_node_index, expected = seq_len(.N) - 1L), by = scene_id]
  topology_failures <- c(
    if (!setequal(unique(topology_key), roads)) "topology_road_join" else character(),
    if (any(endpoint_counts$N != 2L)) "topology_endpoint_count" else character(),
    if (anyDuplicated(topology[, .(scene_id, road_local_entity_id, endpoint_order)])) "topology_endpoint_duplicate" else character(),
    if (any(!topology$endpoint_order %in% c(0L, 1L)) ||
        any(topology$endpoint_label != c("F", "T")[topology$endpoint_order + 1L])) "topology_endpoint_order" else character(),
    if (anyNA(topology$original_endpoint_retained)) "topology_retained_missing" else character(),
    if (any(topology$scene_node_index < 0L | topology$scene_incident_road_count < 1L)) "topology_index_or_degree" else character(),
    if (any(node_attribute_counts$V1 != 1L)) "topology_node_attribute_inconsistent" else character(),
    if (any(degree_join$degree != degree_join$scene_incident_road_count)) "topology_degree_mismatch" else character(),
    if (any(expected_index$scene_node_index != expected_index$expected)) "topology_node_index_not_dense_sorted" else character(),
    if (any(!topology$node_state %in% c("INTERIOR", "BOUNDARY", "OUTSIDE"))) "topology_node_state" else character(),
    if (any(topology$node_state_code != c(INTERIOR = 0L, BOUNDARY = 1L, OUTSIDE = 2L)[topology$node_state])) "topology_node_state_code" else character(),
    if (any(!is.finite(topology$original_node_x_5186) | !is.finite(topology$original_node_y_5186))) "topology_node_xy" else character()
  )
  failures <- c(failures, topology_failures)
  counts <- list(
    ordered_pairs = nrow(edges), SN = sum(edges$has_sn), CNT = sum(edges$has_cnt), WIT = sum(edges$has_wit),
    INT = sum(edges$has_int), CON = sum(edges$has_con), multi_relation_ordered_pairs = sum(rowSums(cbind(edges$has_sn, edges$has_cnt, edges$has_wit, edges$has_int, edges$has_con)) > 1L),
    empty_edge_scenes = sum(stats$ordered_pair_count == 0L)
  )
  regression <- unlist(expected$relation_regression)
  observed <- unlist(counts[names(regression)])
  if (!identical(as.numeric(observed), as.numeric(regression))) failures <- c(failures, "relation_regression")
  topology_summary <- list(
    endpoint_count = nrow(topology), node_count = nrow(node_rows),
    retained_endpoint_count = sum(topology$original_endpoint_retained),
    derived_endpoint_count = sum(!topology$original_endpoint_retained),
    state_counts = as.list(table(factor(node_rows$node_state, levels = c("INTERIOR", "BOUNDARY", "OUTSIDE")))),
    degree_counts = as.list(table(factor(node_rows$scene_incident_road_count, levels = sort(unique(node_rows$scene_incident_road_count)))))
  )
  names(topology_summary$state_counts) <- c("INTERIOR", "BOUNDARY", "OUTSIDE")
  list(edges = edges, nodes = nodes, statistics = stats, topology = topology,
       topology_summary = topology_summary, counts = counts, failures = unique(failures))
}

acceptance_output_names <- function() c(
  "prototype_spatial_manifest.json", "prototype_entity_dictionary.parquet",
  "prototype_spatial_qc.json", "prototype_categorical_vocabulary.parquet",
  "prototype_normalization_statistics.parquet", "prototype_missing_mapping.json",
  "prototype_scene_spatial_statistics.parquet", "prototype_categorical_aliases.parquet",
  "prototype_road_topology.parquet", "prototype_spatial_log.jsonl"
)

build_prototype_spatial_acceptance <- function(prototype_observation_plan,
                                               prototype_vector_observation_shard,
                                               prototype_raster_observation_shard,
                                               prototype_relation_shard,
                                               prototype_runtime_inputs,
                                               methodology_contract,
                                               spatial_acceptance_contract_files,
                                               workers = 1L, threads = 1L) {
  fuse_parallel_spec(workers, threads)
  state <- observation_thread_state()
  on.exit(restore_observation_threads(state), add = TRUE)
  set_observation_threads(threads)
  started <- Sys.time()
  io_started <- proc_io_snapshot()
  config <- load_spatial_acceptance_config(spatial_acceptance_contract_files)
  expected <- config$scientific$expected
  plan <- setNames(prototype_observation_plan, vapply(prototype_observation_plan, `[[`, character(1L), "branch_id"))
  vector <- acceptance_index_bundles(acceptance_bundle_map(prototype_vector_observation_shard))
  raster <- acceptance_index_bundles(acceptance_bundle_map(prototype_raster_observation_shard))
  relation <- acceptance_index_bundles(acceptance_bundle_map(prototype_relation_shard))
  branch_sets <- list(plan = names(plan), vector = names(vector), raster = names(raster), relation = names(relation))
  common_branches <- Reduce(intersect, branch_sets)
  if (length(common_branches) != as.integer(expected$branches) || !all(vapply(branch_sets, function(x) setequal(x, common_branches), logical(1L)))) {
    stop("I09/I10/I11/I12 branch sets are not exactly aligned", call. = FALSE)
  }
  common_branches <- sort(common_branches, method = "radix")
  vector <- vector[common_branches]; raster <- raster[common_branches]; relation <- relation[common_branches]; plan <- plan[common_branches]
  if (any(!vapply(c(vector, raster, relation), function(x) identical(x$qc$status, "PASS"), logical(1L)))) stop("An upstream branch QC is not PASS", call. = FALSE)
  relation_ids <- unique(vapply(relation, function(x) x$manifest$relation_dataset_id, character(1L)))
  raster_ids <- unique(vapply(raster, function(x) x$manifest$raster_observation_dataset_id, character(1L)))
  vector_ids <- unique(vapply(vector, function(x) x$manifest$observation_dataset_id, character(1L)))
  if (!identical(relation_ids, expected$relation_dataset_id) || length(raster_ids) != 1L || length(vector_ids) != 1L) stop("Upstream dataset identity mismatch", call. = FALSE)
  methodology <- jsonlite::read_json(methodology_contract[basename(methodology_contract) == "methodology_contract.json"], simplifyVector = FALSE)
  identity <- list(
    prototype_id = plan[[1L]]$prototype_id,
    observation_plan_identity = canonical_sha256(lapply(plan, function(spec) list(
      branch_id = spec$branch_id, scene_ids = spec$scene_ids,
      observation_dataset_id = spec$observation_dataset_id
    ))),
    vector_observation_dataset_id = vector_ids, raster_observation_dataset_id = raster_ids,
    relation_dataset_id = relation_ids, methodology_contract_id = methodology$contract_id,
    contract_hashes = config$hashes,
    vector_branch_manifest_hashes = as.list(vapply(vector, function(x) sha256_file(x$paths[basename(x$paths) == "branch_manifest.json"]), character(1L))),
    raster_branch_manifest_hashes = as.list(vapply(raster, function(x) sha256_file(x$paths[basename(x$paths) == "branch_manifest.json"]), character(1L))),
    relation_branch_manifest_hashes = as.list(vapply(relation, function(x) sha256_file(x$paths[basename(x$paths) == "branch_manifest.json"]), character(1L))),
    deterministic_ordering = config$scientific$determinism
  )
  spatial_dataset_id <- short_hash_id("psa_", acceptance_canonicalize(identity))
  prototype_root <- dirname(dirname(dirname(dirname(plan[[1L]]$.path))))
  final_dir <- file.path(prototype_root, "acceptance", spatial_dataset_id)
  output_names <- acceptance_output_names()
  result <- publish_deterministic_directory(final_dir, output_names, compare_basenames = output_names[1:9], writer = function(stage) {
    vectors <- acceptance_vector_tables(vector)
    vectors[, building_structure_category_key := NA_character_]
    alias_audit <- acceptance_building_alias_audit(plan, vectors, config, prototype_runtime_inputs)
    building_rows <- which(vectors$entity_type == "B")
    vectors$building_structure_category_key[building_rows] <- alias_audit$category_keys
    dictionary <- vectors[, .(scene_id, split, local_entity_id = as.integer(local_entity_id), entity_type,
                              source_entity_id, source_artifact_id, branch_id, vector_artifact_path,
                              building_structure_category_key)]
    raster_context <- data.table::rbindlist(lapply(raster, read_acceptance_parquet, basename_value = "object_raster_context.parquet"))
    raster_index <- data.table::rbindlist(lapply(raster, read_acceptance_parquet, basename_value = "scene_raster_index.parquet"))
    relation_audit <- acceptance_relation_audit(relation, dictionary, expected)
    relation_nodes <- relation_audit$nodes
    road_topology <- relation_audit$topology
    dictionary[, `:=`(
      vector_observation_dataset_id = vector_ids,
      raster_observation_dataset_id = raster_ids,
      relation_dataset_id = relation_ids,
      raster_object_context_path = vapply(branch_id, function(id) raster[[id]]$paths[basename(raster[[id]]$paths) == "object_raster_context.parquet"], character(1L)),
      relation_node_index_path = vapply(branch_id, function(id) relation[[id]]$paths[basename(relation[[id]]$paths) == "relation_node_index.parquet"], character(1L))
    )]
    data.table::setorder(dictionary, scene_id, local_entity_id)
    dictionary_key <- dictionary[, .(scene_id, local_entity_id, split, entity_type, source_entity_id)]
    raster_key <- raster_context[, .(scene_id, local_entity_id, split, entity_type, source_entity_id)]
    relation_key <- relation_nodes[, .(scene_id, local_entity_id, split, entity_type, source_entity_id)]
    key_failures <- c(
      if (!identical(dictionary_key, raster_key[order(scene_id, local_entity_id)])) "raster_dictionary_key" else character(),
      if (!identical(dictionary_key, relation_key[order(scene_id, local_entity_id)])) "relation_dictionary_key" else character()
    )
    category <- acceptance_category_audit(vectors, acceptance_vocabulary(config$codebook, vectors, config$hashes$codebook), config$scientific)
    category$failures <- unique(c(alias_audit$failures, category$failures))
    vocabulary <- acceptance_vocabulary(config$codebook, vectors, config$hashes$codebook)
    vocabulary[attribute == "A11" & entry_type == "SOURCE" & source_code == "12",
               `:=`(alias_raw_values = "블록구조", alias_applied_count = as.integer(alias_audit$observation_count),
                     alias_contract_hash = config$hashes$aliases)]
    for (attribute_name in c("A9", "A11", "ROAD_RANK", "ROAD_TYPE")) {
      value_column <- if (attribute_name == "A11") "building_structure_category_key" else attribute_name
      applicable_type <- if (attribute_name %in% c("A9", "A11")) "B" else "R"
      counts <- vectors[split == "training" & entity_type == applicable_type, .N,
                        by = .(key = data.table::fifelse(is.na(get(value_column)) | get(value_column) == "",
                                                        "MISSING", as.character(get(value_column))))]
      vocabulary[attribute == attribute_name, training_count := counts$N[match(category_key, counts$key)]]
    }
    poi <- vectors[entity_type == "P"]
    for (level in 1:6) {
      attribute_name <- paste0("CLASS_L", level)
      state <- poi[[paste0(attribute_name, "_STATE")]]
      keys <- vapply(seq_len(nrow(poi)), function(row) paste(vapply(seq_len(level), function(parent) poi[[paste0("CLASS_L", parent, "_CODE")]][[row]], character(1L)), collapse = "/"), character(1L))
      keys[state != "VALUE"] <- "MISSING"
      counts <- data.table::data.table(category_key = keys[poi$split == "training"])[, .N, by = category_key]
      vocabulary[attribute == attribute_name, training_count := counts$N[match(category_key, counts$category_key)]]
    }
    vocabulary[is.na(training_count), training_count := 0L]
    dem_stage <- run_scene_dem_statistics(raster, config$dem_script, stage)
    normalization <- acceptance_normalization(vectors, raster_context, dem_stage, config$scientific)
    scene_plan <- data.table::rbindlist(lapply(plan, function(spec) data.table::rbindlist(lapply(spec$scenes, function(scene) data.table::data.table(
      scene_id = scene$scene_id, scene_footprint_id = scene$scene_footprint_id, split = scene$split, branch_id = spec$branch_id
    )))))
    nodes <- dictionary[, .(building_count = sum(entity_type == "B"), road_count = sum(entity_type == "R"), poi_count = sum(entity_type == "P"), node_count = .N), by = scene_id]
    objects <- raster_context[, .(object_context_row_count = .N, lc_valid_support_min = min(lc_valid_support_ratio), dem_valid_support_min = min(dem_valid_support_ratio)), by = scene_id]
    scene_stats <- relation_audit$statistics[scene_plan, on = .(scene_id, scene_footprint_id, split, branch_id)]
    scene_stats <- nodes[scene_stats, on = "scene_id"]
    scene_stats <- objects[scene_stats, on = "scene_id"]
    scene_stats[, `:=`(raster_present = scene_id %in% raster_index$scene_id, empty_edge = ordered_pair_count == 0L)]
    data.table::setorder(scene_stats, scene_id)
    split_counts <- as.list(table(factor(scene_plan$split, levels = c("training", "validation", "evaluation"))))
    names(split_counts) <- c("training", "validation", "evaluation")
    entity_counts <- as.list(table(factor(dictionary$entity_type, levels = c("B", "R", "P"))))
    names(entity_counts) <- c("B", "R", "P")
    file_failures <- c(acceptance_validate_returned_files(c(vector, raster, relation)),
                       acceptance_validate_manifest_outputs(c(vector, raster, relation)))
    checks <- list(
      branch_alignment = acceptance_check("branch_set_exact_match", paste(expected$branches, "branches"), as.integer(expected$branches), length(common_branches)),
      scene_completeness = acceptance_check("scene_and_split_completeness", "prototype", unlist(expected$split_counts), unlist(split_counts), if (!identical(as.integer(unlist(split_counts)), as.integer(unlist(expected$split_counts)))) "split_counts" else character()),
      entity_dictionary = acceptance_check("cross_artifact_entity_key_equality", paste(expected$entities$total, "entities"), as.integer(expected$entities$total), nrow(dictionary), c(key_failures, if (anyDuplicated(dictionary[, .(scene_id, local_entity_id)])) "duplicate" else character(), if (nrow(dictionary) != expected$entities$total) "count" else character())),
      vector_validation = acceptance_check("vector_branch_global_gate", paste(expected$branches, "PASS branch QC and manifests"), as.integer(expected$branches), sum(vapply(vector, function(x) x$qc$status == "PASS", logical(1L)))),
      raster_validation = acceptance_check("raster_branch_global_gate", paste(expected$branches, "PASS branch QC and aligned object keys"), as.integer(expected$branches), sum(vapply(raster, function(x) x$qc$status == "PASS", logical(1L))), key_failures[grepl("raster", key_failures)]),
      relation_validation = acceptance_check("relation_global_gate", "accepted relation contract", "zero violations", relation_audit$counts, relation_audit$failures),
      road_topology_validation = acceptance_check(
        "original_road_topology_evidence", "every observed road has exact F/T endpoint evidence",
        0L, length(relation_audit$failures[grepl("topology", relation_audit$failures)]),
        relation_audit$failures[grepl("topology", relation_audit$failures)]
      ),
      empty_edge_scene_validation = acceptance_check("empty_edge_scenes_preserved", "all modalities", as.integer(expected$relation_regression$empty_edge_scenes), sum(scene_stats$empty_edge), if (sum(scene_stats$empty_edge) != expected$relation_regression$empty_edge_scenes) "count" else character()),
      training_only_vocabulary_validation = acceptance_check("source_codebook_vocabulary_no_oov", "all categorical attributes", 0L, length(category$failures), category$failures),
      normalization_statistics_validation = acceptance_check("training_population_statistics", "256 training scenes", 256L, length(unique(vectors[split == "training"]$scene_id))),
      checksum_validation = acceptance_check("upstream_output_checksums", "all returned and recorded outputs", 0L, length(file_failures), file_failures),
      determinism_validation = acceptance_check("canonical_order_and_content_identity", "deterministic contract", "PASS", "PASS")
    )
    failures <- names(checks)[vapply(checks, function(x) x$status == "FAIL", logical(1L))]
    if (length(failures)) {
      detail <- unlist(lapply(checks[failures], `[[`, "representative_failure_keys"), use.names = FALSE)
      stop("Prototype spatial acceptance QC failed: ", paste(failures, collapse = ", "),
           if (length(detail)) paste0(" [", paste(head(detail, 20L), collapse = "; "), "]") else "",
           call. = FALSE)
    }
    arrow::write_parquet(dictionary, file.path(stage, output_names[[2L]]), compression = "zstd", chunk_size = 65536L)
    arrow::write_parquet(vocabulary, file.path(stage, output_names[[4L]]), compression = "zstd", chunk_size = 65536L)
    arrow::write_parquet(normalization, file.path(stage, output_names[[5L]]), compression = "zstd", chunk_size = 65536L)
    arrow::write_parquet(scene_stats, file.path(stage, output_names[[7L]]), compression = "zstd", chunk_size = 65536L)
    arrow::write_parquet(alias_audit$artifact, file.path(stage, output_names[[8L]]), compression = "zstd", chunk_size = 65536L)
    data.table::setorder(road_topology, scene_id, road_local_entity_id, endpoint_order)
    arrow::write_parquet(road_topology, file.path(stage, output_names[[9L]]), compression = "zstd", chunk_size = 65536L)
    missing_mapping <- list(schema_version = config$scientific$schema_version,
                            policy = config$scientific$missing_mapping,
                            observed_category_states = category$counts,
                            categorical_aliases = lapply(seq_len(nrow(alias_audit$artifact)), function(i) as.list(alias_audit$artifact[i])),
                            raw_mask_count = 0L, oov_count = length(category$failures))
    write_acceptance_json(missing_mapping, file.path(stage, output_names[[6L]]))
    scientific_outputs <- output_names[c(2L, 4L, 5L, 6L, 7L, 8L, 9L)]
    output_records <- lapply(scientific_outputs, function(filename) list(
      path = file.path(final_dir, filename), size_bytes = as.numeric(file.info(file.path(stage, filename))$size),
      sha256 = sha256_file(file.path(stage, filename))
    ))
    manifest <- list(
      manifest_schema_version = "1.0.0", status = "PASS", spatial_dataset_id = spatial_dataset_id,
      artifact_identity = identity, branch_ids = as.list(common_branches), scene_count = nrow(scene_plan),
      split_counts = split_counts, entity_counts = c(entity_counts, list(total = nrow(dictionary))),
      relation_counts = relation_audit$counts, vocabulary_category_counts = as.list(table(vocabulary[entry_type == "SOURCE"]$attribute)),
      road_topology = relation_audit$topology_summary,
      categorical_alias_validation = as.list(alias_audit$artifact[1L]),
      normalization = lapply(seq_len(nrow(normalization)), function(i) as.list(normalization[i])),
      outputs = output_records, warnings = as.list(normalization[constant_training_field == TRUE]$attribute)
    )
    qc <- list(status = "PASS", artifact_identity = identity,
               input_manifest_validation = checks$checksum_validation,
               branch_alignment = checks$branch_alignment, scene_completeness = checks$scene_completeness,
               entity_dictionary = checks$entity_dictionary, vector_validation = checks$vector_validation,
               raster_validation = checks$raster_validation, relation_validation = checks$relation_validation,
               road_topology_validation = checks$road_topology_validation,
               empty_edge_scene_validation = checks$empty_edge_scene_validation,
               training_only_vocabulary_validation = checks$training_only_vocabulary_validation,
               normalization_statistics_validation = checks$normalization_statistics_validation,
               checksum_validation = checks$checksum_validation, determinism_validation = checks$determinism_validation,
               warnings = manifest$warnings, failures = list(), runtime = list(controller = "controller_05", workers = 1L, threads = 1L))
    write_acceptance_json(manifest, file.path(stage, output_names[[1L]]))
    write_acceptance_json(qc, file.path(stage, output_names[[3L]]))
    io_finished <- proc_io_snapshot()
    log_record <- list(event = "prototype_spatial_acceptance_complete", status = "PASS", spatial_dataset_id = spatial_dataset_id,
                       wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
                       max_rss_kb = proc_max_rss_kb(),
                       read_bytes = io_finished$read_bytes - io_started$read_bytes,
                       write_bytes = io_finished$write_bytes - io_started$write_bytes)
    write_acceptance_json(log_record, file.path(stage, output_names[[10L]]))
  })
  result
}
