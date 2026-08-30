build_p9_infrastructure_readiness <- function(config_file, schema_file, source_commit) {
  command <- c(
    "scripts/p9_infrastructure.py", "--config", config_file,
    "--schema", schema_file, "--source-commit", source_commit
  )
  output <- system2("python", command, stdout = TRUE, stderr = TRUE)
  status <- attr(output, "status")
  if (!is.null(status) && status != 0L) stop(paste(output, collapse = "\n"), call. = FALSE)
  line <- output[startsWith(output, "P9_OUTPUT=")]
  if (length(line) != 1L) stop("P9 readiness output was not reported", call. = FALSE)
  path <- sub("^P9_OUTPUT=", "", line)
  if (!file.exists(path)) stop("P9 readiness artifact is missing", call. = FALSE)
  path
}
