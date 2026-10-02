# Every file target returns its immutable manifest and all checksummed payloads.
# No training, inference, P3 or FM numerical producer appears in this graph.
list_s12_representation <- list(
  tar_target(s12_sources, s12_source_paths(), format = "file", resources = s12_cpu),
  tar_target(s12_accepted_inputs, {s12_sources; s12_stage("parents")}, format = "file", resources = s12_cpu),
  tar_target(s12_shared_descriptors, s12_stage("shared", list(accepted = s12_manifest(s12_accepted_inputs))), format = "file", resources = s12_cpu),
  tar_target(s12_model_block_plan, s12_stage("plan", list(accepted = s12_manifest(s12_accepted_inputs), shared = s12_manifest(s12_shared_descriptors))), format = "file", resources = s12_cpu),
  tar_target(s12_model_specs, s12_specs(s12_model_block_plan, "models"), iteration = "list", resources = s12_cpu),
  tar_target(s12_block_specs, s12_specs(s12_model_block_plan, "blocks"), iteration = "list", resources = s12_cpu),
  tar_target(s12_alignment_blocks, s12_stage("block", list(plan = s12_manifest(s12_model_block_plan), shared = s12_manifest(s12_shared_descriptors), spec = s12_block_specs)),
    pattern = map(s12_block_specs), format = "file", iteration = "list", resources = s12_cpu),
  tar_target(s12_model_summaries, s12_stage("summary", list(model = s12_model_specs, plan = s12_manifest(s12_model_block_plan), blocks = I(s12_manifests(s12_alignment_blocks)))),
    pattern = map(s12_model_specs), format = "file", iteration = "list", resources = s12_cpu),
  tar_target(s12_model_acceptance, s12_stage("model_acceptance", list(model = s12_model_specs, summary = s12_manifest(s12_model_summaries))),
    pattern = map(s12_model_specs, s12_model_summaries), format = "file", iteration = "list", resources = s12_cpu),
  tar_target(s12_cross_model_tables, s12_stage("tables", list(acceptances = I(s12_manifests(s12_model_acceptance)))), format = "file", resources = s12_cpu),
  tar_target(s12_comparison_figures, s12_stage("figures", list(tables = s12_manifest(s12_cross_model_tables))), format = "file", resources = s12_cpu),
  tar_target(s12_scientific_acceptance, s12_stage("acceptance", list(acceptances = I(s12_manifests(s12_model_acceptance)), tables = s12_manifest(s12_cross_model_tables), figures = s12_manifest(s12_comparison_figures))), format = "file", resources = s12_cpu)
)
