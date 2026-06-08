#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(arrow)
  library(data.table)
  library(dplyr)
  library(collapse)
  library(future)
  library(future.mirai)
  library(future.apply)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)
set.seed(20260608)

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || all(is.na(x)) || identical(x, "")) y else x
}

timestamp_now <- function() format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", timestamp_now(), paste(..., collapse = " ")))
}

parse_args <- function(args) {
  list(
    overwrite = any(args %in% c("--overwrite", "-f")),
    workers = {
      hit <- grep("^--workers=", args, value = TRUE)
      if (length(hit)) as.integer(sub("^--workers=", "", hit[[1]])) else
        as.integer(Sys.getenv("GWANAK_GEONEURAL_WORKERS", unset = "8"))
    },
    chunk_size = {
      hit <- grep("^--chunk-size=", args, value = TRUE)
      if (length(hit)) as.integer(sub("^--chunk-size=", "", hit[[1]])) else
        as.integer(Sys.getenv("GWANAK_GEONEURAL_CHUNK_SIZE", unset = "5000"))
    },
    max_features = {
      hit <- grep("^--max-features=", args, value = TRUE)
      if (length(hit)) as.integer(sub("^--max-features=", "", hit[[1]])) else
        as.integer(Sys.getenv("GWANAK_GEONEURAL_MAX_FEATURES", unset = NA_character_))
    }
  )
}

stop_if_missing <- function(path, label) {
  if (!file.exists(path)) stop(label, " does not exist: ", path, call. = FALSE)
}

stop_if_outputs_exist <- function(paths, overwrite) {
  existing <- paths[file.exists(paths)]
  if (!length(existing)) return(invisible(TRUE))
  if (!overwrite) {
    stop(
      "Output file(s) already exist. Re-run with --overwrite to replace them:\n",
      paste(existing, collapse = "\n"),
      call. = FALSE
    )
  }
  for (path in existing) {
    if (grepl("[.]gpkg$", path, ignore.case = TRUE)) {
      unlink(path)
      wal <- paste0(path, "-wal")
      shm <- paste0(path, "-shm")
      if (file.exists(wal)) unlink(wal)
      if (file.exists(shm)) unlink(shm)
    } else {
      unlink(path)
    }
  }
  invisible(TRUE)
}

canonicalize_target_crs <- function(x, target_epsg) {
  if (is.na(sf::st_crs(x))) stop("Cannot canonicalize missing CRS.", call. = FALSE)
  if (!identical(as.integer(sf::st_crs(x)$epsg), as.integer(target_epsg))) {
    x <- sf::st_transform(x, target_epsg)
  }
  suppressWarnings(sf::st_crs(x) <- sf::st_crs(target_epsg))
  x
}

find_gwanak_boundary <- function(sigungu_path, target_epsg) {
  log_msg("Inspecting administrative boundary:", sigungu_path)
  layers <- sf::st_layers(sigungu_path, do_count = TRUE)
  print(layers)

  sigungu <- sf::st_read(sigungu_path, quiet = TRUE, stringsAsFactors = FALSE)
  log_msg("Sigungu columns:", paste(names(sigungu), collapse = ", "))
  log_msg("Sigungu CRS:", sf::st_crs(sigungu)$input %||% "NA", "EPSG", sf::st_crs(sigungu)$epsg %||% NA)

  attr_names <- setdiff(names(sigungu), attr(sigungu, "sf_column"))
  char_cols <- attr_names[vapply(sf::st_drop_geometry(sigungu[, attr_names, drop = FALSE]), is.character, logical(1))]
  if (!length(char_cols)) stop("No character columns found in sigungu boundary for Gwanak-gu lookup.", call. = FALSE)

  hit_idx <- integer()
  hit_col <- NA_character_
  for (nm in char_cols) {
    values <- sigungu[[nm]]
    idx <- which(grepl("관악구|Gwanak|GWANAK", values, ignore.case = TRUE))
    if (length(idx)) {
      hit_idx <- idx
      hit_col <- nm
      break
    }
  }
  if (length(hit_idx) != 1L) {
    log_msg("Boundary columns inspected:", paste(char_cols, collapse = ", "))
    stop("Expected exactly one Gwanak-gu boundary row, found ", length(hit_idx), ".", call. = FALSE)
  }

  gwanak <- sigungu[hit_idx, ]
  log_msg("Identified Gwanak-gu using column", hit_col, "value:", gwanak[[hit_col]][[1]])

  if (is.na(sf::st_crs(gwanak))) stop("Gwanak boundary has missing CRS.", call. = FALSE)
  if (!identical(as.integer(sf::st_crs(gwanak)$epsg), as.integer(target_epsg))) {
    log_msg("Transforming Gwanak boundary to EPSG:", target_epsg)
  }
  gwanak <- canonicalize_target_crs(gwanak, target_epsg)

  invalid <- sum(!sf::st_is_valid(gwanak), na.rm = TRUE)
  if (invalid > 0L) {
    log_msg("Repairing invalid Gwanak boundary geometry with st_make_valid.")
    gwanak <- sf::st_make_valid(gwanak)
  }

  gwanak_union <- sf::st_union(sf::st_geometry(gwanak))
  sf::st_crs(gwanak_union) <- sf::st_crs(gwanak)
  gwanak_union
}

