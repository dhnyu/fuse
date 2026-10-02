# Every file target returns its receipt AND all checksummed payloads.
# Dynamic branches are P3 shards or <=32 queries; CPU05 is one worker/thread.
list_s11_representation <- list(
  tar_target(s11_representation_sources, s11_representation_source_paths(), format = "file", resources = s11_cpu),
  tar_target(s11_accepted_parents, {s11_representation_sources; s11_stage("parents")}, format = "file", resources = s11_cpu),
  tar_target(s11_descriptor_plan, s11_stage("descriptor_plan", list(parent = s11_manifest(s11_accepted_parents))), format = "file", resources = s11_cpu),
  tar_target(s11_descriptor_specs, s11_specs(s11_descriptor_plan, "shards"), iteration = "list", resources = s11_cpu),
  tar_target(s11_descriptor_shards, s11_stage("descriptor_shard", list(plan = s11_manifest(s11_descriptor_plan), spec = s11_descriptor_specs)),
             pattern = map(s11_descriptor_specs), format = "file", iteration = "list", resources = s11_cpu),
  tar_target(s11_descriptor_acceptance, s11_stage("descriptor_acceptance", list(plan = s11_manifest(s11_descriptor_plan),
             shards = I(s11_branch_manifests(s11_descriptor_shards)))), format = "file", resources = s11_cpu),
  tar_target(s11_umap, s11_stage("umap", list(parent = s11_manifest(s11_accepted_parents))), format = "file", resources = s11_cpu),
  tar_target(s11_alignment_plan, s11_stage("alignment_plan", list(parent = s11_manifest(s11_accepted_parents),
             descriptors = s11_manifest(s11_descriptor_acceptance))), format = "file", resources = s11_cpu),
  tar_target(s11_alignment_specs, s11_specs(s11_alignment_plan, "blocks"), iteration = "list", resources = s11_cpu),
  tar_target(s11_alignment_blocks, s11_stage("alignment_block", list(parent = s11_manifest(s11_accepted_parents),
             descriptors = s11_manifest(s11_descriptor_acceptance), plan = s11_manifest(s11_alignment_plan), spec = s11_alignment_specs)),
             pattern = map(s11_alignment_specs), format = "file", iteration = "list", resources = s11_cpu),
  tar_target(s11_alignment_summaries, s11_stage("summaries", list(parent = s11_manifest(s11_accepted_parents),
             plan = s11_manifest(s11_alignment_plan), blocks = I(s11_branch_manifests(s11_alignment_blocks)))), format = "file", resources = s11_cpu),
  tar_target(s11_figures_tables, s11_stage("publication", list(descriptors = s11_manifest(s11_descriptor_acceptance),
             umap = s11_manifest(s11_umap), summaries = s11_manifest(s11_alignment_summaries))), format = "file", resources = s11_cpu),
  tar_target(s11_scientific_acceptance, s11_stage("acceptance", list(parent = s11_manifest(s11_accepted_parents),
             descriptors = s11_manifest(s11_descriptor_acceptance), umap = s11_manifest(s11_umap), plan = s11_manifest(s11_alignment_plan),
             blocks = I(s11_branch_manifests(s11_alignment_blocks)), summaries = s11_manifest(s11_alignment_summaries),
             publication = s11_manifest(s11_figures_tables))), format = "file", resources = s11_cpu)
)
