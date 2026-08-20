#!/usr/bin/env Rscript

source(file.path(Sys.getenv("FUSE_REPO", "/members/dhnyu/fuse"), "R", "preprocessing_utils.R"))
suppressPackageStartupMessages({
  library(sf)
  library(readxl)
  library(future)
  library(future.apply)
})
set_single_thread_env()
cli <- parse_cli()
cfg <- load_preprocessing_config(cli$config)
ensure_preprocessing_dirs(cfg)
assert_free_space(cfg)
key <- "poi"

extract_entry_atomic <- function(zip, entry, destination) {
  if (file.exists(destination)) return(destination)
  dir.create(dirname(destination), recursive = TRUE, showWarnings = FALSE)
  tmp <- paste0(destination, ".tmp.", Sys.getpid())
  con_in <- unz(zip, entry, open = "rb")
  con_out <- file(tmp, open = "wb")
  on.exit({ try(close(con_in), silent = TRUE); try(close(con_out), silent = TRUE) }, add = TRUE)
  repeat {
    bytes <- readBin(con_in, what = "raw", n = 16L * 1024L * 1024L)
    if (!length(bytes)) break
    writeBin(bytes, con_out)
  }
  close(con_in); close(con_out)
  if (!file.rename(tmp, destination)) stop("Could not publish extracted archive: ", destination, call. = FALSE)
  destination
}

read_codebook <- function(path) {
  raw <- readxl::read_excel(path, col_names = FALSE, na = character())
  headers <- make.unique(as.character(unlist(raw[2L, ], use.names = FALSE)))
  x <- as.data.table(raw[-c(1L, 2L), ])
  setnames(x, headers)
  setnames(x, names(x)[16L], "POI_CL_DC")
  x[, POI_CL_DC := trimws(as.character(POI_CL_DC))]
  x[]
}

value_state <- function(x) {
  y <- trimws(as.character(x))
  fifelse(is.na(x), "NULL",
          fifelse(y == "", "EMPTY",
                  fifelse(toupper(y) == "NA", "SOURCE_NA",
                          fifelse(y == "-", "TERMINAL_DASH", "VALUE"))))
}

