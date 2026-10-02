# Reporting-only numerical reduction correction; no training reachable.
b6r_run <- function(dependencies) {
  stopifnot(all(file.exists(dependencies)))
  Sys.setenv(PYTHONPATH=normalizePath('python'),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
  out<-system2('python','scripts/b6_stage_b_results.py',stdout=TRUE,stderr=TRUE)
  if(!is.null(attr(out,'status')) && attr(out,'status')!=0)stop(paste(out,collapse='\n'))
  path<-tail(out,1);stopifnot(file.exists(path),grepl('/b6formal_[a-f0-9]+/final_audit/manifest.json$',path))
  path
}
