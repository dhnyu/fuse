# Dissertation experimental setup and training configuration: deterministic I20
# planning only. This module never constructs an optimizer or performs training.

training_plan_contract_paths <- function(root = getwd(), thesis_root = path.expand("~/dhnyu-masters-dissertation/template")) {
  c(file.path(root, c("config/training_plan.yml", "config/schemas/prototype_training_plan.schema.json",
                      "R/research_training_plan.R")),
    file.path(thesis_root, c("materials/tables/results-04-training-configuration-table.typ",
                             "sections/chapters/results/01-experimental-setup.typ",
                             "sections/chapters/methodology/06-model-training.typ")))
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
                                          prototype_encoder_smoke,
                                          prototype_augmentation_benchmark,
                                          training_plan_contract_files,
                                          workers = 1L, threads = 1L) {
  if (!identical(as.integer(workers), 1L) || !identical(as.integer(threads), 1L)) stop("I20 planning requires one worker/thread", call. = FALSE)
  files <- normalizePath(training_plan_contract_files, mustWork = TRUE)
  by_name <- setNames(files, basename(files))
  config <- yaml::read_yaml(by_name[["training_plan.yml"]])
  dataset_path <- training_plan_manifest_path(prototype_training_dataset_acceptance, "accepted_training_dataset_manifest.json")
  encoder_path <- training_plan_manifest_path(prototype_encoder_smoke, "prototype_encoder_manifest.json")
  augmentation_path <- training_plan_manifest_path(prototype_augmentation_benchmark, "prototype_augmentation_manifest.json")
  dataset <- jsonlite::read_json(dataset_path, simplifyVector = FALSE)
  encoder <- jsonlite::read_json(encoder_path, simplifyVector = FALSE)
  augmentation <- jsonlite::read_json(augmentation_path, simplifyVector = FALSE)
  expected <- config$identity
  observed <- list(accepted_dataset_id = dataset$training_dataset_id,
                   encoder_acceptance_id = encoder$encoder_acceptance_id,
                   augmentation_acceptance_id = augmentation$augmentation_acceptance_id)
  if (!identical(observed, expected[names(observed)]) || !identical(dataset$status, "READY") ||
      !identical(encoder$status, "PASS") || !identical(augmentation$status, "PASS")) stop("I20 upstream identity/status mismatch", call. = FALSE)
  if (!identical(encoder$architecture$trainable_parameters, 1996534L) || !identical(encoder$architecture$precision, "float32")) stop("I20 encoder feasibility mismatch", call. = FALSE)

  scientific <- list(dataset = training_plan_record(dataset_path), encoder = training_plan_record(encoder_path),
                     augmentation = training_plan_record(augmentation_path), training = config[c("runs", "data", "optimization", "validation", "resume")],
                     contract_sha256 = sha256_file(by_name[["training_plan.yml"]]), schema_sha256 = sha256_file(by_name[["prototype_training_plan.schema.json"]]),
                     implementation_sha256 = sha256_file(by_name[["research_training_plan.R"]]), dissertation_commit = expected$dissertation_commit)
  plan_id <- short_hash_id("ptp_", scientific)
  parameter_count <- as.numeric(encoder$architecture$trainable_parameters)
  queue_bytes <- config$optimization$queue_size * 128 * 4 + config$optimization$queue_size * (2 * 8 + 8)
  checkpoint_bytes <- 4 * parameter_count * 4 + queue_bytes + 1024^2
  elapsed <- as.numeric(encoder$gpu_runtime$elapsed_seconds)
  representative_count <- length(encoder$smoke$representative_scenes)
  wall_upper_seconds <- elapsed / representative_count * config$resource_estimate$maximum_microbatches
  resources <- list(single_gpu_float32 = TRUE, peak_vram_bytes = encoder$gpu_runtime$peak_allocated_bytes,
                    wall_time_estimate_seconds = wall_upper_seconds, wall_time_estimate_method = config$resource_estimate$wall_time_method,
                    checkpoint_bytes_estimate = checkpoint_bytes, checkpoint_count_range = config$resource_estimate$checkpoint_count_range,
                    maximum_checkpoint_storage_bytes = checkpoint_bytes * max(unlist(config$resource_estimate$checkpoint_count_range)))
  runs <- lapply(seq_along(config$runs$seeds), function(i) {
    seed <- as.integer(config$runs$seeds[[i]])
    run_scientific <- list(plan_id = plan_id, order = i, seed = seed, dataset = observed$accepted_dataset_id,
                           encoder = observed$encoder_acceptance_id, augmentation = observed$augmentation_acceptance_id,
                           execution_mode = config$runs$execution_mode, precision = config$runs$precision,
                           training = scientific$training)
    list(run_id = short_hash_id("ptr_", run_scientific), run_order = i, seed = seed,
         execution_mode = config$runs$execution_mode, requested_gpu_count = config$runs$requested_gpu_count,
         preferred_gpu = NULL, precision = config$runs$precision, dataset_manifest = training_plan_record(dataset_path),
         encoder_manifest = training_plan_record(encoder_path), augmentation_manifest = training_plan_record(augmentation_path),
         hard_budgets = config$data$hard_budgets, effective_batch_scenes = config$data$effective_batch_scenes,
         gradient_accumulation = config$data$accumulation, optimizer = config$optimization,
         validation = config$validation, resume = config$resume, resource_estimate = resources,
         output_root = file.path(dirname(dataset_path), "runs", short_hash_id("ptr_", run_scientific)))
  })
  final_dir <- file.path(config$output$root, plan_id)
  output_names <- c(config$output$spec_name, config$output$qc_name, config$output$manifest_name)
  outputs <- publish_deterministic_directory(final_dir, output_names, writer = function(stage) {
    write_json_file(runs[[1L]], file.path(stage, output_names[[1L]]))
    write_json_file(list(status = "PASS", optimizer_step_performed = FALSE, run_count = length(runs), resources = resources), file.path(stage, output_names[[2L]]))
    manifest <- list(schema_version = "1.0.0", status = "PASS", plan_id = plan_id, run_count = length(runs),
                     dataset_identity = observed$accepted_dataset_id, encoder_identity = observed$encoder_acceptance_id,
                     augmentation_identity = observed$augmentation_acceptance_id, scientific_identity = scientific,
                     resources = resources, runs = lapply(runs, function(x) x[c("run_id", "run_order", "seed")]),
                     outputs = lapply(output_names[1:2], function(name) list(
                       relative_path = name, size_bytes = as.numeric(file.info(file.path(stage, name))$size),
                       sha256 = sha256_file(file.path(stage, name))
                     )))
    write_json_file(manifest, file.path(stage, output_names[[3L]]))
  })
  list(list(run_id = runs[[1L]]$run_id, plan_id = plan_id, .path = outputs[basename(outputs) == config$output$spec_name], files = outputs))
}
