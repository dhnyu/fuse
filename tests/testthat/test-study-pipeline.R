test_that("configuration schema and approved methodology are valid", {
  config <- load_pipeline_config(file.path(fuse_test_root, "config/paths.yml"), file.path(fuse_test_root, "config/methodology.yml"))
  expect_equal(config$methodology$study_area$source_buffer_m, 400)
  expect_equal(config$methodology$study_area$output_crs, "EPSG:5186")
  expect_equal(config$methodology$dem$resolution_m, 30)
  expect_equal(config$methodology$road$node_candidate_padding_m, 1)
  expect_equal(config$paths$targets$store, "/mnt/hdd002/dhnyu/fusedata/targets/fuse")
})

test_that("research and maintenance pipelines use separate scripts and stores", {
  root_pipeline <- readLines(file.path(fuse_test_root, "_targets.R"), warn = FALSE)
  expect_false(any(grepl("tar_target\\(", root_pipeline)))
  expect_false(any(grepl("seoul_data_preprocess.R", root_pipeline, fixed = TRUE)))
  expect_true(any(grepl("targets/research_scene_index.R", root_pipeline, fixed = TRUE)))

  maintenance_pipeline <- readLines(file.path(fuse_test_root, "_targets_maintenance.R"), warn = FALSE)
  expect_true(any(grepl("targets/seoul_data_preprocess.R", maintenance_pipeline, fixed = TRUE)))
  research_paths <- yaml::read_yaml(file.path(fuse_test_root, "config/research_paths.yml"))
  expect_false(identical(research_paths$targets$research_store, research_paths$targets$maintenance_store))

  research_manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets.R"), callr_arguments = list(wd = fuse_test_root)
  )
  expect_setequal(
    research_manifest$name,
    c(
      "observation_contract_files", "training_dataset_acceptance_contract_files", "membership_contract_files",
      "serialization_shard_contract_files", "augmentation_benchmark_contract_files", "research_config_files",
      "prototype_training_contract_files", "training_plan_contract_files", "joint_model_smoke_contract_files",
      "research_implementation_files", "encoder_smoke_contract_files", "dataloader_smoke_contract_files",
      "relation_contract_files", "distributed_joint_model_contract_files", "serialization_plan_contract_files",
      "raster_observation_contract_files", "spatial_acceptance_contract_files",
      "prototype_model_validation_contract_files",
      "prototype_model_acceptance_contract_files",
      "full_membership_plan_contract_files", "full_membership_authorization_contract",
      "full_membership_i24_authorization",
      "reduced_methodology_source_files", "reduced_methodology_git_state",
      "reduced_methodology_source_set", "reduced_methodology_conflict_gate",
      "scene_methodology_contract", "base_spatial_methodology_contract",
      "original_cache_methodology_contract", "augmentation_methodology_contract",
      "model_methodology_contract", "training_methodology_contract",
      "evaluation_methodology_contract", "downstream_methodology_contract",
      "reduced_methodology_authority",
      "p1_scene_index_contract_files", "reduced_scene_index_plan", "scene_index_acceptance",
      "accepted_off_grid_source", "runtime_mirror_contract_files", "prototype_runtime_inputs",
      "study_data_inputs", "study_data_inventory", "methodology_contract", "spatial_scene_index",
      "prototype_scene_selection", "prototype_membership_plan", "prototype_membership_shard",
      "prototype_membership_acceptance", "prototype_observation_plan",
      "prototype_vector_observation_shard", "prototype_raster_observation_shard", "prototype_relation_shard",
      "prototype_spatial_acceptance", "prototype_serialization_plan", "prototype_serialization_shard",
      "prototype_training_dataset_acceptance", "prototype_dataloader_smoke", "prototype_encoder_smoke",
      "prototype_scientific_geometry_roundtrip", "prototype_augmentation_benchmark",
      "prototype_joint_model_smoke", "prototype_distributed_joint_model_smoke", "prototype_training_plan",
      "prototype_training", "prototype_training_acceptance", "prototype_model_validation",
      "prototype_model_acceptance", "full_membership_plan",
      "p2_base_spatial_contract_files",
      "base_spatial_prototype_membership_plan", "base_spatial_prototype_membership_shard",
      "base_spatial_prototype_membership_acceptance", "base_spatial_prototype_observation_plan",
      "base_spatial_prototype_vector_observation_shard", "base_spatial_prototype_raster_observation_shard",
      "base_spatial_prototype_relation_graph_shard", "base_spatial_prototype_source_topology_shard",
      "base_spatial_prototype_acceptance",
      "base_spatial_membership_plan", "base_spatial_membership_shard",
      "base_spatial_membership_acceptance", "base_spatial_observation_plan",
      "base_vector_observation_shard", "base_raster_observation_shard",
      "base_relation_tiered_execution_acceptance", "base_relation_graph_shard",
      "base_source_topology_shard", "base_spatial_acceptance",
      "p3_original_scene_cache_contract_files", "original_scene_cache_contract",
      "original_scene_serialization_plan", "original_scene_serialization_shard",
      "original_scene_shard_validation", "original_scene_geometry_roundtrip",
      "original_scene_cache_index", "original_scene_cache_manifest",
      "original_scene_dataset_acceptance"
    )
  )
  expect_false("seoul_data_preprocess" %in% research_manifest$name)
  maintenance_manifest <- targets::tar_manifest(
    script = file.path(fuse_test_root, "_targets_maintenance.R"), callr_arguments = list(wd = fuse_test_root)
  )
  expect_equal(maintenance_manifest$name, "seoul_data_preprocess")
})

