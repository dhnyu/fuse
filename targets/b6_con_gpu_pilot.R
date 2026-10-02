list(
  tar_target(b6c_source_files,b6c_sources(),format='file',resources=b6c_cpu),
  tar_target(b6c_con_census,b6c_run('census',b6c_source_files),format='file',resources=b6c_cpu),
  tar_target(b6c_s50_cache,b6c_run('cache',list(b6c_con_census,b6c_source_files)),format='file',resources=b6c_cpu),
  tar_target(b6c_bounded_updates,b6c_run('gpu',list(b6c_s50_cache,b6c_source_files)),format='file',resources=b6c_gpu)
)
