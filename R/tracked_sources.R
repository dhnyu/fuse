.tracked_source_checksums <- new.env(parent = emptyenv())

tracked_source_sha256 <- function(path, expected = NULL) {
  normalized <- normalizePath(path, mustWork = TRUE)
  info <- file.info(normalized)
  key <- paste(normalized, unname(info$size), as.numeric(info$mtime), as.numeric(info$ctime), sep = "|")
  cached <- .tracked_source_checksums[[key]]
  if (!is.null(cached) && (is.null(expected) || identical(cached, expected))) return(cached)
  actual <- sha256_file(normalized)
  if (!is.null(expected) && !identical(actual, expected)) stop("Tracked source checksum mismatch: ", normalized, call. = FALSE)
  .tracked_source_checksums[[key]] <- actual
  actual
}

tracked_source_roles <- function(paths) {
  paths <- normalizePath(paths, mustWork = TRUE)
  roles <- basename(dirname(paths))
  direct <- c(
    seoul_boundary.gpkg = "boundary", seoul_buffer400.gpkg = "buffer400",
    seoul_B.gpkg = "building", seoul_R.gpkg = "road", seoul_P.gpkg = "poi",
    seoul_lc.tif = "landcover", seoul_dem.tif = "dem",
    seoul_data_manifest.json = "study_manifest"
  )
  matched <- direct[basename(paths)]
  roles[!is.na(matched)] <- unname(matched[!is.na(matched)])
  official <- roles == "official_grid"
  roles[official] <- paste0("official_grid_", tools::file_ext(paths[official]))
  setNames(paths, roles)
}

tracked_source_path <- function(inputs, role) {
  value <- tracked_source_roles(inputs)[[role]]
  if (is.null(value) || length(value) != 1L) stop("Tracked source role is missing: ", role, call. = FALSE)
  value
}

validated_source_record <- function(source, inputs, role) {
  value <- source
  value$path <- tracked_source_path(inputs, role)
  if (!identical(as.numeric(file.info(value$path)$size), as.numeric(source$size_bytes)) ||
      !identical(tracked_source_sha256(value$path, source$sha256), source$sha256)) {
    stop("Tracked source does not match scientific source: ", role, call. = FALSE)
  }
  value
}