prepare_region <- function(region_zip, shared_dir, parts_dir, ledger_dir, codebook, smoke_limit = NULL) {
  set_single_thread_env()
  region <- sub("_POI\\.zip$", "", basename(region_zip), ignore.case = TRUE)
  extracted <- file.path(shared_dir, "regions", sub("\\.zip$", "", basename(region_zip), ignore.case = TRUE))
  marker <- file.path(extracted, ".extract_complete")
  if (!file.exists(marker)) {
    dir.create(extracted, recursive = TRUE, showWarnings = FALSE)
    run_cmd("unzip", c("-q", "-o", region_zip, "-d", extracted))
    writeLines(kst_now(), marker)
  }
  shp <- list.files(extracted, pattern = "^TN_POI_.*\\.shp$", recursive = TRUE, full.names = TRUE)
  address <- list.files(extracted, pattern = "^TN_ADRES_.*\\.csv$", recursive = TRUE, full.names = TRUE)
  foreign <- list.files(extracted, pattern = "^TN_FRGN_.*\\.csv$", recursive = TRUE, full.names = TRUE)
  alias <- list.files(extracted, pattern = "^TN_ALIAS_.*\\.csv$", recursive = TRUE, full.names = TRUE)
  if (length(shp) != 1L || length(address) != 1L || length(foreign) != 1L || length(alias) != 1L) {
    stop("Unexpected POI regional payload for ", region, call. = FALSE)
  }
  out <- file.path(parts_dir, paste0(region, ".fgb"))
  ledger <- file.path(ledger_dir, paste0(region, "_exclusions.csv"))
  done <- paste0(out, ".done.json")
  if (file.exists(out) && file.exists(ledger) && file.exists(done)) {
    d <- read_json(done, simplifyVector = TRUE)
    return(data.table(region = region, points = out, address = address, foreign = foreign, alias = alias,
                      source_count = d$source_count, valid_count = d$valid_count, excluded_count = d$excluded_count))
  }

  query <- if (is.null(smoke_limit)) NULL else sprintf('SELECT * FROM "%s" LIMIT %d', tools::file_path_sans_ext(basename(shp)), smoke_limit)
  points <- if (is.null(query)) {
    sf::st_read(shp, quiet = TRUE, options = "ENCODING=CP949", stringsAsFactors = FALSE)
  } else {
    sf::st_read(shp, query = query, quiet = TRUE, options = "ENCODING=CP949", stringsAsFactors = FALSE)
  }
  source_count <- nrow(points)
  points$source_archive <- basename(source_path(cfg, key))
  points$source_region <- region
  points$source_layer <- tools::file_path_sans_ext(basename(shp))
  points$source_record_index <- seq.int(0L, nrow(points) - 1L)
  points$NF_ID <- trimws(as.character(points$NF_ID))
  points$POI_CL_DC <- trimws(as.character(points$POI_CL_DC))

  geom_type <- as.character(sf::st_geometry_type(points, by_geometry = TRUE))
  empty <- sf::st_is_empty(points)
  xy <- suppressWarnings(sf::st_coordinates(points))
  finite <- is.finite(xy[, 1L]) & is.finite(xy[, 2L])
  ll <- suppressWarnings(sf::st_coordinates(sf::st_transform(points, 4326)))
  in_range <- is.finite(ll[, 1L]) & is.finite(ll[, 2L]) &
    ll[, 1L] >= cfg$poi$valid_lon_min & ll[, 1L] <= cfg$poi$valid_lon_max &
    ll[, 2L] >= cfg$poi$valid_lat_min & ll[, 2L] <= cfg$poi$valid_lat_max
  duplicate_id <- duplicated(points$NF_ID) | duplicated(points$NF_ID, fromLast = TRUE)
  code_match <- points$POI_CL_DC %chin% codebook$POI_CL_DC
  reason <- fifelse(is.na(points$NF_ID) | points$NF_ID == "", "NULL_OR_EMPTY_ID",
                    fifelse(duplicate_id, "DUPLICATE_ID_WITHIN_REGION",
                            fifelse(geom_type != "POINT" | empty | !finite, "INVALID_POINT_GEOMETRY",
                                    fifelse(!in_range, "OUTSIDE_SOURCE_CRS_VALID_RANGE",
                                            fifelse(!code_match, "UNMAPPED_CODEBOOK_CODE", NA_character_)))))
  exclusions <- data.table(source_region = region, source_record_index = points$source_record_index,
                           NF_ID = points$NF_ID, POI_CL_DC = points$POI_CL_DC, reason_code = reason)[!is.na(reason)]
  fwrite(exclusions, ledger, bom = TRUE)
  points <- points[is.na(reason), ]

  hierarchy <- copy(codebook)
  keep <- c("POI_CL_DC", headers <- names(hierarchy)[1:12])
  hierarchy <- hierarchy[, ..keep]
  setnames(hierarchy, headers,
           c("CLASS_L1_LABEL", "CLASS_L1_CODE", "CLASS_L2_LABEL", "CLASS_L2_CODE",
             "CLASS_L3_LABEL", "CLASS_L3_CODE", "CLASS_L4_LABEL", "CLASS_L4_CODE",
             "CLASS_L5_LABEL", "CLASS_L5_CODE", "CLASS_L6_LABEL", "CLASS_L6_CODE"))
  attrs <- as.data.table(sf::st_drop_geometry(points))
  attrs[, join_order__ := .I]
  attrs <- hierarchy[attrs, on = "POI_CL_DC"]
  setorder(attrs, join_order__)
  attrs[, join_order__ := NULL]
  for (level in 1:6) {
    label_col <- sprintf("CLASS_L%d_LABEL", level)
    attrs[, (sprintf("CLASS_L%d_STATE", level)) := value_state(get(label_col))]
  }
  enriched <- sf::st_sf(attrs, geom = sf::st_geometry(points), crs = sf::st_crs(points))
  if (file.exists(out)) unlink(out)
  sf::st_write(enriched, out, layer = "poi_part", driver = "FlatGeobuf", quiet = TRUE, append = FALSE)
  write_json_atomic(list(region = region, source_count = source_count, valid_count = nrow(enriched),
                         excluded_count = nrow(exclusions), timestamp = kst_now()), done)
  data.table(region = region, points = out, address = address, foreign = foreign, alias = alias,
             source_count = source_count, valid_count = nrow(enriched), excluded_count = nrow(exclusions))
}

