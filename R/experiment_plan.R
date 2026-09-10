# Current dissertation experiment specification. Superseded P8 builders are
# intentionally absent from the executable source tree.
current_experiment_plan_sources <- function(root = ".", dissertation_root = path.expand("~/dhnyu-masters-dissertation")) {
  local <- c(
    "config/current_methodology.yml", "config/training.yml", "config/p0_scientific_revision.yml",
    "config/s08_plan_identity.yml", "python/current_methodology.py",
    "config/schemas/current_experiment_plan_v3.schema.json",
    "R/experiment_plan.R", "targets/s08_experiment_plan.R"
  )
  dissertation <- c(
    "template/sections/chapters/results/01-experimental-setup.typ",
    "template/sections/chapters/results/05-hyperparameter-study.typ",
    "template/sections/chapters/04-methodology-training.typ",
    "template/materials/tables/results-02-model-dimension-table.typ",
    "template/materials/tables/results-04-training-configuration-table.typ",
    "template/materials/tables/results-05-model-architecture-table.typ"
  )
  normalizePath(c(file.path(root, local), file.path(dissertation_root, dissertation)), mustWork = TRUE)
}

s08_json_equal <- function(left, right) identical(canonical_json(left), canonical_json(right))

s08_read_artifact <- function(paths, basename_required, label, status_field = "status") {
  values <- unlist(paths, recursive = TRUE, use.names = FALSE)
  matches <- values[basename(values) == basename_required & file.exists(values)]
  if (length(matches) != 1L) stop("S08 requires exactly one readable parent artifact: ", label, call. = FALSE)
  path <- normalizePath(matches[[1L]], mustWork = TRUE)
  value <- jsonlite::read_json(path, simplifyVector = FALSE)
  if (!identical(value[[status_field]], "PASS")) stop("S08 parent is not accepted: ", label, call. = FALSE)
  list(path = path, value = value)
}

s08_current_lineage <- function(methodology_authority, scene_acceptance, spatial_acceptance,
                                scene_dataset_acceptance, bank_acceptance,
                                query_acceptance, dataset_acceptance, root = ".") {
  p0 <- s08_read_artifact(methodology_authority, "reduced_methodology_authority.json", "P0", "overall_status")
  p1 <- s08_read_artifact(scene_acceptance, "scene_index_acceptance.json", "P1")
  p2 <- s08_read_artifact(spatial_acceptance, "base_spatial_acceptance.json", "P2")
  p3 <- s08_read_artifact(scene_dataset_acceptance, "original_scene_dataset_acceptance.json", "P3")
  cache <- s08_read_artifact(scene_dataset_acceptance, "original_scene_cache_manifest.json", "P3 cache")
  p4 <- s08_read_artifact(bank_acceptance, "augmentation_bank_acceptance.json", "P4")
  p5 <- s08_read_artifact(query_acceptance, "fixed_query_acceptance.json", "P5")
  p6 <- s08_read_artifact(dataset_acceptance, "model_data_acceptance.json", "P6")
  revision <- yaml::read_yaml(file.path(root, "config/p0_scientific_revision.yml"))
  authority_id <- p0$value$authority_id
  scientific_sha256 <- p0$value$scientific_contract_sha256
  checks <- c(
    identical(revision$invalidation_policy, "explicit_revision_only"),
    identical(revision$material_revision_declared, FALSE),
    identical(revision$accepted_authority_id, authority_id),
    identical(revision$accepted_scientific_contract_sha256, scientific_sha256),
    identical(p1$value$authority_id, authority_id),
    identical(p2$value$authority_id, authority_id),
    identical(p2$value$scene_acceptance_id, p1$value$acceptance_id),
    identical(p3$value$authority_id, authority_id),
    identical(p3$value$base_spatial_acceptance_id, p2$value$acceptance_id),
    identical(p3$value$cache_id, cache$value$cache_id),
    identical(cache$value$authority_id, authority_id),
    identical(cache$value$base_spatial_acceptance_id, p2$value$acceptance_id),
    identical(p4$value$parent_acceptance_id, p3$value$acceptance_id),
    identical(p4$value$parent_cache_id, cache$value$cache_id),
    identical(p5$value$parent_cache_id, cache$value$cache_id),
    identical(p6$value$parents$authority_id, authority_id),
    identical(p6$value$parents$scene_acceptance_id, p1$value$acceptance_id),
    identical(p6$value$parents$base_spatial_acceptance_id, p2$value$acceptance_id),
    identical(p6$value$parents$p3_acceptance_id, p3$value$acceptance_id),
    identical(p6$value$parents$p3_cache_id, cache$value$cache_id),
    identical(p6$value$parents$p4_master_bank_id, p4$value$bank_id),
    identical(p6$value$parents$p5_acceptance_id, p5$value$acceptance_id)
  )
  if (!all(checks)) stop("S08 accepted P0-P6 lineage is inconsistent", call. = FALSE)
  list(
    scientific_revision_token = revision$revision_token,
    scientific_contract_sha256 = scientific_sha256,
    p0_authority_id = authority_id,
    p1_acceptance_id = p1$value$acceptance_id,
    p2_acceptance_id = p2$value$acceptance_id,
    p3_acceptance_id = p3$value$acceptance_id,
    p3_cache_id = cache$value$cache_id,
    p4_acceptance_id = p4$value$acceptance_id,
    p5_acceptance_id = p5$value$acceptance_id,
    p6_acceptance_id = p6$value$model_data_acceptance_id
  )
}

