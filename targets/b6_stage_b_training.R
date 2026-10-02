list(
  tar_target(b6f_source_files,b6f_sources(),format='file',resources=b6f_cpu),
  tar_target(b6f_contract,b6f_run('prepare',b6f_source_files),format='file',resources=b6f_cpu),
  tar_target(b6f_original,b6f_run('launch',list(b6f_source_files,b6f_contract),'B6-original'),format='file',resources=b6f_gpu),
  tar_target(b6f_s50_g,b6f_run('launch',list(b6f_source_files,b6f_contract,b6f_original),'B6-S50-G'),format='file',resources=b6f_gpu),
  tar_target(b6f_s50_ppre,b6f_run('launch',list(b6f_source_files,b6f_contract,b6f_s50_g),'B6-S50-Ppre'),format='file',resources=b6f_gpu),
  tar_target(b6f_comparison,b6f_run('summarize',list(b6f_source_files,b6f_original,b6f_s50_g,b6f_s50_ppre)),format='file',resources=b6f_cpu)
)
