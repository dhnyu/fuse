# P9 v2 production controller orchestration. Scientific state remains in the ledger.
p9v2_training_contract_path <- function() {
  path <- Sys.getenv(
    "P9_V2_TRAINING_CONTRACT",
    unset = "config/p9_v2_training_controller.yml"
  )
  if (!nzchar(path) || !file.exists(path)) {
    stop("P9_V2_TRAINING_CONTRACT_REQUIRED", call. = FALSE)
  }
  normalizePath(path, mustWork = TRUE)
}

p9v2_training_authority_path <- function() {
  path <- Sys.getenv("P9_V2_TRAINING_AUTHORITY", unset = "")
  if (!nzchar(path) || !file.exists(path)) {
    stop("P9_V2_TRAINING_AUTHORITY_REQUIRED: no formal execution is authorized", call. = FALSE)
  }
  normalizePath(path, mustWork = TRUE)
}

p9v2_run_cli <- function(arguments) {
  status <- system2(
    Sys.which("python"),
    arguments,
    stdout = TRUE, stderr = TRUE
  )
  if (!identical(attr(status, "status"), NULL)) stop(paste(status, collapse = "\n"), call. = FALSE)
  result <- jsonlite::fromJSON(tail(status, 1), simplifyVector = FALSE)
  if (!identical(result$status, "PASS") && !identical(result$status, "COMPLETE")) {
    stop("P9_V2_COMMAND_DID_NOT_COMPLETE", call. = FALSE)
  }
  result
}

p9v2_controller_preflight <- function(authority, contract) {
  result <- p9v2_run_cli(c("scripts/p9_v2_training_controller.py", "preflight",
    "--authority", authority, "--contract", contract))
  authority
}

p9v2_controller_run <- function(authority, contract, preflight) {
  cfg <- yaml::read_yaml(contract)
  auth <- jsonlite::read_json(authority, simplifyVector = FALSE)
  configuration <- auth$content$scientific$configuration_id
  matrix <- cfg$roots$configuration_matrix
  if (is.null(matrix) || !nzchar(matrix)) {
    matrix <- file.path(cfg$roots$p8_bundle, "hyperparameter_configuration_matrix.json")
  }
  worker <- paste(shQuote(Sys.which("python")), "-m torch.distributed.run --standalone --nproc_per_node=2",
    "scripts/p9_v2_training_worker.py", "--authority", shQuote(authority), "--matrix", shQuote(matrix),
    "--configuration-id", shQuote(configuration), "--cache-root", shQuote(cfg$roots$production_cache),
    "--categories", shQuote(cfg$roots$categories), "--training-config config/p7_deterministic_training.yml",
    "--model-config config/p6_model_dataloader.yml --mode formal")
  result <- p9v2_run_cli(c("scripts/p9_v2_training_controller.py", "run", "--authority", authority,
    "--contract", contract, "--output", cfg$roots$writable_runs, "--science-worker-command", shQuote(worker)))
  normalizePath(result$training_execution, mustWork = TRUE)
}

p9v2_record_path <- function(contract, authority, stage) {
  cfg <- yaml::read_yaml(contract); auth <- jsonlite::read_json(authority, simplifyVector = FALSE)
  path <- file.path(cfg$roots$lifecycle_records, auth$identity, paste0(stage, ".json"))
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  path
}

p9v2_bundle <- function(execution, authority, contract) {
  output <- p9v2_record_path(contract, authority, "bundle")
  result <- p9v2_run_cli(c("scripts/p9_v2_training_lifecycle.py", "bundle", "--execution", execution,
    "--authority", authority, "--contract", contract, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}

p9v2_finalize <- function(bundle, authority, contract) {
  cfg <- yaml::read_yaml(contract); output <- p9v2_record_path(contract, authority, "finalization")
  result <- p9v2_run_cli(c("scripts/p9_v2_training_lifecycle.py", "finalize", "--bundle-record", bundle,
    "--publication-root", cfg$roots$canonical_publication, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}

p9v2_accept <- function(finalization, authority, contract) {
  cfg <- yaml::read_yaml(contract); output <- p9v2_record_path(contract, authority, "acceptance")
  result <- p9v2_run_cli(c("scripts/p9_v2_training_lifecycle.py", "accept", "--finalization-record", finalization,
    "--authority", authority, "--publication-root", cfg$roots$canonical_publication, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}

p9v2_eligibility <- function(acceptance, authority, contract) {
  cfg <- yaml::read_yaml(contract); output <- p9v2_record_path(contract, authority, "eligibility")
  result <- p9v2_run_cli(c("scripts/p9_v2_training_lifecycle.py", "eligibility", "--acceptance-record", acceptance,
    "--authority", authority, "--existing-eligibility", cfg$roots$eligibility_snapshot,
    "--publication-root", cfg$roots$canonical_publication, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}

p9v2_resolve_accepted_checkpoint <- function(eligibility, authority, contract) {
  cfg <- yaml::read_yaml(contract); output <- p9v2_record_path(contract, authority, "resolution")
  result <- p9v2_run_cli(c("scripts/p9_v2_training_lifecycle.py", "resolve", "--eligibility-record", eligibility,
    "--publication-root", cfg$roots$canonical_publication, "--result", output))
  normalizePath(result$result, mustWork = TRUE)
}
