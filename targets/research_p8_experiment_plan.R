list_research_p8_experiment_plan <- list(
  targets::tar_target(
    p8_experiment_plan_contract_files,
    p8_contract_files(), format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p8_experiment_plan_bundle,
    p8_build_bundle(p8_experiment_plan_contract_files),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    p8_methodology_compatibility,
    p8_bundle_artifact(p8_experiment_plan_bundle, "methodology_compatibility"),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    hyperparameter_configuration_matrix,
    p8_bundle_artifact(p8_experiment_plan_bundle, "hyperparameter_configuration_matrix", p8_methodology_compatibility),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    comparison_variant_template_matrix,
    p8_bundle_artifact(p8_experiment_plan_bundle, "comparison_variant_template_matrix", hyperparameter_configuration_matrix),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    experiment_augmentation_bank_index,
    p8_bundle_artifact(p8_experiment_plan_bundle, "experiment_augmentation_bank_index", comparison_variant_template_matrix),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    formal_hyperparameter_experiment_plan,
    p8_bundle_artifact(p8_experiment_plan_bundle, "formal_hyperparameter_experiment_plan", experiment_augmentation_bank_index),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    comparison_variant_materialization_template,
    p8_bundle_artifact(p8_experiment_plan_bundle, "comparison_variant_materialization_template", formal_hyperparameter_experiment_plan),
    format = "file", resources = controller_05_resources
  ),
  targets::tar_target(
    formal_experiment_plan_acceptance,
    p8_bundle_artifact(p8_experiment_plan_bundle, "formal_experiment_plan_acceptance", comparison_variant_materialization_template),
    format = "file", resources = controller_05_resources
  )
)
