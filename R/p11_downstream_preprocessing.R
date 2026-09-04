# P11 downstream responses: dissertation section 3.6 and equations 3.29-3.31.

p11_read_config <- function(path = "config/p11_downstream_preprocessing.yml") {
  cfg <- yaml::read_yaml(path)
  required <- c("scene_index", "output_root", "sources", "contracts", "thresholds")
  if (!all(required %in% names(cfg))) stop("Incomplete P11 preprocessing configuration", call. = FALSE)
  cfg
}

p11_sha256_file <- function(path) {
  connection <- file(path, "rb")
  on.exit(close(connection), add = TRUE)
  paste0(openssl::sha256(connection))
}

p11_canonical_json <- function(value) {
  jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA, pretty = FALSE)
}

p11_content_identity <- function(prefix, value) {
  digest <- digest::digest(p11_canonical_json(value), algo = "sha256", serialize = FALSE)
  list(id = paste0(prefix, substr(digest, 1L, 24L)), sha256 = digest)
}

p11_source_inventory <- function(root, logical_root, expected_sha256, workers = 1L) {
  paths <- list.files(root, recursive = TRUE, full.names = TRUE, all.files = TRUE, no.. = TRUE)
  paths <- paths[!dir.exists(paths)]
  relative <- substring(paths, nchar(normalizePath(root, mustWork = TRUE)) + 2L)
  order_index <- order(enc2utf8(relative), method = "radix")
  paths <- paths[order_index]
  relative <- enc2utf8(relative[order_index])
  hashes <- unlist(parallel::mclapply(paths, p11_sha256_file,
                                      mc.cores = max(1L, as.integer(workers)), mc.preschedule = TRUE))
  records <- lapply(seq_along(paths), function(i) list(
    byte_size = unname(file.info(paths[[i]])$size), logical_path = relative[[i]], sha256 = hashes[[i]]
  ))
  digest <- digest::digest(p11_canonical_json(records), algo = "sha256", serialize = FALSE)
  if (!identical(digest, expected_sha256)) stop("P11 source inventory hash mismatch: ", logical_root, call. = FALSE)
  list(logical_root = logical_root, file_count = length(paths),
       total_byte_size = sum(file.info(paths)$size), inventory_sha256 = digest, records = records)
}

p11_publish_immutable_bundle <- function(final_dir, basenames, writer) {
  dir.create(dirname(final_dir), recursive = TRUE, showWarnings = FALSE)
  stage <- tempfile(paste0(".", basename(final_dir), ".stage-"), tmpdir = dirname(final_dir))
  dir.create(stage)
  on.exit(if (dir.exists(stage)) unlink(stage, recursive = TRUE), add = TRUE)
  writer(stage)
  staged <- file.path(stage, basenames)
  if (!all(file.exists(staged)) || any(file.info(staged)$size <= 0)) stop("Incomplete P11 staging bundle", call. = FALSE)
  final <- file.path(final_dir, basenames)
  if (dir.exists(final_dir)) {
    if (!all(file.exists(final))) stop("Existing P11 artifact is incomplete", call. = FALSE)
    same <- vapply(seq_along(final), function(i) identical(p11_sha256_file(final[[i]]), p11_sha256_file(staged[[i]])), logical(1L))
    if (!all(same)) stop("Immutable P11 artifact collision", call. = FALSE)
    return(normalizePath(final, mustWork = TRUE))
  }
  if (!file.rename(stage, final_dir)) stop("Atomic P11 artifact publication failed", call. = FALSE)
  normalizePath(final, mustWork = TRUE)
}

p11_evaluation_scenes <- function(path) {
  index <- data.table::as.data.table(arrow::read_parquet(path))
  index <- index[split == "evaluation"]
  if (nrow(index) != 1600L || data.table::uniqueN(index$scene_id) != 1600L) {
    stop("P11 requires the exact 1,600-scene P10 evaluation population", call. = FALSE)
  }
  wkts <- sprintf(
    "POLYGON ((%.8f %.8f, %.8f %.8f, %.8f %.8f, %.8f %.8f, %.8f %.8f))",
    index$xmin, index$ymin, index$xmax, index$ymin, index$xmax, index$ymax,
    index$xmin, index$ymax, index$xmin, index$ymin
  )
  sf::st_sf(
    scene_id = index$scene_id,
    geometry = sf::st_as_sfc(wkts, crs = 5186)
  )
}