s08_training_inheritance <- function(root = ".") {
  methodology <- yaml::read_yaml(file.path(root, "config/current_methodology.yml"))
  config <- yaml::read_yaml(file.path(root, "config/training.yml"))
  expected <- c(
    identical(methodology$training$objective, "symmetric_scene_contrastive"),
    identical(methodology$model$information_preservation, FALSE),
    identical(methodology$model$reconstruction_decoders, FALSE),
    identical(config$training$views_per_scene, 2L),
    identical(config$optimizer$name, "AdamW"),
    identical(config$objective$directions, c("view_0_to_view_1", "view_1_to_view_0")),
    identical(config$ema$initialization, "exact_online_copy"),
    identical(config$ema$update_after_optimizer, TRUE),
    identical(config$queue$capacity, 8192L),
    identical(config$validation$evaluation_consumption, "prohibited")
  )
  if (!all(expected)) stop("S08 current training inheritance source mismatch", call. = FALSE)
  list(
    objective = list(
      name = "symmetric_scene_level_contrastive", scope = "scene",
      directions = config$objective$directions,
      temperature = config$objective$contrastive_temperature,
      negative_exclusion_distance_m = config$objective$negative_exclusion_distance_m
    ),
    views_per_scene = config$training$views_per_scene,
    online_branch = list(
      gradient_mode = "enabled",
      modality_masking = list(enabled = TRUE, probability = config$training$modality_mask_probability)
    ),
    target_branch = list(
      gradient_mode = "disabled", update = "ema_only",
      initialization = config$ema$initialization,
      update_after_optimizer = config$ema$update_after_optimizer
    ),
    ema = list(
      coefficient_source = "hyperparameter_configuration.ema_momentum",
      main_coefficient = config$ema$coefficient
    ),
    fifo_queue = list(
      enabled = TRUE, discipline = "FIFO", capacity = config$queue$capacity,
      embedding_dimension_source = "hyperparameter_configuration.d",
      main_embedding_dimension = config$queue$embedding_dimension,
      initialization = config$queue$initialization,
      gather_order = config$queue$gather_order,
      enqueue_views = config$queue$enqueue_views
    ),
    projection_head = list(enabled = TRUE, architecture = "d_to_256_to_d", output_normalization = "l2"),
    optimizer = list(
      name = config$optimizer$name,
      peak_learning_rate_source = "hyperparameter_configuration.peak_learning_rate",
      main_peak_learning_rate = config$optimizer$peak_learning_rate,
      weight_decay = config$optimizer$weight_decay, betas = config$optimizer$betas,
      epsilon = config$optimizer$eps, parameter_grouping = config$optimizer$parameter_grouping,
      gradient_clip = config$optimizer$gradient_clip
    ),
    scheduler = c(list(name = "linear_warmup_cosine_decay"), config$scheduler),
    training_horizon = list(
      maximum_epochs = config$training$maximum_epochs,
      updates_per_epoch = config$training$updates_per_epoch,
      maximum_updates = config$training$maximum_updates
    ),
    prohibited = list(
      information_preservation_objective = FALSE,
      reconstruction_decoder = FALSE,
      reconstruction_loss = FALSE
    )
  )
}

