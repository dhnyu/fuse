# Execution-only orchestration for the P2 40 -> 10 -> 5 relation policy.
# This file is deliberately excluded from p2_base_spatial_contract_paths():
# worker capacity and pass ledgers are not scientific identity inputs.

p2_relation_tiered_policy_version <- function() "p2-relation-tiered-v1"

p2_relation_tiered_root <- function(observation_plans) {
  plans <- if (is.list(observation_plans) && !is.null(observation_plans$branch_id)) {
    list(observation_plans)
  } else {
    observation_plans
  }
  if (!length(plans)) stop("P2 relation plans are empty", call. = FALSE)
  roots <- vapply(plans, function(spec) {
    dirname(dirname(dirname(dirname(spec$output$directory))))
  }, character(1L))
  if (length(unique(roots)) != 1L) stop("P2 relation plans do not share one observation root", call. = FALSE)
  file.path(unique(roots), "execution", p2_relation_tiered_policy_version())
}

p2_relation_tiered_manifest_path <- function(observation_plans) {
  file.path(p2_relation_tiered_root(observation_plans), "intended_relation_branches.json")
}

p2_relation_tiered_acceptance_path <- function(observation_plans) {
  file.path(p2_relation_tiered_root(observation_plans), "tiered_relation_acceptance.json")
}

p2_relation_expected_paths <- function(final_dir) {
  file.path(final_dir, relation_output_names())
}

