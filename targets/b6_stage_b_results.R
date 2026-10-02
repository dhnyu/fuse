list(
  tar_target(b6r_source_files,c('scripts/b6_stage_b_results.py','R/b6_stage_b_results.R','targets/b6_stage_b_results.R','_targets_b6_stage_b_results.R'),format='file',resources=b6r_cpu),
  tar_target(b6r_acceptance,b6r_run(b6r_source_files),format='file',resources=b6r_cpu)
)
