#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
  library(readxl)
  library(future)
  library(future.mirai)
  library(future.apply)
  library(dplyr)
  library(tibble)
  library(digest)
})

sf::sf_use_s2(FALSE)

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || is.na(x) || identical(x, "")) y else x
}

env_int <- function(name, default) {
  value <- Sys.getenv(name, unset = "")
  if (!nzchar(value)) return(default)
  as.integer(value)
}

env_flag <- function(name, default = FALSE) {
  value <- Sys.getenv(name, unset = if (default) "true" else "false")
  tolower(value) %in% c("1", "true", "t", "yes", "y")
}

insert_tag <- function(path, tag) {
  if (!nzchar(tag)) return(path)
  ext <- tools::file_ext(path)
  stem <- sub(paste0("\\.", ext, "$"), "", path)
  paste0(stem, "_", tag, ".", ext)
}

timestamp <- function() format(Sys.time(), "%Y%m%d_%H%M%S")

backup_existing <- function(path) {
  if (!file.exists(path)) return(NA_character_)
  backup <- paste0(path, ".bak_", timestamp())
  if (!file.rename(path, backup)) stop("Could not back up existing output: ", path)
  backup
}

raw_dir <- path.expand(Sys.getenv("NGII_POI_RAW_DIR", "~/fusedatalarge/POI_ngii"))
outer_shp_zip <- path.expand(Sys.getenv(
  "NGII_POI_SHP_ZIP",
  file.path(raw_dir, "ngii_poi_shp(20260525).ZIP")
))
output_tag <- Sys.getenv("NGII_POI_OUTPUT_TAG", unset = "")

out_gpkg <- insert_tag(
  path.expand(Sys.getenv(
    "NGII_POI_OUTPUT_GPKG",
    "~/fusedatalarge/processed/korea_poi_ngii_point.gpkg"
  )),
  output_tag
)
out_attr_parquet <- insert_tag(
  path.expand(Sys.getenv(
    "NGII_POI_ATTRIBUTE_PARQUET",
    "~/fusedatalarge/processed/korea_poi_ngii_attributes.parquet"
  )),
  output_tag
)
out_summary_parquet <- insert_tag(
  path.expand(Sys.getenv(
    "NGII_POI_SUMMARY_PARQUET",
    "~/fusedatalarge/processed/korea_poi_ngii_merge_summary.parquet"
  )),
  output_tag
)
out_log <- insert_tag(
  path.expand(Sys.getenv(
    "NGII_POI_LOG_FILE",
    "~/fusedatalarge/processed/korea_poi_ngii_merge.log"
  )),
  output_tag
)
out_design_note <- insert_tag(
  path.expand(Sys.getenv(
    "NGII_POI_STORAGE_DESIGN",
    "~/fusedatalarge/processed/korea_poi_ngii_storage_design.md"
  )),
  output_tag
)

target_epsg <- env_int("NGII_POI_TARGET_EPSG", 5186)
inner_zip_regex <- Sys.getenv("NGII_POI_INNER_ZIP_REGEX", unset = "_POI\\.zip$")
max_files <- env_int("NGII_POI_MAX_FILES", NA_integer_)
workers <- max(1L, env_int("NGII_POI_WORKERS", min(30L, parallelly::availableCores())))
gpkg_layer <- Sys.getenv("NGII_POI_GPKG_LAYER", unset = "points")
assume_5179_if_missing <- env_flag("NGII_POI_ASSUME_5179_IF_MISSING", FALSE)

for (dir_path in unique(dirname(c(out_gpkg, out_attr_parquet, out_summary_parquet, out_log, out_design_note)))) {
  dir.create(dir_path, recursive = TRUE, showWarnings = FALSE)
}

existing_before <- c(out_gpkg, out_attr_parquet, out_summary_parquet, out_log, out_design_note)
existing_before <- existing_before[file.exists(existing_before)]
log_backup <- backup_existing(out_log)

log_con <- file(out_log, open = "wt", encoding = "UTF-8")
on.exit(close(log_con), add = TRUE)