test_that("controller and target-level parallel specifications are validated", {
  variable <- "FUSE_TEST_CONTROLLER_WORKERS"
  old <- Sys.getenv(variable, unset = NA_character_)
  on.exit(if (is.na(old)) Sys.unsetenv(variable) else do.call(Sys.setenv, setNames(list(old), variable)))
  Sys.setenv(FUSE_TEST_CONTROLLER_WORKERS = "7")
  expect_equal(fuse_controller_worker_count(variable, 3L), 7L)
  Sys.setenv(FUSE_TEST_CONTROLLER_WORKERS = "0")
  expect_error(fuse_controller_worker_count(variable, 3L), "positive integer")

  specification <- fuse_parallel_spec(5, 4, available = 48)
  expect_equal(specification$workers, 5L)
  expect_equal(specification$threads, 4L)
  expect_equal(specification$maximum_cores, 20L)
  expect_error(fuse_parallel_spec(5, 4, available = 19), "exceeds available logical CPUs")
})

test_that("single-target orchestration retains every former processing stage", {
  config <- load_pipeline_config(file.path(fuse_test_root, "config/paths.yml"), file.path(fuse_test_root, "config/methodology.yml"))
  expect_equal(seoul_subset_task_names(), c("building", "road", "poi", "landcover", "dem"))
  expect_equal(
    seoul_generated_output_paths(config),
    unname(unlist(config$paths$study[c("boundary", "buffer400", "building", "road", "poi", "landcover", "dem", "manifest")]))
  )

  orchestration <- paste(deparse(body(preprocess_seoul_data)), collapse = "\n")
  required_calls <- c(
    "load_pipeline_config", "validate_canonical_inputs", "inspect_seoul_boundary_source",
    "create_seoul_boundary", "create_seoul_buffer", "run_seoul_subset_tasks",
    "validate_seoul_subset", "write_seoul_data_manifest", "write_study_subset_report"
  )
  expect_true(all(vapply(required_calls, grepl, logical(1L), x = orchestration, fixed = TRUE)))

  parallel_body <- paste(deparse(body(run_seoul_subset_tasks)), collapse = "\n")
  expect_match(parallel_body, "future.apply::future_lapply", fixed = TRUE)
  expect_match(parallel_body, "lapply", fixed = TRUE)
})

test_that("native thread limits can be applied and restored", {
  before <- capture_native_thread_state()
  on.exit(restore_native_thread_state(before), add = TRUE)
  set_native_thread_limits(4)
  expect_true(all(Sys.getenv(native_thread_environment_variables()) == "4"))
  expect_equal(data.table::getDTthreads(), 4L)
  restore_native_thread_state(before)
  after <- capture_native_thread_state()
  expect_identical(after$environment, before$environment)
  expect_equal(after$data_table, before$data_table)
})

test_that("Seoul selection is deterministic and source geometry is valid", {
  config <- load_pipeline_config(file.path(fuse_test_root, "config/paths.yml"), file.path(fuse_test_root, "config/methodology.yml"))
  files <- boundary_component_paths(config$paths$administrative$sido)
  manifest <- read_canonical_manifest(config$paths$canonical$manifest)
  info <- inspect_seoul_boundary_source(files, config, manifest)
  expect_match(info$source_feature_identifier, "SIDO_CD=11")
  expect_true(info$source_valid)
  expect_false(info$repair_applied)
  expect_equal(info$source_epsg, 5179)
})

