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
  "grid_id",
  "sample_id",
  "highway_class",
  "sampled_rank",
  "lon",
  "lat",
  "class_length_m",
  "class_proportion",
  "total_road_length_m"
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

  geometry <- st_geometry(roads)
  attrs <- roads %>%
    st_drop_geometry() %>%
    select(any_of(c("highway_class", "sampled_rank"))) %>%
    mutate(sampled_rank = as.integer(sampled_rank)) %>%
    left_join(
      HIGHWAY_RANKS %>% rename(expected_rank = sampled_rank),
      by = "highway_class"
    ) %>%
    mutate(sampled_rank = coalesce(sampled_rank, expected_rank)) %>%
    select(highway_class, sampled_rank)

  st_sf(attrs, geometry = geometry, crs = st_crs(roads))
}

build_seoul_grid <- function(
  cell_size_m = 1000,
  boundary_path = "data/geodata/seoul_boundary.gpkg",
  grid_path = "data/grid_1km/seoul_grid_1km.gpkg",
  map_path = "data/grid_1km/seoul_grid_1km_map.png",
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
    filter(!st_is_empty(st_geometry(.)))

  st_write(roads, out_path, delete_dsn = TRUE, quiet = TRUE)
  normalize_road_schema(roads)
}

empty_grid_samples <- function(grid_id, n_samples = 10L) {
  tibble(
    grid_id = as.integer(grid_id),
    sample_id = seq_len(n_samples),
    highway_class = NA_character_,
    sampled_rank = NA_integer_,
    lon = NA_real_,
    lat = NA_real_,
    class_length_m = NA_real_,
    class_proportion = NA_real_,
    total_road_length_m = 0
  )
}

make_seed <- function(grid_id, sample_id = 0L, seed_base = 100000L) {
  as.integer((seed_base + as.integer(grid_id) * 1000L + as.integer(sample_id)) %% .Machine$integer.max)
}

sample_point_on_lines <- function(lines, seed) {
  set.seed(seed)

  line_set <- st_union(st_geometry(lines)) %>%
    { suppressWarnings(st_collection_extract(., "LINESTRING", warn = FALSE)) } %>%
    { suppressWarnings(st_cast(., "LINESTRING", warn = FALSE)) }

  if (length(line_set) == 0 || all(st_is_empty(line_set))) {
    return(c(lon = NA_real_, lat = NA_real_))
  }

  lengths <- as.numeric(st_length(line_set))
  valid <- which(lengths > 0)
  if (length(valid) == 0) {
    return(c(lon = NA_real_, lat = NA_real_))
  }

  chosen <- sample(valid, size = 1, prob = lengths[valid])
  sampled <- st_line_sample(line_set[chosen], n = 1, type = "random") %>%
    st_cast("POINT", warn = FALSE)

  if (length(sampled) == 0 || all(st_is_empty(sampled))) {
    return(c(lon = NA_real_, lat = NA_real_))
  }

  coords <- sampled %>%
    st_sfc(crs = st_crs(lines)) %>%
    st_transform(LONLAT_CRS) %>%
    st_coordinates()

  stats::setNames(as.numeric(coords[1, c("X", "Y")]), c("lon", "lat"))
}

process_one_grid_probabilistic <- function(
  cell,
  roads,
  n_samples = 10L,
  seed_base = 100000L
) {
  grid_id <- as.integer(cell$grid_id[[1]])
  candidate_idx <- st_intersects(cell, roads, sparse = TRUE)[[1]]

  if (length(candidate_idx) == 0) {
    return(empty_grid_samples(grid_id, n_samples = n_samples))
  }

  clipped <- suppressWarnings(st_intersection(roads[candidate_idx, ], cell)) %>%
    { suppressWarnings(st_collection_extract(., "LINESTRING", warn = FALSE)) } %>%
    filter(!st_is_empty(st_geometry(.)))

  if (nrow(clipped) == 0) {
    return(empty_grid_samples(grid_id, n_samples = n_samples))
  }

  length_summary <- clipped %>%
    mutate(length_m = as.numeric(st_length(st_geometry(.)))) %>%
    filter(length_m > 0) %>%
    st_drop_geometry() %>%
    group_by(highway_class, sampled_rank) %>%
    summarise(class_length_m = sum(length_m), .groups = "drop") %>%
    arrange(sampled_rank)

  total_length <- sum(length_summary$class_length_m, na.rm = TRUE)
  if (total_length <= 0 || nrow(length_summary) == 0) {
    return(empty_grid_samples(grid_id, n_samples = n_samples))
  }

  length_summary <- length_summary %>%
    mutate(class_proportion = class_length_m / total_length)

  set.seed(make_seed(grid_id, sample_id = 0L, seed_base = seed_base))
  allocations <- as.integer(rmultinom(1, size = n_samples, prob = length_summary$class_proportion))

  sample_plan <- length_summary %>%
    mutate(n_allocated = allocations) %>%
    filter(n_allocated > 0) %>%
    tidyr::uncount(n_allocated) %>%
    mutate(sample_id = row_number()) %>%
    select(sample_id, highway_class, sampled_rank, class_length_m, class_proportion)

  purrr::pmap_dfr(sample_plan, function(
    sample_id,
    highway_class,
    sampled_rank,
    class_length_m,
    class_proportion
  ) {
    class_lines <- clipped %>% filter(.data$highway_class == highway_class)
    point <- sample_point_on_lines(
      class_lines,
      seed = make_seed(grid_id, sample_id = sample_id, seed_base = seed_base)
    )

    tibble(
      grid_id = grid_id,
      sample_id = as.integer(sample_id),
      highway_class = highway_class,
      sampled_rank = as.integer(sampled_rank),
      lon = point[["lon"]],
      lat = point[["lat"]],
      class_length_m = as.numeric(class_length_m),
      class_proportion = as.numeric(class_proportion),
      total_road_length_m = as.numeric(total_length)
    )
  }) %>%
    arrange(sample_id)
}

