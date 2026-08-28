p5_contract_paths <- function(root = getwd()) {
  root <- normalizePath(root, mustWork = TRUE)
  cfg <- yaml::read_yaml(file.path(root, "config/p5_deterministic_queries.yml"))
  c(config = file.path(root, "config/p5_deterministic_queries.yml"),
    blueprint = file.path(root, "blueprint/targets_implementation_blueprint.md"),
    vapply(cfg$schemas, function(path) file.path(root, path), character(1L)),
    helper = file.path(root, "R/research_fixed_queries.R"),
    python = file.path(root, "python/p5_fixed_queries.py"),
    cli = file.path(root, "scripts/p5_fixed_queries.py"),
    targets = file.path(root, "targets/research_fixed_queries.R"))
}

p5_load_spec <- function(files, root = getwd()) {
  files <- normalizePath(files, mustWork = TRUE)
  cfg <- yaml::read_yaml(files[basename(files) == "p5_deterministic_queries.yml"])
  schemas <- setNames(vapply(cfg$schemas, function(path) {
    files[basename(files) == basename(path)][[1L]]
  }, character(1L)), names(cfg$schemas))
  relative <- sub(paste0("^", normalizePath(root, mustWork = TRUE), "/"), "", files)
  scientific <- grepl("^(config/p5_|config/schemas/p5_|R/research_fixed_queries|python/p5_|scripts/p5_|targets/research_fixed_queries)", relative)
  scientific_config <- cfg
  scientific_config$publication_root <- NULL
  scientific_config$execution <- NULL
  implementation_hash <- p0_scientific_sha256(list(
    version = cfg$implementation_version,
    files = lapply(which(scientific)[order(relative[scientific], method = "radix")], function(index) {
      sha256 <- if (identical(relative[[index]], "config/p5_deterministic_queries.yml")) {
        p0_scientific_sha256(scientific_config)
      } else {
        sha256_file(files[[index]])
      }
      list(path = relative[[index]], sha256 = sha256)
    })
  ))
  list(config = cfg, files = files, schemas = schemas, implementation_hash = implementation_hash)
}

p5_read <- function(paths, name) jsonlite::read_json(artifact_path(paths, name), simplifyVector = FALSE)

p5_build_contract <- function(evaluation_methodology_contract, augmentation_methodology_contract,
                              original_scene_dataset_acceptance, augmentation_profile_plan,
                              augmentation_bank_plan, contract_files) {
  spec <- p5_load_spec(contract_files); cfg <- spec$config
  evaluation <- p5_read(evaluation_methodology_contract, "evaluation_methodology_contract.json")
  augmentation <- p5_read(augmentation_methodology_contract, "augmentation_methodology_contract.json")
  p3 <- p5_read(original_scene_dataset_acceptance, "original_scene_dataset_acceptance.json")
  p4_profile <- p5_read(augmentation_profile_plan, "augmentation_profile_plan.json")
  p4_plan <- augmentation_bank_plan[[1L]]
  if (evaluation$status != "PASS" || augmentation$status != "PASS" ||
      evaluation$canonical_contract$validation$originals != 400L ||
      evaluation$canonical_contract$validation$augmented_queries != 800L ||
      evaluation$canonical_contract$evaluation$originals != 1600L ||
      evaluation$canonical_contract$evaluation$augmented_queries != 3200L ||
      evaluation$canonical_contract$fixed_query_profile != 1 ||
      p3$cache_id != cfg$p3_cache_id || p3$acceptance_id != cfg$p3_acceptance_id ||
      augmentation$contract_id != cfg$augmentation_contract_id ||
      p4_profile$supplement_version != cfg$p4_supplement_id ||
      p4_plan$bank_id != cfg$p4_master_bank_id ||
      p4_plan$implementation_hash != cfg$p4_accepted_augmenter_sha256) {
    stop("P5 deterministic-query authority/parent mismatch", call. = FALSE)
  }
  value <- list(
    schema_version = cfg$schema_version, status = "PASS", supplement_id = cfg$supplement_id,
    authority_id = cfg$authority_id, augmentation_contract_id = cfg$augmentation_contract_id,
    p3_cache_id = cfg$p3_cache_id, p3_acceptance_id = cfg$p3_acceptance_id,
    p4_supplement_id = cfg$p4_supplement_id,
    p4_accepted_augmenter_sha256 = cfg$p4_accepted_augmenter_sha256,
    profile = cfg$profile, namespaces = cfg$namespaces, query_indices = cfg$query_indices,
    seed = cfg$seed, publication = cfg$publication, implementation_hash = spec$implementation_hash
  )
  value$content_sha256 <- p0_scientific_sha256(value)
  value$contract_id <- paste0("fqc_", substr(value$content_sha256, 1L, 24L))
  root <- file.path(cfg$publication_root, "contracts", value$contract_id)
  p1_publish_immutable_bundle(root, "fixed_query_contract.json", function(stage) {
    output <- write_json_file(value, file.path(stage, "fixed_query_contract.json"))
    validate_json_schema_file(output, spec$schemas[["supplement"]])
  })
}

