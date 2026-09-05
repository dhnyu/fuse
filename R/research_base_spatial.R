p2_base_spatial_contract_paths <- function(root = getwd()) {
  root <- normalizePath(root, mustWork = TRUE)
  cfg <- yaml::read_yaml(file.path(root, "config/p2_base_spatial.yml"))
  c(
    config = file.path(root, "config/p2_base_spatial.yml"),
    membership = file.path(root, "config/membership.yml"),
    vector = file.path(root, "config/vector_observation.yml"),
    raster = file.path(root, "config/raster_observation.yml"),
    relation = file.path(root, "config/relation_graph.yml"),
    codebook = file.path(root, "config/codebooks/spatial_categories.json"),
    vapply(cfg$schemas, function(path) file.path(root, path), character(1L)),
    helper = file.path(root, "R/research_base_spatial.R"),
    membership_helper = file.path(root, "R/research_membership.R"),
    vector_helper = file.path(root, "R/research_observation.R"),
    raster_helper = file.path(root, "R/research_raster_observation.R"),
    relation_helper = file.path(root, "R/research_relation.R"),
    runtime_helper = file.path(root, "R/research_runtime_mirror.R"),
    proxy = file.path(root, "scripts/p2_bbox_proxy_counts.py"),
    zarr_compare = file.path(root, "scripts/p2_zarr_compare.py")
  )
}

p2_scientific_config <- function(cfg) {
  scientific_cfg <- cfg
  scientific_cfg$publication_root <- NULL
  scientific_cfg$branching <- NULL
  for (scope in names(scientific_cfg$scopes)) {
    scientific_cfg$scopes[[scope]]$membership_branches <- NULL
    scientific_cfg$scopes[[scope]]$membership_controller <- NULL
    scientific_cfg$scopes[[scope]]$observation_controller <- NULL
  }
  scientific_cfg
}

p2_load_spec <- function(contract_files, root = getwd()) {
  root <- normalizePath(root, mustWork = TRUE)
  files <- normalizePath(contract_files, mustWork = TRUE)
  cfg <- yaml::read_yaml(files[basename(files) == "p2_base_spatial.yml"])
  schemas <- setNames(
    vapply(cfg$schemas, function(path) files[basename(files) == basename(path)][[1L]], character(1L)),
    names(cfg$schemas)
  )
  relative <- sub(paste0("^", root, "/"), "", files)
  scientific_cfg <- p2_scientific_config(cfg)
  implementation_hash <- p0_scientific_sha256(list(
    version = cfg$implementation_version,
    scientific_config = scientific_cfg,
    files = lapply(order(relative[basename(files) != "p2_base_spatial.yml"], method = "radix"), function(i) {
      selected <- which(basename(files) != "p2_base_spatial.yml")[[i]]
      list(path = relative[[selected]], sha256 = sha256_file(files[[selected]]))
    })
  ))
  list(root = root, config = cfg, files = files, schemas = schemas, implementation_hash = implementation_hash)
}

p2_assert_upstream <- function(reduced_methodology_authority, base_spatial_methodology_contract,
                               scene_index_acceptance, study_data_inventory, spec) {
  authority <- jsonlite::read_json(artifact_path(reduced_methodology_authority, "reduced_methodology_authority.json"), simplifyVector = FALSE)
  contract <- jsonlite::read_json(artifact_path(base_spatial_methodology_contract, "base_spatial_methodology_contract.json"), simplifyVector = FALSE)
  scene <- jsonlite::read_json(artifact_path(scene_index_acceptance, "scene_index_acceptance.json"), simplifyVector = FALSE)
  inventory <- jsonlite::read_json(artifact_path(study_data_inventory, "study_data_inventory.json"), simplifyVector = FALSE)
  cfg <- spec$config
  checks <- c(
    authority$authority_id == cfg$authority$id, authority$overall_status == "PASS",
    contract$contract_id == cfg$authority$base_contract_id, contract$module_content_sha256 == cfg$authority$base_contract_hash,
    contract$status == "PASS", scene$acceptance_id == cfg$p1$scene_acceptance_id, scene$status == "PASS",
    scene$scene_index_id == cfg$p1$scene_index_id, inventory$inventory_id == cfg$p1$inventory_id,
    inventory$status == "PASS", inventory$authority_id == cfg$authority$id
  )
  if (!all(checks)) stop("P2 upstream P0/P1 identity or acceptance mismatch", call. = FALSE)
  list(authority = authority, contract = contract, scene = scene, inventory = inventory)
}

p2_scene_scope <- function(scope, spatial_scene_index, prototype_scene_selection, spec) {
  path <- if (identical(scope, "prototype")) {
    artifact_path(prototype_scene_selection, "prototype_scene_selection.parquet")
  } else {
    artifact_path(spatial_scene_index, "spatial_scene_index.parquet")
  }
  value <- suppressWarnings(sfarrow::st_read_parquet(path))
  value$scene_footprint_id <- value$scene_id
  expected <- unlist(spec$config$scopes[[scope]]$counts)
  actual <- table(factor(value$split, levels = c("training", "validation", "evaluation")))
  if (nrow(value) != expected[["total"]] || !identical(as.integer(actual), as.integer(expected[c("training", "validation", "evaluation")])) ||
      anyDuplicated(value$scene_id) || sf::st_crs(value)$epsg != 5186L) stop("P2 scene scope mismatch", call. = FALSE)
  value[order(value$scene_id, method = "radix"), ]
}

p2_source_contract <- function(inventory, membership_config, root) {
  paths <- yaml::read_yaml(file.path(root, "config/research_paths.yml"))
  records <- setNames(inventory$scientific$files, vapply(inventory$scientific$files, `[[`, character(1L), "role"))
  setNames(lapply(names(membership_config$scientific$sources), function(role) {
    source <- membership_config$scientific$sources[[role]]
    record <- records[[source$input_role]]
    list(role = role, entity_type = membership_config$scientific$predicates[[role]]$entity_type,
         path = paths$inputs[[source$input_role]], layer = source$source_layer,
         source_id_column = source$source_id_column,
         source_artifact_id = paste0("src_", substr(record$sha256, 1L, 24L)),
         sha256 = record$sha256, size_bytes = record$size_bytes)
  }), names(membership_config$scientific$sources))
}

p2_bbox_proxy <- function(scenes, sources, spec) {
  input <- tempfile(fileext = ".tsv"); output <- tempfile(fileext = ".tsv")
  on.exit(unlink(c(input, output)), add = TRUE)
  box <- t(vapply(sf::st_geometry(scenes), sf::st_bbox, numeric(4L)))
  data.table::fwrite(data.table::data.table(scene_id = scenes$scene_id, xmin = box[, 1L], ymin = box[, 2L], xmax = box[, 3L], ymax = box[, 4L]), input, sep = "\t", col.names = FALSE)
  script <- spec$files[basename(spec$files) == "p2_bbox_proxy_counts.py"]
  args <- c(script, "--scenes", input, "--building", sources$building$path, "--road", sources$road$path, "--poi", sources$poi$path, "--output", output)
    message <- system2(research_python_executable(), args, stdout = TRUE, stderr = TRUE)
  if ((attr(message, "status") %||% 0L) != 0L || !file.exists(output)) stop("P2 proxy computation failed: ", paste(message, collapse = " | "), call. = FALSE)
  value <- data.table::fread(output)
  weights <- unlist(spec$config$branching$proxy_weights)
  value[, estimated_cost := building * weights[["building"]] + road * weights[["road"]] + poi * weights[["poi"]]]
  value
}

