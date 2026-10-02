test_that('B6 formal graph is isolated and sequential', {
  root <- if(file.exists('_targets_b6_stage_b_training.R')) '.' else '../..'
  text<-paste(readLines(file.path(root,'targets/b6_stage_b_training.R')),collapse='\n')
  expect_false(grepl('s09|s10|s11|s12',text))
  expect_match(text,'b6f_original')
  expect_match(text,'b6f_s50_g')
  expect_match(text,'b6f_s50_ppre')
  cfg<-yaml::read_yaml(file.path(root,'config/b6_stage_b_training.yml'))
  expect_identical(cfg$arms,c('B6-original','B6-S50-G','B6-S50-Ppre'))
  expect_equal(cfg$resources$world_size,2)
  expect_equal(cfg$resources$global_batch,32)
  expect_false(cfg$canonical_publication)
})
