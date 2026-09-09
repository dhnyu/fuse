# Current production-training campaign orchestration. Scientific state remains in immutable artifacts.
s09_digest <- function(value) {
  raw <- charToRaw(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA, pretty = FALSE))
  paste(format(openssl::sha256(raw)), collapse = "")
}

s09_write_json <- function(value, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  payload <- charToRaw(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA, pretty = FALSE))
  if (file.exists(path)) {
    existing <- readBin(path, "raw", file.info(path)$size)
    if (!identical(existing, payload)) stop("S09_IMMUTABLE_JSON_COLLISION", call. = FALSE)
  } else {
    temporary <- tempfile(tmpdir = dirname(path)); writeBin(payload, temporary)
    if (!file.rename(temporary, path)) stop("S09_IMMUTABLE_JSON_COMMIT_FAILED", call. = FALSE)
  }
  normalizePath(path, mustWork = TRUE)
}

s09_training_contract_path <- function() {
  path <- Sys.getenv("FUSE_TRAINING_CONTRACT", unset = "config/training_controller.yml")
  if (!nzchar(path) || !file.exists(path)) stop("FUSE_TRAINING_CONTRACT_REQUIRED", call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}

s09_training_source_files <- function() {
  paths <- c(
    "config/training_controller.yml", "config/training.yml", "config/model_inputs.yml",
    "config/schemas/training_training_authority.schema.json",
    "config/schemas/training_selection_contract.schema.json",
    "config/schemas/s09_prepared_cache_acceptance.schema.json",
    "config/schemas/s09_campaign_acceptance.schema.json",
    "python/training_campaign.py", "python/training_configuration.py",
    "python/training_controller.py", "python/training_finalization.py",
    "python/training_progress.py",
    "python/training_prepared_cache.py", "python/training_worker.py",
    "scripts/prepare_training_cache.py", "scripts/training_campaign.py",
    "scripts/training_controller.py", "scripts/training_lifecycle.py", "scripts/training_worker.py"
  )
  paths[] <- normalizePath(paths, mustWork = TRUE); paths
}

s09_experiment_plan_path <- function(contract) {
  path <- yaml::read_yaml(contract)$roots$experiment_plan
  if (is.null(path) || !nzchar(path) || !file.exists(path)) stop("CURRENT_EXPERIMENT_PLAN_REQUIRED", call. = FALSE)
  normalizePath(path, mustWork = TRUE)
}

s09_run_cli <- function(arguments) {
  status <- system2(Sys.which("python"), arguments, stdout = TRUE, stderr = TRUE)
  if (!identical(attr(status, "status"), NULL)) stop(paste(status, collapse = "\n"), call. = FALSE)
  result <- jsonlite::fromJSON(tail(status, 1L), simplifyVector = FALSE)
  if (!result$status %in% c("PASS", "COMPLETE")) stop("FUSE_TRAINING_COMMAND_DID_NOT_COMPLETE", call. = FALSE)
  result
}

s09_build_prepared_cache <- function(contract, plan, sources) {
  stopifnot(file.exists(contract), file.exists(plan), all(file.exists(sources)))
  workers <- Sys.getenv("FUSE_S09_CACHE_WORKERS", unset = "16")
  output <- system2(Sys.which("python"), c("scripts/prepare_training_cache.py", "build",
    "--contract", contract, "--workers", workers), stdout = TRUE, stderr = "")
  if (!identical(attr(output, "status"), NULL)) stop(paste(output, collapse = "\n"), call. = FALSE)
  normalizePath(tail(output, 1L), mustWork = TRUE)
}

s09_resolve_contract <- function(contract, plan, cache_acceptance) {
  cfg <- yaml::read_yaml(contract); cache <- jsonlite::read_json(cache_acceptance, simplifyVector = FALSE)
  if (!identical(cache$status, "PASS") || cache$training_runs != 0L || cache$optimizer_updates != 0L) {
    stop("S09_PREPARED_CACHE_ACCEPTANCE_INVALID", call. = FALSE)
  }
  cfg$parents$production_cache_id <- cache$cache_id
  cfg$parents$production_cache_acceptance_id <- cache$acceptance_id
  cfg$roots$production_cache <- normalizePath(dirname(cache_acceptance), mustWork = TRUE)
  cfg$roots$production_cache_acceptance <- normalizePath(cache_acceptance, mustWork = TRUE)
  cfg$production_cache_manifest_sha256 <- cache$manifest_sha256
  output <- file.path(cfg$roots$lifecycle_records, "contracts",
                      paste0("s09contract_", substr(s09_digest(cfg), 1L, 24L), ".yml"))
  dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
  candidate <- tempfile(tmpdir = dirname(output)); yaml::write_yaml(cfg, candidate)
  if (file.exists(output)) {
    if (!identical(readBin(output, "raw", file.info(output)$size), readBin(candidate, "raw", file.info(candidate)$size))) {
      unlink(candidate); stop("S09_RESOLVED_CONTRACT_COLLISION", call. = FALSE)
    }
    unlink(candidate)
  } else if (!file.rename(candidate, output)) stop("S09_RESOLVED_CONTRACT_COMMIT_FAILED", call. = FALSE)
  normalizePath(output, mustWork = TRUE)
}

s09_campaign_cli <- function(mode, plan, contract, cache, output, results = character()) {
  args <- c("scripts/training_campaign.py", mode, "--plan", plan, "--contract", contract,
            "--cache-acceptance", cache, "--output", output)
  if (length(results)) args <- c(args, "--results", results)
  s09_run_cli(args)
}

s09_publish_ofat_authorities <- function(plan, contract, cache) {
  cfg <- yaml::read_yaml(contract); output <- file.path(cfg$roots$immutable_publication, "authorities")
  unlist(s09_campaign_cli("ofat", plan, contract, cache, output)$paths, use.names = FALSE)
}

s09_worker_matrix_value <- function(plan, authority) {
  matrix <- jsonlite::read_json(plan, simplifyVector = FALSE)
  auth <- jsonlite::read_json(authority, simplifyVector = FALSE)
  scientific <- auth$content$scientific
  rows <- matrix$hyperparameter_configurations
  if (identical(scientific$phase, "COMPARISON")) {
    replacement <- c(list(configuration_id = scientific$configuration_id), scientific$hyperparameters,
                     list(model_family = scientific$model_id))
    rows[[1L]] <- replacement
  }
  rows <- lapply(rows, function(row) {
    if (is.null(row$model_family)) row$model_family <- "FM"
    row$scientific <- list(ema = row$ema_momentum, peak_learning_rate = row$peak_learning_rate)
    row$scientific_hash <- if (identical(row$configuration_id, scientific$configuration_id)) {
      scientific$plan_configuration_hash
    } else s09_digest(row[c("d", "d_c", "K_aug", "augmentation_intensity", "ema_momentum", "peak_learning_rate")])
    row$plan_configuration_hash <- row$scientific_hash
    row
  })
  matrix$hyperparameter_configurations <- rows
  matrix
}

s09_worker_matrix <- function(plan, authority, contract) {
  matrix <- s09_worker_matrix_value(plan, authority)
  auth <- jsonlite::read_json(authority, simplifyVector = FALSE)
  cfg <- yaml::read_yaml(contract)
  s09_write_json(matrix, file.path(cfg$roots$lifecycle_records, "matrices",
                                  paste0(auth$identity, ".json")))
}

s09_controller_preflight <- function(authority, contract) {
  s09_run_cli(c("scripts/training_controller.py", "preflight", "--authority", authority, "--contract", contract)); authority
}

s09_controller_run <- function(authority, contract, preflight) {
  cfg <- yaml::read_yaml(contract); auth <- jsonlite::read_json(authority, simplifyVector = FALSE)
  configuration <- auth$content$scientific$configuration_id
  matrix <- s09_worker_matrix(cfg$roots$experiment_plan, authority, contract)
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
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE); path
}

