full_membership_authorization_contract_path <- function(root = getwd()) {
  file.path(root, "config/full_membership_authorization.yml")
}

validate_full_membership_i24_authorization <- function(contract_path) {
  path <- normalizePath(contract_path, mustWork = TRUE)
  contract <- yaml::read_yaml(path)
  artifact <- normalizePath(contract$artifact$path, mustWork = TRUE)
  value <- jsonlite::read_json(artifact, simplifyVector = FALSE)
  if (!identical(contract$schema_version, "1.0.0") ||
      !identical(contract$identity_role, "execution_authorization_only") ||
      !isTRUE(contract$excluded_from_spatial_identity) ||
      !identical(value$model_acceptance_id, contract$artifact$model_acceptance_id) ||
      !identical(value$status, "PASS") ||
      !identical(unname(file.info(artifact)$size), as.numeric(contract$artifact$size_bytes)) ||
      !identical(sha256_file(artifact), contract$artifact$sha256)) {
    stop("C01 I24 authorization contract or artifact mismatch", call. = FALSE)
  }
  artifact
}
