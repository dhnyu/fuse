list_p9_v2_training <- list(
  targets::tar_target(
    p9v2_training_contract,
    "config/p9_v2_training_controller.yml",
    format = "file"
  ),
  targets::tar_target(
    p9v2_training_authority,
    p9v2_training_authority_path(),
    format = "file"
  ),
  targets::tar_target(
    p9v2_closed_ledger,
    p9v2_controller_run(p9v2_training_authority, p9v2_training_contract),
    format = "file"
  ),
  targets::tar_target(
    p9v2_run_bundle,
    p9v2_declared_artifact("P9_V2_RUN_BUNDLE_MANIFEST", p9v2_closed_ledger),
    format = "file"
  ),
  targets::tar_target(
    p9v2_finalization_result,
    p9v2_declared_artifact("P9_V2_FINALIZATION_RESULT", p9v2_run_bundle),
    format = "file"
  ),
  targets::tar_target(
    p9v2_acceptance_commit,
    p9v2_declared_artifact("P9_V2_ACCEPTANCE_COMMIT", p9v2_finalization_result),
    format = "file"
  ),
  targets::tar_target(
    p9v2_eligibility_snapshot,
    p9v2_declared_artifact("P9_V2_ELIGIBILITY_SNAPSHOT", p9v2_acceptance_commit),
    format = "file"
  ),
  targets::tar_target(
    p9v2_accepted_checkpoint,
    p9v2_resolve_accepted_checkpoint(p9v2_eligibility_snapshot),
    format = "file"
  )
)
