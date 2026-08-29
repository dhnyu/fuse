test_that("I20 scientific training contract is complete and fixed", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/training_plan.yml"))
  expect_equal(config$identity$accepted_dataset_id, "ptd_bcb9e6a1061ff7ca9c716b20")
  expect_equal(config$identity$encoder_acceptance_id, "pea_1c66760dbc1e6c0a8d71cb91")
  expect_equal(config$identity$joint_model_acceptance_id, "pjm_6e64c022281a7f2648f78917")
  expect_equal(config$identity$distributed_joint_acceptance_id, "pjd_69c0bd35dac8add3280d72e2")
  expect_equal(config$identity$augmentation_acceptance_id, "paa_5d2b1f56119e8d5f5050a75d")
  expect_equal(config$data$effective_batch_scenes, 32)
  expect_equal(config$optimization$optimizer, "AdamW")
  expect_equal(config$optimization$learning_rate, 3e-4)
  expect_equal(config$optimization$weight_decay, 1e-4)
  expect_equal(config$optimization$maximum_epochs, 200)
  expect_equal(config$optimization$warmup_epochs, 10)
  expect_equal(config$optimization$gradient_norm_clip, 1.0)
  expect_equal(config$optimization$ema_momentum, 0.999)
  expect_equal(config$optimization$queue_size, 8192)
  expect_equal(config$optimization$temperature, 0.1)
  expect_equal(config$optimization$geographic_negative_exclusion_radius_m, 750)
  expect_equal(config$validation$primary_metric, "MRR")
  expect_equal(config$validation$early_stopping_patience_evaluations, 10)
  expect_identical(config$validation$ties_do_not_reset_patience, FALSE)
  expect_equal(config$validation$checkpoint_selection,
               "highest_MRR_then_lowest_validation_retrieval_loss_then_highest_mean_positive_hardest_negative_margin_then_earliest_epoch")
  expect_equal(config$validation$retrieval_loss$temperature, 0.1)
  expect_equal(config$validation$retrieval_loss_min_delta, 1e-4)
  expect_equal(config$validation$floating_point_tolerance, 1e-12)
  expect_equal(config$validation$patience_reset, "higher_MRR_or_saturated_retrieval_loss_min_delta")
  expect_equal(config$validation$evaluation_and_test_for_selection, "forbidden")
  expect_equal(config$optimization$optimizer_steps_per_epoch, 8)
  expect_equal(config$execution$dataloader_workers, 40)
  expect_equal(config$execution$workers_per_rank, 20)
  expect_equal(config$runs$execution_mode, "two_process_ddp")
  expect_true(all(c("optimizer", "scheduler", "ema", "queue_values", "queue_pointer",
                    "numpy_rng", "torch_cuda_rng", "sampler_position", "accumulation_gradient_state") %in%
                  unlist(config$resume$required_state)))
})

test_that("I20 scientific identity uses the augmentation YAML", {
  source_lines <- readLines(file.path(fuse_test_root, "R/research_training_plan.R"), warn = FALSE)
  assignment <- source_lines[grepl("augmentation_scientific <-", source_lines, fixed = TRUE)]
  expect_length(assignment, 1L)
  expect_match(assignment, "augmentation_config\\[c\\(")
})

test_that("I20 scientific identity includes validation and scheduler implementations", {
  source_lines <- readLines(file.path(fuse_test_root, "R/research_training_plan.R"), warn = FALSE)
  expect_true(any(grepl('validation_implementation = training_plan_record', source_lines, fixed = TRUE)))
  expect_true(any(grepl('scheduler_implementation = training_plan_record', source_lines, fixed = TRUE)))
  paths <- training_plan_contract_paths(fuse_test_root)
  expect_true(any(basename(paths) == "prototype_validation.py"))
  expect_true(any(basename(paths) == "run_prototype_training.py"))
  expect_true(any(grepl("dissertation_sources <-", source_lines, fixed = TRUE)))
})

test_that("active P7 graph has bounded gates and aggregate acceptance", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  expect_false("prototype_training" %in% manifest$name)
  expect_true("prototype_training_acceptance" %in% manifest$name)
  expect_true(all(c("p7_deterministic_training_authority", "p7_ddp_initialization_smoke",
                    "p7_single_update_smoke", "p7_ddp_reference_acceptance",
                    "p7_resume_equivalence", "prototype_training_run") %in% manifest$name))
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  training_parents <- intersect(network$edges$from[network$edges$to == "prototype_training_run"], manifest$name)
  expect_setequal(training_parents, c("p7_deterministic_training_authority",
                                      "p7_immutable_parent_reference", "p7_p6_parent_reference",
                                      "p7_resume_equivalence", "p7_training_contract_files",
                                      "p7_validation_query_reference"))
  acceptance_parents <- intersect(network$edges$from[network$edges$to == "prototype_training_acceptance"], manifest$name)
  expect_setequal(acceptance_parents,
                  c("p7_ddp_initialization_smoke", "p7_ddp_reference_acceptance",
                    "p7_deterministic_training_authority", "p7_resume_equivalence",
                    "p7_single_update_smoke", "p7_training_contract_files",
                    "prototype_checkpoint_selection", "prototype_training_execution_record",
                    "prototype_training_run", "prototype_validation_retrieval"))
})

test_that("distributed joint smoke stops before every optimizer step", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/distributed_training.yml"))
  expect_identical(config$acceptance$optimizer_steps, 0L)
  expect_identical(config$execution$total_dataloader_workers, 40L)
  expect_identical(config$execution$workers_per_rank, 20L)
  expect_identical(config$execution$native_threads_per_worker, 1L)

  runner <- readLines(file.path(fuse_test_root, "python/run_prototype_ddp_joint_smoke.py"), warn = FALSE)
  contract <- readLines(file.path(fuse_test_root, "R/research_distributed_joint_model_smoke.R"), warn = FALSE)
  expect_false(any(grepl("prototype_ddp_optimizer_smoke.py", runner, fixed = TRUE)))
  expect_false(any(grepl("run_prototype_training_ddp.py", runner, fixed = TRUE)))
  expect_false(any(grepl("prototype_ddp_optimizer_smoke.py", contract, fixed = TRUE)))
  expect_false(any(grepl("run_prototype_training_ddp.py", contract, fixed = TRUE)))
  expect_true(any(grepl('"optimizer_steps":0', runner, fixed = TRUE)))
})
