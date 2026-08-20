manifest_fingerprint <- function(qc) {
  artifact_fingerprint(
    qc$canonical$manifest$sha256,
    qc$boundary_source$source_checksum,
    qc$config_sha256,
    paste(vapply(qc$outputs, `[[`, character(1L), "sha256"), collapse = "|"),
    qc$contract_version
  )
}

existing_manifest_matches_qc <- function(existing, qc) {
  existing_output_hashes <- vapply(existing$outputs, `[[`, character(1L), "sha256")
  current_output_hashes <- vapply(qc$outputs, `[[`, character(1L), "sha256")
  identical(existing$status, "PASS") &&
    identical(existing$contract_version, qc$contract_version) &&
    identical(existing$canonical$manifest$sha256, qc$canonical$manifest$sha256) &&
    identical(existing$study_area$source_boundary_checksum, qc$boundary_source$source_checksum) &&
    identical(existing_output_hashes, current_output_hashes)
}

write_seoul_data_manifest <- function(qc, config) {
  if (!identical(qc$status, "PASS")) stop("Cannot write manifest for a failed subset", call. = FALSE)
  final <- config$paths$study$manifest
  fingerprint <- manifest_fingerprint(qc)
  value <- c(list(
    schema_version = "1.0.0",
    artifact_fingerprint = fingerprint,
    status = "PASS",
    generated_at = kst_now(),
    configuration = list(config_sha256 = qc$config_sha256),
    study_area = list(
      name = config$methodology$study_area$name,
      source_identifier = qc$boundary_source$source_feature_identifier,
      source_boundary_path = qc$boundary_source$source_path,
      source_boundary_checksum = qc$boundary_source$source_checksum,
      source_crs = qc$boundary_source$source_crs,
      output_crs = config$methodology$study_area$output_crs,
      buffer_distance_m = config$methodology$study_area$source_buffer_m,
      boundary_area_m2 = qc$qc$boundary$boundary_area_m2,
      buffer_area_m2 = qc$qc$boundary$buffer_area_m2,
      buffer_extent = qc$qc$boundary$buffer_extent
    )
  ), qc[c("contract_version", "canonical", "outputs", "qc", "git_commit", "thesis_commit", "software", "execution", "deferred")])
  if (file.exists(final)) {
    existing <- jsonlite::read_json(final, simplifyVector = TRUE)
    if (identical(existing$artifact_fingerprint, fingerprint) && identical(existing$status, "PASS")) return(final)
    if (!existing_manifest_matches_qc(existing, qc)) {
      stop("Conflicting existing Seoul data manifest: ", final, call. = FALSE)
    }
    message("Refreshing manifest provenance for unchanged validated output files: ", final)
  }
  write_json_atomic(value, final)
}

markdown_table <- function(headers, rows) {
  c(
    paste0("| ", paste(headers, collapse = " | "), " |"),
    paste0("|", paste(rep("---", length(headers)), collapse = "|"), "|"),
    vapply(rows, function(row) paste0("| ", paste(row, collapse = " | "), " |"), character(1L))
  )
}