p11_read_grid_overlap <- function(scene, path, id_column = "SPO_NO_CD") {
  filter <- sf::st_as_text(sf::st_transform(sf::st_as_sfc(sf::st_bbox(scene)), 5179))
  grid <- sf::st_read(path, quiet = TRUE, wkt_filter = filter, options = "ENCODING=UTF-8")
  ids <- as.character(grid[[id_column]])
  geometry_hash <- vapply(
    sf::st_as_binary(sf::st_geometry(grid), EWKB = TRUE),
    digest::digest, character(1L), algo = "sha256", serialize = FALSE
  )
  duplicate_audit <- data.table::data.table(source_id = ids, geometry_hash)[
    , .(copies = .N, geometry_count = data.table::uniqueN(geometry_hash)), source_id
  ]
  if (duplicate_audit[copies > 1L & geometry_count != 1L, .N]) {
    stop("Duplicate grid identity has conflicting geometry", call. = FALSE)
  }
  keep <- !duplicated(ids)
  grid <- grid[keep, id_column, drop = FALSE]
  grid <- sf::st_transform(grid, 5186)
  source_area <- as.numeric(sf::st_area(grid))
  intersection <- suppressWarnings(sf::st_intersection(scene, grid))
  out <- data.table::data.table(
    scene_id = intersection$scene_id,
    source_id = as.character(intersection[[id_column]]),
    intersection_area = as.numeric(sf::st_area(intersection))
  )[intersection_area > 1e-6]
  area_map <- data.table::data.table(source_id = as.character(grid[[id_column]]), source_area)
  out[area_map, source_area := i.source_area, on = "source_id"]
  coverage <- out[, sum(intersection_area), scene_id]
  if (any(abs(coverage$V1 - 250000) > 1e-4)) stop("Grid does not partition every P11 scene", call. = FALSE)
  data.table::setorder(out, scene_id, source_id)
  attr(out, "duplicate_count") <- duplicate_audit[copies > 1L, .N]
  out
}

p11_decode_cp949 <- function(value) iconv(value, from = "CP949", to = "UTF-8")

p11_living_grid_id <- function(source_id) {
  suffix <- c(aa = "00", ab = "25", ba = "50", bb = "75")
  body <- substring(source_id, 3L)
  x <- substr(body, 1L, 4L)
  y <- substr(body, 5L, 8L)
  xs <- unname(suffix[substr(x, 3L, 4L)])
  ys <- unname(suffix[substr(y, 3L, 4L)])
  if (anyNA(xs) || anyNA(ys)) stop("Unsupported 250 m grid suffix", call. = FALSE)
  paste0(substr(source_id, 1L, 2L), substr(x, 1L, 2L), xs, substr(y, 1L, 2L), ys)
}

p11_sgis_targets <- function() {
  data.table::data.table(
    target = c("total_population", "households", "housing_units", "establishments", "workers"),
    code = c("to_in_001", "to_ga_001", "to_ho_001", "to_fa_010", "to_em_020"),
    filename = c("2024년_인구_다사_100M.csv", "2024년_가구_다사_100M.csv",
                 "2024년_주택_다사_100M.csv", "2024년_사업체_다사_100M.csv",
                 "2024년_종사자_다사_100M.csv")
  )
}