s08_selection_protocol <- function(root = ".") {
  config <- yaml::read_yaml(file.path(root, "config/training.yml"))$validation
  checks <- c(
    identical(config$interval_epochs, 5L),
    identical(config$primary_metric, "validation_retrieval_loss"),
    identical(config$equivalence_threshold, 0.0001),
    identical(config$secondary_metric, "mean_source_separation_margin"),
    identical(config$final_tie_break, "earlier_epoch"),
    identical(config$patience_events, 4L)
  )
  if (!all(checks)) stop("S08 checkpoint-selection configuration mismatch", call. = FALSE)
  list(
    contract_version = "current-training-selection-v1.0.0",
    validation_interval_epochs = config$interval_epochs,
    primary_metric = config$primary_metric, primary_direction = "minimize",
    equivalence_tolerance = config$equivalence_threshold,
    equivalence_comparison = "absolute_difference_strictly_less_than_tolerance",
    margin_metric = config$secondary_metric, margin_direction = "maximize",
    final_tiebreaker = "earlier_completed_epoch",
    early_stopping_patience = config$patience_events,
    minimum_delta = config$equivalence_threshold,
    patience_reset = "retrieval_loss_decrease_at_least_tolerance_only",
    candidate_eligibility = "VALIDATION_CHECKPOINT_COMMITTED_ONLY"
  )
}

s08_build_base_plan <- function(root = ".") {
  path <- tempfile(fileext = ".json")
  on.exit(if (file.exists(path)) unlink(path), add = TRUE)
  status <- system2(research_python_executable(), c(
    "-B", shQuote(normalizePath(file.path(root, "python/current_methodology.py"), mustWork = TRUE)),
    "--config", shQuote(normalizePath(file.path(root, "config/current_methodology.yml"), mustWork = TRUE)),
    "--output", shQuote(path)
  ))
  if (!identical(status, 0L) || !file.exists(path)) stop("Current experiment-plan base construction failed", call. = FALSE)
  jsonlite::read_json(path, simplifyVector = FALSE)
}

s08_contract_hashes <- function(training, selection, root = ".") {
  identity <- yaml::read_yaml(file.path(root, "config/s08_plan_identity.yml"))
  expected <- c(
    identical(identity$schema_version, "1.0.0"),
    identical(identity$contract_name, "current-s08-scientific-plan-identity-v1"),
    identical(identity$artifact_schema_version, "3.0.0"),
    identical(identity$implementation_hash_semantics, "scientific_plan_contract_compatibility"),
    grepl("^[0-9a-f]{64}$", identity$scientific_contract_implementation_sha256),
    identical(identity$operational_provenance_owner, "s09_training_authority"),
    identical(identity$operational_source_drift_blocking, FALSE)
  )
  if (!all(expected)) stop("S08 scientific-plan identity configuration mismatch", call. = FALSE)
  list(
    training_inheritance_sha256 = canonical_sha256(training),
    selection_protocol_sha256 = canonical_sha256(selection),
    implementation_sha256 = identity$scientific_contract_implementation_sha256
  )
}

s08_plan_value <- function(lineage, root = ".") {
  base <- s08_build_base_plan(root)
  training <- s08_training_inheritance(root)
  selection <- s08_selection_protocol(root)
  base$schema_version <- "3.0.0"
  base$dissertation_commit <- NULL
  base$lineage <- lineage
  base$dissertation_provenance <- list(
    authority_commit = yaml::read_yaml(file.path(root, "config/current_methodology.yml"))$dissertation_commit,
    invalidation_policy = "explicit_revision_only", source_drift_blocking = FALSE
  )
  base$training_inheritance <- training
  base$selection_protocol <- selection
  base$contract_hashes <- s08_contract_hashes(training, selection, root)
  base$plan_id <- NULL
  base$content_sha256 <- NULL
  base$status <- NULL
  digest <- canonical_sha256(base)
  c(base, list(plan_id = paste0("s08plan_", substr(digest, 1L, 24L)), content_sha256 = digest, status = "PASS"))
}