test_that("boundary-inclusive point predicate includes edge points", {
  polygon <- sf::st_sfc(sf::st_polygon(list(matrix(c(0, 0, 10, 0, 10, 10, 0, 10, 0, 0), ncol = 2, byrow = TRUE))), crs = 5186)
  points <- sf::st_sfc(sf::st_point(c(0, 5)), sf::st_point(c(5, 5)), sf::st_point(c(-1, 5)), crs = 5186)
  expect_equal(lengths(sf::st_intersects(points, polygon)) > 0, c(TRUE, TRUE, FALSE))
  expect_equal(lengths(sf::st_within(points, polygon)) > 0, c(FALSE, TRUE, FALSE))
})

test_that("source-aligned land-cover crop snaps outwards", {
  bbox <- structure(c(xmin = 179189.8, ymin = 536547.4, xmax = 216242.3, ymax = 566863.6), class = "bbox")
  geotransform <- c(15214.30761973001, 5, 0, 615320.3831593934, 0, -5)
  extent <- snap_extent_to_source_raster(bbox, geotransform)
  expect_true(extent_covers_bbox(extent, bbox))
  expect_equal((extent[["xmin"]] - geotransform[[1]]) %% 5, 0, tolerance = 1e-7)
  expect_equal((geotransform[[4]] - extent[["ymax"]]) %% 5, 0, tolerance = 1e-7)
})

test_that("DEM grid snaps outwards to the configured anchor", {
  bbox <- structure(c(xmin = 179189.8, ymin = 536547.4, xmax = 216242.3, ymax = 566863.6), class = "bbox")
  extent <- snap_extent_to_grid(bbox, 30, 0, 0)
  expect_true(extent_covers_bbox(extent, bbox))
  expect_equal(unname(extent %% 30), c(0, 0, 0, 0))
})

test_that("an identical recomputed buffer has zero symmetric-difference area", {
  config <- load_pipeline_config(file.path(fuse_test_root, "config/paths.yml"), file.path(fuse_test_root, "config/methodology.yml"))
  if (all(file.exists(c(config$paths$study$boundary, config$paths$study$buffer400)))) {
    result <- validate_boundary_outputs(config$paths$study$boundary, config$paths$study$buffer400, config)
    expect_equal(result$symmetric_difference_area_m2, 0)
  } else {
    skip("Study boundary artifacts are not available")
  }
})

test_that("road node closure includes both endpoints exactly once", {
  required <- road_required_node_ids(c("N3", "N1", "N2"), c("N4", "N2", "N3"))
  expect_equal(required, c("N1", "N2", "N3", "N4"))
})

test_that("atomic publish refuses overwrite", {
  directory <- tempfile("atomic_publish_")
  dir.create(directory)
  stage <- file.path(directory, "artifact.tmp")
  final <- file.path(directory, "artifact.txt")
  writeLines("first", stage)
  expect_equal(atomic_publish(stage, final), final)
  writeLines("second", stage)
  expect_error(atomic_publish(stage, final), "Refusing to overwrite")
  unlink(directory, recursive = TRUE)
})

test_that("manifest fingerprint changes with an output checksum", {
  qc <- list(
    canonical = list(manifest = list(sha256 = "a")),
    boundary_source = list(source_checksum = "b"),
    config_sha256 = "c",
    outputs = list(boundary = list(sha256 = "d")),
    contract_version = "1.0.0"
  )
  first <- manifest_fingerprint(qc)
  qc$outputs$boundary$sha256 <- "e"
  expect_false(identical(first, manifest_fingerprint(qc)))
})

test_that("manifest refresh only accepts unchanged validated artifacts", {
  qc <- list(
    status = "PASS",
    contract_version = "1.0.0",
    canonical = list(manifest = list(sha256 = "canonical")),
    boundary_source = list(source_checksum = "boundary"),
    outputs = list(boundary = list(sha256 = "output"))
  )
  existing <- list(
    status = "PASS",
    contract_version = "1.0.0",
    canonical = list(manifest = list(sha256 = "canonical")),
    study_area = list(source_boundary_checksum = "boundary"),
    outputs = list(boundary = list(sha256 = "output"))
  )
  expect_true(existing_manifest_matches_qc(existing, qc))
  existing$outputs$boundary$sha256 <- "different"
  expect_false(existing_manifest_matches_qc(existing, qc))
})

test_that("software provenance captures executable versions", {
  versions <- software_versions()
  expect_match(versions$GDAL, "GDAL [0-9]+")
  expect_match(versions$PROJ, "^Rel\\. [0-9]+")
})
