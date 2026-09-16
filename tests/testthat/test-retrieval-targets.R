test_that("S10 graph has independent accepted parents and explicit controllers", {
  old <- getwd(); on.exit(setwd(old), add = TRUE); setwd(fuse_test_root)
  manifest <- targets::tar_manifest(script = "_targets_retrieval_visualization.R",
    fields = c("name", "command", "resources"))
  expect_length(manifest$name, 15L)
  expect_true(all(grepl("^s10_retrieval_", manifest$name)))
  expect_true(all(vapply(manifest$resources, function(x) !is.null(x$crew), logical(1))))
  expect_silent(targets::tar_validate(script = "_targets_retrieval_visualization.R"))
  network <- targets::tar_network(script = "_targets_retrieval_visualization.R",
    targets_only = TRUE, outdated = FALSE)
  expect_false(any(grepl("s09_training|s11_evaluation|seoul", network$vertices$name)))
  expect_true(any(network$edges$from == "s10_retrieval_original_inputs" &
                  network$edges$to == "s10_retrieval_embeddings"))
})

test_that("definition-only network never requires or creates a store", {
  source(file.path(fuse_test_root, "tools/targets-network/render_targets_network.R"), local = TRUE)
  old <- getwd(); on.exit(setwd(old), add = TRUE); setwd(fuse_test_root)
  absent <- tempfile("s10-no-store-")
  snapshot <- extract_network_snapshot(absent, "_targets_retrieval_visualization.R", TRUE)
  expect_false(dir.exists(absent))
  expect_length(snapshot$manifest$name, 15L)
  expect_setequal(snapshot$vertices$name, snapshot$manifest$name)
  expect_true(all(snapshot$status == "outdated"))
})
