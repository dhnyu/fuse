# S11 dissertation 5.4.1/5.4.2; user-approved D1-D5 (2026-09-23).
# Pure observations -> descriptor records. No source loading, targets, or publisher.
# Geometry is already clipped to the original 500 m scene (Chapter 3.1).

s11_descriptor <- function(value, total, valid = total, reason = NULL, ...) {
  if (valid < 0 || valid > total) stop("S11 invalid support counts")
  if (!is.null(value) && any(!is.finite(value))) stop("S11 nonfinite descriptor")
  if (is.null(value) && is.null(reason)) stop("S11 null requires reason")
  list(value = value, null_reason = reason, total_count = total,
       valid_count = valid, invalid_count = total - valid, ...)
}

s11_mean <- function(x, positive = FALSE) {
  if (any(is.infinite(x) | is.nan(x))) stop("S11 infinite/NaN observation")
  valid <- !is.na(x) & (!positive | x > 0)
  if (!any(valid)) return(s11_descriptor(NULL, length(x), 0L, "no_valid_support"))
  s11_descriptor(mean(x[valid]), length(x), sum(valid))
}

s11_location_dispersion <- function(geometry) {
  n <- length(geometry)
  if (!n) return(s11_descriptor(NULL, 0L, 0L, "empty_entity_type"))
  centers <- t(vapply(geometry, function(g) {
    b <- sf::st_bbox(g)
    c((b[["xmin"]] + b[["xmax"]]) / 2, (b[["ymin"]] + b[["ymax"]]) / 2)
  }, numeric(2)))
  s11_descriptor(sqrt(mean(rowSums(sweep(centers, 2L, colMeans(centers))^2))), n)
}

s11_axial_dispersion <- function(angles, weights = rep(1, length(angles)), total = length(angles)) {
  if (length(angles) != length(weights) || any(!is.finite(weights)) || any(weights <= 0)) stop("S11 axial weights")
  valid <- is.finite(angles)
  if (!any(valid)) return(s11_descriptor(NULL, total, 0L, "no_identifiable_orientation"))
  resultant <- sqrt(sum(weights[valid] * cos(2 * angles[valid]))^2 +
                    sum(weights[valid] * sin(2 * angles[valid]))^2) / sum(weights[valid])
  # Clamp only roundoff of a mathematically bounded circular resultant.
  if (resultant > 1 + 64 * .Machine$double.eps) stop("S11 axial numerical error")
  s11_descriptor(max(0, 1 - resultant), total, sum(valid), valid_weight = sum(weights[valid]))
}

s11_building_orientation <- function(geometry) {
  if (!length(geometry)) return(s11_descriptor(NULL, 0L, 0L, "empty_entity_type"))
  rectangles <- sf::st_minimum_rotated_rectangle(geometry)
  angles <- vapply(rectangles, function(g) {
    xy <- sf::st_coordinates(g)[, 1:2, drop = FALSE]
    delta <- xy[-1, , drop = FALSE] - xy[-nrow(xy), , drop = FALSE]
    lengths <- sqrt(rowSums(delta^2))
    if (!length(lengths) || max(lengths) <= 0) return(NA_real_)
    # Numerical square ambiguity only: do not invent an aspect-ratio cutoff.
    if (max(lengths) - min(lengths) <= 64 * .Machine$double.eps * max(lengths)) return(NA_real_)
    axis <- delta[which.max(lengths), ]
    atan2(axis[2], axis[1]) %% pi
  }, numeric(1))
  s11_axial_dispersion(angles)
}

s11_road_orientation <- function(geometry) {
  if (!length(geometry)) return(s11_descriptor(NULL, 0L, 0L, "empty_entity_type"))
  lines <- suppressWarnings(sf::st_cast(geometry, "LINESTRING"))
  segments <- lapply(lines, function(g) {
    xy <- sf::st_coordinates(g)[, 1:2, drop = FALSE]
    xy[-1, , drop = FALSE] - xy[-nrow(xy), , drop = FALSE]
  })
  delta <- do.call(rbind, segments)
  weights <- sqrt(rowSums(delta^2))
  positive <- weights > 0
  angles <- atan2(delta[positive, 2], delta[positive, 1]) %% pi
  s11_axial_dispersion(angles, weights[positive], total = length(weights))
}