log_msg <- function(..., .sep = " ") {
  msg <- paste(..., sep = .sep)
  line <- sprintf("[%s] %s", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), msg)
  cat(line, "\n")
  writeLines(line, log_con)
  flush(log_con)
}

list_raw_files <- function(root) {
  files <- list.files(root, recursive = TRUE, full.names = TRUE, all.files = FALSE)
  tibble(
    path = files,
    name = basename(files),
    size_bytes = file.info(files)$size,
    extension = tolower(tools::file_ext(files)),
    is_archive = extension %in% c("zip"),
    is_spatial = extension %in% c("shp", "gpkg"),
    is_metadata = grepl("\\.(xlsx|xls|csv|txt|pdf)$", files, ignore.case = TRUE) |
      grepl("readme|metadata|codebook|attribute|속성|정의|설명", basename(files), ignore.case = TRUE)
  )
}

zip_inventory <- function(zip_path) {
  inv <- as_tibble(utils::unzip(zip_path, list = TRUE))
  converted <- iconv(inv$Name, from = "CP949", to = "UTF-8", sub = "byte")
  inv$Name <- ifelse(is.na(converted), enc2utf8(inv$Name), converted)
  inv |>
    mutate(
      zip_file = basename(zip_path),
      extension = tolower(tools::file_ext(Name)),
      is_zip = extension == "zip",
      is_shapefile = extension == "shp"
    )
}

read_classification_workbook <- function(xlsx) {
  sheets <- readxl::excel_sheets(xlsx)
  class_sheet <- sheets[grepl("분류체계|수정사항", sheets)][1]
  if (is.na(class_sheet)) return(tibble())

  raw <- readxl::read_excel(xlsx, sheet = class_sheet, col_names = FALSE)
  if (nrow(raw) < 2) return(tibble())

  raw <- as_tibble(raw[-1, , drop = FALSE])
  names(raw) <- paste0("v", seq_along(raw))
  raw |>
    transmute(
      metadata_file = basename(xlsx),
      lclasdc = as.character(.data$v1),
      lclasdc_cd = as.character(.data$v2),
      mlsfcdc = as.character(.data$v3),
      mlsfcdc_cd = as.character(.data$v4),
      sclasdc = as.character(.data$v5),
      sclasdc_cd = as.character(.data$v6),
      dclasdc = as.character(.data$v7),
      dclasdc_cd = as.character(.data$v8),
      dfclasdc = as.character(.data$v9),
      fclasfc_cd = as.character(.data$v10),
      dgclasdc = as.character(.data$v11),
      gclasdc_cd = as.character(.data$v12),
      asortcd = as.character(.data$v13),
      dsortcd = as.character(.data$v14),
      adsortcd = as.character(.data$v15),
      input_code = as.character(.data$v16)
    ) |>
    filter(!is.na(input_code), !is.na(asortcd))
}

read_metadata <- function(files) {
  xlsx_files <- files[grepl("\\.xlsx?$", files, ignore.case = TRUE)]
  classifications <- bind_rows(lapply(xlsx_files, function(x) {
    tryCatch(read_classification_workbook(x), error = function(e) tibble())
  }))

  table_fields <- tibble(
    metadata_file = "POI_database_readme.pdf",
    table_name = "TN_POI",
    table_label_ko = "점형 국가관심지점정보",
    field_name = c(
      "NF_ID", "POI_NM", "POI_CL_DC", "ORIGIN_SE", "REFRN_ID",
      "POI_REFRN", "POI_GEOSD", "MGMT_NM", "DACOL_DT", "OBCHG_DT", "MNENT_NM"
    ),
    field_label_ko = c(
      "고유식별자 아이디", "관심지점 명칭", "관심지점 분류 설명", "출처 구분", "참조 아이디",
      "자료 출처", "공간정보 출처", "관리 명칭", "자료수집 일시", "객체변동 일시", "제작업체명"
    )
  )

  list(classifications = classifications, table_fields = table_fields)
}