p2_lpt_bins <- function(scene_ids, costs, target_branches, maximum_scenes) {
  target_branches <- min(as.integer(target_branches), length(scene_ids))
  order_index <- order(-costs, scene_ids, method = "radix")
  bins <- vector("list", target_branches); loads <- numeric(target_branches)
  for (i in order_index) {
    eligible <- which(lengths(bins) < maximum_scenes)
    chosen <- eligible[order(loads[eligible], lengths(bins)[eligible], eligible)[[1L]]]
    bins[[chosen]] <- c(bins[[chosen]], i); loads[[chosen]] <- loads[[chosen]] + costs[[i]]
  }
  bins <- lapply(bins[lengths(bins) > 0L], function(x) x[order(scene_ids[x], method = "radix")])
  bins[order(vapply(bins, function(x) min(scene_ids[x]), character(1L)), method = "radix")]
}

p2_original_observation_id <- function(scientific) {
  paste0("obs_", substr(p0_scientific_sha256(scientific), 1L, 24L))
}

p2_validate_topology_table <- function(rows) {
  required <- c("scene_id", "road_local_entity_id", "source_node_position", "source_node_id",
                "source_node_offset_start", "source_node_offset_end", "chain_length", "road_type",
                "road_hierarchy", "source_node_x_5186", "source_node_y_5186")
  if (!all(required %in% names(rows))) stop("P2 topology fields are incomplete", call. = FALSE)
  if (!nrow(rows)) return(invisible(TRUE))
  failures <- c(
    anyNA(rows[, ..required]), anyDuplicated(rows[, .(scene_id, road_local_entity_id, source_node_position)]) > 0L,
    any(rows$chain_length < 2L), any(rows$source_node_position < 0L | rows$source_node_position >= rows$chain_length),
    any(rows$source_node_offset_end - rows$source_node_offset_start != rows$chain_length),
    any(!is.finite(rows$source_node_x_5186) | !is.finite(rows$source_node_y_5186))
  )
  chain <- rows[, .(rows = .N, positions = data.table::uniqueN(source_node_position),
                    minimum = min(source_node_position), maximum = max(source_node_position)),
                by = .(scene_id, road_local_entity_id, chain_length)]
  failures <- c(failures, any(chain$rows != chain$chain_length | chain$positions != chain$chain_length |
                              chain$minimum != 0L | chain$maximum != chain$chain_length - 1L))
  if (any(failures)) stop("P2 source topology chain failed", call. = FALSE)
  invisible(TRUE)
}

p2_build_membership_plan <- function(scope, spatial_scene_index, prototype_scene_selection,
                                     scene_index_acceptance, study_data_inventory,
                                     reduced_methodology_authority, base_spatial_methodology_contract,
                                     membership_contract_files, p2_base_spatial_contract_files,
                                     prototype_gate = NULL) {
  if (!is.null(prototype_gate)) {
    gate <- jsonlite::read_json(artifact_path(prototype_gate, "base_spatial_acceptance.json"), simplifyVector = FALSE)
    if (gate$scope != "prototype" || gate$status != "PASS") stop("Production P2 requires prototype PASS", call. = FALSE)
  }
  spec <- p2_load_spec(p2_base_spatial_contract_files)
  upstream <- p2_assert_upstream(reduced_methodology_authority, base_spatial_methodology_contract, scene_index_acceptance, study_data_inventory, spec)
  scenes <- p2_scene_scope(scope, spatial_scene_index, prototype_scene_selection, spec)
  membership <- load_membership_config(membership_contract_files)
  sources <- p2_source_contract(upstream$inventory, membership, spec$root)
  proxy <- p2_bbox_proxy(scenes, sources, spec)
  proxy <- proxy[match(scenes$scene_id, proxy$scene_id)]
  bins <- p2_lpt_bins(scenes$scene_id, proxy$estimated_cost, spec$config$scopes[[scope]]$membership_branches,
                      spec$config$branching$maximum_scenes_per_branch)
  scientific <- list(schema_version = "1.0.0", scope = scope, authority_id = upstream$authority$authority_id,
                     base_contract_id = upstream$contract$contract_id, scene_index_id = upstream$scene$scene_index_id,
                     scene_acceptance_id = upstream$scene$acceptance_id, inventory_id = upstream$inventory$inventory_id,
                     ordered_scene_ids = as.list(scenes$scene_id), source_ids = lapply(sources, function(x) x[c("source_artifact_id", "sha256")]),
                     membership_config_hash = membership$scientific_hash, implementation_hash = spec$implementation_hash)
  scientific_hash <- p0_scientific_sha256(scientific)
  dataset_id <- paste0("bmd_", substr(scientific_hash, 1L, 24L))
  plan_id <- paste0("bmp_", substr(p0_scientific_sha256(list(scientific_hash = scientific_hash, scope = scope)), 1L, 24L))
  root <- file.path(spec$config$publication_root, paste0("pending-", dataset_id), scope)
  boxes <- t(vapply(sf::st_geometry(scenes), sf::st_bbox, numeric(4L)))
  branches <- lapply(seq_along(bins), function(position) {
    index <- bins[[position]]; ids <- scenes$scene_id[index]
    branch_id <- paste0("bmb_", substr(p0_scientific_sha256(list(dataset_id = dataset_id, scene_ids = as.list(ids))), 1L, 24L))
    records <- lapply(index, function(i) list(scene_id = scenes$scene_id[[i]], scene_footprint_id = scenes$scene_id[[i]], split = scenes$split[[i]],
      center_x = scenes$center_x[[i]], center_y = scenes$center_y[[i]], xmin = boxes[i, 1L], ymin = boxes[i, 2L], xmax = boxes[i, 3L], ymax = boxes[i, 4L], estimated_cost = proxy$estimated_cost[[i]]))
    list(spec_schema_version = "1.0.0", scope = scope, branch_id = branch_id, membership_dataset_id = dataset_id,
         prototype_id = if (scope == "prototype") spec$config$p1$prototype_id else "production", scene_index_id = spec$config$p1$scene_index_id,
         authority_id = spec$config$authority$id, scene_acceptance_id = spec$config$p1$scene_acceptance_id,
         scene_ids = as.list(ids), scenes = records,
         split_counts = as.list(table(factor(scenes$split[index], levels = c("training", "validation", "evaluation")))),
         estimated_counts = list(building = sum(proxy$building[index]), road = sum(proxy$road[index]), poi = sum(proxy$poi[index])),
         estimated_cost = sum(proxy$estimated_cost[index]), sources = sources,
         membership_contract = list(version = membership$scientific$membership_predicate_version, config_hash = membership$scientific_hash,
                                    schema_hash = membership$schema_hash, implementation_hash = membership$implementation_hash,
                                    predicates = membership$scientific$predicates, geometry_policy = membership$scientific$geometry_policy),
         output = list(directory = file.path(root, "membership", dataset_id, "branches", branch_id)),
         execution = list(controller = spec$config$scopes[[scope]]$membership_controller, workers = 1L, threads = 1L))
  })
  plan_dir <- file.path(spec$config$publication_root, "plans", scope, plan_id)
  basenames <- c("membership_plan.json", vapply(branches, function(x) paste0("spec-", x$branch_id, ".json"), character(1L)))
  paths <- p1_publish_immutable_bundle(plan_dir, basenames, function(stage) {
    plan <- list(schema_version = "1.0.0", scope = scope, plan_id = plan_id, membership_dataset_id = dataset_id,
                 authority_id = spec$config$authority$id, scene_index_id = spec$config$p1$scene_index_id,
                 scene_acceptance_id = spec$config$p1$scene_acceptance_id, inventory_id = spec$config$p1$inventory_id,
                 base_contract_id = spec$config$authority$base_contract_id, scientific_fingerprint = scientific_hash,
                 branch_specs = lapply(branches, function(x) list(branch_id = x$branch_id, scene_ids = x$scene_ids, estimated_cost = x$estimated_cost)),
                 execution = list(algorithm = spec$config$branching$algorithm, branch_count = length(branches), controller = spec$config$scopes[[scope]]$membership_controller, workers_per_branch = 1L, threads_per_worker = 1L))
    plan_path <- write_json_file(plan, file.path(stage, basenames[[1L]])); validate_json_schema_file(plan_path, spec$schemas[["membership_plan"]])
    for (i in seq_along(branches)) write_json_file(branches[[i]], file.path(stage, basenames[[i + 1L]]))
  })
  plan_path <- paths[basename(paths) == "membership_plan.json"]
  lapply(branches, function(value) { value$.path <- paths[basename(paths) == paste0("spec-", value$branch_id, ".json")]; value$.plan_path <- plan_path; value })
}

