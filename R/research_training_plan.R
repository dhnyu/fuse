# Dissertation experimental setup and training configuration: deterministic I20
# planning only. This module never constructs an optimizer or performs training.

training_plan_contract_paths <- function(root = getwd(), thesis_root = path.expand("~/dhnyu-masters-dissertation/template")) {
  c(file.path(root, c("config/training_plan.yml", "config/joint_model.yml", "config/model_architecture.yml",
                      "config/augmentation.yml", "config/distributed_training.yml", "config/schemas/prototype_training_plan.schema.json",
                      "python/prototype_joint_model.py", "python/prototype_encoder.py",
                      "python/prototype_validation.py", "python/run_prototype_training.py",
                      "R/research_training_plan.R")),
    file.path(thesis_root, c("materials/tables/results-04-training-configuration-table.typ",
                             "sections/chapters/results/01-experimental-setup.typ",
                             "sections/chapters/methodology/06-model-training.typ",
                             "sections/appendices/appendix-b.typ", "sections/appendices/appendix-c.typ")))
}

training_plan_record <- function(path) {
  list(path = normalizePath(path, mustWork = TRUE), size_bytes = as.numeric(file.info(path)$size), sha256 = sha256_file(path))
}

training_plan_manifest_path <- function(paths, basename_expected) {
  value <- normalizePath(unlist(paths, use.names = FALSE), mustWork = TRUE)
  selected <- value[basename(value) == basename_expected]
  if (length(selected) != 1L) stop("I20 upstream manifest missing: ", basename_expected, call. = FALSE)
  selected
}