s11_composition <- function(values, keys) {
  if (anyDuplicated(keys) || anyNA(keys)) stop("S11 category dictionary")
  values <- as.character(values)
  missing <- is.na(values) | values == ""
  known <- !missing & values %in% keys
  extras <- list(missing_count = sum(missing), unknown_count = sum(!missing & !known), category_keys = keys)
  if (!any(known)) return(do.call(s11_descriptor, c(list(NULL, length(values), 0L, "no_known_categories"), extras)))
  counts <- tabulate(match(values[known], keys), nbins = length(keys))
  do.call(s11_descriptor, c(list(counts / sum(counts), length(values), sum(known)), extras))
}

s11_resolve_categories <- function(values, entries, attribute) {
  rows <- entries[vapply(entries, function(x) identical(x$attribute, attribute), logical(1))]
  rows <- rows[order(vapply(rows, function(x) x$source_order, numeric(1)),
                     vapply(rows, function(x) x$category_key, character(1)), method = "radix")]
  keys <- vapply(rows, function(x) x$category_key, character(1))
  # A POI code alone is ambiguous. Full-path keys are required for hierarchy fields.
  if (grepl("^CLASS_L", attribute)) return(s11_composition(values, keys))
  aliases <- setNames(as.list(keys), keys)
  collisions <- character()
  for (row in rows) {
    for (alias in unique(c(row$source_label, row$source_code, unlist(row$source_codes)))) {
      if (is.null(aliases[[alias]])) aliases[[alias]] <- row$category_key
      else if (!identical(aliases[[alias]], row$category_key)) collisions <- c(collisions, alias)
    }
  }
  # Existing accepted source alias (model_data.py), never a learned vocabulary.
  if (identical(attribute, "A11") && "12" %in% keys) aliases[["블록구조"]] <- "12"
  mapped <- vapply(as.character(values), function(x) {
    if (is.na(x) || !nzchar(x)) return(NA_character_)
    value <- aliases[[x]]
    if (is.null(value)) paste0("UNKNOWN:", x) else value
  }, character(1))
  # Exact keys win; otherwise preserve the accepted dictionary's first-source-order
  # alias rule (model_data.py:build_vocabulary), with collision QC. No remapping
  # of the source data, and no selection based on S11 results.
  result <- s11_composition(mapped, keys)
  result$alias_collision_count <- length(unique(collisions))
  result
}

s11_poi_l2_keys <- function(pois) {
  good <- !is.na(pois$CLASS_L1_STATE) & !is.na(pois$CLASS_L2_STATE) &
    pois$CLASS_L1_STATE == "VALUE" & pois$CLASS_L2_STATE == "VALUE" &
    !is.na(pois$CLASS_L1_CODE) & !is.na(pois$CLASS_L2_CODE)
  ifelse(good, paste(pois$CLASS_L1_CODE, pois$CLASS_L2_CODE, sep = "/"), NA_character_)
}

s11_relation_descriptors <- function(edges, node_ids) {
  if (anyDuplicated(node_ids)) stop("S11 duplicate nodes")
  source <- edges$source_local_entity_id
  destination <- edges$destination_local_entity_id
  masks <- edges$relation_mask
  if (anyNA(edges) || any(!source %in% node_ids | !destination %in% node_ids) ||
      any(source == destination) || any(masks <= 0 | masks > 31 | masks != as.integer(masks))) stop("S11 invalid relation edge")
  key <- paste(source, destination, sep = "/")
  if (anyDuplicated(key)) stop("S11 duplicate ordered pair")
  reverse <- match(paste(destination, source, sep = "/"), key)
  for (bit in c(1L, 8L, 16L)) {
    use <- bitwAnd(masks, bit) != 0
    if (anyNA(reverse[use]) || any(bitwAnd(masks[reverse[use]], bit) == 0)) stop("S11 asymmetric relation")
  }
  for (pair in list(c(2L, 4L), c(4L, 2L))) {
    use <- bitwAnd(masks, pair[1]) != 0
    if (anyNA(reverse[use]) || any(bitwAnd(masks[reverse[use]], pair[2]) == 0)) stop("S11 CNT/WIT inverse")
  }
  if (anyDuplicated(destination[bitwAnd(masks, 2L) != 0])) stop("S11 multiple containment hosts")
  counts <- vapply(c(1L, 2L, 4L, 8L, 16L), function(bit) sum(bitwAnd(masks, bit) != 0), integer(1))
  names(counts) <- c("SN", "CNT", "WIT", "INT", "CON")
  events <- c(SN = counts[["SN"]] / 2, INC = counts[["CNT"]], INT = counts[["INT"]] / 2, CON = counts[["CON"]] / 2)
  total <- sum(events)
  composition <- if (total) s11_descriptor(unname(events / total), total, category_keys = names(events)) else
    s11_descriptor(NULL, 0L, 0L, "no_relation_events", category_keys = names(events))
  degree <- if (length(node_ids)) s11_descriptor(nrow(edges) / length(node_ids), length(node_ids)) else
    s11_descriptor(NULL, 0L, 0L, "empty_scene")
  list(relation_composition = composition, mean_relational_degree = degree,
       qc = list(directed_counts = counts, event_counts = events, ordered_pairs = nrow(edges), nodes = length(node_ids)))
}

