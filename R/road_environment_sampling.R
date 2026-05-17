suppressPackageStartupMessages({
  library(sf)
  library(tidyverse)
  library(arrow)
  library(future)
  library(future.mirai)
})

sf_use_s2(FALSE)

PROJECTED_CRS <- 5186
LONLAT_CRS <- 4326

HIGHWAY_RANKS <- tibble::tribble(
  ~highway_class, ~sampled_rank,
  "motorway", 1L,
  "trunk", 2L,
  "primary", 3L,
  "secondary", 4L,
  "tertiary", 5L,
  "residential", 6L,
  "service", 7L,
  "living_street", 8L,
  "unclassified", 9L
)

KEPT_HIGHWAYS <- HIGHWAY_RANKS$highway_class
EXCLUDED_HIGHWAYS <- c("footway", "pedestrian", "cycleway", "path")

sample_output_columns <- c(
  "point_id",
  "grid_id",
  "highway_class",
  "sampled_rank",
  "lon",
  "lat",
  "source_road_id",
  "nearest_neighbor_distance"
)

derive_layer_name <- function(path) {
  tools::file_path_sans_ext(basename(path))
}

ensure_dir <- function(path) {
  dir.create(path, recursive = TRUE, showWarnings = FALSE)
  invisible(path)
}

read_sf_projected <- function(path, layer = NULL, query = NULL, wkt_filter = NULL) {
  args <- list(dsn = path, quiet = TRUE)
  if (!is.null(layer)) args$layer <- layer
  if (!is.null(query)) args$query <- query
  if (!is.null(wkt_filter)) args$wkt_filter <- wkt_filter

  do.call(st_read, args) %>%
    st_transform(PROJECTED_CRS)
}

normalize_road_schema <- function(roads) {
  if ("selected_rank" %in% names(roads) && !"sampled_rank" %in% names(roads)) {
    roads <- roads %>% rename(sampled_rank = selected_rank)
  }
  if (!"source_road_id" %in% names(roads)) {
    roads$source_road_id <- seq_len(nrow(roads))
  }

  geometry <- st_geometry(roads)
  attrs <- roads %>%
    st_drop_geometry() %>%
    select(any_of(c("source_road_id", "highway_class", "sampled_rank"))) %>%
    mutate(sampled_rank = as.integer(sampled_rank)) %>%
    left_join(
      HIGHWAY_RANKS %>% rename(expected_rank = sampled_rank),
      by = "highway_class"
    ) %>%
    mutate(sampled_rank = coalesce(sampled_rank, expected_rank)) %>%
    mutate(source_road_id = as.integer(source_road_id)) %>%
    select(source_road_id, highway_class, sampled_rank)

  st_sf(attrs, geometry = geometry, crs = st_crs(roads))
}

build_seoul_grid <- function(
  cell_size_m = 500,
  boundary_path = "data/geodata/seoul_boundary.gpkg",
  grid_path = "data/grid_500m/seoul_grid_500m.gpkg",
  map_path = "data/grid_500m/seoul_grid_500m_map.png",
  force = FALSE
) {
  if (file.exists(grid_path) && !force) {
    return(read_sf_projected(grid_path))
  }

  ensure_dir(dirname(grid_path))
  ensure_dir(dirname(map_path))

  seoul <- read_sf_projected(boundary_path) %>%
    st_make_valid()

  grid <- st_make_grid(
    seoul,
    cellsize = cell_size_m,
    square = TRUE
  ) %>%
    st_sf(grid_id = seq_along(.), geometry = .) %>%
    st_filter(seoul, .predicate = st_intersects) %>%
    mutate(grid_id = row_number())

  st_write(grid, grid_path, layer = derive_layer_name(grid_path), delete_dsn = TRUE, quiet = TRUE)

  grid_plot <- ggplot() +
    geom_sf(data = grid, fill = NA, color = "grey65", linewidth = 0.15) +
    geom_sf(data = seoul, fill = NA, color = "#238b45", linewidth = 0.8) +
    coord_sf(datum = NA) +
    labs(
      title = paste0(cell_size_m, " m Seoul Grid"),
      subtitle = paste0(format(nrow(grid), big.mark = ","), " cells"),
      caption = "CRS: EPSG:5186"
    ) +
    theme_minimal(base_size = 12) +
    theme(axis.title = element_blank(), plot.title = element_text(face = "bold"))

  ggsave(map_path, grid_plot, width = 8, height = 8, dpi = 250)
  grid
}

