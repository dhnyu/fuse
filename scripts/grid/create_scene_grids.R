#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
})

sf::sf_use_s2(FALSE)
Sys.setenv(TZ = "Asia/Seoul")

timestamp <- format(Sys.time(), "%Y%m%d_%H%M")

defaults <- list(
  boundary_path = path.expand("~/fusedatalarge/geodata/koreanadm/bnd_sigungu_00_2024_2Q.shp"),
  boundary_layer = "",
  boundary_filter_column = "SIGUNGU_CD",
  boundary_filter_value = "11210",
  output_dir = path.expand("~/fusedatalarge/working_data/gwanak"),
  region = "gwanak",
  target_crs = "5186",
  cell_size_m = "500",
  strides_m = "500,250",
  report_path = file.path(
    path.expand("~/fuse/reports"),
    sprintf("%s_gwanak_scene_grid_generation.md", timestamp)
  )
)

usage <- function() {
  cat(
    "Create fixed-size scene grids for a region boundary.\n\n",
    "Arguments use --key=value format:\n",
    "  --boundary-path=PATH              Boundary vector file path.\n",
    "  --boundary-layer=LAYER            Optional layer name for multi-layer files.\n",
    "  --boundary-filter-column=COLUMN   Optional attribute column used to select a region.\n",
    "  --boundary-filter-value=VALUE     Optional attribute value used to select a region.\n",
    "  --output-dir=DIR                  Output directory for GPKG files.\n",
    "  --region=NAME                     Region key used in attributes and file names.\n",
    "  --target-crs=EPSG                 Target projected CRS. Default: 5186.\n",
    "  --cell-size-m=METERS              Square scene cell size. Default: 500.\n",
    "  --strides-m=LIST                  Comma-separated stride values. Default: 500,250.\n",
    "  --report-path=PATH                Markdown generation report path.\n\n",
    "Default parameters generate the Gwanak-gu 500 m non-overlap grid and\n",
    "250 m stride overlapping grid from the Korean sigungu boundary layer.\n",
    sep = ""
  )
}

parse_args <- function(args, defaults) {
  out <- defaults
  if (any(args %in% c("--help", "-h"))) {
    usage()
    quit(save = "no", status = 0)
  }
  for (arg in args) {
    if (!startsWith(arg, "--") || !grepl("=", arg, fixed = TRUE)) {
      stop(sprintf("Invalid argument: %s. Use --key=value.", arg), call. = FALSE)
    }
    key <- sub("^--", "", sub("=.*$", "", arg))
    key <- gsub("-", "_", key, fixed = TRUE)
    value <- sub("^[^=]*=", "", arg)
    if (!key %in% names(out)) {
      stop(sprintf("Unknown argument: %s", arg), call. = FALSE)
    }
    out[[key]] <- value
  }
  out
}

args <- parse_args(commandArgs(trailingOnly = TRUE), defaults)

target_crs <- as.integer(args$target_crs)
cell_size_m <- as.numeric(args$cell_size_m)
strides_m <- as.numeric(strsplit(args$strides_m, ",", fixed = TRUE)[[1]])
strides_m <- strides_m[!is.na(strides_m)]

if (!file.exists(args$boundary_path)) {
  stop(sprintf("Boundary path does not exist: %s", args$boundary_path), call. = FALSE)
}
if (is.na(target_crs) || target_crs <= 0) stop("target-crs must be a positive EPSG code.", call. = FALSE)
if (is.na(cell_size_m) || cell_size_m <= 0) stop("cell-size-m must be positive.", call. = FALSE)
if (!length(strides_m) || any(strides_m <= 0)) stop("strides-m must contain positive values.", call. = FALSE)

dir.create(args$output_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(dirname(args$report_path), recursive = TRUE, showWarnings = FALSE)

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), sprintf(...)))
  flush.console()
}

