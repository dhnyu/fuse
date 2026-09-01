list_p9_v2_training <- list(
  targets::tar_target(
    p9v2_training_contract,
    p9v2_training_contract_path(),
    format = "file"
  ),
  targets::tar_target(
    p9v2_training_authority,
    p9v2_training_authority_path(),
    format = "file"
  ),
  targets::tar_target(
    p9v2_startup_preflight,
    p9v2_controller_preflight(p9v2_training_authority, p9v2_training_contract),
    format = "file"
  ),
  targets::tar_target(
    p9v2_closed_ledger,
    p9v2_controller_run(p9v2_training_authority, p9v2_training_contract, p9v2_startup_preflight),
    format = "file"
  ),
  targets::tar_target(
    p9v2_run_bundle,
    p9v2_bundle(p9v2_closed_ledger, p9v2_training_authority, p9v2_training_contract),
    format = "file"
  ),
  targets::tar_target(
    p9v2_finalization_result,
    p9v2_finalize(p9v2_run_bundle, p9v2_training_authority, p9v2_training_contract),
    format = "file"
  ),
  targets::tar_target(
    p9v2_acceptance_commit,
    p9v2_accept(p9v2_finalization_result, p9v2_training_authority, p9v2_training_contract),
    format = "file"
  ),
  targets::tar_target(
    p9v2_eligibility_snapshot,
    p9v2_eligibility(p9v2_acceptance_commit, p9v2_training_authority, p9v2_training_contract),
    format = "file"
  ),
  targets::tar_target(
    p9v2_accepted_checkpoint,
    p9v2_resolve_accepted_checkpoint(p9v2_eligibility_snapshot, p9v2_training_authority, p9v2_training_contract),
    format = "file"
  )
)
