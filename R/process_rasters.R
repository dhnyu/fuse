# Thesis: object/background context and Chapter 4 experimental setup. Land cover
# retains the canonical lattice; DEM is a derived 30 m EPSG:5186 raster.

snap_extent_to_grid <- function(bbox, resolution, anchor_x = 0, anchor_y = 0) {
  c(
    xmin = anchor_x + floor((bbox[["xmin"]] - anchor_x) / resolution) * resolution,
    ymin = anchor_y + floor((bbox[["ymin"]] - anchor_y) / resolution) * resolution,
    xmax = anchor_x + ceiling((bbox[["xmax"]] - anchor_x) / resolution) * resolution,
    ymax = anchor_y + ceiling((bbox[["ymax"]] - anchor_y) / resolution) * resolution
  )
}

snap_extent_to_source_raster <- function(bbox, geotransform) {
  x0 <- geotransform[[1L]]
  xres <- geotransform[[2L]]
  y0 <- geotransform[[4L]]
  yres <- abs(geotransform[[6L]])
  c(
    xmin = x0 + floor((bbox[["xmin"]] - x0) / xres) * xres,
    ymin = y0 - ceiling((y0 - bbox[["ymin"]]) / yres) * yres,
    xmax = x0 + ceiling((bbox[["xmax"]] - x0) / xres) * xres,
    ymax = y0 - floor((y0 - bbox[["ymax"]]) / yres) * yres
  )
}

raster_extent <- function(info) {
  gt <- unlist(info$geoTransform)
  size <- unlist(info$size)
  c(
    xmin = gt[[1L]],
    ymin = gt[[4L]] + gt[[6L]] * size[[2L]],
    xmax = gt[[1L]] + gt[[2L]] * size[[1L]],
    ymax = gt[[4L]]
  )
}

extent_covers_bbox <- function(extent, bbox, tolerance = 1e-7) {
  extent[["xmin"]] <= bbox[["xmin"]] + tolerance &&
    extent[["ymin"]] <= bbox[["ymin"]] + tolerance &&
    extent[["xmax"]] >= bbox[["xmax"]] - tolerance &&
    extent[["ymax"]] >= bbox[["ymax"]] - tolerance
}

subset_seoul_landcover <- function(canonical_inputs, buffer_file, config, threads = 1L) {
  threads <- assert_positive_integer(threads, "threads")
  source <- canonical_inputs$landcover$path
  final <- config$paths$study$landcover
  buffer_hash <- sha256_file(buffer_file)
  source_info <- gdal_json(source)
  source_gt <- unlist(source_info$geoTransform)
  bbox <- bbox_from_gpkg(buffer_file, "research_area")
  extent <- snap_extent_to_source_raster(bbox, source_gt)
  fingerprint <- artifact_fingerprint(
    "seoul_landcover", canonical_inputs$landcover$sha256, buffer_hash,
    paste(format(extent, digits = 17), collapse = ","), "NO_RESAMPLING",
    config$methodology$contract$study_subset_version
  )
  if (existing_raster_matches(final, fingerprint)) return(final)
  if (file.exists(final)) stop("Conflicting existing Seoul land-cover subset: ", final, call. = FALSE)
  stage <- stage_path(final)
  on.exit(if (file.exists(stage)) unlink(stage), add = TRUE)
  run_command("gdal_translate", c(
    "-of", "COG", "-projwin",
    format(extent[["xmin"]], digits = 17), format(extent[["ymax"]], digits = 17),
    format(extent[["xmax"]], digits = 17), format(extent[["ymin"]], digits = 17),
    "-projwin_srs", "EPSG:5186", "-ot", "Byte", "-a_nodata", as.character(config$methodology$landcover$nodata),
    "-co", "COMPRESS=DEFLATE", "-co", "LEVEL=6", "-co", "BLOCKSIZE=512",
    "-co", paste0("NUM_THREADS=", threads),
    "-co", "BIGTIFF=IF_SAFER", "-co", "OVERVIEWS=IGNORE_EXISTING",
    "-co", "OVERVIEW_RESAMPLING=NEAREST", "-co", "STATISTICS=YES",
    "-mo", paste0("ARTIFACT_FINGERPRINT=", fingerprint),
    "-mo", paste0("CANONICAL_SHA256=", canonical_inputs$landcover$sha256),
    "-mo", paste0("BUFFER_SHA256=", buffer_hash),
    "-mo", "SPATIAL_OPERATION=SOURCE_ALIGNED_RECTANGULAR_CROP_NO_RESAMPLING",
    source, stage
  ))
  info <- gdal_json(stage)
  output_gt <- unlist(info$geoTransform)
  output_extent <- raster_extent(info)
  band <- info$bands[[1L]]
  band_metadata <- gdal_default_metadata(band)
  min_value <- as.numeric(band$minimum %||% band_metadata$STATISTICS_MINIMUM)
  max_value <- as.numeric(band$maximum %||% band_metadata$STATISTICS_MAXIMUM)
  source_x_phase <- (output_gt[[1L]] - source_gt[[1L]]) / source_gt[[2L]]
  source_y_phase <- (source_gt[[4L]] - output_gt[[4L]]) / abs(source_gt[[6L]])
  if (!identical(info$metadata$IMAGE_STRUCTURE$LAYOUT, "COG") ||
      !identical(band$type, "Byte") || as.numeric(band$noDataValue) != 0 ||
      abs(output_gt[[2L]] - 5) > 1e-9 || abs(output_gt[[6L]] + 5) > 1e-9 ||
      abs(source_x_phase - round(source_x_phase)) > 1e-8 ||
      abs(source_y_phase - round(source_y_phase)) > 1e-8 ||
      !extent_covers_bbox(output_extent, bbox) || min_value < 1 || max_value > 22) {
    stop("Land-cover lattice/value/coverage QC failed", call. = FALSE)
  }
  atomic_publish(stage, final)
}