grid_extent_boundary <- function(grid, buffer_m = 250) {
  grid %>%
    st_transform(PROJECTED_CRS) %>%
    st_bbox() %>%
    st_as_sfc() %>%
    st_buffer(buffer_m) %>%
    st_transform(LONLAT_CRS)
}

download_and_cache_osm_roads <- function(
  grid,
  out_path = "data/osm/seoul_roads_filtered.gpkg",
  osm_place = "South Korea",
  download_directory = "data/osm/osmextract_downloads",
  buffer_m = 250,
  force = FALSE
) {
  if (file.exists(out_path) && !force) {
    return(read_sf_projected(out_path) %>% normalize_road_schema())
  }

  if (!requireNamespace("osmextract", quietly = TRUE)) {
    stop("Package 'osmextract' is required. Install it and rerun the pipeline.", call. = FALSE)
  }

  ensure_dir(dirname(out_path))
  ensure_dir(download_directory)

  roads_raw <- osmextract::oe_get(
    place = osm_place,
    provider = "geofabrik",
    layer = "lines",
    boundary = grid_extent_boundary(grid, buffer_m = buffer_m),
    boundary_type = "spat",
    download_directory = download_directory,
    max_file_size = 5e9,
    extra_tags = c("highway", "tunnel"),
    quiet = FALSE,
    force_download = FALSE,
    force_vectortranslate = TRUE
  )

  roads <- roads_raw %>%
    st_as_sf() %>%
    filter(
      highway %in% KEPT_HIGHWAYS,
      !highway %in% EXCLUDED_HIGHWAYS,
      is.na(tunnel) | !tolower(as.character(tunnel)) %in% c("yes", "true", "1")
    ) %>%
    transmute(highway_class = highway, geometry = geometry) %>%
    left_join(HIGHWAY_RANKS, by = "highway_class") %>%
    st_transform(PROJECTED_CRS) %>%
    st_make_valid() %>%
    { suppressWarnings(st_collection_extract(., "LINESTRING", warn = FALSE)) } %>%
    { suppressWarnings(st_cast(., "LINESTRING", warn = FALSE)) } %>%
    filter(!st_is_empty(st_geometry(.)))

  st_write(roads, out_path, delete_dsn = TRUE, quiet = TRUE)
  normalize_road_schema(roads)
}

construct_seoul_road_network <- function(roads, boundary = NULL) {
  roads <- roads %>%
    normalize_road_schema() %>%
    filter(.data$highway_class %in% KEPT_HIGHWAYS) %>%
    st_transform(PROJECTED_CRS) %>%
    st_make_valid() %>%
    { suppressWarnings(st_collection_extract(., "LINESTRING", warn = FALSE)) } %>%
    filter(!st_is_empty(st_geometry(.)))

  if (!is.null(boundary)) {
    boundary_union <- boundary %>%
      st_transform(PROJECTED_CRS) %>%
      st_make_valid() %>%
      st_union()

    roads <- roads %>%
      st_filter(boundary_union, .predicate = st_intersects) %>%
      { suppressWarnings(st_intersection(., boundary_union)) } %>%
      { suppressWarnings(st_collection_extract(., "LINESTRING", warn = FALSE)) } %>%
      { suppressWarnings(st_cast(., "LINESTRING", warn = FALSE)) } %>%
      filter(!st_is_empty(st_geometry(.)))
  }

  roads %>%
    mutate(length_m = as.numeric(st_length(st_geometry(.)))) %>%
    filter(.data$length_m > 0) %>%
    select(source_road_id, highway_class, sampled_rank, length_m)
}

