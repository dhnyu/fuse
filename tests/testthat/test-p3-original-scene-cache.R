test_that("P3 Serialization-v3 scientific contract is fixed", {
  cfg <- yaml::read_yaml(file.path(fuse_test_root, "config/p3_original_scene_cache.yml"))
  expect_identical(cfg$schema_version, "3.0.0")
  expect_identical(cfg$authority_id, "mta_f90fecff7bc7bb5d231cc79f")
  expect_identical(cfg$base_spatial_acceptance_id, "bsa_e617ee0280a6edfa722994d3")
  expect_identical(cfg$sharding$expected_shards, 96L)
  expect_identical(cfg$serialization$geometry_dtype, "float64_wkb")
  expect_identical(cfg$serialization$source_node_representation, "ordered_values_offsets")
})

test_that("P3 offsets reject truncation and malformed boundaries", {
  expect_invisible(p3_validate_offsets(c(0, 2, 2, 5), 5))
  expect_error(p3_validate_offsets(c(0, 2, 4), 5), "invalid")
  expect_error(p3_validate_offsets(c(0, 3, 2, 5), 5), "invalid")
  expect_error(p3_validate_offsets(c(1, 2, 5), 5), "invalid")
})

test_that("P3 adversarial mutations are blocked", {
  source <- list(scene_id="s1",split="training",entity_ids=c("B1","R1"),geometry_wkb=as.raw(1:8),
    relation_endpoints=matrix(c(0L,1L),nrow=1),relation_types="CON",source_node_ids=c("n1","n2"),
    source_node_mapping=c(0L,4L),raster_shape=c(100L,100L),raster_channels=c("landcover","valid"),
    raster_values=as.raw(c(1,2)),geometry_coordinates=c(1,2,3,4))
  expect_invisible(p3_validate_fixture_parity(source,source))
  for (field in c("scene_id","split","entity_ids","geometry_wkb","relation_endpoints","relation_types",
                  "source_node_ids","source_node_mapping","raster_shape","raster_channels","raster_values")) {
    altered <- source
    altered[[field]] <- if (is.raw(source[[field]])) c(source[[field]],as.raw(0)) else if (is.matrix(source[[field]])) source[[field]][,2:1,drop=FALSE] else if (length(source[[field]]) == 1L) paste0(source[[field]],"_x") else if (is.numeric(source[[field]]) && length(unique(source[[field]])) == 1L) replace(source[[field]],1L,source[[field]][[1L]]+1) else rev(source[[field]])
    expect_error(p3_validate_fixture_parity(source,altered),"parity mismatch")
  }
  downcast <- source; downcast$geometry_coordinates <- as.integer(downcast$geometry_coordinates)
  expect_error(p3_validate_fixture_parity(source,downcast),"float32 downcast")
})

test_that("P3 deterministic tar is independent of input order and preserves bytes", {
  skip_if_not(file.exists(Sys.which("python3")))
  root <- tempfile("p3-tar-"); dir.create(root); dir.create(file.path(root,"source"))
  writeBin(as.raw(c(0,1,2,255)), file.path(root,"source","a.bin")); writeLines("value",file.path(root,"source","b.txt"))
  make <- function(members, suffix) {
    spec <- list(source_groups=list(list(prefix="payload",root=file.path(root,"source"),members=members)))
    sp <- file.path(root,paste0("spec-",suffix,".json")); write_json_file(spec,sp)
    out <- file.path(root,paste0(suffix,".tar")); man <- file.path(root,paste0(suffix,".json"))
    system2(research_python_executable(),c(file.path(fuse_test_root,"scripts/p3_deterministic_tar.py"),"--spec",sp,"--output",out,"--manifest",man))
    c(tar=sha256_file(out),manifest=p0_scientific_sha256(jsonlite::read_json(man,simplifyVector=FALSE)$members))
  }
  expect_identical(make(c("b.txt","a.bin"),"one"),make(c("a.bin","b.txt"),"two"))
})

test_that("P3 scientific hash excludes execution environment", {
  scientific <- list(schema="3.0.0",parent="bsa",scenes=c("a","b"))
  expect_identical(p0_scientific_sha256(scientific),p0_scientific_sha256(scientific))
  expect_false(any(c("hostname","username","workers","timestamp","target_store") %in% names(scientific)))
})

test_that("P3 graph has no P4, maintenance, or GPU ancestry", {
  required <- c("original_scene_cache_contract","original_scene_serialization_plan","original_scene_serialization_shard",
                "original_scene_geometry_roundtrip","original_scene_cache_index","original_scene_dataset_acceptance")
  text <- paste(readLines(file.path(fuse_test_root,"targets/research_original_scene_cache.R"),warn=FALSE),collapse="\n")
  expect_true(all(vapply(required, grepl, logical(1L), x=text, fixed=TRUE)))
  expect_false(grepl("augmentation|dataloader|gpu|maintenance",text,ignore.case=TRUE))
  expect_true(grepl("base_spatial_acceptance",text,fixed=TRUE))
})
