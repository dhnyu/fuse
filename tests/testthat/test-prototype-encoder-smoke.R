test_that("I18 architecture and GPU execution contract is fixed", {
  contract <- load_encoder_smoke_config(encoder_smoke_contract_paths(fuse_test_root))
  expect_equal(contract$config$dimensions$latent, 128)
  expect_equal(contract$config$architecture$relation_layers, 3)
  expect_equal(contract$config$architecture$attention_heads, 4)
  expect_equal(contract$config$architecture$dropout, 0.1)
  expect_equal(contract$config$geometry$normalization_length_m, 500)
  expect_equal(contract$config$execution$controller, "controller_gpu_02")
})

test_that("I18 CPU scientific fixtures pass", {
  output <- system2(
    "python", c(file.path(fuse_test_root, "tests/python/test_prototype_encoder.py"), "-v"),
    stdout = TRUE, stderr = TRUE
  )
  expect_null(attr(output, "status"), info = paste(output, collapse = "\n"))
  expect_true(any(grepl("OK", output, fixed = TRUE)), info = paste(output, collapse = "\n"))
})

test_that("I18 is static GPU file target with only I16, I17, and scoped contract parents", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  target <- manifest[manifest$name == "prototype_encoder_smoke", ]
  expect_true(is.na(target$pattern) || target$pattern == "")
  declaration <- readLines(file.path(fuse_test_root, "targets/research_encoder_smoke.R"), warn = FALSE)
  expect_true(any(grepl('format = "file"', declaration, fixed = TRUE)))
  expect_true(any(grepl("controller_gpu_02_resources", declaration, fixed = TRUE)))
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  parents <- intersect(network$edges$from[network$edges$to == "prototype_encoder_smoke"], manifest$name)
  expect_setequal(parents, c(
    "prototype_training_dataset_acceptance", "prototype_dataloader_smoke", "encoder_smoke_contract_files"
  ))
})
