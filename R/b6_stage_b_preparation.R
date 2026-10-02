# Post-bank methodology/lineage gates only; dissertation augmentation order.
b6b_sources <- function() c("python/b6_postbank_adapter.py",
  "python/b6_stage_b_preparation.py",
  "config/b6_stage_b_preparation.yml",
  "config/schemas/b6_stage_b_preparation.schema.json",
  "R/b6_stage_b_preparation.R",
  "targets/b6_stage_b_preparation.R",
  "_targets_b6_stage_b_preparation.R",
  "config/training_controller.yml",
  "python/augmentation_rng.py",
  "python/training_prepared_cache.py",
  "python/training_support.py",
  "python/model_families.py",
  "python/current_methodology.py",
  "python/canonical_config.py",
  "python/augmentation_bank.py",
  "python/model_data.py",
  "python/training_family_inputs.py",
  "python/training_configuration.py",
  "python/training_finalization.py",
  "config/training.yml",
  "config/model_inputs.yml",
  "config/p4_deterministic_augmentation.yml",
  "config/p5_deterministic_queries.yml")
b6b_run <- function(action,dependencies=NULL) {
  stopifnot(action%in%c("contract","inventory","lineage","parity","readiness"))
  if(!is.null(dependencies)) stopifnot(all(file.exists(unlist(dependencies))))
  cfg<-yaml::read_yaml("config/b6_stage_b_preparation.yml")
  Sys.setenv(PYTHONPATH=normalizePath("python"),PYTHONDONTWRITEBYTECODE="1",OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
  out<-system2("python",c("python/b6_stage_b_preparation.py",action,"--workers",as.character(cfg$resources$workers)),stdout=TRUE,stderr=TRUE)
  if(!is.null(attr(out,"status")) && attr(out,"status")!=0) stop(paste(c("B6 Stage B gate execution failed",out),collapse="\n"))
  root<-tail(out,1);stopifnot(startsWith(root,paste0(cfg$output_root,"/b6b_")),dir.exists(root))
  files<-list.files(root,full.names=TRUE);stopifnot(any(basename(files)=="manifest.json"),all(file.exists(files)))
  files
}
