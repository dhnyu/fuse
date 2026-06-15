#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)

parse_args <- function(args) {
  out <- list(
    processed_dir = path.expand(Sys.getenv("TOGIEEUM_PROCESSED_DIR", "~/fusedatalarge/processed")),
    report_dir = path.expand(Sys.getenv("FUSE_REPORT_DIR", "~/fuse/reports")),
    overwrite = FALSE,
    target_crs = as.integer(Sys.getenv("TOGIEEUM_TARGET_CRS", "5186"))
  )

  i <- 1L
  while (i <= length(args)) {
    arg <- args[[i]]
    if (identical(arg, "--overwrite")) out$overwrite <- TRUE
    if (identical(arg, "--processed-dir") && i < length(args)) {
      i <- i + 1L
      out$processed_dir <- path.expand(args[[i]])
    }
    if (identical(arg, "--report-dir") && i < length(args)) {
      i <- i + 1L
      out$report_dir <- path.expand(args[[i]])
    }
    i <- i + 1L
  }
  out
}

cfg <- parse_args(commandArgs(trailingOnly = TRUE))

dir.create(cfg$processed_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(cfg$report_dir, recursive = TRUE, showWarnings = FALSE)

run_stamp <- format(Sys.time(), "%Y%m%d_%H%M")
paths <- list(
  input_gpkg = file.path(cfg$processed_dir, "korea_polygon_poi_togieeum.gpkg"),
  input_attributes = file.path(cfg$processed_dir, "korea_polygon_poi_togieeum_attributes.parquet"),
  diagnostics = file.path(cfg$processed_dir, "korea_polygon_poi_togieeum_transport_shape_diagnostics.parquet"),
  corridor_candidates = file.path(cfg$processed_dir, "korea_polygon_poi_togieeum_transport_corridor_candidates.gpkg"),
  facility_gpkg = file.path(cfg$processed_dir, "korea_polygon_poi_togieeum_facility.gpkg"),
  facility_attributes = file.path(cfg$processed_dir, "korea_polygon_poi_togieeum_facility_attributes.parquet"),
  facility_summary = file.path(cfg$processed_dir, "korea_polygon_poi_togieeum_facility_summary.parquet"),
  report = file.path(cfg$report_dir, paste0(run_stamp, "_togieeum_transport_facility_refinement_report.md"))
)

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), paste(..., collapse = " ")))
}

stop_if_outputs_exist <- function(paths, overwrite = FALSE) {
  output_paths <- unlist(paths[c("diagnostics", "corridor_candidates", "facility_gpkg", "facility_attributes", "facility_summary", "report")], use.names = FALSE)
  existing <- output_paths[file.exists(output_paths)]
  if (!length(existing)) return(invisible(TRUE))
  if (!overwrite) {
    stop(
      "Output file(s) already exist. Re-run with --overwrite to replace only these target outputs:\n",
      paste(existing, collapse = "\n"),
      call. = FALSE
    )
  }
  for (path in existing) {
    unlink(path, recursive = FALSE, force = TRUE)
    for (sidecar in paste0(path, c("-wal", "-shm"))) {
      if (file.exists(sidecar)) unlink(sidecar, force = TRUE)
    }
  }
}

clean_string <- function(x) {
  x <- as.character(x)
  x <- trimws(x)
  x[x == ""] <- NA_character_
  x
}

md_table <- function(dt, n = Inf) {
  dt <- as.data.frame(dt[seq_len(min(nrow(dt), n))])
  if (!nrow(dt)) return("_No rows._")
  dt[] <- lapply(dt, function(x) {
    x <- as.character(x)
    x[is.na(x)] <- ""
    gsub("\\|", "\\\\|", x)
  })
  header <- paste0("| ", paste(names(dt), collapse = " | "), " |")
  sep <- paste0("| ", paste(rep("---", ncol(dt)), collapse = " | "), " |")
  rows <- apply(dt, 1, function(r) paste0("| ", paste(r, collapse = " | "), " |"))
  paste(c(header, sep, rows), collapse = "\n")
}