line_candidate_points <- function(geom, spacing_m, crs) {
  length_m <- as.numeric(st_length(geom))
  if (is.na(length_m) || length_m <= 0) {
    return(NULL)
  }

  if (length_m < spacing_m / 2) {
    return(NULL)
  }

  distances <- seq(spacing_m / 2, length_m, by = spacing_m)

  suppressWarnings(
    st_line_sample(st_sfc(geom, crs = crs), sample = pmin(distances / length_m, 1)) %>%
      st_cast("POINT", warn = FALSE)
  )
}

generate_road_candidates_chunk <- function(
  roads,
  spacing_m = 10
) {
  roads <- roads %>%
    st_transform(PROJECTED_CRS) %>%
    normalize_road_schema() %>%
    { suppressWarnings(st_cast(., "LINESTRING", warn = FALSE)) }

  crs <- st_crs(roads)
  geom <- st_geometry(roads)
  attrs <- roads %>% st_drop_geometry()

  purrr::map_dfr(seq_along(geom), function(i) {
    pts <- line_candidate_points(geom[[i]], spacing_m = spacing_m, crs = crs)
    if (is.null(pts) || length(pts) == 0) {
      return(tibble())
    }

    coords <- st_coordinates(pts)
    tibble(
      source_road_id = as.integer(attrs$source_road_id[[i]]),
      highway_class = attrs$highway_class[[i]],
      sampled_rank = as.integer(attrs$sampled_rank[[i]]),
      x = as.numeric(coords[, "X"]),
      y = as.numeric(coords[, "Y"])
    )
  })
}

make_row_chunks <- function(n_rows, chunk_size = 2000L) {
  if (n_rows == 0) {
    return(list())
  }
  split(seq_len(n_rows), ceiling(seq_len(n_rows) / chunk_size))
}

generate_road_candidates <- function(
  roads,
  spacing_m = 10,
  workers = 1L,
  chunk_size = 2000L
) {
  roads <- roads %>%
    mutate(.road_order = row_number())

  chunks <- make_row_chunks(nrow(roads), chunk_size = chunk_size)
  if (length(chunks) == 0) {
    return(tibble(
      candidate_id = integer(),
      source_road_id = integer(),
      highway_class = character(),
      sampled_rank = integer(),
      x = numeric(),
      y = numeric()
    ))
  }

  worker_count <- max(1L, as.integer(workers))
  if (worker_count > 1L && length(chunks) > 1L) {
    old_plan <- future::plan()
    on.exit(future::plan(old_plan), add = TRUE)
    future::plan(future.mirai::mirai_multisession, workers = worker_count)

    futures <- purrr::map(chunks, function(idx) {
      future::future({
        generate_road_candidates_chunk(roads[idx, ], spacing_m = spacing_m)
      }, seed = TRUE, packages = c("sf", "dplyr", "purrr", "tibble"))
    })
    candidates <- purrr::map_dfr(futures, future::value)
  } else {
    candidates <- purrr::map_dfr(chunks, function(idx) {
      generate_road_candidates_chunk(roads[idx, ], spacing_m = spacing_m)
    })
  }

  candidates %>%
    mutate(candidate_id = row_number()) %>%
    select(candidate_id, source_road_id, highway_class, sampled_rank, x, y)
}

cell_key <- function(cell_x, cell_y) {
  paste(cell_x, cell_y, sep = ":")
}

