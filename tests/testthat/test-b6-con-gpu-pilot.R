withr::local_dir(normalizePath('../..'))
source('R/b6_stage_b_preparation.R');source('R/b6_con_gpu_pilot.R')
testthat::test_that('isolated graph gates bounded GPU updates on full CPU acceptance',{
  script<-'_targets_b6_con_gpu_pilot.R'
  m<-targets::tar_manifest(script=script);testthat::expect_length(m$name,4)
  g<-targets::tar_network(script=script)
  testthat::expect_true(igraph::is_dag(igraph::graph_from_data_frame(g$edges)))
  testthat::expect_true(all(startsWith(m$name,'b6c_')))
  testthat::expect_setequal(g$edges$to[g$edges$from=='b6c_source_files'],c('b6c_con_census','b6c_s50_cache','b6c_bounded_updates'))
  testthat::expect_error(b6c_run('full_training'),'not TRUE')
  targets::tar_validate(script=script)
})