p2_prepare_relation_tiered_manifest <- function(observation_plans, vector_shards,
                                                study_data_inputs, relation_contract_files,
                                                aborted_record = NULL) {
  plans <- observation_plans
  if (is.list(plans) && !is.null(plans$branch_id)) plans <- list(plans)
  if (!length(plans) || length(plans) != length(vector_shards)) {
    stop("Plan/vector branch cardinality mismatch", call. = FALSE)
  }
  vector_by_id <- setNames(vector_shards, vapply(vector_shards, function(paths) {
    manifest <- jsonlite::read_json(artifact_path(paths, "branch_manifest.json"), simplifyVector = FALSE)
    manifest$branch_id
  }, character(1L)))
  ordered_ids <- vapply(plans, `[[`, character(1L), "branch_id")
  if (!setequal(names(vector_by_id), ordered_ids)) stop("Plan/vector branch identity mismatch", call. = FALSE)
  vector_shards <- unname(vector_by_id[ordered_ids])
  study <- normalizePath(study_data_inputs, mustWork = TRUE)
  road_path <- relation_road_path(study)
  road_record <- list(
    path = plans[[1L]]$sources$road$path,
    artifact_id = plans[[1L]]$sources$road$source_artifact_id,
    sha256 = sha256_file(road_path), size_bytes = unname(file.info(road_path)$size),
    links_layer = "links", nodes_layer = "nodes"
  )
  config <- load_relation_config(relation_contract_files)
  root <- p2_relation_tiered_root(plans)
  dir.create(root, recursive = TRUE, showWarnings = FALSE)
  branches <- lapply(seq_along(plans), function(i) {
    spec <- plans[[i]]
    vector_paths <- normalizePath(vector_shards[[i]], mustWork = TRUE)
    vector <- read_i10_branch_context(spec, vector_paths)
    relation_id <- relation_dataset_identity(spec, vector, road_record, config)
    final_dir <- file.path(dirname(dirname(dirname(dirname(spec$output$directory)))), relation_id,
                           "relations", "branches", spec$branch_id)
    current_paths <- p2_relation_expected_paths(final_dir)
    list(
      ordinal = i, branch_id = spec$branch_id,
      scene_ids = as.list(sort(unlist(spec$scene_ids), method = "radix")),
      scene_count = length(spec$scene_ids), split_counts = spec$split_counts,
      estimated_counts = spec$estimated_counts,
      estimated_cost = spec$estimated_geometry$estimated_cost,
      observation_dataset_id = spec$observation_dataset_id,
      original_observation_id = spec$original_observation_id,
      scene_index_id = spec$scene_index_id,
      plan_spec_path = normalizePath(spec$.path, mustWork = TRUE),
      vector_inputs = lapply(vector_paths, function(path) list(
        path = normalizePath(path, mustWork = TRUE), size_bytes = unname(file.info(path)$size),
        sha256 = sha256_file(path)
      )),
      relation_dataset_id = relation_id,
      expected_output_directory = final_dir,
      expected_outputs = as.list(current_paths),
      pre_pass_canonical = list(
        complete = all(file.exists(current_paths)),
        checksums = if (all(file.exists(current_paths))) {
          as.list(setNames(vapply(current_paths, sha256_file, character(1L)), basename(current_paths)))
        } else list()
      )
    )
  })
  scientific <- list(
    policy_version = p2_relation_tiered_policy_version(),
    original_observation_id = plans[[1L]]$original_observation_id,
    observation_dataset_id = plans[[1L]]$observation_dataset_id,
    scene_index_id = plans[[1L]]$scene_index_id,
    relation_config_sha256 = config$scientific_hash,
    relation_schema_sha256 = config$schema_hash,
    relation_implementation_sha256 = config$implementation_source_hash,
    road_source_sha256 = road_record$sha256,
    branches = lapply(branches, function(x) x[c(
      "ordinal", "branch_id", "scene_ids", "observation_dataset_id", "relation_dataset_id"
    )] |> c(list(vector_input_sha256 = lapply(x$vector_inputs, `[[`, "sha256"))))
  )
  scientific_identity_sha256 <- p0_scientific_sha256(scientific)
  value <- list(
    schema_version = "1.0.0", policy_version = p2_relation_tiered_policy_version(),
    status = "FROZEN", study_data_inputs = as.list(study),
    relation_contract_files = as.list(normalizePath(relation_contract_files, mustWork = TRUE)),
    relation_attempt_id = paste0("rte_", substr(scientific_identity_sha256, 1L, 24L)),
    branch_count = length(branches), configured_passes = list(
      pass_a_40 = list(workers = 40L, input = "ALL"),
      pass_b_10 = list(workers = 10L, input = "PASS_A_NATIVE_RESOURCE_UNATTEMPTED"),
      pass_c_5 = list(workers = 5L, input = "PASS_B_NATIVE_RESOURCE_UNATTEMPTED")
    ),
    thread_contract = as.list(setNames(rep("1", 9L), c(
      "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
      "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GDAL_NUM_THREADS",
      "ARROW_NUM_THREADS", "PYTHONDONTWRITEBYTECODE"
    ))),
    scientific_identity_sha256 = scientific_identity_sha256,
    branches = branches, aborted_policy_order_run = aborted_record,
    generated_at = kst_now()
  )
  path <- p2_relation_tiered_manifest_path(plans)
  if (file.exists(path)) {
    prior <- jsonlite::read_json(path, simplifyVector = FALSE)
    if (!identical(prior$scientific_identity_sha256, value$scientific_identity_sha256)) {
      stop("Frozen P2 relation branch manifest collision", call. = FALSE)
    }
    return(normalizePath(path, mustWork = TRUE))
  }
  write_json_file(value, path)
  normalizePath(path, mustWork = TRUE)
}

