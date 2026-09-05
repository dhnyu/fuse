# Supplement to P10 qualitative retrieval; this graph has no canonical outputs.
retrieval_stage <- function(action, parent = NULL, evidence = NULL) {
  args <- c("scripts/retrieval_gallery_pipeline.py", action)
  if (!is.null(parent)) args <- c(args, "--parent", shQuote(parent))
  if (!is.null(evidence)) args <- c(args, "--evidence", shQuote(evidence))
  output <- system2("python", args, stdout = TRUE, stderr = TRUE,
    env = c("PYTHONDONTWRITEBYTECODE=1", "OMP_NUM_THREADS=1", "OPENBLAS_NUM_THREADS=1", "MKL_NUM_THREADS=1"))
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop(paste(output, collapse = "\n"), call. = FALSE)
  path <- tail(output, 1L)
  if (length(path) != 1L || !file.exists(path)) stop("Supplemental stage did not return a verified manifest")
  path
}

retrieval_source_files <- function() {
  c("config/retrieval_gallery.yml", "config/p10_evaluation.yml", "config/schemas/retrieval_topology.schema.json",
    list.files("config/schemas/retrieval_gallery", full.names = TRUE),
    "R/retrieval_gallery.R", "R/retrieval_gallery_targets.R", "R/research_base_spatial.R",
    "R/research_membership.R", "R/research_observation.R", "R/research_relation.R", "R/research_raster_observation.R",
    "scripts/retrieval_gallery.R", "scripts/retrieval_gallery_pipeline.py", "scripts/p3_deterministic_tar.py",
    list.files("python", pattern = "^retrieval_gallery.*[.]py$", full.names = TRUE),
    file.path("tools/retrieval_inspector", c("inspector.py", "app.js", "index.html", "style.css")))
}