s11_landcover <- function(fractions, support) {
  if (length(dim(fractions)) != 2L || ncol(fractions) != length(support) ||
      any(!is.finite(support)) || any(support < 0 | support > 1)) stop("S11 landcover support")
  valid <- support > 0
  if (any(!is.finite(fractions[, valid, drop = FALSE])) || any(fractions[, valid, drop = FALSE] < 0) ||
      any(abs(colSums(fractions[, valid, drop = FALSE]) - 1) > 1e-6)) stop("S11 invalid landcover proportions")
  if (!any(valid)) return(s11_descriptor(NULL, length(support), 0L, "no_valid_raster_support", valid_weight = 0))
  result <- as.vector(fractions[, valid, drop = FALSE] %*% support[valid] / sum(support[valid]))
  s11_descriptor(result, length(support), sum(valid), valid_weight = sum(support))
}

s11_dem <- function(values, support) {
  if (length(values) != length(support) || any(!is.finite(support)) || any(support < 0 | support > 1)) stop("S11 DEM support")
  valid <- support > 0
  if (any(!is.finite(values[valid])) || any(values[valid] == -32767)) stop("S11 invalid supported DEM")
  if (!any(valid)) {
    absent <- s11_descriptor(NULL, length(values), 0L, "no_valid_raster_support", valid_weight = 0)
    return(list(mean_elevation = absent, elevation_variability = absent))
  }
  v <- values[valid]; w <- support[valid]
  mu <- sum(v * w) / sum(w)
  make <- function(x) s11_descriptor(x, length(values), sum(valid), valid_weight = sum(w))
  list(mean_elevation = make(mu), elevation_variability = make(sqrt(sum(w * (v - mu)^2) / sum(w))))
}

s11_geometry_descriptors <- function(buildings, roads, pois) {
  for (pair in list(list(buildings, c("POLYGON", "MULTIPOLYGON")),
                    list(roads, c("LINESTRING", "MULTILINESTRING")), list(pois, "POINT"))) {
    g <- pair[[1]]
    if (is.na(sf::st_crs(g)$epsg) || sf::st_crs(g)$epsg != 5186 ||
        any(!sf::st_is_valid(g)) || any(sf::st_is_empty(g)) ||
        any(!as.character(sf::st_geometry_type(g)) %in% pair[[2]])) stop("S11 original geometry/CRS")
  }
  nb <- length(buildings); nr <- length(roads); np <- length(pois)
  area <- as.numeric(sf::st_area(buildings)); length_m <- as.numeric(sf::st_length(roads))
  perimeter <- as.numeric(sf::st_length(sf::st_boundary(buildings)))
  if (any(area <= 0 | perimeter <= 0) || any(length_m <= 0)) stop("S11 degenerate geometry")
  coverage <- if (nb) as.numeric(sf::st_area(sf::st_union(buildings))) / 250000 else 0
  if (coverage > 1 + 1e-10) stop("S11 footprint coverage exceeds window")
  list(building_coverage = s11_descriptor(coverage, nb),
       road_density = s11_descriptor(sum(length_m) / 1000 / 0.25, nr),
       poi_density = s11_descriptor(np / 0.25, np),
       mean_building_footprint_size = s11_mean(area),
       mean_building_compactness = s11_mean(4 * pi * area / perimeter^2),
       building_orientation_dispersion = s11_building_orientation(buildings),
       road_orientation_dispersion = s11_road_orientation(roads),
       mean_road_segment_length = s11_mean(length_m),
       building_location_dispersion = s11_location_dispersion(buildings),
       road_location_dispersion = s11_location_dispersion(roads),
       poi_location_dispersion = s11_location_dispersion(pois))
}
