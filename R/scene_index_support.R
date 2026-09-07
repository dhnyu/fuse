with_research_rng <- function(seed, kind, normal_kind, sample_kind, code) {
  old_kind <- RNGkind()
  had_seed <- exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  if (had_seed) old_seed <- get(".Random.seed", envir = .GlobalEnv, inherits = FALSE)
  on.exit({
    do.call(RNGkind, as.list(old_kind))
    if (had_seed) {
      assign(".Random.seed", old_seed, envir = .GlobalEnv)
    } else if (exists(".Random.seed", envir = .GlobalEnv, inherits = FALSE)) {
      rm(".Random.seed", envir = .GlobalEnv)
    }
  }, add = TRUE)
  RNGkind(kind = kind, normal.kind = normal_kind, sample.kind = sample_kind)
  set.seed(as.integer(seed))
  force(code)
}

round_to_precision <- function(value, precision) {
  round(value / precision) * precision
}

coordinate_token <- function(value, precision) {
  integer <- round(value / precision)
  format(integer, scientific = FALSE, trim = TRUE)
}

deterministic_scene_ids <- function(split, center_x, center_y, schema_version,
                                    precision, prefix = "scn_", characters = 24L) {
  vapply(seq_along(split), function(index) {
    token <- paste(
      schema_version, split[[index]],
      coordinate_token(center_x[[index]], precision),
      coordinate_token(center_y[[index]], precision),
      sep = "|"
    )
    paste0(prefix, substr(digest::digest(token, algo = "sha256", serialize = FALSE), 1L, characters))
  }, character(1L))
}

deterministic_footprint_ids <- function(xmin, ymin, xmax, ymax, schema_version,
                                        precision, prefix = "fpt_", characters = 24L) {
  vapply(seq_along(xmin), function(index) {
    token <- paste(
      schema_version, "EPSG:5186",
      coordinate_token(xmin[[index]], precision), coordinate_token(ymin[[index]], precision),
      coordinate_token(xmax[[index]], precision), coordinate_token(ymax[[index]], precision),
      sep = "|"
    )
    paste0(prefix, substr(digest::digest(token, algo = "sha256", serialize = FALSE), 1L, characters))
  }, character(1L))
}

square_footprints <- function(center_x, center_y, width, crs = 5186L) {
  half <- width / 2
  geometries <- lapply(seq_along(center_x), function(index) {
    x <- center_x[[index]]
    y <- center_y[[index]]
    sf::st_polygon(list(matrix(c(
      x - half, y - half,
      x + half, y - half,
      x + half, y + half,
      x - half, y + half,
      x - half, y - half
    ), ncol = 2L, byrow = TRUE)))
  })
  sf::st_sfc(geometries, crs = crs)
}

geometry_sha256 <- function(geometry) {
  vapply(sf::st_as_binary(geometry, EWKB = TRUE), function(value) {
    digest::digest(value, algo = "sha256", serialize = FALSE)
  }, character(1L))
}

canonicalize_official_grid <- function(official, id_column) {
  if (!id_column %in% names(official)) stop("Official grid ID column is missing", call. = FALSE)
  ids <- as.character(official[[id_column]])
  if (anyNA(ids) || any(!nzchar(ids))) stop("Official grid has missing cell IDs", call. = FALSE)
  geometry_hash <- geometry_sha256(sf::st_geometry(official))
  centers <- suppressWarnings(sf::st_centroid(sf::st_geometry(official)))
  xy <- sf::st_coordinates(centers)
  evidence <- data.table::data.table(
    source_row = seq_len(nrow(official)), official_grid_id = ids,
    geometry_sha256 = geometry_hash, center_x = xy[, "X"], center_y = xy[, "Y"]
  )
  inconsistent <- evidence[, .(
    geometry_count = data.table::uniqueN(geometry_sha256),
    center_count = data.table::uniqueN(paste(format(center_x, digits = 17), format(center_y, digits = 17)))
  ), by = official_grid_id][geometry_count != 1L | center_count != 1L]
  if (nrow(inconsistent)) {
    stop("Official grid same ID has different center or geometry: ", inconsistent$official_grid_id[[1L]], call. = FALSE)
  }
  data.table::setorder(evidence, official_grid_id, geometry_sha256, source_row)
  retained <- evidence[, source_row[[1L]], by = official_grid_id]$V1
  canonical <- official[retained, c(id_column)]
  canonical$official_grid_id <- as.character(canonical[[id_column]])
  canonical <- canonical[order(canonical$official_grid_id, method = "radix"), ]
  list(
    data = canonical,
    source_row_count = nrow(official),
    canonical_cell_count = nrow(canonical),
    identical_duplicate_rows_removed = nrow(official) - nrow(canonical)
  )
}