extract_inner_zip <- function(outer_zip, inner_member, tmp_dir) {
  utils::unzip(outer_zip, files = inner_member, exdir = tmp_dir)
  inner_zip <- file.path(tmp_dir, inner_member)
  if (!file.exists(inner_zip)) stop("Failed to extract inner zip: ", inner_member)
  inner_zip
}

make_poi_id <- function(source_file, source_layer, source_feature_index, geometry) {
  coords <- sf::st_coordinates(geometry)
  key <- paste(
    source_file,
    source_layer,
    source_feature_index,
    sprintf("%.6f", coords[, "X"]),
    sprintf("%.6f", coords[, "Y"]),
    sep = "|"
  )
  paste0("ngii_", vapply(key, digest, character(1), algo = "xxhash64", serialize = FALSE, USE.NAMES = FALSE))
}

read_point_layer <- function(shp_path, source_file, source_layer, target_epsg, assume_5179_if_missing) {
  started_at <- Sys.time()
  layer <- tools::file_path_sans_ext(basename(shp_path))
  x <- sf::st_read(
    shp_path,
    layer = layer,
    quiet = TRUE,
    options = c("ENCODING=CP949"),
    stringsAsFactors = FALSE
  )

  input_feature_count <- nrow(x)
  source_feature_index <- seq_len(input_feature_count)
  geometry_type_in <- paste(sort(unique(as.character(sf::st_geometry_type(x)))), collapse = ";")
  point_like <- all(as.character(sf::st_geometry_type(x)) %in% c("POINT", "MULTIPOINT"))

  if (!point_like) {
    return(list(
      data = NULL,
      summary = tibble(
        source_file = source_file,
        source_layer = source_layer,
        geometry_type = geometry_type_in,
        input_feature_count = input_feature_count,
        output_feature_count = 0L,
        invalid_geometry_count_before = NA_integer_,
        invalid_geometry_count_after = NA_integer_,
        crs_input = sf::st_crs(x)$epsg %||% NA_integer_,
        crs_output = target_epsg,
        processing_status = "skipped_non_point",
        error_message = NA_character_,
        started_at = as.character(started_at),
        finished_at = as.character(Sys.time())
      )
    ))
  }

  epsg_in <- sf::st_crs(x)$epsg %||% NA_integer_
  if (is.na(epsg_in) && assume_5179_if_missing) {
    sf::st_crs(x) <- 5179
    epsg_in <- 5179
  }
  if (is.na(sf::st_crs(x))) stop("Missing CRS for ", source_file, "::", source_layer)
  if (!identical(sf::st_crs(x)$epsg, target_epsg)) x <- sf::st_transform(x, target_epsg)

  invalid_before <- sum(!sf::st_is_valid(x), na.rm = TRUE)
  x <- sf::st_make_valid(x)
  keep <- as.character(sf::st_geometry_type(x)) %in% c("POINT", "MULTIPOINT") & !sf::st_is_empty(x)
  x <- x[keep, , drop = FALSE]
  source_feature_index <- source_feature_index[keep]
  x <- suppressWarnings(sf::st_cast(x, "POINT", warn = FALSE))
  invalid_after <- sum(!sf::st_is_valid(x), na.rm = TRUE)

  x$source_file <- rep(source_file, nrow(x))
  x$source_layer <- rep(source_layer, nrow(x))
  x$source_feature_index <- source_feature_index
  x$processing_crs_input <- rep(epsg_in, nrow(x))
  x$processing_crs_output <- rep(target_epsg, nrow(x))
  x$poi_id <- make_poi_id(x$source_file, x$source_layer, x$source_feature_index, sf::st_geometry(x))

  x <- x[, c("poi_id", setdiff(names(x), "poi_id"))]

  list(
    data = x,
    summary = tibble(
      source_file = source_file,
      source_layer = source_layer,
      geometry_type = geometry_type_in,
      input_feature_count = input_feature_count,
      output_feature_count = nrow(x),
      invalid_geometry_count_before = invalid_before,
      invalid_geometry_count_after = invalid_after,
      crs_input = epsg_in,
      crs_output = sf::st_crs(x)$epsg %||% target_epsg,
      processing_status = "ok",
      error_message = NA_character_,
      started_at = as.character(started_at),
      finished_at = as.character(Sys.time())
    )
  )
}

