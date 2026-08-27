args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) stop("Usage: run_p2_relation_branch.R MANIFEST PASS BRANCH_ID", call. = FALSE)
manifest_path <- normalizePath(args[[1L]], mustWork = TRUE)
pass_id <- args[[2L]]
branch_id <- args[[3L]]
pass_label <- switch(pass_id, pass_a_40 = "PASS_A", pass_b_10 = "PASS_B", pass_c_5 = "PASS_C",
                     stop("Unsupported pass ID", call. = FALSE))
source("_targets.R")
frozen <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
index <- match(branch_id, vapply(frozen$branches, `[[`, character(1L), "branch_id"))
if (is.na(index)) stop("Unknown P2 relation branch: ", branch_id, call. = FALSE)
branch <- frozen$branches[[index]]
store <- frozen$research_store
plans <- targets::tar_read(base_spatial_observation_plan, store = store)
spec <- plans[[as.integer(branch$ordinal)]]
vector_paths <- targets::tar_read_raw(branch$vector_target, store = store)
stage_root <- file.path(dirname(manifest_path), "staging", pass_id, branch_id)
result_dir <- file.path(dirname(manifest_path), "results", pass_id)
dir.create(result_dir, recursive = TRUE, showWarnings = FALSE)
result_path <- file.path(result_dir, paste0(branch_id, ".json"))
started <- Sys.time()
.p2_tiered_publish_record <- NULL

publish_deterministic_directory <- function(final_dir, required_basenames, writer,
                                            compare_basenames = required_basenames) {
  if (dir.exists(stage_root)) stop("Pass-specific stage already exists: ", stage_root, call. = FALSE)
  dir.create(dirname(stage_root), recursive = TRUE, showWarnings = FALSE)
  dir.create(stage_root)
  writer(stage_root)
  staged <- file.path(stage_root, required_basenames)
  if (!all(file.exists(staged)) || any(file.info(staged)$size <= 0)) {
    stop("Tiered relation stage is incomplete: ", stage_root, call. = FALSE)
  }
  staged_checksums <- setNames(vapply(staged, sha256_file, character(1L)), basename(staged))
  final <- file.path(final_dir, required_basenames)
  reused <- FALSE
  if (dir.exists(final_dir)) {
    if (!all(file.exists(final))) stop("Existing relation bundle is incomplete: ", final_dir, call. = FALSE)
    stage_hash <- staged_checksums[compare_basenames]
    final_hash <- setNames(vapply(file.path(final_dir, compare_basenames), sha256_file, character(1L)), compare_basenames)
    if (!identical(stage_hash, final_hash)) stop("Immutable relation collision: ", final_dir, call. = FALSE)
    reused <- TRUE
  } else {
    dir.create(dirname(final_dir), recursive = TRUE, showWarnings = FALSE)
    if (!file.rename(stage_root, final_dir)) stop("Atomic tiered relation publish failed: ", final_dir, call. = FALSE)
  }
  .p2_tiered_publish_record <<- list(
    stage_path = stage_root, stage_retained = reused,
    canonical_directory = final_dir, canonical_reused = reused,
    staged_checksums = as.list(staged_checksums),
    canonical_checksums = as.list(setNames(vapply(final, sha256_file, character(1L)), basename(final)))
  )
  normalizePath(final, mustWork = TRUE)
}

write_result <- function(value) {
  tmp <- paste0(result_path, ".tmp-", Sys.getpid())
  write_json_file(value, tmp)
  if (!file.rename(tmp, result_path)) stop("Could not publish branch result", call. = FALSE)
}

status <- tryCatch({
  outputs <- p2_build_relation_shard(spec, vector_paths,
    targets::tar_read(study_data_inputs, store = store),
    targets::tar_read(study_data_inputs, store = store),
    relation_contract_paths(), 1L, 1L)
  manifest <- jsonlite::read_json(outputs[basename(outputs) == "branch_manifest.json"], simplifyVector = FALSE)
  if (!identical(manifest$status_final, "PASS") || !identical(manifest$branch_id, branch_id)) {
    stop("Relation branch manifest validation failed", call. = FALSE)
  }
  vector_manifest <- vector_paths[basename(vector_paths) == "branch_manifest.json"]
  write_result(list(
    schema_version = "1.0.0", pass = pass_id, branch_id = branch_id,
    status = paste0("COMPLETED_", pass_label), final_status = "COMPLETED",
    started_at = format(started, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul"),
    completed_at = kst_now(), wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
    pid = Sys.getpid(), workers = 1L, threads = 1L,
    vector_manifest_sha256 = sha256_file(vector_manifest),
    relation_dataset_id = branch$relation_dataset_id,
    output_paths = as.list(normalizePath(outputs, mustWork = TRUE)),
    canonical_reused = .p2_tiered_publish_record$canonical_reused,
    staging_path = .p2_tiered_publish_record$stage_path,
    staging_retained = .p2_tiered_publish_record$stage_retained,
    staged_checksums = .p2_tiered_publish_record$staged_checksums,
    canonical_checksums = .p2_tiered_publish_record$canonical_checksums,
    max_rss_kb = proc_max_rss_kb()
  ))
  0L
}, error = function(error) {
  message <- conditionMessage(error)
  classification <- if (grepl("OOM|out of memory|No space left|too many open files", message, ignore.case = TRUE)) {
    paste0("FAILED_RESOURCE_", pass_label)
  } else {
    paste0("FAILED_SCIENTIFIC_", pass_label)
  }
  write_result(list(
    schema_version = "1.0.0", pass = pass_id, branch_id = branch_id,
    status = classification, final_status = "FAILED",
    started_at = format(started, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul"),
    completed_at = kst_now(), wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
    pid = Sys.getpid(), workers = 1L, threads = 1L, error = message,
    staging_path = stage_root, staging_complete = FALSE, max_rss_kb = proc_max_rss_kb()
  ))
  1L
})
quit(save = "no", status = status)
