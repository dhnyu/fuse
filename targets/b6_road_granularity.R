# Fixed stage directories and payload names are documented in the B6 design report.
# Only the dedicated store/operator may execute these targets.
list_b6_stage_a <- list(
  tar_target(b6_sources,b6_source_paths(),format="file",resources=b6_cpu),
  tar_target(b6_configuration,b6_config(b6_sources),resources=b6_cpu),
  tar_target(b6_parents,b6_parent_check(b6_configuration),format="file",resources=b6_cpu),
  tar_target(b6_pilot,b6_sampling(b6_configuration,b6_parents),format="file",resources=b6_cpu),
  tar_target(b6_stress_set,b6_stress(b6_configuration,b6_parents,b6_pilot),format="file",resources=b6_cpu),
  tar_target(b6_inputs,b6_extract(b6_configuration,b6_parents,b6_pilot,b6_stress_set),format="file",resources=b6_cpu),
  tar_target(b6_scene_jobs,b6_jobs(b6_inputs),iteration="list",resources=b6_cpu),
  tar_target(b6_parity_scene,b6_parity_one(b6_configuration,b6_scene_jobs),pattern=map(b6_scene_jobs),iteration="list",format="file",resources=b6_cpu),
  tar_target(b6_parity,b6_parity_aggregate(b6_configuration,b6_parity_scene,b6_scene_jobs),format="file",resources=b6_cpu),
  tar_target(b6_scene_diagnostics,b6_diagnostic_one(b6_configuration,b6_scene_jobs,b6_parity),pattern=map(b6_scene_jobs),iteration="list",format="file",resources=b6_cpu),
  tar_target(b6_structural_summary,b6_diagnostics_collect(b6_configuration,b6_scene_diagnostics,b6_scene_jobs),format="file",resources=b6_cpu),
  tar_target(b6_coverage_audit,b6_coverage(b6_configuration,b6_parents),format="file",resources=b6_cpu),
  tar_target(b6_topology,b6_topology_audit(b6_configuration,b6_inputs),format="file",resources=b6_cpu),
  tar_target(b6_existing_artifacts,b6_artifact_audit(b6_configuration,b6_pilot,b6_topology),format="file",resources=b6_cpu),
  tar_target(b6_stage_a_acceptance,b6_acceptance(b6_configuration,b6_parents,b6_inputs,b6_parity,b6_structural_summary,b6_coverage_audit,b6_existing_artifacts,b6_topology),format="file",resources=b6_cpu)
)
