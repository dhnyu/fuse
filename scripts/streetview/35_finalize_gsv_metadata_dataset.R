#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(sf)
  library(dplyr)
  library(arrow)
  library(readr)
})

find_repo_root_from <- function(start) {
  current <- normalizePath(start, winslash = "/", mustWork = TRUE)
  repeat {
    if (file.exists(file.path(current, "config", "paths.R"))) return(current)
    parent <- dirname(current)
    if (identical(parent, current)) stop("Could not locate repository root.", call. = FALSE)
    current <- parent
  }
}

script_arg <- grep("^--file=", commandArgs(FALSE), value = TRUE)
start_dir <- if (length(script_arg)) dirname(sub("^--file=", "", script_arg[1])) else getwd()
repo_root <- find_repo_root_from(start_dir)
source(file.path(repo_root, "config", "paths.R"))

sf_use_s2(FALSE)

target_count <- as.integer(Sys.getenv("GSV_FINAL_METADATA_TARGET_COUNT", "40000"))
admin_dir <- fuse_path("geodata", "koreanadm", must_exist = TRUE)
final_dir <- fuse_path("streetview", "final", create_parent = TRUE)
dir.create(final_dir, recursive = TRUE, showWarnings = FALSE)

accepted_path <- fuse_file("gsv_accepted_metadata", must_exist = TRUE)
candidate_path <- fuse_file("gsv_candidate_pool_parquet", must_exist = TRUE)
out_path <- file.path(final_dir, "gsv_seoul_metadata_final_40000.parquet")
qc_path <- file.path(final_dir, "gsv_seoul_metadata_final_40000_qc.csv")

read_admin <- function(filename) {
  path <- file.path(admin_dir, filename)
  if (!file.exists(path)) stop("Missing administrative layer: ", path, call. = FALSE)
  st_read(path, quiet = TRUE, options = "ENCODING=UTF-8") |>
    st_make_valid()
}

admin_join <- function(points, polygons, keep_cols, prefix) {
  polygons <- polygons |>
    select(all_of(keep_cols), geometry) |>
    st_transform(st_crs(points)) |>
    st_make_valid()

  hits <- st_intersects(points, polygons)
  hit_idx <- vapply(hits, function(x) if (length(x) > 0) x[[1]] else NA_integer_, integer(1))
  missing <- which(is.na(hit_idx))
  fallback_col <- paste0(prefix, "_join_fallback")
  joined <- points
  joined[[fallback_col]] <- FALSE

  if (length(missing) > 0) {
    hit_idx[missing] <- st_nearest_feature(points[missing, ], polygons)
    joined[[fallback_col]][missing] <- TRUE
  }
  attrs <- st_drop_geometry(polygons[hit_idx, keep_cols, drop = FALSE])
  for (col in keep_cols) {
    joined[[col]] <- attrs[[col]]
  }
  joined
}

accepted <- read_parquet(accepted_path)
candidates <- read_parquet(candidate_path) |>
  rename(
    point_id = candidate_id,
    point_lon = lon,
    point_lat = lat
  )

if (nrow(accepted) != target_count) {
  stop("Accepted metadata row count is ", nrow(accepted), "; expected ", target_count, ".", call. = FALSE)
}

final <- accepted |>
  left_join(candidates, by = c("candidate_id" = "point_id"), suffix = c("", "_candidate")) |>
  mutate(
    point_id = candidate_id,
    lon = coalesce(point_lon, source_lon),
    lat = coalesce(point_lat, source_lat),
    gsv_provider = if_else(grepl("Google", copyright, ignore.case = TRUE), "Google", NA_character_)
  ) |>
  select(
    point_id,
    candidate_id,
    candidate_rank,
    accepted_rank,
    grid_id,
    highway_class,
    sampled_rank,
    source_road_id,
    nearest_neighbor_distance,
    candidate_seed,
    candidate_spacing_m,
    candidate_min_spacing_m,
    lon,
    lat,
    source_lon,
    source_lat,
    pano_id,
    pano_lat,
    pano_lon,
    capture_date,
    capture_year,
    copyright,
    gsv_provider,
    point_to_pano_distance_m,
    retrieval_timestamp,
    http_status_code,
    content_type,
    metadata_url_without_key,
    error_message,
    raw_metadata_json,
    accepted
  )

points <- st_as_sf(final, coords = c("lon", "lat"), crs = 4326, remove = FALSE)
sido <- read_admin("bnd_sido_00_2024_2Q.shp")
sigungu <- read_admin("bnd_sigungu_00_2024_2Q.shp")
dong <- read_admin("bnd_dong_00_2024_2Q.shp")
target_crs <- st_crs(sido)
points_projected <- st_transform(points, target_crs)

joined <- points_projected |>
  admin_join(sido, c("SIDO_CD", "SIDO_NM"), "sido") |>
  admin_join(sigungu, c("SIGUNGU_CD", "SIGUNGU_NM"), "sigungu") |>
  admin_join(dong, c("ADM_CD", "ADM_NM"), "dong") |>
  st_drop_geometry() |>
  rename(
    `시도명` = SIDO_NM,
    `시군구명` = SIGUNGU_NM,
    `행정동명` = ADM_NM,
    sido_code = SIDO_CD,
    sigungu_code = SIGUNGU_CD,
    dong_code = ADM_CD
  )

qc <- tibble(
  metric = c(
    "row_count",
    "unique_pano_ids",
    "duplicate_pano_ids",
    "missing_coordinates",
    "missing_sido",
    "missing_sigungu",
    "missing_dong",
    "non_google_provider",
    "capture_year_before_2018",
    "pano_distance_gt_20m",
    "sido_join_fallback",
    "sigungu_join_fallback",
    "dong_join_fallback"
  ),
  value = c(
    nrow(joined),
    n_distinct(joined$pano_id),
    nrow(joined) - n_distinct(joined$pano_id),
    sum(is.na(joined$lon) | is.na(joined$lat)),
    sum(is.na(joined$`시도명`)),
    sum(is.na(joined$`시군구명`)),
    sum(is.na(joined$`행정동명`)),
    sum(joined$gsv_provider != "Google" | is.na(joined$gsv_provider)),
    sum(is.na(joined$capture_year) | joined$capture_year < 2018),
    sum(is.na(joined$point_to_pano_distance_m) | joined$point_to_pano_distance_m > 20),
    sum(joined$sido_join_fallback),
    sum(joined$sigungu_join_fallback),
    sum(joined$dong_join_fallback)
  )
)

hard_failures <- qc |>
  filter(metric %in% c(
    "duplicate_pano_ids",
    "missing_coordinates",
    "missing_sido",
    "missing_sigungu",
    "missing_dong",
    "non_google_provider",
    "capture_year_before_2018",
    "pano_distance_gt_20m"
  ), value != 0)

if (nrow(joined) != target_count || nrow(hard_failures) > 0) {
  print(qc)
  stop("Final metadata validation failed.", call. = FALSE)
}

write_parquet(joined, out_path, compression = "zstd")
write_csv(qc, qc_path)

cat("Final GSV metadata dataset written\n")
cat("rows: ", nrow(joined), "\n", sep = "")
cat("unique_pano_ids: ", n_distinct(joined$pano_id), "\n", sep = "")
cat("output: ", out_path, "\n", sep = "")
cat("qc: ", qc_path, "\n", sep = "")
