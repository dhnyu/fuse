quote_command <- function(command, args = character()) {
  paste(c(shQuote(command), vapply(args, shQuote, character(1L))), collapse = " ")
}

run_command <- function(command, args = character(), env = character(), capture = FALSE) {
  cat(sprintf("[%s] RUN %s\n", kst_now(), quote_command(command, args)))
  started <- Sys.time()
  safe_args <- vapply(args, shQuote, character(1L))
  output <- if (capture) {
    system2(command, args = safe_args, env = env, stdout = TRUE, stderr = TRUE)
  } else {
    system2(command, args = safe_args, env = env, stdout = "", stderr = "")
  }
  status <- if (capture) attr(output, "status") %||% 0L else output
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  cat(sprintf("[%s] EXIT status=%d elapsed_sec=%.3f command=%s\n", kst_now(), status, elapsed, command))
  if (!identical(as.integer(status), 0L)) {
    detail <- if (capture) paste(output, collapse = "\n") else ""
    stop("Command failed: ", quote_command(command, args), "\n", detail, call. = FALSE)
  }
  if (capture) output else invisible(list(status = 0L, elapsed_sec = elapsed))
}

sha256_file <- function(path) {
  output <- run_command("sha256sum", path, capture = TRUE)
  strsplit(output[[1L]], "[[:space:]]+")[[1L]][[1L]]
}

sha256_file_set <- function(paths) {
  normalized <- normalizePath(paths, mustWork = TRUE)
  entries <- paste(basename(normalized), vapply(normalized, sha256_file, character(1L)), sep = "|")
  digest::digest(paste(entries, collapse = "\n"), algo = "sha256", serialize = FALSE)
}

write_json_atomic <- function(value, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  temp <- paste0(path, ".tmp.", Sys.getpid())
  on.exit(if (file.exists(temp)) unlink(temp), add = TRUE)
  jsonlite::write_json(value, temp, auto_unbox = TRUE, pretty = TRUE, null = "null", digits = NA)
  if (!file.rename(temp, path)) stop("Atomic JSON publish failed: ", path, call. = FALSE)
  path
}

stage_path <- function(final) {
  dir.create(dirname(final), recursive = TRUE, showWarnings = FALSE)
  extension <- tools::file_ext(final)
  stem <- tools::file_path_sans_ext(basename(final))
  suffix <- if (nzchar(extension)) paste0(".", extension) else ""
  file.path(
    dirname(final),
    sprintf(".%s.tmp.%s.%s%s", stem, Sys.getpid(), format(Sys.time(), "%Y%m%d%H%M%S"), suffix)
  )
}

atomic_publish <- function(stage, final) {
  if (!file.exists(stage)) stop("Staged artifact does not exist: ", stage, call. = FALSE)
  if (file.exists(final)) stop("Refusing to overwrite existing artifact: ", final, call. = FALSE)
  sidecars <- paste0(stage, c("-wal", "-shm"))
  if (any(file.exists(sidecars))) stop("SQLite sidecar remains beside staging artifact", call. = FALSE)
  if (!file.rename(stage, final)) stop("Atomic rename failed: ", stage, " -> ", final, call. = FALSE)
  final
}

sqlite_integrity <- function(path) {
  code <- paste0(
    "import sqlite3,sys;",
    "c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);",
    "r=c.execute('PRAGMA integrity_check').fetchone()[0];print(r);c.close();",
    "sys.exit(0 if r=='ok' else 2)"
  )
  identical(tail(run_command("python", c("-c", code, path), capture = TRUE), 1L), "ok")
}

ogr_scalar <- function(dataset, sql, field = "value", read_only = TRUE) {
  args <- c(if (read_only) "-ro", "-q", dataset, "-dialect", "SQLite", "-sql", sql)
  output <- run_command("ogrinfo", args, capture = TRUE)
  line <- grep(sprintf("^[[:space:]]+%s ", field), output, value = TRUE)
  if (length(line) != 1L) {
    line <- grep("^[[:space:]]+[^=]+ = ", output, value = TRUE)
  }
  if (length(line) != 1L) stop("Cannot parse OGR scalar: ", paste(output, collapse = " | "), call. = FALSE)
  sub("^.* = ", "", line[[1L]])
}

ogr_execute <- function(dataset, sql) {
  run_command("ogrinfo", c(dataset, "-dialect", "SQLite", "-sql", sql))
}