p5_build_shard_plan <- function(fixed_query_methodology_contract, spatial_scene_index,
                                original_scene_cache_index, original_scene_serialization_shard,
                                original_scene_dataset_acceptance, augmentation_bank_plan,
                                contract_files) {
  spec <- p5_load_spec(contract_files); cfg <- spec$config
  contract <- p5_read(fixed_query_methodology_contract, "fixed_query_contract.json")
  p3 <- p5_read(original_scene_dataset_acceptance, "original_scene_dataset_acceptance.json")
  if (contract$status != "PASS" || p3$status != "PASS") stop("P5 plan parent rejection", call. = FALSE)
  cache_index <- arrow::read_parquet(artifact_path(original_scene_cache_index, "scene_to_shard.parquet"), as_data_frame = TRUE)
  scene_index <- arrow::read_parquet(artifact_path(spatial_scene_index, "spatial_scene_index.parquet"), as_data_frame = TRUE)
  rows <- merge(cache_index, scene_index[, c("scene_id", "split")], by = "scene_id", sort = FALSE)
  rows <- rows[rows$split %in% c("validation", "evaluation"), ]
  rows <- rows[order(rows$split, rows$scene_id, method = "radix"), ]
  if (!identical(unname(as.integer(table(rows$split)[c("validation", "evaluation")])), c(400L, 1600L))) {
    stop("P5 P1/P3 split population mismatch", call. = FALSE)
  }
  parents <- p4_parent_tar_records(original_scene_serialization_shard)
  parent_map <- setNames(parents, vapply(parents, `[[`, character(1L), "branch_id"))
  p4_plan <- augmentation_bank_plan[[1L]]
  resources_path <- p4_plan$resources_path
  scientific <- list(
    supplement = contract$content_sha256, evaluation_contract = cfg$authority_id,
    p3_cache_id = p3$cache_id, p3_acceptance_id = p3$acceptance_id,
    p3_aggregate = p3$aggregate_content_sha256,
    p4_bank_id = cfg$p4_master_bank_id, p4_index_id = cfg$p4_logical_index_id,
    p4_accepted_augmenter_sha256 = cfg$p4_accepted_augmenter_sha256,
    parent_payloads = lapply(parents[order(names(parent_map), method = "radix")], function(parent) parent[c("branch_id", "sha256")]),
    populations = lapply(cfg$namespaces, function(value) value[c("namespace", "originals", "queries", "gallery")]),
    query_indices = cfg$query_indices, profile = cfg$profile, implementation_hash = spec$implementation_hash
  )
  fingerprint <- p0_scientific_sha256(scientific)
  authority_id <- paste0("fqa_", substr(fingerprint, 1L, 24L))
  plan_id <- paste0("fqp_", substr(p0_scientific_sha256(list(authority_id, "plan")), 1L, 24L))
  groups <- split(rows, interaction(rows$split, rows$branch_id, drop = TRUE, lex.order = TRUE))
  branches <- unname(lapply(groups, function(group) {
    split_name <- unique(group$split); parent_id <- unique(group$branch_id)
    if (length(split_name) != 1L || length(parent_id) != 1L) stop("P5 noncanonical plan group", call. = FALSE)
    parent <- parent_map[[parent_id]]; namespace <- cfg$namespaces[[split_name]]$namespace
    branch_id <- paste0("fqb_", substr(p0_scientific_sha256(list(authority_id, namespace, parent_id)), 1L, 24L))
    list(schema_version = cfg$schema_version, query_authority_id = authority_id, plan_id = plan_id,
         branch_id = branch_id, namespace = namespace, split = split_name, profile = cfg$profile,
         parent_branch_id = parent_id, parent_tar = parent$path, parent_tar_sha256 = parent$sha256,
         scene_ids = as.list(sort(group$scene_id, method = "radix")), resources_path = resources_path,
         implementation_hash = spec$implementation_hash,
         output_directory = file.path(cfg$publication_root, authority_id, namespace, "shards", branch_id),
         config = cfg)
  }))
  branches <- branches[order(vapply(branches, `[[`, character(1L), "branch_id"), method = "radix")]
  if (sum(vapply(branches, function(branch) length(branch$scene_ids), integer(1L))) != 2000L) stop("P5 plan coverage mismatch", call. = FALSE)
  plan <- list(schema_version = cfg$schema_version, status = "PASS", query_authority_id = authority_id,
               plan_id = plan_id, supplement_id = cfg$supplement_id, parent_cache_id = p3$cache_id,
               parent_acceptance_id = p3$acceptance_id, branch_count = length(branches), scene_count = 2000L,
               query_count = 4000L, split_counts = list(validation = 400L, evaluation = 1600L),
               scientific_fingerprint = fingerprint, implementation_hash = spec$implementation_hash,
               branches = unname(lapply(branches, function(branch) branch[c("branch_id", "namespace", "split", "parent_branch_id", "scene_ids")])))
  plan_dir <- file.path(cfg$publication_root, authority_id, "plans", plan_id)
  filenames <- c("fixed_query_plan.json", paste0("spec-", vapply(branches, `[[`, character(1L), "branch_id"), ".json"))
  paths <- p1_publish_immutable_bundle(plan_dir, filenames, function(stage) {
    plan_path <- write_json_file(plan, file.path(stage, filenames[[1L]]))
    validate_json_schema_file(plan_path, spec$schemas[["plan"]])
    for (index in seq_along(branches)) write_json_file(branches[[index]], file.path(stage, filenames[[index + 1L]]))
  })
  lapply(branches, function(branch) {
    branch$.path <- paths[basename(paths) == paste0("spec-", branch$branch_id, ".json")]
    branch$.plan_path <- paths[basename(paths) == "fixed_query_plan.json"]
    branch
  })
}