p11_preprocess_sgis <- function(scene, root, threshold = 1, tolerance = 1e-9) {
  overlap <- p11_read_grid_overlap(scene, file.path(root, "빈격자(100m).shp"))
  targets <- p11_sgis_targets()
  results <- lapply(seq_len(nrow(targets)), function(i) {
    spec <- targets[i]
    raw <- data.table::fread(file.path(root, spec$filename), header = FALSE,
                             colClasses = "character", encoding = "unknown")
    data.table::setnames(raw, c("year", "source_id", "code", "released_value"))
    raw[, source_id := p11_decode_cp949(source_id)]
    raw <- raw[code == spec$code]
    if (!nrow(raw) || anyNA(raw$source_id) || any(raw$year != "2024")) {
      stop("SGIS source contract mismatch: ", spec$target, call. = FALSE)
    }
    if (raw[, anyDuplicated(paste(year, source_id, code))]) stop("Duplicate SGIS source row", call. = FALSE)
    raw[, value := suppressWarnings(as.numeric(released_value))]
    if (any(!is.finite(raw$value)) || any(raw$value < 0)) stop("Invalid SGIS released value", call. = FALSE)
    joined <- merge(overlap, raw[, .(source_id, value)], by = "source_id", all.x = TRUE, sort = FALSE)
    aggregate <- joined[, .(
      response = sum(value * intersection_area / source_area, na.rm = TRUE),
      contributing_grid_count = sum(!is.na(value)),
      total_grid_count = .N,
      represented_source_area = sum(intersection_area[!is.na(value)]),
      total_source_area = sum(intersection_area)
    ), scene_id]
    aggregate[, `:=`(
      target = spec$target,
      unit = "official privacy-protected released count",
      spatial_coverage = represented_source_area / total_source_area,
      temporal_coverage = NA_real_, observed_count = contributing_grid_count,
      expected_count = total_grid_count
    )]
    aggregate[, eligible := represented_source_area > tolerance & spatial_coverage + tolerance >= threshold]
    aggregate[eligible == FALSE, response := NA_real_]
    aggregate[, missing_reason := fifelse(eligible, NA_character_, "OMITTED_SOURCE_GRID_SUPPORT")]
    aggregate
  })
  data.table::rbindlist(results, use.names = TRUE)
}

p11_holidays_2025 <- function() {
  as.Date(c("2025-01-01", "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30",
            "2025-03-01", "2025-03-03", "2025-05-05", "2025-05-06", "2025-06-03",
            "2025-06-06", "2025-08-15", "2025-10-03", "2025-10-05", "2025-10-06",
            "2025-10-07", "2025-10-08", "2025-10-09", "2025-12-25"))
}

p11_temporal_class <- function(date, hour) {
  date <- as.Date(as.character(date), "%Y%m%d")
  hour <- as.integer(hour)
  weekend <- as.POSIXlt(date)$wday %in% c(0L, 6L) | date %in% p11_holidays_2025()
  daytime <- hour >= 9L & hour <= 18L
  paste(ifelse(weekend, "weekend", "weekday"), ifelse(daytime, "daytime", "nighttime"), sep = "_")
}

p11_expected_hours_2025 <- function() {
  dates <- seq(as.Date("2025-01-01"), as.Date("2025-12-31"), by = "day")
  values <- data.table::CJ(date = dates, hour = 0:23)
  values[, temporal_class := p11_temporal_class(format(date, "%Y%m%d"), hour)]
  values[, .(expected_count = .N), temporal_class][order(temporal_class)]
}

p11_living_day <- function(path, overlap) {
  raw <- data.table::fread(path, select = 1:5, colClasses = "character", encoding = "unknown")
  data.table::setnames(raw, c("date", "hour", "admin_id", "source_id", "released_value"))
  raw[, source_id := p11_decode_cp949(source_id)]
  raw <- raw[source_id %chin% overlap$source_id]
  raw[, value := suppressWarnings(as.numeric(released_value))]
  aggregate <- raw[, .(
    value = if (all(is.finite(value) & value >= 0)) sum(value) else NA_real_,
    source_rows = .N
  ), .(source_id, date, hour)]
  joined <- merge(overlap, aggregate, by = "source_id", all.x = TRUE, allow.cartesian = TRUE, sort = FALSE)
  hourly <- joined[, .(
    response = sum(value * intersection_area / source_area, na.rm = TRUE),
    represented_source_area = sum(intersection_area[!is.na(value)]),
    total_source_area = sum(intersection_area)
  ), .(scene_id, date, hour)]
  hourly[, valid_hour := abs(represented_source_area - total_source_area) <= 1e-4]
  hourly[, temporal_class := p11_temporal_class(date, hour)]
  hourly[valid_hour == TRUE, .(response_sum = sum(response), observed_count = .N),
                              .(scene_id, temporal_class)]
}