build_prototype_training_plan <- function(prototype_training_dataset_acceptance,
                                          prototype_dataloader_smoke,
                                          prototype_scientific_geometry_roundtrip,
                                          prototype_encoder_smoke,
                                          prototype_augmentation_benchmark,
                                          prototype_joint_model_smoke,
                                          prototype_distributed_joint_model_smoke,
                                          training_plan_contract_files,
                                          workers = 1L, threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) stop("I20 planning requires one worker/thread", call. = FALSE)
  files <- normalizePath(training_plan_contract_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  config <- yaml::read_yaml(by_name[["training_plan.yml"]])
  joint <- yaml::read_yaml(by_name[["joint_model.yml"]])
  model <- yaml::read_yaml(by_name[["model_architecture.yml"]])
  augmentation_config <- yaml::read_yaml(by_name[["augmentation.yml"]])
  derived_steps_per_epoch <- as.integer(config$data$training_scenes / config$data$effective_batch_scenes)
  if (config$data$training_scenes %% config$data$effective_batch_scenes != 0L ||
      !identical(as.integer(config$optimization$optimizer_steps_per_epoch), derived_steps_per_epoch) ||
      !identical(config$optimization$schedule_unit,
                 "epoch_converted_to_optimizer_steps_from_training_population_and_effective_batch") ||
      !identical(config$optimization$optimizer_steps_per_epoch_derivation,
                 "training_scenes_divided_by_effective_batch_scenes_exact") ||
      !identical(config$optimization$warmup_optimizer_steps_derivation,
                 "warmup_epochs_times_optimizer_steps_per_epoch") ||
      !identical(config$optimization$scheduler_step_order, "optimizer_step_then_scheduler_step")) {
    stop("I20 optimizer schedule population/step contract mismatch", call. = FALSE)
  }
  if (!identical(config$validation$checkpoint_selection,
                 "highest_MRR_then_lowest_validation_retrieval_loss_then_highest_mean_positive_hardest_negative_margin_then_earliest_epoch") ||
      !identical(config$validation$patience_reset, "higher_MRR_or_saturated_retrieval_loss_min_delta") ||
      !identical(config$validation$evaluation_and_test_for_selection, "forbidden") ||
      !isTRUE(config$validation$fixed_query_views) || !isTRUE(config$validation$fixed_query_augmentation_seed) ||
      !isTRUE(config$validation$fixed_candidate_gallery)) {
    stop("I20 validation selection/isolation contract mismatch", call. = FALSE)
  }
  dataset_path <- training_plan_manifest_path(prototype_training_dataset_acceptance, "accepted_training_dataset_manifest.json")
  encoder_path <- training_plan_manifest_path(prototype_encoder_smoke, "prototype_encoder_manifest.json")
  augmentation_path <- training_plan_manifest_path(prototype_augmentation_benchmark, "prototype_augmentation_manifest.json")
  loader_path <- training_plan_manifest_path(prototype_dataloader_smoke, "prototype_dataloader_smoke.json")
  gate_path <- training_plan_manifest_path(prototype_scientific_geometry_roundtrip, "scientific_geometry_roundtrip_manifest.json")
  joint_path <- training_plan_manifest_path(prototype_joint_model_smoke, "prototype_joint_model_manifest.json")
  distributed_path <- training_plan_manifest_path(prototype_distributed_joint_model_smoke, "distributed_joint_model_manifest.json")
  dataset <- jsonlite::read_json(dataset_path, simplifyVector = FALSE)
  encoder <- jsonlite::read_json(encoder_path, simplifyVector = FALSE)
  augmentation <- jsonlite::read_json(augmentation_path, simplifyVector = FALSE)
  loader <- jsonlite::read_json(loader_path, simplifyVector = FALSE)
  gate <- jsonlite::read_json(gate_path, simplifyVector = FALSE)
  joint_manifest <- jsonlite::read_json(joint_path, simplifyVector = FALSE)
  distributed_manifest <- jsonlite::read_json(distributed_path, simplifyVector = FALSE)
  expected <- config$identity
  observed <- list(accepted_dataset_id = dataset$training_dataset_id,
                   encoder_acceptance_id = encoder$encoder_acceptance_id,
                   joint_model_acceptance_id = joint_manifest$joint_model_acceptance_id,
                   distributed_joint_acceptance_id = distributed_manifest$distributed_joint_acceptance_id,
                   augmentation_acceptance_id = augmentation$augmentation_acceptance_id,
                   no_op_gate_id = gate$gate_id, dataloader_smoke_id = loader$smoke_id)
  if (!identical(observed, expected[names(observed)]) || !identical(dataset$status, "READY") ||
      !identical(encoder$status, "PASS") || !identical(augmentation$status, "PASS") ||
      !identical(loader$status, "READY") || !identical(gate$status, "PASS") ||
      !identical(joint_manifest$status, "PASS") || !identical(distributed_manifest$status, "PASS")) stop("I20 upstream identity/status mismatch", call. = FALSE)
  if (!identical(encoder$architecture$trainable_parameters, 1996534L) || !identical(encoder$architecture$precision, "float32")) stop("I20 encoder feasibility mismatch", call. = FALSE)

  joint_scientific <- joint[c("numerical_policy", "modality_masking", "decoders", "loss", "contrastive")]
  model_scientific <- model[c("dimensions", "position", "geometry", "architecture")]
  augmentation_scientific <- augmentation_config[c("rng", "entity_removal", "geometry", "attributes", "categorical", "raster", "relations")]
  training_scientific <- config[c("runs", "data", "optimization", "validation", "resume")]
  # Execution semantics affect immutable run identity, while host-specific paths remain excluded.
  execution_identity <- config$execution[c(
    "distributed_strategy", "distributed_backend", "world_size", "workers_per_rank",
    "rank_logical_batch_scenes", "persistent_workers", "pin_memory", "prefetch_factor",
    "native_threads_per_worker", "process_start_method"
  )]
  scoped_hash <- function(value) digest::digest(value, algo = "sha256", serialize = TRUE)
  dissertation_names <- c(
    "results-04-training-configuration-table.typ", "01-experimental-setup.typ", "06-model-training.typ",
    "appendix-b.typ", "appendix-c.typ"
  )
  dissertation_sources <- lapply(dissertation_names, function(name) training_plan_record(by_name[[name]]))
  names(dissertation_sources) <- dissertation_names
  scientific <- list(dataset = training_plan_record(dataset_path), loader = training_plan_record(loader_path),
                     no_op_gate = training_plan_record(gate_path), encoder = training_plan_record(encoder_path),
                     augmentation = training_plan_record(augmentation_path), joint_model = training_plan_record(joint_path),
                     distributed_joint_model = training_plan_record(distributed_path),
                     model_config = model_scientific, decoder_loss_masking_config = joint_scientific,
                     augmentation_config = augmentation_scientific, training_config = training_scientific,
                     execution_contract = execution_identity,
                     validation_implementation = training_plan_record(by_name[["prototype_validation.py"]]),
                     scheduler_implementation = training_plan_record(by_name[["run_prototype_training.py"]]),
                     dissertation_sources = dissertation_sources,
                     scientific_hashes = list(model = scoped_hash(model_scientific), joint = scoped_hash(joint_scientific),
                                              augmentation = scoped_hash(augmentation_scientific), training = scoped_hash(training_scientific),
                                              execution = scoped_hash(execution_identity),
                                              validation_implementation = sha256_file(by_name[["prototype_validation.py"]]),
                                              scheduler_implementation = sha256_file(by_name[["run_prototype_training.py"]])),
                     schema_sha256 = sha256_file(by_name[["prototype_training_plan.schema.json"]]),
                     implementation_sha256 = sha256_file(by_name[["research_training_plan.R"]]), dissertation_commit = expected$dissertation_commit)
  plan_id <- short_hash_id("ptp_", scientific)
  encoder_parameter_count <- as.numeric(encoder$architecture$trainable_parameters)
  joint_parameter_count <- as.numeric(joint_manifest$architecture$joint_trainable_parameters)
  queue_bytes <- config$optimization$queue_size * 128 * 4 + config$optimization$queue_size * (2 * 8 + 8)
  checkpoint_bytes <- 4 * (3 * joint_parameter_count + encoder_parameter_count) + queue_bytes + 1024^2
  elapsed <- as.numeric(encoder$gpu_runtime$elapsed_seconds)
  representative_count <- length(encoder$smoke$representative_scenes)
  wall_upper_seconds <- elapsed / representative_count * config$resource_estimate$maximum_microbatches
  resources <- list(single_gpu_float32 = FALSE, dual_gpu_float32 = TRUE,
                    distributed_strategy = config$execution$distributed_strategy,
                    requested_gpu_count = config$runs$requested_gpu_count,
                    peak_vram_bytes_per_rank = encoder$gpu_runtime$peak_allocated_bytes,
                    wall_time_estimate_seconds = wall_upper_seconds,
                    wall_time_estimate_method = config$resource_estimate$wall_time_method,
                    checkpoint_bytes_estimate = checkpoint_bytes, checkpoint_count_range = config$resource_estimate$checkpoint_count_range,
                    maximum_checkpoint_storage_bytes = checkpoint_bytes * max(unlist(config$resource_estimate$checkpoint_count_range)))
  runs <- lapply(seq_along(config$runs$seeds), function(i) {
    seed <- as.integer(config$runs$seeds[[i]])
    run_scientific <- list(plan_id = plan_id, order = i, seed = seed, dataset = observed$accepted_dataset_id,
                           encoder = observed$encoder_acceptance_id, augmentation = observed$augmentation_acceptance_id,
                           distributed_joint_model = observed$distributed_joint_acceptance_id,
                           execution_mode = config$runs$execution_mode, precision = config$runs$precision,
                           scientific_hashes = scientific$scientific_hashes, training = training_scientific,
                           execution_contract = execution_identity)
    list(plan_id = plan_id, run_id = short_hash_id("ptr_", run_scientific), run_order = i, seed = seed,
         execution_mode = config$runs$execution_mode, requested_gpu_count = config$runs$requested_gpu_count,
         preferred_gpu = NULL, precision = config$runs$precision, dataset_manifest = training_plan_record(dataset_path),
         dataloader_manifest = training_plan_record(loader_path), no_op_gate_manifest = training_plan_record(gate_path),
         encoder_manifest = training_plan_record(encoder_path), joint_model_manifest = training_plan_record(joint_path),
         distributed_joint_model_manifest = training_plan_record(distributed_path),
         augmentation_manifest = training_plan_record(augmentation_path),
         model_config = model_scientific, decoder_loss_masking_config = joint_scientific,
         augmentation_config = augmentation_scientific, scientific_hashes = scientific$scientific_hashes,
         hard_budgets = config$data$hard_budgets, training_scenes = config$data$training_scenes,
         effective_batch_scenes = config$data$effective_batch_scenes,
         gradient_accumulation = config$data$accumulation, optimizer = config$optimization,
         validation = config$validation, resume = config$resume, execution = config$execution, resource_estimate = resources,
         output_root = file.path(dirname(dataset_path), "runs", short_hash_id("ptr_", run_scientific)))
  })
  final_dir <- file.path(config$output$root, plan_id)
  output_names <- c(config$output$spec_name, config$output$qc_name, config$output$manifest_name)
  outputs <- publish_deterministic_directory(final_dir, output_names, writer = function(stage) {
    write_json_file(runs[[1L]], file.path(stage, output_names[[1L]]))
    write_json_file(list(status = "PASS", optimizer_step_performed = FALSE, run_count = length(runs), resources = resources), file.path(stage, output_names[[2L]]))
    manifest <- list(schema_version = "1.0.0", status = "PASS", plan_id = plan_id, run_count = length(runs),
                     dataset_identity = observed$accepted_dataset_id,
                     dataloader_identity = observed$dataloader_smoke_id,
                     no_op_gate_identity = observed$no_op_gate_id,
                     encoder_identity = observed$encoder_acceptance_id,
                     augmentation_identity = observed$augmentation_acceptance_id,
                     joint_model_identity = observed$joint_model_acceptance_id,
                     distributed_joint_model_identity = observed$distributed_joint_acceptance_id,
                     scientific_identity = scientific,
                     resources = resources, runs = lapply(runs, function(x) x[c("run_id", "run_order", "seed")]),
                     outputs = lapply(output_names[1:2], function(name) list(
                       relative_path = name, size_bytes = as.numeric(file.info(file.path(stage, name))$size),
                       sha256 = sha256_file(file.path(stage, name))
                     )))
    write_json_file(manifest, file.path(stage, output_names[[3L]]))
  })
  list(list(run_id = runs[[1L]]$run_id, plan_id = plan_id, .path = outputs[basename(outputs) == config$output$spec_name], files = outputs))
}
