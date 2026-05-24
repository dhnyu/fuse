#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(sf)
  library(dplyr)
  library(arrow)
  library(leaflet)
  library(htmlwidgets)
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

admin_dir <- fuse_path("geodata", "koreanadm", must_exist = TRUE)
final_dir <- fuse_path("streetview", "final", create_parent = TRUE)
metadata_path <- file.path(final_dir, "gsv_seoul_metadata_final_40000.parquet")
map_path <- file.path(final_dir, "gsv_seoul_metadata_qc_map.html")

if (!file.exists(metadata_path)) {
  stop("Final metadata parquet does not exist: ", metadata_path, call. = FALSE)
}

PROJECTED_CRS <- 5179

read_admin <- function(filename) {
  st_read(file.path(admin_dir, filename), quiet = TRUE, options = "ENCODING=UTF-8")
}

label_points <- function(x, label_col) {
  x |>
    select(all_of(label_col)) |>
    st_transform(PROJECTED_CRS) |>
    st_point_on_surface() |>
    st_transform(4326)
}

sido <- read_admin("bnd_sido_00_2024_2Q.shp")
sigungu <- read_admin("bnd_sigungu_00_2024_2Q.shp")
dong <- read_admin("bnd_dong_00_2024_2Q.shp")
grid <- st_read(fuse_file("seoul_grid_500m", must_exist = TRUE), quiet = TRUE) |>
  st_transform(4326)

metadata <- read_parquet(metadata_path)
points <- st_as_sf(metadata, coords = c("lon", "lat"), crs = 4326, remove = FALSE)

seoul_sido <- sido |> filter(SIDO_NM == "서울특별시")
seoul_sigungu <- sigungu |> filter(substr(SIGUNGU_CD, 1, 2) == "11")
seoul_dong <- dong |> filter(substr(ADM_CD, 1, 2) == "11")
gwanak <- seoul_sigungu |> filter(SIGUNGU_NM == "관악구")

sido_map <- st_transform(sido, 4326)
sigungu_map <- st_transform(seoul_sigungu, 4326)
dong_map <- st_transform(seoul_dong, 4326)
grid_map <- grid
seoul_sido_map <- st_transform(seoul_sido, 4326)
gwanak_map <- st_transform(gwanak, 4326)

seoul_label <- label_points(seoul_sido, "SIDO_NM")
sigungu_labels <- label_points(seoul_sigungu, "SIGUNGU_NM")
dong_labels <- label_points(seoul_dong, "ADM_NM")

pal <- colorFactor(
  palette = c("#1f78b4", "#33a02c", "#ff7f00", "#6a3d9a", "#b15928", "#e31a1c"),
  domain = metadata$highway_class
)

m <- leaflet(options = leafletOptions(preferCanvas = TRUE, minZoom = 6)) |>
  addProviderTiles(providers$CartoDB.Positron, group = "Base") |>
  addPolygons(
    data = sido_map,
    group = "시도 경계",
    color = "#1f2937",
    weight = 2.2,
    fillOpacity = 0,
    opacity = 0.95,
    smoothFactor = 0,
    label = ~SIDO_NM
  ) |>
  addPolygons(
    data = sigungu_map,
    group = "시군구 경계",
    color = "#4b5563",
    weight = 1.35,
    fillOpacity = 0,
    opacity = 0.9,
    smoothFactor = 0,
    label = ~SIGUNGU_NM
  ) |>
  addPolygons(
    data = dong_map,
    group = "행정동 경계",
    color = "#9ca3af",
    weight = 0.55,
    fillOpacity = 0,
    opacity = 0.75,
    smoothFactor = 0,
    label = ~ADM_NM
  ) |>
  addPolygons(
    data = gwanak_map,
    group = "관악구 강조",
    color = "#dc2626",
    weight = 3.2,
    fillColor = "#ef4444",
    fillOpacity = 0.12,
    opacity = 1,
    smoothFactor = 0,
    label = ~SIGUNGU_NM
  ) |>
  addPolygons(
    data = grid_map,
    group = "500m grid",
    color = "#2563eb",
    weight = 0.45,
    fillOpacity = 0,
    opacity = 0.35,
    smoothFactor = 0
  ) |>
  addCircleMarkers(
    data = points,
    group = "Street View points",
    lng = ~lon,
    lat = ~lat,
    radius = 3.2,
    stroke = TRUE,
    color = "#111827",
    weight = 0.45,
    opacity = 0.8,
    fillColor = ~pal(highway_class),
    fillOpacity = 0.82,
    popup = ~paste0(
      "<b>point_id:</b> ", point_id,
      "<br><b>pano_id:</b> ", pano_id,
      "<br><b>구:</b> ", `시군구명`,
      "<br><b>동:</b> ", `행정동명`,
      "<br><b>capture_year:</b> ", capture_year,
      "<br><b>distance_m:</b> ", round(point_to_pano_distance_m, 2)
    )
  ) |>
  addLabelOnlyMarkers(
    data = seoul_label,
    group = "Labels",
    label = ~SIDO_NM,
    labelOptions = labelOptions(noHide = TRUE, direction = "center", textOnly = TRUE, textsize = "18px", style = list("font-weight" = "700", "color" = "#111827"))
  ) |>
  addLabelOnlyMarkers(
    data = sigungu_labels,
    group = "Labels",
    label = ~SIGUNGU_NM,
    labelOptions = labelOptions(noHide = TRUE, direction = "center", textOnly = TRUE, textsize = "12px", style = list("font-weight" = "600", "color" = "#374151"))
  ) |>
  addLabelOnlyMarkers(
    data = dong_labels,
    group = "Labels",
    label = ~ADM_NM,
    labelOptions = labelOptions(noHide = TRUE, direction = "center", textOnly = TRUE, textsize = "9px", style = list("font-weight" = "500", "color" = "#6b7280"))
  ) |>
  addLegend(
    position = "bottomright",
    pal = pal,
    values = metadata$highway_class,
    title = "Road class",
    opacity = 0.8
  ) |>
  addLayersControl(
    overlayGroups = c("시도 경계", "시군구 경계", "행정동 경계", "관악구 강조", "500m grid", "Street View points", "Labels"),
    options = layersControlOptions(collapsed = FALSE)
  ) |>
  fitBounds(
    lng1 = st_bbox(seoul_sido_map)[["xmin"]],
    lat1 = st_bbox(seoul_sido_map)[["ymin"]],
    lng2 = st_bbox(seoul_sido_map)[["xmax"]],
    lat2 = st_bbox(seoul_sido_map)[["ymax"]]
  )

saveWidget(m, map_path, selfcontained = TRUE)
cat("GSV metadata QC map written: ", map_path, "\n", sep = "")