p11_preprocess_living <- function(scene, root, threshold = 0.9, workers = 1L) {
  overlap <- p11_read_grid_overlap(scene, file.path(root, "빈격자(250m).shp"))
  overlap[, source_id := p11_living_grid_id(source_id)]
  files <- sort(Sys.glob(file.path(root, "250_LOCAL_RESD_2025*.csv")), method = "radix")
  if (length(files) != 365L) stop("Living-population source must contain all 365 days", call. = FALSE)
  values <- parallel::mclapply(files, p11_living_day, overlap = overlap,
                               mc.cores = max(1L, as.integer(workers)), mc.preschedule = TRUE)
  combined <- data.table::rbindlist(values)
  result <- combined[, .(response_sum = sum(response_sum), observed_count = sum(observed_count)),
                     .(scene_id, temporal_class)]
  expected <- p11_expected_hours_2025()
  universe <- data.table::CJ(scene_id = scene$scene_id, temporal_class = expected$temporal_class, sorted = TRUE)
  result <- merge(universe, result, by = c("scene_id", "temporal_class"), all.x = TRUE, sort = FALSE)
  result[is.na(observed_count), `:=`(observed_count = 0L, response_sum = 0)]
  result[expected, expected_count := i.expected_count, on = "temporal_class"]
  result[, `:=`(
    target = temporal_class,
    response = data.table::fifelse(observed_count > 0L, response_sum / observed_count, NA_real_),
    unit = "persons",
    spatial_coverage = 1,
    temporal_coverage = observed_count / expected_count,
    contributing_grid_count = NA_integer_, represented_source_area = 250000,
    total_source_area = 250000
  )]
  result[, eligible := temporal_coverage + 1e-12 >= threshold]
  result[eligible == FALSE, response := NA_real_]
  result[, missing_reason := data.table::fifelse(eligible, NA_character_, "INSUFFICIENT_VALID_HOUR_COVERAGE")]
  result
}

p11_read_land_values <- function(path) {
  raw <- data.table::fread(path, encoding = "unknown", colClasses = "character")
  data.table::setnames(raw, p11_decode_cp949(names(raw)))
  required <- c("고유번호", "기준연도", "공시지가")
  if (!all(required %in% names(raw))) stop("Land-value CSV schema mismatch", call. = FALSE)
  out <- raw[, .(parcel_id = get("고유번호"), year = get("기준연도"), raw_value = get("공시지가"))]
  if (out[, anyDuplicated(parcel_id)]) stop("Duplicate Seoul parcel value identity", call. = FALSE)
  out[, value := suppressWarnings(as.numeric(raw_value))]
  if (any(out$year != "2026") || any(!is.finite(out$value)) || any(out$value < 0)) {
    stop("Land-value source year/value mismatch", call. = FALSE)
  }
  out[, .(parcel_id, value)]
}

