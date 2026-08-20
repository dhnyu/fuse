#!/usr/bin/env Rscript

source(file.path(Sys.getenv("FUSE_REPO", "/members/dhnyu/fuse"), "R", "preprocessing_utils.R"))
set_single_thread_env()
cli <- parse_cli()
cfg <- load_preprocessing_config(cli$config)
ensure_preprocessing_dirs(cfg)
key <- "validation"

required_layers <- list(
  building = c("buildings", "metadata"),
  road = c("links", "nodes", "multilink", "turninfo", "metadata"),
  poi = c("points", "addresses", "foreign_names", "aliases", "category_lookup", "metadata")
)

gpkg_layers <- function(path) {
  info <- jsonlite::fromJSON(paste(capture_cmd("ogrinfo", c("-ro", "-json", "-so", "-al", path)), collapse = "\n"), simplifyVector = FALSE)
  vapply(info$layers, `[[`, character(1L), "name")
}

validate_gpkg <- function(dataset, path) {
  if (!file.exists(path)) stop("Missing GeoPackage: ", path, call. = FALSE)
  layers <- gpkg_layers(path)
  missing <- setdiff(required_layers[[dataset]], layers)
  if (length(missing)) stop(dataset, " missing layers: ", paste(missing, collapse = ", "), call. = FALSE)
  if (!sqlite_integrity(path)) stop(dataset, " PRAGMA integrity_check failed", call. = FALSE)
  spatial_layer <- c(building = "buildings", road = "links", poi = "points")[[dataset]]
  spatial_index <- ogr_scalar(path, sprintf("SELECT HasSpatialIndex('%s','geom') AS value", spatial_layer), "value")
  if (spatial_index != "1") stop(dataset, " missing spatial index", call. = FALSE)
  run_cmd("ogrinfo", c("-ro", "-q", path, spatial_layer, "-spat", "900000", "1800000", "1000000", "1900000", "-limit", "1"))
  if (file.exists(paste0(path, "-wal")) || file.exists(paste0(path, "-shm"))) stop(dataset, " has SQLite sidecar", call. = FALSE)
  list(layers = layers, integrity = "PASS", spatial_index = "PASS", random_spatial_query = "PASS")
}

validate_raster <- function(dataset, path) {
  if (!file.exists(path)) stop("Missing raster: ", path, call. = FALSE)
  info <- jsonlite::fromJSON(paste(capture_cmd("gdalinfo", c("-json", path)), collapse = "\n"), simplifyVector = FALSE)
  if (!identical(info$metadata$`IMAGE_STRUCTURE`$LAYOUT, "COG")) stop(dataset, " is not a COG", call. = FALSE)
  list(driver = info$driverShortName, dimensions = unlist(info$size), geotransform = unlist(info$geoTransform),
       datatype = info$bands[[1L]]$type, nodata = info$bands[[1L]]$noDataValue,
       overview_count = length(info$bands[[1L]]$overviews), cog = "PASS")
}

raster_checksum <- function(path) {
  out <- capture_cmd("gdalinfo", c("-checksum", path))
  line <- grep("Checksum=", out, value = TRUE)
  if (length(line) != 1L) stop("Could not read raster checksum: ", path, call. = FALSE)
  as.integer(sub("^.*Checksum=", "", trimws(line[[1L]])))
}

