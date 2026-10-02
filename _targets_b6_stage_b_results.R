library(targets)
library(crew)
controller_05<-crew_controller_local(name='controller_05',workers=1L)
tar_option_set(controller=controller_05,error='stop')
b6r_cpu<-tar_resources(crew=tar_resources_crew(controller='controller_05'))
source('R/b6_stage_b_results.R')
source('targets/b6_stage_b_results.R')$value
