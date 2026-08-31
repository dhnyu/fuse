list_p9_formal_execution_historical <- list(
  # Layer A: immutable accepted file bindings.
  targets::tar_target(p9x_runtime_config, p9x_runtime_config_path(), format = "file"),
  targets::tar_target(p9x_runtime_files, p9x_runtime_file_paths(), format = "file"),
  targets::tar_target(p9x_p7_acceptance, p9x_validate_root("p7_acceptance", p9x_runtime_config), format = "file"),
  targets::tar_target(p9x_p7_runtime_acceptance, p9x_validate_root("p7_runtime_acceptance", p9x_runtime_config), format = "file"),
  targets::tar_target(p9x_p8_acceptance, p9x_validate_root("p8_acceptance", p9x_runtime_config), format = "file"),
  targets::tar_target(p9x_p8_hyperparameter_matrix, p9x_validate_root("p8_hyperparameter_matrix", p9x_runtime_config), format = "file"),
  targets::tar_target(p9x_p8_bank_index, p9x_validate_root("p8_bank_index", p9x_runtime_config), format = "file"),
  targets::tar_target(p9x_p9_readiness, p9x_validate_root("p9_readiness", p9x_runtime_config), format = "file"),
  targets::tar_target(p9x_production_cache_acceptance, p9x_validate_root("production_cache_acceptance", p9x_runtime_config), format = "file"),
  targets::tar_target(p9x_categories, p9x_validate_root("categories", p9x_runtime_config), format = "file"),
  targets::tar_target(p9x_production_cache_manifests, p9x_validate_cache_manifests(p9x_runtime_config, p9x_production_cache_acceptance), format = "file"),

  # Layer B: isolated execution authorization publication.
  targets::tar_target(p9x_publication_config, p9x_publication_config_path(), format = "file"),
  targets::tar_target(p9x_production_startup_gate_evidence, p9x_startup_gate_evidence_path(p9x_publication_config), format = "file"),
  targets::tar_target(
    p9x_authorization_bundle,
    p9x_publish_authorization(
      p9x_runtime_files, p9x_publication_config,
      c(p9x_p7_acceptance, p9x_p7_runtime_acceptance, p9x_p8_acceptance,
        p9x_p8_hyperparameter_matrix, p9x_p8_bank_index, p9x_p9_readiness,
        p9x_production_cache_acceptance, p9x_categories),
      p9x_production_cache_manifests, p9x_production_startup_gate_evidence
    ),
    format = "file"
  ),
  targets::tar_target(p9x_immutable_root_inventory, p9x_bundle_artifact(p9x_authorization_bundle, "immutable_root_inventory.json"), format = "file"),
  targets::tar_target(p9x_formal_execution_supersession, p9x_bundle_artifact(p9x_authorization_bundle, "formal_execution_supersession.json"), format = "file"),
  targets::tar_target(p9x_formal_training_authority, p9x_bundle_artifact(p9x_authorization_bundle, "formal_training_authority.json", p9x_formal_execution_supersession), format = "file"),
  targets::tar_target(p9x_cfg_main_attempt_reservation, p9x_bundle_artifact(p9x_authorization_bundle, "cfg_main_attempt_reservation.json", p9x_formal_training_authority), format = "file"),
  targets::tar_target(p9x_cfg_main_preassigned_attempt, p9x_bundle_artifact(p9x_authorization_bundle, "cfg_main_preassigned_attempt.json", p9x_cfg_main_attempt_reservation), format = "file"),
  targets::tar_target(p9x_execution_authorization_acceptance, p9x_bundle_artifact(p9x_authorization_bundle, "execution_authorization_acceptance.json", p9x_cfg_main_preassigned_attempt), format = "file"),

  # Layer C: formal execution. Never selected during reauthorization.
  targets::tar_target(
    p9_cfg_main_formal_run,
    p9x_execute_formal_run(
      p9x_formal_training_authority, p9x_cfg_main_attempt_reservation,
      p9x_execution_authorization_acceptance, p9x_p8_hyperparameter_matrix,
      p9x_production_cache_acceptance, p9x_production_cache_manifests,
      p9x_categories, p9x_runtime_files
    ),
    format = "file"
  ),
  targets::tar_target(p9_cfg_main_validation_trace, p9x_run_artifact(p9_cfg_main_formal_run, "validation_trace.json"), format = "file"),
  targets::tar_target(p9_cfg_main_checkpoint_candidates, p9x_run_artifact(p9_cfg_main_formal_run, "checkpoint_candidate_index.json", p9_cfg_main_validation_trace), format = "file"),
  targets::tar_target(p9_cfg_main_selected_checkpoint, p9x_run_artifact(p9_cfg_main_formal_run, "selected_checkpoint.json", p9_cfg_main_checkpoint_candidates), format = "file"),
  targets::tar_target(p9_cfg_main_terminal_execution, p9x_run_artifact(p9_cfg_main_formal_run, "terminal_execution_record.json", p9_cfg_main_selected_checkpoint), format = "file"),
  targets::tar_target(p9_cfg_main_attempt_acceptance, p9x_run_artifact(p9_cfg_main_formal_run, "cfg_main_attempt_acceptance.json", p9_cfg_main_terminal_execution), format = "file")
)

list_p9_formal_execution <- list(
  targets::tar_target(
    p9_v1_formal_execution_retired,
    p9_v1_retired_stop("_targets_p9_formal.R")
  )
)
