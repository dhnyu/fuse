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

p9r_readonly_join <- function(contract) {
  value <- jsonlite::read_json(contract, simplifyVector = FALSE)
  if (length(value$checkpoint_candidates) != 25L) stop("recovery requires exactly 25 checkpoint candidates", call. = FALSE)
  value$checkpoint_candidates
}

p9r_selected_checkpoint <- function(join) {
  best <- NULL
  for (candidate in join) {
    if (is.null(best)) { best <- candidate; next }
    delta <- as.numeric(candidate$validation_retrieval_loss) - as.numeric(best$validation_retrieval_loss)
    improved <- if (abs(delta) >= 1e-4) delta < 0 else if (as.numeric(candidate$mean_source_separation_margin) != as.numeric(best$mean_source_separation_margin)) as.numeric(candidate$mean_source_separation_margin) > as.numeric(best$mean_source_separation_margin) else as.integer(candidate$epoch) < as.integer(best$epoch)
    if (improved) best <- candidate
  }
  if (!identical(best$checkpoint_id, "p9ck_42f7957d2ea998ac9e8ff705")) stop("recovery selector result mismatch", call. = FALSE)
  best
}

p9r_early_stopping <- function(contract, selected) {
  value <- jsonlite::read_json(contract, simplifyVector = FALSE)$stopping
  if (!identical(as.integer(value$stopping_epoch), 125L) || !identical(as.integer(selected$epoch), 105L)) {
    stop("recovery stopping-boundary contract mismatch", call. = FALSE)
  }
  value
}

p9r_execute_terminal <- function(bundle, selected, stopping) {
  invisible(list(selected, stopping))
  reservation <- p9r_artifact(bundle, "recovery_reservation.json")
  token <- Sys.getenv("FUSE_P9_RECOVERY_RESERVATION_ID", unset = "")
  if (!identical(token, jsonlite::read_json(reservation)$recovery_reservation_id)) stop("exact recovery token required", call. = FALSE)
  output <- "/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/recovery_operations"
  result <- system2(Sys.which("python"), c("scripts/p9_checkpoint_recovery_authorization.py", "execute", "--failed-run", "/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/attempts/p9attempt_a754afd14ac87287afb04029", "--authorization-dir", bundle, "--output", output), stdout = TRUE, stderr = TRUE)
  if (!is.null(attr(result, "status")) && attr(result, "status") != 0L) stop(paste(result, collapse = "\n"), call. = FALSE)
  normalizePath(sub("^P9_RECOVERY_TERMINAL_OUTPUT=", "", result[startsWith(result, "P9_RECOVERY_TERMINAL_OUTPUT=")]), mustWork = TRUE)
}
