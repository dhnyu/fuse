test_that("I24 is a read-only gate with the blueprint direct parents", {
  config <- yaml::read_yaml(file.path(fuse_test_root, "config/prototype_model_acceptance.yml"))
  expect_identical(config$scientific$gate_mode, "read_only_zero_compute")
  expect_setequal(
    unlist(config$scientific$direct_parents, use.names = FALSE),
    c("prototype_dataloader_smoke", "prototype_encoder_smoke", "prototype_augmentation_benchmark",
      "prototype_training_acceptance", "prototype_model_validation")
  )
  expect_true(all(c("forward", "augmentation", "optimizer_update", "scheduler_update",
                    "ema_update", "queue_update", "checkpoint_mutation") %in%
                  unlist(config$scientific$forbidden_operations, use.names = FALSE)))
  expect_identical(config$scientific$retrieval$original_relevance_metrics, "forbidden")
  expect_identical(config$scientific$retrieval$augmented_source_metrics,
                   c("MRR", "HIT@1", "HIT@5", "HIT@10"))

  manifest <- targets::tar_manifest(script = file.path(fuse_test_root, "_targets.R"),
                                    callr_arguments = list(wd = fuse_test_root))
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  parents <- network$edges$from[network$edges$to == "prototype_model_acceptance"]
  parents <- intersect(parents, manifest$name)
  expect_setequal(parents, c("prototype_dataloader_smoke", "prototype_encoder_smoke",
                             "prototype_augmentation_benchmark", "prototype_training_acceptance",
                             "prototype_model_validation", "prototype_model_acceptance_contract_files"))
  expect_false(any(grepl("^full_|^single_gpu_experiment|^ddp_experiment", manifest$name)))
})

test_that("I24 schema fixes zero-compute and immutable publication gates", {
  schema <- jsonlite::read_json(
    file.path(fuse_test_root, "config/schemas/prototype_model_acceptance.schema.json"),
    simplifyVector = FALSE
  )
  expect_identical(schema$properties$zero_compute$properties$additional_optimizer_steps$const, 0L)
  expect_identical(schema$properties$zero_compute$properties$forward_calls$const, 0L)
  expect_identical(schema$properties$zero_compute$properties$augmentation_calls$const, 0L)
  expect_identical(schema$properties$checkpoint$properties$sha256$const,
                   "a17477a647d68024cb59ce6c3ce66a703e12143f37340b90c82cd3549b303704")
  expect_identical(schema$properties$immutable_publication$properties$atomic$const, "PASS")
})

test_that("I24 publisher cannot invoke model or training computation", {
  source <- readLines(file.path(fuse_test_root, "python/accept_prototype_model.py"), warn = FALSE)
  text <- paste(source, collapse = "\n")
  expect_false(grepl("import torch", text, fixed = TRUE))
  expect_false(grepl("prototype_encoder", text, fixed = TRUE))
  expect_false(grepl("prototype_augmentation", text, fixed = TRUE))
  expect_false(grepl("optimizer.step", text, fixed = TRUE))
})
