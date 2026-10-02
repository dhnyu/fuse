# Dissertation spatial relations / augmentation / training; experimental B6 only.
b6c_sources <- function() c(b6b_sources(),
  'python/b6_con_lift.py','python/b6_con_census.py','python/b6_segmented_inputs.py',
  'python/b6_s50_cache.py','python/b6_bounded_pilot.py','config/b6_con_execution.yml','config/b6_con_lift.yml','config/schemas/b6_con_lift.schema.json',
  'R/b6_con_gpu_pilot.R','targets/b6_con_gpu_pilot.R','_targets_b6_con_gpu_pilot.R',
  'python/scene_encoder.py','python/training_worker.py','python/training_geometry_cache.py',
  'python/training_transport.py','python/training_runtime_inputs.py')
b6c_run <- function(action, dependencies=NULL) {
  stopifnot(action %in% c('census','cache','gpu'))
  if(!is.null(dependencies)) stopifnot(all(file.exists(unlist(dependencies))))
  Sys.setenv(PYTHONPATH=normalizePath('python'),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
  execution<-yaml::read_yaml('config/b6_con_execution.yml')
  stopifnot(execution$threads_per_worker==1L,execution$gpu_world_size==2L,
    execution$census_workers>=1L,execution$cache_workers>=1L,execution$cache_workers<=40L,
    max(execution$census_workers,execution$cache_workers)*execution$threads_per_worker<=execution$cpu_budget)
  args<-switch(action,census=c('python/b6_con_census.py','--workers',as.character(execution$census_workers)),
    cache=c('python/b6_s50_cache.py','--workers',as.character(execution$cache_workers)),gpu=c('python/b6_bounded_pilot.py','launch'))
  out<-system2('python',args,stdout=TRUE,stderr=TRUE)
  if(!is.null(attr(out,'status')) && attr(out,'status')!=0) stop(paste(out,collapse='\n'))
  root<-tail(out,1)
  stopifnot(startsWith(root,'/mnt/hdd002/dhnyu/fusedata/experiments/b6_'),dir.exists(root))
  receipt<-file.path(root,if(action=='census') 'census.json' else 'acceptance.json')
  value<-jsonlite::read_json(receipt,simplifyVector=TRUE)
  stopifnot(if(action=='census') value$verdict=='PASS' else if(action=='cache') value$status=='PASS' else value$verdict=='READY_FOR_STAGE_B_TRAINING_AUTHORIZATION')
  result<-c(receipt,file.path(root,'manifest.json'))
  stopifnot(all(file.exists(result)));result
}
