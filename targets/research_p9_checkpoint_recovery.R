list_p9_checkpoint_recovery <- list(
  targets::tar_target(p9_recovery_authorization_bundle, p9r_publish_recovery_authorization(), format = "file"),
  targets::tar_target(p9_recovery_contract, p9r_artifact(p9_recovery_authorization_bundle, "recovery_contract.json"), format = "file"),
  targets::tar_target(p9_recovery_authority, p9r_artifact(p9_recovery_authorization_bundle, "recovery_authority.json"), format = "file"),
  targets::tar_target(p9_recovery_reservation, p9r_artifact(p9_recovery_authorization_bundle, "recovery_reservation.json"), format = "file"),
  targets::tar_target(p9_recovery_operation, p9r_artifact(p9_recovery_authorization_bundle, "recovery_operation.json"), format = "file"),
  targets::tar_target(p9_recovery_authorization_acceptance, p9r_artifact(p9_recovery_authorization_bundle, "recovery_authorization_acceptance.json"), format = "file")
)