process_region_zip <- function(inner_member, outer_zip, target_epsg, assume_5179_if_missing) {
  tmp_dir <- tempfile("ngii_poi_")
  dir.create(tmp_dir, recursive = TRUE)
  on.exit(unlink(tmp_dir, recursive = TRUE, force = TRUE), add = TRUE)

  inner_zip <- extract_inner_zip(outer_zip, inner_member, tmp_dir)
  inv <- zip_inventory(inner_zip) |> mutate(source_file = inner_member)
  shp_members <- inv$Name[inv$is_shapefile]

  if (!length(shp_members)) {
    return(list(data = NULL, archive = inv, summary = tibble(
      source_file = inner_member,
      source_layer = NA_character_,
      geometry_type = NA_character_,
      input_feature_count = 0L,
      output_feature_count = 0L,
      invalid_geometry_count_before = NA_integer_,
      invalid_geometry_count_after = NA_integer_,
      crs_input = NA_integer_,
      crs_output = target_epsg,
      processing_status = "skipped_no_shapefile",
      error_message = "No shapefile members found",
      started_at = as.character(Sys.time()),
      finished_at = as.character(Sys.time())
    )))
  }

  # The NGII regional zips place point POI shapefiles under TN_POI. Extract only
  # shapefile sidecars from directories containing shp files to avoid loading
  # large non-spatial CSV/DBF tables such as TN_ADRES and TN_FRGN.
  shp_dirs <- unique(dirname(shp_members))
  for (shp_dir in shp_dirs) {
    ok <- system2(
      "unzip",
      c("-q", shQuote(inner_zip), shQuote(file.path(shp_dir, "*")), "-d", shQuote(tmp_dir)),
      stdout = FALSE,
      stderr = FALSE
    )
    if (!is.null(attr(ok, "status")) && attr(ok, "status") != 0) {
      stop("Failed to extract shapefile directory from ", inner_member)
    }
  }

  shp_paths <- Sys.glob(file.path(tmp_dir, "*", "*.shp"))
  layer_results <- lapply(shp_members, function(member) {
    source_layer <- tools::file_path_sans_ext(basename(member))
    tryCatch({
      shp_path <- shp_paths[tools::file_path_sans_ext(basename(shp_paths)) == source_layer][1]
      if (is.na(shp_path) && length(shp_paths) == 1) shp_path <- shp_paths[1]
      if (is.na(shp_path)) stop("Extracted shapefile not found for archive member: ", member)
      read_point_layer(shp_path, inner_member, source_layer, target_epsg, assume_5179_if_missing)
    }, error = function(e) {
      list(data = NULL, summary = tibble(
        source_file = inner_member,
        source_layer = source_layer,
        geometry_type = NA_character_,
        input_feature_count = NA_integer_,
        output_feature_count = NA_integer_,
        invalid_geometry_count_before = NA_integer_,
        invalid_geometry_count_after = NA_integer_,
        crs_input = NA_integer_,
        crs_output = target_epsg,
        processing_status = "error",
        error_message = conditionMessage(e),
        started_at = as.character(Sys.time()),
        finished_at = as.character(Sys.time())
      ))
    })
  })

  list(
    data = bind_rows(lapply(layer_results, `[[`, "data")),
    archive = inv,
    summary = bind_rows(lapply(layer_results, `[[`, "summary"))
  )
}