p11_preprocess_land_value <- function(scene, root, threshold = 1, tolerance = 1e-9) {
  path <- file.path(root, "AL_D150_11_20260526.shp")
  parcels <- sf::st_read(path, quiet = TRUE, wkt_filter = sf::st_as_text(sf::st_as_sfc(sf::st_bbox(scene))))
  parcels <- sf::st_transform(parcels, 5186)
  parcels <- parcels[, "A0", drop = FALSE]
  names(parcels)[names(parcels) == "A0"] <- "parcel_id"
  if (anyDuplicated(parcels$parcel_id)) stop("Duplicate Seoul parcel geometry identity", call. = FALSE)
  source_parcel_count <- nrow(parcels)
  source_parcel_ids <- parcels$parcel_id
  relevant_index <- sort(unique(unlist(sf::st_intersects(scene, parcels))), method = "radix")
  parcels <- parcels[relevant_index, ]
  initially_valid <- sf::st_is_valid(parcels)
  repaired <- !initially_valid
  if (any(repaired)) sf::st_geometry(parcels)[repaired] <- sf::st_geometry(sf::st_make_valid(parcels[repaired, ]))
  geometry_type <- as.character(sf::st_geometry_type(parcels))
  accepted_geometry <- !sf::st_is_empty(parcels) & sf::st_is_valid(parcels) &
    geometry_type %in% c("POLYGON", "MULTIPOLYGON")
  dropped <- sum(!accepted_geometry)
  parcels <- parcels[accepted_geometry, ]
  values <- p11_read_land_values(file.path(root, "AL_D151_11_20260526.csv"))
  parcels$value <- values$value[match(parcels$parcel_id, values$parcel_id)]
  candidates <- sf::st_intersects(scene, parcels)
  pieces <- lapply(seq_len(nrow(scene)), function(i) {
    selected <- candidates[[i]]
    if (!length(selected)) return(NULL)
    intersection <- suppressWarnings(sf::st_intersection(scene[i, ], parcels[selected, ]))
    data.table::data.table(
      scene_id = scene$scene_id[[i]], parcel_id = intersection$parcel_id,
      value = intersection$value, intersection_area = as.numeric(sf::st_area(intersection))
    )[intersection_area > 1e-6]
  })
  tab <- data.table::rbindlist(pieces)
  result <- tab[, .(
    response = if (any(!is.na(value))) weighted.mean(value, intersection_area, na.rm = TRUE) else NA_real_,
    contributing_grid_count = sum(!is.na(value)),
    total_parcel_count = .N,
    represented_source_area = sum(intersection_area[!is.na(value)]),
    total_source_area = sum(intersection_area)
  ), scene_id]
  result[, `:=`(
    target = "official_land_value", unit = "KRW per square metre",
    spatial_coverage = represented_source_area / total_source_area,
    temporal_coverage = NA_real_, observed_count = contributing_grid_count,
    expected_count = total_parcel_count
  )]
  result[, eligible := is.finite(response) & spatial_coverage + tolerance >= threshold]
  result[eligible == FALSE, response := NA_real_]
  result[, missing_reason := data.table::fifelse(eligible, NA_character_, "INCOMPLETE_VALUED_PARCEL_SUPPORT")]
  attr(result, "geometry_audit") <- list(
    source_parcel_count = source_parcel_count, spatially_relevant = length(relevant_index),
    relevant_initially_valid = sum(initially_valid), repaired = sum(repaired & accepted_geometry), dropped = dropped,
    value_without_source_geometry = sum(!values$parcel_id %in% source_parcel_ids),
    geometry_without_value = sum(!parcels$parcel_id %in% values$parcel_id)
  )
  result
}

p11_ecostress_triplets <- function(root) {
  candidates <- list.files(root, pattern = "[.]tif$", full.names = TRUE)
  lst <- sort(candidates[grepl("ECO_L2T_LSTE[.]002_LST_[0-9]{8}T[0-9]{6}_", basename(candidates))], method = "radix")
  timestamp <- sub(".*_([0-9]{8}T[0-9]{6})_.*", "\\1", basename(lst))
  make <- function(layer, value) file.path(root, sub("_LST_", paste0("_", layer, "_"), basename(value), fixed = TRUE))
  out <- data.table::data.table(timestamp, lst, qc = make("QC", lst), cloud = make("cloud", lst))
  if (nrow(out) != 79L || any(!file.exists(out$qc)) || any(!file.exists(out$cloud)) || anyDuplicated(timestamp)) {
    stop("ECOSTRESS timestamp triplet contract mismatch", call. = FALSE)
  }
  out
}

p11_ecostress_acquisition <- function(lst_path, qc_path, cloud_path, timestamp, scene_utm) {
  raster <- terra::rast(c(lst_path, qc_path, cloud_path))
  names(raster) <- c("lst", "qc", "cloud")
  extracted <- exactextractr::exact_extract(raster, scene_utm, function(values, coverage_fractions) {
    ok <- is.finite(values$lst) & values$lst >= 150 & values$lst <= 1310.7 &
      bitwAnd(as.integer(values$qc), 3L) == 0L & values$cloud == 0
    weight <- coverage_fractions[ok]
    list(response = if (sum(weight) > 0) sum(values$lst[ok] * weight) / sum(weight) else NA_real_,
         valid_area = sum(weight) * 4900)
  }, progress = FALSE)
  unpack <- function(value) {
    if (is.null(value) || !length(value)) return(c(response = NA_real_, valid_area = 0))
    unlist(value, use.names = TRUE)
  }
  extracted <- if (is.matrix(extracted)) {
    as.data.frame(t(extracted))
  } else {
    as.data.frame(do.call(rbind, lapply(extracted, unpack)))
  }
  extracted$response <- as.numeric(unlist(extracted$response))
  extracted$valid_area <- as.numeric(unlist(extracted$valid_area))
  data.table::data.table(
    scene_id = scene_utm$scene_id, timestamp = timestamp,
    response = extracted$response, valid_area = extracted$valid_area,
    spatial_coverage = pmin(extracted$valid_area / 250000, 1)
  )
}

