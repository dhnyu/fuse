#!/usr/bin/env Rscript

source(file.path(Sys.getenv("FUSE_REPO", "/members/dhnyu/fuse"), "R", "preprocessing_utils.R"))
set_single_thread_env()
cli <- parse_cli()
cfg <- load_preprocessing_config(cli$config)
ensure_preprocessing_dirs(cfg)
assert_free_space(cfg)
key <- "road"

layer_count <- function(dataset, layer) {
  as.numeric(ogr_scalar(dataset, sprintf('SELECT COUNT(*) AS n FROM "%s"', layer), "n"))
}

copy_spatial_layer <- function(source, destination, source_layer, target_layer, limit = NULL, create = FALSE, where = "") {
  where <- if (nzchar(where)) paste(" WHERE", where) else ""
  sql <- sprintf('SELECT *, \'%s\' AS source_archive, \'%s\' AS source_layer, ROWID AS source_record_index FROM "%s"%s%s',
                 basename(source_path(cfg, key)), source_layer, source_layer, where,
                 if (is.null(limit)) "" else sprintf(" LIMIT %d", limit))
  args <- c(if (create) c("-f", "GPKG") else c("-update", "-append"),
            destination, source, "--config", "SHAPE_ENCODING", cfg$road$source_encoding,
            "-dialect", "SQLite", "-sql", sql, "-nln", target_layer,
            "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO")
  run_cmd("ogr2ogr", args)
}

copy_attribute_layer <- function(source, destination, source_layer, target_layer, limit = NULL) {
  sql <- sprintf('SELECT *, \'%s\' AS source_archive, \'%s\' AS source_layer, ROWID AS source_record_index FROM "%s"%s',
                 basename(source_path(cfg, key)), source_layer, source_layer,
                 if (is.null(limit)) "" else sprintf(" LIMIT %d", limit))
  run_cmd("ogr2ogr", c("-update", destination, source, "--config", "SHAPE_ENCODING", cfg$road$source_encoding,
                        "-dialect", "SQLite", "-sql", sql, "-nln", target_layer,
                        "-nlt", "NONE", "-lco", "ASPATIAL_VARIANT=GPKG_ATTRIBUTES"))
}