p2_run_relation_tiered_execution <- function(observation_plans, vector_shards,
                                             study_data_inputs, relation_contract_files) {
  manifest <- p2_prepare_relation_tiered_manifest(
    observation_plans, vector_shards, study_data_inputs, relation_contract_files
  )
  acceptance <- p2_relation_tiered_acceptance_path(observation_plans)
  if (file.exists(acceptance)) {
    current <- jsonlite::read_json(acceptance, simplifyVector = FALSE)
    frozen <- jsonlite::read_json(manifest, simplifyVector = FALSE)
    if (identical(current$status, "PASS") &&
        identical(current$intended_branch_manifest_sha256, sha256_file(manifest)) &&
        identical(current$policy_version, frozen$policy_version)) {
      return(normalizePath(c(manifest, acceptance, unlist(lapply(current$pass_summaries, `[[`, "path"))), mustWork = TRUE))
    }
    stop("Existing P2 relation execution acceptance does not match the current manifest", call. = FALSE)
  }
  runner <- normalizePath(file.path(getwd(), "scripts/run_spatial_relations.py"), mustWork = TRUE)
  passes <- c(pass_a_40 = 40L, pass_b_10 = 10L, pass_c_5 = 5L)
  previous <- NULL; summaries <- character()
  for (pass_id in names(passes)) {
    if (!is.null(previous)) {
      prior <- jsonlite::read_json(previous, simplifyVector = FALSE)
      statuses <- vapply(prior$records, `[[`, character(1L), "status")
      retryable <- grepl("^FAILED_(NATIVE|RESOURCE)|^UNATTEMPTED", statuses)
      if (!any(retryable)) break
    }
    summary <- file.path(dirname(manifest), "passes", pass_id, "summary.json")
    if (!file.exists(summary)) {
      args <- c(runner, "--manifest", manifest, "--pass-id", pass_id,
                "--workers", as.character(passes[[pass_id]]))
      if (!is.null(previous)) args <- c(args, "--previous-summary", previous)
      output <- system2(research_python_executable(), args, stdout = TRUE, stderr = TRUE)
      if ((attr(output, "status") %||% 0L) != 0L && !file.exists(summary)) {
        stop("P2 relation pass failed before publishing its summary: ", paste(output, collapse = " | "), call. = FALSE)
      }
    }
    current <- jsonlite::read_json(summary, simplifyVector = FALSE)
    statuses <- vapply(current$records, `[[`, character(1L), "status")
    if (any(grepl("^FAILED_SCIENTIFIC", statuses))) stop("P2 relation scientific failure in ", pass_id, call. = FALSE)
    summaries <- c(summaries, summary); previous <- summary
  }
  accepted <- p2_finalize_relation_tiered(manifest)
  normalizePath(c(manifest, accepted, summaries), mustWork = TRUE)
}

p2_validate_registered_relation_bundle <- function(branch, result) {
  required <- unlist(branch$expected_outputs, use.names = FALSE)
  if (!all(file.exists(required)) || any(file.info(required)$size <= 0)) {
    stop("Tiered relation canonical bundle is incomplete: ", branch$branch_id, call. = FALSE)
  }
  checksums <- setNames(vapply(required, sha256_file, character(1L)), basename(required))
  recorded <- unlist(result$canonical_checksums, use.names = TRUE)
  if (!identical(checksums[names(recorded)], recorded)) {
    stop("Tiered relation canonical checksum mismatch: ", branch$branch_id, call. = FALSE)
  }
  manifest <- jsonlite::read_json(required[basename(required) == "branch_manifest.json"], simplifyVector = FALSE)
  checks <- c(
    identical(manifest$status, "PASS"), identical(manifest$status_final, "PASS"),
    identical(manifest$branch_id, branch$branch_id),
    identical(manifest$relation_dataset_id, branch$relation_dataset_id),
    identical(as.integer(manifest$scene_count), as.integer(branch$scene_count)),
    setequal(unlist(manifest$scene_ids), unlist(branch$scene_ids))
  )
  if (!all(checks)) stop("Tiered relation manifest contract mismatch: ", branch$branch_id, call. = FALSE)
  normalizePath(required, mustWork = TRUE)
}

p2_register_tiered_relation_shard <- function(observation_plan, vector_shard,
                                                tiered_acceptance_file) {
  acceptance <- jsonlite::read_json(
    artifact_path(tiered_acceptance_file, "tiered_relation_acceptance.json"), simplifyVector = FALSE
  )
  if (!identical(acceptance$status, "PASS")) stop("Tiered relation acceptance is not PASS", call. = FALSE)
  branch <- acceptance$branches[[observation_plan$branch_id]]
  if (is.null(branch) || !identical(branch$final_status, "COMPLETED")) {
    stop("Tiered relation branch is not completed: ", observation_plan$branch_id, call. = FALSE)
  }
  frozen <- jsonlite::read_json(acceptance$intended_branch_manifest, simplifyVector = FALSE)
  intended <- frozen$branches[[match(observation_plan$branch_id, vapply(frozen$branches, `[[`, character(1L), "branch_id"))]]
  vector_manifest <- vector_shard[basename(vector_shard) == "branch_manifest.json"]
  if (!length(vector_manifest) || !identical(sha256_file(vector_manifest), branch$vector_manifest_sha256)) {
    stop("Tiered relation vector input mismatch: ", observation_plan$branch_id, call. = FALSE)
  }
  p2_validate_registered_relation_bundle(intended, branch)
}