p5_filter_plan <- function(plan, split) plan[vapply(plan, function(branch) identical(branch$split, split), logical(1L))]

p5_build_query_shard <- function(plan_branch, contract_files) {
  spec <- p5_load_spec(contract_files)
  Sys.setenv(OMP_NUM_THREADS = "1", OPENBLAS_NUM_THREADS = "1", MKL_NUM_THREADS = "1",
             BLIS_NUM_THREADS = "1", VECLIB_MAXIMUM_THREADS = "1", NUMEXPR_NUM_THREADS = "1",
             GDAL_NUM_THREADS = "1", ARROW_NUM_THREADS = "1", PYTHONDONTWRITEBYTECODE = "1")
  data.table::setDTthreads(1L)
  final <- plan_branch$output_directory; payload <- paste0(plan_branch$branch_id, ".tar")
  existing <- file.path(final, c(payload, "branch_manifest.json", "execution.json"))
  if (all(file.exists(existing))) {
    manifest <- jsonlite::read_json(existing[[2L]], simplifyVector = FALSE)
    validate_json_schema_file(existing[[2L]], spec$schemas[["shard"]])
    if (manifest$branch_id != plan_branch$branch_id || manifest$payload$sha256 != sha256_file(existing[[1L]])) {
      stop("P5 immutable branch mismatch: ", plan_branch$branch_id, call. = FALSE)
    }
    return(normalizePath(existing, mustWork = TRUE))
  }
  publish_deterministic_directory(final, c(payload, "branch_manifest.json", "execution.json"),
    compare_basenames = c(payload, "branch_manifest.json"), writer = function(stage) {
      build <- file.path(stage, "build")
      result <- system2(research_python_executable(), c(
        spec$files[basename(spec$files) == "p5_fixed_queries.py" & grepl("/scripts/", spec$files)],
        "branch", "--spec", plan_branch$.path, "--output-dir", build), stdout = TRUE, stderr = TRUE)
      if ((attr(result, "status") %||% 0L) != 0L) stop("P5 branch failed: ", paste(result, collapse = " | "), call. = FALSE)
      files <- list.files(build, full.names = TRUE)
      if (!all(file.rename(files, file.path(stage, basename(files))))) stop("P5 branch staging promotion failed", call. = FALSE)
      unlink(build, recursive = TRUE)
      validate_json_schema_file(file.path(stage, "branch_manifest.json"), spec$schemas[["shard"]])
    })
}