calculate_transport_diagnostics <- function(transport_sf, transport_attrs) {
  geom <- sf::st_geometry(transport_sf)
  bbox <- do.call(rbind, lapply(geom, function(g) as.numeric(sf::st_bbox(g))))
  colnames(bbox) <- c("xmin", "ymin", "xmax", "ymax")

  area_m2 <- as.numeric(sf::st_area(geom))
  perimeter_m <- as.numeric(sf::st_length(sf::st_boundary(geom)))
  bbox_width_m <- bbox[, "xmax"] - bbox[, "xmin"]
  bbox_height_m <- bbox[, "ymax"] - bbox[, "ymin"]
  longest_bbox_side_m <- pmax(bbox_width_m, bbox_height_m)
  shortest_bbox_side_m <- pmin(bbox_width_m, bbox_height_m)
  small_epsilon <- 1e-6

  diagnostics <- copy(transport_attrs)
  diagnostics[, `:=`(
    area_m2 = area_m2,
    perimeter_m = perimeter_m,
    bbox_width_m = bbox_width_m,
    bbox_height_m = bbox_height_m,
    bbox_aspect_ratio = longest_bbox_side_m / pmax(shortest_bbox_side_m, small_epsilon),
    compactness = 4 * pi * area_m2 / pmax(perimeter_m^2, small_epsilon),
    thinness = perimeter_m^2 / pmax(area_m2, small_epsilon),
    longest_bbox_side_m = longest_bbox_side_m,
    approximate_width_m = area_m2 / pmax(longest_bbox_side_m, small_epsilon),
    bbox_diagonal_m = sqrt(bbox_width_m^2 + bbox_height_m^2)
  )]

  facility_terms <- "역|역사|정거장|터미널|공항|항만|항구|주차장|차고지|환승|어항|항만시설|공항시설|자동차정류장|검사시설|운전학원"
  corridor_terms <- "철도|도시철도|지하철|궤도|선로|터널|일반철도|고속철도"
  diagnostics[, label_text_for_review := paste(
    clean_string(feature_label_ko),
    clean_string(semantic_type_label_ko),
    clean_string(decoded_type_label_ko),
    clean_string(decision_sclas_label_ko),
    sep = " "
  )]
  diagnostics[, facility_label_safety := grepl(facility_terms, label_text_for_review)]
  diagnostics[, corridor_label_hint := grepl(corridor_terms, label_text_for_review)]

  diagnostics[, base_geometry_corridor_screen :=
    compactness <= 0.08 &
      approximate_width_m <= 50 &
      bbox_diagonal_m >= 500 &
      (bbox_aspect_ratio >= 8 | compactness <= 0.04 | approximate_width_m <= 25)
  ]
  diagnostics[, extreme_corridor_geometry :=
    compactness <= 0.02 &
      approximate_width_m <= 15 &
      bbox_diagonal_m >= 1000
  ]
  diagnostics[, transport_corridor_candidate :=
    base_geometry_corridor_screen &
      (!facility_label_safety | extreme_corridor_geometry)
  ]
  diagnostics[, review_preserved_by_facility_label :=
    base_geometry_corridor_screen &
      facility_label_safety &
      !extreme_corridor_geometry
  ]
  diagnostics[, corridor_decision_reason := fifelse(
    transport_corridor_candidate & facility_label_safety & extreme_corridor_geometry,
    "candidate_extreme_geometry_despite_facility_label",
    fifelse(
      transport_corridor_candidate & corridor_label_hint,
      "candidate_geometry_screen_with_corridor_label_hint",
      fifelse(
        transport_corridor_candidate,
        "candidate_geometry_screen_without_corridor_label_hint",
        fifelse(
          review_preserved_by_facility_label,
          "preserved_facility_label_safety",
          "not_corridor_candidate"
        )
      )
    )
  )]

  diagnostics[, rank_highest_bbox_aspect_ratio := frank(-bbox_aspect_ratio, ties.method = "first")]
  diagnostics[, rank_lowest_compactness := frank(compactness, ties.method = "first")]
  diagnostics[, rank_largest_bbox_diagonal := frank(-bbox_diagonal_m, ties.method = "first")]
  diagnostics[, rank_smallest_approx_width_large_polygon := fifelse(
    bbox_diagonal_m >= 500,
    frank(fifelse(bbox_diagonal_m >= 500, approximate_width_m, Inf), ties.method = "first"),
    NA_integer_
  )]
  diagnostics[order(-transport_corridor_candidate, -base_geometry_corridor_screen, rank_largest_bbox_diagonal)]
}

