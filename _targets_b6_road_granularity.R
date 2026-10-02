library(targets)
library(crew)
# Independent optimizer-free Stage A. Same registered CPU controller name as
# _targets.R; bounded scene workers x one thread, no canonical target imports.
Sys.setenv(OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",ARROW_NUM_THREADS="1")
data.table::setDTthreads(1L);arrow::set_cpu_count(1L)
b6_workers <- yaml::read_yaml("config/b6_road_granularity.yml")$resources$workers
stopifnot(b6_workers>=1,b6_workers<=40)
controller_05 <- crew_controller_local(name="controller_05",workers=as.integer(b6_workers))
tar_option_set(packages=c("sf","data.table","arrow","digest","jsonlite","yaml","igraph"),
  controller=controller_05,error="stop",memory="transient",garbage_collection=TRUE)
b6_cpu <- tar_resources(crew=tar_resources_crew(controller="controller_05"))
source("R/spatial_relations.R")
source("R/b6_road_segmentation.R")
source("R/b6_road_relations.R")
source("R/b6_stage_a.R")
source("R/b6_diagnostics.R")
source("targets/b6_road_granularity.R")
list_b6_stage_a
