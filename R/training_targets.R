# Current production-training controller orchestration. Scientific state remains in the ledger.
s09_training_contract_path <- function() {
  path <- Sys.getenv(
    "FUSE_TRAINING_CONTRACT",
    unset = "config/training_controller.yml"
  )
  if (!nzchar(path) || !file.exists(path)) {
    stop("FUSE_TRAINING_CONTRACT_REQUIRED", call. = FALSE)
  }
  normalizePath(path, mustWork = TRUE)
}

s09_training_authority_path <- function() {
  path <- Sys.getenv("FUSE_TRAINING_AUTHORITY", unset = "")
  if (!nzchar(path) || !file.exists(path)) {
    stop("FUSE_TRAINING_AUTHORITY_REQUIRED: no formal execution is authorized", call. = FALSE)
  }
  normalizePath(path, mustWork = TRUE)
}

s09_run_cli <- function(arguments) {
  status <- system2(
    Sys.which("python"),
    arguments,
    stdout = TRUE, stderr = TRUE
  )
  if (!identical(attr(status, "status"), NULL)) stop(paste(status, collapse = "\n"), call. = FALSE)
  result <- jsonlite::fromJSON(tail(status, 1), simplifyVector = FALSE)
  if (!identical(result$status, "PASS") && !identical(result$status, "COMPLETE")) {
    stop("FUSE_TRAINING_COMMAND_DID_NOT_COMPLETE", call. = FALSE)
  }
  result
}

s09_controller_preflight <- function(authority, contract) {
  result <- s09_run_cli(c("scripts/training_controller.py", "preflight",
    "--authority", authority, "--contract", contract))
  authority
}

s09_controller_run <- function(authority, contract, preflight) {
  cfg <- yaml::read_yaml(contract)
  auth <- jsonlite::read_json(authority, simplifyVector = FALSE)
  configuration <- auth$content$scientific$configuration_id
  matrix <- cfg$roots$experiment_plan
  if (is.null(matrix) || !nzchar(matrix)) stop("CURRENT_EXPERIMENT_PLAN_REQUIRED", call. = FALSE)
  worker <- paste(shQuote(Sys.which("python")), "-m torch.distributed.run --standalone --nproc_per_node=2",
    "scripts/training_worker.py", "--authority", shQuote(authority), "--matrix", shQuote(matrix),
    "--configuration-id", shQuote(configuration), "--cache-root", shQuote(cfg$roots$production_cache),
    "--categories", shQuote(cfg$roots$categories), "--training-config config/training.yml",
    "--model-config config/model_inputs.yml --mode formal")
  result <- s09_run_cli(c("scripts/training_controller.py", "run", "--authority", authority,
    "--contract", contract, "--output", cfg$roots$writable_runs, "--science-worker-command", shQuote(worker)))
  normalizePath(result$training_execution, mustWork = TRUE)
}

s09_record_path <- function(contract, authority, stage) {
  cfg <- yaml::read_yaml(contract); auth <- jsonlite::read_json(authority, simplifyVector = FALSE)
  path <- file.path(cfg$roots$lifecycle_records, auth$identity, paste0(stage, ".json"))
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  path
}

s09_bundle <- function(execution, authority, contract) {
  output <- s09_record_path(contract, authority, "bundle")
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "bundle", "--execution", execution,
    "--authority", authority, "--contract", contract, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}

s09_finalize <- function(bundle, authority, contract) {
  cfg <- yaml::read_yaml(contract); output <- s09_record_path(contract, authority, "finalization")
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "finalize", "--bundle-record", bundle,
    "--publication-root", cfg$roots$canonical_publication, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}

s09_accept <- function(finalization, authority, contract) {
  cfg <- yaml::read_yaml(contract); output <- s09_record_path(contract, authority, "acceptance")
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "accept", "--finalization-record", finalization,
    "--authority", authority, "--publication-root", cfg$roots$canonical_publication, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}

s09_eligibility <- function(acceptance, authority, contract) {
  cfg <- yaml::read_yaml(contract); output <- s09_record_path(contract, authority, "eligibility")
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "eligibility", "--acceptance-record", acceptance,
    "--authority", authority, "--existing-eligibility", cfg$roots$eligibility_snapshot,
    "--publication-root", cfg$roots$canonical_publication, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}

s09_resolve_accepted_checkpoint <- function(eligibility, authority, contract) {
  cfg <- yaml::read_yaml(contract); output <- s09_record_path(contract, authority, "resolution")
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "resolve", "--eligibility-record", eligibility,
    "--publication-root", cfg$roots$canonical_publication, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}
