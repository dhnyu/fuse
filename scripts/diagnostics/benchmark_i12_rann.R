#!/usr/bin/env Rscript

# I12 diagnostic only: compare exact SN candidate generators without publishing artifacts.
source("_targets.R")

parse_option <- function(name, default) {
  prefix <- paste0("--", name, "=")
  value <- grep(paste0("^", prefix), commandArgs(trailingOnly = TRUE), value = TRUE)
  if (!length(value)) default else sub(prefix, "", value[[1L]], fixed = TRUE)
}

scene_path <- parse_option("scenes", "/tmp/fuse_i12_320_scenes_classified.rds")
output_path <- parse_option("output", "/tmp/fuse_i12_rann_benchmark.json")
scope <- parse_option("scope", "all")
repetitions <- as.integer(parse_option("repetitions", "3"))
workers <- as.integer(parse_option("workers", "20"))
parity_only <- identical(parse_option("parity-only", "false"), "true")
stopifnot((parity_only || repetitions >= 3L), workers >= 1L)

config <- load_relation_config(targets::tar_read(relation_contract_files))
scenes <- readRDS(scene_path)

geometry_bbox_center_radius <- function(geometry) {
  boxes <- t(vapply(geometry, function(value) as.numeric(sf::st_bbox(value)), numeric(4L)))
  centers <- cbind((boxes[, 1L] + boxes[, 3L]) / 2, (boxes[, 2L] + boxes[, 4L]) / 2)
  radii <- sqrt(((boxes[, 3L] - boxes[, 1L]) / 2)^2 + ((boxes[, 4L] - boxes[, 2L]) / 2)^2)
  list(center = centers, radius = radii)
}

point_coordinates <- function(scene, index) {
  value <- sf::st_coordinates(sf::st_geometry(scene[index, ]))
  if (nrow(value) != length(index)) stop("P_out geometry is not one point per entity", call. = FALSE)
  unname(value[, c("X", "Y"), drop = FALSE])
}

rann_radius_lists <- function(data, query, radius, block_size = 128L) {
  if (!nrow(query) || !nrow(data)) return(vector("list", nrow(query)))
  # k = all destinations is deliberate: RANN's fixed-width result cannot otherwise
  # prove that a dense radius query was not truncated.
  k <- nrow(data)
  blocks <- split(seq_len(nrow(query)), ceiling(seq_len(nrow(query)) / block_size))
  answer <- vector("list", nrow(query))
  for (block in blocks) {
    result <- RANN::nn2(data = data, query = query[block, , drop = FALSE], k = k,
                        searchtype = "radius", radius = radius, eps = 0)
    for (i in seq_along(block)) answer[[block[[i]]]] <- result$nn.idx[i, result$nn.idx[i, ] > 0L]
  }
  answer
}

candidate_lists <- function(scene, state, source_state, destination, radius, method,
                            block_size = 128L) {
  source <- which(state == source_state)
  if (!length(source) || !length(destination)) return(list(source = integer(), candidates = list()))
  if (method == "geos" || source_state != "P_out") {
    blocks <- split(source, ceiling(seq_along(source) / block_size))
    candidates <- unlist(lapply(blocks, function(block) {
      nearby <- sf::st_is_within_distance(scene[block, ], scene[destination, ], dist = radius, sparse = TRUE)
      lapply(seq_along(block), function(i) destination[nearby[[i]]])
    }), recursive = FALSE)
    return(list(source = source, candidates = candidates))
  }

  point_destination <- which(state == "P_out")
  geometry_destination <- setdiff(destination, point_destination)
  geometry_candidates <- if (length(geometry_destination)) {
    nearby <- sf::st_is_within_distance(scene[source, ], scene[geometry_destination, ], dist = radius, sparse = TRUE)
    lapply(nearby, function(value) geometry_destination[value])
  } else vector("list", length(source))
  point_data <- point_coordinates(scene, point_destination)
  point_query <- point_coordinates(scene, source)
  point_candidates <- if (method == "rann_point") {
    lapply(rann_radius_lists(point_data, point_query, radius), function(value) point_destination[value])
  } else if (method == "dbscan_point") {
    result <- dbscan::frNN(point_data, eps = radius, query = point_query, sort = FALSE, approx = 0)
    lapply(result$id, function(value) point_destination[value])
  } else {
    stop("Unknown point candidate method: ", method, call. = FALSE)
  }
  list(source = source, candidates = Map(c, geometry_candidates, point_candidates))
}