write_storage_design_note <- function(path) {
  lines <- c(
    "# Korea NGII POI Storage Design",
    "",
    "This dataset separates geometry from attributes to keep the GeoPackage small and fast to open.",
    "",
    "- `/members/dhnyu/fusedatalarge/processed/korea_poi_ngii_point.gpkg` contains layer `points` with only `poi_id` and point geometry.",
    "- `/members/dhnyu/fusedatalarge/processed/korea_poi_ngii_attributes.parquet` contains `poi_id`, all original non-geometry NGII attributes, source tracking fields, and processing metadata.",
    "- `poi_id` is the join key between geometry and attributes.",
    "- `poi_id` is deterministic: it hashes `source_file`, `source_layer`, `source_feature_index`, and EPSG:5186 coordinates.",
    "",
    "Example R join:",
    "",
    "```r",
    "library(sf)",
    "library(arrow)",
    "library(dplyr)",
    "",
    "geom <- st_read('/members/dhnyu/fusedatalarge/processed/korea_poi_ngii_point.gpkg', layer = 'points')",
    "attrs <- read_parquet('/members/dhnyu/fusedatalarge/processed/korea_poi_ngii_attributes.parquet')",
    "poi <- left_join(geom, attrs, by = 'poi_id')",
    "```"
  )
  writeLines(lines, path, useBytes = TRUE)
}

validate_outputs <- function(gpkg, layer, attr_parquet, expected_epsg) {
  geom <- sf::st_read(gpkg, layer = layer, quiet = TRUE)
  attrs <- arrow::read_parquet(attr_parquet, col_select = "poi_id")
  geom_cols <- names(sf::st_drop_geometry(geom))
  tibble(
    gpkg_exists = file.exists(gpkg),
    attribute_parquet_exists = file.exists(attr_parquet),
    gpkg_layer = layer,
    gpkg_feature_count = nrow(geom),
    attribute_row_count = nrow(attrs),
    gpkg_poi_id_unique = !anyDuplicated(geom$poi_id),
    attribute_poi_id_unique = !anyDuplicated(attrs$poi_id),
    id_counts_match = nrow(geom) == nrow(attrs),
    crs_epsg = sf::st_crs(geom)$epsg %||% NA_integer_,
    crs_ok = identical(sf::st_crs(geom)$epsg, expected_epsg),
    geometry_types = paste(sort(unique(as.character(sf::st_geometry_type(geom)))), collapse = ";"),
    gpkg_non_geometry_columns = paste(geom_cols, collapse = ";"),
    gpkg_has_only_poi_id = identical(geom_cols, "poi_id")
  )
}

log_msg("Starting NGII nationwide POI point split-storage merge")
log_msg("Raw directory:", raw_dir)
log_msg("Outer shapefile zip:", outer_shp_zip)
log_msg("Geometry GeoPackage:", out_gpkg)
log_msg("Attribute parquet:", out_attr_parquet)
log_msg("Summary parquet:", out_summary_parquet)
log_msg("Log path:", out_log)
log_msg("Storage design note:", out_design_note)
log_msg("Workers:", workers)
log_msg("Existing outputs before run:", if (length(existing_before)) paste(existing_before, collapse = "; ") else "none")
if (!is.na(log_backup)) log_msg("Backed up existing log:", log_backup)

if (!dir.exists(raw_dir)) stop("Raw directory does not exist: ", raw_dir)
if (!file.exists(outer_shp_zip)) stop("Raw shapefile archive does not exist: ", outer_shp_zip)

raw_files <- list_raw_files(raw_dir)
log_msg("Raw files found:", nrow(raw_files))
log_msg("Raw archives:", paste(raw_files$name[raw_files$is_archive], collapse = "; "))
log_msg("Raw spatial files:", paste(raw_files$name[raw_files$is_spatial], collapse = "; "))
log_msg("Raw metadata files:", paste(raw_files$name[raw_files$is_metadata], collapse = "; "))

metadata <- read_metadata(raw_files$path[raw_files$is_metadata])
log_msg("Classification metadata rows:", nrow(metadata$classifications))
log_msg("TN_POI field metadata rows:", nrow(metadata$table_fields))

outer_inv <- zip_inventory(outer_shp_zip)
inner_members <- sort(outer_inv$Name[outer_inv$is_zip & grepl(inner_zip_regex, outer_inv$Name, ignore.case = TRUE)])
if (!length(inner_members)) stop("No regional zip files matched: ", inner_zip_regex)
if (!is.na(max_files)) inner_members <- head(inner_members, max_files)
log_msg("Regional zip files selected:", length(inner_members))
log_msg("Regional zip file names:", paste(inner_members, collapse = "; "))

