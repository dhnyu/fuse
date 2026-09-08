p4_tiered_status_levels <- function() {
  c("COMPLETED", "FAILED_NATIVE", "FAILED_RESOURCE", "FAILED_SCIENTIFIC", "UNATTEMPTED")
}

p4_tiered_ledger_counts <- function(ledger, pass_name) {
  if (!is.list(ledger) || !is.list(ledger$branches) || !length(ledger$branches)) {
    stop("P4 Pass ", pass_name, " ledger has no branch results", call. = FALSE)
  }
  branch_ids <- unname(vapply(ledger$branches, function(x) x$branch_id %||% "", character(1L)))
  statuses <- unname(vapply(ledger$branches, function(x) x$status %||% "", character(1L)))
  if (any(!nzchar(branch_ids)) || anyDuplicated(branch_ids)) {
    stop("P4 Pass ", pass_name, " ledger has missing or duplicate branch IDs", call. = FALSE)
  }
  unknown <- setdiff(unique(statuses), p4_tiered_status_levels())
  if (length(unknown)) {
    stop("P4 Pass ", pass_name, " ledger has unknown status: ", paste(unknown, collapse = ", "), call. = FALSE)
  }
  counts <- setNames(
    vapply(p4_tiered_status_levels(), function(x) sum(statuses == x), integer(1L)),
    p4_tiered_status_levels()
  )
  declared <- ledger$status_counts
  if (is.null(declared) || any(!p4_tiered_status_levels() %in% names(declared))) {
    stop("P4 Pass ", pass_name, " ledger status counts are missing", call. = FALSE)
  }
  declared <- setNames(
    vapply(p4_tiered_status_levels(), function(x) as.integer(declared[[x]]), integer(1L)),
    p4_tiered_status_levels()
  )
  if (!identical(counts, declared)) {
    stop("P4 Pass ", pass_name, " ledger status counts do not match branch results", call. = FALSE)
  }
  list(counts = counts, branch_ids = branch_ids, statuses = statuses)
}

p4_assert_tiered_pass <- function(ledger, runner_status, pass_name, log_path) {
  observed <- p4_tiered_ledger_counts(ledger, pass_name)
  failed <- observed$branch_ids[observed$statuses == "FAILED_SCIENTIFIC"]
  if (length(failed) || identical(runner_status, 2L)) {
    stop(
      "P4 Pass ", pass_name, " scientific failure", if (length(failed)) paste0(": ", paste(failed, collapse = ", ")) else "",
      "; see ", log_path, call. = FALSE
    )
  }
  retryable <- sum(observed$counts[c("FAILED_NATIVE", "FAILED_RESOURCE", "UNATTEMPTED")])
  expected_status <- if (retryable) 1L else 0L
  if (is.na(runner_status) || !identical(as.integer(runner_status), expected_status)) {
    stop(
      "P4 Pass ", pass_name, " runner exit status disagrees with its ledger: exit=",
      if (is.na(runner_status)) "NA" else runner_status, ", retryable=", retryable,
      "; see ", log_path, call. = FALSE
    )
  }
  observed
}

p4_summarize_tiered_execution <- function(final_ledger, bank_id, plan_id, pass_ledgers,
                                           expected_branch_ids) {
  observed <- p4_tiered_ledger_counts(final_ledger, final_ledger$pass %||% "final")
  expected_branch_ids <- sort(as.character(expected_branch_ids), method = "radix")
  actual_branch_ids <- sort(observed$branch_ids, method = "radix")
  if (!length(expected_branch_ids) || !identical(actual_branch_ids, expected_branch_ids)) {
    stop("P4 final ledger branch coverage does not match the bank plan", call. = FALSE)
  }
  failed <- observed$branch_ids[observed$statuses == "FAILED_SCIENTIFIC"]
  if (length(failed)) {
    stop("P4 final ledger contains scientific failures: ", paste(failed, collapse = ", "), call. = FALSE)
  }
  unresolved <- sum(observed$counts[c("FAILED_NATIVE", "FAILED_RESOURCE", "UNATTEMPTED")])
  if (unresolved) {
    stop("P4 tiered execution exhausted recovery passes with unresolved branches", call. = FALSE)
  }
  list(
    schema_version = "1.0.0", status = "PASS", bank_id = bank_id,
    plan_id = plan_id, branch_count = length(expected_branch_ids),
    pass_ledgers = basename(pass_ledgers), final_completed = unname(observed$counts[["COMPLETED"]])
  )
}