read_candidate_buildings <- function(building_gpkg, layer_name, gwanak_geom, target_epsg, max_features = NA_integer_) {
  log_msg("Inspecting building GeoPackage:", building_gpkg)
  layers <- sf::st_layers(building_gpkg, do_count = TRUE)
  print(layers)
  if (!layer_name %in% layers$name) stop("Layer not found in building GeoPackage: ", layer_name, call. = FALSE)

  layer_idx <- match(layer_name, layers$name)
  layer_crs <- layers$crs[[layer_idx]]
  log_msg("Building layer CRS from st_layers:", layer_crs$input %||% "NA", "EPSG", layer_crs$epsg %||% NA)

  wkt_filter <- sf::st_as_text(sf::st_as_sfc(sf::st_bbox(gwanak_geom)))
  log_msg("Reading candidate buildings with GDAL wkt_filter on Gwanak bounding box.")
  buildings <- sf::st_read(
    building_gpkg,
    layer = layer_name,
    wkt_filter = wkt_filter,
    quiet = TRUE,
    stringsAsFactors = FALSE
  )

  if (!"building_id" %in% names(buildings)) stop("Building layer does not contain stable key building_id.", call. = FALSE)
  buildings <- buildings[, "building_id", drop = FALSE]

  if (!is.na(max_features)) {
    log_msg("Applying experimental max feature limit:", max_features)
    buildings <- utils::head(buildings, max_features)
  }

  if (is.na(sf::st_crs(buildings))) stop("Building candidate geometries have missing CRS.", call. = FALSE)
  if (!identical(as.integer(sf::st_crs(buildings)$epsg), as.integer(target_epsg))) {
    log_msg("Transforming building candidates to EPSG:", target_epsg)
  }
  buildings <- canonicalize_target_crs(buildings, target_epsg)

  log_msg("Candidate rows from bounding-box spatial filter:", nrow(buildings))
  buildings
}

repair_candidate_geometry <- function(buildings) {
  empty <- sf::st_is_empty(buildings)
  valid <- sf::st_is_valid(buildings)

  n_empty <- sum(empty, na.rm = TRUE)
  n_invalid <- sum(!valid & !empty, na.rm = TRUE)
  log_msg("Empty candidate geometries:", n_empty)
  log_msg("Invalid non-empty candidate geometries:", n_invalid)

  if (n_empty > 0L) {
    log_msg("Dropping empty candidate geometries before membership classification.")
    buildings <- buildings[!empty, ]
    valid <- sf::st_is_valid(buildings)
  }

  if (n_invalid > 0L) {
    log_msg("Repairing invalid candidate geometries with st_make_valid. This does not clip to Gwanak-gu.")
    geom <- sf::st_geometry(buildings)
    bad <- which(!valid)
    geom[bad] <- sf::st_geometry(sf::st_make_valid(buildings[bad, ]))
    geom <- sf::st_collection_extract(geom, "POLYGON", warn = FALSE)
    sf::st_geometry(buildings) <- geom
  }

  list(
    buildings = buildings,
    n_empty = n_empty,
    n_invalid = n_invalid,
    n_after_empty_drop = nrow(buildings)
  )
}