s09_bundle <- function(execution, authority, contract) {
  cfg <- yaml::read_yaml(contract)
  matrix <- s09_worker_matrix(cfg$roots$experiment_plan, authority, contract)
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "bundle", "--execution", execution,
    "--authority", authority, "--contract", contract, "--matrix", matrix,
    "--result", s09_record_path(contract, authority, "bundle")))
  normalizePath(result$result, mustWork = TRUE)
}

s09_finalize <- function(bundle, authority, contract) {
  cfg <- yaml::read_yaml(contract)
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "finalize", "--bundle-record", bundle,
    "--publication-root", cfg$roots$canonical_publication, "--result", s09_record_path(contract, authority, "finalization")))
  normalizePath(result$result, mustWork = TRUE)
}

s09_accept <- function(finalization, authority, contract) {
  cfg <- yaml::read_yaml(contract)
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "accept", "--finalization-record", finalization,
    "--authority", authority, "--contract", contract,
    "--publication-root", cfg$roots$canonical_publication,
    "--result", s09_record_path(contract, authority, "acceptance")))
  normalizePath(result$result, mustWork = TRUE)
}

s09_eligibility <- function(acceptance, authority, contract) {
  cfg <- yaml::read_yaml(contract)
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "eligibility", "--acceptance-record", acceptance,
    "--authority", authority, "--existing-eligibility", cfg$roots$eligibility_snapshot,
    "--publication-root", cfg$roots$canonical_publication,
    "--result", s09_record_path(contract, authority, "eligibility")))
  normalizePath(result$result, mustWork = TRUE)
}