with_failure_result(cfg, key, {
  started <- Sys.time()
  if (cli$mode == "production") assert_no_final_collision(cfg, key)
  source <- vsi_zip(source_path(cfg, key))
  run_tag <- if (cli$mode == "production") "production" else paste0("smoke_", run_id_now())
  stage_dir <- file.path(dataset_stage_dir(cfg, key), run_tag)
  dir.create(stage_dir, recursive = TRUE, showWarnings = FALSE)
  gpkg <- file.path(stage_dir, "korea_R.staging.gpkg")
  if (file.exists(gpkg)) stop("Refusing ambiguous existing road staging file: ", gpkg, call. = FALSE)

  source_layers <- c(links = "MOCT_LINK", nodes = "MOCT_NODE", multilink = "MULTILINK", turninfo = "TURNINFO")
  counts <- vapply(source_layers, function(x) layer_count(source, x), numeric(1L))
  expected <- c(links = cfg$road$expected_links, nodes = cfg$road$expected_nodes,
                multilink = cfg$road$expected_multilink, turninfo = cfg$road$expected_turninfo)
  if (cli$mode == "production" && !identical(as.numeric(counts), as.numeric(expected))) {
    stop("Road source count contract mismatch: ", paste(names(counts), counts, sep = "=", collapse = ", "), call. = FALSE)
  }
  smoke_limit <- if (cli$mode == "smoke") 100L else NULL
  copy_spatial_layer(source, gpkg, source_layers[["links"]], "links", smoke_limit, create = TRUE)
  copy_spatial_layer(source, gpkg, source_layers[["nodes"]], "nodes", smoke_limit)
  copy_attribute_layer(source, gpkg, source_layers[["multilink"]], "multilink", smoke_limit)
  copy_attribute_layer(source, gpkg, source_layers[["turninfo"]], "turninfo", smoke_limit)

  metadata_csv <- file.path(stage_dir, "metadata.csv")
  source_wkt <- paste(capture_cmd("ogrinfo", c("-ro", "-so", source, source_layers[["links"]])), collapse = "\n")
  source_wkt <- sub(".*Layer SRS WKT:\n", "", source_wkt)
  write_metadata_csv(metadata_csv, list(
    schema_version = cfg$schema_version, snapshot_id = cfg$snapshot_id,
    source_archive = basename(source_path(cfg, key)), source_sha256 = sha256_file(source_path(cfg, key)),
    source_crs_policy = "preserved custom source WKT; no relabel or datum transformation",
    source_wkt_excerpt = substr(source_wkt, 1L, 2000L), con_relation_created = FALSE, created_at = kst_now()
  ))
  append_csv_table_to_gpkg(metadata_csv, gpkg, "metadata")

  add_gpkg_spatial_index(gpkg, "links", "geom")
  add_gpkg_spatial_index(gpkg, "nodes", "geom")
  create_attribute_index(gpkg, "CREATE UNIQUE INDEX IF NOT EXISTS idx_links_link_id ON links(LINK_ID)")
  create_attribute_index(gpkg, "CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_node_id ON nodes(NODE_ID)")
  create_attribute_index(gpkg, "CREATE INDEX IF NOT EXISTS idx_links_f_node ON links(F_NODE)")
  create_attribute_index(gpkg, "CREATE INDEX IF NOT EXISTS idx_links_t_node ON links(T_NODE)")

  output_counts <- vapply(names(source_layers), function(x) layer_count(gpkg, x), numeric(1L))
  null_link_ids <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM links WHERE LINK_ID IS NULL OR trim(LINK_ID) = ''", "n"))
  null_node_ids <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM nodes WHERE NODE_ID IS NULL OR trim(NODE_ID) = ''", "n"))
  orphan_from <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM links l LEFT JOIN nodes n ON l.F_NODE=n.NODE_ID WHERE n.NODE_ID IS NULL", "n"))
  orphan_to <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM links l LEFT JOIN nodes n ON l.T_NODE=n.NODE_ID WHERE n.NODE_ID IS NULL", "n"))
  endpoint_qc <- NULL
  if (cli$mode == "production") {
    endpoint_sql <- paste0(
      "SELECT COUNT(*) AS n, MAX(MAX(ST_Distance(ST_StartPoint(l.geom),nf.geom),",
      "ST_Distance(ST_EndPoint(l.geom),nt.geom))) AS max_error FROM links l ",
      "JOIN nodes nf ON l.F_NODE=nf.NODE_ID JOIN nodes nt ON l.T_NODE=nt.NODE_ID"
    )
    endpoint_qc <- list(
      compared_links = as.numeric(ogr_scalar(gpkg, endpoint_sql, "n")),
      max_error = as.numeric(ogr_scalar(gpkg, endpoint_sql, "max_error"))
    )
  }
  if (cli$mode == "production" && null_link_ids + null_node_ids + orphan_from + orphan_to != 0) {
    stop(sprintf("Road integrity failure null_link=%d null_node=%d orphan_from=%d orphan_to=%d",
                 null_link_ids, null_node_ids, orphan_from, orphan_to), call. = FALSE)
  }
  if (cli$mode == "production") {
    if (!identical(as.numeric(output_counts), as.numeric(expected))) stop("Road output count mismatch", call. = FALSE)
    if (!is.finite(endpoint_qc$max_error) || endpoint_qc$max_error > cfg$road$endpoint_tolerance_m) {
      stop("Road endpoint/source-node coordinate tolerance failure: ", endpoint_qc$max_error, call. = FALSE)
    }
  }
  if (!sqlite_integrity(gpkg)) stop("Road GeoPackage integrity check failed", call. = FALSE)
  if (file.exists(paste0(gpkg, "-wal")) || file.exists(paste0(gpkg, "-shm"))) stop("Road GPKG has WAL/SHM sidecar", call. = FALSE)

  qc <- list(source_counts = as.list(counts), output_counts = as.list(output_counts),
             null_link_ids = null_link_ids, null_node_ids = null_node_ids,
             orphan_from = orphan_from, orphan_to = orphan_to, endpoint = endpoint_qc,
             source_crs_preserved = TRUE)
  write_json_atomic(qc, file.path(stage_dir, "road_qc.json"))
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  details <- list(mode = cli$mode, staging_path = gpkg, elapsed_sec = elapsed, workers = 1L, qc = qc)
  if (cli$mode == "production") {
    final <- output_path(cfg, key)
    atomic_publish(gpkg, final)
    details$final_path <- final
    details$final_size <- unname(file.info(final)$size)
    details$final_sha256 <- sha256_file(final)
    write_marker(cfg, key, "production_complete", details)
  }
  write_dataset_result(cfg, key, "PASS", details)
  log_line(sprintf("ROAD_COMPLETE mode=%s links=%d nodes=%d elapsed_sec=%.3f",
                   cli$mode, output_counts[["links"]], output_counts[["nodes"]], elapsed))
})
