# P11 living-population rematerialization: dissertation downstream methodology.

p11_living_v2_read_config <- function(path = "config/p11_downstream_preprocessing_v2.yml") {
  cfg <- yaml::read_yaml(path)
  required <- c("status", "dissertation_authority", "methodology_decision",
                "scene_index", "output_root", "previous_dataset_root", "sources",
                "contracts", "source_inventory_sha256", "living_population", "execution")
  if (!all(required %in% names(cfg)) ||
      !identical(cfg$status, "AUTHORIZED_FOR_LIVING_REMATERIALIZATION")) {
    stop("P11 living-population rematerialization is not authorized", call. = FALSE)
  }
  cfg
}

p11_living_v2_validate_authority <- function(cfg) {
  authority <- jsonlite::read_json(cfg$dissertation_authority, simplifyVector = FALSE)
  methodology <- jsonlite::read_json(cfg$methodology_decision, simplifyVector = FALSE)
  contract <- jsonlite::read_json(cfg$contracts$living_population, simplifyVector = FALSE)
  expected <- list(
    authority = "disauth_60a514578f57b9397ce71ee6",
    dissertation = "4adbd49b6dacab589d2fa99d88ec5be83aceb287",
    methodology = "p11meth_42070c9b832c232a6e989d25",
    contract = "p11src_ff2f5bb24376968aedfdfecc",
    old_dataset = "p11ds_fdb1f34c6daeda259e803e37"
  )
  checks <- c(
    identical(authority$authority_id, expected$authority),
    identical(authority$dissertation$commit, expected$dissertation),
    identical(methodology$decision_id, expected$methodology),
    identical(methodology$dissertation_authority_id, expected$authority),
    identical(contract$contract_id, expected$contract),
    identical(contract$methodology_authority$methodology_decision_id, expected$methodology),
    identical(basename(cfg$previous_dataset_root), expected$old_dataset),
    identical(cfg$living_population$minimum_valid_scene_hours, 1L),
    identical(cfg$living_population$extrapolate_missing_spatial_support, FALSE)
  )
  retired <- grepl("90 percent|complete explicitly present", methodology$coverage_rules$living_temporal) ||
    grepl("complete explicitly present", methodology$coverage_rules$living_spatial)
  if (!all(checks) || retired) stop("P11 v2 living-population authority mismatch", call. = FALSE)
  list(authority = authority, methodology = methodology, contract = contract, expected = expected)
}

p11_living_v2_group_rows <- function(raw, expected_date, source_ids) {
  raw <- data.table::as.data.table(raw)
  required <- c("date", "hour", "admin_id", "source_id", "released_value")
  if (!all(required %in% names(raw))) stop("Living-population row schema mismatch", call. = FALSE)
  raw <- raw[source_id %chin% source_ids]
  raw[, hour := suppressWarnings(as.integer(hour))]
  if (nrow(raw) && (any(raw$date != expected_date) || anyNA(raw$hour) ||
                    any(raw$hour < 0L | raw$hour > 23L))) {
    stop("Living-population date/hour mismatch", call. = FALSE)
  }
  raw[, numeric_value := suppressWarnings(as.numeric(released_value))]
  grouped <- raw[, {
    usable <- is.finite(numeric_value) & numeric_value >= 0
    valid <- all(usable)
    reason <- if (valid) NA_character_ else if (any(!is.finite(numeric_value))) {
      "SUPPRESSED_OR_NONNUMERIC_COMPONENT"
    } else {
      "NEGATIVE_COMPONENT"
    }
    list(
      value = if (valid) sum(numeric_value) else NA_real_,
      raw_row_count = .N,
      contributing_admin_row_count = sum(usable),
      duplicate_count = .N - 1L,
      valid = valid,
      missing_reason = reason
    )
  }, .(source_id, date, hour)]
  if (grouped[, anyDuplicated(paste(source_id, date, hour))]) {
    stop("Duplicate living grid-hour after aggregation", call. = FALSE)
  }
  data.table::setorder(grouped, source_id, date, hour)
  grouped
}