candidate_intersects_gwanak <- function(buildings, gwanak_geom) {
  log_msg("Selecting buildings whose preserved footprints intersect Gwanak-gu.")
  hits <- lengths(sf::st_intersects(buildings, gwanak_geom, sparse = TRUE)) > 0L
  buildings[hits, , drop = FALSE]
}

compute_point_membership <- function(buildings, gwanak_geom) {
  log_msg("Computing representative points with st_point_on_surface.")
  pts <- sf::st_point_on_surface(sf::st_geometry(buildings))
  lengths(sf::st_within(pts, gwanak_geom, sparse = TRUE)) > 0L
}

compute_area_share_chunk <- function(chunk, gwanak_geom) {
  suppressPackageStartupMessages(library(sf))
  sf::sf_use_s2(FALSE)

  b_area <- as.numeric(sf::st_area(chunk))
  inter <- suppressWarnings(sf::st_intersection(chunk[, "building_id", drop = FALSE], gwanak_geom))
  if (!nrow(inter)) {
    return(data.table::data.table(building_id = chunk$building_id, area_share_gwanak = 0))
  }
  inter_area <- data.table::data.table(
    building_id = inter$building_id,
    inter_area = as.numeric(sf::st_area(inter))
  )[, .(inter_area = sum(inter_area, na.rm = TRUE)), by = building_id]

  out <- data.table::data.table(building_id = chunk$building_id, building_area = b_area)
  out <- merge(out, inter_area, by = "building_id", all.x = TRUE)
  out[is.na(inter_area), inter_area := 0]
  out[, area_share_gwanak := fifelse(building_area > 0, pmin(1, pmax(0, inter_area / building_area)), 0)]
  out[, .(building_id, area_share_gwanak)]
}

compute_area_share <- function(buildings, gwanak_geom, workers, chunk_size) {
  n <- nrow(buildings)
  log_msg("Computing area share inside Gwanak-gu for candidate buildings:", n)
  if (!n) return(data.table(building_id = character(), area_share_gwanak = numeric()))

  starts <- seq.int(1L, n, by = chunk_size)
  chunks <- lapply(starts, function(i) buildings[i:min(i + chunk_size - 1L, n), , drop = FALSE])
  workers <- max(1L, min(as.integer(workers), length(chunks)))

  if (workers > 1L && length(chunks) > 1L) {
    log_msg("Using future.mirai for area-share chunks. Workers:", workers, "Chunks:", length(chunks))
    old_plan <- future::plan()
    on.exit(future::plan(old_plan), add = TRUE)
    future::plan(future.mirai::mirai_multisession, workers = workers)
    rows <- future.apply::future_lapply(
      chunks,
      compute_area_share_chunk,
      gwanak_geom = gwanak_geom,
      future.seed = TRUE,
      future.packages = c("sf", "data.table")
    )
  } else {
    log_msg("Using serial area-share computation. Chunks:", length(chunks))
    rows <- lapply(chunks, compute_area_share_chunk, gwanak_geom = gwanak_geom)
  }

  data.table::rbindlist(rows, use.names = TRUE)
}

read_matching_attributes <- function(attributes_parquet, final_ids, id_chunk_size = 50000L) {
  log_msg("Reading matching attributes from Parquet with Arrow. IDs:", length(final_ids))
  ds <- arrow::open_dataset(attributes_parquet)
  if (!"building_id" %in% names(ds)) stop("Attributes parquet does not contain building_id.", call. = FALSE)

  id_chunks <- split(final_ids, ceiling(seq_along(final_ids) / id_chunk_size))
  rows <- vector("list", length(id_chunks))
  for (i in seq_along(id_chunks)) {
    ids <- id_chunks[[i]]
    rows[[i]] <- ds %>%
      dplyr::filter(building_id %in% ids) %>%
      dplyr::collect()
    log_msg("Collected attribute chunk", i, "of", length(id_chunks), "rows:", nrow(rows[[i]]))
  }
  data.table::rbindlist(lapply(rows, data.table::as.data.table), fill = TRUE)
}