nearest_neighbor_distances_grid <- function(points, cell_size_m = 50) {
  n_points <- nrow(points)
  if (n_points == 0) {
    return(numeric())
  }
  if (n_points == 1) {
    return(NA_real_)
  }

  cell_x <- floor(points$x / cell_size_m)
  cell_y <- floor(points$y / cell_size_m)
  cell_index <- new.env(hash = TRUE, parent = emptyenv())

  for (i in seq_len(n_points)) {
    key <- cell_key(cell_x[[i]], cell_y[[i]])
    existing <- if (exists(key, envir = cell_index, inherits = FALSE)) {
      get(key, envir = cell_index, inherits = FALSE)
    } else {
      integer(0)
    }
    assign(key, c(existing, i), envir = cell_index)
  }

  max_radius <- max(diff(range(cell_x)), diff(range(cell_y))) + 1L
  purrr::map_dbl(seq_len(n_points), function(i) {
    best <- Inf
    radius <- 1L

    while (radius <= max_radius) {
      neighbor_ids <- integer(0)
      for (dx in seq.int(-radius, radius)) {
        for (dy in seq.int(-radius, radius)) {
          key <- cell_key(cell_x[[i]] + dx, cell_y[[i]] + dy)
          if (exists(key, envir = cell_index, inherits = FALSE)) {
            neighbor_ids <- c(neighbor_ids, get(key, envir = cell_index, inherits = FALSE))
          }
        }
      }

      neighbor_ids <- setdiff(unique(neighbor_ids), i)
      if (length(neighbor_ids) > 0) {
        dist_sq <- (points$x[neighbor_ids] - points$x[[i]])^2 +
          (points$y[neighbor_ids] - points$y[[i]])^2
        best <- min(best, sqrt(min(dist_sq)))
      }

      if (is.finite(best) && best <= radius * cell_size_m) {
        break
      }
      radius <- radius + 1L
    }

    if (is.finite(best)) best else NA_real_
  })
}

poisson_disk_thin_candidates <- function(
  candidates,
  min_spacing_m = 50,
  target_count = 40000L,
  seed = 20260517L
) {
  if (nrow(candidates) == 0) {
    return(tibble(
      point_id = integer(),
      source_road_id = integer(),
      highway_class = character(),
      sampled_rank = integer(),
      x = numeric(),
      y = numeric(),
      nearest_neighbor_distance = numeric()
    ))
  }

  set.seed(seed)
  order_idx <- sample.int(nrow(candidates))
  candidates <- candidates[order_idx, , drop = FALSE]
  candidates$cell_x <- floor(candidates$x / min_spacing_m)
  candidates$cell_y <- floor(candidates$y / min_spacing_m)

  accepted_rows <- integer(0)
  accepted_x <- numeric(0)
  accepted_y <- numeric(0)
  cell_index <- new.env(hash = TRUE, parent = emptyenv())
  min_spacing_sq <- min_spacing_m^2

  for (i in seq_len(nrow(candidates))) {
    cx <- candidates$cell_x[[i]]
    cy <- candidates$cell_y[[i]]
    neighbor_ids <- integer(0)

    for (dx in -1:1) {
      for (dy in -1:1) {
        key <- cell_key(cx + dx, cy + dy)
        if (exists(key, envir = cell_index, inherits = FALSE)) {
          neighbor_ids <- c(neighbor_ids, get(key, envir = cell_index, inherits = FALSE))
        }
      }
    }

    nearest <- NA_real_
    if (length(neighbor_ids) > 0) {
      dist_sq <- (accepted_x[neighbor_ids] - candidates$x[[i]])^2 +
        (accepted_y[neighbor_ids] - candidates$y[[i]])^2
      nearest <- sqrt(min(dist_sq))
      if (any(dist_sq < min_spacing_sq)) {
        next
      }
    }

    accepted_id <- length(accepted_rows) + 1L
    accepted_rows[[accepted_id]] <- i
    accepted_x[[accepted_id]] <- candidates$x[[i]]
    accepted_y[[accepted_id]] <- candidates$y[[i]]

    key <- cell_key(cx, cy)
    existing <- if (exists(key, envir = cell_index, inherits = FALSE)) {
      get(key, envir = cell_index, inherits = FALSE)
    } else {
      integer(0)
    }
    assign(key, c(existing, accepted_id), envir = cell_index)

    if (!is.null(target_count) && length(accepted_rows) >= target_count) {
      break
    }
  }

  accepted <- candidates[accepted_rows, , drop = FALSE] %>%
    transmute(
      point_id = row_number(),
      source_road_id,
      highway_class,
      sampled_rank,
      x,
      y
    )

  accepted %>%
    mutate(nearest_neighbor_distance = nearest_neighbor_distances_grid(accepted, cell_size_m = min_spacing_m))
}

samples_to_sf <- function(samples) {
  samples %>%
    st_as_sf(coords = c("x", "y"), crs = PROJECTED_CRS, remove = FALSE)
}

