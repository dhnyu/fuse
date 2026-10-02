library(targets)
library(crew)
# One orchestration worker; the bounded lineage census uses configured processes.
Sys.setenv(OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
controller_05<-crew_controller_local(name="controller_05",workers=1L)
tar_option_set(packages=c("yaml"),controller=controller_05,error="stop")
b6b_cpu<-tar_resources(crew=tar_resources_crew(controller="controller_05"))
source("R/b6_stage_b_preparation.R")
source("targets/b6_stage_b_preparation.R")$value