p11_living_v2_full_universe <- function(grouped, source_ids, expected_date) {
  universe <- data.table::CJ(
    source_id = sort(unique(source_ids), method = "radix"),
    hour = 0:23,
    sorted = TRUE
  )
  universe[, date := expected_date]
  universe[grouped, `:=`(
    value = i.value,
    raw_row_count = i.raw_row_count,
    contributing_admin_row_count = i.contributing_admin_row_count,
    duplicate_count = i.duplicate_count,
    valid = i.valid,
    missing_reason = i.missing_reason
  ), on = .(source_id, date, hour)]
  universe[is.na(raw_row_count), `:=`(
    raw_row_count = 0L,
    contributing_admin_row_count = 0L,
    duplicate_count = 0L,
    valid = FALSE,
    missing_reason = "MISSING_SOURCE_ROW"
  )]
  data.table::setcolorder(universe, c(
    "date", "hour", "source_id", "value", "raw_row_count",
    "contributing_admin_row_count", "duplicate_count", "valid", "missing_reason"
  ))
  data.table::setorder(universe, date, hour, source_id)
  universe
}

p11_living_v2_scene_hours <- function(universe, overlap, tolerance = 1e-9) {
  joined <- merge(overlap, universe, by = "source_id", allow.cartesian = TRUE, sort = FALSE)
  hourly <- joined[, .(
    response = if (any(valid)) sum(value[valid] * intersection_area[valid] / source_area[valid]) else NA_real_,
    total_expected_source_area = sum(intersection_area),
    valid_observed_source_area = sum(intersection_area[valid]),
    expected_grid_count = .N,
    valid_grid_count = sum(valid),
    unavailable_grid_count = sum(!valid),
    missing_source_row_count = sum(missing_reason == "MISSING_SOURCE_ROW", na.rm = TRUE),
    invalid_component_group_count = sum(!valid & missing_reason != "MISSING_SOURCE_ROW"),
    raw_row_count = sum(raw_row_count),
    contributing_admin_row_count = sum(contributing_admin_row_count),
    duplicate_count = sum(duplicate_count)
  ), .(scene_id, date, hour)]
  if (any(abs(hourly$total_expected_source_area - 250000) > 1e-4)) {
    stop("Full living grid-hour universe does not cover the 500 m scene", call. = FALSE)
  }
  hourly[, `:=`(
    unavailable_source_area = total_expected_source_area - valid_observed_source_area,
    spatial_support_fraction = valid_observed_source_area / total_expected_source_area,
    valid_scene_hour = valid_observed_source_area > tolerance,
    temporal_class = p11_temporal_class(date, hour)
  )]
  hourly[valid_scene_hour == FALSE, response := NA_real_]
  data.table::setorder(hourly, scene_id, date, hour)
  hourly
}

p11_living_v2_process_day <- function(path, overlap, grid_hour_dir, scene_hour_dir,
                                      tolerance = 1e-9) {
  expected_date <- sub("^250_LOCAL_RESD_([0-9]{8})[.]csv$", "\\1", basename(path))
  if (!grepl("^[0-9]{8}$", expected_date)) stop("Unexpected living-population filename", call. = FALSE)
  raw <- data.table::fread(path, select = 1:5, colClasses = "character", encoding = "unknown")
  data.table::setnames(raw, c("date", "hour", "admin_id", "source_id", "released_value"))
  raw[, source_id := p11_decode_cp949(source_id)]
  source_ids <- unique(overlap$source_id)
  grouped <- p11_living_v2_group_rows(raw, expected_date, source_ids)
  universe <- p11_living_v2_full_universe(grouped, source_ids, expected_date)
  hourly <- p11_living_v2_scene_hours(universe, overlap, tolerance)
  grid_path <- file.path(grid_hour_dir, paste0(expected_date, ".parquet"))
  scene_path <- file.path(scene_hour_dir, paste0(expected_date, ".parquet"))
  arrow::write_parquet(universe, grid_path, compression = "zstd")
  arrow::write_parquet(hourly, scene_path, compression = "zstd")
  list(
    date = expected_date,
    grid_artifact = file.path("grid_hour_diagnostics", basename(grid_path)),
    scene_artifact = file.path("scene_hour_coverage", basename(scene_path)),
    raw_rows = sum(universe$raw_row_count),
    duplicate_rows = sum(universe$duplicate_count),
    valid_grid_hours = sum(universe$valid),
    invalid_grid_hours = sum(!universe$valid),
    usable_scene_hours = sum(hourly$valid_scene_hour)
  )
}