bbox_candidate_lists <- function(scene, state, source_state, destination, radius,
                                 block_size = 128L) {
  source <- which(state == source_state)
  if (!length(source) || !length(destination)) return(list(source = integer(), candidates = list(), bound_misses = 0L))
  bounds <- geometry_bbox_center_radius(sf::st_geometry(scene))
  blocks <- split(seq_along(source), ceiling(seq_along(source) / block_size))
  answer <- vector("list", length(source))
  bound_misses <- 0L
  for (positions in blocks) {
    source_index <- source[positions]
    global_radius <- radius + max(bounds$radius[source_index]) + max(bounds$radius[destination])
    raw <- rann_radius_lists(bounds$center[destination, , drop = FALSE],
                             bounds$center[source_index, , drop = FALSE], global_radius,
                             block_size = block_size)
    for (j in seq_along(positions)) {
      candidate <- destination[raw[[j]]]
      if (length(candidate)) {
        delta <- sweep(bounds$center[candidate, , drop = FALSE], 2L,
                       bounds$center[source_index[[j]], ], FUN = "-")
        center_distance <- sqrt(rowSums(delta^2))
        candidate <- candidate[center_distance <= radius + bounds$radius[source_index[[j]]] +
                                 bounds$radius[candidate] + 1e-9]
      }
      answer[[positions[[j]]]] <- candidate
    }
  }
  exact <- sf::st_is_within_distance(scene[source, ], scene[destination, ], dist = radius, sparse = TRUE)
  for (i in seq_along(source)) {
    expected <- destination[exact[[i]]]
    bound_misses <- bound_misses + length(setdiff(expected, answer[[i]]))
  }
  list(source = source, candidates = answer, bound_misses = bound_misses)
}

scene_sn_edges_method <- function(scene, state, config, method) {
  bits <- relation_bit_values(config)
  radius <- as.numeric(config$scientific$sn$radius_m)
  top_k <- as.integer(config$scientific$sn$top_k)
  tolerance <- as.numeric(config$scientific$sn$distance_tie_tolerance_m)
  selected <- list(); position <- 0L; candidate_count <- 0L; max_candidate_count <- 0L; bound_misses <- 0L
  for (source_state in c("B", "R", "P_in", "P_out")) {
    destination <- which(state %in% sn_eligible_destination_states(source_state))
    value <- if (method == "rann_bbox") {
      bbox_candidate_lists(scene, state, source_state, destination, radius)
    } else {
      candidate_lists(scene, state, source_state, destination, radius, method)
    }
    bound_misses <- bound_misses + (value$bound_misses %||% 0L)
    blocks <- split(seq_along(value$source), ceiling(seq_along(value$source) / 128L))
    for (block in blocks) {
      destination_by_source <- lapply(block, function(i) {
        candidate <- unique(value$candidates[[i]])
        candidate[candidate != value$source[[i]]]
      })
      candidate_lengths <- lengths(destination_by_source)
      candidate_count <- candidate_count + sum(candidate_lengths)
      max_candidate_count <- max(max_candidate_count, candidate_lengths, 0L)
      flat_destination <- unlist(destination_by_source, use.names = FALSE)
      flat_distance <- if (length(flat_destination)) {
        as.numeric(sf::st_distance(
          scene[rep(value$source[block], candidate_lengths), ], scene[flat_destination, ], by_element = TRUE
        ))
      } else numeric()
      cursor <- 0L
      for (j in seq_along(block)) {
        source_index <- value$source[[block[[j]]]]
        destination_index <- destination_by_source[[j]]
        if (!length(destination_index)) next
        positions <- seq.int(cursor + 1L, cursor + length(destination_index))
        distance <- flat_distance[positions]
        cursor <- cursor + length(destination_index)
        keep <- is.finite(distance) & distance <= radius
        destination_index <- destination_index[keep]; distance <- distance[keep]
        if (!length(destination_index)) next
        ordering <- order(round(distance / tolerance) * tolerance,
                          scene$local_entity_id[destination_index], method = "radix")
        ordering <- head(ordering, top_k); position <- position + 1L
        selected[[position]] <- data.table::data.table(
          source_local_entity_id = as.integer(scene$local_entity_id[source_index]),
          destination_local_entity_id = as.integer(scene$local_entity_id[destination_index[ordering]]),
          distance_m = distance[ordering], sn_rank = seq_along(ordering)
        )
      }
    }
  }
  selected <- data.table::rbindlist(selected)
  if (!nrow(selected)) return(list(edges = relation_empty_edges(), candidate_count = candidate_count,
                                    max_candidate_count = max_candidate_count,
                                    retained_selection_count = 0L, bound_misses = bound_misses))
  selected[, `:=`(pair_min = pmin(source_local_entity_id, destination_local_entity_id),
                  pair_max = pmax(source_local_entity_id, destination_local_entity_id))]
  pairs <- selected[, .(distance_m = min(distance_m)), by = .(pair_min, pair_max)]
  forward <- selected[, .(pair_min, pair_max, selected_source = source_local_entity_id, sn_rank)]
  direction <- function(source, destination) {
    value <- data.table::data.table(pair_min = pairs$pair_min, pair_max = pairs$pair_max,
                                    source_local_entity_id = source, destination_local_entity_id = destination)
    source_rank <- forward[value, on = .(pair_min, pair_max, selected_source = source_local_entity_id), sn_rank]
    destination_rank <- forward[value, on = .(pair_min, pair_max, selected_source = destination_local_entity_id), sn_rank]
    data.table::data.table(
      source_local_entity_id = source, destination_local_entity_id = destination,
      relation_bit = bits[["SN"]], distance_m = pairs$distance_m,
      sn_source_rank = as.integer(source_rank), sn_destination_rank = as.integer(destination_rank),
      host_building_local_entity_id = NA_integer_, shared_original_node_id = NA_character_
    )
  }
  edges <- data.table::rbindlist(list(direction(pairs$pair_min, pairs$pair_max),
                                      direction(pairs$pair_max, pairs$pair_min)))
  data.table::setorder(edges, source_local_entity_id, destination_local_entity_id)
  list(edges = edges, candidate_count = candidate_count,
       max_candidate_count = max_candidate_count,
       retained_selection_count = nrow(selected), bound_misses = bound_misses)
}