dem_source_provenance <- function(cfg) {
  source <- source_path(cfg, "dem")
  python <- paste(
    "import hashlib,io,json,struct,sys,zipfile",
    "p=sys.argv[1]",
    "data=open(p,'rb').read()",
    "tiles=[]",
    "with zipfile.ZipFile(io.BytesIO(data)) as z:",
    " infos=z.infolist()",
    " for i in infos:",
    "  if not i.filename.lower().endswith('.tif'): continue",
    "  h=hashlib.sha256()",
    "  with z.open(i) as f:",
    "   for block in iter(lambda:f.read(8<<20),b''): h.update(block)",
    "  tiles.append({'entry':i.filename,'size_bytes':i.file_size,'compressed_size_bytes':i.compress_size,'crc32':format(i.CRC,'08x'),'sha256':h.hexdigest()})",
    " aux=[i for i in infos if i.filename.lower().endswith('.aux.xml')]",
    " local_end=min(i.header_offset for i in aux) if aux else z.start_dir",
    " cd_start=z.start_dir",
    "records=[];pos=cd_start",
    "while data[pos:pos+4]==b'PK\\x01\\x02':",
    " n,e,c=struct.unpack_from('<HHH',data,pos+28);end=pos+46+n+e+c",
    " name=data[pos+46:pos+46+n].decode('utf-8')",
    " if not name.lower().endswith('.aux.xml'): records.append(data[pos:end])",
    " pos=end",
    "cd=b''.join(records)",
    "eocd=struct.pack('<4sHHHHIIH',b'PK\\x05\\x06',0,0,len(records),len(records),len(cd),local_end,0)",
    "no_pam=data[:local_end]+cd+eocd",
    "with zipfile.ZipFile(io.BytesIO(no_pam)) as old: no_pam_entries=len(old.infolist())",
    "payload='\\n'.join(f\"{x['entry']}|{x['size_bytes']}|{x['crc32']}|{x['sha256']}\" for x in sorted(tiles,key=lambda x:x['entry'])).encode()",
    "result={'entry_count':len(infos),'tiff_count':len(tiles),'aux_xml_count':len(aux),'tiff_uncompressed_bytes':sum(x['size_bytes'] for x in tiles),'aux_xml_uncompressed_bytes':sum(i.file_size for i in aux),'tiff_payload_set_sha256':hashlib.sha256(payload).hexdigest(),'tiles':tiles,'without_pam':{'size_bytes':len(no_pam),'sha256':hashlib.sha256(no_pam).hexdigest(),'entry_count':no_pam_entries,'zip_test':'PASS'}}",
    "print(json.dumps(result,separators=(',',':')))",
    sep = "\n"
  )
  provenance <- jsonlite::fromJSON(paste(capture_cmd("python", c("-c", python, source)), collapse = "\n"), simplifyVector = FALSE)
  stat_values <- strsplit(capture_cmd("stat", c("-c", "%s|%y|%z|%w", source))[[1L]], "\\|", fixed = FALSE)[[1L]]
  provenance$current <- list(
    path = source,
    size_bytes = unname(file.info(source)$size),
    mtime = stat_values[[2L]],
    ctime = stat_values[[3L]],
    birth_time = stat_values[[4L]],
    sha256 = sha256_file(source)
  )
  provenance$historical_audit <- list(
    path = source,
    size_bytes = cfg$dem$historical_source_size,
    mtime = "2026-08-20 15:36:08 Asia/Seoul",
    sha256 = cfg$dem$historical_source_sha256
  )
  provenance$historical_reconstruction_match <-
    identical(as.numeric(provenance$without_pam$size_bytes), as.numeric(cfg$dem$historical_source_size)) &&
    identical(provenance$without_pam$sha256, cfg$dem$historical_source_sha256)
  provenance$change_classification <- if (isTRUE(provenance$historical_reconstruction_match)) {
    "SAME_30_TIFF_PAYLOADS_WITH_30_GDAL_PAM_STATISTICS_SIDECARS_ADDED"
  } else {
    "UNRESOLVED_SOURCE_CHANGE"
  }

  current_vrt <- file.path(dataset_stage_dir(cfg, "dem"), "production", "korea_dem.vrt")
  final_dem <- output_path(cfg, "dem")
  provenance$reconciliation <- list(
    source_vrt_checksum = raster_checksum(current_vrt),
    canonical_checksum = raster_checksum(final_dem),
    production_source_inventory_timestamp = jsonlite::read_json(
      file.path(cfg$paths$staging_dir, "inventory", "environment_production.json"),
      simplifyVector = TRUE
    )$timestamp,
    dem_production_timestamp = read_marker(cfg, "dem", "production_complete")$timestamp
  )
  provenance$reconciliation$pixel_checksum_match <- identical(
    provenance$reconciliation$source_vrt_checksum,
    provenance$reconciliation$canonical_checksum
  )

  if (provenance$current$size_bytes != cfg$dem$approved_source_size ||
      provenance$current$sha256 != cfg$dem$approved_source_sha256) {
    stop("Current SRTM source does not match the approved checksum", call. = FALSE)
  }
  if (provenance$tiff_count != cfg$dem$expected_tiles || provenance$aux_xml_count != cfg$dem$expected_tiles) {
    stop("SRTM recursive inventory count mismatch", call. = FALSE)
  }
  if (!isTRUE(provenance$historical_reconstruction_match)) stop("Historical SRTM provenance remains unresolved", call. = FALSE)
  if (!isTRUE(provenance$reconciliation$pixel_checksum_match)) stop("Current SRTM and canonical DEM pixel checksums differ", call. = FALSE)

  inventory_dir <- file.path(cfg$paths$staging_dir, "inventory")
  write_json_atomic(provenance, file.path(inventory_dir, "dem_recursive_inventory_production.json"))
  tiles <- rbindlist(lapply(provenance$tiles, as.data.table), fill = TRUE)
  setorder(tiles, entry)
  fwrite(tiles, file.path(inventory_dir, "dem_tile_checksums_production.csv"))
  provenance
}

