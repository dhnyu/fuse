source(file.path(fuse_test_root, "R/p11_downstream_preprocessing.R"))
source(file.path(fuse_test_root, "R/p11_living_population_rematerialization.R"))

test_that("duplicate administrative rows aggregate only when every value is usable", {
  raw <- data.table::data.table(
    date = rep("20250101", 5), hour = c(0, 0, 1, 1, 0), admin_id = letters[1:5],
    source_id = c("g1", "g1", "g1", "g1", "g2"),
    released_value = c("2.5", "3.5", "4", "*", "-1")
  )
  value <- p11_living_v2_group_rows(raw, "20250101", c("g1", "g2"))
  expect_equal(value[source_id == "g1" & hour == 0, value], 6)
  expect_equal(value[source_id == "g1" & hour == 0, duplicate_count], 1L)
  expect_true(value[source_id == "g1" & hour == 0, valid])
  expect_false(value[source_id == "g1" & hour == 1, valid])
  expect_identical(value[source_id == "g1" & hour == 1, missing_reason],
                   "SUPPRESSED_OR_NONNUMERIC_COMPONENT")
  expect_false(value[source_id == "g2", valid])
  expect_identical(value[source_id == "g2", missing_reason], "NEGATIVE_COMPONENT")
})

test_that("full grid-hour universe retains omitted source rows", {
  raw <- data.table::data.table(
    date = "20250101", hour = 0L, admin_id = "a", source_id = "g1", released_value = "8"
  )
  grouped <- p11_living_v2_group_rows(raw, "20250101", c("g1", "g2"))
  universe <- p11_living_v2_full_universe(grouped, c("g2", "g1"), "20250101")
  expect_equal(nrow(universe), 48L)
  expect_equal(universe[valid == TRUE, .N], 1L)
  expect_equal(universe[missing_reason == "MISSING_SOURCE_ROW", .N], 47L)
  expect_identical(universe$source_id[1:2], c("g1", "g2"))
})

test_that("partial scene support is summed without extrapolation or zero fill", {
  overlap <- data.table::data.table(
    source_id = c("g1", "g2"), scene_id = c("s1", "s1"),
    intersection_area = c(125000, 125000), source_area = c(250000, 250000)
  )
  grouped <- data.table::data.table(
    source_id = "g1", date = "20250102", hour = 9L, value = 20,
    raw_row_count = 1L, contributing_admin_row_count = 1L, duplicate_count = 0L,
    valid = TRUE, missing_reason = NA_character_
  )
  universe <- p11_living_v2_full_universe(grouped, c("g1", "g2"), "20250102")
  hourly <- p11_living_v2_scene_hours(universe, overlap)
  value <- hourly[hour == 9L]
  expect_equal(value$response, 10)
  expect_equal(value$total_expected_source_area, 250000)
  expect_equal(value$valid_observed_source_area, 125000)
  expect_equal(value$unavailable_source_area, 125000)
  expect_equal(value$spatial_support_fraction, 0.5)
  expect_equal(value$expected_grid_count, 2L)
  expect_equal(value$valid_grid_count, 1L)
  expect_equal(value$unavailable_grid_count, 1L)
  expect_true(value$valid_scene_hour)
  expect_false(hourly[hour == 10L, valid_scene_hour])
  expect_true(is.na(hourly[hour == 10L, response]))
})

test_that("calendar classes and authority remain frozen", {
  cfg <- p11_living_v2_read_config(file.path(fuse_test_root, "config/p11_downstream_preprocessing_v2.yml"))
  old <- getwd(); on.exit(setwd(old), add = TRUE); setwd(fuse_test_root)
  authority <- p11_living_v2_validate_authority(cfg)
  expect_identical(authority$expected$methodology, "p11meth_42070c9b832c232a6e989d25")
  expect_identical(p11_temporal_class("20250127", 10), "weekend_daytime")
  expect_identical(p11_temporal_class("20250603", 2), "weekend_nighttime")
})

test_that("shard inventory readback rejects corruption", {
  root <- tempfile("p11lp-inventory-"); dir.create(root)
  writeLines("stable", file.path(root, "value.txt"), useBytes = TRUE)
  records <- p11_living_v2_file_inventory(root)
  expect_true(p11_living_v2_validate_inventory(root, records))
  writeLines("changed", file.path(root, "value.txt"), useBytes = TRUE)
  expect_error(p11_living_v2_validate_inventory(root, records), "corruption")
})
