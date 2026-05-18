#!/usr/bin/env Rscript

# Build semantic OpenStreetMap POI datasets for Seoul.
#
# The project no longer treats OSM as a general geometry foundation layer.
# Geometry-heavy representation learning from raw OSM lines and polygon
# coordinate hierarchies was abandoned because the current research direction is
# semantic place representation, multimodal fusion with Street View imagery, and
# later integration with authoritative building geometry. In this workflow OSM
# is primarily a semantic/place-information source: POI tags provide useful
# anchors for urban scene similarity, place meaning, and future image-text-place
# fusion, while high-quality building geometry will come from external datasets.

suppressPackageStartupMessages({
  library(osmextract)
  library(sf)
  library(tidyverse)
  library(arrow)
  library(fs)
  library(cli)
  library(future)
  library(future.mirai)
  library(furrr)
})

sf::sf_use_s2(FALSE)

target_crs <- 5186
parallel_workers <- 40L
chunk_size <- 10000L
extraction_timestamp <- format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")

options(future.globals.maxSize = 500 * 1024^3)

priority_order <- c(
  "amenity",
  "shop",
  "tourism",
  "leisure",
  "office",
  "healthcare",
  "public_transport",
  "craft",
  "man_made"
)

extra_tags <- unique(c(
  priority_order,
  "name", "name:ko", "name:en", "alt_name", "official_name",
  "brand", "operator", "network", "branch", "ref",
  "addr:city", "addr:district", "addr:subdistrict", "addr:housenumber",
  "addr:street", "addr:postcode", "addr:full",
  "cuisine", "opening_hours", "phone", "contact:phone", "website",
  "contact:website", "email", "contact:email",
  "wheelchair", "internet_access", "delivery", "takeaway", "drive_through",
  "capacity", "level", "indoor", "building", "building:levels",
  "historic", "sport", "religion", "denomination", "emergency",
  "fee", "access", "entrance"
))

paths <- list(
  pbf = "data/osm/raw/geofabrik_south-korea-latest.osm.pbf",
  gadm_dir = "data/geodata/gadm",
  canonical_gpkg_dir = "data/osm/canonical/gpkg",
  canonical_parquet_dir = "data/osm/canonical/parquet",
  metadata_dir = "data/osm/metadata",
  logs_dir = "data/osm/logs",
  tmp_dir = "data/osm/tmp"
)

outputs <- list(
  gpkg_point = file.path(paths$canonical_gpkg_dir, "seoul_pois_point.gpkg"),
  gpkg_polygon = file.path(paths$canonical_gpkg_dir, "seoul_pois_polygon.gpkg"),
  parquet_point = file.path(paths$canonical_parquet_dir, "seoul_pois_point.parquet"),
  parquet_polygon = file.path(paths$canonical_parquet_dir, "seoul_pois_polygon.parquet"),
  poi_id_mapping = file.path(paths$metadata_dir, "poi_id_mapping.parquet"),
  layer_summary = file.path(paths$metadata_dir, "layer_summary.parquet"),
  poi_class_distribution = file.path(paths$metadata_dir, "poi_class_distribution.parquet"),
  poi_type_distribution = file.path(paths$metadata_dir, "poi_type_distribution.parquet"),
  log = file.path(paths$logs_dir, "extraction.log")
)

work_paths <- list(
  pbf = file.path(paths$tmp_dir, "seoul_osm_poi_extract.osm.pbf")
)

fs::dir_create(c(
  paths$canonical_gpkg_dir,
  paths$canonical_parquet_dir,
  paths$metadata_dir,
  paths$logs_dir,
  paths$tmp_dir
))