subset_seoul_dem <- function(canonical_inputs, buffer_file, config, threads = 1L) {
  threads <- assert_positive_integer(threads, "threads")
  source <- canonical_inputs$dem$path
  final <- config$paths$study$dem
  buffer_hash <- sha256_file(buffer_file)
  bbox <- bbox_from_gpkg(buffer_file, "research_area")
  resolution <- as.numeric(config$methodology$dem$resolution_m)
  anchor_x <- as.numeric(config$methodology$dem$grid_anchor_x_m)
  anchor_y <- as.numeric(config$methodology$dem$grid_anchor_y_m)
  extent <- snap_extent_to_grid(bbox, resolution, anchor_x, anchor_y)
  fingerprint <- artifact_fingerprint(
    "seoul_dem", canonical_inputs$dem$sha256, buffer_hash,
    paste(extent, collapse = ","), resolution, anchor_x, anchor_y,
    config$methodology$dem$resampling,
    config$methodology$contract$study_subset_version
  )
  if (existing_raster_matches(final, fingerprint)) return(final)
  if (file.exists(final)) stop("Conflicting existing Seoul DEM subset: ", final, call. = FALSE)
  stage <- stage_path(final)
  intermediate <- paste0(stage, ".warp.tif")
  on.exit(unlink(c(stage, intermediate, paste0(stage, ".aux.xml"), paste0(intermediate, ".aux.xml"))), add = TRUE)
  run_command("gdalwarp", c(
    "-overwrite", "-s_srs", "EPSG:4326", "-t_srs", "EPSG:5186",
    "-te", format(extent[["xmin"]], digits = 17), format(extent[["ymin"]], digits = 17),
    format(extent[["xmax"]], digits = 17), format(extent[["ymax"]], digits = 17),
    "-tr", as.character(resolution), as.character(resolution), "-tap",
    "-r", "bilinear", "-srcnodata", as.character(config$methodology$dem$source_nodata),
    "-dstnodata", as.character(config$methodology$dem$output_nodata),
    "-ot", "Int16", "-of", "GTiff", "-wm", "512",
    "-wo", "UNIFIED_SRC_NODATA=YES", "-wo", paste0("NUM_THREADS=", threads),
    "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-co", paste0("NUM_THREADS=", threads),
    "-co", "PREDICTOR=2", "-co", "BIGTIFF=IF_SAFER", source, intermediate
  ))
  run_command("gdal_translate", c(
    "-of", "COG", "-ot", "Int16", "-a_nodata", as.character(config$methodology$dem$output_nodata),
    "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=STANDARD", "-co", "LEVEL=6",
    "-co", "BLOCKSIZE=512", "-co", "BIGTIFF=IF_SAFER", "-co", "OVERVIEWS=IGNORE_EXISTING",
    "-co", paste0("NUM_THREADS=", threads),
    "-co", "OVERVIEW_RESAMPLING=AVERAGE", "-co", "STATISTICS=YES",
    "-mo", paste0("ARTIFACT_FINGERPRINT=", fingerprint),
    "-mo", paste0("CANONICAL_SHA256=", canonical_inputs$dem$sha256),
    "-mo", paste0("BUFFER_SHA256=", buffer_hash),
    "-mo", "SOURCE_CRS=EPSG:4326", "-mo", "OUTPUT_CRS=EPSG:5186",
    "-mo", "WARP_RESAMPLING=BILINEAR", "-mo", "OVERVIEW_RESAMPLING=AVERAGE",
    "-mo", paste0("GRID_ANCHOR=", anchor_x, ",", anchor_y),
    "-mo", "VERTICAL_UNIT=m", "-mo", "VERTICAL_DATUM=E96",
    intermediate, stage
  ))
  unlink(intermediate)
  info <- gdal_json(stage)
  gt <- unlist(info$geoTransform)
  output_extent <- raster_extent(info)
  band <- info$bands[[1L]]
  band_metadata <- gdal_default_metadata(band)
  min_value <- as.numeric(band$minimum %||% band_metadata$STATISTICS_MINIMUM)
  valid_percent <- as.numeric(band_metadata$STATISTICS_VALID_PERCENT %||% 0)
  if (!identical(info$metadata$IMAGE_STRUCTURE$LAYOUT, "COG") ||
      !identical(band$type, "Int16") || as.numeric(band$noDataValue) != -32767 ||
      abs(gt[[2L]] - resolution) > 1e-9 || abs(gt[[6L]] + resolution) > 1e-9 ||
      abs((gt[[1L]] - anchor_x) / resolution - round((gt[[1L]] - anchor_x) / resolution)) > 1e-8 ||
      abs((gt[[4L]] - anchor_y) / resolution - round((gt[[4L]] - anchor_y) / resolution)) > 1e-8 ||
      !extent_covers_bbox(output_extent, bbox) || !is.finite(min_value) || valid_percent <= 0) {
    stop("Derived DEM grid/nodata/coverage QC failed", call. = FALSE)
  }
  atomic_publish(stage, final)
}
