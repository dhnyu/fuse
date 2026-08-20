test_that("target network options and focus selection are deterministic", {
  network_script <- file.path(fuse_test_root, "tools/targets-network/render_targets_network.R")
  source(network_script, local = TRUE)

  options <- parse_network_args(c("--focus=a,b", "--degree=2", "--output-dir=out"))
  expect_equal(options$focus, c("a", "b"))
  expect_equal(options$degree, 2L)
  expect_equal(options$output_dir, "out")

  network <- list(
    vertices = data.frame(name = c("a", "b", "c", "d")),
    edges = data.frame(from = c("a", "b", "c"), to = c("b", "c", "d"))
  )
  focused <- focus_network(network, "b", 1L)
  expect_setequal(focused$vertices$name, c("a", "b", "c"))
  expect_equal(nrow(focused$edges), 2L)
  expect_error(focus_network(network, "missing", 1L), "Unknown focus target")

  singleton <- list(
    vertices = data.frame(
      name = "seoul_data_preprocess", status = NA_character_,
      seconds = NA_real_, bytes = NA_real_
    ),
    edges = data.frame(from = character(), to = character())
  )
  expect_s3_class(build_widget(singleton, "singleton"), "visNetwork")
})
