# S11 dissertation 5.4; FM-only immutable consumers, no producer dependencies.
s11_representation_source_paths <- function() {
  c("config/s11_representation_analysis.json", "config/s11_representation_analysis.lock.json",
    "config/schemas/s11_representation_analysis.schema.json", "config/s11_execution.json",
    "python/representation_analysis.py", "python/s11_inputs.py", "python/s11_artifacts.py",
    "python/s11_descriptors.py", "python/s11_alignment.py", "python/s11_umap.py",
    "python/s11_production.py", "scripts/s11_production.py", "scripts/pilot_s11_production.py",
    "R/scene_descriptors.R", "R/s11_p3_reader.R", "scripts/s11_descriptor_worker.R",
    "R/s11_representation.R", "targets/s11_representation.R", "_targets_representation.R",
    "scripts/run_s11_representation.R")
}

s11_manifest <- function(files) {
  result <- files[basename(files) == "manifest.json"]
  stopifnot(length(result) == 1L)
  result
}

s11_stage <- function(stage, request = list()) {
  temporary <- tempfile(fileext = ".json")
  on.exit(unlink(temporary), add = TRUE)
  jsonlite::write_json(request, temporary, auto_unbox = TRUE, null = "null", digits = NA)
  # The Python entrypoint pins all thread environments before importing NumPy.
  output <- system2(Sys.getenv("FUSE_PYTHON", "python"),
    c("scripts/s11_production.py", stage, "--request", shQuote(temporary)), stdout = TRUE)
  if (!is.null(attr(output, "status")) && attr(output, "status") != 0L) stop("S11 stage failed: ", stage)
  result <- jsonlite::fromJSON(tail(output, 1L))$manifest
  body <- jsonlite::read_json(result)
  paths <- c(result, file.path(dirname(result), names(body$files)))
  stopifnot(identical(body$status, "PASS"), all(file.exists(paths)))
  for (name in names(body$files)) {
    stopifnot(identical(digest::digest(file = file.path(dirname(result), name), algo = "sha256", serialize = FALSE), body$files[[name]]))
  }
  paths
}

s11_specs <- function(plan_files, key) {
  plan <- jsonlite::read_json(file.path(dirname(s11_manifest(plan_files)), "plan.json"))
  plan[[key]]
}

s11_branch_manifests <- function(files) {
  files <- unlist(files, use.names = FALSE)
  unique(files[basename(files) == "manifest.json"])
}
