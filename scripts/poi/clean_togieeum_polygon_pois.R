#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
  library(readxl)
  library(digest)
  library(parallel)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || all(is.na(x)) || identical(x, "")) y else x
}

timestamp <- function() format(Sys.time(), "%Y%m%d_%H%M%S")

parse_args <- function(args) {
  out <- list(
    raw_dir = path.expand(Sys.getenv("TOGIEEUM_RAW_DIR", "~/fusedatalarge/raw/togieeum")),
    out_dir = path.expand(Sys.getenv("TOGIEEUM_PROCESSED_DIR", "~/fusedatalarge/processed")),
    report_dir = path.expand(Sys.getenv("FUSE_REPORT_DIR", "~/fuse/reports")),
    work_dir = Sys.getenv("TOGIEEUM_WORK_DIR", unset = ""),
    workers = as.integer(Sys.getenv("TOGIEEUM_WORKERS", "40")),
    overwrite = FALSE,
    keep_work = identical(tolower(Sys.getenv("TOGIEEUM_KEEP_WORK", "false")), "true"),
    target_crs = as.integer(Sys.getenv("TOGIEEUM_TARGET_CRS", "5186")),
    assumed_raw_crs = as.integer(Sys.getenv("TOGIEEUM_ASSUMED_RAW_CRS", "5174")),
    source_encoding = Sys.getenv("TOGIEEUM_SOURCE_ENCODING", "CP949"),
    max_nested_group_size = as.integer(Sys.getenv("TOGIEEUM_MAX_NESTED_GROUP_SIZE", "50000")),
    nested_chunk_size = as.integer(Sys.getenv("TOGIEEUM_NESTED_CHUNK_SIZE", "5000"))
  )

  i <- 1L
  while (i <= length(args)) {
    arg <- args[[i]]
    if (arg == "--overwrite") out$overwrite <- TRUE
    if (arg == "--keep-work") out$keep_work <- TRUE
    if (arg == "--raw-dir" && i < length(args)) {
      i <- i + 1L
      out$raw_dir <- path.expand(args[[i]])
    }
    if (arg == "--out-dir" && i < length(args)) {
      i <- i + 1L
      out$out_dir <- path.expand(args[[i]])
    }
    if (arg == "--report-dir" && i < length(args)) {
      i <- i + 1L
      out$report_dir <- path.expand(args[[i]])
    }
    if (arg == "--work-dir" && i < length(args)) {
      i <- i + 1L
      out$work_dir <- path.expand(args[[i]])
      out$keep_work <- TRUE
    }
    if (arg == "--workers" && i < length(args)) {
      i <- i + 1L
      out$workers <- as.integer(args[[i]])
    }
    i <- i + 1L
  }
  out$workers <- max(1L, min(40L, out$workers, parallel::detectCores(logical = TRUE)))
  if (!nzchar(out$work_dir)) {
    out$work_dir <- file.path(tempdir(), paste0("fuse_togieeum_polygon_poi_", timestamp()))
  }
  out
}

cfg <- parse_args(commandArgs(trailingOnly = TRUE))

