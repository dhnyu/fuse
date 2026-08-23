test_that("I20 scientific training contract is complete and fixed", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/training_plan.yml"))
  expect_equal(config$identity$accepted_dataset_id, "ptd_8b3359690ea2d0bef52d63e3")
  expect_equal(config$identity$encoder_acceptance_id, "pea_bb192d9b73c6189d36c452fa")
  expect_equal(config$identity$joint_model_acceptance_id, "pjm_0dbf194eb2fd469781a220d1")
  expect_equal(config$identity$distributed_joint_acceptance_id, "pjd_8f3798ffaf37c115b6448165")
  expect_equal(config$identity$augmentation_acceptance_id, "paa_f561eea03b05c47375b7198e")
  expect_equal(config$data$effective_batch_scenes, 32)
  expect_equal(config$optimization$optimizer, "AdamW")
  expect_equal(config$optimization$learning_rate, 1e-4)
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
  expect_identical(config$validation$ties_do_not_reset_patience, TRUE)
  expect_equal(config$execution$dataloader_workers, 40)
  expect_equal(config$execution$workers_per_rank, 20)
  expect_equal(config$runs$execution_mode, "two_process_ddp")
  expect_true(all(c("optimizer", "scheduler", "ema", "queue_values", "queue_pointer",
                    "numpy_rng", "torch_cuda_rng", "sampler_position", "accumulation_gradient_state") %in%
                  unlist(config$resume$required_state)))
})
test_that("I20 has all approved parents and I21 is the first optimizer target", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  expect_true("prototype_training" %in% manifest$name)
  expect_true("prototype_training_acceptance" %in% manifest$name)
  expect_true("prototype_training_plan" %in% manifest$name)
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  parents <- intersect(network$edges$from[network$edges$to == "prototype_training_plan"], manifest$name)
  expect_setequal(parents, c("prototype_training_dataset_acceptance", "prototype_encoder_smoke",
                             "prototype_dataloader_smoke", "prototype_scientific_geometry_roundtrip",
                             "prototype_augmentation_benchmark", "prototype_joint_model_smoke",
                             "prototype_distributed_joint_model_smoke",
                             "training_plan_contract_files"))
  training_parents <- intersect(network$edges$from[network$edges$to == "prototype_training"], manifest$name)
  expect_setequal(training_parents, c("prototype_training_plan", "prototype_training_contract_files"))
  acceptance_parents <- intersect(network$edges$from[network$edges$to == "prototype_training_acceptance"], manifest$name)
  expect_setequal(acceptance_parents, c("prototype_training_plan", "prototype_training",
                                        "prototype_training_contract_files"))
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
