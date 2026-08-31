list_p9_checkpoint_recovery_historical <- list(
  targets::tar_target(p9_recovery_authorization_bundle, p9r_publish_recovery_authorization(), format = "file"),
  targets::tar_target(p9_recovery_contract, p9r_artifact(p9_recovery_authorization_bundle, "recovery_contract.json"), format = "file"),
  targets::tar_target(p9_recovery_authority, p9r_artifact(p9_recovery_authorization_bundle, "recovery_authority.json"), format = "file"),
  targets::tar_target(p9_recovery_reservation, p9r_artifact(p9_recovery_authorization_bundle, "recovery_reservation.json"), format = "file"),
  targets::tar_target(p9_recovery_operation, p9r_artifact(p9_recovery_authorization_bundle, "recovery_operation.json"), format = "file"),
  targets::tar_target(p9_recovery_authorization_acceptance, p9r_artifact(p9_recovery_authorization_bundle, "recovery_authorization_acceptance.json"), format = "file"),
  targets::tar_target(p9_cfg_main_recovery_checkpoint_join, p9r_readonly_join(p9_recovery_contract)),
  targets::tar_target(p9_cfg_main_recovery_selected_checkpoint, p9r_selected_checkpoint(p9_cfg_main_recovery_checkpoint_join)),
  targets::tar_target(p9_cfg_main_recovery_stopping_boundary, p9r_early_stopping(p9_recovery_contract, p9_cfg_main_recovery_selected_checkpoint)),
  targets::tar_target(p9_cfg_main_terminal_recovery, p9r_execute_terminal(p9_recovery_authorization_bundle, p9_cfg_main_recovery_selected_checkpoint, p9_cfg_main_recovery_stopping_boundary), format = "file"),
  targets::tar_target(p9_cfg_main_recovery_acceptance, p9r_artifact(p9_cfg_main_terminal_recovery, "recovery_acceptance.json"), format = "file")
)

list_p9_checkpoint_recovery <- list(
  targets::tar_target(
    p9_v1_recovery_execution_retired,
    p9_v1_retired_stop("_targets_p9_recovery.R")
  )
)