future::plan(future.mirai::mirai_multisession, workers = workers)
options(future.globals.maxSize = Inf)
on.exit(future::plan(future::sequential), add = TRUE)

results <- future.apply::future_lapply(
  inner_members,
  process_region_zip,
  outer_zip = outer_shp_zip,
  target_epsg = target_epsg,
  assume_5179_if_missing = assume_5179_if_missing,
  future.seed = TRUE
)

archive_summary <- bind_rows(lapply(results, `[[`, "archive"))
layer_summary <- bind_rows(lapply(results, `[[`, "summary"))
errors <- layer_summary |> filter(processing_status == "error")
if (nrow(errors)) {
  arrow::write_parquet(layer_summary, out_summary_parquet)
  stop("One or more layers failed. See summary parquet: ", out_summary_parquet)
}

poi_full <- bind_rows(lapply(results, `[[`, "data"))
if (!inherits(poi_full, "sf") || !nrow(poi_full)) stop("No point features were read")
if (!identical(sf::st_crs(poi_full)$epsg, target_epsg)) poi_full <- sf::st_transform(poi_full, target_epsg)

before_count <- nrow(poi_full)
duplicate_count <- sum(duplicated(poi_full$poi_id))
if (duplicate_count > 0) {
  keep <- !duplicated(poi_full$poi_id)
  poi_full <- poi_full[keep, , drop = FALSE]
}
after_count <- nrow(poi_full)

log_msg("Merged feature count before poi_id duplicate check:", before_count)
log_msg("Duplicate poi_id records dropped:", duplicate_count)
log_msg("Merged feature count after cleanup:", after_count)

attr_table <- sf::st_drop_geometry(poi_full)
geom_only <- poi_full[, "poi_id", drop = FALSE]

gpkg_backup <- backup_existing(out_gpkg)
attr_backup <- backup_existing(out_attr_parquet)
summary_backup <- backup_existing(out_summary_parquet)
design_backup <- backup_existing(out_design_note)
if (!is.na(gpkg_backup)) log_msg("Backed up existing GeoPackage:", gpkg_backup)
if (!is.na(attr_backup)) log_msg("Backed up existing attribute parquet:", attr_backup)
if (!is.na(summary_backup)) log_msg("Backed up existing summary parquet:", summary_backup)
if (!is.na(design_backup)) log_msg("Backed up existing design note:", design_backup)

sf::st_write(geom_only, out_gpkg, layer = gpkg_layer, delete_layer = TRUE, quiet = TRUE)
arrow::write_parquet(attr_table, out_attr_parquet)

