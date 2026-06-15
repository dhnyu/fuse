#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
  library(digest)
  library(parallel)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || all(is.na(x)) || identical(x, "")) y else x
}

clean_string <- function(x) {
  x <- as.character(x)
  x <- trimws(x)
  x[x == ""] <- NA_character_
  x
}

coalesce_chr <- function(...) {
  vals <- list(...)
  if (!length(vals)) return(character())
  out <- clean_string(vals[[1]])
  if (length(vals) > 1) {
    for (v in vals[-1]) {
      v <- clean_string(v)
      replace <- is.na(out) & !is.na(v)
      out[replace] <- v[replace]
    }
  }
  out
}

parse_args <- function(args) {
  out <- list(
    canonical_dir = path.expand(Sys.getenv("OSM_CANONICAL_DIR", "~/fusedatalarge/osm/canonical")),
    report_dir = path.expand(Sys.getenv("FUSE_REPORT_DIR", "~/fuse/reports")),
    workers = as.integer(Sys.getenv("OSM_POLYGON_POI_WORKERS", "40")),
    target_crs = as.integer(Sys.getenv("OSM_POLYGON_POI_TARGET_CRS", "5186")),
    overwrite = FALSE,
    max_nested_group_size = as.integer(Sys.getenv("OSM_POLYGON_POI_MAX_NESTED_GROUP_SIZE", "50000")),
    nested_chunk_size = as.integer(Sys.getenv("OSM_POLYGON_POI_NESTED_CHUNK_SIZE", "5000"))
  )

  i <- 1L
  while (i <= length(args)) {
    arg <- args[[i]]
    if (identical(arg, "--overwrite")) out$overwrite <- TRUE
    if (identical(arg, "--canonical-dir") && i < length(args)) {
      i <- i + 1L
      out$canonical_dir <- path.expand(args[[i]])
    }
    if (identical(arg, "--report-dir") && i < length(args)) {
      i <- i + 1L
      out$report_dir <- path.expand(args[[i]])
    }
    if (identical(arg, "--workers") && i < length(args)) {
      i <- i + 1L
      out$workers <- as.integer(args[[i]])
    }
    i <- i + 1L
  }

  out$workers <- max(1L, min(40L, out$workers, parallel::detectCores(logical = TRUE)))
  out
}

cfg <- parse_args(commandArgs(trailingOnly = TRUE))