assign_samples_to_grid <- function(samples, grid) {
  if (nrow(samples) == 0) {
    return(tibble(
      point_id = integer(),
      grid_id = integer(),
      highway_class = character(),
      sampled_rank = integer(),
      lon = numeric(),
      lat = numeric(),
      source_road_id = integer(),
      nearest_neighbor_distance = numeric()
    ))
  }

  point_sf <- samples_to_sf(samples)
  grid_sf <- grid %>%
    st_transform(PROJECTED_CRS) %>%
    select(grid_id)

  joined <- suppressWarnings(st_join(point_sf, grid_sf, join = st_within, left = TRUE)) %>%
    group_by(point_id) %>%
    slice(1) %>%
    ungroup()

  missing_grid <- which(is.na(joined$grid_id))
  if (length(missing_grid) > 0 && nrow(grid_sf) > 0) {
    nearest <- st_nearest_feature(joined[missing_grid, ], grid_sf)
    joined$grid_id[missing_grid] <- grid_sf$grid_id[nearest]
  }

  lonlat <- joined %>%
    st_transform(LONLAT_CRS) %>%
    st_coordinates()

  joined %>%
    st_drop_geometry() %>%
    mutate(
      grid_id = as.integer(grid_id),
      lon = as.numeric(lonlat[, "X"]),
      lat = as.numeric(lonlat[, "Y"])
    ) %>%
    arrange(point_id) %>%
    select(all_of(sample_output_columns))
}

parquet_has_schema <- function(path, required_columns = sample_output_columns) {
  if (!file.exists(path)) {
    return(FALSE)
  }

  columns <- tryCatch(
    names(arrow::read_parquet(path, as_data_frame = FALSE)),
    error = function(e) NULL
  )
  !is.null(columns) && identical(columns, required_columns)
}

run_global_road_network_sampling <- function(
  roads,
  grid,
  boundary = NULL,
  final_parquet = "data/sampling_global/seoul_road_network_samples.parquet",
  candidate_spacing_m = 10,
  min_spacing_m = 50,
  target_count = 40000L,
  seed = 20260517L,
  candidate_workers = 1L,
  candidate_chunk_size = 2000L
) {
  ensure_dir(dirname(final_parquet))

  message("Constructing unified Seoul road network...")
  network <- construct_seoul_road_network(roads = roads, boundary = boundary)
  message(
    "Network features: ", format(nrow(network), big.mark = ","),
    "; length m: ", format(round(sum(network$length_m, na.rm = TRUE)), big.mark = ",")
  )
  message(
    "Generating regular road candidates with ", candidate_workers,
    " worker(s), chunk size ", candidate_chunk_size, "..."
  )
  candidates <- generate_road_candidates(
    network,
    spacing_m = candidate_spacing_m,
    workers = candidate_workers,
    chunk_size = candidate_chunk_size
  )
  message("Candidate points: ", format(nrow(candidates), big.mark = ","))
  message("Applying greedy Poisson-disk-style thinning...")
  thinned <- poisson_disk_thin_candidates(
    candidates = candidates,
    min_spacing_m = min_spacing_m,
    target_count = target_count,
    seed = seed
  )
  message("Accepted points: ", format(nrow(thinned), big.mark = ","))
  message("Assigning accepted points to 500 m grids...")
  samples <- assign_samples_to_grid(thinned, grid = grid)

  arrow::write_parquet(samples, final_parquet)
  attr(samples, "candidate_count") <- nrow(candidates)
  attr(samples, "network_road_count") <- nrow(network)
  attr(samples, "network_length_m") <- sum(network$length_m, na.rm = TRUE)
  samples
}

write_debug_outputs <- function(
  samples,
  output_dir = "data/sampling_global/debug",
  sample_points_gpkg = "sampled_points_global.gpkg"
) {
  ensure_dir(output_dir)

  sampled_points <- samples %>%
    filter(!is.na(lon), !is.na(lat)) %>%
    st_as_sf(coords = c("lon", "lat"), crs = LONLAT_CRS, remove = FALSE) %>%
    st_transform(PROJECTED_CRS)

  st_write(sampled_points, file.path(output_dir, sample_points_gpkg), delete_dsn = TRUE, quiet = TRUE)
  invisible(sampled_points)
}