summary_out <- bind_rows(
  layer_summary |>
    mutate(
      record_type = "layer",
      output_gpkg = out_gpkg,
      output_layer = gpkg_layer,
      output_attribute_parquet = out_attr_parquet,
      total_features_before_cleanup = before_count,
      total_features_written = after_count,
      duplicate_poi_id_records_dropped = duplicate_count,
      gpkg_backup_path = gpkg_backup,
      attribute_backup_path = attr_backup,
      summary_backup_path = summary_backup,
      metadata_classification_rows = nrow(metadata$classifications),
      metadata_field_rows = nrow(metadata$table_fields)
    ),
  archive_summary |>
    transmute(
      source_file,
      source_layer = NA_character_,
      geometry_type = NA_character_,
      input_feature_count = NA_real_,
      output_feature_count = NA_real_,
      invalid_geometry_count_before = NA_real_,
      invalid_geometry_count_after = NA_real_,
      crs_input = NA_integer_,
      crs_output = target_epsg,
      processing_status = if_else(is_shapefile, "archive_shp", "archive_aux"),
      error_message = paste0(Name, " length_bytes=", Length),
      started_at = NA_character_,
      finished_at = NA_character_
    ) |>
    mutate(
      record_type = "archive_member",
      output_gpkg = out_gpkg,
      output_layer = gpkg_layer,
      output_attribute_parquet = out_attr_parquet,
      total_features_before_cleanup = before_count,
      total_features_written = after_count,
      duplicate_poi_id_records_dropped = duplicate_count,
      gpkg_backup_path = gpkg_backup,
      attribute_backup_path = attr_backup,
      summary_backup_path = summary_backup,
      metadata_classification_rows = nrow(metadata$classifications),
      metadata_field_rows = nrow(metadata$table_fields)
    ),
  metadata$table_fields |>
    transmute(
      source_file = NA_character_,
      source_layer = table_name,
      geometry_type = "POINT",
      input_feature_count = NA_real_,
      output_feature_count = NA_real_,
      invalid_geometry_count_before = NA_real_,
      invalid_geometry_count_after = NA_real_,
      crs_input = NA_integer_,
      crs_output = target_epsg,
      processing_status = "metadata_field",
      error_message = paste(field_name, field_label_ko, sep = " | "),
      started_at = NA_character_,
      finished_at = NA_character_
    ) |>
    mutate(
      record_type = "metadata",
      output_gpkg = out_gpkg,
      output_layer = gpkg_layer,
      output_attribute_parquet = out_attr_parquet,
      total_features_before_cleanup = before_count,
      total_features_written = after_count,
      duplicate_poi_id_records_dropped = duplicate_count,
      gpkg_backup_path = gpkg_backup,
      attribute_backup_path = attr_backup,
      summary_backup_path = summary_backup,
      metadata_classification_rows = nrow(metadata$classifications),
      metadata_field_rows = nrow(metadata$table_fields)
    ),
  metadata$classifications |>
    transmute(
      source_file = NA_character_,
      source_layer = "TN_ASORTCL",
      geometry_type = "POINT",
      input_feature_count = NA_real_,
      output_feature_count = NA_real_,
      invalid_geometry_count_before = NA_real_,
      invalid_geometry_count_after = NA_real_,
      crs_input = NA_integer_,
      crs_output = target_epsg,
      processing_status = "metadata_classification",
      error_message = paste(input_code, lclasdc, mlsfcdc, sclasdc, dclasdc, dfclasdc, dgclasdc, sep = " | "),
      started_at = NA_character_,
      finished_at = NA_character_
    ) |>
    mutate(
      record_type = "metadata",
      output_gpkg = out_gpkg,
      output_layer = gpkg_layer,
      output_attribute_parquet = out_attr_parquet,
      total_features_before_cleanup = before_count,
      total_features_written = after_count,
      duplicate_poi_id_records_dropped = duplicate_count,
      gpkg_backup_path = gpkg_backup,
      attribute_backup_path = attr_backup,
      summary_backup_path = summary_backup,
      metadata_classification_rows = nrow(metadata$classifications),
      metadata_field_rows = nrow(metadata$table_fields)
    )
)
arrow::write_parquet(summary_out, out_summary_parquet)
write_storage_design_note(out_design_note)

validation <- validate_outputs(out_gpkg, gpkg_layer, out_attr_parquet, target_epsg)
log_msg("Validation gpkg feature count:", validation$gpkg_feature_count)
log_msg("Validation attribute row count:", validation$attribute_row_count)
log_msg("Validation poi_id unique in gpkg:", validation$gpkg_poi_id_unique)
log_msg("Validation poi_id unique in attributes:", validation$attribute_poi_id_unique)
log_msg("Validation id counts match:", validation$id_counts_match)
log_msg("Validation CRS EPSG:", validation$crs_epsg)
log_msg("Validation geometry types:", validation$geometry_types)
log_msg("Validation GeoPackage non-geometry columns:", validation$gpkg_non_geometry_columns)
log_msg("Wrote geometry GeoPackage:", out_gpkg)
log_msg("Wrote attribute parquet:", out_attr_parquet)
log_msg("Wrote summary parquet:", out_summary_parquet)
log_msg("Wrote storage design note:", out_design_note)
log_msg("Finished NGII nationwide POI split-storage merge")