p4_existing_bank_branch_state <- function(plan_branch) {
  final <- plan_branch$output_directory
  payload_name <- paste0(plan_branch$branch_id, ".tar")
  paths <- file.path(final, c(payload_name, "branch_manifest.json", "execution.json"))
  if (!dir.exists(final)) return(list(status = "MISSING", branch_id = plan_branch$branch_id, paths = paths))
  if (!all(file.exists(paths))) return(list(status = "INCOMPLETE", branch_id = plan_branch$branch_id, paths = paths))
  manifest <- tryCatch(jsonlite::read_json(paths[[2L]], simplifyVector = FALSE), error = identity)
  execution <- tryCatch(jsonlite::read_json(paths[[3L]], simplifyVector = FALSE), error = identity)
  if (inherits(manifest, "error") || inherits(execution, "error")) {
    return(list(status = "INVALID", branch_id = plan_branch$branch_id, paths = paths))
  }
  valid <- identical(manifest$branch_id, plan_branch$branch_id) &&
    identical(manifest$bank_id, plan_branch$bank_id) &&
    identical(manifest$payload$filename, payload_name) &&
    identical(as.numeric(manifest$payload$size_bytes), unname(file.info(paths[[1L]])$size)) &&
    identical(manifest$payload$sha256, sha256_file(paths[[1L]])) &&
    all(unlist(manifest$validation, use.names = FALSE) == "PASS") &&
    identical(execution$pass, "A")
  list(status = if (valid) "VALID" else "INVALID", branch_id = plan_branch$branch_id, paths = paths)
}

p4_run_tiered_bank_current <- function(plan, contract_files) {
  spec <- p4_load_spec(contract_files)
  if (length(plan) != 288L) stop("P4 tiered execution requires 288 planned branches", call. = FALSE)
  bank_id <- plan[[1L]]$bank_id
  plan_dir <- dirname(plan[[1L]]$.plan_path)
  bank_root <- dirname(dirname(plan_dir))
  attempt_id <- paste0(format(Sys.time(), "%Y%m%d_%H%M%S"), "_", Sys.getpid())
  execution_root <- file.path(bank_root, "executions", paste0("tiered_", attempt_id))
  dir.create(execution_root, recursive = TRUE, showWarnings = FALSE)
  runner <- spec$files[basename(spec$files) == "run_augmentation_bank.py"]
  previous_ledger <- NULL
  ledgers <- character()
  logs <- character()
  passes <- list(A = 40L, B = 10L, C = 5L)
  for (pass_name in names(passes)) {
    if (pass_name != "A") {
      previous <- jsonlite::read_json(previous_ledger, simplifyVector = FALSE)
      previous_counts <- p4_tiered_ledger_counts(previous, names(passes)[match(pass_name, names(passes)) - 1L])$counts
      retryable <- sum(previous_counts[c("FAILED_NATIVE", "FAILED_RESOURCE", "UNATTEMPTED")])
      if (retryable == 0L) break
    }
    workers <- passes[[pass_name]]
    pass_slug <- tolower(pass_name)
    ledger <- file.path(execution_root, paste0("pass_", pass_slug, "_ledger.json"))
    log <- file.path(execution_root, paste0("pass_", pass_slug, ".log"))
    staging <- file.path(bank_root, "staging", paste0("pass_", pass_slug, "_", workers), attempt_id)
    args <- c(
      runner, "--plan-dir", plan_dir, "--pass-name", pass_name,
      "--workers", as.character(workers), "--staging-root", staging, "--ledger", ledger
    )
    if (!is.null(previous_ledger)) args <- c(args, "--retry-ledger", previous_ledger)
    runner_status <- NA_integer_
    runner_status <- system2(research_python_executable(), args, stdout = log, stderr = log)
    if (!file.exists(ledger)) stop("P4 tiered runner did not publish a ledger for Pass ", pass_name, call. = FALSE)
    value <- jsonlite::read_json(ledger, simplifyVector = FALSE)
    p4_assert_tiered_pass(value, runner_status, pass_name, log)
    ledgers <- c(ledgers, ledger)
    logs <- c(logs, log)
    previous_ledger <- ledger
  }
  if (is.null(previous_ledger)) stop("P4 tiered execution produced no pass ledger", call. = FALSE)
  final <- jsonlite::read_json(previous_ledger, simplifyVector = FALSE)
  expected_branch_ids <- vapply(plan, `[[`, character(1L), "branch_id")
  summary <- p4_summarize_tiered_execution(
    final, bank_id, plan[[1L]]$plan_id, ledgers, expected_branch_ids
  )
  states <- lapply(plan, p4_existing_bank_branch_state)
  invalid <- vapply(states, function(x) !identical(x$status, "VALID"), logical(1L))
  if (any(invalid)) {
    detail <- paste(vapply(states[invalid], function(x) paste0(x$branch_id, "=", x$status), character(1L)), collapse = ", ")
    stop("P4 tiered execution did not leave complete canonical branches: ", detail, call. = FALSE)
  }
  summary_path <- write_json_file(summary, file.path(execution_root, "tiered_execution_summary.json"))
  normalizePath(c(summary_path, ledgers, logs), mustWork = TRUE)
}