p11_living_v2_temporal_targets <- function(scene_hour_dir, scene_ids) {
  paths <- sort(list.files(scene_hour_dir, pattern = "[.]parquet$", full.names = TRUE), method = "radix")
  if (length(paths) != 365L) stop("Living scene-hour shard count mismatch", call. = FALSE)
  con <- DBI::dbConnect(duckdb::duckdb())
  on.exit(DBI::dbDisconnect(con, shutdown = TRUE), add = TRUE)
  DBI::dbExecute(con, "SET threads = 1")
  glob <- gsub("'", "''", file.path(scene_hour_dir, "*.parquet"), fixed = TRUE)
  query <- sprintf(
    paste(
      "SELECT scene_id, temporal_class AS target,",
      "avg(response) FILTER (WHERE valid_scene_hour) AS response,",
      "sum(CASE WHEN valid_scene_hour THEN 1 ELSE 0 END)::BIGINT AS valid_hour_count,",
      "avg(spatial_support_fraction) FILTER (WHERE valid_scene_hour) AS mean_spatial_support_fraction,",
      "median(spatial_support_fraction) FILTER (WHERE valid_scene_hour) AS median_spatial_support_fraction,",
      "min(spatial_support_fraction) FILTER (WHERE valid_scene_hour) AS minimum_spatial_support_fraction,",
      "max(spatial_support_fraction) FILTER (WHERE valid_scene_hour) AS maximum_spatial_support_fraction,",
      "sum(missing_source_row_count)::BIGINT AS missing_source_grid_hour_count,",
      "sum(invalid_component_group_count)::BIGINT AS invalid_component_grid_hour_count,",
      "sum(raw_row_count)::BIGINT AS raw_row_count,",
      "sum(contributing_admin_row_count)::BIGINT AS contributing_admin_row_count,",
      "sum(duplicate_count)::BIGINT AS duplicate_count,",
      "sum(valid_grid_count)::BIGINT AS contributing_grid_count,",
      "sum(valid_observed_source_area) AS represented_source_area,",
      "sum(total_expected_source_area) AS total_source_area",
      "FROM read_parquet('%s') GROUP BY scene_id, temporal_class ORDER BY temporal_class, scene_id",
      sep = " "
    ), glob
  )
  result <- data.table::as.data.table(DBI::dbGetQuery(con, query))
  expected <- p11_expected_hours_2025()
  data.table::setnames(expected, "temporal_class", "target")
  universe <- data.table::CJ(
    target = expected$target,
    scene_id = sort(scene_ids, method = "radix"),
    sorted = TRUE
  )
  result <- merge(universe, result, by = c("target", "scene_id"), all.x = TRUE, sort = FALSE)
  result[is.na(valid_hour_count), valid_hour_count := 0L]
  result[expected, expected_count := i.expected_count, on = "target"]
  result[, `:=`(
    unavailable_hour_count = expected_count - valid_hour_count,
    valid_hour_fraction = valid_hour_count / expected_count,
    temporal_coverage = valid_hour_count / expected_count,
    spatial_coverage = mean_spatial_support_fraction,
    observed_count = valid_hour_count,
    eligible = valid_hour_count >= 1L,
    unit = "persons"
  )]
  result[eligible == FALSE, response := NA_real_]
  result[, missing_reason := data.table::fifelse(eligible, NA_character_, "ZERO_VALID_SCENE_HOURS")]
  numeric_zero <- c(
    "missing_source_grid_hour_count", "invalid_component_grid_hour_count", "raw_row_count",
    "contributing_admin_row_count", "duplicate_count", "contributing_grid_count",
    "represented_source_area", "total_source_area"
  )
  for (column in numeric_zero) result[is.na(get(column)), (column) := 0]
  data.table::setorder(result, target, scene_id)
  result
}

