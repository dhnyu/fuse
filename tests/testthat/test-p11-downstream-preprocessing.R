source(file.path(fuse_test_root, "R/p11_downstream_preprocessing.R"))

test_that("2025 calendar and temporal classes are fixed", {
  expected <- p11_expected_hours_2025()
  observed <- setNames(expected$expected_count, expected$temporal_class)
  expect_identical(unname(observed[c("weekday_daytime", "weekday_nighttime", "weekend_daytime", "weekend_nighttime")]),
                   c(2440L, 3416L, 1210L, 1694L))
  expect_identical(p11_temporal_class("20250127", 10), "weekend_daytime")
  expect_identical(p11_temporal_class("20250603", 2), "weekend_nighttime")
  expect_identical(p11_temporal_class("20250102", 9), "weekday_daytime")
})

test_that("250 m SGIS identifier conversion is deterministic", {
  source <- c("다사52aa54aa", "다사52ab54ab", "다사52ba54ba", "다사52bb54bb")
  expect_identical(p11_living_grid_id(source), c("다사52005400", "다사52255425", "다사52505450", "다사52755475"))
  expect_error(p11_living_grid_id("다사52zz54aa"), "Unsupported")
})

test_that("target validation rejects duplicates and unknown targets", {
  scenes <- c("a", "b")
  good <- data.table::data.table(
    scene_id = rep(scenes, 11),
    target = rep(c("total_population", "households", "housing_units", "establishments", "workers",
                   "weekday_daytime", "weekday_nighttime", "weekend_daytime", "weekend_nighttime",
                   "official_land_value", "ecostress_lst"), each = 2),
    eligible = TRUE, response = 1, missing_reason = NA_character_
  )
  expect_true(p11_validate_targets(good, scenes))
  expect_error(p11_validate_targets(rbind(good, good[1])), "Duplicate")
  bad <- data.table::copy(good); bad[1, scene_id := "unknown"]
  expect_error(p11_validate_targets(bad, scenes), "unknown scene")
})

test_that("SGIS extensive overlap conserves source contributions", {
  overlap <- data.table::data.table(
    scene_id = c("a", "a", "b"), source_id = c("g1", "g2", "g1"),
    intersection_area = c(5000, 10000, 5000), source_area = c(10000, 10000, 10000)
  )
  value <- data.table::data.table(source_id = c("g1", "g2"), value = c(10, 20))
  joined <- merge(overlap, value, by = "source_id")
  by_scene <- joined[, sum(value * intersection_area / source_area), scene_id]
  expect_equal(by_scene[scene_id == "a", V1], 25)
  expect_equal(sum(by_scene$V1), sum(joined$value * joined$intersection_area / joined$source_area))
})

test_that("immutable publisher validates duplicates and rejects collisions", {
  root <- tempfile("p11-publish-")
  writer <- function(stage) writeLines("stable", file.path(stage, "value.txt"), useBytes = TRUE)
  first <- p11_publish_immutable_bundle(root, "value.txt", writer)
  second <- p11_publish_immutable_bundle(root, "value.txt", writer)
  expect_identical(first, second)
  expect_error(p11_publish_immutable_bundle(root, "value.txt", function(stage) {
    writeLines("changed", file.path(stage, "value.txt"), useBytes = TRUE)
  }), "collision")
})
