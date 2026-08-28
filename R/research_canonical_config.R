canonical_yaml_sha256 <- function(path, excluded_top_level = character()) {
  script <- paste0(
    "from canonical_config import canonical_yaml_sha256; ",
    "import sys; print(canonical_yaml_sha256(sys.argv[1], tuple(sys.argv[2:])))"
  )
  python_path <- normalizePath("python", mustWork = TRUE)
  old_pythonpath <- Sys.getenv("PYTHONPATH", unset = "")
  on.exit(Sys.setenv(PYTHONPATH = old_pythonpath), add = TRUE)
  Sys.setenv(PYTHONPATH = paste(Filter(nzchar, c(python_path, old_pythonpath)), collapse = .Platform$path.sep))
  output <- system2(research_python_executable(), c("-c", shQuote(script), shQuote(normalizePath(path, mustWork = TRUE)),
                                                    vapply(excluded_top_level, shQuote, character(1L))),
                    stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status") %||% 0L
  if (status != 0L || length(output) != 1L || !grepl("^[0-9a-f]{64}$", output[[1L]])) {
    stop("Canonical YAML validation failed: ", paste(output, collapse = " | "), call. = FALSE)
  }
  output[[1L]]
}
