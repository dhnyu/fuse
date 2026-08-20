interval_overlap_matrix <- function(target_lower, target_upper, source_lower, source_upper) {
  value <- outer(target_upper, source_upper, pmin) - outer(target_lower, source_lower, pmax)
  value[value < 0] <- 0
  value
}

reference_scene_overlap <- function(source, scene, shape, modality, class_codes = 1:22,
                                    invalid_fill = -32767) {
  target <- scene_local_raster(scene, shape)
  local <- terra::crop(source, terra::ext(target), snap = "out")
  source_values <- terra::as.matrix(local, wide = TRUE)
  source_x_edges <- seq(terra::xmin(local), terra::xmax(local), length.out = terra::ncol(local) + 1L)
  source_y_edges <- seq(terra::ymax(local), terra::ymin(local), length.out = terra::nrow(local) + 1L)
  target_x_edges <- seq(as.numeric(scene$xmin), as.numeric(scene$xmax), length.out = as.integer(shape[[2L]]) + 1L)
  target_y_edges <- seq(as.numeric(scene$ymax), as.numeric(scene$ymin), length.out = as.integer(shape[[1L]]) + 1L)
  x_weight <- interval_overlap_matrix(
    head(target_x_edges, -1L), tail(target_x_edges, -1L),
    head(source_x_edges, -1L), tail(source_x_edges, -1L)
  )
  y_weight <- interval_overlap_matrix(
    tail(target_y_edges, -1L), head(target_y_edges, -1L),
    tail(source_y_edges, -1L), head(source_y_edges, -1L)
  )
  target_area <- (diff(range(target_x_edges)) / as.integer(shape[[2L]])) *
    (diff(range(target_y_edges)) / as.integer(shape[[1L]]))
  valid_source <- !is.na(source_values)
  valid_area <- y_weight %*% valid_source %*% t(x_weight)
  valid_ratio <- valid_area / target_area
  if (identical(modality, "landcover")) {
    support <- array(0, c(length(class_codes), as.integer(shape[[1L]]), as.integer(shape[[2L]])))
    for (index in seq_along(class_codes)) {
      support[index, , ] <- y_weight %*% (valid_source & source_values == class_codes[[index]]) %*% t(x_weight) / target_area
    }
    composition <- support
    for (index in seq_along(class_codes)) composition[index, , ] <- ifelse(valid_area > 0, support[index, , ] / valid_ratio, 0)
    return(list(composition = composition, valid_support_ratio = valid_ratio))
  }
  numerator <- y_weight %*% ifelse(valid_source, source_values, 0) %*% t(x_weight)
  value <- numerator / valid_area
  value[valid_area <= 0] <- invalid_fill
  list(value = value, valid_support_ratio = valid_ratio)
}