read_boundary <- function(path, layer, filter_column, filter_value, target_crs) {
  read_args <- list(dsn = path, quiet = TRUE, options = "ENCODING=UTF-8")
  if (nzchar(layer)) read_args$layer <- layer
  boundary <- do.call(sf::st_read, read_args)

  if (!nzchar(sf::st_crs(boundary)$wkt)) {
    stop("Boundary input has no CRS. Provide a boundary with a defined CRS.", call. = FALSE)
  }

  if (nzchar(filter_column) || nzchar(filter_value)) {
    if (!nzchar(filter_column) || !nzchar(filter_value)) {
      stop("Both boundary-filter-column and boundary-filter-value are required when filtering.", call. = FALSE)
    }
    if (!filter_column %in% names(boundary)) {
      stop(sprintf("Filter column not found in boundary input: %s", filter_column), call. = FALSE)
    }
    keep <- as.character(boundary[[filter_column]]) == filter_value
    boundary <- boundary[keep, , drop = FALSE]
  }

  if (!nrow(boundary)) {
    stop("Boundary selection produced zero features.", call. = FALSE)
  }

  boundary <- sf::st_transform(boundary, target_crs)
  boundary <- sf::st_make_valid(boundary)
  boundary_union <- sf::st_union(sf::st_geometry(boundary))
  boundary_union <- sf::st_make_valid(boundary_union)
  sf::st_sf(geometry = boundary_union)
}

make_square_grid <- function(boundary, cell_size_m, stride_m, crs) {
  bbox <- sf::st_bbox(boundary)
  x_start <- floor(as.numeric(bbox["xmin"]) / stride_m) * stride_m
  x_end <- ceiling(as.numeric(bbox["xmax"]) / stride_m) * stride_m
  y_start <- floor(as.numeric(bbox["ymin"]) / stride_m) * stride_m
  y_end <- ceiling(as.numeric(bbox["ymax"]) / stride_m) * stride_m

  xs <- seq(x_start, x_end, by = stride_m)
  ys <- seq(y_start, y_end, by = stride_m)
  anchors <- expand.grid(xmin = xs, ymin = ys)
  anchors <- anchors[order(anchors$ymin, anchors$xmin), , drop = FALSE]

  polygons <- lapply(seq_len(nrow(anchors)), function(i) {
    x <- anchors$xmin[i]
    y <- anchors$ymin[i]
    sf::st_polygon(list(matrix(
      c(
        x, y,
        x + cell_size_m, y,
        x + cell_size_m, y + cell_size_m,
        x, y + cell_size_m,
        x, y
      ),
      ncol = 2,
      byrow = TRUE
    )))
  })

  sf::st_sf(
    anchor_x = anchors$xmin,
    anchor_y = anchors$ymin,
    geometry = sf::st_sfc(polygons, crs = crs)
  )
}

grid_type_for_stride <- function(cell_size_m, stride_m) {
  if (isTRUE(all.equal(cell_size_m, stride_m))) return("nonoverlap")
  sprintf("overlap_stride%sm", format(stride_m, trim = TRUE, scientific = FALSE))
}

output_path_for_grid <- function(output_dir, region, cell_size_m, grid_type) {
  size_label <- sprintf("%sm", format(cell_size_m, trim = TRUE, scientific = FALSE))
  file.path(output_dir, sprintf("%s_scene_grid_%s_%s.gpkg", region, size_label, grid_type))
}

coverage_summary <- function(x) {
  values <- x$coverage_ratio
  stats <- stats::quantile(values, probs = c(0, 0.25, 0.5, 0.75, 1), na.rm = TRUE, names = FALSE)
  c(
    min = stats[1],
    q1 = stats[2],
    median = stats[3],
    mean = mean(values, na.rm = TRUE),
    q3 = stats[4],
    max = stats[5]
  )
}

