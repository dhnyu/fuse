test_that("supplemental processing order does not mutate source-stream order", {
  source(file.path(fuse_test_root, "R/retrieval_gallery.R"), local = TRUE)
  scenes <- list(list(scene_id = "retrscn_z", stream_ordinal = 2001L),
                 list(scene_id = "retrscn_a", stream_ordinal = 2002L))
  ordered <- retrieval_order_scenes(scenes)
  expect_identical(vapply(ordered, `[[`, character(1), "scene_id"), c("retrscn_a", "retrscn_z"))
  expect_identical(vapply(scenes, `[[`, integer(1), "stream_ordinal"), c(2001L, 2002L))
})

test_that("per-scene relation summaries cannot be permuted silently", {
  withr::local_dir(fuse_test_root)
  source("R/retrieval_gallery.R", local = TRUE)
  root <- withr::local_tempdir()
  paths <- file.path(root, c("relation_edges.parquet", "relation_node_index.parquet", "scene_relation_statistics.parquet"))
  arrow::write_parquet(data.frame(scene_id = "s", relation_mask = 1L), paths[[1L]])
  arrow::write_parquet(data.frame(scene_id = c("s", "s")), paths[[2L]])
  stats <- data.frame(scene_id = "s", node_count = 2L, ordered_pair_count = 1L,
    outside_poi_count = 0L, contained_poi_count = 0L, poi_count = 0L,
    sn_edge_count = 1L, cnt_edge_count = 0L, wit_edge_count = 0L, int_edge_count = 0L, con_edge_count = 0L)
  arrow::write_parquet(stats, paths[[3L]])
  expect_true(retrieval_validate_relation_statistics(paths))
  stats$ordered_pair_count <- 2838L
  arrow::write_parquet(stats, paths[[3L]])
  expect_error(retrieval_validate_relation_statistics(paths), "per-scene relation statistics mismatch")
})
