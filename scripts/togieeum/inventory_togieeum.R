#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(sf)
  library(data.table)
  library(arrow)
  library(readxl)
  library(digest)
})

sf::sf_use_s2(FALSE)
options(stringsAsFactors = FALSE)

`%||%` <- function(x, y) {
  if (is.null(x) || length(x) == 0 || all(is.na(x)) || identical(x, "")) y else x
}

root <- path.expand(Sys.getenv("TOGIEEUM_ROOT", "~/fusedatalarge/raw/togieeum"))
out_dir <- path.expand(Sys.getenv("TOGIEEUM_PROCESSED_DIR", "~/fusedatalarge/processed"))
inventory_out <- file.path(out_dir, "togieeum_inventory.parquet")
catalog_out <- file.path(out_dir, "togieeum_layer_catalog.parquet")
report_out <- file.path(out_dir, "togieeum_schema_report.md")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

log_msg <- function(...) {
  cat(sprintf("[%s] %s\n", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"), paste(..., collapse = " ")))
}

vsi_zip_member <- function(zip_path, member) {
  paste0("/vsizip/", normalizePath(zip_path, mustWork = TRUE), "/", member)
}

feature_count_from_shx <- function(inv, shp_member) {
  shx_member <- sub("[.][Ss][Hh][Pp]$", ".shx", shp_member)
  shx_len <- inv[tolower(Name) == tolower(shx_member), Length]
  if (!length(shx_len) || is.na(shx_len)) return(NA_integer_)
  as.integer((shx_len - 100L) / 8L)
}

layer_family <- function(layer_name) {
  sub("^(KLIP|UPIS)_", "", layer_name)
}

geometry_class <- function(geometry_type) {
  gt <- toupper(geometry_type %||% "")
  if (grepl("POLYGON|SURFACE", gt)) return("polygon")
  if (grepl("POINT", gt)) return("point")
  if (grepl("LINE|CURVE", gt)) return("line")
  if (!nzchar(gt)) return("unknown")
  "other"
}

read_schema <- function(zip_path, member) {
  dsn <- paste0("/vsizip/", normalizePath(zip_path, mustWork = TRUE))
  layer <- tools::file_path_sans_ext(basename(member))
  info <- try(system2("ogrinfo", c("-ro", "-so", dsn, layer), stdout = TRUE, stderr = TRUE), silent = TRUE)
  if (inherits(info, "try-error") || !length(info)) {
    return(list(
      schema = data.table(),
      geometry_type = NA_character_,
      crs_input = NA_character_,
      crs_epsg = NA_integer_,
      error = as.character(info)
    ))
  }

  geom_line <- info[grepl("^Geometry:", info)]
  geometry_type <- if (length(geom_line)) trimws(sub("^Geometry:[[:space:]]*", "", geom_line[[1]])) else NA_character_

  epsg_matches <- regmatches(info, gregexpr('ID\\["EPSG",[0-9]+\\]', info, perl = TRUE))
  epsg_values <- unique(as.integer(gsub("[^0-9]", "", unlist(epsg_matches))))
  korean_projected_epsg <- c(5186L, 5174L, 5179L, 5178L, 5180L, 5181L, 5185L, 5187L, 5188L)
  crs_epsg <- if (any(korean_projected_epsg %in% epsg_values)) {
    korean_projected_epsg[korean_projected_epsg %in% epsg_values][[1]]
  } else if (length(epsg_values)) {
    tail(epsg_values, 1L)
  } else {
    NA_integer_
  }
  crs_line <- info[grepl('^(PROJCRS|GEOGCRS)\\[', info)]
  crs_input <- if (length(crs_line)) crs_line[[1]] else NA_character_

  field_lines <- info[grepl("^[A-Za-z_][A-Za-z0-9_]*:[[:space:]]", info)]
  field_lines <- field_lines[!grepl("^(INFO|Layer name|Geometry|Feature Count|Extent|FID Column|Geometry Column|Data axis)", field_lines)]
  if (!length(field_lines)) {
    schema <- data.table(field_order = integer(), field_name = character(), field_type_r = character())
  } else {
    schema <- data.table(raw = field_lines)
    schema[, `:=`(
      field_order = seq_len(.N),
      field_name = sub(":.*$", "", raw),
      field_type_r = trimws(sub("^[^:]+:[[:space:]]*", "", raw))
    )]
    schema <- schema[, .(field_order, field_name, field_type_r)]
  }
  list(
    schema = schema,
    geometry_type = geometry_type,
    crs_input = crs_input,
    crs_epsg = crs_epsg,
    error = NA_character_
  )
}

inspect_zip <- function(zip_path) {
  source_zip <- basename(zip_path)
  source_system <- sub("_.*$", "", source_zip)
  region_code <- sub(".*_([0-9]{5})[.]zip$", "\\1", source_zip)
  inv <- as.data.table(utils::unzip(zip_path, list = TRUE))
  inv[, `:=`(
    source_zip = source_zip,
    source_path = zip_path,
    source_system = source_system,
    region_code = region_code,
    extension = tolower(tools::file_ext(Name))
  )]

  shp_members <- inv[extension == "shp", Name]
  if (!length(shp_members)) {
    csv_members <- inv[extension == "csv", Name]
    return(list(
      inventory = inv[, .(
        source_system, source_zip, source_path, region_code,
        archive_member = Name,
        layer_name = tools::file_path_sans_ext(basename(Name)),
        layer_family = tools::file_path_sans_ext(basename(Name)),
        file_type = extension,
        geometry_type = NA_character_,
        geometry_class = "none",
        crs_input = NA_character_,
        crs_epsg = NA_integer_,
        feature_count = NA_integer_,
        attribute_field_count = NA_integer_,
        schema_hash = NA_character_,
        schema_fields = NA_character_,
        schema_status = "csv_member_or_aux",
        error_message = NA_character_,
        zip_size_bytes = file.info(zip_path)$size,
        member_size_bytes = Length
      )],
      schema = data.table()
    ))
  }

  rows <- vector("list", length(shp_members))
  schemas <- list()
  for (i in seq_along(shp_members)) {
    member <- shp_members[[i]]
    layer <- tools::file_path_sans_ext(basename(member))
    log_msg("Inspecting", source_zip, layer)
    rs <- read_schema(zip_path, member)
    schema_hash <- if (nrow(rs$schema)) {
      digest(paste(rs$schema$field_order, rs$schema$field_name, rs$schema$field_type_r, collapse = "|"), algo = "xxhash64", serialize = FALSE)
    } else {
      NA_character_
    }
    if (nrow(rs$schema)) {
      ss <- copy(rs$schema)
      ss[, `:=`(
        source_system = source_system,
        source_zip = source_zip,
        region_code = region_code,
        layer_name = layer,
        layer_family = layer_family(layer),
        schema_hash = schema_hash
      )]
      setcolorder(ss, c("source_system", "source_zip", "region_code", "layer_name", "layer_family", "schema_hash", "field_order", "field_name", "field_type_r"))
      schemas[[length(schemas) + 1L]] <- ss
    }
    fields <- if (nrow(rs$schema)) paste(rs$schema$field_name, collapse = "|") else NA_character_
    rows[[i]] <- data.table(
      source_system = source_system,
      source_zip = source_zip,
      source_path = zip_path,
      region_code = region_code,
      archive_member = member,
      layer_name = layer,
      layer_family = layer_family(layer),
      file_type = "shp",
      geometry_type = rs$geometry_type,
      geometry_class = geometry_class(rs$geometry_type),
      crs_input = rs$crs_input,
      crs_epsg = rs$crs_epsg,
      feature_count = feature_count_from_shx(inv, member),
      attribute_field_count = nrow(rs$schema),
      schema_hash = schema_hash,
      schema_fields = fields,
      schema_status = if (is.na(rs$error)) "ok" else "failed",
      error_message = rs$error,
      zip_size_bytes = file.info(zip_path)$size,
      member_size_bytes = inv[Name == member, Length]
    )
  }

  aux <- inv[extension != "shp", .(
    source_system, source_zip, source_path, region_code,
    archive_member = Name,
    layer_name = tools::file_path_sans_ext(basename(Name)),
    layer_family = tools::file_path_sans_ext(basename(Name)),
    file_type = extension,
    geometry_type = NA_character_,
    geometry_class = "none",
    crs_input = NA_character_,
    crs_epsg = NA_integer_,
    feature_count = NA_integer_,
    attribute_field_count = NA_integer_,
    schema_hash = NA_character_,
    schema_fields = NA_character_,
    schema_status = "aux_member",
    error_message = NA_character_,
    zip_size_bytes = file.info(zip_path)$size,
    member_size_bytes = Length
  )]

  list(
    inventory = rbindlist(c(rows, list(aux)), fill = TRUE),
    schema = rbindlist(schemas, fill = TRUE)
  )
}

inspect_csv_file <- function(csv_path) {
  log_msg("Inspecting CSV", basename(csv_path))
  header <- names(data.table::fread(csv_path, nrows = 0, encoding = "UTF-8", showProgress = FALSE))
  wc_out <- system2("wc", c("-l", csv_path), stdout = TRUE)
  n <- as.integer(strsplit(trimws(wc_out), "[[:space:]]+")[[1]][1])
  schema_hash <- digest(paste(seq_along(header), header, collapse = "|"), algo = "xxhash64", serialize = FALSE)
  inv <- data.table(
    source_system = fifelse(grepl("^KP_", basename(csv_path)), "KLIP", fifelse(grepl("^TN_", basename(csv_path)), "UPIS", "CSV")),
    source_zip = NA_character_,
    source_path = csv_path,
    region_code = NA_character_,
    archive_member = basename(csv_path),
    layer_name = tools::file_path_sans_ext(basename(csv_path)),
    layer_family = tools::file_path_sans_ext(basename(csv_path)),
    file_type = "csv",
    geometry_type = NA_character_,
    geometry_class = "none",
    crs_input = NA_character_,
    crs_epsg = NA_integer_,
    feature_count = max(0L, n - 1L),
    attribute_field_count = length(header),
    schema_hash = schema_hash,
    schema_fields = paste(header, collapse = "|"),
    schema_status = "ok",
    error_message = NA_character_,
    zip_size_bytes = NA_real_,
    member_size_bytes = file.info(csv_path)$size
  )
  schema <- data.table(
    source_system = inv$source_system,
    source_zip = NA_character_,
    region_code = NA_character_,
    layer_name = inv$layer_name,
    layer_family = inv$layer_family,
    schema_hash = schema_hash,
    field_order = seq_along(header),
    field_name = header,
    field_type_r = "csv_untyped"
  )
  list(inventory = inv, schema = schema)
}

read_klip_metadata <- function(path) {
  if (!file.exists(path)) return(list(tables = data.table(), fields = data.table()))
  tables <- as.data.table(readxl::read_excel(path, sheet = "테이블 목록"))
  setnames(tables, make.names(names(tables), unique = TRUE))
  tables[, `:=`(metadata_source = basename(path), source_system = "KLIP")]

  fields <- as.data.table(readxl::read_excel(path, sheet = "테이블 정의서"))
  setnames(fields, make.names(names(fields), unique = TRUE))
  fields[, `:=`(metadata_source = basename(path), source_system = "KLIP")]
  list(tables = tables, fields = fields)
}

read_upis_metadata <- function(design_path, col_path) {
  out_tables <- list()
  out_fields <- list()
  if (file.exists(design_path)) {
    raw <- as.data.table(readxl::read_excel(design_path, sheet = "도형테이블 설계 목록", col_names = FALSE))
    raw <- raw[!is.na(...3) & grepl("^UPIS_", ...3)]
    if (nrow(raw)) {
      out_tables[[length(out_tables) + 1L]] <- raw[, .(
        metadata_source = basename(design_path),
        source_system = "UPIS",
        category = as.character(...2),
        table_name = as.character(...3),
        table_label_ko = as.character(...4),
        geometry_label = as.character(...5)
      )]
    }
    raw_attr <- as.data.table(readxl::read_excel(design_path, sheet = "속성테이블 설계 목록", col_names = FALSE))
    raw_attr <- raw_attr[!is.na(...3) & grepl("^[A-Z][A-Z0-9_]+$", ...3)]
    if (nrow(raw_attr)) {
      out_tables[[length(out_tables) + 1L]] <- raw_attr[, .(
        metadata_source = basename(design_path),
        source_system = "UPIS",
        category = as.character(...2),
        table_name = as.character(...3),
        table_label_ko = as.character(...4),
        geometry_label = NA_character_
      )]
    }
  }
  if (file.exists(col_path)) {
    fields <- as.data.table(readxl::read_excel(col_path, sheet = 1))
    setnames(fields, make.names(names(fields), unique = TRUE))
    fields[, `:=`(metadata_source = basename(col_path), source_system = "UPIS")]
    out_fields[[length(out_fields) + 1L]] <- fields
  }
  list(tables = rbindlist(out_tables, fill = TRUE), fields = rbindlist(out_fields, fill = TRUE))
}

recommend_key <- function(layer_family_name, fields) {
  preferred <- c("GID", "PRESENT_SN", "MNUM", "OBJECTID", "ID", "UFID", "RECORD_CODE", "PROJ_CODE", "WEVD_CD")
  present <- unique(fields[layer_family == layer_family_name, field_name])
  hit <- preferred[preferred %in% present]
  if (length(hit)) hit[[1]] else paste0(tolower(layer_family_name), "_id")
}

write_report <- function(path, inventory, catalog, klip_meta, upis_meta, csv_files, zip_files) {
  geom_counts <- inventory[file_type == "shp" & schema_status == "ok", .N, by = geometry_class][order(geometry_class)]
  source_counts <- inventory[file_type == "shp" & schema_status == "ok", .(
    layers = .N,
    feature_count = sum(feature_count, na.rm = TRUE),
    layer_families = uniqueN(layer_family)
  ), by = source_system][order(source_system)]
  schema_variants <- catalog[, .N, by = .(source_system, layer_family, schema_variant_count)][order(source_system, layer_family)]
  lines <- c(
    "# Togieeum Inventory and Schema Report",
    "",
    paste0("Generated: ", format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")),
    "",
    "## Scope",
    "",
    paste0("- Root inspected: `", root, "`"),
    "- Included archive patterns: `KLIP_003_*.zip`, `UPIS_003_*.zip`",
    "- Excluded: `TN_RIVER_BT`",
    "- No nationwide merged geometry outputs were created.",
    "",
    "## Source Files",
    "",
    paste0("- Zip files inspected: ", length(zip_files)),
    paste0("- CSV files inspected: ", length(csv_files)),
    "- Metadata/codebook files inspected:",
    "  - `24-1010_토지이음개방용 KLIP 테이블 목록 및 정의서.xlsx`",
    "  - `데이터베이스설계서_UPIS8_20220512(NS).xlsx`",
    "  - `컬럼정의서(NS).xls`",
    "",
    "## Geometry Inventory",
    "",
    paste(capture.output(print(geom_counts)), collapse = "\n"),
    "",
    "## Source Summary",
    "",
    paste(capture.output(print(source_counts)), collapse = "\n"),
    "",
    "## Schema Compatibility",
    "",
    "Layers with `schema_variant_count == 1` have the same discovered field schema across inspected regions for that source system and family. Higher counts should be reviewed before merging.",
    "",
    paste(capture.output(print(schema_variants)), collapse = "\n"),
    "",
    "## Recommended Canonical Storage Design",
    "",
    "Use split storage for any future nationwide canonical outputs:",
    "",
    "- GeoPackage: geometry plus stable key only.",
    "- Parquet: all non-geometry attributes plus the same key.",
    "- Final geometry CRS should be EPSG:5186 after CRS verification/transformation.",
    "- Preserve region/source lineage columns: `source_system`, `source_zip`, `region_code`, `source_layer`, `source_feature_index`.",
    "",
    "| Source | Layer family | Merge nationwide? | Geometry type | Expected geometry output | Expected attribute output | Recommended key | Estimated feature count | Schema variants |",
    "|---|---:|---:|---|---|---|---|---:|---:|"
  )
  for (i in seq_len(nrow(catalog))) {
    row <- catalog[i]
    merge_yes <- if (row$geometry_class %in% c("polygon", "point", "line") && row$schema_variant_count == 1) "yes" else "review"
    base <- tolower(paste("togieeum", row$source_system, row$layer_family, sep = "_"))
    lines <- c(lines, sprintf(
      "| %s | `%s` | %s | %s | `%s.gpkg` | `%s_attributes.parquet` | `%s` | %s | %s |",
      row$source_system,
      row$layer_family,
      merge_yes,
      row$geometry_class,
      base,
      base,
      row$recommended_key,
      format(row$estimated_feature_count, scientific = FALSE, trim = TRUE),
      row$schema_variant_count
    ))
  }
  lines <- c(
    lines,
    "",
    "## Notes",
    "",
    "- `KLIP_003_20260501_00000.zip` contains CSV members, not shapefiles.",
    "- Top-level CSVs are side/attribute tables and are inventoried with `geometry_class = none`.",
    "- Korean metadata labels from Excel/XLS are preserved in the Parquet inventory/catalog where available."
  )
  writeLines(lines, path, useBytes = TRUE)
}

if (!dir.exists(root)) stop("Missing Togieeum root: ", root)

zip_files <- list.files(root, pattern = "^(KLIP|UPIS)_003_.*[.]zip$", full.names = TRUE)
zip_files <- zip_files[!grepl("/TN_RIVER_BT/", zip_files, fixed = FALSE)]
zip_files <- sort(zip_files)
csv_files <- list.files(root, pattern = "[.]csv$", full.names = TRUE)
csv_files <- csv_files[!grepl("/TN_RIVER_BT/", csv_files, fixed = FALSE)]

log_msg("Zip files:", length(zip_files))
log_msg("CSV files:", length(csv_files))

zip_results <- lapply(zip_files, inspect_zip)
csv_results <- lapply(csv_files, inspect_csv_file)

inventory <- rbindlist(c(lapply(zip_results, `[[`, "inventory"), lapply(csv_results, `[[`, "inventory")), fill = TRUE)
schema <- rbindlist(c(lapply(zip_results, `[[`, "schema"), lapply(csv_results, `[[`, "schema")), fill = TRUE)

klip_meta <- read_klip_metadata(file.path(root, "24-1010_토지이음개방용 KLIP 테이블 목록 및 정의서.xlsx"))
upis_meta <- read_upis_metadata(
  file.path(root, "데이터베이스설계서_UPIS8_20220512(NS).xlsx"),
  file.path(root, "컬럼정의서(NS).xls")
)

klip_table_labels <- data.table()
if (nrow(klip_meta$tables)) {
  name_col <- "테이블.영문명"
  label_col <- "테이블.한글명"
  format_col <- "파일.형식"
  klip_table_labels <- klip_meta$tables[, .(
    source_system = "KLIP",
    layer_name = get(name_col),
    table_label_ko = get(label_col),
    metadata_file_type = get(format_col)
  )]
}

upis_table_labels <- data.table()
if (nrow(upis_meta$tables)) {
  upis_table_labels <- upis_meta$tables[, .(
    source_system = "UPIS",
    layer_name = table_name,
    table_label_ko = table_label_ko,
    metadata_file_type = geometry_label
  )]
}
table_labels <- rbindlist(list(klip_table_labels, upis_table_labels), fill = TRUE)

shp_inv <- inventory[file_type == "shp" & schema_status == "ok"]
catalog <- shp_inv[, .(
  archive_count = uniqueN(source_zip),
  region_count = uniqueN(region_code),
  layer_count = .N,
  geometry_types = paste(sort(unique(geometry_type)), collapse = ";"),
  geometry_class = paste(sort(unique(geometry_class)), collapse = ";"),
  crs_epsg_values = paste(sort(unique(na.omit(crs_epsg))), collapse = ";"),
  estimated_feature_count = sum(feature_count, na.rm = TRUE),
  min_feature_count = min(feature_count, na.rm = TRUE),
  max_feature_count = max(feature_count, na.rm = TRUE),
  schema_variant_count = uniqueN(schema_hash),
  schema_hashes = paste(sort(unique(schema_hash)), collapse = ";"),
  field_count_values = paste(sort(unique(attribute_field_count)), collapse = ";")
), by = .(source_system, layer_family)]

family_fields <- unique(schema[, .(source_system, layer_family, field_name)])
catalog[, recommended_key := vapply(layer_family, recommend_key, character(1), fields = family_fields)]
catalog[, `:=`(
  merge_nationwide = fifelse(geometry_class %in% c("polygon", "point", "line") & schema_variant_count == 1L, "yes", "review"),
  expected_output_name = paste0("togieeum_", tolower(source_system), "_", tolower(layer_family)),
  expected_geometry_output = paste0("togieeum_", tolower(source_system), "_", tolower(layer_family), ".gpkg"),
  expected_attribute_output = paste0("togieeum_", tolower(source_system), "_", tolower(layer_family), "_attributes.parquet")
)]

catalog <- merge(catalog, table_labels[, .(source_system, layer_family = layer_family(layer_name), table_label_ko, metadata_file_type)], by = c("source_system", "layer_family"), all.x = TRUE)
setorder(catalog, source_system, layer_family)
setorder(inventory, source_system, source_zip, file_type, layer_name, archive_member)

arrow::write_parquet(inventory, inventory_out)
arrow::write_parquet(catalog, catalog_out)
write_report(report_out, inventory, catalog, klip_meta, upis_meta, csv_files, zip_files)

log_msg("Wrote", inventory_out)
log_msg("Wrote", catalog_out)
log_msg("Wrote", report_out)