edge_digest <- function(value) {
  value <- data.table::copy(value)
  data.table::setorder(value, source_local_entity_id, destination_local_entity_id, relation_bit)
  tmp <- tempfile(fileext = ".rds"); on.exit(unlink(tmp), add = TRUE)
  saveRDS(value, tmp, version = 3, compress = FALSE)
  digest::digest(file = tmp, algo = "sha256", serialize = FALSE)
}

run_one <- function(item, method) {
  before <- proc.time(); started <- Sys.time()
  value <- if (method == "production") {
    result <- scene_sn_edges(item$scene, item$state, config)
    result$bound_misses <- 0L
    result$max_candidate_count <- NA_integer_
    result
  } else {
    scene_sn_edges_method(item$scene, item$state, config, method)
  }
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs")); cpu <- proc.time() - before
  list(scene_id = item$scene_id, method = method, wall_seconds = elapsed,
       user_seconds = unname(cpu[["user.self"]]), system_seconds = unname(cpu[["sys.self"]]),
       candidate_count = value$candidate_count, exact_distance_count = value$candidate_count,
       max_candidate_count = value$max_candidate_count,
       retained_selection_count = value$retained_selection_count, edge_count = nrow(value$edges),
       bound_misses = value$bound_misses, digest = edge_digest(value$edges))
}

inventory <- data.table::rbindlist(lapply(scenes, function(item) {
  counts <- table(factor(item$state, levels = c("B", "R", "P_in", "P_out")))
  data.table::data.table(scene_id = item$scene_id, entities = nrow(item$scene),
                         B = counts[[1L]], R = counts[[2L]], P_in = counts[[3L]], P_out = counts[[4L]])
}))
data.table::setorder(inventory, entities, scene_id)
if (scope == "selected") {
  selected_ids <- inventory[c(1L, ceiling(.N / 2), .N), scene_id]
  scenes <- scenes[vapply(scenes, function(item) item$scene_id %in% selected_ids, logical(1L))]
} else if (scope != "all") stop("scope must be selected or all", call. = FALSE)

methods <- c("production", "rann_point", "dbscan_point", "rann_bbox")
# One explicit warm-up precedes the three recorded warm-cache repetitions.
if (!parity_only) {
  invisible(parallel::mclapply(scenes, run_one, method = "production", mc.cores = workers, mc.preschedule = FALSE))
}
records <- list(); position <- 0L
for (method in methods) {
  for (repetition in seq_len(if (parity_only) 1L else repetitions)) {
    gc(full = TRUE)
    started <- Sys.time(); cpu <- proc.time()
    values <- parallel::mclapply(scenes, run_one, method = method,
                                 mc.cores = workers, mc.preschedule = FALSE)
    aggregate_cpu <- proc.time() - cpu
    position <- position + 1L
    records[[position]] <- list(
      method = method, repetition = repetition,
      wall_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
      parent_user_seconds = unname(aggregate_cpu[["user.self"]]),
      parent_system_seconds = unname(aggregate_cpu[["sys.self"]]), values = values
    )
    cat(method, repetition, records[[position]]$wall_seconds, "seconds\n")
  }
}

reference <- records[[which(vapply(records, function(value) value$method == "production", logical(1L)))[[1L]]]]$values
reference <- setNames(reference, vapply(reference, `[[`, character(1L), "scene_id"))
parity <- lapply(methods, function(method) {
  values <- records[[which(vapply(records, function(value) value$method == method, logical(1L)))[[1L]]]]$values
  comparisons <- lapply(values, function(value) {
    baseline <- reference[[value$scene_id]]
    list(scene_id = value$scene_id, digest_equal = identical(value$digest, baseline$digest),
         candidate_delta = value$candidate_count - baseline$candidate_count,
         bound_misses = value$bound_misses)
  })
  list(method = method, scenes = length(values), digest_mismatches = sum(!vapply(comparisons, `[[`, logical(1L), "digest_equal")),
       bound_misses = sum(vapply(comparisons, `[[`, integer(1L), "bound_misses")), comparisons = comparisons)
})

result <- list(
  generated_at = kst_now(), scope = scope, scene_count = length(scenes), repetitions = repetitions,
  workers = workers, parity_only = parity_only,
  radius_m = config$scientific$sn$radius_m, top_k = config$scientific$sn$top_k,
  rann = list(eps = 0, k_contract = "k equals the complete destination population in every query",
              truncation_possible = FALSE), inventory = inventory, parity = parity, runs = records
)
jsonlite::write_json(result, output_path, auto_unbox = TRUE, pretty = TRUE, digits = 16, na = "null")
cat(normalizePath(output_path, mustWork = TRUE), "\n")