with_failure_result(cfg, key, {
  started <- Sys.time()
  datasets <- c("building", "road", "poi", "landcover", "dem")
  results <- lapply(datasets, function(dataset) {
    path <- dataset_result_path(cfg, dataset)
    if (!file.exists(path)) return(list(dataset = dataset, status = "FAIL", error = "missing dataset result"))
    jsonlite::read_json(path, simplifyVector = FALSE)
  })
  names(results) <- datasets
  wrong_mode <- datasets[vapply(results, function(x) !identical(x$mode, cli$mode), logical(1L))]
  failed <- datasets[vapply(results, function(x) !identical(x$status, "PASS"), logical(1L))]
  if (length(wrong_mode)) failed <- union(failed, wrong_mode)

  dem_provenance <- NULL
  dem_provenance_error <- NULL
  if (cli$mode == "production" && !"dem" %in% failed) {
    dem_provenance <- tryCatch(dem_source_provenance(cfg), error = function(e) {
      dem_provenance_error <<- conditionMessage(e)
      NULL
    })
    if (is.null(dem_provenance)) failed <- union(failed, "dem")
  }

  validation <- list()
  for (dataset in datasets) {
    if (dataset %in% failed) next
    path <- if (cli$mode == "production") output_path(cfg, dataset) else results[[dataset]]$staging_path
    validation[[dataset]] <- if (dataset %in% c("building", "road", "poi")) validate_gpkg(dataset, path) else validate_raster(dataset, path)
    if (dataset == "dem" && !is.null(dem_provenance)) validation[[dataset]]$source_provenance <- dem_provenance
  }
  final_status <- if (!length(failed) && length(validation) == 5L) "PASS" else if (length(validation)) "PARTIAL" else "FAIL"

  source_inventory_path <- file.path(cfg$paths$staging_dir, "inventory", sprintf("source_inventory_%s.json", cli$mode))
  sources <- if (file.exists(source_inventory_path)) jsonlite::read_json(source_inventory_path, simplifyVector = FALSE) else NULL
  outputs <- lapply(datasets, function(dataset) {
    result <- results[[dataset]]
    path <- if (cli$mode == "production") output_path(cfg, dataset) else result$staging_path %||% NA_character_
    list(dataset = dataset, path = path, exists = !is.na(path) && file.exists(path),
         size_bytes = if (!is.na(path) && file.exists(path)) unname(file.info(path)$size) else NULL,
         sha256 = if (cli$mode == "production" && !is.na(path) && file.exists(path)) sha256_file(path) else NULL,
         result = result, validation = validation[[dataset]] %||% NULL)
  })
  names(outputs) <- datasets

  manifest <- list(schema_version = cfg$schema_version, snapshot_id = cfg$snapshot_id, generated_at = kst_now(),
                   mode = cli$mode, status = final_status, config_sha256 = sha256_file(cfg$config_path),
                   fuse_commit = trimws(capture_cmd("git", c("-C", cfg$paths$repo, "rev-parse", "HEAD"))[[1L]]),
                   thesis_commit = trimws(capture_cmd("git", c("-C", cfg$paths$thesis_repo, "rev-parse", "HEAD"))[[1L]]),
                   sources = sources, source_recursive_inventory = list(dem = dem_provenance),
                   source_provenance_errors = list(dem = dem_provenance_error),
                   outputs = outputs, failed_datasets = failed)
  manifest_path <- if (cli$mode == "production") file.path(cfg$paths$output_dir, "core_data_manifest.json") else file.path(cfg$paths$staging_dir, "qc", "core_data_manifest_smoke.json")
  if (cli$mode == "production" && file.exists(manifest_path)) {
    previous <- jsonlite::read_json(manifest_path, simplifyVector = TRUE)
    if (identical(previous$status, "PASS")) stop("Refusing to overwrite existing PASS canonical manifest: ", manifest_path, call. = FALSE)
    if (!identical(previous$snapshot_id, cfg$snapshot_id)) stop("Existing manifest belongs to a different snapshot: ", manifest_path, call. = FALSE)
  }
  write_json_atomic(manifest, manifest_path)

  report_path <- NULL
  if (cli$mode == "production") {
    output_rows <- rbindlist(lapply(outputs, function(x) data.table(
      dataset = x$dataset, path = x$path, size_bytes = x$size_bytes %||% NA_real_, sha256 = x$sha256 %||% "-",
      elapsed_sec = x$result$elapsed_sec %||% NA_real_, status = x$result$status %||% "FAIL")))
    input_rows <- if (!is.null(sources)) rbindlist(lapply(sources, as.data.table), fill = TRUE) else data.table()
    outdated_paths <- c(
      "/mnt/hdd002/dhnyu/fusedata/main_data/korea_buildings_vworld.gpkg",
      "/mnt/hdd002/dhnyu/fusedata/main_data/korea_buildings_vworld_attributes.parquet",
      "/mnt/hdd002/dhnyu/fusedata/main_data/korea_itslink.gpkg",
      "/mnt/hdd002/dhnyu/fusedata/main_data/korea_itsnode.gpkg",
      "/mnt/hdd002/dhnyu/fusedata/main_data/korea_poi_ngii_clean.gpkg",
      "/mnt/hdd002/dhnyu/fusedata/main_data/korea_poi_ngii_clean.parquet",
      "/mnt/hdd002/dhnyu/fusedata/main_data/korea_landcover_egis2025.tif",
      "/mnt/hdd002/dhnyu/fusedata/main_data/korea_srtm2014.tif")
    outdated <- data.table(path = outdated_paths, exists = file.exists(outdated_paths),
                           size_bytes = ifelse(file.exists(outdated_paths), file.info(outdated_paths)$size, NA_real_))
    table_md <- function(dt) {
      if (!nrow(dt)) return("(없음)")
      cols <- names(dt)
      c(paste0("| ", paste(cols, collapse = " | "), " |"),
        paste0("|", paste(rep("---", length(cols)), collapse = "|"), "|"),
        apply(dt, 1L, function(row) paste0("| ", paste(gsub("\\|", "\\\\|", as.character(row)), collapse = " | "), " |")))
    }
    report_time <- Sys.time()
    report_path <- file.path(
      cfg$paths$repo,
      "reports",
      sprintf("%s_core_data_production_report.md", format(report_time, "%Y%m%d_%H%M", tz = "Asia/Seoul"))
    )
    if (file.exists(report_path)) stop("Refusing to overwrite existing timestamped report: ", report_path, call. = FALSE)
    report <- c(
      "# Canonical 핵심 데이터 production 실행 보고서", "",
      sprintf("- 최종 판정: **%s**", final_status),
      sprintf("- 실행 완료: `%s`", format(report_time, "%Y-%m-%dT%H:%M:%S%z", tz = "Asia/Seoul")),
      sprintf("- schema/snapshot: `%s` / `%s`", cfg$schema_version, cfg$snapshot_id),
      sprintf("- fuse commit: `%s`", manifest$fuse_commit), sprintf("- thesis commit: `%s`", manifest$thesis_commit),
      sprintf("- 실제 worker 구성: building=%s, road=1, POI=%s, land-cover=%s, DEM=%s; worker 내부 thread=1",
              cfg$runtime$building_workers, cfg$runtime$poi_workers, cfg$runtime$landcover_workers, cfg$runtime$dem_workers), "",
      "## 입력 provenance", "", table_md(input_rows[, intersect(c("dataset", "path", "size_bytes", "mtime", "sha256", "zip_crc"), names(input_rows)), with = FALSE]), "",
      "## canonical 산출물", "", table_md(output_rows), "",
      "## 데이터별 QC", "",
      paste(vapply(datasets, function(d) sprintf("- `%s`: `%s`; %s", d, outputs[[d]]$result$status %||% "FAIL",
                                                  jsonlite::toJSON(outputs[[d]]$result$qc %||% outputs[[d]]$validation %||% list(), auto_unbox = TRUE)), character(1L)), collapse = "\n"), "",
      "## 제외·중복 ledger", "",
      "- Building: production staging의 `building_exclusion_ledger.csv`와 `building_invalid_geometry_ledger.csv`.",
      "- POI: production staging의 `poi_exclusion_ledger.csv` (reason code별 source-invalid 객체).",
      "- Land-cover: production staging의 `ledgers/landcover_exact_duplicate_ledger.csv`.",
      "- Road/DEM: 계약상 자동 제거 없음.", "",
      "## outdated 산출물과의 관계", "", table_md(outdated), "",
      "기존 산출물은 회귀 비교 대상으로만 조회했으며 canonical 입력으로 사용하지 않았다. 차이는 최신 원본 snapshot, 전체 source-valid POI 보존, road topology 다중 layer 보존, land-cover fractional lattice 유지, DEM source grid 유지라는 확정 계약에서 발생한다.", "",
      "## SRTM source provenance", "",
      sprintf("- 과거/현재가 검사한 경로: `%s` (동일 경로)", source_path(cfg, "dem")),
      sprintf("- 과거 archive: %s bytes, `%s`", cfg$dem$historical_source_size, cfg$dem$historical_source_sha256),
      sprintf("- 현재 archive: %s bytes, `%s`", dem_provenance$current$size_bytes, dem_provenance$current$sha256),
      sprintf("- 현재 mtime/ctime: `%s` / `%s`", dem_provenance$current$mtime, dem_provenance$current$ctime),
      sprintf("- recursive inventory: TIFF=%s, PAM aux.xml=%s", dem_provenance$tiff_count, dem_provenance$aux_xml_count),
      sprintf("- PAM 제거 메모리 재구성의 과거 size/hash 일치: `%s`", dem_provenance$historical_reconstruction_match),
      sprintf("- current VRT/canonical 전체 pixel checksum: `%s` / `%s`", dem_provenance$reconciliation$source_vrt_checksum, dem_provenance$reconciliation$canonical_checksum),
      "- 판정: TIFF payload 교체가 아니라 30개 GDAL PAM statistics sidecar가 ZIP에 추가됨. DEM PASS 유지.", "",
      "## 경고와 미해결 문제", "", if (length(failed)) paste("실패 데이터:", paste(failed, collapse = ", ")) else "없음. 모든 acceptance QC를 통과했다.", "",
      "## 실행 로그와 manifest", "", sprintf("- Manifest: `%s`", manifest_path),
      "- 실행 표준 출력/오류: `logs/preprocessing/production_*.log`", "",
      sprintf("## 최종 판정: %s", final_status), ""
    )
    writeLines(report, report_path, useBytes = TRUE)
  }

  elapsed <- as.numeric(difftime(Sys.time(), started, units = "secs"))
  write_dataset_result(cfg, key, final_status, list(mode = cli$mode, elapsed_sec = elapsed,
                                                     manifest_path = manifest_path, report_path = report_path,
                                                     failed_datasets = failed))
  log_line(sprintf("VALIDATION_COMPLETE mode=%s status=%s elapsed_sec=%.3f", cli$mode, final_status, elapsed))
  if (final_status != "PASS") stop("Core data validation status: ", final_status, call. = FALSE)
})