p2_finalize_relation_tiered <- function(manifest_path) {
  manifest_path <- normalizePath(manifest_path, mustWork = TRUE)
  root <- dirname(manifest_path)
  frozen <- jsonlite::read_json(manifest_path, simplifyVector = FALSE)
  pass_paths <- setNames(file.path(root, "passes", c("pass_a_40", "pass_b_10", "pass_c_5"), "summary.json"),
                         c("pass_a_40", "pass_b_10", "pass_c_5"))
  summaries <- lapply(pass_paths[file.exists(pass_paths)], jsonlite::read_json, simplifyVector = FALSE)
  if (!"pass_a_40" %in% names(summaries)) stop("Pass A summary is required", call. = FALSE)
  final <- list()
  blocked <- list()
  for (branch in frozen$branches) {
    id <- branch$branch_id
    records <- lapply(summaries, function(summary) summary$records[[id]])
    records <- records[!vapply(records, is.null, logical(1L))]
    completed <- records[vapply(records, function(record) identical(record$final_status, "COMPLETED"), logical(1L))]
    scientific <- records[vapply(records, function(record) grepl("^FAILED_SCIENTIFIC", record$status), logical(1L))]
    if (length(scientific)) {
      blocked[[id]] <- scientific[[1L]]
      next
    }
    if (!length(completed)) {
      blocked[[id]] <- list(status = "UNRESOLVED", records = records)
      next
    }
    record <- completed[[1L]]
    paths <- p2_validate_registered_relation_bundle(branch, record)
    record$output_paths <- as.list(paths)
    record$final_pass <- record$pass
    final[[id]] <- record
  }
  if (length(blocked) || length(final) != as.integer(frozen$branch_count)) {
    stop("Tiered relation execution has unresolved/scientific failures: ", paste(names(blocked), collapse = ", "), call. = FALSE)
  }
  scientific <- list(
    intended_scientific_identity_sha256 = frozen$scientific_identity_sha256,
    branch_outputs = lapply(final, function(record) list(
      branch_id = record$branch_id, relation_dataset_id = record$relation_dataset_id,
      canonical_checksums = record$canonical_checksums
    ))
  )
  value <- list(
    schema_version = "1.0.0", status = "PASS",
    acceptance_id = paste0("rta_", substr(p0_scientific_sha256(scientific), 1L, 24L)),
    scientific_identity_sha256 = p0_scientific_sha256(scientific),
    intended_branch_manifest = manifest_path,
    intended_branch_manifest_sha256 = sha256_file(manifest_path),
    policy_version = frozen$policy_version, relation_attempt_id = frozen$relation_attempt_id,
    branch_count = length(final),
    pass_summaries = lapply(names(summaries), function(name) list(
      pass = name, path = normalizePath(pass_paths[[name]], mustWork = TRUE),
      sha256 = sha256_file(pass_paths[[name]]), status_counts = summaries[[name]]$status_counts,
      requested_workers = summaries[[name]]$requested_workers,
      peak_concurrency = summaries[[name]]$peak_concurrency,
      peak_worker_rss_sum_kb = summaries[[name]]$peak_worker_rss_sum_kb,
      wall_time_seconds = summaries[[name]]$wall_time_seconds
    )),
    branches = final, generated_at = kst_now()
  )
  path <- file.path(root, "tiered_relation_acceptance.json")
  if (file.exists(path)) {
    prior <- jsonlite::read_json(path, simplifyVector = FALSE)
    if (!identical(prior$scientific_identity_sha256, value$scientific_identity_sha256)) {
      stop("Tiered relation acceptance collision", call. = FALSE)
    }
    return(normalizePath(path, mustWork = TRUE))
  }
  write_json_file(value, path)
  normalizePath(path, mustWork = TRUE)
}
