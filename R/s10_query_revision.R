# Dissertation sec:spatial-scene-retrieval; authorized qualitative 100-query policy.
s10_revision_run <- function(stage, config, input = NULL) {
  args <- c("scripts/s10_query_revision.py", stage, "--config", config)
  if (!is.null(input)) args <- c(args, "--input", input)
  value <- system2("python", vapply(args, shQuote, character(1)), stdout = TRUE,
    env = c("OMP_NUM_THREADS=1", "OPENBLAS_NUM_THREADS=1", "MKL_NUM_THREADS=1"))
  if (!is.null(attr(value, "status")) && attr(value, "status") != 0L) stop("S10 revision worker failed")
  paths <- unlist(jsonlite::fromJSON(tail(value, 1L)), use.names = FALSE)
  if (!length(paths) || any(!file.exists(paths))) stop("S10 revision outputs missing")
  paths
}
s10_revision_file <- function(paths, name) {
  value <- paths[basename(paths) == name]
  if (length(value) != 1L) stop("Ambiguous revision artifact: ", name)
  value
}