p11_preprocess_ecostress <- function(scene, root, area_threshold = 0.5,
                                     minimum_acquisitions = 12L, required_quarters = 4L) {
  triplets <- p11_ecostress_triplets(root)
  scene_utm <- sf::st_transform(scene, 32652)
  values <- lapply(seq_len(nrow(triplets)), function(i) p11_ecostress_acquisition(
    triplets$lst[i], triplets$qc[i], triplets$cloud[i], triplets$timestamp[i], scene_utm
  ))
  observations <- data.table::rbindlist(values)
  observations[, accepted := is.finite(response) & spatial_coverage + 1e-12 >= area_threshold]
  observations[, quarter := as.integer((as.integer(substr(timestamp, 5L, 6L)) - 1L) %/% 3L + 1L)]
  result <- observations[, .(
    response = mean(response[accepted]),
    observed_count = sum(accepted),
    available_count = sum(is.finite(response)),
    represented_source_area = sum(valid_area[accepted]),
    total_source_area = .N * 250000,
    temporal_quarter_count = data.table::uniqueN(quarter[accepted]),
    spatial_coverage = mean(spatial_coverage[accepted])
  ), scene_id]
  result[, `:=`(
    target = "ecostress_lst", unit = "Kelvin", expected_count = nrow(triplets),
    temporal_coverage = observed_count / nrow(triplets), contributing_grid_count = NA_integer_
  )]
  result[, eligible := observed_count >= minimum_acquisitions & temporal_quarter_count >= required_quarters]
  result[eligible == FALSE, response := NA_real_]
  result[, missing_reason := data.table::fifelse(eligible, NA_character_, "INSUFFICIENT_ECOSTRESS_SUPPORT")]
  attr(result, "acquisition_audit") <- observations
  result
}

p11_normalize_output <- function(value, family) {
  value <- data.table::as.data.table(value)
  value[, source_family := family]
  columns <- c("scene_id", "target", "source_family", "response", "unit", "eligible",
               "missing_reason", "spatial_coverage", "temporal_coverage", "observed_count",
               "expected_count", "contributing_grid_count", "represented_source_area",
               "total_source_area")
  missing <- setdiff(columns, names(value))
  for (column in missing) value[, (column) := NA]
  data.table::setcolorder(value, columns)
  data.table::setorder(value, target, scene_id)
  value[]
}

p11_validate_targets <- function(value, scene_ids) {
  value <- data.table::as.data.table(value)
  if (value[, anyDuplicated(paste(scene_id, target))]) stop("Duplicate P11 scene-target row", call. = FALSE)
  if (!all(value$scene_id %in% scene_ids)) stop("P11 response contains an unknown scene", call. = FALSE)
  if (any(value$eligible & !is.finite(value$response))) stop("Eligible P11 response is not finite", call. = FALSE)
  if (any(!value$eligible & is.na(value$missing_reason))) stop("Ineligible P11 response lacks a reason", call. = FALSE)
  expected_targets <- c("total_population", "households", "housing_units", "establishments", "workers",
                        "weekday_daytime", "weekday_nighttime", "weekend_daytime", "weekend_nighttime",
                        "official_land_value", "ecostress_lst")
  if (!setequal(unique(value$target), expected_targets)) stop("P11 target inventory mismatch", call. = FALSE)
  cardinality <- value[, .N, target]
  if (nrow(cardinality) != 11L || any(cardinality$N != length(scene_ids))) {
    stop("P11 must record every scene for every target", call. = FALSE)
  }
  TRUE
}

