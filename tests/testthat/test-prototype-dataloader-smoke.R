test_that("I17 DataLoader smoke contract is fixed", {
  contract <- load_dataloader_smoke_config(dataloader_smoke_contract_paths(fuse_test_root))
  expect_equal(contract$config$identity$accepted_dataset_id, "ptd_cee61a525ca92f1b7951c40d")
  expect_equal(contract$config$execution$controller, "controller_05")
  expect_equal(unname(unlist(contract$config$execution$candidate_workers)), c(0, 4))
  expect_equal(contract$config$coordinates$geometry_scale_to_m, 500)
  expect_equal(names(contract$config$batching$budgets), c(
    "scenes", "nodes", "ordered_edges", "coordinates", "actual_payload_bytes"
  ))
})

test_that("I17 Python Dataset, collate, sampler, and corruption fixtures pass", {
  output <- system2(
    "python", c(file.path(fuse_test_root, "tests/python/test_prototype_dataloader.py"), "-v"),
    stdout = TRUE, stderr = TRUE
  )
  expect_null(attr(output, "status"), info = paste(output, collapse = "\n"))
  expect_true(any(grepl("OK", output, fixed = TRUE)), info = paste(output, collapse = "\n"))
})

test_that("I17 is a static CPU file target with only I16 and scoped contract parents", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  target <- manifest[manifest$name == "prototype_dataloader_smoke", ]
  expect_true(is.na(target$pattern) || target$pattern == "")
  declaration <- readLines(file.path(fuse_test_root, "targets/research_dataloader_smoke.R"), warn = FALSE)
  expect_true(any(grepl('format = "file"', declaration, fixed = TRUE)))
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  parents <- intersect(network$edges$from[network$edges$to == "prototype_dataloader_smoke"], manifest$name)
  expect_setequal(parents, c("prototype_training_dataset_acceptance", "dataloader_smoke_contract_files"))
  expect_false(any(c("prototype_serialization_shard", "prototype_spatial_acceptance",
                     "prototype_serialization_plan") %in% parents))
})
