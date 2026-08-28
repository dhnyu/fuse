test_that("accepted P1-P3 references preserve exact immutable identities", {
  config <- accepted_parent_config_path(fuse_test_root)
  p1 <- accepted_p1_scene_index_files(config)
  p2 <- accepted_p2_base_spatial_files(config)
  p3_files <- accepted_p3_shard_files(config)
  p3_groups <- accepted_p3_shard_groups(p3_files, config)
  p3_index <- accepted_p3_index_files(config)
  p3_acceptance <- accepted_p3_acceptance_files(config)

  expect_length(p1, 2L)
  expect_length(p2, 6L)
  expect_length(p3_files, 288L)
  expect_length(p3_groups, 96L)
  expect_true(all(vapply(p3_groups, length, integer(1L)) == 3L))
  expect_length(p3_index, 2L)
  expect_length(p3_acceptance, 1L)
})

test_that("revised downstream targets use references instead of rebuilding P1-P3", {
  files <- c(
    "targets/research_fixed_augmentation_banks.R",
    "targets/research_fixed_queries.R",
    "targets/research_model_dataloader.R"
  )
  text <- paste(vapply(file.path(fuse_test_root, files), function(path) {
    paste(readLines(path, warn = FALSE), collapse = "\n")
  }, character(1L)), collapse = "\n")
  expect_match(text, "accepted_p3_dataset_acceptance_reference", fixed = TRUE)
  expect_match(text, "accepted_p3_shard_reference", fixed = TRUE)
  expect_match(text, "accepted_p2_base_spatial_reference", fixed = TRUE)
})