p11_execute_preprocessing <- function(config_path = "config/p11_downstream_preprocessing.yml") {
  cfg <- p11_read_config(config_path)
  decision <- jsonlite::read_json(cfg$methodology_decision, simplifyVector = FALSE)
  if (!identical(decision$status, "CLOSED") || decision$unspecified_scientific_decision_count != 0L) {
    stop("P11 methodology is not closed", call. = FALSE)
  }
  scene <- p11_evaluation_scenes(cfg$scene_index)
  thresholds <- cfg$thresholds
  sgis <- p11_preprocess_sgis(scene, cfg$sources$sgis, thresholds$grid_spatial_fraction, cfg$numeric_tolerance)
  living <- p11_preprocess_living(scene, cfg$sources$living_population,
                                  thresholds$living_temporal_fraction, cfg$workers)
  land <- p11_preprocess_land_value(scene, cfg$sources$land_value,
                                    thresholds$land_value_parcel_support_fraction, cfg$numeric_tolerance)
  eco <- p11_preprocess_ecostress(scene, cfg$sources$ecostress,
                                  thresholds$ecostress_acquisition_area_fraction,
                                  thresholds$ecostress_minimum_acquisitions,
                                  thresholds$ecostress_required_calendar_quarters)
  families <- list(
    sgis = p11_normalize_output(sgis, "sgis_grid_statistics"),
    living_population = p11_normalize_output(living, "living_population"),
    land_value = p11_normalize_output(land, "official_land_value"),
    ecostress = p11_normalize_output(eco, "ecostress_lst")
  )
  combined <- data.table::rbindlist(families, use.names = TRUE, fill = TRUE)
  p11_validate_targets(combined, scene$scene_id)
  contract_hashes <- lapply(cfg$contracts, p11_sha256_file)
  inventories <- lapply(names(cfg$sources), function(name) p11_source_inventory(
    cfg$sources[[name]], paste0("downstream_data/", basename(cfg$sources[[name]])),
    cfg$source_inventory_sha256[[name]], cfg$workers
  ))
  names(inventories) <- names(cfg$sources)
  implementation <- list(
    version = cfg$version,
    implementation_sha256 = p11_sha256_file("R/p11_downstream_preprocessing.R"),
    configuration_sha256 = p11_sha256_file(config_path)
  )
  output_content_sha256 <- lapply(families, function(value) {
    digest::digest(p11_canonical_json(as.data.frame(value)), algo = "sha256", serialize = FALSE)
  })
  preimage <- list(
    schema_version = "1.0.0", artifact_type = "p11_downstream_dataset_acceptance",
    implementation = implementation, methodology_decision_id = decision$decision_id,
    p10_acceptance_id = "p10acc_6e5071beee7616750dec7907",
    scene_index_id = "rsi_80031f1493c75163f91b7c71",
    source_inventory_sha256 = cfg$source_inventory_sha256,
    source_contract_sha256 = contract_hashes,
    output_content_sha256 = output_content_sha256,
    thresholds = thresholds,
    target_count = 11L, scene_universe_count = 1600L
  )
  identity <- p11_content_identity("p11ds_", preimage)
  final_dir <- file.path(cfg$output_root, identity$id)
  basenames <- c(paste0(names(families), ".parquet"), paste0(names(families), "_source_acceptance.json"),
                 "scene_targets.parquet", "target_eligibility.parquet", "coverage_summary.json",
                 "downstream_dataset_acceptance.json")
  paths <- p11_publish_immutable_bundle(final_dir, basenames, function(stage) {
    for (name in names(families)) arrow::write_parquet(families[[name]], file.path(stage, paste0(name, ".parquet")), compression = "zstd")
    arrow::write_parquet(combined, file.path(stage, "scene_targets.parquet"), compression = "zstd")
    arrow::write_parquet(combined[, .(scene_id, target, eligible, missing_reason, spatial_coverage,
                                      temporal_coverage, observed_count, expected_count)],
                         file.path(stage, "target_eligibility.parquet"), compression = "zstd")
    for (name in names(families)) {
      source_preimage <- list(
        schema_version = "1.0.0", artifact_type = "p11_source_acceptance", source_family = name,
        contract_sha256 = contract_hashes[[name]], inventory = inventories[[name]], status = "ACCEPTED"
      )
      source_identity <- p11_content_identity("p11sa_", source_preimage)
      source_acceptance <- c(source_preimage, list(acceptance_id = source_identity$id,
                                                  content_sha256 = source_identity$sha256))
      jsonlite::write_json(source_acceptance, file.path(stage, paste0(name, "_source_acceptance.json")),
                           auto_unbox = TRUE, pretty = TRUE, null = "null", digits = NA)
    }
    safe_min <- function(x) if (any(is.finite(x))) min(x[is.finite(x)]) else NA_real_
    summary <- combined[, .(scene_rows = .N, eligible_scenes = sum(eligible), missing_scenes = sum(!eligible),
                            minimum_spatial_coverage = safe_min(spatial_coverage),
                            minimum_temporal_coverage = safe_min(temporal_coverage)), target]
    jsonlite::write_json(summary, file.path(stage, "coverage_summary.json"), auto_unbox = TRUE, pretty = TRUE, na = "null")
    artifacts <- lapply(setdiff(basenames, "downstream_dataset_acceptance.json"), function(name) list(
      role = sub("[.]parquet$|[.]json$", "", name), basename = name,
      byte_size = unname(file.info(file.path(stage, name))$size), sha256 = p11_sha256_file(file.path(stage, name))
    ))
    acceptance <- c(preimage, list(dataset_id = identity$id, content_sha256 = identity$sha256,
                                  status = "ACCEPTED", artifacts = artifacts))
    jsonlite::write_json(acceptance, file.path(stage, "downstream_dataset_acceptance.json"), auto_unbox = TRUE,
                         pretty = TRUE, null = "null", na = "null", digits = NA)
  })
  list(dataset_id = identity$id, content_sha256 = identity$sha256, paths = paths,
       coverage = combined[, .(eligible = sum(eligible), total = .N), target],
       land_geometry_audit = attr(land, "geometry_audit"),
       ecostress_acquisition_audit = attr(eco, "acquisition_audit"))
}