gpkg_dir <- file.path(cfg$canonical_dir, "gpkg")
parquet_dir <- file.path(cfg$canonical_dir, "parquet")
dir.create(gpkg_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(parquet_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(cfg$report_dir, recursive = TRUE, showWarnings = FALSE)

run_stamp <- format(Sys.time(), "%Y%m%d_%H%M")
paths <- list(
  input_gpkg = file.path(gpkg_dir, "korea_pois_polygon.gpkg"),
  input_parquet = file.path(parquet_dir, "korea_pois_polygon.parquet"),
  output_gpkg = file.path(gpkg_dir, "korea_osm_polygon_poi_cleaned.gpkg"),
  output_attributes = file.path(parquet_dir, "korea_osm_polygon_poi_cleaned_attributes.parquet"),
  output_summary = file.path(parquet_dir, "korea_osm_polygon_poi_cleaned_summary.parquet"),
  report = file.path(cfg$report_dir, paste0(run_stamp, "_osm_polygon_poi_cleaning_report.md")),
  log = file.path(cfg$canonical_dir, "korea_osm_polygon_poi_cleaning.log")
)

log_con <- file(paths$log, open = "at", encoding = "UTF-8")
on.exit(close(log_con), add = TRUE)

log_msg <- function(...) {
  msg <- sprintf("[%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), paste(..., collapse = " "))
  cat(msg, "\n")
  writeLines(msg, log_con, useBytes = TRUE)
  flush(log_con)
}

stop_if_outputs_exist <- function(paths, overwrite = FALSE) {
  output_paths <- unlist(paths[c("output_gpkg", "output_attributes", "output_summary", "report")], use.names = FALSE)
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

discover_related_files <- function(canonical_dir) {
  osm_root <- dirname(canonical_dir)
  canonical_files <- list.files(canonical_dir, recursive = TRUE, full.names = TRUE, all.files = FALSE)
  metadata_dir <- file.path(osm_root, "metadata")
  metadata_files <- if (dir.exists(metadata_dir)) {
    list.files(metadata_dir, recursive = TRUE, full.names = TRUE, all.files = FALSE)
  } else {
    character()
  }
  files <- unique(c(canonical_files, metadata_files))
  info <- file.info(files)
  data.table(
    path = normalizePath(files, winslash = "/", mustWork = FALSE),
    size_bytes = as.numeric(info$size),
    role = fifelse(grepl("korea_pois_polygon", basename(files)), "nationwide polygon POI input/sidecar",
      fifelse(grepl("polygon", basename(files), ignore.case = TRUE), "related polygon POI file",
        fifelse(grepl("metadata|summary|distribution|validation|mapping", files, ignore.case = TRUE), "metadata/summary/validation",
          fifelse(grepl("point", basename(files), ignore.case = TRUE), "point POI file excluded", "other canonical OSM file")
        )
      )
    )
  )[order(path)]
}

get_gpkg_layers <- function(path) {
  layers <- sf::st_layers(path)
  as.character(layers$name)
}

read_input <- function(paths) {
  if (!file.exists(paths$input_gpkg)) stop("Input GPKG not found: ", paths$input_gpkg, call. = FALSE)
  layer <- if ("korea_pois_polygon" %in% get_gpkg_layers(paths$input_gpkg)) "korea_pois_polygon" else get_gpkg_layers(paths$input_gpkg)[1]
  log_msg("Reading input GPKG:", paths$input_gpkg, "layer:", layer)
  x <- sf::st_read(paths$input_gpkg, layer = layer, quiet = TRUE, stringsAsFactors = FALSE)
  parquet <- NULL
  if (file.exists(paths$input_parquet)) {
    log_msg("Reading input parquet sidecar:", paths$input_parquet)
    parquet <- as.data.table(arrow::read_parquet(paths$input_parquet))
  }
  list(sf = x, parquet = parquet, layer = layer)
}

safe_make_valid <- function(x) {
  if (requireNamespace("lwgeom", quietly = TRUE)) {
    out <- try(lwgeom::st_make_valid(x), silent = TRUE)
    if (!inherits(out, "try-error")) return(out)
  }
  out <- try(sf::st_make_valid(x), silent = TRUE)
  if (!inherits(out, "try-error")) return(out)
  sf::st_buffer(x, 0)
}

hash_geometry <- function(geom) {
  wkb <- sf::st_as_binary(geom, EWKB = TRUE)
  vapply(wkb, digest, character(1), algo = "xxhash64", serialize = FALSE)
}

make_clean_ids <- function(dt, geom_hash) {
  base <- paste(
    coalesce_chr(dt$poi_id, dt$osm_id, dt$osm_way_id, dt$row_id),
    coalesce_chr(dt$major_category, "unknown"),
    coalesce_chr(dt$semantic_type_key, "unknown"),
    geom_hash,
    sep = "|"
  )
  paste0("osmp_", vapply(base, digest, character(1), algo = "xxhash64", serialize = FALSE))
}

priority_tags <- c(
  "amenity", "shop", "tourism", "leisure", "office", "craft", "healthcare",
  "historic", "public_transport", "railway", "highway", "aeroway",
  "man_made", "building", "landuse", "natural", "boundary"
)

major_category_ko_map <- c(
  amenity = "편의시설",
  shop = "상업시설",
  tourism = "관광시설",
  leisure = "여가시설",
  office = "업무시설",
  craft = "수공업시설",
  healthcare = "보건의료시설",
  historic = "역사문화시설",
  public_transport = "대중교통시설",
  railway = "철도시설",
  highway = "도로시설",
  aeroway = "항공시설",
  man_made = "인공구조물",
  building = "건물",
  landuse = "토지이용",
  natural = "자연지형",
  boundary = "경계"
)

derive_classification <- function(dt) {
  for (tag in priority_tags) {
    if (!tag %in% names(dt)) dt[, (tag) := NA_character_]
    dt[, (tag) := clean_string(get(tag))]
  }

  if ("poi_class" %in% names(dt) && "poi_type" %in% names(dt)) {
    dt[, poi_class := clean_string(poi_class)]
    dt[, poi_type := clean_string(poi_type)]
  } else {
    dt[, `:=`(poi_class = NA_character_, poi_type = NA_character_)]
  }

  tag_matrix <- as.matrix(dt[, ..priority_tags])
  nonempty <- !is.na(tag_matrix) & tag_matrix != ""
  first_idx <- max.col(nonempty, ties.method = "first")
  has_tag <- rowSums(nonempty) > 0
  derived_key <- rep(NA_character_, nrow(dt))
  derived_value <- rep(NA_character_, nrow(dt))
  derived_key[has_tag] <- priority_tags[first_idx[has_tag]]
  derived_value[has_tag] <- tag_matrix[cbind(which(has_tag), first_idx[has_tag])]

  dt[, primary_tag_key := coalesce_chr(poi_class, derived_key)]
  dt[, primary_tag_value := coalesce_chr(poi_type, derived_value)]
  dt[, classification_source := fifelse(!is.na(poi_class) & !is.na(poi_type), "existing_poi_class_poi_type", "derived_from_priority_osm_tags")]
  dt[, major_category := primary_tag_key]
  dt[, major_category_ko := unname(major_category_ko_map[major_category])]
  dt[is.na(major_category_ko), major_category_ko := major_category]
  dt[, subcategory := primary_tag_value]
  dt[, subcategory_ko := NA_character_]
  dt[, semantic_type_key := fifelse(!is.na(major_category) & !is.na(subcategory), paste0(major_category, "=", subcategory), NA_character_)]
  dt[, semantic_type_label := semantic_type_key]
  dt[]
}

clean_geometry <- function(x, target_crs) {
  original_crs <- sf::st_crs(x)
  original_geom_type <- as.character(sf::st_geometry_type(x, by_geometry = TRUE))
  original_valid <- sf::st_is_valid(x)
  original_valid[is.na(original_valid)] <- FALSE
  original_empty <- sf::st_is_empty(x)

  if (is.na(original_crs)) stop("Input CRS is missing; refusing to guess for canonical OSM layer.", call. = FALSE)

  if (!identical(original_crs$epsg, target_crs)) {
    x <- sf::st_transform(x, target_crs)
  }
  x <- safe_make_valid(x)
  x <- suppressWarnings(sf::st_collection_extract(x, "POLYGON"))
  geom_type <- as.character(sf::st_geometry_type(x, by_geometry = TRUE))
  keep_polygon <- geom_type %chin% c("POLYGON", "MULTIPOLYGON")
  keep_nonempty <- !sf::st_is_empty(x)
  x <- x[keep_polygon & keep_nonempty, , drop = FALSE]
  if (!nrow(x)) stop("No polygon features remained after geometry repair and extraction.", call. = FALSE)

  x <- sf::st_cast(x, "MULTIPOLYGON", warn = FALSE)
  area_m2 <- as.numeric(sf::st_area(x))
  x$area_m2 <- area_m2
  x$zero_area <- !is.finite(area_m2) | area_m2 <= 0
  x <- x[!x$zero_area, , drop = FALSE]

  attr(x, "geometry_qc") <- list(
    original_crs_epsg = original_crs$epsg %||% NA_integer_,
    original_crs_input = original_crs$input %||% NA_character_,
    original_feature_count = length(original_geom_type),
    original_geometry_types = data.table(geometry_type = original_geom_type)[, .N, by = geometry_type][order(-N)],
    original_invalid = sum(!original_valid, na.rm = TRUE),
    original_empty = sum(original_empty, na.rm = TRUE),
    final_geometry_types = data.table(geometry_type = as.character(sf::st_geometry_type(x, by_geometry = TRUE)))[, .N, by = geometry_type][order(-N)],
    final_crs_epsg = sf::st_crs(x)$epsg %||% NA_integer_
  )
  x
}

remove_exact_and_near_duplicates <- function(attrs) {
  attrs[, exact_duplicate_removed := duplicated(paste(major_category, semantic_type_key, geom_hash, sep = "|"))]
  attrs[, near_duplicate_key := paste(
    major_category,
    semantic_type_key,
    round(area_m2, 1),
    round(xmin, 1),
    round(ymin, 1),
    round(xmax, 1),
    round(ymax, 1),
    sep = "|"
  )]
  attrs[, near_duplicate_removed := FALSE]
  remaining <- !attrs$exact_duplicate_removed
  attrs[remaining, near_duplicate_removed := duplicated(near_duplicate_key)]
  attrs[]
}

within_group_nested <- function(group_rows, attrs, geom, chunk_size) {
  rows <- group_rows
  if (length(rows) < 2L) return(integer())
  group_geom <- geom[rows]
  group_area <- attrs$area_m2[rows]
  remove_local <- logical(length(rows))
  chunks <- split(seq_along(rows), ceiling(seq_along(rows) / chunk_size))

  for (chunk in chunks) {
    rel <- sf::st_within(group_geom[chunk], group_geom, sparse = TRUE)
    for (i in seq_along(rel)) {
      matches <- rel[[i]]
      if (!length(matches)) next
      self <- chunk[[i]]
      matches <- setdiff(matches, self)
      if (!length(matches)) next
      if (any(group_area[matches] >= group_area[self], na.rm = TRUE)) {
        remove_local[self] <- TRUE
      }
    }
  }

  rows[remove_local]
}

remove_nested_polygons <- function(attrs, geom, workers, max_group_size, chunk_size) {
  candidates <- attrs[!exact_duplicate_removed & !near_duplicate_removed & !is.na(major_category) & !is.na(semantic_type_key),
    .(row_id, group_key = paste(major_category, semantic_type_key, sep = "|"))]
  group_sizes <- candidates[, .N, by = group_key][order(-N)]
  if (!nrow(group_sizes)) return(list(rows = integer(), skipped = data.table()))

  skipped <- group_sizes[N > max_group_size]
  process_groups <- group_sizes[N <= max_group_size]
  row_groups <- split(candidates$row_id, candidates$group_key)
  row_groups <- row_groups[process_groups$group_key]

  log_msg("Running nested-polygon removal on", length(row_groups), "same-category/type groups with", workers, "workers")
  if (nrow(skipped)) {
    log_msg("Skipping", nrow(skipped), "groups larger than max_nested_group_size", max_group_size)
  }

  if (workers > 1L && length(row_groups) > 1L && .Platform$OS.type != "windows") {
    nested <- parallel::mclapply(
      row_groups,
      within_group_nested,
      attrs = attrs,
      geom = geom,
      chunk_size = chunk_size,
      mc.cores = min(workers, length(row_groups))
    )
  } else {
    nested <- lapply(row_groups, within_group_nested, attrs = attrs, geom = geom, chunk_size = chunk_size)
  }

  list(rows = sort(unique(unlist(nested, use.names = FALSE))), skipped = skipped)
}

fmt_dt <- function(dt, n = Inf) {
  if (!nrow(dt)) return("_No rows._")
  paste(capture.output(print(dt[seq_len(min(nrow(dt), n))])), collapse = "\n")
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

write_report <- function(
  paths, cfg, related_files, input_info, tag_diagnostics, class_decision,
  attrs_after_geom, attrs_final, summary_dt, top_semantic, validation, nested_skipped,
  start_time
) {
  qc <- input_info$geometry_qc
  by_category <- attrs_final[, .(feature_count = .N, total_area_m2 = round(sum(area_m2, na.rm = TRUE), 3)),
    by = .(major_category, major_category_ko)][order(-feature_count)]
  by_category_before <- attrs_after_geom[, .(feature_count = .N, total_area_m2 = round(sum(area_m2, na.rm = TRUE), 3)),
    by = .(major_category, major_category_ko)][order(-feature_count)]

  lines <- c(
    "# OSM Polygon POI Cleaning Report",
    "",
    sprintf("Generated: `%s`", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
    sprintf("Script: `%s`", normalizePath(sys.frame(1)$ofile %||% "scripts/poi/clean_osm_polygon_pois.R", winslash = "/", mustWork = FALSE)),
    "",
    "## Objective",
    "",
    "Clean and standardize the existing nationwide OpenStreetMap polygon POI dataset, inspect available OSM classification fields, and remove duplicate or nested polygon POIs within the same semantic class. Point POIs were not used.",
    "",
    "## Input Discovery",
    "",
    sprintf("- OSM canonical directory: `%s`", normalizePath(cfg$canonical_dir, winslash = "/", mustWork = FALSE)),
    sprintf("- Input polygon GPKG: `%s`", paths$input_gpkg),
    sprintf("- Input polygon Parquet sidecar: `%s`", paths$input_parquet),
    sprintf("- Input layer: `%s`", input_info$layer),
    sprintf("- Input feature count: `%s`", input_info$input_n),
    sprintf("- Input CRS: EPSG:%s", qc$original_crs_epsg),
    sprintf("- Final CRS: EPSG:%s", qc$final_crs_epsg),
    "",
    "Related canonical OSM files:",
    "",
    md_table(related_files[, .(path, size_bytes, role)]),
    "",
    "Input geometry types:",
    "",
    md_table(qc$original_geometry_types),
    "",
    "Final geometry types after cleaning:",
    "",
    md_table(qc$final_geometry_types),
    "",
    "## Classification Fields",
    "",
    "The existing canonical OSM polygon output already contains `poi_class` and `poi_type`, created by the upstream OSM POI extraction workflow from OSM semantic tags. Because every input polygon has both fields populated, this cleaner uses them as the canonical classification. The broader priority-tag fallback is implemented but was not needed for the current input.",
    "",
    "Available OSM tag/classification fields:",
    "",
    md_table(tag_diagnostics),
    "",
    "Classification decision:",
    "",
    md_table(class_decision),
    "",
    "Derived fields:",
    "",
    "- `major_category = poi_class` when available, otherwise the first populated priority tag key.",
    "- `subcategory = poi_type` when available, otherwise the first populated priority tag value.",
    "- `semantic_type_key = paste0(major_category, \"=\", subcategory)`.",
    "- `semantic_type_label` is the English OSM semantic key/value string. A comprehensive reliable Korean mapping for OSM subcategory values is not available, so `subcategory_ko` is left missing. Coarse Korean labels are provided only for the major OSM tag key.",
    "",
    "## Geometry Cleaning",
    "",
    sprintf("- Original invalid geometries: `%s`", qc$original_invalid),
    sprintf("- Original empty geometries: `%s`", qc$original_empty),
    sprintf("- Feature count after geometry cleaning: `%s`", nrow(attrs_after_geom)),
    sprintf("- CRS standardized to: EPSG:%s", qc$final_crs_epsg),
    "",
    "Geometry cleaning used `st_make_valid` where available, polygon extraction from geometry collections, removal of empty/non-polygon/zero-area geometries, and normalization to `MULTIPOLYGON`.",
    "",
    "## Duplicate And Nested Removal",
    "",
    sprintf("- Exact duplicate features removed: `%s`", attrs_after_geom[exact_duplicate_removed == TRUE, .N]),
    sprintf("- Near-identical duplicate features removed: `%s`", attrs_after_geom[near_duplicate_removed == TRUE, .N]),
    sprintf("- Nested contained features removed: `%s`", attrs_after_geom[nested_removed == TRUE, .N]),
    sprintf("- Final feature count: `%s`", nrow(attrs_final)),
    "",
    "Duplicate and containment removal was restricted to features with the same `major_category` and the same `semantic_type_key`. Near-identical duplicate removal used a conservative key based on same semantic class, area rounded to 0.1 square meters, and bounding box coordinates rounded to 0.1 meters.",
    "",
    if (nrow(nested_skipped)) {
      c("Nested-removal skipped groups larger than the configured bound:", "", md_table(nested_skipped))
    } else {
      "No semantic groups were skipped by the nested-polygon removal bound."
    },
    "",
    "## Feature Counts And Area By Major Category",
    "",
    "Before duplicate/nested removal:",
    "",
    md_table(by_category_before),
    "",
    "After duplicate/nested removal:",
    "",
    md_table(by_category),
    "",
    "## Top Semantic Types",
    "",
    md_table(top_semantic, n = 40),
    "",
    "## Output Validation",
    "",
    md_table(validation),
    "",
    "## Outputs",
    "",
    sprintf("- Cleaned GeoPackage: `%s`", paths$output_gpkg),
    sprintf("- Attribute Parquet: `%s`", paths$output_attributes),
    sprintf("- Summary Parquet: `%s`", paths$output_summary),
    sprintf("- Log: `%s`", paths$log),
    "",
    "QGIS inspection path:",
    "",
    sprintf("`%s`", paths$output_gpkg),
    "",
    "## Limitations And Follow-up",
    "",
    "- Korean labels are reliable only at the coarse OSM tag-key level. OSM subcategory values are retained in English because a comprehensive project-approved Korean OSM tag dictionary was not available.",
    "- Containment removal is semantic-class bounded. This intentionally preserves nested polygons across different OSM classes, such as a park containing a restaurant or a school containing a playground.",
    "- The output CRS follows current project policy (`EPSG:5186`). If this OSM polygon layer becomes a long-lived national distribution product, an additional EPSG:5179 export may be useful, matching the recommendation made for the Togieeum polygon POI layer.",
    sprintf("- Runtime seconds: `%.2f`", as.numeric(difftime(Sys.time(), start_time, units = "secs")))
  )

  writeLines(lines, paths$report, useBytes = TRUE)
}

main <- function() {
  start_time <- Sys.time()
  stop_if_outputs_exist(paths, cfg$overwrite)

  log_msg("Starting OSM polygon POI cleaning")
  log_msg("Canonical dir:", cfg$canonical_dir)
  log_msg("Workers:", cfg$workers)
  log_msg("Target CRS: EPSG", cfg$target_crs)

  related_files <- discover_related_files(cfg$canonical_dir)
  input <- read_input(paths)
  x <- input$sf
  input_n <- nrow(x)

  input_parquet <- input$parquet
  if (!is.null(input_parquet)) {
    if (!"poi_id" %in% names(input_parquet) || !"poi_id" %in% names(x)) {
      log_msg("Parquet sidecar exists but poi_id join field is missing in one input; using GPKG attributes as authoritative.")
    } else if (nrow(input_parquet) != nrow(x)) {
      log_msg("Parquet sidecar row count differs from GPKG; using GPKG attributes as authoritative.")
    }
  }

  tag_fields <- c("poi_class", "poi_type", priority_tags, "name", "name_ko", "name_en", "osm_id", "osm_way_id", "other_tags")
  tag_diagnostics <- rbindlist(lapply(tag_fields, function(field) {
    if (!field %in% names(x)) {
      data.table(field = field, available = FALSE, nonempty_features = 0L, unique_values = 0L)
    } else {
      vals <- clean_string(sf::st_drop_geometry(x)[[field]])
      data.table(field = field, available = TRUE, nonempty_features = sum(!is.na(vals)), unique_values = uniqueN(vals[!is.na(vals)]))
    }
  }))

  cleaned <- clean_geometry(x, cfg$target_crs)
  qc <- attr(cleaned, "geometry_qc")
  attrs <- as.data.table(sf::st_drop_geometry(cleaned))
  geoms <- sf::st_geometry(cleaned)
  sf::st_crs(geoms) <- cfg$target_crs
  rm(x, cleaned)
  gc(verbose = FALSE)

  attrs[, row_id := seq_len(.N)]
  attrs[, source_file := basename(paths$input_gpkg)]
  attrs[, source_layer := input$layer]
  for (nm in c("addr_city", "addr_district", "addr_subdistrict")) {
    if (!nm %in% names(attrs)) attrs[, (nm) := NA_character_]
  }
  attrs[, region_label := coalesce_chr(addr_district, addr_city, addr_subdistrict)]
  attrs <- derive_classification(attrs)

  class_decision <- attrs[, .N, by = classification_source][order(-N)]
  class_decision[, share := round(N / sum(N), 6)]

  attrs[, geom_hash := hash_geometry(geoms)]
  attrs[, polygon_poi_id := make_clean_ids(attrs, geom_hash)]

  bboxes <- do.call(rbind, lapply(geoms, function(g) as.numeric(sf::st_bbox(g))))
  colnames(bboxes) <- c("xmin", "ymin", "xmax", "ymax")
  attrs[, `:=`(
    xmin = bboxes[, "xmin"],
    ymin = bboxes[, "ymin"],
    xmax = bboxes[, "xmax"],
    ymax = bboxes[, "ymax"]
  )]
  rm(bboxes)

  attrs_after_geom <- remove_exact_and_near_duplicates(copy(attrs))
  attrs_after_geom[, nested_removed := FALSE]
  nested <- remove_nested_polygons(
    attrs_after_geom,
    geoms,
    workers = cfg$workers,
    max_group_size = cfg$max_nested_group_size,
    chunk_size = cfg$nested_chunk_size
  )
  if (length(nested$rows)) attrs_after_geom[row_id %in% nested$rows, nested_removed := TRUE]

  keep <- !attrs_after_geom$exact_duplicate_removed &
    !attrs_after_geom$near_duplicate_removed &
    !attrs_after_geom$nested_removed

  attrs_final <- copy(attrs_after_geom[keep])
  geoms_final <- geoms[keep]
  attrs_final[, `:=`(
    cleaned_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
    target_crs_epsg = cfg$target_crs
  )]

  summary_before <- attrs_after_geom[, .(
    input_feature_count_after_geometry = .N,
    input_total_area_m2 = sum(area_m2, na.rm = TRUE)
  ), by = .(major_category, semantic_type_key, source_file, source_layer, region_label)]
  summary_removed <- attrs_after_geom[, .(
    exact_duplicate_removed = sum(exact_duplicate_removed, na.rm = TRUE),
    near_duplicate_removed = sum(near_duplicate_removed, na.rm = TRUE),
    nested_removed = sum(nested_removed, na.rm = TRUE)
  ), by = .(major_category, semantic_type_key, source_file, source_layer, region_label)]
  summary_final <- attrs_final[, .(
    cleaned_feature_count = .N,
    cleaned_total_area_m2 = sum(area_m2, na.rm = TRUE)
  ), by = .(major_category, semantic_type_key, source_file, source_layer, region_label)]
  summary_keys <- c("major_category", "semantic_type_key", "source_file", "source_layer", "region_label")
  summary_dt <- merge(summary_before, summary_removed, by = summary_keys, all = TRUE)
  summary_dt <- merge(summary_dt, summary_final, by = summary_keys, all = TRUE)
  for (nm in names(summary_dt)) {
    if (is.numeric(summary_dt[[nm]]) || is.integer(summary_dt[[nm]])) {
      set(summary_dt, which(is.na(summary_dt[[nm]])), nm, 0)
    }
  }

  attr_out <- copy(attrs_final)
  if ("near_duplicate_key" %in% names(attr_out)) attr_out[, near_duplicate_key := NULL]
  arrow::write_parquet(attr_out, paths$output_attributes)
  arrow::write_parquet(summary_dt, paths$output_summary)

  gpkg_cols <- unique(c(
    "polygon_poi_id", "poi_id", "osm_id", "osm_way_id", "major_category",
    "major_category_ko", "subcategory", "semantic_type_key", "semantic_type_label",
    "name", "name_ko", "source_file", "source_layer", "region_label", "area_m2"
  ))
  gpkg_cols <- gpkg_cols[gpkg_cols %in% names(attrs_final)]
  geom_out <- sf::st_sf(attrs_final[, ..gpkg_cols], geometry = geoms_final)
  sf::st_write(geom_out, paths$output_gpkg, layer = "polygon_pois", delete_dsn = TRUE, quiet = TRUE)

  gpkg_check <- sf::st_read(paths$output_gpkg, layer = "polygon_pois", quiet = TRUE)
  attr_check <- as.data.table(arrow::read_parquet(paths$output_attributes))
  validation <- data.table(
    check = c(
      "input_feature_count",
      "feature_count_after_geometry_cleaning",
      "final_gpkg_rows",
      "final_parquet_rows",
      "gpkg_unique_polygon_poi_id",
      "parquet_unique_polygon_poi_id",
      "gpkg_parquet_id_sets_equal",
      "invalid_final_geometries",
      "empty_final_geometries",
      "zero_area_final_geometries",
      "final_crs_epsg"
    ),
    value = c(
      as.character(input_n),
      as.character(nrow(attrs_after_geom)),
      as.character(nrow(gpkg_check)),
      as.character(nrow(attr_check)),
      as.character(uniqueN(gpkg_check$polygon_poi_id)),
      as.character(uniqueN(attr_check$polygon_poi_id)),
      as.character(setequal(gpkg_check$polygon_poi_id, attr_check$polygon_poi_id)),
      as.character(sum(!sf::st_is_valid(gpkg_check), na.rm = TRUE)),
      as.character(sum(sf::st_is_empty(gpkg_check))),
      as.character(sum(as.numeric(sf::st_area(gpkg_check)) <= 0)),
      as.character(sf::st_crs(gpkg_check)$epsg %||% NA_integer_)
    )
  )

  if (validation[check == "final_gpkg_rows", value] != validation[check == "final_parquet_rows", value]) {
    stop("Validation failed: GPKG and Parquet row counts differ.", call. = FALSE)
  }
  if (!identical(validation[check == "gpkg_parquet_id_sets_equal", value], "TRUE")) {
    stop("Validation failed: GPKG and Parquet ID sets differ.", call. = FALSE)
  }
  if (as.integer(validation[check == "gpkg_unique_polygon_poi_id", value]) != nrow(gpkg_check) ||
      as.integer(validation[check == "parquet_unique_polygon_poi_id", value]) != nrow(attr_check)) {
    stop("Validation failed: polygon_poi_id is not unique.", call. = FALSE)
  }
  if (as.integer(validation[check == "invalid_final_geometries", value]) > 0 ||
      as.integer(validation[check == "empty_final_geometries", value]) > 0 ||
      as.integer(validation[check == "zero_area_final_geometries", value]) > 0) {
    stop("Validation failed: final geometries include invalid, empty, or zero-area records.", call. = FALSE)
  }

  top_semantic <- attrs_final[, .(feature_count = .N, total_area_m2 = round(sum(area_m2, na.rm = TRUE), 3)),
    by = .(major_category, semantic_type_key)][order(-feature_count)][1:min(.N, 50)]

  input_info <- list(
    layer = input$layer,
    input_n = input_n,
    geometry_qc = qc
  )

  write_report(
    paths = paths,
    cfg = cfg,
    related_files = related_files,
    input_info = input_info,
    tag_diagnostics = tag_diagnostics,
    class_decision = class_decision,
    attrs_after_geom = attrs_after_geom,
    attrs_final = attrs_final,
    summary_dt = summary_dt,
    top_semantic = top_semantic,
    validation = validation,
    nested_skipped = nested$skipped,
    start_time = start_time
  )

  log_msg("Done.")
  log_msg("Output GeoPackage:", paths$output_gpkg)
  log_msg("Output attributes:", paths$output_attributes)
  log_msg("Output summary:", paths$output_summary)
  log_msg("Report:", paths$report)
}

main()
