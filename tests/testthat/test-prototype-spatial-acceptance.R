acceptance_fixture <- function() {
  plan <- data.table::data.table(scene_id = c("s0", "s1"), split = c("training", "validation"), branch_id = c("b0", "b1"))
  dictionary <- data.table::data.table(scene_id = c("s0", "s1"), local_entity_id = c(0L, 0L), entity_type = c("B", "P"))
  edges <- data.table::data.table(scene_id = character(), source_local_entity_id = integer(),
                                  destination_local_entity_id = integer(), relation_mask = integer(),
                                  relation_dataset_id = character())
  list(plan = plan, dictionary = dictionary, raster = data.table::copy(dictionary),
       nodes = data.table::copy(dictionary), edges = edges)
}

test_that("I13 scientific contract fixes source-codebook vocabulary and population statistics", {
  config <- load_spatial_acceptance_config(spatial_acceptance_contract_paths(fuse_test_root))
  expect_equal(config$scientific$vocabulary$universe, "official_source_codebook_full")
  expect_equal(unlist(config$scientific$vocabulary$reserved_tokens), c("MISSING", "MASK"))
  expect_equal(config$scientific$vocabulary$oov_policy, "hard_failure_no_oov_token")
  expect_equal(config$scientific$normalization$sd_denominator, "N")
  expect_equal(length(config$codebook$entries), 3467L)
  alias <- config$aliases$aliases[[1L]]
  expect_equal(c(alias$raw_value, alias$official_code, alias$official_label), c("블록구조", "12", "블럭구조"))
  expect_equal(c(alias$mapping_type, alias$match_type), c("exact_source_alias", "exact"))
  expect_true(alias$case_sensitive)
})

building_alias_fixture <- function(raw = "블록구조", code = "12", source_id = "b1",
                                   codebook_duplicate = FALSE, separate_alias = FALSE) {
  config <- load_spatial_acceptance_config(spatial_acceptance_contract_paths(fuse_test_root))
  alias <- config$aliases$aliases[[1L]]
  codebook <- data.table::data.table(official_code = "12", official_label = "블럭구조",
                                     category_key = "12", source_order = 0L)
  if (codebook_duplicate) codebook <- data.table::rbindlist(list(codebook, codebook))
  if (separate_alias) codebook <- data.table::rbindlist(list(codebook, data.table::data.table(
    official_code = "98", official_label = "블록구조", category_key = "98", source_order = 1L)))
  canonical <- data.table::data.table(source_entity_id = "b1", A10 = code, A11 = raw)
  observed <- data.table::data.table(source_entity_id = source_id, A11 = raw,
                                     scene_id = "s1", split = "training")
  list(alias = alias, codebook = codebook, canonical = canonical, observed = observed)
}

test_that("exact Building A11 alias resolves only verified code 12 sources", {
  x <- building_alias_fixture()
  audit <- validate_building_structure_alias(x$alias, x$codebook, x$canonical, x$observed)
  expect_length(audit$failures, 0L)
  expect_equal(audit$category_keys, "12")
  expect_true(audit$alias_applied)
  official <- building_alias_fixture(raw = "블럭구조")
  official_audit <- validate_building_structure_alias(official$alias, official$codebook, official$canonical, official$observed)
  expect_length(official_audit$failures, 0L)
  expect_equal(official_audit$category_keys, "12")
  expect_false(official_audit$alias_applied)
})

test_that("Building A11 alias rejects code mismatch and unverified source", {
  wrong_code <- building_alias_fixture(code = "13")
  expect_true(any(grepl("alias_non_official_code", validate_building_structure_alias(wrong_code$alias, wrong_code$codebook,
    wrong_code$canonical, wrong_code$observed)$failures)))
  unverified <- building_alias_fixture(source_id = "outside")
  expect_true(any(grepl("alias_source_not_verified", validate_building_structure_alias(unverified$alias, unverified$codebook,
    unverified$canonical, unverified$observed)$failures)))
})

test_that("Building A11 alias is exact and codebook ambiguity is fatal", {
  for (variant in c("블록 구조", "블록구조 ")) {
    x <- building_alias_fixture(raw = variant)
    expect_true(any(grepl("invalid_A11", validate_building_structure_alias(x$alias, x$codebook,
      x$canonical, x$observed)$failures)))
  }
  separate <- building_alias_fixture(separate_alias = TRUE)
  expect_true(any(grepl("alias_is_separate_official_category", validate_building_structure_alias(separate$alias,
    separate$codebook, separate$canonical, separate$observed)$failures)))
  duplicate <- building_alias_fixture(codebook_duplicate = TRUE)
  expect_true(any(grepl("official_code_not_unique", validate_building_structure_alias(duplicate$alias,
    duplicate$codebook, duplicate$canonical, duplicate$observed)$failures)))
})

test_that("A11 vocabulary has one official code 12 entry and no alias category", {
  config <- load_spatial_acceptance_config(spatial_acceptance_contract_paths(fuse_test_root))
  vocabulary <- acceptance_vocabulary(config$codebook, NULL, config$hashes$codebook)
  expect_equal(nrow(vocabulary[attribute == "A11" & entry_type == "SOURCE" & source_code == "12"]), 1L)
  expect_equal(vocabulary[attribute == "A11" & source_code == "12"]$source_label, "블럭구조")
  expect_false(any(vocabulary[attribute == "A11"]$category_key == "블록구조"))
  expect_false(any(vocabulary$category_key %in% c("OOV", "UNKNOWN", "UNK")))
})

