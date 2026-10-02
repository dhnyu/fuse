s11_reader_root <- normalizePath(Sys.getenv("FUSE_REPO_ROOT", "../.."), mustWork = TRUE)
source(file.path(s11_reader_root, "R/scene_descriptors.R"))
source(file.path(s11_reader_root, "R/s11_p3_reader.R"))

test_that("production WKB independently verifies measures and bbox centers", {
  g <- sf::st_sfc(sf::st_polygon(list(matrix(c(0,0,4,0,4,2,0,2,0,0), ncol=2, byrow=TRUE))),crs=5186)
  rows <- data.frame(observed_center_x_5186=2,observed_center_y_5186=1,
    scene_center_x_5186=0,scene_center_y_5186=0,relative_center_x_m=2,relative_center_y_m=1,
    observed_area_m2=8)
  rows$observed_geometry <- as.list(sf::st_as_binary(g))
  read <- s11_cached_geometry(rows,"B")
  expect_equal(read$max_measure_error,0)
  expect_equal(read$max_center_error,0)
  bad <- rows;bad$observed_area_m2 <- 8.01
  expect_error(s11_cached_geometry(bad,"B"),"measure mismatch")
  bad <- rows;bad$observed_center_x_5186 <- 2.001
  expect_error(s11_cached_geometry(bad,"B"),"center mismatch")
  bad <- rows;bad$relative_center_x_m <- 3
  expect_error(s11_cached_geometry(bad,"B"),"relative center")
  expect_length(s11_cached_geometry(rows[0,],"B")$geometry,0)
})

test_that("targets request serialization preserves singleton branch arrays", {
  spec <- jsonlite::fromJSON('{"scene_ids":["one"],"positions":[0]}', simplifyVector = FALSE)
  request <- list(spec = spec, shards = I("/external/manifest.json"))
  read <- jsonlite::fromJSON(jsonlite::toJSON(request, auto_unbox = TRUE), simplifyVector = FALSE)
  expect_identical(read$spec$scene_ids, list("one"))
  expect_identical(read$spec$positions, list(0L))
  expect_identical(read$shards, list("/external/manifest.json"))
})

test_that("FM-only DAG is isolated and all targets have explicit CPU resources", {
  old <- setwd(s11_reader_root); on.exit(setwd(old))
  manifest <- targets::tar_manifest(script = "_targets_representation.R", fields = tidyselect::everything())
  expect_equal(nrow(manifest), 13L)
  expect_true(all(grepl("^s11_", manifest$name)))
  expect_true(all(vapply(manifest$resources, function(x) identical(x$crew$controller, "controller_05"), logical(1))))
  network <- targets::tar_network(script = "_targets_representation.R", outdated = FALSE, targets_only = TRUE,
    store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-s11-representation-analysis")
  expect_equal(nrow(network$edges), 28L)
  expect_true(all(c("s11_descriptor_acceptance", "s11_umap", "s11_figures_tables") %in%
    network$edges$from[network$edges$to == "s11_scientific_acceptance"]))
})
