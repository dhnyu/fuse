# Chapter 5.5: immutable S11 geographic observations and S10 model embeddings.
s12_source_paths <- function() {
  # Read the Python literal source registry without importing/executing targets.
  text <- readLines("python/s12_runtime.py", warn = FALSE)
  text <- paste(text[seq(which(grepl("^SOURCES =", text)), which(grepl("^@lru_cache", text))-1L)], collapse = " ")
  paths <- regmatches(text, gregexpr("'[^']+'", text))[[1L]]
  paths <- substring(paths, 2L, nchar(paths)-1L)
  lock <- jsonlite::read_json("config/s12_representation_alignment.lock.json")
  unique(c(paths, names(lock$kernel_sources)))
}
s12_manifest <- function(files) {
  p <- files[basename(files) == "manifest.json"]
  stopifnot(length(p) == 1L); p
}
s12_manifests <- function(files) {
  p <- unlist(files, use.names = FALSE)
  unique(p[basename(p) == "manifest.json"])
}
s12_write_request <- function(request, path) {
  # jsonlite serializes list() as []; Python stage requests must be objects.
  if (!length(request)) writeLines("{}", path)
  else jsonlite::write_json(request, path, auto_unbox = TRUE, null = "null", digits = NA)
}
s12_stage <- function(stage, request = list()) {
  temporary <- tempfile(fileext = ".json")
  on.exit(unlink(temporary), add = TRUE)
  s12_write_request(request, temporary)
  output <- system2(Sys.getenv("FUSE_PYTHON", "python"), c("scripts/s12_representation.py", stage, "--request", shQuote(temporary)), stdout = TRUE)
  if (!is.null(attr(output, "status")) && attr(output, "status") != 0L) stop("S12 stage failed: ", stage)
  manifest <- jsonlite::fromJSON(tail(output, 1L))$manifest
  body <- jsonlite::read_json(manifest)
  paths <- c(manifest, file.path(dirname(manifest), names(body$files)))
  stopifnot(identical(body$status, "PASS"), all(file.exists(paths)))
  for (p in names(body$files)) stopifnot(identical(digest::digest(file = file.path(dirname(manifest), p), algo = "sha256", serialize = FALSE), body$files[[p]]))
  paths
}
s12_specs <- function(plan, key) {
  jsonlite::read_json(file.path(dirname(s12_manifest(plan)), "plan.json"))[[key]]
}
