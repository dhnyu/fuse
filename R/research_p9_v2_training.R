# P9 v2 production controller orchestration. Scientific state remains in the ledger.
p9v2_training_authority_path <- function() {
  path <- Sys.getenv("P9_V2_TRAINING_AUTHORITY", unset = "")
  if (!nzchar(path) || !file.exists(path)) {
    stop("P9_V2_TRAINING_AUTHORITY_REQUIRED: no formal execution is authorized", call. = FALSE)
  }
  normalizePath(path, mustWork = TRUE)
}

p9v2_controller_run <- function(authority, contract) {
  output <- Sys.getenv("P9_V2_TRAINING_OUTPUT", unset = "")
  worker <- Sys.getenv("P9_V2_SCIENCE_WORKER_COMMAND", unset = "")
  if (!nzchar(output) || !nzchar(worker)) {
    stop("P9_V2_EXPLICIT_OUTPUT_AND_SCIENCE_WORKER_REQUIRED", call. = FALSE)
  }
  status <- system2(
    Sys.which("python"),
    c("scripts/p9_v2_training_controller.py", "run", "--authority", authority,
      "--contract", contract, "--output", output, "--science-worker-command", worker),
    stdout = TRUE, stderr = TRUE
  )
  if (!identical(attr(status, "status"), NULL)) stop(paste(status, collapse = "\n"), call. = FALSE)
  result <- jsonlite::fromJSON(tail(status, 1), simplifyVector = FALSE)
  if (!identical(result$status, "COMPLETE")) stop("P9_V2_CONTROLLER_DID_NOT_COMPLETE", call. = FALSE)
  normalizePath(result$ledger_manifest, mustWork = TRUE)
}

p9v2_declared_artifact <- function(environment_name, dependency) {
  path <- Sys.getenv(environment_name, unset = "")
  if (!nzchar(path) || !file.exists(path)) {
    stop(paste0(environment_name, "_REQUIRED_AFTER_CONTROLLER"), call. = FALSE)
  }
  normalizePath(path, mustWork = TRUE)
}

p9v2_resolve_accepted_checkpoint <- function(eligibility_snapshot) {
  identity <- Sys.getenv("P9_V2_ACCEPTANCE_ID", unset = "")
  roots <- Sys.getenv("P9_V2_LOCATOR_ROOTS_JSON", unset = "")
  output <- Sys.getenv("P9_V2_RESOLUTION_RECORD", unset = "")
  if (!grepl("^p9accv2_[0-9a-f]{24}$", identity) || !file.exists(roots) || !nzchar(output)) {
    stop("P9_V2_CANONICAL_ACCEPTANCE_RESOLVER_INPUT_REQUIRED", call. = FALSE)
  }
  status <- system2(
    Sys.which("python"),
    c("scripts/p9_v2_resolve_checkpoint.py", "--acceptance-id", identity,
      "--eligibility", eligibility_snapshot, "--locator-roots", roots,
      "--output", output), stdout = TRUE, stderr = TRUE
  )
  if (!identical(attr(status, "status"), NULL)) stop(paste(status, collapse = "\n"), call. = FALSE)
  normalizePath(output, mustWork = TRUE)
}
