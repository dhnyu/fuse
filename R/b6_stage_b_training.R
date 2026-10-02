# Dissertation training/selection; isolated B6 formal authority and GPU pair lock.
b6f_sources <- function() c(list.files('python',pattern='[.]py$',full.names=TRUE),
  list.files('config',pattern='[.]yml$',recursive=TRUE,full.names=TRUE),
  list.files('config/schemas',pattern='[.]json$',full.names=TRUE),
  'R/scene_descriptors.R','R/b6_validation_descriptors.R','R/b6_stage_b_training.R','targets/b6_stage_b_training.R','_targets_b6_stage_b_training.R')
b6f_run <- function(action, dependencies=NULL, arm=NULL) {
  stopifnot(action %in% c('prepare','launch','summarize'))
  if(!is.null(dependencies)) stopifnot(all(file.exists(unlist(dependencies))))
  Sys.setenv(PYTHONPATH=normalizePath('python'),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
  args<-c('python/b6_formal_training.py',action)
  if(!is.null(arm)) args<-c(args,'--arm',arm)
  out<-system2('python',args,stdout=TRUE,stderr=TRUE)
  if(!is.null(attr(out,'status')) && attr(out,'status')!=0) stop(paste(out,collapse='\n'))
  path<-tail(out,1)
  stopifnot(startsWith(path,'/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b_training/b6formal_'),file.exists(path))
  path
}