build_scene_grid <- function(boundary, region, grid_type, cell_size_m, stride_m, target_crs) {
  boundary_geom <- sf::st_geometry(boundary)
  candidates <- make_square_grid(boundary, cell_size_m, stride_m, target_crs)

  intersects <- lengths(sf::st_intersects(candidates, boundary_geom)) > 0
  grid <- candidates[intersects, , drop = FALSE]
  if (!nrow(grid)) stop(sprintf("No grid cells intersect boundary for stride %s.", stride_m), call. = FALSE)

  within <- lengths(sf::st_within(grid, boundary_geom)) > 0
  intersections <- suppressWarnings(sf::st_intersection(grid, boundary_geom))
  intersection_area <- as.numeric(sf::st_area(intersections))
  full_area <- as.numeric(sf::st_area(grid))
  centroids <- sf::st_coordinates(sf::st_centroid(sf::st_geometry(grid)))

  id_prefix <- sprintf("%s_%s_%sm", region, grid_type, format(cell_size_m, trim = TRUE, scientific = FALSE))
  grid$scene_id <- sprintf("%s_%06d", id_prefix, seq_len(nrow(grid)))
  grid$region <- region
  grid$grid_type <- grid_type
  grid$cell_size_m <- cell_size_m
  grid$stride_m <- stride_m
  grid$area_m2 <- full_area
  grid$centroid_x <- centroids[, "X"]
  grid$centroid_y <- centroids[, "Y"]
  grid$intersects_boundary <- TRUE
  grid$within_boundary <- within
  grid$coverage_ratio <- pmax(0, pmin(1, intersection_area / full_area))

  required_columns <- c(
    "scene_id", "region", "grid_type", "cell_size_m", "stride_m", "area_m2",
    "centroid_x", "centroid_y", "intersects_boundary", "within_boundary",
    "coverage_ratio"
  )
  grid[, c(required_columns, attr(grid, "sf_column")), drop = FALSE]
}

validate_written_grid <- function(path, expected_crs, required_columns) {
  checks <- character()
  if (!file.exists(path)) stop(sprintf("Expected output was not written: %s", path), call. = FALSE)
  checks <- c(checks, sprintf("file exists: %s", path))

  x <- sf::st_read(path, quiet = TRUE)
  if (!nrow(x)) stop(sprintf("Output contains zero rows: %s", path), call. = FALSE)
  checks <- c(checks, sprintf("row count > 0: %s", format(nrow(x), big.mark = ",")))

  missing_columns <- setdiff(required_columns, names(x))
  if (length(missing_columns)) {
    stop(sprintf("Output is missing required columns: %s", paste(missing_columns, collapse = ", ")), call. = FALSE)
  }
  checks <- c(checks, "required columns present")

  if (!identical(sf::st_crs(x)$epsg, expected_crs)) {
    stop(sprintf("Output CRS mismatch in %s: expected EPSG:%s, got EPSG:%s", path, expected_crs, sf::st_crs(x)$epsg), call. = FALSE)
  }
  checks <- c(checks, sprintf("CRS is EPSG:%s", expected_crs))

  if (any(!is.finite(x$coverage_ratio)) || any(x$coverage_ratio <= 0) || any(x$coverage_ratio > 1.000001)) {
    stop(sprintf("Invalid coverage_ratio values in %s", path), call. = FALSE)
  }
  checks <- c(checks, "coverage_ratio values are finite and within (0, 1]")

  if (!all(x$intersects_boundary)) {
    stop(sprintf("Not all output cells intersect the boundary in %s", path), call. = FALSE)
  }
  checks <- c(checks, "all cells intersect boundary")

  checks
}

write_grid <- function(grid, path) {
  if (file.exists(path)) unlink(path)
  layer_name <- tools::file_path_sans_ext(basename(path))
  sf::st_write(grid, path, layer = layer_name, quiet = TRUE)
}

format_bbox <- function(bbox) {
  sprintf(
    "xmin=%.3f, ymin=%.3f, xmax=%.3f, ymax=%.3f",
    as.numeric(bbox["xmin"]), as.numeric(bbox["ymin"]),
    as.numeric(bbox["xmax"]), as.numeric(bbox["ymax"])
  )
}