read_grid_ids <- function(grid_path, layer = derive_layer_name(grid_path)) {
  st_read(grid_path, query = paste0("SELECT grid_id FROM ", layer), quiet = TRUE) %>%
    st_drop_geometry() %>%
    pull(grid_id)
}

read_grid_chunk <- function(grid_path, grid_ids, layer = derive_layer_name(grid_path)) {
  id_sql <- paste(as.integer(grid_ids), collapse = ",")
  read_sf_projected(
    grid_path,
    query = paste0("SELECT * FROM ", layer, " WHERE grid_id IN (", id_sql, ")")
  )
}

read_roads_for_chunk <- function(roads_path, grid_chunk, buffer_m = 50) {
  chunk_filter <- grid_chunk %>%
    st_union() %>%
    st_buffer(buffer_m) %>%
    st_as_text()

  read_sf_projected(roads_path, wkt_filter = chunk_filter) %>%
    normalize_road_schema()
}

process_grid_chunk <- function(
  grid_ids,
  grid_path,
  roads_path,
  out_path = NULL,
  grid_layer = derive_layer_name(grid_path),
  n_samples = 10L,
  seed_base = 100000L
) {
  grid_chunk <- read_grid_chunk(grid_path, grid_ids, layer = grid_layer)
  roads_chunk <- read_roads_for_chunk(roads_path, grid_chunk)

  result <- if (nrow(roads_chunk) == 0) {
    purrr::map_dfr(grid_chunk$grid_id, empty_grid_samples, n_samples = n_samples)
  } else {
    purrr::map_dfr(seq_len(nrow(grid_chunk)), function(i) {
      process_one_grid_probabilistic(
        cell = grid_chunk[i, ],
        roads = roads_chunk,
        n_samples = n_samples,
        seed_base = seed_base
      )
    })
  }

  result <- result %>% select(all_of(sample_output_columns))

  if (!is.null(out_path)) {
    ensure_dir(dirname(out_path))
    arrow::write_parquet(result, out_path)
  }

  result
}