test_that("alias identity and mapping are deterministic and split-independent", {
  config <- load_spatial_acceptance_config(spatial_acceptance_contract_paths(fuse_test_root))
  x <- building_alias_fixture()
  observations <- data.table::rbindlist(list(
    x$observed, data.table::data.table(source_entity_id = "b1", A11 = "블록구조", scene_id = "s2", split = "validation")
  ))
  first <- validate_building_structure_alias(x$alias, x$codebook, x$canonical, observations)
  second <- validate_building_structure_alias(x$alias, x$codebook, x$canonical, observations[2:1])
  expect_equal(sort(first$category_keys), sort(second$category_keys))
  first_vocab <- acceptance_vocabulary(config$codebook, NULL, config$hashes$codebook)
  expect_identical(first_vocab, acceptance_vocabulary(config$codebook, observations, config$hashes$codebook))
  changed <- config$hashes; changed$aliases <- paste0(changed$aliases, "x")
  expect_false(identical(short_hash_id("psa_", config$hashes), short_hash_id("psa_", changed)))
})

test_that("normal aligned fixture accepts a zero-edge scene", {
  x <- acceptance_fixture()
  expect_length(validate_acceptance_fixture(x$plan, x$dictionary, x$raster, x$nodes, x$edges, "rid"), 0L)
})

test_that("cross-artifact key and type failures are detected", {
  x <- acceptance_fixture()
  expect_match(validate_acceptance_fixture(x$plan, x$dictionary, x$raster[-1], x$nodes, x$edges, "rid"), "raster_key_mismatch")
  nodes <- data.table::copy(x$nodes); nodes[1, entity_type := "R"]
  expect_match(validate_acceptance_fixture(x$plan, x$dictionary, x$raster, nodes, x$edges, "rid"), "relation_node_type_mismatch")
  dictionary <- data.table::rbindlist(list(x$dictionary, x$dictionary[1]))
  expect_match(validate_acceptance_fixture(x$plan, dictionary, x$raster, x$nodes, x$edges, "rid"), "duplicate_entity_key")
})

test_that("dangling endpoints, old dataset IDs, and unknown bits fail", {
  x <- acceptance_fixture()
  edge <- data.table::data.table(scene_id = "s0", source_local_entity_id = 0L,
                                 destination_local_entity_id = 99L, relation_mask = 32L,
                                 relation_dataset_id = "old")
  failures <- validate_acceptance_fixture(x$plan, x$dictionary, x$raster, x$nodes, edge, "rid")
  expect_true(all(c("dangling_relation_endpoint", "unknown_relation_bit", "relation_dataset_id") %in% failures))
})

test_that("duplicate scenes and branch grouping mismatch fail", {
  x <- acceptance_fixture()
  duplicated <- data.table::rbindlist(list(x$plan, x$plan[1]))
  failures <- validate_acceptance_fixture(duplicated, x$dictionary, x$raster, x$nodes, x$edges, "rid")
  expect_true(all(c("duplicate_scene", "branch_scene_grouping") %in% failures))
})

test_that("validation categories cannot enter an observed training vocabulary", {
  x <- acceptance_fixture()
  failures <- validate_acceptance_fixture(x$plan, x$dictionary, x$raster, x$nodes, x$edges, "rid",
                                          training_categories = "A", vocabulary_categories = c("A", "V"),
                                          validation_categories = "V")
  expect_match(failures, "validation_vocabulary_leakage")
})

test_that("population SD, missing counts, and zero variance follow the contract", {
  stat <- acceptance_population_stat(c(1, 2, 3, NA), "x", "identity", "training_scene_entity_observation_row")
  expect_equal(stat$mean, 2)
  expect_equal(stat$raw_sd, sqrt(2 / 3))
  expect_equal(stat$valid_count, 3)
  expect_equal(stat$missing_count, 1)
  constant <- acceptance_population_stat(c(4, 4), "x", "identity", "training_scene_entity_observation_row")
  expect_equal(constant$raw_sd, 0)
  expect_equal(constant$applied_scale, 1)
  expect_true(constant$constant_training_field)
})

test_that("checksum mismatch is a hard fixture failure", {
  x <- acceptance_fixture()
  failures <- validate_acceptance_fixture(x$plan, x$dictionary, x$raster, x$nodes, x$edges, "rid",
                                          expected_checksums = "a", actual_checksums = "b")
  expect_match(failures, "checksum_mismatch")
})

test_that("vocabulary and canonical JSON are insensitive to input entry order", {
  config <- load_spatial_acceptance_config(spatial_acceptance_contract_paths(fuse_test_root))
  first <- acceptance_vocabulary(config$codebook, NULL, config$hashes$codebook)
  shuffled <- config$codebook
  shuffled$entries <- rev(shuffled$entries)
  second <- acceptance_vocabulary(shuffled, NULL, config$hashes$codebook)
  expect_identical(first, second)
  expect_false(any(first$category_key %in% c("OOV", "UNKNOWN", "UNK")))
  reserved <- first[entry_type != "SOURCE", .(category_key), by = attribute]
  expect_true(all(vapply(split(reserved$category_key, reserved$attribute), identical, logical(1L), c("MISSING", "MASK"))))
})

test_that("immutable directory reuse accepts identical content and rejects conflict", {
  root <- tempfile("acceptance-publish-")
  writer <- function(stage) writeLines("same", file.path(stage, "value.txt"))
  first <- publish_deterministic_directory(root, "value.txt", writer)
  second <- publish_deterministic_directory(root, "value.txt", writer)
  expect_identical(first, second)
  expect_error(publish_deterministic_directory(root, "value.txt", function(stage) writeLines("different", file.path(stage, "value.txt"))), "non-deterministic")
})
