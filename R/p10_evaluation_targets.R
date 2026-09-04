# P10 is a closed, evaluation-only target graph. Scientific execution lives in Python.
p10_build_prepared_input <- function(contract) {
  command <- c("scripts/p10_prepared_input.py", "build", "--contract", contract)
  status <- system2("python", command, stdout = TRUE, stderr = TRUE)
  code <- attr(status, "status")
  if (is.null(code)) code <- 0L
  if (!identical(code, 0L)) stop(paste(status, collapse = "\n"), call. = FALSE)
  path <- tail(status, 1)
  if (!file.exists(path)) stop("P10 prepared input manifest was not committed", call. = FALSE)
  path
}

p10_build_prepared_geometry <- function(contract, prepared_input) {
  stopifnot(file.exists(prepared_input))
  command <- c("scripts/p10_prepared_input.py", "build-geometry", "--contract", contract,
               "--input-manifest", prepared_input)
  status <- system2("python", command, stdout = TRUE, stderr = TRUE)
  code <- attr(status, "status")
  if (is.null(code)) code <- 0L
  if (!identical(code, 0L)) stop(paste(status, collapse = "\n"), call. = FALSE)
  path <- tail(status, 1)
  if (!file.exists(path)) stop("P10 prepared geometry manifest was not committed", call. = FALSE)
  path
}

p10_run_evaluation <- function(contract, prepared_input, prepared_geometry) {
  stopifnot(file.exists(prepared_input))
  stopifnot(file.exists(prepared_geometry))
  command <- c("scripts/p10_evaluation.py", "--contract", contract, "--reexecute")
  status <- system2("python", command, stdout = TRUE, stderr = TRUE)
  code <- attr(status, "status")
  if (is.null(code)) code <- 0L
  if (!identical(code, 0L)) stop(paste(status, collapse = "\n"), call. = FALSE)
  value <- jsonlite::fromJSON(tail(status, 1), simplifyVector = FALSE)
  path <- file.path(value$result_root, "commit", "evaluation_acceptance.json")
  if (!file.exists(path)) stop("P10 acceptance was not committed", call. = FALSE)
  path
}

p10_acceptance_readback <- function(path) {
  value <- jsonlite::read_json(path, simplifyVector = FALSE)
  stopifnot(identical(value$status, "PASS"), identical(value$artifact_type, "p10_evaluation_acceptance"))
  path
}