p11_living_v2_file_inventory <- function(root, exclude = character()) {
  paths <- list.files(root, recursive = TRUE, full.names = TRUE, all.files = TRUE, no.. = TRUE)
  paths <- paths[!dir.exists(paths)]
  relative <- substring(paths, nchar(normalizePath(root, mustWork = TRUE)) + 2L)
  keep <- !relative %in% exclude
  paths <- paths[keep]
  relative <- relative[keep]
  index <- order(enc2utf8(relative), method = "radix")
  lapply(index, function(i) list(
    logical_path = enc2utf8(relative[[i]]),
    byte_size = unname(file.info(paths[[i]])$size),
    sha256 = p11_sha256_file(paths[[i]])
  ))
}

p11_living_v2_validate_inventory <- function(root, records) {
  for (record in records) {
    path <- file.path(root, record$logical_path)
    if (!file.exists(path) || file.info(path)$size != record$byte_size ||
        !identical(p11_sha256_file(path), record$sha256)) {
      stop("Living-population shard corruption: ", record$logical_path, call. = FALSE)
    }
  }
  TRUE
}

p11_living_v2_publish_shard <- function(cfg, authorities, scene, overlap) {
  parent <- file.path(cfg$output_root, "living_population")
  dir.create(parent, recursive = TRUE, showWarnings = FALSE)
  stage <- tempfile(".p11lp-stage-", tmpdir = parent)
  dir.create(stage)
  on.exit(if (dir.exists(stage)) unlink(stage, recursive = TRUE), add = TRUE)
  grid_dir <- file.path(stage, "grid_hour_diagnostics")
  hour_dir <- file.path(stage, "scene_hour_coverage")
  dir.create(grid_dir)
  dir.create(hour_dir)
  files <- sort(Sys.glob(file.path(cfg$sources$living_population, "250_LOCAL_RESD_2025*.csv")), method = "radix")
  if (length(files) != 365L) stop("Living-population source must contain all 365 days", call. = FALSE)
  audits <- parallel::mclapply(
    files,
    p11_living_v2_process_day,
    overlap = overlap,
    grid_hour_dir = grid_dir,
    scene_hour_dir = hour_dir,
    tolerance = cfg$execution$numeric_tolerance,
    mc.cores = max(1L, as.integer(cfg$execution$workers)),
    mc.preschedule = TRUE
  )
  if (any(vapply(audits, inherits, logical(1L), what = "try-error"))) {
    stop("Living-population daily materialization failed", call. = FALSE)
  }
  targets <- p11_living_v2_temporal_targets(hour_dir, scene$scene_id)
  arrow::write_parquet(targets, file.path(stage, "living_population.parquet"), compression = "zstd")
  audit <- data.table::rbindlist(audits)
  data.table::setorder(audit, date)
  arrow::write_parquet(audit, file.path(stage, "daily_audit.parquet"), compression = "zstd")
  zero <- targets[eligible == FALSE, .(scene_id, target, missing_reason)]
  arrow::write_parquet(zero, file.path(stage, "zero_observation_scenes.parquet"), compression = "zstd")
  records <- p11_living_v2_file_inventory(stage)
  preimage <- list(
    schema_version = "1.0.0",
    artifact_type = "p11_living_population_partial_support_shard",
    dissertation_authority_id = authorities$expected$authority,
    methodology_decision_id = authorities$expected$methodology,
    source_contract_id = authorities$expected$contract,
    source_inventory_sha256 = cfg$source_inventory_sha256$living_population,
    scene_index_id = "rsi_80031f1493c75163f91b7c71",
    implementation_version = "p11-living-partial-support-v1",
    implementation_sha256 = p11_sha256_file("R/p11_living_population_rematerialization.R"),
    calendar = list(year = 2025L, timezone = "Asia/Seoul", expected_hours = p11_expected_hours_2025()),
    eligibility = "valid_scene_hour_count >= 1",
    file_inventory = records
  )
  identity <- p11_content_identity("p11lp_", preimage)
  manifest <- c(preimage, list(shard_id = identity$id, content_sha256 = identity$sha256, status = "ACCEPTED"))
  jsonlite::write_json(manifest, file.path(stage, "living_population_shard_acceptance.json"),
                       auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null", digits = NA)
  final <- file.path(parent, identity$id)
  if (dir.exists(final)) {
    existing <- jsonlite::read_json(file.path(final, "living_population_shard_acceptance.json"), simplifyVector = FALSE)
    if (!identical(existing$shard_id, identity$id) || !identical(existing$content_sha256, identity$sha256)) {
      stop("Living-population shard identity collision", call. = FALSE)
    }
    p11_living_v2_validate_inventory(final, existing$file_inventory)
    return(list(root = normalizePath(final), manifest = existing,
                targets = data.table::as.data.table(arrow::read_parquet(file.path(final, "living_population.parquet"))),
                created = FALSE))
  }
  if (!file.rename(stage, final)) stop("Atomic living-population shard publication failed", call. = FALSE)
  list(root = normalizePath(final), manifest = manifest, targets = targets, created = TRUE)
}

p11_living_v2_content_hash <- function(value) {
  value <- data.table::copy(data.table::as.data.table(value))
  data.table::setorder(value, target, scene_id)
  digest::digest(p11_canonical_json(as.data.frame(value)), algo = "sha256", serialize = FALSE)
}

p11_living_v2_assert_seven_target_equivalence <- function(old_root, new_values) {
  names <- c("sgis", "land_value", "ecostress")
  for (name in names) {
    old <- data.table::as.data.table(arrow::read_parquet(file.path(old_root, paste0(name, ".parquet"))))
    new <- data.table::as.data.table(new_values[[name]])
    data.table::setorder(old, target, scene_id)
    data.table::setorder(new, target, scene_id)
    if (!identical(old, new) || !identical(p11_living_v2_content_hash(old), p11_living_v2_content_hash(new))) {
      stop("Non-living P11 target changed: ", name, call. = FALSE)
    }
  }
  TRUE
}

p11_living_v2_publish_dataset <- function(cfg, authorities, shard) {
  old_root <- cfg$previous_dataset_root
  old_acceptance <- jsonlite::read_json(file.path(old_root, "downstream_dataset_acceptance.json"), simplifyVector = FALSE)
  if (!identical(old_acceptance$dataset_id, authorities$expected$old_dataset)) {
    stop("Historical P11 dataset identity mismatch", call. = FALSE)
  }
  families <- list(
    sgis = data.table::as.data.table(arrow::read_parquet(file.path(old_root, "sgis.parquet"))),
    living_population = data.table::as.data.table(shard$targets),
    land_value = data.table::as.data.table(arrow::read_parquet(file.path(old_root, "land_value.parquet"))),
    ecostress = data.table::as.data.table(arrow::read_parquet(file.path(old_root, "ecostress.parquet")))
  )
  p11_living_v2_assert_seven_target_equivalence(old_root, families)
  combined <- data.table::rbindlist(families, use.names = TRUE, fill = TRUE)
  data.table::setorder(combined, target, scene_id)
  p11_validate_targets(combined, unique(combined$scene_id))
  if (nrow(combined) != 17600L || data.table::uniqueN(combined$scene_id) != 1600L) {
    stop("P11 v2 dataset cardinality mismatch", call. = FALSE)
  }
  output_hashes <- lapply(families, p11_living_v2_content_hash)
  old_hashes <- old_acceptance$output_content_sha256
  if (!identical(output_hashes$sgis, old_hashes$sgis) ||
      !identical(output_hashes$land_value, old_hashes$land_value) ||
      !identical(output_hashes$ecostress, old_hashes$ecostress)) {
    stop("Seven-target content hash equivalence failed", call. = FALSE)
  }
  reused <- lapply(c("sgis.parquet", "land_value.parquet", "ecostress.parquet",
                     "sgis_source_acceptance.json", "land_value_source_acceptance.json",
                     "ecostress_source_acceptance.json"), function(name) list(
    basename = name,
    byte_size = unname(file.info(file.path(old_root, name))$size),
    sha256 = p11_sha256_file(file.path(old_root, name))
  ))
  preimage <- list(
    schema_version = "2.0.0",
    artifact_type = "p11_downstream_dataset_acceptance",
    implementation = list(
      version = "p11-living-partial-support-rematerialization-v1",
      implementation_sha256 = p11_sha256_file("R/p11_living_population_rematerialization.R")
    ),
    dissertation_authority_id = authorities$expected$authority,
    methodology_decision_id = authorities$expected$methodology,
    p10_acceptance_id = "p10acc_6e5071beee7616750dec7907",
    scene_index_id = "rsi_80031f1493c75163f91b7c71",
    supersedes = authorities$expected$old_dataset,
    supersession_reason = "living_population_methodology_authority_revision_to_partial_support",
    living_population_shard = list(
      shard_id = shard$manifest$shard_id,
      content_sha256 = shard$manifest$content_sha256
    ),
    source_inventory_sha256 = old_acceptance$source_inventory_sha256,
    source_contract_sha256 = list(
      sgis = old_acceptance$source_contract_sha256$sgis,
      living_population = p11_sha256_file(cfg$contracts$living_population),
      land_value = old_acceptance$source_contract_sha256$land_value,
      ecostress = old_acceptance$source_contract_sha256$ecostress
    ),
    output_content_sha256 = output_hashes,
    reused_artifacts = reused,
    target_count = 11L,
    scene_universe_count = 1600L
  )
  identity <- p11_content_identity("p11ds_", preimage)
  final <- file.path(cfg$output_root, identity$id)
  basenames <- c(
    "sgis.parquet", "living_population.parquet", "land_value.parquet", "ecostress.parquet",
    "sgis_source_acceptance.json", "living_population_source_acceptance.json",
    "land_value_source_acceptance.json", "ecostress_source_acceptance.json",
    "scene_targets.parquet", "target_eligibility.parquet", "coverage_summary.json",
    "supersession.json", "downstream_dataset_acceptance.json"
  )
  paths <- p11_publish_immutable_bundle(final, basenames, function(stage) {
    for (name in c("sgis.parquet", "land_value.parquet", "ecostress.parquet",
                   "sgis_source_acceptance.json", "land_value_source_acceptance.json",
                   "ecostress_source_acceptance.json")) {
      if (!file.copy(file.path(old_root, name), file.path(stage, name), copy.mode = TRUE)) {
        stop("Failed to reuse immutable P11 artifact: ", name, call. = FALSE)
      }
    }
    if (!file.copy(file.path(shard$root, "living_population.parquet"),
                   file.path(stage, "living_population.parquet"), copy.mode = TRUE)) {
      stop("Failed to bind living-population shard", call. = FALSE)
    }
    source_preimage <- list(
      schema_version = "2.0.0",
      artifact_type = "p11_source_acceptance",
      source_family = "living_population",
      contract_id = authorities$expected$contract,
      contract_sha256 = p11_sha256_file(cfg$contracts$living_population),
      source_inventory_sha256 = cfg$source_inventory_sha256$living_population,
      shard_id = shard$manifest$shard_id,
      status = "ACCEPTED"
    )
    source_identity <- p11_content_identity("p11sa_", source_preimage)
    jsonlite::write_json(c(source_preimage, list(
      acceptance_id = source_identity$id,
      content_sha256 = source_identity$sha256
    )), file.path(stage, "living_population_source_acceptance.json"),
    auto_unbox = TRUE, pretty = TRUE, null = "null", digits = NA)
    arrow::write_parquet(combined, file.path(stage, "scene_targets.parquet"), compression = "zstd")
    eligibility_columns <- setdiff(names(combined), c("response", "unit", "source_family"))
    arrow::write_parquet(combined[, ..eligibility_columns],
                         file.path(stage, "target_eligibility.parquet"), compression = "zstd")
    safe_summary <- function(x, fun) if (any(is.finite(x))) fun(x[is.finite(x)]) else NA_real_
    coverage <- combined[, .(
      scene_rows = .N,
      eligible_scenes = sum(eligible),
      ineligible_scenes = sum(!eligible),
      eligibility_percentage = 100 * mean(eligible),
      minimum_spatial_coverage = safe_summary(spatial_coverage, min),
      median_spatial_coverage = safe_summary(spatial_coverage, stats::median),
      maximum_spatial_coverage = safe_summary(spatial_coverage, max),
      minimum_temporal_coverage = safe_summary(temporal_coverage, min),
      median_temporal_coverage = safe_summary(temporal_coverage, stats::median),
      maximum_temporal_coverage = safe_summary(temporal_coverage, max)
    ), target]
    jsonlite::write_json(coverage, file.path(stage, "coverage_summary.json"),
                         auto_unbox = TRUE, pretty = TRUE, na = "null", digits = NA)
    jsonlite::write_json(list(
      supersedes = authorities$expected$old_dataset,
      reason = "living_population_methodology_authority_revision_to_partial_support",
      historical_dataset_mutated = FALSE
    ), file.path(stage, "supersession.json"), auto_unbox = TRUE, pretty = TRUE)
    artifacts <- lapply(setdiff(basenames, "downstream_dataset_acceptance.json"), function(name) list(
      role = sub("[.]parquet$|[.]json$", "", name),
      basename = name,
      byte_size = unname(file.info(file.path(stage, name))$size),
      sha256 = p11_sha256_file(file.path(stage, name))
    ))
    acceptance <- c(preimage, list(
      dataset_id = identity$id,
      content_sha256 = identity$sha256,
      status = "ACCEPTED",
      artifacts = artifacts
    ))
    jsonlite::write_json(acceptance, file.path(stage, "downstream_dataset_acceptance.json"),
                         auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null", digits = NA)
  })
  list(root = normalizePath(final), dataset_id = identity$id, content_sha256 = identity$sha256,
       paths = paths, acceptance = jsonlite::read_json(file.path(final, "downstream_dataset_acceptance.json"), simplifyVector = FALSE),
       combined = combined)
}

p11_living_v2_validate_dataset <- function(root, old_root) {
  acceptance <- jsonlite::read_json(file.path(root, "downstream_dataset_acceptance.json"), simplifyVector = FALSE)
  keys <- c(
    "schema_version", "artifact_type", "implementation", "dissertation_authority_id",
    "methodology_decision_id", "p10_acceptance_id", "scene_index_id", "supersedes",
    "supersession_reason", "living_population_shard", "source_inventory_sha256",
    "source_contract_sha256", "output_content_sha256", "reused_artifacts",
    "target_count", "scene_universe_count"
  )
  identity <- p11_content_identity("p11ds_", acceptance[keys])
  if (!identical(identity$id, acceptance$dataset_id) || !identical(identity$sha256, acceptance$content_sha256)) {
    stop("P11 v2 dataset identity mismatch", call. = FALSE)
  }
  for (artifact in acceptance$artifacts) {
    path <- file.path(root, artifact$basename)
    if (!file.exists(path) || file.info(path)$size != artifact$byte_size ||
        !identical(p11_sha256_file(path), artifact$sha256)) {
      stop("P11 v2 dataset corruption: ", artifact$basename, call. = FALSE)
    }
  }
  for (name in c("sgis.parquet", "land_value.parquet", "ecostress.parquet",
                 "sgis_source_acceptance.json", "land_value_source_acceptance.json",
                 "ecostress_source_acceptance.json")) {
    if (!identical(p11_sha256_file(file.path(root, name)), p11_sha256_file(file.path(old_root, name)))) {
      stop("Reused P11 artifact byte mismatch: ", name, call. = FALSE)
    }
  }
  combined <- data.table::as.data.table(arrow::read_parquet(file.path(root, "scene_targets.parquet")))
  p11_validate_targets(combined, unique(combined$scene_id))
  if (nrow(combined) != 17600L || data.table::uniqueN(combined$scene_id) != 1600L) {
    stop("P11 v2 accepted cardinality mismatch", call. = FALSE)
  }
  list(dataset_id = acceptance$dataset_id, content_sha256 = acceptance$content_sha256,
       target_count = data.table::uniqueN(combined$target), scene_count = data.table::uniqueN(combined$scene_id))
}

p11_living_v2_district_audit <- function(scene, targets, boundary_path, low_fraction = 0.25) {
  district <- sf::st_read(boundary_path, quiet = TRUE, options = "ENCODING=UTF-8")
  district <- sf::st_transform(district[, c("SIGUNGU_CD", "SIGUNGU_NM")], 5186)
  centers <- sf::st_centroid(scene)
  intersects <- sf::st_intersects(centers, district)
  assigned <- vapply(intersects, function(index) {
    if (!length(index)) return(NA_character_)
    sort(as.character(district$SIGUNGU_CD[index]), method = "radix")[[1L]]
  }, character(1L))
  map <- data.table::data.table(scene_id = scene$scene_id, district_id = assigned)
  audit <- merge(targets, map, by = "scene_id", all.x = TRUE, sort = FALSE)
  list(
    zero = audit[eligible == FALSE, .N, .(target, district_id)][order(target, district_id)],
    low = audit[eligible == TRUE & valid_hour_fraction < low_fraction,
                .N, .(target, district_id)][order(target, district_id)]
  )
}

p11_execute_living_partial_support_rematerialization <- function(
    config_path = "config/p11_downstream_preprocessing_v2.yml") {
  cfg <- p11_living_v2_read_config(config_path)
  authorities <- p11_living_v2_validate_authority(cfg)
  inventory <- p11_source_inventory(
    cfg$sources$living_population,
    "downstream_data/livingpopulation",
    cfg$source_inventory_sha256$living_population,
    cfg$execution$workers
  )
  scene <- p11_evaluation_scenes(cfg$scene_index)
  overlap <- p11_read_grid_overlap(scene, file.path(cfg$sources$living_population, "빈격자(250m).shp"))
  overlap[, source_id := p11_living_grid_id(source_id)]
  shard <- p11_living_v2_publish_shard(cfg, authorities, scene, overlap)
  dataset <- p11_living_v2_publish_dataset(cfg, authorities, shard)
  readback <- p11_living_v2_validate_dataset(dataset$root, cfg$previous_dataset_root)
  district <- p11_living_v2_district_audit(
    scene, shard$targets, cfg$district_boundary,
    cfg$living_population$low_coverage_diagnostic_fraction
  )
  coverage <- shard$targets[, .(
    eligible_scenes = sum(eligible),
    ineligible_scenes = sum(!eligible),
    minimum_valid_hours = min(valid_hour_count),
    median_valid_hours = stats::median(valid_hour_count),
    maximum_valid_hours = max(valid_hour_count),
    minimum_valid_hour_fraction = min(valid_hour_fraction),
    median_valid_hour_fraction = stats::median(valid_hour_fraction),
    maximum_valid_hour_fraction = max(valid_hour_fraction),
    minimum_spatial_support = min(minimum_spatial_support_fraction, na.rm = TRUE),
    median_spatial_support = stats::median(median_spatial_support_fraction, na.rm = TRUE),
    maximum_spatial_support = max(maximum_spatial_support_fraction, na.rm = TRUE)
  ), target]
  list(
    authority_id = authorities$expected$authority,
    methodology_decision_id = authorities$expected$methodology,
    living_contract_id = authorities$expected$contract,
    source_inventory = inventory[c("file_count", "total_byte_size", "inventory_sha256")],
    shard_id = shard$manifest$shard_id,
    shard_content_sha256 = shard$manifest$content_sha256,
    dataset_id = dataset$dataset_id,
    dataset_content_sha256 = dataset$content_sha256,
    dataset_root = dataset$root,
    dataset_acceptance_sha256 = p11_sha256_file(file.path(dataset$root, "downstream_dataset_acceptance.json")),
    coverage = coverage,
    zero_observation_scenes = shard$targets[eligible == FALSE, .(target, scene_id, missing_reason)],
    district_audit = district,
    readback = readback,
    shard_created = shard$created
  )
}