simplify_for_leaflet <- function(x, tolerance_m) {
  x %>%
    st_transform(PROJECTED_CRS) %>%
    st_simplify(dTolerance = tolerance_m, preserveTopology = TRUE) %>%
    st_transform(LONLAT_CRS)
}

thin_sf_by_group <- function(x, group_col, max_features, seed = 20260517L) {
  if (nrow(x) <= max_features) {
    return(x)
  }

  set.seed(seed)
  groups <- split(seq_len(nrow(x)), x[[group_col]])
  sampled_idx <- purrr::imap(groups, function(idx, group_name) {
    n_group <- max(1L, floor(length(idx) / nrow(x) * max_features))
    sample(idx, size = min(length(idx), n_group))
  }) %>%
    unlist(use.names = FALSE)

  x[sort(sampled_idx), ]
}

validate_leaflet_export <- function(out_html) {
  dependency_dir <- paste0(tools::file_path_sans_ext(out_html), "_files")

  if (!file.exists(out_html)) {
    stop("Leaflet export failed: HTML file was not created: ", out_html, call. = FALSE)
  }
  if (!dir.exists(dependency_dir)) {
    stop("Leaflet export failed: dependency directory was not created: ", dependency_dir, call. = FALSE)
  }

  html_text <- paste(readLines(out_html, warn = FALSE, n = 200), collapse = "\n")
  has_leaflet <- grepl("leaflet", html_text, fixed = TRUE)
  has_widget <- grepl("htmlwidgets", html_text, fixed = TRUE)
  html_size <- file.info(out_html)$size

  if (!has_leaflet || !has_widget || is.na(html_size) || html_size <= 0) {
    stop("Leaflet export failed structural validation; HTML appears incomplete.", call. = FALSE)
  }

  message("Leaflet HTML size: ", format(utils::object.size(readLines(out_html, warn = FALSE)), units = "auto"))
  message("Leaflet HTML file bytes: ", format(html_size, big.mark = ","))
  message("Leaflet dependency directory: ", dependency_dir)
  invisible(TRUE)
}

make_leaflet_map <- function(
  boundary,
  grid,
  samples,
  out_html = "data/sampling_global/seoul_road_network_sampling_map.html",
  max_grid_cells = 5000,
  max_points = 30000,
  grid_simplify_tolerance_m = 1,
  boundary_simplify_tolerance_m = 5
) {
  if (!requireNamespace("leaflet", quietly = TRUE) ||
      !requireNamespace("htmlwidgets", quietly = TRUE)) {
    stop("Packages 'leaflet' and 'htmlwidgets' are required for map output.", call. = FALSE)
  }

  ensure_dir(dirname(out_html))

  boundary_map <- boundary %>%
    simplify_for_leaflet(boundary_simplify_tolerance_m)

  grid_map <- grid %>%
    slice_head(n = max_grid_cells) %>%
    simplify_for_leaflet(grid_simplify_tolerance_m)

  points_map <- samples %>%
    filter(!is.na(lon), !is.na(lat)) %>%
    slice_head(n = max_points) %>%
    st_as_sf(coords = c("lon", "lat"), crs = LONLAT_CRS, remove = FALSE)

  message("Leaflet layer counts:")
  message("  boundary features: ", nrow(boundary_map))
  message("  grid features: ", nrow(grid_map), " / ", nrow(grid))
  message("  sampled points: ", nrow(points_map), " / ", sum(!is.na(samples$lon)))
  message("Leaflet layer object sizes:")
  message("  boundary: ", format(utils::object.size(boundary_map), units = "auto"))
  message("  grid: ", format(utils::object.size(grid_map), units = "auto"))
  message("  points: ", format(utils::object.size(points_map), units = "auto"))

  map <- leaflet::leaflet(options = leaflet::leafletOptions(preferCanvas = TRUE)) %>%
    leaflet::addProviderTiles(leaflet::providers$CartoDB.Positron) %>%
    leaflet::addPolygons(
      data = boundary_map,
      color = "#238b45",
      weight = 2,
      fill = FALSE,
      group = "Seoul boundary"
    ) %>%
    leaflet::addPolygons(
      data = grid_map,
      color = "#8c8c8c",
      weight = 0.45,
      fill = FALSE,
      opacity = 0.5,
      group = "500m grid"
    ) %>%
    leaflet::addCircleMarkers(
      data = points_map,
      lng = ~lon,
      lat = ~lat,
      radius = 2,
      stroke = FALSE,
      fillOpacity = 0.75,
      color = "#2166ac",
      popup = ~paste0(
        "point_id: ", point_id,
        "<br>grid_id: ", grid_id,
        "<br>class: ", highway_class,
        "<br>nearest prior spacing: ", round(nearest_neighbor_distance, 1), " m"
      ),
      group = "Sampled points"
    ) %>%
    leaflet::addLayersControl(
      overlayGroups = c("Seoul boundary", "500m grid", "Sampled points"),
      options = leaflet::layersControlOptions(collapsed = FALSE)
    )

  htmlwidgets::saveWidget(map, out_html, selfcontained = FALSE)
  validate_leaflet_export(out_html)
  map
}