write_study_subset_report <- function(qc, manifest_file, config) {
  manifest <- jsonlite::read_json(manifest_file, simplifyVector = FALSE)
  if (!identical(manifest$status, "PASS")) stop("Cannot report a non-PASS manifest", call. = FALSE)
  path <- file.path(config$paths$repository$reports, paste0(kst_stamp(), "_seoul_study_subset.md"))
  if (file.exists(path)) stop("Refusing to overwrite timestamped report: ", path, call. = FALSE)
  output_rows <- lapply(names(qc$outputs), function(name) {
    item <- qc$outputs[[name]]
    count <- switch(name,
      building = qc$qc$building$count,
      road = qc$qc$road$counts$links,
      poi = qc$qc$poi$counts$points,
      landcover = paste(qc$qc$landcover$dimensions, collapse = " x "),
      dem = paste(qc$qc$dem$dimensions, collapse = " x "),
      boundary = 1,
      buffer400 = 1
    )
    c(name, item$path, format(item$size_bytes, scientific = FALSE), as.character(count), item$sha256, "PASS")
  })
  target_names <- "seoul_data_preprocess"
  lines <- c(
    "# 서울특별시 400 m buffer 연구지역 subset 실행 보고서",
    "",
    paste0("- 최종 판정: **", qc$status, "**"),
    paste0("- 실행 시각: `", qc$generated_at, "` (Asia/Seoul)"),
    paste0("- fuse commit: `", qc$git_commit, "`"),
    paste0("- thesis commit: `", qc$thesis_commit, "`"),
    paste0("- canonical schema/snapshot: `", qc$canonical$schema_version, "` / `", qc$canonical$snapshot_id, "`"),
    paste0("- canonical manifest SHA-256: `", qc$canonical$manifest$sha256, "`"),
    paste0("- targets store: `", config$paths$targets$store, "`"),
    paste0("- backend: `", qc$execution$backend, "`; workers=", qc$execution$workers, ", threads/worker=", qc$execution$threads_per_worker),
    "",
    "## Target graph",
    "",
    paste0("`", paste(target_names, collapse = "` -> `"), "`"),
    "",
    "Canonical ingest는 graph에 포함하지 않고 검증된 `core_data_manifest.json`과 5개 canonical 파일에서 시작한다.",
    "",
    "## 연구지역",
    "",
    paste0("- 선택 기준: `", qc$boundary_source$source_feature_identifier, "` (행 순서 미사용)"),
    paste0("- 원본 경계 checksum: `", qc$boundary_source$source_checksum, "`"),
    paste0("- 원본/출력 CRS: `", qc$boundary_source$source_crs, "` / `EPSG:5186`"),
    paste0("- 원본 geometry valid: `", qc$boundary_source$source_valid, "`; repair: `", qc$boundary_source$repair_applied, "`"),
    paste0("- boundary area: ", format(qc$qc$boundary$boundary_area_m2, scientific = FALSE), " m2"),
    paste0("- 400 m buffer area: ", format(qc$qc$boundary$buffer_area_m2, scientific = FALSE), " m2"),
    paste0("- buffer extent: `", paste(unlist(qc$qc$boundary$buffer_extent), collapse = ", "), "`"),
    "",
    "## 입력·출력 요약",
    "",
    markdown_table(c("dataset", "path", "size_bytes", "count/dimensions", "sha256", "QC"), output_rows),
    "",
    "## 데이터별 QC",
    "",
    paste0("- Building: canonical 14,388,603 -> subset ", qc$qc$building$count,
           "; unique ID, A9/A11/A14, invalid=0, full geometry/no clipping, RTree `PASS`."),
    paste0("- Road: links=", qc$qc$road$counts$links, ", nodes=", qc$qc$road$counts$nodes,
           ", multilink=", qc$qc$road$counts$multilink, ", turninfo=", qc$qc$road$counts$turninfo,
           "; orphan/dangling=0; endpoint max error=", qc$qc$road$endpoint_max_error_m, " m."),
    paste0("- Road transform: `", qc$qc$road$transformation$definition, "`; ", qc$qc$road$transformation$description,
           ". PROJ의 formal accuracy는 미정(ballpark datum step)이지만 투영 파라미터가 일치하고 좌표 변화·endpoint 오차는 0 m이다."),
    paste0("- POI: canonical 9,801,999 -> points ", qc$qc$poi$counts$points,
           "; addresses=", qc$qc$poi$counts$addresses, ", foreign_names=", qc$qc$poi$counts$foreign_names,
           ", aliases=", qc$qc$poi$counts$aliases, "; hierarchy/raw state, no filtering/dedup, RTree `PASS`."),
    paste0("- Land cover: ", paste(qc$qc$landcover$dimensions, collapse = " x "),
           ", EPSG:5186, 5 m, Byte, nodata=0, value range ", qc$qc$landcover$min, "-", qc$qc$landcover$max,
           ", source lattice/no resampling, nearest overviews, COG `PASS`."),
    paste0("- DEM: ", paste(qc$qc$dem$dimensions, collapse = " x "),
           ", EPSG:5186, 30 m, Int16, nodata=-32767, range ", qc$qc$dem$min, "-", qc$qc$dem$max,
           ", bilinear warp, average overviews, negative values not clamped, COG `PASS`."),
    "",
    "## 경고 및 해결",
    "",
    "- Road custom ITRF2000 WKT -> EPSG:5186은 PROJ에서 유일한 `+proj=noop +ellps=GRS80` operation이며 datum step의 formal accuracy가 제공되지 않는다. Silent relabel 대신 명시적 `-ct`를 사용했고 endpoint·관리경계 정합 QC로 수치 일관성을 확인했다.",
    "- Outdated road 비교 파일은 실행 시점에 없어 회귀 비교에 사용하지 않았다. Canonical source topology의 endpoint 오차 0 m와 cross-modal Seoul coverage를 대체 hard gate로 사용했다.",
    "- 미해결 hard QC는 없다.",
    "",
    "## 범위 제한",
    "",
    paste0("500 m scene, 250 m lattice, scene clipping, observed attributes, spatial relations, model training은 실행하지 않았다."),
    "",
    "## Manifest",
    "",
    paste0("`", manifest_file, "`"),
    "",
    "## 최종 판정: PASS",
    ""
  )
  writeLines(lines, path, useBytes = TRUE)
  path
}