append_auxiliary <- function(source_file, gpkg, target_layer, region, is_csv = FALSE) {
  layer <- tools::file_path_sans_ext(basename(source_file))
  sql <- sprintf('SELECT *, \'%s\' AS source_region, ROWID AS source_record_index FROM "%s"', region,
                 gsub('"', '""', layer, fixed = TRUE))
  args <- c("-update", if (file.exists(gpkg)) "-append" else NULL, gpkg, source_file,
            if (!is_csv) c("--config", "SHAPE_ENCODING", cfg$poi$source_encoding) else NULL,
            "-dialect", "SQLite", "-sql", sql, "-nln", target_layer, "-nlt", "NONE",
            "-lco", "ASPATIAL_VARIANT=GPKG_ATTRIBUTES")
  run_cmd("ogr2ogr", args)
}

with_failure_result(cfg, key, {
  started <- Sys.time()
  if (cli$mode == "production") assert_no_final_collision(cfg, key)
  outer <- source_path(cfg, key)
  shared <- file.path(dataset_stage_dir(cfg, key), "shared")
  dir.create(shared, recursive = TRUE, showWarnings = FALSE)
  central <- file.path(shared, "ngii_poi_shp_20260525.zip")
  extract_entry_atomic(outer, "POI_ngii/ngii_poi_shp(20260525).ZIP", central)
  run_cmd("unzip", c("-tq", central))
  codebook_path <- unzip(outer, files = "POI_ngii/POI_CL_DC_code.xlsx", exdir = shared, overwrite = TRUE)
  codebook <- read_codebook(codebook_path)
  if (nrow(codebook) != cfg$poi$expected_category_rows) stop("POI codebook row mismatch: ", nrow(codebook), call. = FALSE)

  regional_entries <- list_zip_entries(central, "(?i)_POI\\.zip$")
  if (length(regional_entries) != 17L) stop("Expected 17 POI region archives, found ", length(regional_entries), call. = FALSE)
  if (cli$mode == "smoke") regional_entries <- regional_entries[grepl("SEJONG", regional_entries)][1L]
  region_zip_dir <- file.path(shared, "region_zips")
  dir.create(region_zip_dir, recursive = TRUE, showWarnings = FALSE)
  region_zips <- vapply(regional_entries, function(entry) extract_entry_atomic(central, entry, file.path(region_zip_dir, basename(entry))), character(1L))

  run_tag <- if (cli$mode == "production") "production" else paste0("smoke_", run_id_now())
  stage_dir <- file.path(dataset_stage_dir(cfg, key), run_tag)
  parts_dir <- file.path(stage_dir, "parts")
  ledger_dir <- file.path(stage_dir, "ledgers")
  dir.create(parts_dir, recursive = TRUE, showWarnings = FALSE)
  dir.create(ledger_dir, recursive = TRUE, showWarnings = FALSE)
  workers <- if (cli$mode == "smoke") 1L else min(cfg$runtime$poi_workers, length(region_zips))
  future::plan(future::multisession, workers = workers)
  on.exit(future::plan(future::sequential), add = TRUE)
  rows <- future.apply::future_lapply(
    region_zips,
    function(z) prepare_region(z, shared, parts_dir, ledger_dir, codebook, if (cli$mode == "smoke") 5000L else NULL),
    future.seed = TRUE,
    future.packages = c("data.table", "sf", "jsonlite", "yaml")
  )
  future::plan(future::sequential)
  staged <- rbindlist(rows)
  fwrite(staged, file.path(stage_dir, "poi_staging_qc.csv"))
  if (cli$mode == "production" && sum(staged$source_count) != cfg$poi$expected_source_records) {
    stop("POI source count mismatch: ", sum(staged$source_count), call. = FALSE)
  }

  gpkg <- file.path(stage_dir, "korea_P.staging.gpkg")
  if (file.exists(gpkg)) stop("Refusing ambiguous existing POI staging file: ", gpkg, call. = FALSE)
  for (i in seq_len(nrow(staged))) {
    args <- c(if (i == 1L) c("-f", "GPKG") else c("-update", "-append"), gpkg, staged$points[[i]],
              "-nln", "points", "-nlt", "POINT", "-lco", "GEOMETRY_NAME=geom", "-lco", "SPATIAL_INDEX=NO")
    run_cmd("ogr2ogr", args)
  }
  for (i in seq_len(nrow(staged))) append_auxiliary(staged$address[[i]], gpkg, "addresses", staged$region[[i]], is_csv = TRUE)
  for (i in seq_len(nrow(staged))) append_auxiliary(staged$foreign[[i]], gpkg, "foreign_names", staged$region[[i]], is_csv = TRUE)
  for (i in seq_len(nrow(staged))) append_auxiliary(staged$alias[[i]], gpkg, "aliases", staged$region[[i]], is_csv = TRUE)

  lookup_csv <- file.path(stage_dir, "category_lookup.csv")
  fwrite(codebook, lookup_csv, bom = TRUE, na = "")
  append_csv_table_to_gpkg(lookup_csv, gpkg, "category_lookup")
  metadata_csv <- file.path(stage_dir, "metadata.csv")
  write_metadata_csv(metadata_csv, list(
    schema_version = cfg$schema_version, snapshot_id = cfg$snapshot_id,
    source_archive = basename(outer), source_sha256 = sha256_file(outer), source_crs = "EPSG:5179",
    existing_category_filter_applied = FALSE, fuzzy_deduplication_applied = FALSE,
    model_missing_token_applied = FALSE, codebook_rows = nrow(codebook), created_at = kst_now()
  ))
  append_csv_table_to_gpkg(metadata_csv, gpkg, "metadata")

  add_gpkg_spatial_index(gpkg, "points", "geom")
  create_attribute_index(gpkg, "CREATE UNIQUE INDEX IF NOT EXISTS idx_points_nf_id ON points(NF_ID)")
  create_attribute_index(gpkg, "CREATE INDEX IF NOT EXISTS idx_points_category ON points(POI_CL_DC)")
  output_count <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM points", "n"))
  unique_count <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(DISTINCT NF_ID) AS n FROM points", "n"))
  unmapped <- as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM points WHERE CLASS_L1_CODE IS NULL", "n"))
  if (output_count != unique_count) stop("Cross-region NF_ID duplication detected", call. = FALSE)
  if (unmapped != 0) stop("POI codebook join has unmatched accepted points: ", unmapped, call. = FALSE)
  if (cli$mode == "production" && output_count + sum(staged$excluded_count) != cfg$poi$expected_source_records) {
    stop("POI accepted/excluded count reconciliation failure", call. = FALSE)
  }
  if (!sqlite_integrity(gpkg)) stop("POI GeoPackage integrity check failed", call. = FALSE)
  if (file.exists(paste0(gpkg, "-wal")) || file.exists(paste0(gpkg, "-shm"))) stop("POI GPKG has WAL/SHM sidecar", call. = FALSE)

  ledgers <- list.files(ledger_dir, pattern = "_exclusions\\.csv$", full.names = TRUE)
  ledger <- rbindlist(lapply(ledgers, fread), fill = TRUE)
  fwrite(ledger, file.path(stage_dir, "poi_exclusion_ledger.csv"), bom = TRUE)
  qc <- list(source_records = sum(staged$source_count), output_records = output_count,
             excluded_records = nrow(ledger), codebook_rows = nrow(codebook), unmatched_accepted = unmapped,
             auxiliary_counts = list(
               addresses = as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM addresses", "n")),
               foreign_names = as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM foreign_names", "n")),
               aliases = as.numeric(ogr_scalar(gpkg, "SELECT COUNT(*) AS n FROM aliases", "n"))))
  write_json_atomic(qc, file.path(stage_dir, "poi_qc.json"))
  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  details <- list(mode = cli$mode, staging_path = gpkg, elapsed_sec = elapsed, workers = workers, qc = qc)
  if (cli$mode == "production") {
    final <- output_path(cfg, key)
    atomic_publish(gpkg, final)
    details$final_path <- final
    details$final_size <- unname(file.info(final)$size)
    details$final_sha256 <- sha256_file(final)
    write_marker(cfg, key, "production_complete", details)
  }
  write_dataset_result(cfg, key, "PASS", details)
  log_line(sprintf("POI_COMPLETE mode=%s records=%d excluded=%d elapsed_sec=%.3f", cli$mode, output_count, nrow(ledger), elapsed))
})