format_coverage <- function(stats) {
  sprintf(
    "min=%.4f, q1=%.4f, median=%.4f, mean=%.4f, q3=%.4f, max=%.4f",
    stats["min"], stats["q1"], stats["median"], stats["mean"], stats["q3"], stats["max"]
  )
}

required_columns <- c(
  "scene_id", "region", "grid_type", "cell_size_m", "stride_m", "area_m2",
  "centroid_x", "centroid_y", "intersects_boundary", "within_boundary",
  "coverage_ratio"
)

log_msg("Reading boundary: %s", args$boundary_path)
boundary <- read_boundary(
  path = args$boundary_path,
  layer = args$boundary_layer,
  filter_column = args$boundary_filter_column,
  filter_value = args$boundary_filter_value,
  target_crs = target_crs
)
boundary_bbox <- sf::st_bbox(boundary)

outputs <- list()
for (stride_m in strides_m) {
  grid_type <- grid_type_for_stride(cell_size_m, stride_m)
  output_path <- output_path_for_grid(args$output_dir, args$region, cell_size_m, grid_type)
  log_msg("Building %s grid: cell size %.0f m, stride %.0f m", grid_type, cell_size_m, stride_m)
  grid <- build_scene_grid(
    boundary = boundary,
    region = args$region,
    grid_type = grid_type,
    cell_size_m = cell_size_m,
    stride_m = stride_m,
    target_crs = target_crs
  )
  write_grid(grid, output_path)
  validation_checks <- validate_written_grid(output_path, target_crs, required_columns)
  outputs[[grid_type]] <- list(
    path = output_path,
    n_cells = nrow(grid),
    coverage = coverage_summary(grid),
    validation_checks = validation_checks
  )
  log_msg("Wrote %s cells to %s", format(nrow(grid), big.mark = ","), output_path)
}

report_lines <- c(
  sprintf("# %s Scene Grid Generation", tools::toTitleCase(args$region)),
  "",
  sprintf("Date: %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
  "",
  "## Inputs",
  "",
  sprintf("- Boundary path: `%s`", args$boundary_path),
  sprintf("- Boundary layer: `%s`", if (nzchar(args$boundary_layer)) args$boundary_layer else "(default layer)"),
  sprintf("- Boundary filter column: `%s`", if (nzchar(args$boundary_filter_column)) args$boundary_filter_column else "(none)"),
  sprintf("- Boundary filter value: `%s`", if (nzchar(args$boundary_filter_value)) args$boundary_filter_value else "(none)"),
  sprintf("- Region: `%s`", args$region),
  sprintf("- CRS: EPSG:%s", target_crs),
  sprintf("- Boundary bbox after CRS transform: %s", format_bbox(boundary_bbox)),
  sprintf("- Cell size: %.0f m x %.0f m", cell_size_m, cell_size_m),
  sprintf("- Strides: %s m", paste(format(strides_m, trim = TRUE, scientific = FALSE), collapse = ", ")),
  "",
  "## Outputs",
  ""
)

for (grid_type in names(outputs)) {
  item <- outputs[[grid_type]]
  report_lines <- c(
    report_lines,
    sprintf("### %s", grid_type),
    "",
    sprintf("- Output path: `%s`", item$path),
    sprintf("- Number of cells: %s", format(item$n_cells, big.mark = ",")),
    sprintf("- coverage_ratio summary: %s", format_coverage(item$coverage)),
    "",
    "Validation checks:",
    "",
    paste0("- ", item$validation_checks),
    ""
  )
}

report_lines <- c(
  report_lines,
  "## Notes",
  "",
  "- Grid cells are full 500 m squares and are not clipped to the boundary.",
  "- Cells are retained when they intersect the boundary.",
  "- `coverage_ratio` is the boundary intersection area divided by full cell area.",
  "- Overlapping scene grids should not be used for leakage-prone evaluation splits."
)

writeLines(report_lines, args$report_path)

cat(paste(report_lines, collapse = "\n"))
cat("\n")
log_msg("Report written to %s", args$report_path)