p5_validate_query_shard <- function(shard_files, contract_files) {
  spec <- p5_load_spec(contract_files)
  config_json <- tempfile(fileext = ".json"); output <- tempfile(fileext = ".json")
  write_json_file(spec$config, config_json)
  result <- system2(research_python_executable(), c(
    spec$files[basename(spec$files) == "p5_fixed_queries.py" & grepl("/scripts/", spec$files)],
    "validate", "--manifest", artifact_path(shard_files, "branch_manifest.json"),
    "--config-json", config_json, "--output", output), stdout = TRUE, stderr = TRUE)
  unlink(config_json)
  if ((attr(result, "status") %||% 0L) != 0L) stop("P5 independent branch validation failed: ", paste(result, collapse = " | "), call. = FALSE)
  value <- jsonlite::read_json(output, simplifyVector = FALSE); unlink(output); value
}

p5_accept_queries <- function(plan, shard_files, shard_validation, fixed_query_methodology_contract,
                              original_scene_dataset_acceptance, contract_files) {
  spec <- p5_load_spec(contract_files); cfg <- spec$config
  contract <- p5_read(fixed_query_methodology_contract, "fixed_query_contract.json")
  p3 <- p5_read(original_scene_dataset_acceptance, "original_scene_dataset_acceptance.json")
  if (length(shard_files) != length(plan) || length(shard_validation) != length(plan) ||
      !all(vapply(shard_validation, function(value) value$status == "PASS", logical(1L)))) {
    stop("P5 validated shard coverage incomplete", call. = FALSE)
  }
  manifests <- vapply(shard_files, function(paths) artifact_path(paths, "branch_manifest.json"), character(1L))
  temp_spec <- tempfile(fileext = ".json"); temp_output <- tempfile(pattern = "p5-aggregate-"); dir.create(temp_output)
  write_json_file(list(query_authority_id = plan[[1L]]$query_authority_id,
                       p3_cache_id = p3$cache_id, manifests = unname(manifests),
                       validations = unname(shard_validation)), temp_spec)
  result <- system2(research_python_executable(), c(
    spec$files[basename(spec$files) == "p5_fixed_queries.py" & grepl("/scripts/", spec$files)],
    "aggregate", "--spec", temp_spec, "--output-dir", file.path(temp_output, "bundle")), stdout = TRUE, stderr = TRUE)
  unlink(temp_spec)
  if ((attr(result, "status") %||% 0L) != 0L) stop("P5 aggregate acceptance failed: ", paste(result, collapse = " | "), call. = FALSE)
  bundle <- file.path(temp_output, "bundle")
  aggregate <- jsonlite::read_json(file.path(bundle, "fixed_query_acceptance.json"), simplifyVector = FALSE)
  validate_json_schema_file(file.path(bundle, "fixed_query_acceptance.json"), spec$schemas[["aggregate_acceptance"]])
  for (split in c("validation", "evaluation")) validate_json_schema_file(file.path(bundle, paste0(split, "_acceptance.json")), spec$schemas[["split_acceptance"]])
  destination <- file.path(cfg$publication_root, plan[[1L]]$query_authority_id, "acceptance", aggregate$acceptance_id)
  filenames <- list.files(bundle)
  paths <- p1_publish_immutable_bundle(destination, filenames, function(stage) {
    if (!all(file.copy(file.path(bundle, filenames), file.path(stage, filenames)))) stop("P5 acceptance publication failed", call. = FALSE)
  })
  unlink(temp_output, recursive = TRUE)
  paths
}

p5_select_acceptance <- function(bundle, split, contract_files) {
  spec <- p5_load_spec(contract_files)
  path <- artifact_path(bundle, paste0(split, "_acceptance.json"))
  validate_json_schema_file(path, spec$schemas[["split_acceptance"]])
  bundle
}

p5_final_acceptance <- function(bundle, validation_acceptance, evaluation_acceptance, contract_files) {
  spec <- p5_load_spec(contract_files)
  value <- p5_read(bundle, "fixed_query_acceptance.json")
  validate_json_schema_file(artifact_path(bundle, "fixed_query_acceptance.json"), spec$schemas[["aggregate_acceptance"]])
  if (value$status != "PASS" || value$query_count != 4000L || value$gallery_count != 2000L) stop("P5 final acceptance rejection", call. = FALSE)
  bundle
}