summarise_samples <- function(samples) {
  sampled <- samples %>% filter(!is.na(lon), !is.na(lat))

  if (nrow(sampled) == 0) {
    empty_distribution <- tibble(
      grids_with_points = integer(),
      min_n = integer(),
      p25_n = numeric(),
      median_n = numeric(),
      mean_n = numeric(),
      p75_n = numeric(),
      max_n = integer()
    )
    empty_distance <- tibble(
      min_m = numeric(),
      p05_m = numeric(),
      median_m = numeric(),
      mean_m = numeric(),
      p95_m = numeric(),
      max_m = numeric()
    )

    return(list(
      rows = nrow(samples),
      sampled_points = 0L,
      grids_covered = 0L,
      class_counts = tibble(highway_class = character(), n = integer()),
      class_proportions = tibble(highway_class = character(), n = integer(), proportion = numeric()),
      per_grid_points = empty_distribution,
      nearest_neighbor_distance = empty_distance
    ))
  }

  list(
    rows = nrow(samples),
    sampled_points = nrow(sampled),
    grids_covered = dplyr::n_distinct(sampled$grid_id),
    class_counts = sampled %>% count(highway_class, sort = TRUE),
    class_proportions = sampled %>%
      count(highway_class, sort = TRUE) %>%
      mutate(proportion = n / sum(n)),
    per_grid_points = sampled %>%
      count(grid_id, name = "n_points") %>%
      summarise(
        grids_with_points = n(),
        min_n = min(n_points),
        p25_n = as.numeric(quantile(n_points, 0.25)),
        median_n = median(n_points),
        mean_n = mean(n_points),
        p75_n = as.numeric(quantile(n_points, 0.75)),
        max_n = max(n_points),
        .groups = "drop"
      ),
    nearest_neighbor_distance = sampled %>%
      filter(!is.na(nearest_neighbor_distance)) %>%
      summarise(
        min_m = min(nearest_neighbor_distance),
        p05_m = as.numeric(quantile(nearest_neighbor_distance, 0.05)),
        median_m = median(nearest_neighbor_distance),
        mean_m = mean(nearest_neighbor_distance),
        p95_m = as.numeric(quantile(nearest_neighbor_distance, 0.95)),
        max_m = max(nearest_neighbor_distance),
        .groups = "drop"
      )
  )
}

print_sample_diagnostics <- function(summary) {
  message("Rows written: ", format(summary$rows, big.mark = ","))
  message("Sampled points: ", format(summary$sampled_points, big.mark = ","))
  message("Grids covered: ", format(summary$grids_covered, big.mark = ","))
  message("Highway class proportions:")
  print(summary$class_proportions)
  message("Points per grid distribution:")
  print(summary$per_grid_points)
  message("Nearest-neighbor distance summary:")
  print(summary$nearest_neighbor_distance)
  invisible(summary)
}