derive_official_training_scenes <- function(boundary, grid_path, contract) {
  native_epsg <- as.integer(contract$crs$official_grid_epsg)
  processing_epsg <- as.integer(contract$crs$processing_epsg)
  precision <- as.numeric(contract$scene$coordinate_precision_m)
  boundary_native <- sf::st_transform(boundary, native_epsg)
  filter <- sf::st_as_text(sf::st_as_sfc(sf::st_bbox(sf::st_buffer(boundary_native, 1000))))
  official <- sf::st_read(grid_path, quiet = TRUE, wkt_filter = filter)
  if (!nrow(official) || sf::st_crs(official)$epsg != native_epsg) {
    stop("Official grid subset is empty or has the wrong CRS", call. = FALSE)
  }
  # The Shapefile advertises EPSG:5179 through a BOUNDCRS wrapper. Coordinates
  # are already native EPSG:5179, so normalize metadata without transforming.
  suppressWarnings(sf::st_crs(official) <- sf::st_crs(native_epsg))
  canonical <- canonicalize_official_grid(official, contract$scene$official_cell_id_column)
  official <- canonical$data
  centers <- suppressWarnings(sf::st_centroid(sf::st_geometry(official)))
  coordinates <- sf::st_coordinates(centers)
  widths <- vapply(sf::st_geometry(head(official, 100L)), function(geometry) diff(sf::st_bbox(geometry)[c("xmin", "xmax")]), numeric(1L))
  heights <- vapply(sf::st_geometry(head(official, 100L)), function(geometry) diff(sf::st_bbox(geometry)[c("ymin", "ymax")]), numeric(1L))
  if (any(abs(widths - 500) > 1e-8) || any(abs(heights - 500) > 1e-8)) {
    stop("Official grid cells are not 500 m squares", call. = FALSE)
  }
  native_points <- sf::st_as_sf(
    data.frame(center_x_native = coordinates[, "X"], center_y_native = coordinates[, "Y"],
               official_grid_id = official$official_grid_id),
    coords = c("center_x_native", "center_y_native"), crs = native_epsg, remove = FALSE
  )
  points <- sf::st_transform(native_points, processing_epsg)
  xy <- sf::st_coordinates(points)
  xy[, "X"] <- round_to_precision(xy[, "X"], precision)
  xy[, "Y"] <- round_to_precision(xy[, "Y"], precision)
  points <- sf::st_as_sf(
    data.frame(center_x_5186 = xy[, "X"], center_y_5186 = xy[, "Y"]),
    coords = c("center_x_5186", "center_y_5186"), crs = processing_epsg, remove = FALSE
  )
  retained <- lengths(sf::st_within(points, sf::st_union(boundary))) > 0L
  result <- sf::st_drop_geometry(native_points)[retained, , drop = FALSE]
  result$center_x_5186 <- xy[retained, "X"]
  result$center_y_5186 <- xy[retained, "Y"]
  result$official_grid_row <- as.integer(round(result$center_y_native / 500))
  result$official_grid_column <- as.integer(round(result$center_x_native / 500))
  result <- result[order(result$official_grid_id, method = "radix"), , drop = FALSE]
  list(data = result, dedup = canonical)
}

write_geo_parquet <- function(value, path) {
  suppressWarnings(sfarrow::st_write_parquet(value, path))
  invisible(path)
}
