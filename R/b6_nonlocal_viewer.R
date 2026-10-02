# Dissertation retrieval; experimental B6 output only, no canonical S10 execution.
b6n_run <- function(action, dependencies=NULL, contract=NULL) {
  if(!is.null(dependencies)) stopifnot(all(file.exists(unlist(dependencies))))
  Sys.setenv(PYTHONPATH=normalizePath('python'),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
  args<-c('python/b6_nonlocal_viewer.py',action)
  if(!is.null(contract)) args<-c(args,'--contract',contract)
  out<-system2('/members/dhnyu/.conda/envs/rgeo/bin/python',args,stdout=TRUE,stderr=TRUE)
  if(!is.null(attr(out,'status')) && attr(out,'status')!=0) stop(paste(out,collapse='\n'))
  path<-tail(out,1);stopifnot(file.exists(path),startsWith(path,'/mnt/hdd002/dhnyu/fusedata/experiments/b6_nonlocal_retrieval_viewer/'))
  path
}