write_outputs <- function(final_buildings, final_attributes, summary_dt, out_gpkg, out_attrs, out_summary) {
  log_msg("Writing GeoPackage:", out_gpkg)
  sf::st_write(final_buildings, out_gpkg, layer = "gwanak_buildings", delete_dsn = TRUE, quiet = TRUE)

  log_msg("Writing attributes Parquet:", out_attrs)
  arrow::write_parquet(final_attributes, out_attrs)

  log_msg("Writing summary Parquet:", out_summary)
  arrow::write_parquet(summary_dt, out_summary)
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  target_epsg <- 5186L
  layer_name <- "buildings"

  sigungu_path <- path.expand("~/fusedata/geodata/koreanadm/bnd_sigungu_00_2024_2Q.shp")
  building_gpkg <- path.expand("~/fusedatalarge/processed/korea_buildings_vworld.gpkg")
  attributes_parquet <- path.expand("~/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet")

  out_gpkg <- path.expand("~/fusedatalarge/processed/gwanak_buildings_vworld.gpkg")
  out_attrs <- path.expand("~/fusedatalarge/processed/gwanak_buildings_vworld_attributes.parquet")
  out_summary <- path.expand("~/fusedatalarge/processed/gwanak_buildings_vworld_summary.parquet")

  for (x in list(
    "Administrative boundary" = sigungu_path,
    "Building GeoPackage" = building_gpkg,
    "Building attributes Parquet" = attributes_parquet
  )) {
    stop_if_missing(x[[1]], names(x))
  }
  stop_if_outputs_exist(c(out_gpkg, out_attrs, out_summary), args$overwrite)

  log_msg("Starting Gwanak-gu VWorld building preprocessing for GeoNeuralRepresentation.")
  log_msg("Overwrite:", args$overwrite)
  log_msg("Workers:", args$workers)
  log_msg("Chunk size:", args$chunk_size)

  gwanak_geom <- find_gwanak_boundary(sigungu_path, target_epsg)
  boundary_crs <- sf::st_crs(gwanak_geom)

  candidates_bbox <- read_candidate_buildings(
    building_gpkg = building_gpkg,
    layer_name = layer_name,
    gwanak_geom = gwanak_geom,
    target_epsg = target_epsg,
    max_features = args$max_features
  )
  building_crs <- sf::st_crs(candidates_bbox)
  if (!identical(sf::st_crs(gwanak_geom), building_crs)) {
    if (!identical(as.integer(sf::st_crs(gwanak_geom)$epsg), as.integer(building_crs$epsg))) {
      stop("Gwanak boundary and building candidates have incompatible CRS after transformation.", call. = FALSE)
    }
    log_msg("Aligning Gwanak boundary CRS metadata to building layer CRS object for sf predicates.")
    sf::st_crs(gwanak_geom) <- building_crs
  }

  repaired <- repair_candidate_geometry(candidates_bbox)
  candidates_bbox <- repaired$buildings

  candidates <- candidate_intersects_gwanak(candidates_bbox, gwanak_geom)
  n_intersecting_candidates <- nrow(candidates)
  log_msg("Intersecting candidate buildings:", n_intersecting_candidates)
  if (n_intersecting_candidates == 0L) stop("No buildings intersect Gwanak-gu.", call. = FALSE)

  candidates[, "point_on_surface_in_gwanak"] <- compute_point_membership(candidates, gwanak_geom)

  area_share <- compute_area_share(
    candidates,
    gwanak_geom,
    workers = args$workers,
    chunk_size = args$chunk_size
  )

  candidate_dt <- data.table::as.data.table(sf::st_drop_geometry(candidates))
  candidate_dt <- merge(candidate_dt, area_share, by = "building_id", all.x = TRUE)
  candidate_dt[is.na(area_share_gwanak), area_share_gwanak := 0]
  candidate_dt[, boundary_crossing := area_share_gwanak > 0 & area_share_gwanak < 1]
  candidate_dt[, include_gwanak_experiment := point_on_surface_in_gwanak | area_share_gwanak >= 0.5]

  candidates$area_share_gwanak <- candidate_dt$area_share_gwanak[match(candidates$building_id, candidate_dt$building_id)]
  candidates$boundary_crossing <- candidate_dt$boundary_crossing[match(candidates$building_id, candidate_dt$building_id)]
  candidates$include_gwanak_experiment <- candidate_dt$include_gwanak_experiment[match(candidates$building_id, candidate_dt$building_id)]

  final_buildings <- candidates[candidates$include_gwanak_experiment, c(
    "building_id",
    "point_on_surface_in_gwanak",
    "area_share_gwanak",
    "boundary_crossing",
    "include_gwanak_experiment"
  )]

  n_final <- nrow(final_buildings)
  log_msg("Final included buildings:", n_final)
  if (n_final == 0L) stop("No final buildings selected for Gwanak-gu experiment.", call. = FALSE)

  final_ids <- final_buildings$building_id
  final_attributes <- read_matching_attributes(attributes_parquet, final_ids)
  missing_attr <- setdiff(final_ids, final_attributes$building_id)
  if (length(missing_attr)) {
    stop("Attributes parquet is missing ", length(missing_attr), " selected building_id values.", call. = FALSE)
  }
  data.table::setDT(final_attributes)
  data.table::setkey(final_attributes, building_id)
  final_attributes <- final_attributes[final_ids]

  final_dt <- data.table::as.data.table(sf::st_drop_geometry(final_buildings))
  area_values <- final_dt$area_share_gwanak
  summary_dt <- data.table::data.table(
    sigungu_path = sigungu_path,
    building_gpkg = building_gpkg,
    attributes_parquet = attributes_parquet,
    output_gpkg = out_gpkg,
    output_attributes_parquet = out_attrs,
    output_summary_parquet = out_summary,
    boundary_crs_input = boundary_crs$input %||% NA_character_,
    boundary_crs_epsg = boundary_crs$epsg %||% NA_integer_,
    building_crs_input = building_crs$input %||% NA_character_,
    building_crs_epsg = building_crs$epsg %||% NA_integer_,
    target_epsg = target_epsg,
    n_bbox_candidates_after_empty_drop = repaired$n_after_empty_drop,
    n_empty_candidate_geometries = repaired$n_empty,
    n_invalid_candidate_geometries = repaired$n_invalid,
    invalid_geometry_handling = if (repaired$n_invalid > 0L) "st_make_valid on candidate geometries before classification/output; no administrative clipping" else "none",
    n_intersecting_candidate_buildings = n_intersecting_candidates,
    n_final_included_buildings = n_final,
    n_representative_point_in_gwanak_buildings = sum(final_dt$point_on_surface_in_gwanak, na.rm = TRUE),
    n_area_share_included_buildings = sum(final_dt$area_share_gwanak >= 0.5, na.rm = TRUE),
    n_boundary_crossing_buildings = sum(final_dt$boundary_crossing, na.rm = TRUE),
    min_area_share_gwanak = fmin(area_values, na.rm = TRUE),
    median_area_share_gwanak = fmedian(area_values, na.rm = TRUE),
    mean_area_share_gwanak = fmean(area_values, na.rm = TRUE),
    max_area_share_gwanak = fmax(area_values, na.rm = TRUE),
    timestamp = timestamp_now()
  )

  write_outputs(final_buildings, final_attributes, summary_dt, out_gpkg, out_attrs, out_summary)

  log_msg("Done.")
  log_msg("Final counts:")
  print(summary_dt[, .(
    n_intersecting_candidate_buildings,
    n_final_included_buildings,
    n_representative_point_in_gwanak_buildings,
    n_area_share_included_buildings,
    n_boundary_crossing_buildings,
    min_area_share_gwanak,
    median_area_share_gwanak,
    mean_area_share_gwanak,
    max_area_share_gwanak
  )])
  log_msg("Output GeoPackage:", out_gpkg)
  log_msg("Output attributes Parquet:", out_attrs)
  log_msg("Output summary Parquet:", out_summary)
}

main()