dir.create(cfg$out_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(cfg$report_dir, recursive = TRUE, showWarnings = FALSE)
dir.create(cfg$work_dir, recursive = TRUE, showWarnings = FALSE)

run_stamp <- format(Sys.time(), "%Y%m%d_%H%M")
paths <- list(
  gpkg = file.path(cfg$out_dir, "korea_polygon_poi_togieeum.gpkg"),
  attributes = file.path(cfg$out_dir, "korea_polygon_poi_togieeum_attributes.parquet"),
  summary = file.path(cfg$out_dir, "korea_polygon_poi_togieeum_summary.parquet"),
  report = file.path(cfg$report_dir, paste0(run_stamp, "_togieeum_polygon_poi_cleaning_report.md")),
  log = file.path(cfg$out_dir, "korea_polygon_poi_togieeum_cleaning.log")
)

log_con <- file(paths$log, open = "at", encoding = "UTF-8")
on.exit(close(log_con), add = TRUE)

log_msg <- function(...) {
  msg <- sprintf("[%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), paste(..., collapse = " "))
  cat(msg, "\n")
  writeLines(msg, log_con, useBytes = TRUE)
  flush(log_con)
}

stop_if_outputs_exist <- function(paths, overwrite = FALSE) {
  existing <- unlist(paths[c("gpkg", "attributes", "summary", "report")], use.names = FALSE)
  existing <- existing[file.exists(existing)]
  if (!length(existing)) return(invisible(TRUE))
  if (!overwrite) {
    stop(
      "Output file(s) already exist. Re-run with --overwrite to replace only these target outputs:\n",
      paste(existing, collapse = "\n"),
      call. = FALSE
    )
  }
  for (path in existing) {
    if (file.exists(path)) unlink(path, recursive = FALSE, force = TRUE)
    for (sidecar in paste0(path, c("-wal", "-shm"))) {
      if (file.exists(sidecar)) unlink(sidecar, force = TRUE)
    }
  }
}

target_layers <- data.table(
  source_layer_code = c("152", "153", "155", "157"),
  major_category = c(
    "transportation_facility",
    "spatial_facility",
    "public_cultural_sports_facility",
    "health_sanitation_facility"
  ),
  major_category_ko = c("교통시설", "공간시설", "공공문화체육시설", "보건위생시설")
)

excluded_layers <- data.table(
  source_layer_code = c("151", "154", "156", "158", "159"),
  excluded_label_ko = c("도로", "유통공급시설", "방재시설", "환경기초시설", "기타기반시설")
)

clean_string <- function(x) {
  if (is.null(x)) return(NA_character_)
  x <- as.character(x)
  x <- trimws(x)
  x[x == ""] <- NA_character_
  x
}

coalesce_chr <- function(...) {
  xs <- list(...)
  out <- rep(NA_character_, length(xs[[1]]))
  for (x in xs) {
    x <- clean_string(x)
    hit <- is.na(out) & !is.na(x)
    out[hit] <- x[hit]
  }
  out
}

safe_read_excel <- function(path, sheet) {
  tryCatch(
    as.data.table(readxl::read_excel(path, sheet = sheet, col_names = FALSE)),
    error = function(e) data.table()
  )
}

read_workbook_evidence <- function(raw_dir) {
  files <- list.files(raw_dir, pattern = "[.](xlsx|xls)$", full.names = TRUE)
  rows <- list()
  definitions <- list()
  for (file in files) {
    sheets <- tryCatch(readxl::excel_sheets(file), error = function(e) character())
    for (sheet in sheets) {
      x <- safe_read_excel(file, sheet)
      if (!nrow(x)) next
      txt <- apply(x, 1, function(r) paste(clean_string(r), collapse = " | "))
      hit <- grepl("UQ15[123456789]|도시.*시설|도형.*분류|도형속성|CLASSIFY|LCLAS|MLSFC|SCLAS|ATRB", txt, ignore.case = TRUE)
      if (any(hit)) {
        rows[[length(rows) + 1L]] <- data.table(
          workbook = basename(file),
          sheet = sheet,
          evidence_row = which(hit),
          evidence_text = txt[hit]
        )
      }
      if (grepl("정의|설계", sheet)) {
        y <- copy(x)
        y[, workbook := basename(file)]
        y[, sheet := sheet]
        definitions[[length(definitions) + 1L]] <- y
      }
    }
  }
  list(
    evidence = rbindlist(rows, fill = TRUE),
    definitions = rbindlist(definitions, fill = TRUE)
  )
}

list_zip_members <- function(zip_path) {
  inv <- as.data.table(utils::unzip(zip_path, list = TRUE))
  inv[, source_zip := basename(zip_path)]
  inv[, source_path := zip_path]
  inv[, archive_member := Name]
  inv[, extension := tolower(tools::file_ext(Name))]
  inv[, layer_name := tools::file_path_sans_ext(basename(Name))]
  inv[, source_system := sub("_.*$", "", source_zip)]
  inv[, region_code := sub(".*_([0-9]{5})[.]zip$", "\\1", source_zip)]
  inv[, source_layer_code := sub(".*UQ([0-9]{3}).*$", "\\1", layer_name)]
  inv[source_layer_code == layer_name, source_layer_code := NA_character_]
  inv[]
}

unzip_archives <- function(zip_files, work_dir) {
  rows <- vector("list", length(zip_files))
  for (i in seq_along(zip_files)) {
    zip_path <- zip_files[[i]]
    zip_name <- tools::file_path_sans_ext(basename(zip_path))
    extract_dir <- file.path(work_dir, zip_name)
    dir.create(extract_dir, recursive = TRUE, showWarnings = FALSE)
    log_msg("Unzipping", basename(zip_path), "to", extract_dir)
    utils::unzip(zip_path, exdir = extract_dir)
    inv <- list_zip_members(zip_path)
    inv[, extract_dir := extract_dir]
    inv[, extracted_path := file.path(extract_dir, archive_member)]
    rows[[i]] <- inv
  }
  rbindlist(rows, fill = TRUE)
}

read_layer_schema <- function(shp_path) {
  layer <- tools::file_path_sans_ext(basename(shp_path))
  info <- try(system2("ogrinfo", c("-ro", "-so", shQuote(shp_path), layer), stdout = TRUE, stderr = TRUE), silent = TRUE)
  if (inherits(info, "try-error")) {
    return(list(geometry_type = NA_character_, crs_epsg = NA_integer_, fields = NA_character_))
  }
  geom_line <- info[grepl("^Geometry:", info)]
  geometry_type <- if (length(geom_line)) trimws(sub("^Geometry:[[:space:]]*", "", geom_line[[1]])) else NA_character_
  epsg_matches <- regmatches(info, gregexpr('ID\\["EPSG",[0-9]+\\]', info, perl = TRUE))
  epsg_values <- unique(as.integer(gsub("[^0-9]", "", unlist(epsg_matches))))
  crs_epsg <- if (5174L %in% epsg_values) 5174L else if (length(epsg_values)) tail(epsg_values, 1L) else NA_integer_
  fields <- info[grepl("^[A-Za-z_][A-Za-z0-9_]*:[[:space:]]", info)]
  fields <- fields[!grepl("^(INFO|Layer name|Geometry|Feature Count|Extent|FID Column|Geometry Column|Data axis)", fields)]
  fields <- sub(":.*$", "", fields)
  list(geometry_type = geometry_type, crs_epsg = crs_epsg, fields = paste(fields, collapse = "|"))
}

add_shx_feature_counts <- function(shp_inventory, full_inventory) {
  shx <- full_inventory[extension == "shx", .(
    source_zip,
    shx_layer_name = layer_name,
    shx_feature_count = as.integer((Length - 100L) / 8L)
  )]
  out <- merge(
    shp_inventory,
    shx,
    by.x = c("source_zip", "layer_name"),
    by.y = c("source_zip", "shx_layer_name"),
    all.x = TRUE,
    sort = FALSE
  )
  out[]
}

read_cp949_csv <- function(path, select) {
  cmd <- sprintf("iconv -f CP949 -t UTF-8//IGNORE %s", shQuote(path))
  fread(cmd = cmd, select = select, fill = TRUE, showProgress = FALSE)
}

mode_label <- function(x) {
  x <- clean_string(x)
  x <- x[!is.na(x)]
  if (!length(x)) return(NA_character_)
  tab <- sort(table(x), decreasing = TRUE)
  names(tab)[[1]]
}

build_code_maps <- function(raw_dir) {
  maps <- list()
  tn_path <- file.path(raw_dir, "TN_UBPLFC_WTNNC.csv")
  kp_path <- file.path(raw_dir, "KP_CTPL_FCLT_DSWE.csv")

  if (file.exists(tn_path)) {
    log_msg("Reading UPIS decision-record code evidence:", tn_path)
    tn <- read_cp949_csv(
      tn_path,
      c("RECORD_CODE", "CLASSIFY_G", "CLASSIFY_M", "CLASSIFY_L", "CLASSIFY_L_NAME", "ZONE_NAME", "LOCATION_NAME")
    )
    setnames(tn, tolower(names(tn)))
    tn_code <- rbindlist(list(
      tn[, .(code = classify_g, label_ko = NA_character_, code_level = "large", source_table = "TN_UBPLFC_WTNNC")],
      tn[, .(code = classify_m, label_ko = NA_character_, code_level = "middle", source_table = "TN_UBPLFC_WTNNC")],
      tn[, .(code = classify_l, label_ko = classify_l_name, code_level = "small", source_table = "TN_UBPLFC_WTNNC")]
    ), fill = TRUE)
    maps[["tn_code"]] <- tn_code
    maps[["tn_record"]] <- tn[, .(
      decision_record_code = record_code,
      decision_lclas_code = classify_g,
      decision_mlsfc_code = classify_m,
      decision_sclas_code = classify_l,
      decision_sclas_label_ko = classify_l_name,
      decision_zone_name_ko = zone_name,
      decision_location_name_ko = location_name,
      decision_source_table = "TN_UBPLFC_WTNNC"
    )]
  }

  if (file.exists(kp_path)) {
    log_msg("Reading KLIP decision-record code evidence:", kp_path)
    kp <- read_cp949_csv(
      kp_path,
      c("wevd_cd", "lcls_cd", "mcls_cd", "scls_cd", "scls_nm", "area_nm", "lc_nm")
    )
    setnames(kp, tolower(names(kp)))
    kp_code <- rbindlist(list(
      kp[, .(code = lcls_cd, label_ko = NA_character_, code_level = "large", source_table = "KP_CTPL_FCLT_DSWE")],
      kp[, .(code = mcls_cd, label_ko = NA_character_, code_level = "middle", source_table = "KP_CTPL_FCLT_DSWE")],
      kp[, .(code = scls_cd, label_ko = scls_nm, code_level = "small", source_table = "KP_CTPL_FCLT_DSWE")]
    ), fill = TRUE)
    maps[["kp_code"]] <- kp_code
    maps[["kp_record"]] <- kp[, .(
      decision_record_code = wevd_cd,
      decision_lclas_code = lcls_cd,
      decision_mlsfc_code = mcls_cd,
      decision_sclas_code = scls_cd,
      decision_sclas_label_ko = scls_nm,
      decision_zone_name_ko = area_nm,
      decision_location_name_ko = lc_nm,
      decision_source_table = "KP_CTPL_FCLT_DSWE"
    )]
  }

  code_map <- rbindlist(maps[grep("_code$", names(maps))], fill = TRUE)
  if (nrow(code_map)) {
    code_map[, code := clean_string(code)]
    code_map[, label_ko := clean_string(label_ko)]
    code_map <- code_map[!is.na(code)]
    code_map <- code_map[, .(
      decoded_type_label_ko = mode_label(label_ko),
      decoded_label_variant_count = uniqueN(na.omit(label_ko)),
      decoded_label_source_tables = paste(sort(unique(source_table)), collapse = "|")
    ), by = code]
  }

  record_map <- rbindlist(maps[grep("_record$", names(maps))], fill = TRUE)
  if (nrow(record_map)) {
    record_map[, decision_record_code := clean_string(decision_record_code)]
    record_map <- unique(record_map[!is.na(decision_record_code)], by = "decision_record_code")
  }

  list(code_map = code_map, record_map = record_map)
}

safe_make_valid <- function(x) {
  if (requireNamespace("lwgeom", quietly = TRUE)) {
    out <- try(lwgeom::st_make_valid(x), silent = TRUE)
    if (!inherits(out, "try-error")) return(out)
  }
  out <- try(sf::st_make_valid(x), silent = TRUE)
  if (!inherits(out, "try-error")) return(out)
  sf::st_buffer(x, 0)
}

read_target_layer <- function(row, source_encoding, target_crs, assumed_raw_crs) {
  source_shp <- row$extracted_path
  log_msg("Reading target layer", basename(source_shp), "from", row$source_zip)
  x <- sf::st_read(source_shp, options = paste0("ENCODING=", source_encoding), quiet = TRUE, stringsAsFactors = FALSE)
  input_n <- nrow(x)
  original_crs <- sf::st_crs(x)
  if (is.na(original_crs)) {
    sf::st_crs(x) <- assumed_raw_crs
    original_crs <- sf::st_crs(x)
  }
  original_valid <- sf::st_is_valid(x)
  original_valid[is.na(original_valid)] <- FALSE
  original_empty <- sf::st_is_empty(x)
  original_geom_type <- as.character(sf::st_geometry_type(x, by_geometry = TRUE))

  names(x) <- tolower(names(x))
  if (!"geometry" %in% names(x)) names(x)[attr(x, "sf_column")] <- "geometry"
  x$source_feature_index <- seq_len(input_n)
  x$source_zip <- row$source_zip
  x$source_shp <- basename(source_shp)
  x$source_system <- row$source_system
  x$source_layer_code <- row$source_layer_code
  x$source_layer_label <- target_layers[source_layer_code == row$source_layer_code, major_category_ko]
  x$major_category <- target_layers[source_layer_code == row$source_layer_code, major_category]
  x$major_category_ko <- target_layers[source_layer_code == row$source_layer_code, major_category_ko]
  x$region_code <- row$region_code
  x$source_crs_epsg <- original_crs$epsg %||% NA_integer_
  x$source_crs_input <- original_crs$input %||% NA_character_
  x$source_geometry_type <- paste(sort(unique(original_geom_type)), collapse = "|")
  x$original_valid <- original_valid
  x$original_empty <- original_empty

  x <- sf::st_transform(x, target_crs)
  before_repair_wkb <- sf::st_as_binary(sf::st_geometry(x), EWKB = TRUE)
  before_repair_hash <- vapply(before_repair_wkb, digest, character(1), algo = "xxhash64", serialize = FALSE)
  x$pre_repair_geom_hash <- before_repair_hash

  x <- safe_make_valid(x)
  x <- suppressWarnings(sf::st_collection_extract(x, "POLYGON"))
  geom_type <- as.character(sf::st_geometry_type(x, by_geometry = TRUE))
  keep_polygon <- geom_type %chin% c("POLYGON", "MULTIPOLYGON")
  keep_nonempty <- !sf::st_is_empty(x)
  x <- x[keep_polygon & keep_nonempty, , drop = FALSE]
  if (!nrow(x)) return(x)

  x <- sf::st_cast(x, "MULTIPOLYGON", warn = FALSE)
  area_m2 <- as.numeric(sf::st_area(x))
  x$area_m2 <- area_m2
  x$zero_area <- !is.finite(area_m2) | area_m2 <= 0
  x <- x[!x$zero_area, , drop = FALSE]
  if (!nrow(x)) return(x)

  names(x) <- tolower(names(x))
  x
}

normalize_layer_attributes <- function(x) {
  dt <- as.data.table(sf::st_drop_geometry(x))
  for (nm in c("present_sn", "lclas_cl", "mlsfc_cl", "sclas_cl", "atrb_se", "wtnnc_sn", "ntfc_sn", "dgm_nm", "sgg_cd", "signgu_se")) {
    if (!nm %in% names(dt)) dt[, (nm) := NA_character_]
  }
  dt[, region_sgg_code := coalesce_chr(sgg_cd, signgu_se, region_code)]
  dt[, lclas_cl := clean_string(lclas_cl)]
  dt[, mlsfc_cl := clean_string(mlsfc_cl)]
  dt[, sclas_cl := clean_string(sclas_cl)]
  dt[, atrb_se := clean_string(atrb_se)]
  dt[, type_code := coalesce_chr(sclas_cl, atrb_se, mlsfc_cl, lclas_cl)]
  dt[, middle_type_code := coalesce_chr(mlsfc_cl, lclas_cl)]
  dt[, feature_label_ko := clean_string(dgm_nm)]
  dt
}

add_semantic_decoding <- function(dt, code_map, record_map) {
  if (nrow(code_map)) {
    setnames(code_map, "code", "type_code")
    dt <- code_map[dt, on = "type_code"]
    setnames(code_map, "type_code", "code")
  } else {
    dt[, `:=`(
      decoded_type_label_ko = NA_character_,
      decoded_label_variant_count = NA_integer_,
      decoded_label_source_tables = NA_character_
    )]
  }

  if (nrow(record_map)) {
    dt <- record_map[dt, on = c(decision_record_code = "wtnnc_sn")]
  } else {
    dt[, `:=`(
      decision_record_code = NA_character_,
      decision_lclas_code = NA_character_,
      decision_mlsfc_code = NA_character_,
      decision_sclas_code = NA_character_,
      decision_sclas_label_ko = NA_character_,
      decision_zone_name_ko = NA_character_,
      decision_location_name_ko = NA_character_,
      decision_source_table = NA_character_
    )]
  }

  dt[, semantic_type_label_ko := coalesce_chr(decoded_type_label_ko, decision_sclas_label_ko)]
  dt[, semantic_type_key := fifelse(!is.na(type_code), type_code, coalesce_chr(semantic_type_label_ko, feature_label_ko, "unknown"))]
  dt[, code_mapping_status := fifelse(
    !is.na(semantic_type_label_ko),
    "decoded_from_supporting_csv_code_or_record_map",
    "not_decoded_from_supporting_files"
  )]
  dt
}

hash_geometry <- function(geom) {
  vapply(sf::st_as_binary(geom, EWKB = TRUE), digest, character(1), algo = "xxhash64", serialize = FALSE)
}

make_polygon_ids <- function(dt, geom_hash) {
  seed <- paste(
    dt$source_system,
    dt$source_zip,
    dt$source_shp,
    dt$source_feature_index,
    coalesce_chr(dt$present_sn, ""),
    coalesce_chr(dt$wtnnc_sn, ""),
    coalesce_chr(dt$ntfc_sn, ""),
    geom_hash,
    sep = "|"
  )
  paste0("tpp_", vapply(seed, digest, character(1), algo = "xxhash64", serialize = FALSE))
}

remove_exact_and_near_duplicates <- function(attrs) {
  attrs[, exact_duplicate_removed := duplicated(paste(major_category, semantic_type_key, geom_hash, sep = "|"))]
  attrs[, near_duplicate_key := paste(
    major_category,
    semantic_type_key,
    round(area_m2, 1),
    round(xmin, 1), round(ymin, 1), round(xmax, 1), round(ymax, 1),
    sep = "|"
  )]
  attrs[, near_duplicate_removed := FALSE]
  remaining <- !attrs$exact_duplicate_removed
  attrs[remaining, near_duplicate_removed := duplicated(near_duplicate_key)]
  attrs[]
}

find_nested_indices_one_group <- function(indices, geom, area, max_group_size, chunk_size) {
  n <- length(indices)
  if (n <= 1L) return(integer())
  g <- geom[indices]
  a <- area[indices]
  remove_local <- logical(n)
  starts <- seq.int(1L, n, by = chunk_size)
  for (start in starts) {
    end <- min(n, start + chunk_size - 1L)
    rel <- start:end
    within <- sf::st_within(g[rel], g, sparse = TRUE)
    for (k in seq_along(within)) {
      i_local <- rel[[k]]
      cand <- within[[k]]
      cand <- cand[cand != i_local]
      if (!length(cand)) next
      larger <- cand[a[cand] > (a[[i_local]] + 1e-6)]
      if (length(larger)) remove_local[[i_local]] <- TRUE
    }
  }
  indices[remove_local]
}

remove_nested_polygons <- function(attrs, geom, workers, max_group_size, chunk_size) {
  candidates <- attrs[!exact_duplicate_removed & !near_duplicate_removed, .(row_id, group_key = paste(major_category, semantic_type_key, sep = "|"))]
  groups <- split(candidates$row_id, candidates$group_key)
  groups <- groups[lengths(groups) > 1L]
  if (!length(groups)) return(integer())
  log_msg("Running nested-polygon removal on", length(groups), "same-category/type groups with", workers, "workers")
  worker_fun <- function(idx) {
    suppressPackageStartupMessages(library(sf))
    find_nested_indices_one_group(idx, geom, attrs$area_m2, max_group_size, chunk_size)
  }
  if (.Platform$OS.type == "unix" && workers > 1L) {
    rows <- parallel::mclapply(groups, worker_fun, mc.cores = min(workers, length(groups)))
  } else {
    rows <- lapply(groups, worker_fun)
  }
  unique(unlist(rows, use.names = FALSE))
}

summarise_stage <- function(attrs, stage_col, count_name, area_name) {
  attrs[, .(
    value_count = .N,
    value_area = sum(area_m2, na.rm = TRUE)
  ), by = .(major_category, major_category_ko, semantic_type_key, semantic_type_label_ko, source_shp, region_sgg_code, get(stage_col))][
    , .(
      value_count = sum(value_count),
      value_area = sum(value_area)
    ),
    by = .(major_category, major_category_ko, semantic_type_key, semantic_type_label_ko, source_shp, region_sgg_code)
  ][
    , `:=`(metric_count_name = count_name, metric_area_name = area_name)
  ]
}

write_report <- function(
  paths, cfg, zip_files, inventory, target_inventory, excluded_inventory,
  schema_summary, workbook_evidence, attrs_all, attrs_after_geom, attrs_final,
  code_map, mapping_success, start_time, nested_scope_note, raw_target_feature_count
) {
  category_summary <- attrs_final[, .(
    feature_count = .N,
    total_area_m2 = sum(area_m2, na.rm = TRUE)
  ), by = .(major_category, major_category_ko)][order(major_category)]

  mapping_summary <- attrs_after_geom[, .(
    features = .N,
    decoded_features = sum(code_mapping_status == "decoded_from_supporting_csv_code_or_record_map", na.rm = TRUE),
    undecoded_features = sum(code_mapping_status != "decoded_from_supporting_csv_code_or_record_map", na.rm = TRUE)
  ), by = .(major_category, major_category_ko)][order(major_category)]

  schema_lines <- if (nrow(schema_summary)) {
    capture.output(print(schema_summary))
  } else {
    "No schema rows available."
  }
  category_lines <- capture.output(print(category_summary))
  mapping_lines <- capture.output(print(mapping_summary))

  evidence_files <- c(
    "24-1010_토지이음개방용 KLIP 테이블 목록 및 정의서.xlsx",
    "데이터베이스설계서_UPIS8_20220512(NS).xlsx",
    "컬럼정의서(NS).xls",
    "KP_CTPL_FCLT_DSWE.csv",
    "TN_UBPLFC_WTNNC.csv",
    "KP_OPTN_PLAN_CNFM.csv"
  )

  lines <- c(
    "# Togieeum Polygon POI Cleaning Report",
    "",
    sprintf("Generated: `%s`", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
    sprintf("Script: `%s`", normalizePath(sys.frame(1)$ofile %||% "scripts/poi/clean_togieeum_polygon_pois.R", mustWork = FALSE)),
    "",
    "## Objective",
    "",
    "Rebuild a reliable nationwide polygon POI dataset from raw Togieeum ZIP archives without relying on the previous simple-merge outputs.",
    "",
    "## Inputs",
    "",
    sprintf("- Raw directory: `%s`", cfg$raw_dir),
    sprintf("- Output directory: `%s`", cfg$out_dir),
    sprintf("- Working directory: `%s`", cfg$work_dir),
    sprintf("- Workers requested/used: `%s`", cfg$workers),
    "",
    "## Source Exploration",
    "",
    sprintf("- ZIP files found: `%s`", length(zip_files)),
    sprintf("- Shapefiles extracted/identified: `%s`", inventory[extension == "shp", .N]),
    sprintf("- Target 152/153/155/157 shapefiles used: `%s`", nrow(target_inventory)),
    sprintf("- Excluded 151/154/156/158/159 shapefiles identified: `%s`", nrow(excluded_inventory)),
    sprintf("- Raw target source-feature count from SHX indexes: `%s`", raw_target_feature_count),
    sprintf("- Character encoding used for shapefiles: `%s`", cfg$source_encoding),
    "- Source CRS observed in target shapefiles: EPSG:5174, Korean 1985 / Modified Central Belt.",
    sprintf("- Final CRS: EPSG:%s. Project policy in `AGENTS.md` prefers EPSG:5186, so EPSG:5186 was used rather than EPSG:5179.", cfg$target_crs),
    "",
    "Supporting schema/code files checked:",
    paste0("- `", evidence_files, "`"),
    "",
    "## Target Layer Policy",
    "",
    "| Layer | Included | Major category | Korean label |",
    "|---|---:|---|---|",
    "| 152 | yes | transportation_facility | 교통시설 |",
    "| 153 | yes | spatial_facility | 공간시설 |",
    "| 155 | yes | public_cultural_sports_facility | 공공문화체육시설 |",
    "| 157 | yes | health_sanitation_facility | 보건위생시설 |",
    "| 151 | no | road | 도로 |",
    "| 154 | no | distribution_supply_facility | 유통공급시설 |",
    "| 156 | no | disaster_prevention_facility | 방재시설 |",
    "| 158 | no | environmental_infrastructure_facility | 환경기초시설 |",
    "| 159 | no | other_infrastructure_facility | 기타기반시설 |",
    "",
    "## Schema Findings",
    "",
    "```text",
    schema_lines,
    "```",
    "",
    "Important fields retained include `PRESENT_SN`, `LCLAS_CL`, `MLSFC_CL`, `SCLAS_CL`, `ATRB_SE`, `WTNNC_SN`, `NTFC_SN`, `DGM_NM`, `SGG_CD` / `SIGNGU_SE`, source ZIP, source shapefile, layer code, and source feature index.",
    "",
    "## Code Decoding",
    "",
    sprintf("- Code-to-label mapping succeeded: `%s`", mapping_success),
    sprintf("- Code map rows built from supporting CSVs: `%s`", nrow(code_map)),
    "",
    "The pipeline first derives `type_code` from the most detailed available code, preferring `SCLAS_CL`, then `ATRB_SE`, then `MLSFC_CL`, then `LCLAS_CL`. Korean type labels are decoded from `TN_UBPLFC_WTNNC.csv` and `KP_CTPL_FCLT_DSWE.csv` where possible. Feature-level labels from `DGM_NM` are preserved separately as `feature_label_ko` because they often name a particular facility rather than a reusable type.",
    "",
    "```text",
    mapping_lines,
    "```",
    "",
    "## Cleaning Counts",
    "",
    sprintf("- Raw target source-feature count from SHX indexes: `%s`", raw_target_feature_count),
    sprintf("- Feature count after geometry cleaning: `%s`", nrow(attrs_after_geom)),
    sprintf("- Net feature-count change during geometry repair/extraction: `%s`", nrow(attrs_after_geom) - raw_target_feature_count),
    sprintf("- Feature count after duplicate/nested removal: `%s`", nrow(attrs_final)),
    sprintf("- Exact duplicate features removed: `%s`", attrs_after_geom[exact_duplicate_removed == TRUE, .N]),
    sprintf("- Near-identical duplicate features removed: `%s`", attrs_after_geom[near_duplicate_removed == TRUE, .N]),
    sprintf("- Nested contained features removed: `%s`", attrs_after_geom[nested_removed == TRUE, .N]),
    sprintf("- Nested-polygon approach: `%s`", nested_scope_note),
    "",
    "Near-identical duplicate removal is deliberately conservative: it removes features with the same major category, same type key, near-identical area rounded to 0.1 square meters, and near-identical bounding box rounded to 0.1 meters.",
    "",
    "## Final Feature Count And Area By Major Category",
    "",
    "```text",
    category_lines,
    "```",
    "",
    "## Outputs",
    "",
    sprintf("- Geometry GeoPackage: `%s`", paths$gpkg),
    sprintf("- Attribute Parquet: `%s`", paths$attributes),
    sprintf("- Summary Parquet: `%s`", paths$summary),
    sprintf("- Log: `%s`", paths$log),
    "",
    "QGIS inspection path:",
    "",
    sprintf("`%s`", paths$gpkg),
    "",
    "## Limitations",
    "",
    "- Code labels are decoded from decision-record CSV evidence where possible. The workbooks document field meanings and layer names, but they do not provide a complete standalone code dictionary for every UQ code.",
    "- Containment removal is restricted to features sharing the same major category and same derived type key. This avoids deleting legitimately nested facilities across different semantic classes.",
    "- The previous `korea_togieeum_polygon.*` outputs were not used as inputs.",
    "",
    sprintf("Runtime seconds: `%.2f`", as.numeric(difftime(Sys.time(), start_time, units = "secs")))
  )
  writeLines(lines, paths$report, useBytes = TRUE)
}

main <- function() {
  start_time <- Sys.time()
  stop_if_outputs_exist(paths, cfg$overwrite)

  log_msg("Starting Togieeum polygon POI cleaning")
  log_msg("Raw dir:", cfg$raw_dir)
  log_msg("Output dir:", cfg$out_dir)
  log_msg("Work dir:", cfg$work_dir)
  log_msg("Workers:", cfg$workers)

  zip_files <- sort(list.files(cfg$raw_dir, pattern = "[.]zip$", full.names = TRUE, ignore.case = TRUE))
  if (!length(zip_files)) stop("No zip files found under raw directory: ", cfg$raw_dir, call. = FALSE)

  workbook <- read_workbook_evidence(cfg$raw_dir)
  maps <- build_code_maps(cfg$raw_dir)
  mapping_success <- nrow(maps$code_map) > 0L

  inventory <- unzip_archives(zip_files, cfg$work_dir)
  shp_inventory <- inventory[extension == "shp"]
  if (!nrow(shp_inventory)) stop("No shapefiles found after extracting Togieeum ZIP archives.", call. = FALSE)

  schema_rows <- vector("list", nrow(shp_inventory))
  for (i in seq_len(nrow(shp_inventory))) {
    rs <- read_layer_schema(shp_inventory$extracted_path[[i]])
    schema_rows[[i]] <- data.table(
      source_zip = shp_inventory$source_zip[[i]],
      source_shp = basename(shp_inventory$extracted_path[[i]]),
      source_system = shp_inventory$source_system[[i]],
      region_code = shp_inventory$region_code[[i]],
      source_layer_code = shp_inventory$source_layer_code[[i]],
      geometry_type = rs$geometry_type,
      crs_epsg = rs$crs_epsg,
      key_attribute_fields = rs$fields
    )
  }
  schema_summary <- rbindlist(schema_rows, fill = TRUE)

  shp_inventory <- add_shx_feature_counts(shp_inventory, inventory)
  target_inventory <- shp_inventory[source_layer_code %chin% target_layers$source_layer_code]
  excluded_inventory <- shp_inventory[source_layer_code %chin% excluded_layers$source_layer_code]
  if (!nrow(target_inventory)) stop("No target UQ152/UQ153/UQ155/UQ157 shapefiles found.", call. = FALSE)
  raw_target_feature_count <- sum(target_inventory$shx_feature_count, na.rm = TRUE)

  log_msg("ZIP files:", length(zip_files))
  log_msg("Shapefiles:", nrow(shp_inventory))
  log_msg("Target shapefiles:", nrow(target_inventory))
  log_msg("Excluded shapefiles:", nrow(excluded_inventory))

  layer_rows <- vector("list", nrow(target_inventory))
  geom_rows <- vector("list", nrow(target_inventory))
  for (i in seq_len(nrow(target_inventory))) {
    x <- read_target_layer(target_inventory[i], cfg$source_encoding, cfg$target_crs, cfg$assumed_raw_crs)
    if (!nrow(x)) {
      layer_rows[[i]] <- data.table()
      geom_rows[[i]] <- sf::st_sfc(crs = cfg$target_crs)
      next
    }
    dt <- normalize_layer_attributes(x)
    layer_rows[[i]] <- dt
    geom_rows[[i]] <- sf::st_geometry(x)
  }

  attrs_all <- rbindlist(layer_rows, fill = TRUE)
  geoms <- do.call(c, geom_rows)
  sf::st_crs(geoms) <- cfg$target_crs
  if (!nrow(attrs_all)) stop("No target features remained after geometry repair and polygon filtering.", call. = FALSE)

  attrs_after_geom <- add_semantic_decoding(copy(attrs_all), maps$code_map, maps$record_map)
  attrs_after_geom[, row_id := seq_len(.N)]
  attrs_after_geom[, geom_hash := hash_geometry(geoms)]
  attrs_after_geom[, polygon_poi_id := make_polygon_ids(attrs_after_geom, geom_hash)]
  bbox <- sf::st_bbox(geoms)
  bboxes <- do.call(rbind, lapply(geoms, function(g) as.numeric(sf::st_bbox(g))))
  colnames(bboxes) <- c("xmin", "ymin", "xmax", "ymax")
  attrs_after_geom[, `:=`(
    xmin = bboxes[, "xmin"],
    ymin = bboxes[, "ymin"],
    xmax = bboxes[, "xmax"],
    ymax = bboxes[, "ymax"]
  )]
  rm(bbox, bboxes)

  attrs_after_geom <- remove_exact_and_near_duplicates(attrs_after_geom)
  attrs_after_geom[, nested_removed := FALSE]
  nested_rows <- remove_nested_polygons(
    attrs_after_geom,
    geoms,
    workers = cfg$workers,
    max_group_size = cfg$max_nested_group_size,
    chunk_size = cfg$nested_chunk_size
  )
  if (length(nested_rows)) attrs_after_geom[row_id %in% nested_rows, nested_removed := TRUE]

  keep <- !attrs_after_geom$exact_duplicate_removed &
    !attrs_after_geom$near_duplicate_removed &
    !attrs_after_geom$nested_removed

  attrs_final <- copy(attrs_after_geom[keep])
  final_geoms <- geoms[keep]
  attrs_final[, `:=`(
    cleaned_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
    target_crs_epsg = cfg$target_crs,
    source_encoding = cfg$source_encoding
  )]

  summary_raw <- attrs_after_geom[, .(
    raw_feature_count = .N,
    raw_total_area_m2 = sum(area_m2, na.rm = TRUE)
  ), by = .(major_category, major_category_ko, semantic_type_key, semantic_type_label_ko, source_shp, region_sgg_code)]

  summary_final <- attrs_final[, .(
    cleaned_feature_count = .N,
    cleaned_total_area_m2 = sum(area_m2, na.rm = TRUE),
    exact_duplicate_removed = sum(exact_duplicate_removed, na.rm = TRUE),
    near_duplicate_removed = sum(near_duplicate_removed, na.rm = TRUE),
    nested_removed = sum(nested_removed, na.rm = TRUE)
  ), by = .(major_category, major_category_ko, semantic_type_key, semantic_type_label_ko, source_shp, region_sgg_code)]

  summary_dt <- merge(
    summary_raw,
    summary_final,
    by = c("major_category", "major_category_ko", "semantic_type_key", "semantic_type_label_ko", "source_shp", "region_sgg_code"),
    all = TRUE
  )
  for (nm in names(summary_dt)) {
    if (is.integer(summary_dt[[nm]]) || is.numeric(summary_dt[[nm]])) summary_dt[is.na(get(nm)), (nm) := 0]
  }

  attr_out <- copy(attrs_final)
  attr_out[, geometry := NULL]
  if ("near_duplicate_key" %in% names(attr_out)) attr_out[, near_duplicate_key := NULL]
  arrow::write_parquet(attr_out, paths$attributes)
  arrow::write_parquet(summary_dt, paths$summary)

  geom_out <- sf::st_sf(
    polygon_poi_id = attrs_final$polygon_poi_id,
    major_category = attrs_final$major_category,
    major_category_ko = attrs_final$major_category_ko,
    source_layer_code = attrs_final$source_layer_code,
    semantic_type_key = attrs_final$semantic_type_key,
    semantic_type_label_ko = attrs_final$semantic_type_label_ko,
    feature_label_ko = attrs_final$feature_label_ko,
    region_sgg_code = attrs_final$region_sgg_code,
    area_m2 = attrs_final$area_m2,
    geometry = final_geoms
  )
  sf::st_write(geom_out, paths$gpkg, layer = "polygon_pois", delete_dsn = TRUE, quiet = TRUE)

  nested_scope_note <- "full group-wise st_within checks by major category and semantic type key, chunked within large groups"

  write_report(
    paths = paths,
    cfg = cfg,
    zip_files = zip_files,
    inventory = inventory,
    target_inventory = target_inventory,
    excluded_inventory = excluded_inventory,
    schema_summary = unique(schema_summary[source_layer_code %chin% target_layers$source_layer_code, .(
      source_system, source_layer_code, geometry_type, crs_epsg, key_attribute_fields
    )]),
    workbook_evidence = workbook$evidence,
    attrs_all = attrs_all,
    attrs_after_geom = attrs_after_geom,
    attrs_final = attrs_final,
    code_map = maps$code_map,
    mapping_success = mapping_success,
    start_time = start_time,
    nested_scope_note = nested_scope_note,
    raw_target_feature_count = raw_target_feature_count
  )

  log_msg("Done.")
  log_msg("Output GeoPackage:", paths$gpkg)
  log_msg("Output attributes:", paths$attributes)
  log_msg("Output summary:", paths$summary)
  log_msg("Report:", paths$report)

  if (!cfg$keep_work) {
    log_msg("Removing working directory:", cfg$work_dir)
    unlink(cfg$work_dir, recursive = TRUE, force = TRUE)
  } else {
    log_msg("Keeping working directory:", cfg$work_dir)
  }
}

main()