p11_validate_dataset_acceptance <- function(directory) {
  path <- file.path(directory, "downstream_dataset_acceptance.json")
  acceptance <- jsonlite::read_json(path, simplifyVector = FALSE)
  keys <- c("schema_version", "artifact_type", "implementation", "methodology_decision_id",
            "p10_acceptance_id", "scene_index_id", "source_inventory_sha256",
            "source_contract_sha256", "output_content_sha256", "thresholds",
            "target_count", "scene_universe_count")
  identity <- p11_content_identity("p11ds_", acceptance[keys])
  if (!identical(acceptance$dataset_id, identity$id) || !identical(acceptance$content_sha256, identity$sha256)) {
    stop("P11 dataset content identity mismatch", call. = FALSE)
  }
  for (artifact in acceptance$artifacts) {
    artifact_path <- file.path(directory, artifact$basename)
    if (!file.exists(artifact_path) || file.info(artifact_path)$size != artifact$byte_size ||
        !identical(p11_sha256_file(artifact_path), artifact$sha256)) {
      stop("P11 accepted artifact hash mismatch: ", artifact$basename, call. = FALSE)
    }
  }
  combined <- data.table::as.data.table(arrow::read_parquet(file.path(directory, "scene_targets.parquet")))
  p11_validate_targets(combined, unique(combined$scene_id))
  for (name in c("sgis", "living_population", "land_value", "ecostress")) {
    value <- data.table::as.data.table(arrow::read_parquet(file.path(directory, paste0(name, ".parquet"))))
    digest <- digest::digest(p11_canonical_json(as.data.frame(value)), algo = "sha256", serialize = FALSE)
    if (!identical(digest, acceptance$output_content_sha256[[name]])) stop("P11 output content hash mismatch: ", name, call. = FALSE)
    source <- jsonlite::read_json(file.path(directory, paste0(name, "_source_acceptance.json")), simplifyVector = FALSE)
    source_identity <- p11_content_identity("p11sa_", source[setdiff(names(source), c("acceptance_id", "content_sha256"))])
    if (!identical(source$acceptance_id, source_identity$id) || !identical(source$content_sha256, source_identity$sha256)) {
      stop("P11 source acceptance identity mismatch: ", name, call. = FALSE)
    }
  }
  list(dataset_id = acceptance$dataset_id, status = acceptance$status,
       target_count = data.table::uniqueN(combined$target), scene_count = data.table::uniqueN(combined$scene_id))
}
