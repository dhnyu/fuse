test_that("I15 serialization shard contract is fixed", {
  config <- load_serialization_shard_config(serialization_shard_contract_paths(fuse_test_root))
  expect_equal(config$scientific$identity$serialization_plan_id, "psp_72c5e4e5c3e4c84eb47aad85")
  expect_equal(config$scientific$identity$serialization_dataset_id, "psd_72c5e4e5c3e4c84eb47aad85")
  expect_equal(config$scientific$geometry_representations$scientific_reference$crs, "EPSG:5186")
  expect_equal(config$scientific$geometry_representations$scientific_reference$encoder_input, "forbidden")
  expect_equal(config$scientific$tensor$safetensors$geometry$coordinates_absolute_xy_5186$dtype, "float64")
  expect_equal(config$runtime$controller, "controller_10")
  expect_equal(config$runtime$workers, 1)
  expect_equal(config$runtime$threads_per_worker, 1)
  expect_equal(length(config$scientific$tensor$object_raster_features), 26)
  expect_equal(unlist(config$scientific$archive$member_order), c(
    "meta.json", "entities.safetensors", "geometry.safetensors", "edges.safetensors",
    "topology.safetensors", "rasters.safetensors"
  ))
})

test_that("I15 Python fixtures pass", {
  output <- system2(
    "python", c(file.path(fuse_test_root, "tests/python/test_serialize_prototype_shard.py"), "-v"),
    stdout = TRUE, stderr = TRUE
  )
  expect_null(attr(output, "status"), info = paste(output, collapse = "\n"))
  expect_true(any(grepl("OK", output, fixed = TRUE)), info = paste(output, collapse = "\n"))
})

test_that("I15 target is dynamic, file-tracked, and directly scoped", {
  manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  target <- manifest[manifest$name == "prototype_serialization_shard", ]
  expect_equal(target$pattern, "map(prototype_serialization_plan)")
  declaration <- readLines(file.path(fuse_test_root, "targets/research_serialization_shard.R"), warn = FALSE)
  expect_true(any(grepl('format = "file"', declaration, fixed = TRUE)))
  network <- targets::tar_network(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  edges <- network$edges
  parents <- intersect(edges$from[edges$to == "prototype_serialization_shard"], manifest$name)
  expect_setequal(parents, c("prototype_serialization_plan", "serialization_shard_contract_files"))
  expect_false(any(c("prototype_membership_plan", "prototype_observation_plan", "prototype_spatial_acceptance") %in% parents))
})
