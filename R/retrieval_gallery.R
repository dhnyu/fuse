# Supplement to Results: Spatial Scene Retrieval. Sampling uses the accepted
# off-grid 50 m rule; P2 relation/raster mathematics and P3 v3 bytes are reused.
retrieval_source_helpers <- function() {
  files <- c("config_paths", "io_spatial", "research_contracts",
    "research_canonical_config", "research_methodology_authority",
    "research_runtime_mirror", "research_scene_index", "research_scene_index_reduced",
    "research_membership", "research_observation", "research_raster_observation",
    "research_relation", "research_spatial_acceptance", "research_base_spatial",
    "research_original_scene_cache")
  for (name in files) sys.source(file.path("R", paste0(name, ".R")), envir = .GlobalEnv)
}

retrieval_sample <- function(config, output) {
  if (dir.exists(output)) stop("Sampling output already exists; immutable output required")
  contract <- yaml::read_yaml(config)
  cfg <- contract$scientific
  p1 <- yaml::read_yaml("config/p1_scene_index.yml")
  paths <- yaml::read_yaml("config/research_paths.yml")
  old <- arrow::read_parquet(p1$off_grid_source$parquet$path)
  old <- old[order(old$off_grid_order), ]
  index_path <- file.path(p1$publication$root, "rsi_80031f1493c75163f91b7c71", "spatial_scene_index.parquet")
  canonical <- arrow::read_parquet(index_path)
  training <- sf::st_as_sf(canonical[canonical$split == "training", c("center_x", "center_y")],
    coords = c("center_x", "center_y"), crs = 5186)
  boundary <- sf::st_union(sf::st_read(paths$inputs$boundary, paths$layers$boundary, quiet = TRUE))
  buffer <- sf::st_union(sf::st_read(paths$inputs$buffer400, paths$layers$buffer400, quiet = TRUE))
  bbox <- sf::st_bbox(boundary)
  generate <- function(additional_count = cfg$supplemental_count) {
    suppressWarnings(RNGversion(cfg$rng_version))
    RNGkind(cfg$rng_kind, cfg$normal_kind, cfg$sample_kind)
    set.seed(cfg$seed)
    accepted <- list(); count <- 0L; batch <- 0L; first_eligible <- NULL
    while (count < cfg$skip_accepted_positions + additional_count) {
      batch <- batch + 1L
      u <- matrix(runif(2L * cfg$candidate_batch_size), ncol = 2L, byrow = TRUE)
      xy <- data.frame(x = bbox[[1]] + u[, 1] * (bbox[[3]] - bbox[[1]]),
        y = bbox[[2]] + u[, 2] * (bbox[[4]] - bbox[[2]]))
      points <- sf::st_as_sf(xy, coords = c("x", "y"), crs = 5186)
      inside <- which(lengths(sf::st_intersects(points, boundary)) > 0L)
      nearest <- sf::st_nearest_feature(points[inside, ], training)
      distance <- as.numeric(sf::st_distance(points[inside, ], training[nearest, ], by_element = TRUE))
      good <- inside[distance >= cfg$minimum_training_distance_m]
      if (batch == 1L) first_eligible <- length(good)
      keep <- head(good, cfg$skip_accepted_positions + additional_count - count)
      xy <- xy[keep, , drop = FALSE]
      xy$candidate_ordinal <- (batch - 1L) * cfg$candidate_batch_size + keep
      accepted[[batch]] <- xy; count <- count + nrow(xy)
      if (batch > 100L) stop("Supplemental sampling guard exceeded")
    }
    list(rows = do.call(rbind, accepted), batches = batch, first_eligible = first_eligible)
  }
  started <- proc.time()[[3]]
  a <- generate(); b <- generate()
  stopifnot(identical(a, b), identical(a$rows$x[1:2000], old$x), identical(a$rows$y[1:2000], old$y))
  nested_timings <- lapply(c(100L, 500L, 1000L), function(n) {
    start <- proc.time()[[3]]
    nested <- generate(n)
    elapsed <- proc.time()[[3]] - start
    stopifnot(identical(nested$rows$x, head(a$rows$x, 2000L + n)),
      identical(nested$rows$y, head(a$rows$y, 2000L + n)))
    list(count = n, wall_seconds = elapsed, candidates_generated = nested$batches * 8192L,
      exact_nested_prefix = TRUE)
  })
  rows <- a$rows[2001:10400, ]
  rows$stream_ordinal <- 2001:10400
  rows$scene_id <- vapply(seq_len(nrow(rows)), function(i) paste0(cfg$scene_prefix,
    substr(digest::digest(paste(contract$contract_version,
      rows$stream_ordinal[i], sprintf("%.17g", rows$x[i]), sprintf("%.17g", rows$y[i]),
      sep = "|"), algo = "sha256", serialize = FALSE), 1, 24)), character(1))
  rows$split <- "retrieval_only"
  rows$center_x <- rows$x; rows$center_y <- rows$y
  rows$xmin <- rows$x - 250; rows$xmax <- rows$x + 250
  rows$ymin <- rows$y - 250; rows$ymax <- rows$y + 250
  points <- sf::st_as_sf(rows, coords = c("x", "y"), crs = 5186, remove = FALSE)
  nearest <- sf::st_nearest_feature(points, training)
  rows$nearest_training_center_m <- as.numeric(sf::st_distance(points, training[nearest, ], by_element = TRUE))
  footprints <- sf::st_sf(rows, geometry = square_footprints(rows$x, rows$y, 500), crs = 5186)
  stopifnot(!anyDuplicated(rows[, c("x", "y")]), !anyDuplicated(rows$scene_id),
    !any(rows$scene_id %in% canonical$scene_id),
    !anyDuplicated(rbind(old[, c("x", "y")], rows[, c("x", "y")])),
    all(rows$nearest_training_center_m >= 50),
    all(lengths(sf::st_covered_by(points, boundary)) > 0),
    all(lengths(sf::st_covered_by(footprints, buffer)) > 0))
  dir.create(output, recursive = TRUE, showWarnings = FALSE)
  write_geo_parquet(footprints, file.path(output, "supplemental_scene_index.parquet"))
  write_json_file(list(status = "PASS", exact_prefix = TRUE, deterministic_replay = TRUE,
    count = nrow(rows), canonical_counts = as.list(table(canonical$split)),
    first_batch_eligible = a$first_eligible, batches = a$batches,
    candidates_generated = a$batches * 8192L, minimum_training_distance_m = min(rows$nearest_training_center_m),
    coordinate_duplicates = 0L, id_collisions = 0L, domain_violations = 0L, buffer_violations = 0L,
    sampler_wall_seconds = proc.time()[[3]] - started,
    nested_sampling_benchmarks = nested_timings,
    index_sha256 = sha256_file(file.path(output, "supplemental_scene_index.parquet"))),
    file.path(output, "sampling_qc.json"))
}