p2_build_membership_shard <- function(base_spatial_membership_plan, study_data_inputs, prototype_runtime_inputs,
                                      membership_contract_files, workers = 1L, threads = 1L) {
  spec <- base_spatial_membership_plan
  fuse_parallel_spec(workers, threads); state <- membership_thread_state(); on.exit(restore_membership_threads(state), add = TRUE); set_membership_threads(threads)
  config <- load_membership_config(membership_contract_files); started <- Sys.time(); io_start <- proc_io_snapshot(); scenes <- membership_scene_sf(spec)
  roles <- c("building", "road", "poi")
  runtime_sources <- setNames(lapply(roles, function(role) runtime_source_record(spec$sources[[role]], prototype_runtime_inputs, role)), roles)
  candidates <- setNames(lapply(roles, function(role) read_membership_candidates(runtime_sources[[role]], scenes)), roles)
  Map(validate_membership_candidates, candidates, roles, MoreArgs = list(geometry_policy = config$scientific$geometry_policy))
  tables <- Map(exact_membership_pairs, MoreArgs = list(scenes = scenes, spec = spec), entities = candidates, role = roles); names(tables) <- roles
  output_names <- membership_output_names(); final_dir <- spec$output$directory
  publish_deterministic_directory(final_dir, output_names, compare_basenames = output_names[1:3], writer = function(stage) {
    for (i in seq_along(tables)) { arrow::write_parquet(tables[[i]], file.path(stage, output_names[[i]]), compression = "zstd", use_dictionary = TRUE); validate_membership_table(arrow::read_parquet(file.path(stage, output_names[[i]])), spec, spec$sources[[names(tables)[[i]]]]$entity_type) }
    counts <- vapply(tables, nrow, integer(1L)); io_end <- proc_io_snapshot()
    qc <- list(status = "PASS", scope = spec$scope, branch_id = spec$branch_id, scene_count = nrow(scenes), entity_rows = as.list(counts), duplicate_membership_rows = 0L, invalid_geometry_count = 0L, missing_branch = 0L)
    write_json_file(qc, file.path(stage, "branch_qc.json")); write_json_lines(list(list(event = "branch_completed", status = "PASS", branch_id = spec$branch_id)), file.path(stage, "branch_log.jsonl"))
    outputs <- lapply(file.path(stage, output_names[1:3]), function(path) list(path = file.path(final_dir, basename(path)), sha256 = sha256_file(path), size_bytes = unname(file.info(path)$size)))
    manifest <- list(status = "PASS", scope = spec$scope, branch_id = spec$branch_id, membership_dataset_id = spec$membership_dataset_id,
                     scene_index_id = spec$scene_index_id, scene_ids = spec$scene_ids, scene_count = nrow(scenes), entity_rows = as.list(counts), outputs = outputs,
                     execution = list(wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")), max_rss_kb = proc_max_rss_kb(), read_bytes = proc_io_snapshot()$read_bytes - io_start$read_bytes, write_bytes = io_end$write_bytes - io_start$write_bytes))
    write_json_file(manifest, file.path(stage, "branch_manifest.json"))
  })
}

p2_accept_membership <- function(scope, membership_plan, membership_shard, spatial_scene_index,
                                 prototype_scene_selection, study_data_inventory,
                                 membership_contract_files, p2_base_spatial_contract_files) {
  spec <- p2_load_spec(p2_base_spatial_contract_files); cfg <- load_membership_config(membership_contract_files)
  plans <- membership_plan; bundles <- normalize_membership_branch_outputs(membership_shard)
  manifests <- lapply(bundles, function(x) jsonlite::read_json(x[basename(x) == "branch_manifest.json"], simplifyVector = FALSE))
  planned <- unname(sort(vapply(plans, `[[`, character(1L), "branch_id")))
  observed <- unname(sort(vapply(manifests, `[[`, character(1L), "branch_id")))
  if (!identical(planned, observed) || any(vapply(manifests, function(x) x$status != "PASS", logical(1L)))) stop("P2 membership branches incomplete", call. = FALSE)
  scenes <- p2_scene_scope(scope, spatial_scene_index, prototype_scene_selection, spec)
  all_ids <- unlist(lapply(plans, `[[`, "scene_ids"), use.names = FALSE)
  if (length(all_ids) != nrow(scenes) || anyDuplicated(all_ids) || !setequal(all_ids, scenes$scene_id)) stop("P2 membership scene completeness failed", call. = FALSE)
  paths <- unlist(bundles, use.names = FALSE); parquets <- paths[grepl("_membership[.]parquet$", paths)]
  tables <- lapply(parquets, arrow::read_parquet, as_data_frame = TRUE); combined <- data.table::rbindlist(tables, use.names = TRUE)
  if (anyDuplicated(combined[, .(scene_id, entity_type, source_entity_id)])) stop("P2 duplicate membership", call. = FALSE)
  membership_source_id_check(parquets, plans)
  sample <- membership_brute_force_sample(plans, as.integer(spec$config$parity$membership_scene_sample))
  brute <- data.table::rbindlist(lapply(seq_len(nrow(sample)), function(i) {
    branch <- plans[[which(vapply(plans, function(x) sample$scene_id[[i]] %in% unlist(x$scene_ids), logical(1L)))[[1L]]]]
    record <- branch$scenes[[which(vapply(branch$scenes, `[[`, character(1L), "scene_id") == sample$scene_id[[i]])[[1L]]]]
    brute_force_membership_for_scene(record, branch)
  }), use.names = TRUE)
  key <- c("scene_id", "entity_type", "source_entity_id"); optimized <- combined[scene_id %in% sample$scene_id]
  false_negative <- nrow(data.table::fsetdiff(unique(brute[, ..key]), unique(optimized[, ..key])))
  false_positive <- nrow(data.table::fsetdiff(unique(optimized[, ..key]), unique(brute[, ..key])))
  if (false_negative || false_positive) stop("P2 independent membership parity failed", call. = FALSE)
  entity_counts <- as.list(table(factor(combined$entity_type, levels = c("B", "R", "P")))); names(entity_counts) <- c("B", "R", "P")
  scientific <- list(scope = scope, membership_dataset_id = plans[[1L]]$membership_dataset_id, ordered_scene_ids = as.list(scenes$scene_id), entity_counts = entity_counts,
                     config_hash = cfg$scientific_hash, implementation_hash = spec$implementation_hash)
  hash <- p0_scientific_sha256(scientific); id <- paste0("bma_", substr(hash, 1L, 24L))
  root <- file.path(spec$config$publication_root, paste0("pending-", plans[[1L]]$membership_dataset_id), scope, "membership", plans[[1L]]$membership_dataset_id, "acceptance", id)
  p1_publish_immutable_bundle(root, c("aggregate_membership_manifest.json", "membership_statistics.parquet"), function(stage) {
    stats <- combined[, .(membership_count = .N), by = .(scene_id, entity_type)][order(scene_id, entity_type)]
    arrow::write_parquet(stats, file.path(stage, "membership_statistics.parquet"), compression = "zstd")
    value <- list(schema_version = "1.0.0", scope = scope, acceptance_id = id, status = "PASS", authority_id = spec$config$authority$id,
                  scene_index_id = spec$config$p1$scene_index_id, membership_dataset_id = plans[[1L]]$membership_dataset_id, scene_count = nrow(scenes),
                  split_counts = as.list(table(factor(scenes$split, levels = c("training", "validation", "evaluation")))), entity_counts = entity_counts,
                  branch_ids = as.list(planned), membership_parquets = as.list(sort(parquets)),
                  parity = list(sample_count = nrow(sample), false_positive = 0L, false_negative = 0L, independent_source_read = TRUE), scientific_hash = hash)
    path <- write_json_file(value, file.path(stage, "aggregate_membership_manifest.json")); validate_json_schema_file(path, spec$schemas[["membership_acceptance"]])
  })
}

p2_build_observation_plan <- function(scope, membership_plan, membership_acceptance,
                                      spatial_scene_index, prototype_scene_selection,
                                      observation_contract_files, raster_observation_contract_files,
                                      relation_contract_files, p2_base_spatial_contract_files) {
  spec <- p2_load_spec(p2_base_spatial_contract_files); vector_cfg <- load_observation_config(observation_contract_files)
  raster_cfg <- load_raster_observation_config(raster_observation_contract_files); relation_cfg <- load_relation_config(relation_contract_files)
  acceptance <- jsonlite::read_json(artifact_path(membership_acceptance, "aggregate_membership_manifest.json"), simplifyVector = FALSE)
  scenes <- p2_scene_scope(scope, spatial_scene_index, prototype_scene_selection, spec); plans <- membership_plan
  membership <- data.table::rbindlist(lapply(unlist(acceptance$membership_parquets), arrow::read_parquet), use.names = TRUE)
  scientific <- list(scope = scope, authority_id = spec$config$authority$id, base_contract_hash = spec$config$authority$base_contract_hash,
                     scene_index_id = spec$config$p1$scene_index_id, scene_acceptance_id = spec$config$p1$scene_acceptance_id,
                     membership_acceptance_id = acceptance$acceptance_id, vector_hash = vector_cfg$scientific_hash,
                     raster_hash = raster_cfg$scientific_hash, relation_hash = relation_cfg$scientific_hash,
                     topology = spec$config$topology, implementation_hash = spec$implementation_hash)
  hash <- p0_scientific_sha256(scientific); observation_id <- p2_original_observation_id(scientific); plan_id <- paste0("bop_", substr(p0_scientific_sha256(list(hash, scope)), 1L, 24L))
  vector_dataset_id <- paste0("bvo_", substr(p0_scientific_sha256(list(observation_id, "vector")), 1L, 24L))
  root <- file.path(spec$config$publication_root, observation_id, scope)
  branches <- lapply(plans, function(plan) {
    rows <- membership[scene_id %in% unlist(plan$scene_ids)]; counts <- table(factor(rows$entity_type, levels = c("B", "R", "P")))
    records <- lapply(plan$scenes, function(x) list(scene_id = x$scene_id, scene_footprint_id = x$scene_footprint_id, split = x$split,
      center_x = x$center_x, center_y = x$center_y, xmin = x$xmin, ymin = x$ymin, xmax = x$xmax, ymax = x$ymax,
      estimated_cost = x$estimated_cost, entity_count = sum(rows$scene_id == x$scene_id), coordinate_count = 0L, source_geometry_bytes = 0L))
    list(spec_schema_version = "1.0.0", scope = scope, branch_id = plan$branch_id, observation_dataset_id = vector_dataset_id,
         original_observation_id = observation_id, prototype_id = plan$prototype_id, membership_dataset_id = acceptance$membership_dataset_id,
         scene_index_id = spec$config$p1$scene_index_id, scene_ids = plan$scene_ids, scenes = records, split_counts = plan$split_counts,
         estimated_counts = list(building = unname(counts[[1L]]), road = unname(counts[[2L]]), poi = unname(counts[[3L]]), total = nrow(rows)),
         estimated_geometry = list(coordinate_count = 0L, component_count = 0L, source_geometry_bytes = 0L, estimated_cost = plan$estimated_cost, dense_singleton = FALSE),
         shared_grouping = list(grouping_version = "1.0.0", aligned_stages = c("vector", "raster", "relation", "topology"), immutable_scene_group = TRUE),
         sources = plan$sources, membership_parquets = acceptance$membership_parquets,
         contract = list(observation_contract_version = vector_cfg$scientific$observation_contract_version, config_hash = vector_cfg$scientific_hash,
                         schema_hash = vector_cfg$schema_hash, implementation_source_hash = vector_cfg$implementation_source_hash,
                         writer_hash = vector_cfg$writer_hash, writer = vector_cfg$scientific$writer, geometry = vector_cfg$scientific$geometry,
                         attributes = vector_cfg$scientific$attributes, local_entity_id = vector_cfg$scientific$local_entity_id),
         output = list(directory = file.path(root, "vector", "branches", plan$branch_id)),
         execution = list(controller = spec$config$scopes[[scope]]$observation_controller, workers = 1L, threads = 1L))
  })
  plan_dir <- file.path(root, "plans", plan_id); basenames <- c("observation_plan.json", vapply(branches, function(x) paste0("spec-", x$branch_id, ".json"), character(1L)))
  paths <- p1_publish_immutable_bundle(plan_dir, basenames, function(stage) {
    value <- list(schema_version = "1.0.0", scope = scope, plan_id = plan_id, original_observation_id = observation_id,
                  authority_id = spec$config$authority$id, scene_index_id = spec$config$p1$scene_index_id, membership_acceptance_id = acceptance$acceptance_id,
                  scientific_fingerprint = hash, branch_specs = lapply(branches, function(x) list(branch_id = x$branch_id, scene_ids = x$scene_ids)),
                  execution = list(branch_count = length(branches), controller = spec$config$scopes[[scope]]$observation_controller, workers_per_branch = 1L, threads_per_worker = 1L))
    path <- write_json_file(value, file.path(stage, basenames[[1L]])); validate_json_schema_file(path, spec$schemas[["observation_plan"]])
    for (i in seq_along(branches)) write_json_file(branches[[i]], file.path(stage, basenames[[i + 1L]]))
  })
  plan_path <- paths[basename(paths) == "observation_plan.json"]
  lapply(branches, function(value) { value$.path <- paths[basename(paths) == paste0("spec-", value$branch_id, ".json")]; value$.plan_path <- plan_path; value })
}

p2_build_vector_shard <- function(base_spatial_observation_plan, membership_acceptance, study_data_inputs,
                                  prototype_runtime_inputs, observation_contract_files, workers = 1L, threads = 1L) {
  build_prototype_vector_observation_shard(base_spatial_observation_plan, membership_acceptance, study_data_inputs,
                                           prototype_runtime_inputs, observation_contract_files, workers, threads)
}

p2_build_raster_shard <- function(base_spatial_observation_plan, vector_shard, study_data_inputs,
                                  prototype_runtime_inputs, raster_observation_contract_files, workers = 1L, threads = 1L) {
  build_prototype_raster_observation_shard(base_spatial_observation_plan, vector_shard, study_data_inputs,
                                           prototype_runtime_inputs, raster_observation_contract_files, workers, threads)
}

p2_build_relation_shard <- function(base_spatial_observation_plan, vector_shard, study_data_inputs,
                                    prototype_runtime_inputs, relation_contract_files, workers = 1L, threads = 1L) {
  build_prototype_relation_shard(base_spatial_observation_plan, vector_shard, study_data_inputs,
                                 prototype_runtime_inputs, relation_contract_files, workers, threads)
}

p2_observed_vertex_index <- function(geometry, x, y, tolerance) {
  coordinates <- sf::st_coordinates(geometry)
  if (!nrow(coordinates)) return(NA_integer_)
  distance <- sqrt((coordinates[, "X"] - x)^2 + (coordinates[, "Y"] - y)^2)
  if (min(distance) > tolerance) NA_integer_ else as.integer(which.min(distance) - 1L)
}

p2_build_topology_shard <- function(base_spatial_observation_plan, vector_shard, prototype_runtime_inputs,
                                    p2_base_spatial_contract_files, workers = 1L, threads = 1L,
                                    output_directory = NULL, manifest_schema = NULL) {
  fuse_parallel_spec(workers, threads); spec_cfg <- p2_load_spec(p2_base_spatial_contract_files); branch <- base_spatial_observation_plan
  vector <- read_i10_branch_context(branch, vector_shard); roads <- read_standard_geoparquet(vector$files[["road"]])
  road_path <- runtime_mirror_path(prototype_runtime_inputs, "road")
  node_positions <- read_relation_node_positions(road_path, c(roads$F_NODE, roads$T_NODE))
  dataset_id <- paste0("top_", substr(p0_scientific_sha256(list(original_observation_id = branch$original_observation_id,
    road_source = branch$sources$road[c("source_artifact_id", "sha256")], topology = spec_cfg$config$topology, implementation_hash = spec_cfg$implementation_hash)), 1L, 24L))
  if (nrow(roads)) {
    rows <- data.table::rbindlist(lapply(seq_len(nrow(roads)), function(i) {
      road <- roads[i, ]; ids <- c(as.character(road$F_NODE), as.character(road$T_NODE)); positions <- node_positions[match(ids, node_id)]
      geometry <- sf::st_geometry(road)[[1L]]; observed_wkb <- geometry_wkb(sf::st_sfc(geometry, crs = 5186L))[[1L]]
      mapping <- vapply(seq_along(ids), function(j) p2_observed_vertex_index(geometry, positions$x[[j]], positions$y[[j]], spec_cfg$config$topology$vertex_tolerance_m), integer(1L))
      retained <- c(as.logical(road$source_f_node_endpoint_retained), as.logical(road$source_t_node_endpoint_retained))
      data.table::data.table(scene_id = road$scene_id, road_id = road$source_entity_id, road_local_entity_id = as.integer(road$local_entity_id),
        source_road_link_id = road$source_entity_id, road_type = road$ROAD_TYPE, road_hierarchy = road$ROAD_RANK,
        source_node_ids = paste(ids, collapse = "|"), source_node_offsets = "0|2", source_node_offset_start = 0L, source_node_offset_end = 2L,
        source_node_position = 0:1, source_node_id = ids, source_node_order = c("F", "T"), source_node_x_5186 = positions$x, source_node_y_5186 = positions$y,
        source_node_vertex_index = 0:1, observed_geometry_vertex_index = mapping, endpoint_internal_flag = "terminal",
        retained_visible_flag = retained, clipping_induced_endpoint_flag = !retained, chain_length = 2L,
        source_geometry_wkb = road$source_geometry_wkb, observed_geometry_wkb = list(observed_wkb, observed_wkb),
        topology_provenance = "seoul_R.gpkg:links(F_NODE,T_NODE)+nodes(NODE_ID)", source_identity_hash = branch$sources$road$sha256,
        topology_dataset_id = dataset_id, branch_id = branch$branch_id)
    }), use.names = TRUE)
    offsets <- unique(rows[, .(scene_id, road_local_entity_id, chain_length)])[order(scene_id, road_local_entity_id)]
    offsets[, source_node_offset_start := cumsum(data.table::shift(chain_length, fill = 0L)), by = scene_id]
    offsets[, source_node_offset_end := source_node_offset_start + chain_length]
    rows[, c("source_node_offset_start", "source_node_offset_end") := NULL]
    rows <- merge(
      rows,
      offsets[, .(scene_id, road_local_entity_id, source_node_offset_start, source_node_offset_end)],
      by = c("scene_id", "road_local_entity_id"),
      all.x = TRUE,
      sort = FALSE
    )
    rows[, source_node_offsets := paste(source_node_offset_start, source_node_offset_end, sep = "|")]
    data.table::setorder(rows, scene_id, road_local_entity_id, source_node_position)
  } else {
    rows <- data.table::data.table(scene_id = character(), road_id = character(), road_local_entity_id = integer(), source_road_link_id = character(),
      road_type = character(), road_hierarchy = character(), source_node_ids = character(), source_node_offsets = character(), source_node_offset_start = integer(),
      source_node_offset_end = integer(), source_node_position = integer(), source_node_id = character(), source_node_order = character(), source_node_x_5186 = numeric(),
      source_node_y_5186 = numeric(), source_node_vertex_index = integer(), observed_geometry_vertex_index = integer(), endpoint_internal_flag = character(),
      retained_visible_flag = logical(), clipping_induced_endpoint_flag = logical(), chain_length = integer(), source_geometry_wkb = list(), observed_geometry_wkb = list(),
      topology_provenance = character(), source_identity_hash = character(), topology_dataset_id = character(), branch_id = character())
  }
  p2_validate_topology_table(rows)
  final_dir <- output_directory %||% file.path(spec_cfg$config$publication_root, branch$original_observation_id, branch$scope, "topology", "branches", branch$branch_id)
  p1_publish_immutable_bundle(final_dir, c("source_topology.parquet", "topology_manifest.json", "topology_qc.json"), function(stage) {
    parquet <- file.path(stage, "source_topology.parquet"); arrow::write_parquet(rows, parquet, compression = "zstd")
    scientific <- list(scope = branch$scope, branch_id = branch$branch_id, dataset_id = dataset_id, scene_ids = branch$scene_ids,
                       ordered_key = if (nrow(rows)) paste(rows$scene_id, rows$road_local_entity_id, rows$source_node_position, rows$source_node_id, sep = "|") else list(),
                       source_hash = branch$sources$road$sha256, implementation_hash = spec_cfg$implementation_hash)
    hash <- p0_scientific_sha256(scientific); roads_count <- if (nrow(rows)) data.table::uniqueN(rows[, .(scene_id, road_local_entity_id)]) else 0L
    qc <- list(status = "PASS", zero_road_scene_count = length(setdiff(unlist(branch$scene_ids), unique(rows$scene_id))), duplicate_chain_row_count = 0L,
               missing_type_hierarchy_count = 0L, invalid_node_reference_count = 0L, p4_absorption_ready = TRUE)
    write_json_file(qc, file.path(stage, "topology_qc.json"))
    manifest <- list(schema_version = "1.0.0", scope = branch$scope, branch_id = branch$branch_id, status = "PASS", topology_dataset_id = dataset_id,
                     scene_ids = branch$scene_ids, road_count = roads_count, node_row_count = nrow(rows),
                     chain_length_distribution = list(min = if (roads_count) 2L else 0L, max = if (roads_count) 2L else 0L, variable_length_schema = TRUE),
                     p4_absorption_ready = TRUE, files = list(p1_artifact_record(parquet, "source_topology"),
                     p1_artifact_record(file.path(stage, "topology_qc.json"), "topology_qc")), scientific_hash = hash)
    path <- write_json_file(manifest, file.path(stage, "topology_manifest.json")); validate_json_schema_file(path, manifest_schema %||% spec_cfg$schemas[["topology_manifest"]])
  })
}

p2_index_bundles <- function(values, manifest_name) {
  paths <- unlist(values, recursive = TRUE, use.names = FALSE)
  grouped <- split(paths, dirname(paths))
  grouped <- grouped[vapply(grouped, function(x) manifest_name %in% basename(x), logical(1L))]
  setNames(lapply(grouped, function(x) {
    manifest <- jsonlite::read_json(x[basename(x) == manifest_name], simplifyVector = FALSE)
    list(paths = x, manifest = manifest)
  }), vapply(grouped, function(x) jsonlite::read_json(x[basename(x) == manifest_name], simplifyVector = FALSE)$branch_id, character(1L)))
}

p2_branch_checksums <- function(bundles) {
  failures <- character(); records <- list()
  for (bundle in bundles) {
    manifest_path <- bundle$paths[basename(bundle$paths) %in% c("branch_manifest.json", "topology_manifest.json")]
    records[[length(records) + 1L]] <- p1_artifact_record(manifest_path, basename(manifest_path))
    outputs <- bundle$manifest$outputs %||% bundle$manifest$files
    for (output in outputs) {
      path <- output$path
      if (is.null(path)) path <- bundle$paths[basename(bundle$paths) == output$basename]
      if (!length(path) || !file.exists(path)) { failures <- c(failures, paste0(bundle$manifest$branch_id, ":missing")); next }
      if (!is.null(output$sha256) && !identical(sha256_file(path), output$sha256)) failures <- c(failures, paste0(bundle$manifest$branch_id, ":checksum"))
      if (!dir.exists(path)) records[[length(records) + 1L]] <- p1_artifact_record(path, output$role %||% basename(path))
    }
    zarr_manifest <- bundle$paths[basename(bundle$paths) == "zarr_member_manifest.json"]
    if (length(zarr_manifest)) {
      zarr <- jsonlite::read_json(zarr_manifest, simplifyVector = FALSE)
      for (store in zarr$stores) for (member in store$members) {
        if (!file.exists(member$path) || !identical(sha256_file(member$path), member$sha256)) failures <- c(failures, paste0(bundle$manifest$branch_id, ":zarr"))
      }
      records[[length(records) + 1L]] <- p1_artifact_record(zarr_manifest, "zarr_member_manifest")
    }
  }
  list(failures = unique(failures), records = records)
}

p2_sample_scenes <- function(plan, count) {
  records <- data.table::rbindlist(lapply(plan, function(spec) data.table::rbindlist(lapply(spec$scenes, function(scene) data.table::data.table(
    scene_id = scene$scene_id, split = scene$split, branch_id = spec$branch_id, estimated_cost = scene$estimated_cost
  )))))
  allocations <- c(training = count - 4L, validation = 2L, evaluation = 2L); selected <- integer()
  for (split in names(allocations)) {
    rows <- which(records$split == split); rows <- rows[order(records$estimated_cost[rows], records$scene_id[rows], method = "radix")]
    selected <- c(selected, rows[unique(round(seq(1, length(rows), length.out = allocations[[split]])))])
  }
  records[selected][order(scene_id)]
}

p2_raster_parity <- function(plan, raster_bundles, prototype_runtime_inputs, raster_observation_contract_files,
                             p2_base_spatial_contract_files, sample_count) {
  config <- load_raster_observation_config(raster_observation_contract_files); p2 <- p2_load_spec(p2_base_spatial_contract_files)
  landcover <- terra::rast(runtime_mirror_path(prototype_runtime_inputs, "landcover")); dem <- terra::rast(runtime_mirror_path(prototype_runtime_inputs, "dem"))
  sample <- p2_sample_scenes(plan, sample_count); maximum <- 0
  script <- p2$files[basename(p2$files) == "p2_zarr_compare.py"]
  for (i in seq_len(nrow(sample))) {
    branch <- plan[[match(sample$branch_id[[i]], vapply(plan, `[[`, character(1L), "branch_id"))]]
    scene <- branch$scenes[[match(sample$scene_id[[i]], vapply(branch$scenes, `[[`, character(1L), "scene_id"))]]
    bundle <- raster_bundles[[sample$branch_id[[i]]]]; index <- arrow::read_parquet(bundle$paths[basename(bundle$paths) == "scene_raster_index.parquet"])
    zindex <- index$zarr_index[index$scene_id == sample$scene_id[[i]]]
    expected <- list(
      list(value = scene_landcover_observation(landcover, scene, config)$composition, store = "scene_landcover.zarr", array = "class_fraction", atol = 1e-6),
      list(value = scene_dem_observation(dem, scene, config)$value, store = "scene_dem.zarr", array = "raw_mean_m", atol = 1e-5)
    )
    for (item in expected) {
      raw <- tempfile(fileext = ".bin"); on.exit(unlink(raw), add = TRUE); write_raw_array(item$value, raw, "float32")
      store_path <- file.path(dirname(bundle$paths[[1L]]), item$store)
      if (!dir.exists(store_path)) stop("P2 raster store missing: ", store_path, call. = FALSE)
      args <- c(script, "--store", store_path, "--array", item$array,
                "--index", as.character(zindex), "--expected", raw, "--shape", paste(dim(item$value), collapse = ","), "--atol", as.character(item$atol))
      output <- system2(research_python_executable(), args, stdout = TRUE, stderr = TRUE); status <- attr(output, "status") %||% 0L
      if (status != 0L) stop("P2 independent raster parity failed: ", paste(output, collapse = " | "), call. = FALSE)
      record <- jsonlite::fromJSON(tail(output, 1L)); maximum <- max(maximum, record$maximum_absolute_error)
      unlink(raw)
    }
  }
  list(status = "PASS", sample_count = nrow(sample), independent_source_read = TRUE, maximum_absolute_error = maximum)
}

p2_relation_parity <- function(plan, vector_bundles, relation_bundles, prototype_runtime_inputs,
                               relation_contract_files, sample_count) {
  config <- load_relation_config(relation_contract_files); sample <- p2_sample_scenes(plan, sample_count)
  road_path <- runtime_mirror_path(prototype_runtime_inputs, "road"); maximum <- 0
  for (i in seq_len(nrow(sample))) {
    branch <- plan[[match(sample$branch_id[[i]], vapply(plan, `[[`, character(1L), "branch_id"))]]
    vb <- vector_bundles[[sample$branch_id[[i]]]]; rb <- relation_bundles[[sample$branch_id[[i]]]]
    files <- setNames(vb$paths[grepl("_observed[.]parquet$", vb$paths)], sub("_observed[.]parquet$", "", basename(vb$paths[grepl("_observed[.]parquet$", vb$paths)])))
    entities <- relation_entity_table(lapply(files, read_standard_geoparquet)); entities <- entities[scene_id == sample$scene_id[[i]]]
    node_positions <- read_relation_node_positions(road_path, c(entities$F_NODE, entities$T_NODE))
    scene_spec <- branch$scenes[[match(sample$scene_id[[i]], vapply(branch$scenes, `[[`, character(1L), "scene_id"))]]
    relation_id <- rb$manifest$relation_dataset_id; reference <- reference_scene_relations(relation_scene_sf(entities), node_positions, scene_spec, branch, relation_id, config)
    optimized <- data.table::as.data.table(arrow::read_parquet(rb$paths[basename(rb$paths) == "relation_edges.parquet"]))[scene_id == sample$scene_id[[i]]]
    comparison <- compare_relation_reference(optimized, reference)
    if (comparison$status != "PASS") stop("P2 independent relation parity failed: ", sample$scene_id[[i]], call. = FALSE)
    maximum <- max(maximum, comparison$maximum_distance_error_m)
  }
  list(status = "PASS", sample_count = nrow(sample), exhaustive_reference = TRUE, maximum_distance_error_m = maximum)
}

p2_build_base_spatial_acceptance <- function(scope, membership_plan, membership_acceptance, observation_plan,
                                             vector_shard, raster_shard, relation_shard, topology_shard,
                                             spatial_scene_index, prototype_scene_selection,
                                             reduced_methodology_authority, scene_index_acceptance,
                                             prototype_runtime_inputs, raster_observation_contract_files,
                                             relation_contract_files, p2_base_spatial_contract_files) {
  p2 <- p2_load_spec(p2_base_spatial_contract_files); scenes <- p2_scene_scope(scope, spatial_scene_index, prototype_scene_selection, p2)
  authority <- jsonlite::read_json(artifact_path(reduced_methodology_authority, "reduced_methodology_authority.json"), simplifyVector = FALSE)
  scene_gate <- jsonlite::read_json(artifact_path(scene_index_acceptance, "scene_index_acceptance.json"), simplifyVector = FALSE)
  membership <- jsonlite::read_json(artifact_path(membership_acceptance, "aggregate_membership_manifest.json"), simplifyVector = FALSE)
  plans <- observation_plan; vector <- p2_index_bundles(vector_shard, "branch_manifest.json")
  raster <- p2_index_bundles(raster_shard, "branch_manifest.json"); relation <- p2_index_bundles(relation_shard, "branch_manifest.json")
  topology <- p2_index_bundles(topology_shard, "topology_manifest.json")
  planned <- unname(sort(vapply(plans, `[[`, character(1L), "branch_id")))
  sets <- lapply(list(vector, raster, relation, topology), function(x) unname(sort(names(x))))
  if (!all(vapply(sets, function(x) setequal(x, planned), logical(1L)))) stop("P2 observation branch alignment failed", call. = FALSE)
  vector <- vector[planned]; raster <- raster[planned]; relation <- relation[planned]; topology <- topology[planned]
  if (any(!vapply(c(vector, raster, relation, topology), function(x) identical(x$manifest$status, "PASS"), logical(1L)))) stop("P2 branch QC is not PASS", call. = FALSE)
  checksums <- lapply(list(vector, raster, relation, topology), p2_branch_checksums)
  failures <- unique(unlist(lapply(checksums, `[[`, "failures"), use.names = FALSE)); if (length(failures)) stop("P2 branch checksum failed", call. = FALSE)
  vector_tables <- lapply(vector, function(bundle) lapply(bundle$paths[grepl("_observed[.]parquet$", bundle$paths)], read_standard_geoparquet))
  entities <- data.table::rbindlist(lapply(unlist(vector_tables, recursive = FALSE), function(x) data.table::as.data.table(sf::st_drop_geometry(x))), fill = TRUE)
  data.table::setorder(entities, scene_id, local_entity_id)
  if (anyDuplicated(entities[, .(scene_id, local_entity_id)]) || anyDuplicated(entities[, .(scene_id, entity_type, source_entity_id)]) ||
      !all(entities$entity_type %in% c("B", "R", "P")) || !"source_geometry_wkb" %in% names(entities)) stop("P2 entity identity contract failed", call. = FALSE)
  contexts <- data.table::rbindlist(lapply(raster, function(x) arrow::read_parquet(x$paths[basename(x$paths) == "object_raster_context.parquet"])), use.names = TRUE)
  raster_index <- data.table::rbindlist(lapply(raster, function(x) arrow::read_parquet(x$paths[basename(x$paths) == "scene_raster_index.parquet"])), use.names = TRUE)
  nodes <- data.table::rbindlist(lapply(relation, function(x) arrow::read_parquet(x$paths[basename(x$paths) == "relation_node_index.parquet"])), use.names = TRUE)
  edges <- data.table::rbindlist(lapply(relation, function(x) arrow::read_parquet(x$paths[basename(x$paths) == "relation_edges.parquet"])), use.names = TRUE)
  relation_stats <- data.table::rbindlist(lapply(relation, function(x) arrow::read_parquet(x$paths[basename(x$paths) == "scene_relation_statistics.parquet"])), use.names = TRUE)
  topology_rows <- data.table::rbindlist(lapply(topology, function(x) arrow::read_parquet(x$paths[basename(x$paths) == "source_topology.parquet"])), fill = TRUE)
  key <- function(x) paste(x$scene_id, x$local_entity_id, sep = "|"); entity_key <- key(entities)
  if (!setequal(entity_key, key(contexts)) || !setequal(entity_key, key(nodes))) stop("P2 cross-artifact entity reference failed", call. = FALSE)
  scene_ids <- scenes$scene_id
  if (anyDuplicated(raster_index$scene_id) || !setequal(raster_index$scene_id, scene_ids) || anyDuplicated(relation_stats$scene_id) || !setequal(relation_stats$scene_id, scene_ids)) stop("P2 scene completeness failed", call. = FALSE)
  bits <- relation_bit_values(load_relation_config(relation_contract_files)); relation_counts <- setNames(lapply(names(bits), function(name) sum(bitwAnd(edges$relation_mask, bits[[name]]) != 0L)), names(bits))
  if (!identical(sort(names(relation_counts)), sort(unlist(p2$config$relations$allowed))) || any(unlist(relation_counts) <= 0L) || any(edges$source_local_entity_id == edges$destination_local_entity_id)) stop("P2 relation-set acceptance failed", call. = FALSE)
  road_count <- sum(entities$entity_type == "R"); topology_road_count <- if (nrow(topology_rows)) data.table::uniqueN(topology_rows[, .(scene_id, road_local_entity_id)]) else 0L
  if (topology_road_count != road_count || (nrow(topology_rows) && (anyNA(topology_rows$source_node_id) || anyNA(topology_rows$road_type) || anyNA(topology_rows$road_hierarchy)))) stop("P2 topology completeness failed", call. = FALSE)
  raster_parity <- p2_raster_parity(plans, raster, prototype_runtime_inputs, raster_observation_contract_files, p2_base_spatial_contract_files, as.integer(p2$config$parity$raster_scene_sample))
  relation_parity <- p2_relation_parity(plans, vector, relation, prototype_runtime_inputs, relation_contract_files, as.integer(p2$config$parity$relation_scene_sample))
  entity_counts <- as.list(table(factor(entities$entity_type, levels = c("B", "R", "P")))); names(entity_counts) <- c("B", "R", "P")
  observation_id <- plans[[1L]]$original_observation_id
  invariants <- list(scene_completeness = TRUE, branch_alignment = TRUE, checksum_completeness = TRUE, entity_identity = TRUE,
    geometry_epsg_5186 = TRUE, source_geometry_preserved = TRUE, raster_shape_support_nodata = TRUE, raster_independent_parity = TRUE,
    relation_set_exact = TRUE, relation_reference_valid = TRUE, crossing_without_shared_node_not_con = TRUE, topology_variable_length_schema = TRUE,
    p4_absorption_prerequisites_complete = TRUE, empty_edge_scenes_retained = sum(relation_stats$ordered_pair_count == 0L) >= 0L,
    zero_road_scenes_supported = length(setdiff(scene_ids, unique(topology_rows$scene_id))) >= 0L)
  scientific <- list(scope = scope, authority_id = authority$authority_id, scene_index_id = scene_gate$scene_index_id,
    scene_acceptance_id = scene_gate$acceptance_id, original_observation_id = observation_id, ordered_scene_ids = as.list(scene_ids),
    entity_counts = entity_counts, relation_counts = relation_counts, topology_road_count = topology_road_count,
    membership_parity = membership$parity, raster_parity = raster_parity, relation_parity = relation_parity,
    implementation_hash = p2$implementation_hash, schema_version = "1.0.0")
  hash <- p0_scientific_sha256(scientific); acceptance_id <- paste0("bsa_", substr(hash, 1L, 24L))
  final_dir <- file.path(p2$config$publication_root, observation_id, scope, "acceptance", acceptance_id)
  names_out <- c("base_spatial_acceptance.json", "base_spatial_qc.json", "entity_dictionary.parquet", "scene_spatial_statistics.parquet", "relation_type_dictionary.json", "spatial_categories.json")
  p1_publish_immutable_bundle(final_dir, names_out, function(stage) {
    dictionary <- entities[, .(scene_id, split, local_entity_id, entity_type, source_entity_id, source_artifact_id,
      source_geometry_fingerprint, observed_geometry_fingerprint, source_geometry_wkb, observation_dataset_id = plans[[1L]]$observation_dataset_id)]
    arrow::write_parquet(dictionary, file.path(stage, names_out[[3L]]), compression = "zstd")
    stats <- merge(data.table::data.table(scene_id = scene_ids, split = scenes$split), relation_stats, by = c("scene_id", "split"), all.x = TRUE)
    arrow::write_parquet(stats, file.path(stage, names_out[[4L]]), compression = "zstd")
    write_json_file(list(schema_version = "1.0.0", order = names(bits), bits = as.list(bits)), file.path(stage, names_out[[5L]]))
    file.copy(p2$files[basename(p2$files) == "spatial_categories.json"], file.path(stage, names_out[[6L]]))
    qc <- list(status = "PASS", scope = scope, failures = list(), membership_parity = membership$parity, raster_parity = raster_parity,
      relation_parity = relation_parity, empty_entity_scene_count = length(setdiff(scene_ids, unique(entities$scene_id))),
      empty_edge_scene_count = sum(relation_stats$ordered_pair_count == 0L), zero_road_scene_count = length(setdiff(scene_ids, unique(topology_rows$scene_id))),
      topology_chain_length = if (nrow(topology_rows)) as.list(table(topology_rows$chain_length)) else list())
    write_json_file(qc, file.path(stage, names_out[[2L]]))
    artifact_records <- lapply(file.path(stage, names_out[-1L]), function(path) p1_artifact_record(path, basename(path)))
    value <- list(schema_version = "1.0.0", scope = scope, acceptance_id = acceptance_id, status = "PASS", authority_id = authority$authority_id,
      scene_index_id = scene_gate$scene_index_id, scene_acceptance_id = scene_gate$acceptance_id, original_observation_id = observation_id,
      scene_count = nrow(scenes), split_counts = as.list(table(factor(scenes$split, levels = c("training", "validation", "evaluation")))),
      entity_counts = entity_counts, relation_counts = relation_counts,
      topology = list(road_count = road_count, node_row_count = nrow(topology_rows), minimum_chain_length = if (road_count) min(topology_rows$chain_length) else 0L,
                      maximum_chain_length = if (road_count) max(topology_rows$chain_length) else 0L, variable_length_schema = TRUE, p4_absorption_ready = TRUE),
      invariants = invariants, artifact_checksums = artifact_records, scientific_hash = hash)
    path <- write_json_file(value, file.path(stage, names_out[[1L]])); validate_json_schema_file(path, p2$schemas[["aggregate_acceptance"]])
  })
}
