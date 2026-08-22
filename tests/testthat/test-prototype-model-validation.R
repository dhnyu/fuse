test_that("I23 contract separates qualitative and quantitative retrieval", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/prototype_model_validation.yml"))
  expect_identical(config$identity$training_acceptance_id, "pta_cf6bc4679a06305fb1185a8e")
  expect_identical(config$scientific$inference$output, "pre_projection_scene_embedding")
  expect_identical(config$scientific$inference$augmentation, "forbidden")
  expect_identical(config$scientific$original_retrieval$candidate_count, 319L)
  expect_identical(config$scientific$original_retrieval$relevance_ground_truth, "absent")
  expect_identical(config$scientific$original_retrieval$relevance_metrics, "forbidden")
  expect_identical(config$scientific$augmented_source_retrieval$candidate_count, 320L)
  expect_identical(config$scientific$augmented_source_retrieval$unique_relevant_candidate,
                   "unaugmented_source_scene")
  expect_identical(unlist(config$scientific$augmented_source_retrieval$metrics),
                   c("MRR", "HIT@1", "HIT@5", "HIT@10"))
  expect_identical(config$scientific$checkpoint_validation$mutation, "forbidden")
  expect_identical(config$scientific$checkpoint_validation$additional_optimizer_steps, 0L)
})

test_that("I23 target has only accepted scientific parents and no I24", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  command <- manifest$command[manifest$name == "prototype_model_validation"]
  expect_length(command, 1L)
  expect_match(command, "prototype_training_acceptance")
  expect_match(command, "prototype_training_dataset_acceptance")
  expect_match(command, "prototype_scene_selection")
  expect_false("prototype_model_acceptance" %in% manifest$name)
})