retrieval_contract_paths <- function(paths) {
  replace <- grepl("prototype_(vector_observation|raster_observation|relation)[.]schema[.]json$", paths)
  paths[replace] <- file.path(getwd(), "config/schemas/retrieval_gallery", basename(paths[replace]))
  paths
}

retrieval_order_scenes <- function(scenes) {
  scenes[order(vapply(scenes, `[[`, character(1), "scene_id"), method = "radix")]
}

retrieval_spatial_branch <- function(job_path) {
  job <- jsonlite::read_json(job_path, simplifyVector = FALSE)
  root <- job$root
  dir.create(root, recursive = TRUE, showWarnings = FALSE)
  paths <- yaml::read_yaml("config/research_paths.yml")
  inputs <- unlist(paths$inputs, use.names = TRUE)
  membership <- load_membership_config(membership_contract_paths())
  vector_paths <- retrieval_contract_paths(observation_contract_paths())
  raster_paths <- retrieval_contract_paths(raster_observation_contract_paths())
  relation_paths <- retrieval_contract_paths(relation_contract_paths())
  vector <- load_observation_config(vector_paths)
  inventory_path <- file.path("/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/index/_inputs",
    "rin_fc622f56cb4afdcb9a5db08b/study_data_inventory.json")
  sources <- p2_source_contract(jsonlite::read_json(inventory_path, simplifyVector = FALSE), membership, getwd())
  # The accepted relation statistics helper pairs results with specs by position.
  # Its kernel sorts IDs; shard processing must use that same order. Union order
  # remains the independent source-stream order in the scene index.
  scenes <- retrieval_order_scenes(job$scenes)
  ids <- vapply(scenes, `[[`, character(1), "scene_id")
  spec <- list(scope = "retrieval_only", branch_id = job$branch_id,
    membership_dataset_id = job$dataset_id, prototype_id = "supplemental_retrieval_only",
    scene_index_id = job$index_id, scene_ids = as.list(ids), scenes = scenes,
    split_counts = list(retrieval_only = length(scenes)), sources = sources,
    membership_contract = list(version = membership$scientific$membership_predicate_version,
      predicates = membership$scientific$predicates, geometry_policy = membership$scientific$geometry_policy),
    output = list(directory = file.path(root, "membership")),
    execution = list(controller = "retrieval_spatial", workers = 1L, threads = 1L))
  output <- list(); timings <- list()
  stage <- function(name, expression) {
    t <- proc.time()[[3]]; value <- force(expression)
    timings[[name]] <<- proc.time()[[3]] - t
    value
  }
  output$membership <- stage("membership", p2_build_membership_shard(spec, inputs, inputs, membership_contract_paths()))
  member_paths <- output$membership[grepl("_membership.parquet$", output$membership)]
  tables <- lapply(member_paths, arrow::read_parquet)
  counts <- setNames(vapply(c("B", "R", "P"), function(k)
    sum(vapply(tables, function(x) sum(x$entity_type == k), integer(1))), numeric(1)), c("building", "road", "poi"))
  acceptance_path <- file.path(root, "aggregate_membership_manifest.json")
  write_json_file(list(membership_dataset_id = job$dataset_id, status = "PASS"), acceptance_path)
  spec$observation_dataset_id <- paste0("retrvec_", job$branch_id)
  spec$original_observation_id <- job$dataset_id
  spec$estimated_counts <- c(as.list(counts), list(total = sum(counts)))
  spec$estimated_geometry <- list(coordinate_count = 0, component_count = 0, source_geometry_bytes = 0,
    estimated_cost = sum(counts), dense_singleton = FALSE)
  spec$shared_grouping <- list(grouping_version = "1.0.0", immutable_scene_group = TRUE)
  spec$membership_parquets <- as.list(member_paths)
  spec$contract <- list(config_hash = vector$scientific_hash,
    schema_hash = vector$schema_hash, implementation_source_hash = vector$implementation_source_hash,
    observation_contract_version = vector$scientific$observation_contract_version)
  spec$output$directory <- file.path(root, "observations", "vector", "branches", job$branch_id)
  spec$.path <- file.path(root, paste0("spec-", job$branch_id, ".json"))
  write_json_file(spec, spec$.path)
  output$vector <- stage("vector", p2_build_vector_shard(spec, acceptance_path, inputs, inputs, vector_paths))
  output$topology <- stage("topology", p2_build_topology_shard(spec, output$vector, inputs,
    p2_base_spatial_contract_paths(), output_directory = file.path(root, "topology"),
    manifest_schema = "config/schemas/retrieval_topology.schema.json"))
  output$raster <- stage("raster", p2_build_raster_shard(spec, output$vector, inputs, inputs, raster_paths))
  output$relations <- stage("relations", p2_build_relation_shard(spec, output$vector, inputs, inputs, relation_paths))
  retrieval_validate_relation_statistics(output$relations)
  groups <- p3_output_groups(job$branch_id, list(output$vector), list(output$raster),
    list(output$relations), list(output$topology), member_paths, spec$.path)
  serialization_spec <- list(source_groups = groups)
  write_json_file(serialization_spec, file.path(root, "serialization_spec.json"))
  rel <- jsonlite::read_json(output$relations[basename(output$relations) == "branch_manifest.json"])
  write_json_file(list(status = "PASS", branch_id = job$branch_id, scene_ids = as.list(ids),
    count = length(ids), entities = sum(counts), relation_edges = rel$ordered_pair_count,
    timings = timings, max_rss_kb = proc_max_rss_kb(), io = proc_io_snapshot(),
    files = output, serialization_spec = file.path(root, "serialization_spec.json")),
    file.path(root, "spatial_result.json"))
}

