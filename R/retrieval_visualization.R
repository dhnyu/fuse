# Dissertation spatial-scene retrieval: independent qualitative inspection only.
s10_manifest <- function(paths) {
  paths <- unlist(paths, use.names = FALSE)
  selected <- paths[grepl("(manifest|summary|acceptance)\\.json$", paths)]
  if (length(selected) != 1L) stop("S10 manifest is missing or ambiguous", call. = FALSE)
  selected
}

s10_rank_manifests <- function(paths) {
  paths <- unlist(paths, use.names = FALSE)
  paths[grepl("/rankings/[^/]+/manifest\\.json$", paths)]
}

s10_run <- function(stage, ...) {
  command <- c("scripts/retrieval_visualization.py", stage, unlist(list(...), use.names = FALSE))
  output <- system2("python", vapply(command, shQuote, character(1)), stdout = TRUE)
  code <- attr(output, "status")
  if (!is.null(code) && code != 0L) stop("S10 worker failed", call. = FALSE)
  paths <- unlist(jsonlite::fromJSON(tail(output, 1L)), use.names = FALSE)
  if (!length(paths) || any(!file.exists(paths))) stop("S10 output incomplete", call. = FALSE)
  paths
}

s10_common_args <- function(models, gallery, queries) {
  c("--models", s10_manifest(models), "--gallery", s10_manifest(gallery),
    "--queries", s10_manifest(queries))
}

s10_model_ids <- function(paths) {
  value <- jsonlite::read_json(s10_manifest(paths), simplifyVector = FALSE)
  lapply(value$body$models, `[[`, "configuration_id")
}

s10_parent_files <- function(contract) {
  cfg <- yaml::read_yaml(contract)
  campaign <- jsonlite::read_json(cfg$campaign, simplifyVector = FALSE)
  winner_path <- file.path(dirname(dirname(cfg$campaign)), campaign$experiment_plan_id,
                           campaign$runtime_implementation_sha256, "ofat_winner.json")
  winner <- jsonlite::read_json(winner_path, simplifyVector = FALSE)
  rows <- c(winner$candidate_results, lapply(campaign$comparison_acceptance_records,
    jsonlite::read_json, simplifyVector = FALSE))
  paths <- c(cfg$campaign, winner_path, unlist(campaign$comparison_acceptance_records),
             names(cfg$source_pins))
  for (row in rows) {
    handoff <- jsonlite::read_json(row$acceptance_record, simplifyVector = FALSE)
    final <- jsonlite::read_json(handoff$finalization_path, simplifyVector = FALSE)
    paths <- c(paths, row$acceptance_record, handoff$finalization_path,
      list.files(handoff$acceptance_path, recursive = TRUE, full.names = TRUE),
      list.files(handoff$bundle_path, recursive = TRUE, full.names = TRUE),
      file.path(handoff$checkpoint_root, final$selected_checkpoint$payload_locator$location$relative_path))
  }
  paths <- unique(unlist(paths, use.names = FALSE))
  if (any(!file.exists(paths))) stop("S10 parent evidence missing", call. = FALSE)
  paths
}