make_grid_chunks <- function(grid_ids, chunk_size = 200L) {
  split(grid_ids, ceiling(seq_along(grid_ids) / chunk_size))
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

run_chunked_sampling <- function(
  grid_path,
  roads_path,
  output_dir = "data/sampling_1km/chunks",
  final_parquet = "data/sampling_1km/seoul_road_environment_samples_1km.parquet",
  grid_layer = derive_layer_name(grid_path),
  chunk_size = 200L,
  workers = 12L,
  n_samples = 10L,
  seed_base = 100000L
) {
  ensure_dir(output_dir)
  ensure_dir(dirname(final_parquet))

  grid_ids <- read_grid_ids(grid_path, layer = grid_layer)
  chunks <- make_grid_chunks(grid_ids, chunk_size = chunk_size)
  chunk_paths <- file.path(output_dir, sprintf("chunk_%04d.parquet", seq_along(chunks)))
  todo <- which(!vapply(chunk_paths, parquet_has_schema, logical(1)))

  if (length(todo) > 0) {
    old_plan <- future::plan()
    on.exit(future::plan(old_plan), add = TRUE)
    future::plan(future.mirai::mirai_multisession, workers = workers)

    futures <- purrr::map(todo, function(i) {
      future::future({
        process_grid_chunk(
          grid_ids = chunks[[i]],
          grid_path = grid_path,
          roads_path = roads_path,
          out_path = chunk_paths[[i]],
          grid_layer = grid_layer,
          n_samples = n_samples,
          seed_base = seed_base
        )
      }, seed = TRUE)
    })

    invisible(purrr::map(futures, future::value))
  }

  samples <- arrow::open_dataset(output_dir, format = "parquet") %>%
    collect() %>%
    arrange(grid_id, sample_id) %>%
    select(all_of(sample_output_columns))

  arrow::write_parquet(samples, final_parquet)
  samples
}

write_debug_outputs <- function(
  samples,
  roads,
  output_dir = "data/sampling_1km/debug",
  sample_points_gpkg = "sampled_points_1km.gpkg",
  roads_gpkg = "roads_filtered_1km_context.gpkg"
) {
  ensure_dir(output_dir)

  sampled_points <- samples %>%
    filter(!is.na(lon), !is.na(lat)) %>%
    st_as_sf(coords = c("lon", "lat"), crs = LONLAT_CRS, remove = FALSE) %>%
    st_transform(PROJECTED_CRS)

  st_write(sampled_points, file.path(output_dir, sample_points_gpkg), delete_dsn = TRUE, quiet = TRUE)
  st_write(roads, file.path(output_dir, roads_gpkg), delete_dsn = TRUE, quiet = TRUE)
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
  roads,
  samples,
  out_html = "data/sampling_1km/seoul_road_environment_sampling_1km_map.html",
  max_grid_cells = 1200,
  max_roads = 20000,
  max_points = 10000,
  road_simplify_tolerance_m = 10,
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

  roads_map <- roads %>%
    arrange(sampled_rank) %>%
    thin_sf_by_group("highway_class", max_features = max_roads) %>%
    simplify_for_leaflet(road_simplify_tolerance_m)

  points_map <- samples %>%
    filter(!is.na(lon), !is.na(lat)) %>%
    slice_head(n = max_points) %>%
    st_as_sf(coords = c("lon", "lat"), crs = LONLAT_CRS, remove = FALSE)

  message("Leaflet layer counts:")
  message("  boundary features: ", nrow(boundary_map))
  message("  grid features: ", nrow(grid_map), " / ", nrow(grid))
  message("  road features: ", nrow(roads_map), " / ", nrow(roads))
  message("  sampled points: ", nrow(points_map), " / ", sum(!is.na(samples$lon)))
  message("Leaflet layer object sizes:")
  message("  boundary: ", format(utils::object.size(boundary_map), units = "auto"))
  message("  grid: ", format(utils::object.size(grid_map), units = "auto"))
  message("  roads: ", format(utils::object.size(roads_map), units = "auto"))
  message("  points: ", format(utils::object.size(points_map), units = "auto"))

  road_palette <- leaflet::colorNumeric(
    palette = c("#67000d", "#cb181d", "#fb6a4a", "#fcae91", "#fee5d9"),
    domain = c(1, 9),
    reverse = FALSE
  )

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
      weight = 0.7,
      fill = FALSE,
      opacity = 0.55,
      group = "1km grid"
    ) %>%
    leaflet::addPolylines(
      data = roads_map,
      color = ~road_palette(sampled_rank),
      weight = ~pmax(0.7, 3.2 - sampled_rank * 0.25),
      opacity = 0.8,
      group = "Roads"
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
        "grid_id: ", grid_id,
        "<br>sample_id: ", sample_id,
        "<br>class: ", highway_class,
        "<br>p: ", round(class_proportion, 3)
      ),
      group = "Sampled points"
    ) %>%
    leaflet::addLegend(
      "bottomright",
      pal = road_palette,
      values = c(1, 9),
      title = "Highway rank",
      opacity = 0.9
    ) %>%
    leaflet::addLayersControl(
      overlayGroups = c("Seoul boundary", "1km grid", "Roads", "Sampled points"),
      options = leaflet::layersControlOptions(collapsed = FALSE)
    )

  htmlwidgets::saveWidget(map, out_html, selfcontained = FALSE)
  validate_leaflet_export(out_html)
  map
}

summarise_samples <- function(samples) {
  list(
    rows = nrow(samples),
    grids = dplyr::n_distinct(samples$grid_id),
    sampled_points = sum(!is.na(samples$lon)),
    missing_points = sum(is.na(samples$lon)),
    class_counts = samples %>% count(highway_class, sort = TRUE),
    per_grid_rows = samples %>% count(grid_id) %>% summarise(min_n = min(n), max_n = max(n))
  )
}
