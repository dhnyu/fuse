# Read-only P9 post-training recovery orchestration. This script has no
# dependency on the formal training runner or a research targets store.

p9r_publish_recovery_authorization <- function() {
  failed_run <- "/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/attempts/p9attempt_a754afd14ac87287afb04029"
  output <- "/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/recovery_authorization"
  result <- system2(Sys.which("python"), c(
    "scripts/p9_checkpoint_recovery_authorization.py", "publish",
    "--failed-run", failed_run, "--output", output
  ), stdout = TRUE, stderr = TRUE)
  status <- attr(result, "status")
  if (!is.null(status) && status != 0L) stop(paste(result, collapse = "\n"), call. = FALSE)
  line <- result[startsWith(result, "P9_RECOVERY_OUTPUT=")]
  if (length(line) != 1L) stop("recovery authorization output mismatch", call. = FALSE)
  normalizePath(sub("^P9_RECOVERY_OUTPUT=", "", line), mustWork = TRUE)
}

p9r_artifact <- function(bundle, name) {
  value <- file.path(bundle, name)
  if (!file.exists(value)) stop("missing recovery artifact: ", name, call. = FALSE)
  normalizePath(value, mustWork = TRUE)
}
