fuse_test_root <- normalizePath(file.path("..", ".."), mustWork = TRUE)
source(file.path(fuse_test_root, "R/config_paths.R"))
source(file.path(fuse_test_root, "R/io_spatial.R"))
source(file.path(fuse_test_root, "R/spatial_boundary.R"))
source(file.path(fuse_test_root, "R/process_buildings.R"))
source(file.path(fuse_test_root, "R/process_roads.R"))
source(file.path(fuse_test_root, "R/process_pois.R"))
source(file.path(fuse_test_root, "R/process_rasters.R"))
source(file.path(fuse_test_root, "R/validate_outputs.R"))
source(file.path(fuse_test_root, "R/output_manifest.R"))
source(file.path(fuse_test_root, "R/pipeline_seoul_data_preprocess.R"))
source(file.path(fuse_test_root, "R/downstream_sources.R"))
source(file.path(fuse_test_root, "R/current_source_registry.R"))
source_current_research_files(fuse_test_root, environment())

current_parent_fixture <- function(root = tempfile("current-parent-")) {
  dir.create(root, recursive = TRUE)
  put <- function(dir, name, value = NULL, text = NULL) {
    dir.create(dir, recursive = TRUE, showWarnings = FALSE)
    path <- file.path(dir, name)
    if (is.null(text)) write_json_file(value, path) else writeLines(text, path, useBytes = TRUE)
    path
  }
  authority_id <- "mta_2142a2914bc5c43ea8d6e312"
  index_dir <- file.path(root, "index")
  index <- put(index_dir, "spatial_scene_index.parquet", text = "fixture-index")
  manifest <- put(index_dir, "spatial_scene_index_manifest.json", list(
    schema_version = "1.0.0", status = "PASS", authority_id = authority_id,
    scene_index_id = "rsi_111111111111111111111111", row_count = 12421L,
    split_counts = list(training = 2421L, validation = 1000L, evaluation = 9000L)
  ))
  acceptance <- put(file.path(root, "scene"), "scene_index_acceptance.json", list(
    schema_version = "1.0.0", status = "PASS", authority_id = authority_id,
    acceptance_id = "sia_222222222222222222222222", scene_index_id = "rsi_111111111111111111111111",
    split_counts = list(training = 2421L, validation = 1000L, evaluation = 9000L),
    artifact_checksums = list(
      list(role = "spatial_scene_index", sha256 = sha256_file(index)),
      list(role = "spatial_scene_index_manifest", sha256 = sha256_file(manifest))
    )
  ))
  inventory <- put(file.path(root, "inventory"), "study_data_inventory.json", list(
    schema_version = "1.0.0", status = "PASS", authority_id = authority_id,
    inventory_id = "rin_333333333333333333333333"
  ))
  p2 <- put(file.path(root, "p2"), "base_spatial_acceptance.json", list(
    schema_version = "1.0.0", status = "PASS", authority_id = authority_id,
    acceptance_id = "bsa_444444444444444444444444", original_observation_id = "obs_555555555555555555555555",
    scene_index_id = "rsi_111111111111111111111111", scene_acceptance_id = "sia_222222222222222222222222",
    scene_count = 12421L, split_counts = list(training = 2421L, validation = 1000L, evaluation = 9000L)
  ))
  membership <- put(file.path(root, "membership"), "aggregate_membership_manifest.json", list(
    schema_version = "1.0.0", status = "PASS", authority_id = authority_id,
    scene_index_id = "rsi_111111111111111111111111"
  ))
  authority <- put(file.path(root, "authority"), "reduced_methodology_authority.json", list(
    authority_id = authority_id, overall_status = "PASS"
  ))
  contract <- put(file.path(root, "contract"), "base_spatial_methodology_contract.json", list(
    contract_id = "mmc_b75dcec66fe442fc", module_content_sha256 = "b75dcec66fe442fc5deda2b8798d6ff5b7f4380ec66cab6e769dd8c31cb3dfa8",
    status = "PASS"
  ))
  list(root = root, index = c(index, manifest), scene = acceptance, inventory = inventory,
       p2 = p2, membership = membership, authority = authority, contract = contract)
}