s09_resolve_accepted_checkpoint <- function(eligibility, authority, contract) {
  cfg <- yaml::read_yaml(contract)
  result <- s09_run_cli(c("scripts/training_lifecycle.py", "resolve", "--eligibility-record", eligibility,
    "--publication-root", cfg$roots$canonical_publication,
    "--result", s09_record_path(contract, authority, "resolution")))
  normalizePath(result$result, mustWork = TRUE)
}

s09_training_result <- function(finalization, acceptance, resolution, authority, contract) {
  handoff <- jsonlite::read_json(finalization, simplifyVector = FALSE)
  final <- jsonlite::read_json(handoff$finalization_path, simplifyVector = FALSE)
  auth <- jsonlite::read_json(authority, simplifyVector = FALSE)
  if (!identical(final$status, "SUCCEEDED")) stop("S09_TRAINING_RESULT_NOT_ACCEPTED", call. = FALSE)
  selected <- final$selected_checkpoint
  resolved <- jsonlite::read_json(resolution, simplifyVector = FALSE)
  if (!identical(resolved$checkpoint_id, selected$checkpoint_id)) stop("S09_CHECKPOINT_RESOLUTION_MISMATCH", call. = FALSE)
  value <- list(schema_version = "1.0.0", status = "PASS", phase = auth$content$scientific$phase,
    configuration_id = auth$content$scientific$configuration_id, model_id = auth$content$scientific$model_id,
    authority_id = auth$identity, acceptance_record = normalizePath(acceptance, mustWork = TRUE),
    checkpoint_id = selected$checkpoint_id, validation_retrieval_loss = selected$validation_retrieval_loss,
    mean_source_separation_margin = selected$mean_source_separation_margin, completed_epoch = selected$completed_epoch)
  s09_write_json(value, s09_record_path(contract, authority, "campaign-result"))
}

s09_select_winner <- function(plan, contract, cache, results) {
  cfg <- yaml::read_yaml(contract); output <- file.path(cfg$roots$canonical_publication, "campaign",
    jsonlite::read_json(plan, simplifyVector = FALSE)$plan_id, "ofat_winner.json")
  result <- s09_campaign_cli("winner", plan, contract, cache, output, results)
  normalizePath(result$path, mustWork = TRUE)
}

s09_publish_comparison_authorities <- function(plan, contract, cache, winner) {
  cfg <- yaml::read_yaml(contract); output <- file.path(cfg$roots$immutable_publication, "authorities")
  unlist(s09_campaign_cli("comparison", plan, contract, cache, output, winner)$paths, use.names = FALSE)
}

s09_accept_campaign <- function(plan, winner, comparison_results, cache, contract) {
  comparisons <- lapply(comparison_results, jsonlite::read_json, simplifyVector = FALSE)
  expected <- c("FM", paste0("A", 1:5), paste0("B", 1:9), "SSV", "DS")
  if (length(comparisons) != 17L || !setequal(vapply(comparisons, `[[`, character(1L), "model_id"), expected)) {
    stop("S09_COMPARISON_CAMPAIGN_INCOMPLETE", call. = FALSE)
  }
  value <- list(schema_version = "1.0.0", status = "PASS",
    experiment_plan_id = jsonlite::read_json(plan, simplifyVector = FALSE)$plan_id,
    prepared_cache_acceptance_id = jsonlite::read_json(cache, simplifyVector = FALSE)$acceptance_id,
    winner_id = jsonlite::read_json(winner, simplifyVector = FALSE)$winner_id,
    comparison_acceptance_records = sort(normalizePath(comparison_results, mustWork = TRUE)),
    training_runs = 28L, evaluation_runs = 0L)
  value$content_sha256 <- s09_digest(value)
  value$campaign_acceptance_id <- paste0("s09camp_", substr(value$content_sha256, 1L, 24L))
  cfg <- yaml::read_yaml(contract)
  path <- s09_write_json(value, file.path(cfg$roots$canonical_publication, "campaign",
                                         value$campaign_acceptance_id, "campaign_acceptance.json"))
  s09_campaign_cli("campaign-accepted", plan, contract, cache, path, winner)
  path
}