write_report <- function(
  diagnostics, attrs, facility_attrs, validation, paths, start_time
) {
  metric_quantiles <- rbindlist(lapply(
    c("bbox_aspect_ratio", "compactness", "thinness", "approximate_width_m", "bbox_diagonal_m", "area_m2", "perimeter_m"),
    function(metric) {
      qs <- quantile(diagnostics[[metric]], probs = c(0, .01, .05, .1, .25, .5, .75, .9, .95, .99, 1), na.rm = TRUE)
      data.table(metric = metric, probability = names(qs), value = signif(as.numeric(qs), 8))
    }
  ))

  top_aspect <- diagnostics[order(-bbox_aspect_ratio)][1:25, .(
    polygon_poi_id, semantic_type_key, semantic_type_label_ko, feature_label_ko,
    region_sgg_code, area_m2 = round(area_m2, 1), bbox_aspect_ratio = round(bbox_aspect_ratio, 1),
    compactness = signif(compactness, 3), approximate_width_m = round(approximate_width_m, 1),
    bbox_diagonal_m = round(bbox_diagonal_m, 1), facility_label_safety,
    corridor_label_hint, transport_corridor_candidate
  )]
  low_compact <- diagnostics[bbox_diagonal_m >= 300][order(compactness)][1:25, .(
    polygon_poi_id, semantic_type_key, semantic_type_label_ko, feature_label_ko,
    region_sgg_code, area_m2 = round(area_m2, 1), bbox_aspect_ratio = round(bbox_aspect_ratio, 1),
    compactness = signif(compactness, 3), approximate_width_m = round(approximate_width_m, 1),
    bbox_diagonal_m = round(bbox_diagonal_m, 1), facility_label_safety,
    corridor_label_hint, transport_corridor_candidate
  )]
  largest_diag <- diagnostics[order(-bbox_diagonal_m)][1:25, .(
    polygon_poi_id, semantic_type_key, semantic_type_label_ko, feature_label_ko,
    region_sgg_code, area_m2 = round(area_m2, 1), bbox_aspect_ratio = round(bbox_aspect_ratio, 1),
    compactness = signif(compactness, 3), approximate_width_m = round(approximate_width_m, 1),
    bbox_diagonal_m = round(bbox_diagonal_m, 1), facility_label_safety,
    corridor_label_hint, transport_corridor_candidate
  )]
  small_width_large <- diagnostics[bbox_diagonal_m >= 500][order(approximate_width_m)][1:25, .(
    polygon_poi_id, semantic_type_key, semantic_type_label_ko, feature_label_ko,
    region_sgg_code, area_m2 = round(area_m2, 1), bbox_aspect_ratio = round(bbox_aspect_ratio, 1),
    compactness = signif(compactness, 3), approximate_width_m = round(approximate_width_m, 1),
    bbox_diagonal_m = round(bbox_diagonal_m, 1), facility_label_safety,
    corridor_label_hint, transport_corridor_candidate
  )]

  candidate_by_type <- diagnostics[transport_corridor_candidate == TRUE, .N,
    by = .(semantic_type_key, semantic_type_label_ko, feature_label_ko)
  ][order(-N)]
  preserved_by_type <- diagnostics[review_preserved_by_facility_label == TRUE, .N,
    by = .(semantic_type_key, semantic_type_label_ko, feature_label_ko)
  ][order(-N)]
  final_by_category <- facility_attrs[, .(
    feature_count = .N,
    total_area_m2 = round(sum(area_m2, na.rm = TRUE), 3)
  ), by = .(major_category, major_category_ko)][order(-feature_count)]

  lines <- c(
    "# Togieeum Transportation Corridor Refinement Report",
    "",
    sprintf("Generated: `%s`", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
    sprintf("Script: `%s`", normalizePath("scripts/poi/refine_togieeum_transport_facilities.R", winslash = "/", mustWork = FALSE)),
    "",
    "## Objective",
    "",
    "Create a facility-oriented Togieeum polygon POI layer by identifying route-like transportation corridor polygons using geometry diagnostics as the primary evidence. The original cleaned Togieeum output is left unchanged.",
    "",
    "## Threshold Selection",
    "",
    "Transportation labels are not sufficient for corridor identification because Togieeum subcategory fields do not consistently separate routes, stations, ports, yards, and other transport facilities. The diagnostic review therefore used shape metrics first and labels only as a secondary safety layer.",
    "",
    "The selected conservative geometry screen is:",
    "",
    "```text",
    "base_geometry_corridor_screen =",
    "  compactness <= 0.08",
    "  AND approximate_width_m <= 50",
    "  AND bbox_diagonal_m >= 500",
    "  AND (bbox_aspect_ratio >= 8 OR compactness <= 0.04 OR approximate_width_m <= 25)",
    "",
    "extreme_corridor_geometry =",
    "  compactness <= 0.02",
    "  AND approximate_width_m <= 15",
    "  AND bbox_diagonal_m >= 1000",
    "",
    "transport_corridor_candidate =",
    "  base_geometry_corridor_screen",
    "  AND (not facility_label_safety OR extreme_corridor_geometry)",
    "```",
    "",
    "This avoids relying on subcategory text to find corridors, while preserving station/terminal/airport/port/parking/depot-like labels unless their geometry is extremely corridor-like.",
    "",
    "## Metric Quantiles",
    "",
    md_table(metric_quantiles),
    "",
    "## Diagnostic Views Used Before Thresholding",
    "",
    "### Highest Bbox Aspect Ratio",
    "",
    md_table(top_aspect),
    "",
    "### Lowest Compactness Among Polygons With Bbox Diagonal >= 300 m",
    "",
    md_table(low_compact),
    "",
    "### Largest Bbox Diagonal",
    "",
    md_table(largest_diag),
    "",
    "### Smallest Approximate Width Among Polygons With Bbox Diagonal >= 500 m",
    "",
    md_table(small_width_large),
    "",
    "## Corridor Candidate Results",
    "",
    sprintf("- Transportation polygons evaluated: `%s`", nrow(diagnostics)),
    sprintf("- Base geometry screen positives: `%s`", diagnostics[base_geometry_corridor_screen == TRUE, .N]),
    sprintf("- Preserved by facility-label safety: `%s`", diagnostics[review_preserved_by_facility_label == TRUE, .N]),
    sprintf("- Corridor candidates exported for QGIS review: `%s`", diagnostics[transport_corridor_candidate == TRUE, .N]),
    sprintf("- Candidate polygons with corridor label hints: `%s`", diagnostics[transport_corridor_candidate == TRUE & corridor_label_hint == TRUE, .N]),
    sprintf("- Candidate polygons without corridor label hints: `%s`", diagnostics[transport_corridor_candidate == TRUE & corridor_label_hint == FALSE, .N]),
    "",
    "Candidate count by semantic/type label:",
    "",
    md_table(candidate_by_type, n = 60),
    "",
    "Preserved safety-label geometries that passed the base geometry screen:",
    "",
    md_table(preserved_by_type, n = 60),
    "",
    "## Output Validation",
    "",
    md_table(validation),
    "",
    "## Facility Dataset Summary",
    "",
    md_table(final_by_category),
    "",
    "## Outputs",
    "",
    sprintf("- Transport diagnostics Parquet: `%s`", paths$diagnostics),
    sprintf("- Corridor candidate GPKG for QGIS inspection: `%s`", paths$corridor_candidates),
    sprintf("- Facility GeoPackage: `%s`", paths$facility_gpkg),
    sprintf("- Facility attributes Parquet: `%s`", paths$facility_attributes),
    sprintf("- Facility summary Parquet: `%s`", paths$facility_summary),
    "",
    "QGIS inspection path for candidate corridors:",
    "",
    sprintf("`%s`", paths$corridor_candidates),
    "",
    "QGIS inspection path for facility layer:",
    "",
    sprintf("`%s`", paths$facility_gpkg),
    "",
    "## Caveat",
    "",
    "The candidate corridor layer is intentionally conservative but should still be inspected in QGIS before treating the facility version as canonical for embedding. Some preserved transport polygons with facility labels remain geometrically elongated because their labels indicate stations, ports, parking, terminals, or similar facility-like sites.",
    "",
    sprintf("Runtime seconds: `%.2f`", as.numeric(difftime(Sys.time(), start_time, units = "secs")))
  )
  writeLines(lines, paths$report, useBytes = TRUE)
}

main <- function() {
  start_time <- Sys.time()
  stop_if_outputs_exist(paths, cfg$overwrite)

  log_msg("Reading cleaned Togieeum GPKG:", paths$input_gpkg)
  g <- sf::st_read(paths$input_gpkg, layer = "polygon_pois", quiet = TRUE)
  if (sf::st_crs(g)$epsg != cfg$target_crs) {
    g <- sf::st_transform(g, cfg$target_crs)
  }
  log_msg("Reading cleaned Togieeum attributes:", paths$input_attributes)
  attrs <- as.data.table(arrow::read_parquet(paths$input_attributes))

  if (!setequal(g$polygon_poi_id, attrs$polygon_poi_id)) {
    stop("Input GPKG and attribute Parquet polygon_poi_id sets do not match.", call. = FALSE)
  }
  attrs <- attrs[match(g$polygon_poi_id, polygon_poi_id)]
  if (!all(attrs$polygon_poi_id == g$polygon_poi_id)) {
    stop("Failed to align attributes to GPKG geometry order.", call. = FALSE)
  }

  transport_idx <- which(attrs$source_layer_code == "152" | attrs$major_category == "transportation_facility")
  transport_sf <- g[transport_idx, ]
  transport_attrs <- attrs[transport_idx]

  diagnostics <- calculate_transport_diagnostics(transport_sf, transport_attrs)
  arrow::write_parquet(diagnostics, paths$diagnostics)

  candidate_ids <- diagnostics[transport_corridor_candidate == TRUE, polygon_poi_id]
  candidate_idx <- which(g$polygon_poi_id %in% candidate_ids)
  facility_idx <- which(!g$polygon_poi_id %in% candidate_ids)

  candidate_cols <- c(
    "polygon_poi_id", "source_layer_code", "major_category", "major_category_ko",
    "semantic_type_key", "semantic_type_label_ko", "feature_label_ko", "region_sgg_code",
    "area_m2", "perimeter_m", "bbox_aspect_ratio", "compactness", "thinness",
    "approximate_width_m", "bbox_diagonal_m", "facility_label_safety",
    "corridor_label_hint", "extreme_corridor_geometry", "corridor_decision_reason"
  )
  candidate_attrs <- diagnostics[match(g$polygon_poi_id[candidate_idx], polygon_poi_id), ..candidate_cols]
  if (!all(candidate_attrs$polygon_poi_id == g$polygon_poi_id[candidate_idx])) {
    stop("Failed to align corridor candidate attributes to candidate geometry order.", call. = FALSE)
  }
  candidate_sf <- sf::st_sf(candidate_attrs, geometry = sf::st_geometry(g[candidate_idx, ]))
  sf::st_crs(candidate_sf) <- sf::st_crs(g)
  sf::st_write(candidate_sf, paths$corridor_candidates, layer = "corridor_candidates", delete_dsn = TRUE, quiet = TRUE)

  facility_attrs <- copy(attrs[facility_idx])
  facility_attrs[, transport_corridor_candidate_removed := FALSE]
  transport_diag_cols <- c(
    "polygon_poi_id", "perimeter_m", "bbox_width_m", "bbox_height_m", "bbox_aspect_ratio",
    "compactness", "thinness", "longest_bbox_side_m", "approximate_width_m",
    "bbox_diagonal_m", "facility_label_safety", "corridor_label_hint",
    "base_geometry_corridor_screen", "extreme_corridor_geometry",
    "review_preserved_by_facility_label", "corridor_decision_reason"
  )
  facility_attrs <- merge(
    facility_attrs,
    diagnostics[, ..transport_diag_cols],
    by = "polygon_poi_id",
    all.x = TRUE,
    sort = FALSE
  )
  setkey(facility_attrs, polygon_poi_id)
  facility_attrs <- facility_attrs[attrs[facility_idx, .(polygon_poi_id)], on = "polygon_poi_id"]
  arrow::write_parquet(facility_attrs, paths$facility_attributes)

  facility_summary <- facility_attrs[, .(
    feature_count = .N,
    total_area_m2 = round(sum(area_m2, na.rm = TRUE), 3),
    transport_corridor_candidates_removed = 0L
  ), by = .(major_category, major_category_ko, semantic_type_key, semantic_type_label_ko, source_shp, region_sgg_code)]
  removed_summary <- diagnostics[transport_corridor_candidate == TRUE, .(
    transport_corridor_candidates_removed = .N
  ), by = .(major_category, major_category_ko, semantic_type_key, semantic_type_label_ko, source_shp, region_sgg_code)]
  facility_summary <- merge(
    facility_summary,
    removed_summary,
    by = c("major_category", "major_category_ko", "semantic_type_key", "semantic_type_label_ko", "source_shp", "region_sgg_code"),
    all = TRUE,
    suffixes = c("", "_actual")
  )
  facility_summary[is.na(feature_count), `:=`(feature_count = 0L, total_area_m2 = 0)]
  facility_summary[!is.na(transport_corridor_candidates_removed_actual),
    transport_corridor_candidates_removed := transport_corridor_candidates_removed_actual
  ]
  facility_summary[, transport_corridor_candidates_removed_actual := NULL]
  arrow::write_parquet(facility_summary, paths$facility_summary)

  facility_gpkg_cols <- c(
    "polygon_poi_id", "major_category", "major_category_ko", "source_layer_code",
    "semantic_type_key", "semantic_type_label_ko", "feature_label_ko",
    "region_sgg_code", "area_m2"
  )
  facility_gpkg_cols <- facility_gpkg_cols[facility_gpkg_cols %in% names(facility_attrs)]
  facility_sf <- sf::st_sf(facility_attrs[, ..facility_gpkg_cols], geometry = sf::st_geometry(g[facility_idx, ]))
  sf::st_crs(facility_sf) <- sf::st_crs(g)
  sf::st_write(facility_sf, paths$facility_gpkg, layer = "polygon_pois_facility", delete_dsn = TRUE, quiet = TRUE)

  candidate_check <- sf::st_read(paths$corridor_candidates, layer = "corridor_candidates", quiet = TRUE)
  facility_check <- sf::st_read(paths$facility_gpkg, layer = "polygon_pois_facility", quiet = TRUE)
  facility_attr_check <- as.data.table(arrow::read_parquet(paths$facility_attributes))
  diagnostics_check <- as.data.table(arrow::read_parquet(paths$diagnostics))
  validation <- data.table(
    check = c(
      "input_cleaned_features",
      "transportation_features_evaluated",
      "diagnostics_rows",
      "corridor_candidate_gpkg_rows",
      "facility_gpkg_rows",
      "facility_attribute_rows",
      "candidate_plus_facility_equals_input",
      "facility_ids_unique",
      "candidate_ids_unique",
      "facility_gpkg_attributes_id_sets_equal",
      "facility_invalid_geometries",
      "candidate_invalid_geometries",
      "facility_empty_geometries",
      "candidate_empty_geometries",
      "facility_zero_area_geometries",
      "candidate_zero_area_geometries",
      "facility_crs_epsg",
      "candidate_crs_epsg"
    ),
    value = c(
      as.character(nrow(g)),
      as.character(length(transport_idx)),
      as.character(nrow(diagnostics_check)),
      as.character(nrow(candidate_check)),
      as.character(nrow(facility_check)),
      as.character(nrow(facility_attr_check)),
      as.character(nrow(candidate_check) + nrow(facility_check) == nrow(g)),
      as.character(!anyDuplicated(facility_check$polygon_poi_id)),
      as.character(!anyDuplicated(candidate_check$polygon_poi_id)),
      as.character(setequal(facility_check$polygon_poi_id, facility_attr_check$polygon_poi_id)),
      as.character(sum(!sf::st_is_valid(facility_check), na.rm = TRUE)),
      as.character(sum(!sf::st_is_valid(candidate_check), na.rm = TRUE)),
      as.character(sum(sf::st_is_empty(facility_check))),
      as.character(sum(sf::st_is_empty(candidate_check))),
      as.character(sum(as.numeric(sf::st_area(facility_check)) <= 0)),
      as.character(sum(as.numeric(sf::st_area(candidate_check)) <= 0)),
      as.character(sf::st_crs(facility_check)$epsg),
      as.character(sf::st_crs(candidate_check)$epsg)
    )
  )

  if (!identical(validation[check == "candidate_plus_facility_equals_input", value], "TRUE") ||
      !identical(validation[check == "facility_ids_unique", value], "TRUE") ||
      !identical(validation[check == "candidate_ids_unique", value], "TRUE") ||
      !identical(validation[check == "facility_gpkg_attributes_id_sets_equal", value], "TRUE")) {
    stop("Output validation failed for row partition or ID consistency.", call. = FALSE)
  }
  if (any(as.integer(validation[check %in% c(
    "facility_invalid_geometries", "candidate_invalid_geometries",
    "facility_empty_geometries", "candidate_empty_geometries",
    "facility_zero_area_geometries", "candidate_zero_area_geometries"
  ), value]) > 0)) {
    stop("Output validation failed for geometry quality.", call. = FALSE)
  }

  write_report(diagnostics, attrs, facility_attrs, validation, paths, start_time)

  log_msg("Done.")
  log_msg("Transport diagnostics:", paths$diagnostics)
  log_msg("Corridor candidates:", paths$corridor_candidates)
  log_msg("Facility GPKG:", paths$facility_gpkg)
  log_msg("Facility attributes:", paths$facility_attributes)
  log_msg("Facility summary:", paths$facility_summary)
  log_msg("Report:", paths$report)
}

main()