ensure_spatial_index <- function(gpkg, layer, geometry = "geom") {
  has <- ogr_scalar(gpkg, sprintf("SELECT HasSpatialIndex('%s','%s') AS value", layer, geometry))
  if (identical(has, "0")) {
    ogr_execute(gpkg, sprintf("SELECT CreateSpatialIndex('%s','%s')", layer, geometry))
  }
  if (!identical(ogr_scalar(gpkg, sprintf("SELECT HasSpatialIndex('%s','%s') AS value", layer, geometry)), "1")) {
    stop("Spatial index creation failed for ", layer, call. = FALSE)
  }
  invisible(TRUE)
}

write_gpkg_metadata <- function(gpkg, values, append = FALSE) {
  csv <- tempfile(pattern = "metadata_", fileext = ".csv", tmpdir = dirname(gpkg))
  on.exit(unlink(csv), add = TRUE)
  metadata <- data.table::as.data.table(list(
    key = names(values),
    value = vapply(values, as.character, character(1L))
  ))
  data.table::fwrite(metadata, csv, bom = TRUE)
  args <- if (append) c("-update", "-append") else c("-update")
  run_command("ogr2ogr", c(args, gpkg, csv, "-nln", "metadata", "-lco", "ASPATIAL_VARIANT=GPKG_ATTRIBUTES"))
  invisible(gpkg)
}

gpkg_layers <- function(path) {
  output <- run_command("ogrinfo", c("-ro", "-so", path), capture = TRUE)
  sub("^[0-9]+: ([^ ]+).*$", "\\1", grep("^[0-9]+:", output, value = TRUE))
}

gdal_json <- function(path, checksum = FALSE) {
  args <- c("-json", if (checksum) "-checksum", path)
  jsonlite::fromJSON(paste(run_command("gdalinfo", args, capture = TRUE), collapse = "\n"), simplifyVector = FALSE)
}

gdal_default_metadata <- function(object) {
  metadata <- object$metadata %||% list()
  index <- which(names(metadata) == "")
  if (length(index)) metadata[[index[[1L]]]] else list()
}

software_versions <- function() {
  proj_output <- run_command("proj", capture = TRUE)
  proj_version <- grep("^Rel\\.", proj_output, value = TRUE)
  if (length(proj_version) != 1L) stop("Could not determine PROJ version", call. = FALSE)
  list(
    R = R.version.string,
    packages = as.list(vapply(c("targets", "crew", "future", "future.apply", "sf", "data.table", "yaml", "jsonlite", "digest"), function(x) as.character(utils::packageVersion(x)), character(1L))),
    GDAL = run_command("gdalinfo", "--version", capture = TRUE)[[1L]],
    PROJ = proj_version[[1L]]
  )
}

bbox_from_gpkg <- function(path, layer) {
  x <- sf::st_read(path, layer = layer, quiet = TRUE)
  if (nrow(x) != 1L) stop("Expected one geometry in ", path, call. = FALSE)
  sf::st_bbox(x)
}

artifact_fingerprint <- function(...) {
  digest::digest(paste(..., sep = "|", collapse = "|"), algo = "sha256", serialize = FALSE)
}

existing_gpkg_matches <- function(path, fingerprint) {
  if (!file.exists(path)) return(FALSE)
  value <- tryCatch(ogr_scalar(path, "SELECT value FROM metadata WHERE key='artifact_fingerprint'", "value"), error = function(e) NA_character_)
  identical(value, fingerprint) && sqlite_integrity(path)
}

existing_raster_matches <- function(path, fingerprint) {
  if (!file.exists(path)) return(FALSE)
  info <- tryCatch(gdal_json(path), error = function(e) NULL)
  identical(gdal_default_metadata(info)$ARTIFACT_FINGERPRINT %||% NA_character_, fingerprint)
}

read_gpkg_metadata <- function(path) {
  code <- paste0(
    "import json,sqlite3,sys;",
    "c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);",
    "print(json.dumps(dict(c.execute('SELECT key,value FROM metadata').fetchall()),ensure_ascii=False));",
    "c.close()"
  )
  jsonlite::fromJSON(paste(run_command("python", c("-c", code, path), capture = TRUE), collapse = "\n"), simplifyVector = TRUE)
}

gpkg_count <- function(path, layer) {
  as.numeric(ogr_scalar(path, sprintf("SELECT COUNT(*) AS value FROM \"%s\"", layer)))
}

gpkg_fields <- function(path, layer) {
  info <- jsonlite::fromJSON(
    paste(run_command("ogrinfo", c("-ro", "-json", "-so", path, layer), capture = TRUE), collapse = "\n"),
    simplifyVector = FALSE
  )
  vapply(info$layers[[1L]]$fields, `[[`, character(1L), "name")
}
