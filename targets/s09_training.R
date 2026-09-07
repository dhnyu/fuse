list_s09_training <- list(
  targets::tar_target(
    s09_training_contract,
    s09_training_contract_path(),
    format = "file"
  ),
  targets::tar_target(
    s09_training_authority,
    s09_training_authority_path(),
    format = "file"
  ),
  targets::tar_target(
    s09_startup_preflight,
    s09_controller_preflight(s09_training_authority, s09_training_contract),
    format = "file"
  ),
  targets::tar_target(
    s09_closed_ledger,
    s09_controller_run(s09_training_authority, s09_training_contract, s09_startup_preflight),
    format = "file"
  ),
  targets::tar_target(
    s09_run_bundle,
    s09_bundle(s09_closed_ledger, s09_training_authority, s09_training_contract),
    format = "file"
  ),
  targets::tar_target(
    s09_finalization_result,
    s09_finalize(s09_run_bundle, s09_training_authority, s09_training_contract),
    format = "file"
  ),
  targets::tar_target(
    s09_acceptance_commit,
    s09_accept(s09_finalization_result, s09_training_authority, s09_training_contract),
    format = "file"
  ),
  targets::tar_target(
    s09_eligibility_snapshot,
    s09_eligibility(s09_acceptance_commit, s09_training_authority, s09_training_contract),
    format = "file"
  ),
  targets::tar_target(
    s09_accepted_checkpoint,
    s09_resolve_accepted_checkpoint(s09_eligibility_snapshot, s09_training_authority, s09_training_contract),
    format = "file"
  )
)