retrieval_validate_relation_statistics <- function(paths) {
  edges <- data.table::as.data.table(arrow::read_parquet(paths[basename(paths) == "relation_edges.parquet"]))
  nodes <- data.table::as.data.table(arrow::read_parquet(paths[basename(paths) == "relation_node_index.parquet"]))
  stats <- data.table::as.data.table(arrow::read_parquet(paths[basename(paths) == "scene_relation_statistics.parquet"]))
  bits <- relation_bit_values(load_relation_config(retrieval_contract_paths(relation_contract_paths())))
  for (i in seq_len(nrow(stats))) {
    sid <- stats$scene_id[[i]]
    e <- edges[scene_id == sid]; n <- nodes[scene_id == sid]
    checks <- c(stats$node_count[[i]] == nrow(n), stats$ordered_pair_count[[i]] == nrow(e),
      stats$outside_poi_count[[i]] >= 0,
      stats$contained_poi_count[[i]] + stats$outside_poi_count[[i]] == stats$poi_count[[i]])
    for (name in names(bits)) checks <- c(checks,
      stats[[paste0(tolower(name), "_edge_count")]][[i]] == sum(bitwAnd(e$relation_mask, bits[[name]]) != 0L))
    if (!all(checks)) stop("Supplemental per-scene relation statistics mismatch: ", sid)
  }
  invisible(TRUE)
}