s08_validate_plan <- function(value, lineage, root = ".") {
  base <- s08_build_base_plan(root)
  training <- s08_training_inheritance(root)
  selection <- s08_selection_protocol(root)
  content <- value[setdiff(names(value), c("plan_id", "content_sha256", "status"))]
  digest <- canonical_sha256(content)
  expected_ids <- c(
    "main", "ofat_d_64", "ofat_d_256", "ofat_K_aug_4", "ofat_K_aug_16",
    "ofat_augmentation_intensity_0.5", "ofat_augmentation_intensity_2.0",
    "ofat_ema_momentum_0.99", "ofat_peak_learning_rate_0.002",
    "ofat_peak_learning_rate_0.003", "ofat_peak_learning_rate_0.005"
  )
  comparison_ids <- c("FM", "A1", "A2", "A3", "A4", "A5", paste0("B", 1:9), "SSV", "DS")
  ofat_ids <- vapply(value$hyperparameter_configurations, `[[`, character(1L), "configuration_id")
  observed_comparisons <- vapply(value$comparison_configurations, `[[`, character(1L), "name")
  checks <- c(
    identical(value$schema_version, "3.0.0"), identical(value$status, "PASS"),
    identical(value$plan_id, paste0("s08plan_", substr(digest, 1L, 24L))),
    identical(value$content_sha256, digest), s08_json_equal(value$lineage, lineage),
    s08_json_equal(value$scene_split, base$scene_split),
    s08_json_equal(value$model, base$model), s08_json_equal(value$training, base$training),
    s08_json_equal(value$training_inheritance, training),
    s08_json_equal(value$selection_protocol, selection),
    s08_json_equal(value$contract_hashes, s08_contract_hashes(training, selection, root)),
    s08_json_equal(value$hyperparameter_configurations, base$hyperparameter_configurations),
    s08_json_equal(value$comparison_configurations, base$comparison_configurations),
    identical(ofat_ids, expected_ids), identical(length(unique(ofat_ids)), 11L),
    identical(observed_comparisons, comparison_ids), identical(length(unique(observed_comparisons)), 17L),
    identical(value$model$information_preservation, FALSE),
    identical(value$model$reconstruction_decoders, FALSE)
  )
  if (!all(checks)) stop("Current S08 experiment-plan contract validation failed", call. = FALSE)
  invisible(TRUE)
}

build_current_experiment_plan <- function(sources, methodology_authority, scene_acceptance,
                                          spatial_acceptance, scene_dataset_acceptance,
                                          bank_acceptance, query_acceptance, dataset_acceptance,
                                          root = ".",
                                          dissertation_root = path.expand("~/dhnyu-masters-dissertation"),
                                          publication_root = "/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_plan") {
  expected <- current_experiment_plan_sources(root, dissertation_root)
  if (!identical(sort(normalizePath(sources, mustWork = TRUE)), sort(expected))) {
    stop("Current experiment-plan source tracking mismatch", call. = FALSE)
  }
  lineage <- s08_current_lineage(methodology_authority, scene_acceptance, spatial_acceptance,
                                 scene_dataset_acceptance, bank_acceptance,
                                 query_acceptance, dataset_acceptance, root)
  value <- s08_plan_value(lineage, root)
  s08_validate_plan(value, lineage, root)
  cfg <- yaml::read_yaml(file.path(root, "config/current_methodology.yml"))
  final_dir <- file.path(publication_root, paste0("current_", substr(cfg$dissertation_commit, 1L, 16L)))
  output <- publish_deterministic_directory(final_dir, "current_experiment_plan.json", function(stage) {
    write_json_file(value, file.path(stage, "current_experiment_plan.json"))
  })
  validate_json_schema_file(output, file.path(root, "config/schemas/current_experiment_plan_v3.schema.json"))
  s08_validate_plan(jsonlite::read_json(output, simplifyVector = FALSE), lineage, root)
  normalizePath(output, mustWork = TRUE)
}
