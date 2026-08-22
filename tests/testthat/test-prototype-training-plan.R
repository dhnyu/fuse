test_that("I20 scientific training contract is complete and fixed", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/training_plan.yml"))
  expect_equal(config$identity$accepted_dataset_id, "ptd_cee61a525ca92f1b7951c40d")
  expect_equal(config$identity$encoder_acceptance_id, "pea_5784252434798d9dfa05d796")
  expect_equal(config$identity$augmentation_acceptance_id, "paa_8d73a94e574dcdbc5c5106d2")
  expect_equal(config$data$effective_batch_scenes, 32)
  expect_equal(config$optimization$optimizer, "AdamW")
  expect_equal(config$optimization$learning_rate, 1e-4)
  expect_equal(config$optimization$weight_decay, 1e-4)
  expect_equal(config$optimization$maximum_epochs, 200)
  expect_equal(config$optimization$warmup_epochs, 10)
  expect_equal(config$optimization$ema_momentum, 0.999)
  expect_equal(config$optimization$queue_size, 8192)
  expect_equal(config$optimization$temperature, 0.1)
  expect_equal(config$optimization$geographic_negative_exclusion_radius_m, 750)
  expect_equal(config$validation$primary_metric, "MRR")
  expect_true(all(c("optimizer", "scheduler", "ema", "queue_values", "queue_pointer",
                    "numpy_rng", "torch_cuda_rng", "sampler_position", "accumulation_gradient_state") %in%
                  unlist(config$resume$required_state)))
})
test_that("I20 has only approved parents and I21 is not declared", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  expect_false("prototype_training" %in% manifest$name)
  expect_true("prototype_training_plan" %in% manifest$name)
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  parents <- intersect(network$edges$from[network$edges$to == "prototype_training_plan"], manifest$name)
  expect_setequal(parents, c("prototype_training_dataset_acceptance", "prototype_encoder_smoke",
                             "prototype_augmentation_benchmark", "training_plan_contract_files"))
})