log_message <- function(text, class = "info") {
  line <- sprintf("[%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), text)
  cat(line, "\n", file = outputs$log, append = TRUE)

  if (identical(class, "success")) {
    cli::cli_alert_success(text)
  } else if (identical(class, "warning")) {
    cli::cli_alert_warning(text)
  } else if (identical(class, "danger")) {
    cli::cli_alert_danger(text)
  } else {
    cli::cli_alert_info(text)
  }
}

stop_with_log <- function(message) {
  log_message(message, class = "danger")
  stop(message, call. = FALSE)
}

with_timing <- function(label, expr) {
  start <- Sys.time()
  log_message(sprintf("Starting %s", label))
  result <- force(expr)
  elapsed <- round(as.numeric(difftime(Sys.time(), start, units = "mins")), 2)
  log_message(sprintf("Finished %s in %.2f minutes", label, elapsed), class = "success")
  result
}

prepare_working_pbf <- function(source_pbf, working_pbf) {
  if (!fs::file_exists(source_pbf)) {
    stop_with_log(sprintf("PBF input does not exist: %s", source_pbf))
  }

  fs::dir_create(dirname(working_pbf))
  existing_link <- Sys.readlink(working_pbf)
  has_existing_link <- !is.na(existing_link) && nzchar(existing_link)
  if (fs::file_exists(working_pbf) || file.exists(working_pbf) || has_existing_link) {
    unlink(working_pbf)
  }

  fs::link_create(path = fs::path_abs(source_pbf), new_path = working_pbf, symbolic = TRUE)
  log_message(sprintf("Prepared temporary PBF symlink: %s", working_pbf))
  invisible(working_pbf)
}

read_gadm_boundary <- function(gadm_dir) {
  gadm_files <- fs::dir_ls(
    gadm_dir,
    regexp = "\\.(gpkg|rds|RDS|shp)$",
    recurse = TRUE,
    type = "file"
  )

  if (length(gadm_files) == 0) {
    stop_with_log(sprintf("No GADM boundary file found under %s", gadm_dir))
  }

  gadm_path <- gadm_files[1]
  log_message(sprintf("Reading GADM boundary: %s", gadm_path))

  if (grepl("\\.rds$", gadm_path, ignore.case = TRUE)) {
    gadm <- readRDS(gadm_path)
    if (inherits(gadm, "PackedSpatVector")) {
      if (!requireNamespace("terra", quietly = TRUE)) {
        stop_with_log("The GADM RDS is a terra PackedSpatVector, but package 'terra' is not installed.")
      }
      gadm <- terra::unwrap(gadm)
    }
    if (inherits(gadm, "SpatVector")) {
      gadm <- sf::st_as_sf(gadm)
    }
  } else {
    gadm <- sf::st_read(gadm_path, quiet = TRUE)
  }

  if (!inherits(gadm, "sf")) {
    stop_with_log("GADM boundary could not be converted to an sf object.")
  }

  gadm
}

extract_seoul_boundary <- function(gadm) {
  attrs <- sf::st_drop_geometry(gadm)
  seoul_idx <- rep(FALSE, nrow(attrs))

  if ("NAME_1" %in% names(attrs)) {
    seoul_idx <- seoul_idx | stringr::str_detect(attrs$NAME_1, regex("^Seoul$", ignore_case = TRUE))
  }
  if ("ISO_1" %in% names(attrs)) {
    seoul_idx <- seoul_idx | attrs$ISO_1 %in% c("KR-11", "KOR-11")
  }
  if ("HASC_1" %in% names(attrs)) {
    seoul_idx <- seoul_idx | attrs$HASC_1 %in% c("KR.SO", "KR.SL")
  }

  if (!any(seoul_idx, na.rm = TRUE)) {
    stop_with_log("Could not identify Seoul in the GADM boundary attributes.")
  }

  gadm[seoul_idx, , drop = FALSE] |>
    sf::st_make_valid() |>
    sf::st_transform(target_crs) |>
    dplyr::summarise(geometry = sf::st_union(geometry), .groups = "drop") |>
    sf::st_make_valid()
}

extract_osm_layer <- function(layer_name, boundary_wgs84) {
  with_timing(sprintf("OSM %s POI source extraction", layer_name), {
    osmextract::oe_read(
      file_path = work_paths$pbf,
      layer = layer_name,
      boundary = boundary_wgs84,
      boundary_type = "clipsrc",
      extra_tags = extra_tags,
      force_download = FALSE,
      force_vectortranslate = TRUE,
      never_skip_vectortranslate = TRUE,
      quiet = FALSE,
      stringsAsFactors = FALSE
    )
  })
}

clean_osm_geometry <- function(x, layer_name) {
  if (!inherits(x, "sf")) {
    stop(sprintf("Layer '%s' is not an sf object.", layer_name), call. = FALSE)
  }

  before <- nrow(x)
  x <- x[!sf::st_is_empty(x), , drop = FALSE]
  x <- sf::st_make_valid(x)
  x <- sf::st_transform(x, target_crs)

  if (identical(layer_name, "multipolygons")) {
    x <- suppressWarnings(sf::st_collection_extract(x, "POLYGON"))
    supported <- as.character(sf::st_geometry_type(x, by_geometry = TRUE)) %in% c("POLYGON", "MULTIPOLYGON")
    x <- x[supported & !sf::st_is_empty(x), , drop = FALSE]
  }

  after <- nrow(x)
  log_message(sprintf(
    "Cleaned %s: kept %s of %s non-empty valid geometries",
    layer_name,
    format(after, big.mark = ","),
    format(before, big.mark = ",")
  ))

  x
}

original_osm_id_column <- function(x) {
  candidates <- c("osm_id", "osm_way_id", "osm_relation_id", "id")
  hit <- intersect(candidates, names(x))
  if (length(hit) == 0) NA_character_ else hit[1]
}

normalise_missing_text <- function(x) {
  x <- as.character(x)
  x[is.na(x) | !nzchar(trimws(x)) | x %in% c("NA", "NULL", "null")] <- NA_character_
  x
}

normalise_attribute_columns <- function(attrs) {
  attrs |>
    dplyr::mutate(dplyr::across(where(is.factor), as.character)) |>
    dplyr::mutate(dplyr::across(where(is.list), ~ vapply(.x, function(v) {
      if (length(v) == 0 || all(is.na(v))) {
        NA_character_
      } else {
        as.character(jsonlite::toJSON(v, auto_unbox = TRUE, null = "null"))
      }
    }, character(1))))
}

add_poi_semantics_chunk <- function(x, geometry_source) {
  for (tag in priority_order) {
    if (!tag %in% names(x)) {
      x[[tag]] <- NA_character_
    }
    x[[tag]] <- normalise_missing_text(x[[tag]])
  }

  tag_df <- sf::st_drop_geometry(x)[, priority_order, drop = FALSE]
  present <- apply(!is.na(tag_df), 1, any)

  if (!any(present)) {
    return(x[0, , drop = FALSE])
  }

  x <- x[present, , drop = FALSE]
  tag_matrix <- as.matrix(sf::st_drop_geometry(x)[, priority_order, drop = FALSE])
  has_value <- !is.na(tag_matrix) & nzchar(tag_matrix)
  first_idx <- max.col(has_value, ties.method = "first")

  x$poi_class <- priority_order[first_idx]
  x$poi_type <- tag_matrix[cbind(seq_len(nrow(tag_matrix)), first_idx)]
  x$geometry_source <- geometry_source
  x$geometry_type <- as.character(sf::st_geometry_type(x, by_geometry = TRUE))
  x
}

parallel_add_poi_semantics <- function(x, geometry_source) {
  if (nrow(x) == 0) {
    return(add_poi_semantics_chunk(x, geometry_source))
  }

  chunks <- split(seq_len(nrow(x)), ceiling(seq_len(nrow(x)) / chunk_size))
  chunk_layers <- purrr::map(chunks, ~ x[.x, , drop = FALSE])
  old_plan <- future::plan()
  on.exit(future::plan(old_plan), add = TRUE)

  future::plan(future.mirai::mirai_multisession, workers = parallel_workers)
  log_message(sprintf(
    "Applying semantic POI priority rules to %s using %d workers and %d chunks",
    geometry_source,
    parallel_workers,
    length(chunks)
  ))

  furrr::future_map_dfr(
    chunk_layers,
    add_poi_semantics_chunk,
    geometry_source = geometry_source,
    .options = furrr::furrr_options(
      seed = FALSE,
      packages = c("sf", "dplyr", "tibble", "jsonlite")
    )
  ) |>
    sf::st_as_sf()
}

add_canonical_ids <- function(x, prefix) {
  id_width <- 7L
  x$poi_id <- sprintf("%s%0*d", prefix, id_width, seq_len(nrow(x)))

  osm_col <- original_osm_id_column(x)
  if (is.na(osm_col)) {
    x$osm_id <- NA_character_
  } else {
    x$osm_id <- as.character(x[[osm_col]])
  }

  x
}

ordered_attribute_table <- function(attrs, leading_cols) {
  existing_leading <- intersect(leading_cols, names(attrs))
  remaining <- setdiff(names(attrs), existing_leading)
  attrs[, c(existing_leading, remaining), drop = FALSE]
}

make_point_parquet_chunk <- function(x) {
  coords <- sf::st_coordinates(x)
  attrs <- x |>
    sf::st_drop_geometry() |>
    dplyr::select(-dplyr::any_of(c("geometry_source", "geometry_type"))) |>
    normalise_attribute_columns() |>
    dplyr::mutate(
      x = coords[, "X"],
      y = coords[, "Y"],
      .after = osm_id
    )

  ordered_attribute_table(
    attrs,
    c("poi_id", "osm_id", "x", "y", "poi_class", "poi_type", "name")
  )
}

make_polygon_parquet_chunk <- function(x) {
  centroids <- suppressWarnings(sf::st_centroid(sf::st_geometry(x)))
  coords <- sf::st_coordinates(centroids)
  attrs <- x |>
    sf::st_drop_geometry() |>
    dplyr::select(-dplyr::any_of("geometry_source")) |>
    normalise_attribute_columns() |>
    dplyr::mutate(
      centroid_x = coords[, "X"],
      centroid_y = coords[, "Y"],
      .after = osm_id
    )

  ordered_attribute_table(
    attrs,
    c("poi_id", "osm_id", "centroid_x", "centroid_y", "poi_class", "poi_type", "name", "geometry_type")
  )
}

parallel_make_parquet_rows <- function(x, label, chunk_function) {
  if (nrow(x) == 0) {
    return(chunk_function(x))
  }

  chunks <- split(seq_len(nrow(x)), ceiling(seq_len(nrow(x)) / chunk_size))
  chunk_layers <- purrr::map(chunks, ~ x[.x, , drop = FALSE])
  old_plan <- future::plan()
  on.exit(future::plan(old_plan), add = TRUE)

  future::plan(future.mirai::mirai_multisession, workers = parallel_workers)
  log_message(sprintf(
    "Converting %s attributes to parquet rows using %d workers and %d chunks",
    label,
    parallel_workers,
    length(chunks)
  ))

  furrr::future_map_dfr(
    chunk_layers,
    chunk_function,
    .options = furrr::furrr_options(
      seed = FALSE,
      packages = c("sf", "dplyr", "tibble", "jsonlite")
    )
  )
}

write_gpkg_semantic <- function(x, dsn, layer_name, keep_geometry_type = FALSE) {
  # Canonical GPKG files are used directly in GIS QA/QC and spatial workflows,
  # so they should carry the same semantic POI attributes that make the parquet
  # tables useful for representation learning. Coordinate-only parquet columns
  # are omitted because the GPKG stores real geometry.
  attrs <- x |>
    sf::st_drop_geometry() |>
    dplyr::select(-dplyr::any_of("geometry_source"))

  if (!keep_geometry_type) {
    attrs <- attrs |>
      dplyr::select(-dplyr::any_of("geometry_type"))
  }

  attrs <- attrs |>
    normalise_attribute_columns() |>
    ordered_attribute_table(
      c("poi_id", "osm_id", "poi_class", "poi_type", "name", "geometry_type")
    )

  gpkg <- sf::st_sf(attrs, geometry = sf::st_geometry(x), crs = sf::st_crs(x))

  sf::st_write(gpkg, dsn = dsn, layer = layer_name, delete_dsn = TRUE, quiet = TRUE)
  log_message(sprintf("Wrote %s GPKG with %s POIs: %s", layer_name, format(nrow(gpkg), big.mark = ","), dsn))
}

write_parquet_rows <- function(rows, dsn, label) {
  arrow::write_parquet(rows, dsn)
  log_message(sprintf("Wrote %s parquet with %s POIs: %s", label, format(nrow(rows), big.mark = ","), dsn))
}

create_poi_mapping <- function(point_pois, polygon_pois) {
  dplyr::bind_rows(
    point_pois |>
      sf::st_drop_geometry() |>
      dplyr::transmute(
        poi_id,
        osm_id,
        geometry_source,
        geometry_type = as.character(geometry_type)
      ),
    polygon_pois |>
      sf::st_drop_geometry() |>
      dplyr::transmute(
        poi_id,
        osm_id,
        geometry_source,
        geometry_type = as.character(geometry_type)
      )
  )
}

summarise_layer <- function(rows, source, output_gpkg, output_parquet) {
  top_type_count <- rows |>
    dplyr::count(poi_type, sort = TRUE, name = "n") |>
    utils::head(20) |>
    dplyr::mutate(label = paste0(poi_type, "=", n)) |>
    dplyr::pull(label) |>
    paste(collapse = "; ")

  tibble::tibble(
    layer_name = source,
    feature_count = nrow(rows),
    unique_poi_classes = dplyr::n_distinct(rows$poi_class, na.rm = TRUE),
    unique_poi_types = dplyr::n_distinct(rows$poi_type, na.rm = TRUE),
    geometry_types = if ("geometry_type" %in% names(rows)) paste(sort(unique(rows$geometry_type)), collapse = ",") else "POINT",
    crs = sprintf("EPSG:%s", target_crs),
    top_poi_types = top_type_count,
    extraction_timestamp = extraction_timestamp,
    gpkg_path = output_gpkg,
    parquet_path = output_parquet
  )
}

make_distribution <- function(point_rows, polygon_rows, field) {
  point_distribution <- point_rows |>
    dplyr::transmute(geometry_source = "point", value = .data[[field]])
  polygon_distribution <- polygon_rows |>
    dplyr::transmute(geometry_source = "polygon", value = .data[[field]])

  dplyr::bind_rows(
    point_distribution,
    polygon_distribution,
    dplyr::bind_rows(point_distribution, polygon_distribution) |>
      dplyr::mutate(geometry_source = "all")
  ) |>
    dplyr::mutate(value = dplyr::coalesce(as.character(value), "__missing__")) |>
    dplyr::count(geometry_source, value, name = "n") |>
    dplyr::group_by(geometry_source) |>
    dplyr::mutate(
      total = sum(n),
      proportion = n / total,
      rank = dplyr::min_rank(dplyr::desc(n))
    ) |>
    dplyr::ungroup() |>
    dplyr::arrange(geometry_source, rank, value) |>
    dplyr::rename(!!field := value)
}

write_distribution_outputs <- function(point_rows, polygon_rows) {
  class_distribution <- make_distribution(point_rows, polygon_rows, "poi_class")
  type_distribution <- make_distribution(point_rows, polygon_rows, "poi_type")

  arrow::write_parquet(class_distribution, outputs$poi_class_distribution)
  arrow::write_parquet(type_distribution, outputs$poi_type_distribution)

  log_message(sprintf("Wrote POI class distribution: %s", outputs$poi_class_distribution))
  log_message(sprintf("Wrote POI type distribution: %s", outputs$poi_type_distribution))

  list(
    poi_class = class_distribution,
    poi_type = type_distribution
  )
}

verify_outputs <- function(point_rows, polygon_rows) {
  required_files <- unlist(outputs[c(
    "gpkg_point",
    "gpkg_polygon",
    "parquet_point",
    "parquet_polygon",
    "poi_id_mapping",
    "layer_summary",
    "poi_class_distribution",
    "poi_type_distribution"
  )])

  missing_files <- required_files[!fs::file_exists(required_files)]
  if (length(missing_files) > 0) {
    stop_with_log(sprintf("Missing expected output files: %s", paste(missing_files, collapse = ", ")))
  }

  required_point_columns <- c("poi_class", "poi_type", "x", "y")
  required_polygon_columns <- c("poi_class", "poi_type", "centroid_x", "centroid_y", "geometry_type")

  missing_point_columns <- setdiff(required_point_columns, names(point_rows))
  missing_polygon_columns <- setdiff(required_polygon_columns, names(polygon_rows))
  if (length(missing_point_columns) > 0 || length(missing_polygon_columns) > 0) {
    stop_with_log(sprintf(
      "Missing expected parquet columns. point=[%s], polygon=[%s]",
      paste(missing_point_columns, collapse = ","),
      paste(missing_polygon_columns, collapse = ",")
    ))
  }

  if (nrow(point_rows) == 0 || nrow(polygon_rows) == 0) {
    stop_with_log(sprintf(
      "POI counts must be nonzero. point=%s polygon=%s",
      nrow(point_rows),
      nrow(polygon_rows)
    ))
  }

  original_tag_columns <- setdiff(priority_order, c("poi_class", "poi_type"))
  if (!any(original_tag_columns %in% names(point_rows)) || !any(original_tag_columns %in% names(polygon_rows))) {
    stop_with_log("Parquet outputs do not retain original OSM semantic tag columns.")
  }

  point_gpkg <- sf::st_read(outputs$gpkg_point, quiet = TRUE)
  polygon_gpkg <- sf::st_read(outputs$gpkg_polygon, quiet = TRUE)
  required_gpkg_columns <- c("poi_class", "poi_type", "name")
  missing_point_gpkg_columns <- setdiff(required_gpkg_columns, names(point_gpkg))
  missing_polygon_gpkg_columns <- setdiff(required_gpkg_columns, names(polygon_gpkg))

  if (length(missing_point_gpkg_columns) > 0 || length(missing_polygon_gpkg_columns) > 0) {
    stop_with_log(sprintf(
      "Missing expected GPKG semantic columns. point=[%s], polygon=[%s]",
      paste(missing_point_gpkg_columns, collapse = ","),
      paste(missing_polygon_gpkg_columns, collapse = ",")
    ))
  }

  if (nrow(point_gpkg) != nrow(point_rows) || nrow(polygon_gpkg) != nrow(polygon_rows)) {
    stop_with_log(sprintf(
      "GPKG and parquet row counts differ. point_gpkg=%s point_parquet=%s polygon_gpkg=%s polygon_parquet=%s",
      nrow(point_gpkg),
      nrow(point_rows),
      nrow(polygon_gpkg),
      nrow(polygon_rows)
    ))
  }

  log_message("Verified expected POI outputs, GPKG semantic fields, nonzero counts, coordinates, and retained OSM tags.", class = "success")
  invisible(TRUE)
}

cat("", file = outputs$log)
log_message("Seoul OSM semantic POI dataset build started.")

prepare_working_pbf(paths$pbf, work_paths$pbf)

seoul_boundary_5186 <- with_timing(
  "Seoul boundary preparation",
  extract_seoul_boundary(read_gadm_boundary(paths$gadm_dir))
)
seoul_boundary_wgs84 <- sf::st_transform(seoul_boundary_5186, 4326)

points_raw <- extract_osm_layer("points", seoul_boundary_wgs84) |>
  clean_osm_geometry("points")

polygons_raw <- extract_osm_layer("multipolygons", seoul_boundary_wgs84) |>
  clean_osm_geometry("multipolygons")

point_pois <- with_timing(
  "point POI semantic filtering",
  parallel_add_poi_semantics(points_raw, "points")
) |>
  add_canonical_ids("POIP")

polygon_pois <- with_timing(
  "polygon POI semantic filtering",
  parallel_add_poi_semantics(polygons_raw, "multipolygons")
) |>
  add_canonical_ids("POIG")

write_gpkg_semantic(point_pois, outputs$gpkg_point, "seoul_pois_point")
write_gpkg_semantic(polygon_pois, outputs$gpkg_polygon, "seoul_pois_polygon", keep_geometry_type = TRUE)

point_rows <- with_timing(
  "point POI parquet conversion",
  parallel_make_parquet_rows(point_pois, "point POIs", make_point_parquet_chunk)
)
polygon_rows <- with_timing(
  "polygon POI parquet conversion",
  parallel_make_parquet_rows(polygon_pois, "polygon POIs", make_polygon_parquet_chunk)
)

write_parquet_rows(point_rows, outputs$parquet_point, "seoul_pois_point")
write_parquet_rows(polygon_rows, outputs$parquet_polygon, "seoul_pois_polygon")

poi_mapping <- create_poi_mapping(point_pois, polygon_pois)
arrow::write_parquet(poi_mapping, outputs$poi_id_mapping)
log_message(sprintf("Wrote POI ID mapping: %s", outputs$poi_id_mapping))

layer_summary <- dplyr::bind_rows(
  summarise_layer(point_rows, "seoul_pois_point", outputs$gpkg_point, outputs$parquet_point),
  summarise_layer(polygon_rows, "seoul_pois_polygon", outputs$gpkg_polygon, outputs$parquet_polygon)
)
arrow::write_parquet(layer_summary, outputs$layer_summary)
log_message(sprintf("Wrote layer summary: %s", outputs$layer_summary))

distributions <- write_distribution_outputs(point_rows, polygon_rows)

verify_outputs(point_rows, polygon_rows)

top_20_poi_types <- dplyr::bind_rows(
  point_rows |> dplyr::select(poi_type),
  polygon_rows |> dplyr::select(poi_type)
) |>
  dplyr::count(poi_type, sort = TRUE, name = "n") |>
  utils::head(20)

cli::cli_h2("Final POI Extraction Summary")
cat(sprintf("Total point POI count: %s\n", format(nrow(point_rows), big.mark = ",")))
cat(sprintf("Total polygon POI count: %s\n", format(nrow(polygon_rows), big.mark = ",")))
cat("Top 20 poi_class frequencies by source:\n")
print(distributions$poi_class |> dplyr::filter(geometry_source != "all", rank <= 20))
cat("Top 20 poi_type frequencies:\n")
print(top_20_poi_types)
cat("Top 50 poi_type frequencies by source:\n")
print(distributions$poi_type |> dplyr::filter(geometry_source != "all", rank <= 50))

log_message("Seoul OSM semantic POI dataset build finished.", class = "success")
