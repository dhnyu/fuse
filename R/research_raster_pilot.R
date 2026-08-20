raster_pilot_task <- function(task, plans, vectors, study_data_inputs, config) {
  thread_state <- raster_thread_state()
  on.exit(restore_raster_threads(thread_state), add = TRUE)
  set_raster_threads(1L)
  started <- Sys.time()
  io_start <- proc_io_snapshot()
  error <- NULL
  result <- tryCatch({
    spec <- plans[[task$plan_index]]
    vector_paths <- vectors[[task$plan_index]]
    files <- setNames(c(
      artifact_path(vector_paths, "building_observed.parquet"),
      artifact_path(vector_paths, "road_observed.parquet"),
      artifact_path(vector_paths, "poi_observed.parquet")
    ), c("building", "road", "poi"))
    read_started <- Sys.time()
    observations <- lapply(files, function(path) {
      value <- read_standard_geoparquet(path)
      value[value$scene_id == task$scene_id, ]
    })
    landcover <- terra::rast(study_raster_path(study_data_inputs, "seoul_lc.tif"))
    dem <- terra::rast(study_raster_path(study_data_inputs, "seoul_dem.tif"))
    read_seconds <- as.numeric(difftime(Sys.time(), read_started, units = "secs"))
    scene <- spec$scenes[[match(task$scene_id, vapply(spec$scenes, `[[`, character(1L), "scene_id"))]]
    landcover_started <- Sys.time()
    scene_landcover <- scene_landcover_observation(landcover, scene, config)
    landcover_seconds <- as.numeric(difftime(Sys.time(), landcover_started, units = "secs"))
    dem_started <- Sys.time()
    scene_dem <- scene_dem_observation(dem, scene, config)
    dem_seconds <- as.numeric(difftime(Sys.time(), dem_started, units = "secs"))
    context_started <- Sys.time()
    context <- build_object_raster_context(
      observations, landcover, dem, spec$observation_dataset_id, "pilot", config
    )
    context_seconds <- as.numeric(difftime(Sys.time(), context_started, units = "secs"))
    validate_object_context(context, observations, config)
    directory <- tempfile("i11-raster-pilot-")
    dir.create(directory)
    on.exit(if (dir.exists(directory)) unlink(directory, recursive = TRUE), add = TRUE)
    zarr_started <- Sys.time()
    landcover_metadata <- write_zarr_store(list(
      class_fraction = list(value = array(scene_landcover$composition, c(1, dim(scene_landcover$composition))), dtype = "float32", fill_value = -1),
      valid_support_ratio = list(value = array(scene_landcover$valid_support_ratio, c(1, 100, 100)), dtype = "float32", fill_value = -1),
      valid_mask = list(value = array(scene_landcover$valid_mask, c(1, 100, 100)), dtype = "uint8", fill_value = 255)
    ), file.path(directory, "landcover.zarr"), list(scene_ids = list(task$scene_id)), config)
    dem_metadata <- write_zarr_store(list(
      raw_mean_m = list(value = array(scene_dem$value, c(1, 17, 17)), dtype = "float32", fill_value = -32767),
      valid_support_ratio = list(value = array(scene_dem$valid_support_ratio, c(1, 17, 17)), dtype = "float32", fill_value = -1),
      valid_mask = list(value = array(scene_dem$valid_mask, c(1, 17, 17)), dtype = "uint8", fill_value = 255)
    ), file.path(directory, "dem.zarr"), list(scene_ids = list(task$scene_id)), config)
    zarr_seconds <- as.numeric(difftime(Sys.time(), zarr_started, units = "secs"))
    parquet_started <- Sys.time()
    context_path <- file.path(directory, "context.parquet")
    arrow::write_parquet(context, context_path, compression = "zstd")
    parquet_seconds <- as.numeric(difftime(Sys.time(), parquet_started, units = "secs"))
    raw_bytes <- length(scene_landcover$composition) * 4 + length(scene_landcover$valid_support_ratio) * 4 +
      length(scene_landcover$valid_mask) + length(scene_dem$value) * 4 +
      length(scene_dem$valid_support_ratio) * 4 + length(scene_dem$valid_mask)
    list(
      rows = nrow(context), source_read_seconds = read_seconds,
      landcover_seconds = landcover_seconds, dem_seconds = dem_seconds,
      object_context_seconds = context_seconds, zarr_write_seconds = zarr_seconds,
      parquet_write_seconds = parquet_seconds, raw_bytes = raw_bytes,
      output_bytes = landcover_metadata$size_bytes + dem_metadata$size_bytes + unname(file.info(context_path)$size)
    )
  }, error = function(condition) {
    error <<- conditionMessage(condition)
    list(rows = NA_integer_)
  })
  io_end <- proc_io_snapshot()
  c(list(
    scene_id = task$scene_id, cost = task$cost,
    wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
    max_rss_kb = proc_max_rss_kb(), read_bytes = io_end$read_bytes - io_start$read_bytes,
    write_bytes = io_end$write_bytes - io_start$write_bytes, error = error
  ), result)
}

benchmark_raster_concurrency <- function(plans, vectors, study_data_inputs, config,
                                         concurrency = c(5L, 10L), task_count = 10L) {
  records <- data.table::rbindlist(lapply(seq_along(plans), function(index) {
    data.table::rbindlist(lapply(plans[[index]]$scenes, function(scene) data.table::data.table(
      plan_index = index, scene_id = scene$scene_id, cost = scene$estimated_cost
    )))
  }))
  data.table::setorder(records, cost, scene_id)
  positions <- unique(as.integer(round(seq(1, nrow(records), length.out = task_count))))
  tasks <- split(records[positions], seq_along(positions))
  runs <- lapply(as.integer(concurrency), function(workers) {
    iowait_start <- proc_iowait_ticks()
    started <- Sys.time()
    values <- parallel::mclapply(
      tasks, raster_pilot_task, plans = plans, vectors = vectors,
      study_data_inputs = study_data_inputs, config = config,
      mc.cores = workers, mc.preschedule = FALSE
    )
    table <- data.table::rbindlist(values, fill = TRUE)
    list(
      workers = workers, task_count = length(tasks),
      wall_time_seconds = as.numeric(difftime(Sys.time(), started, units = "secs")),
      max_worker_rss_kb = max(table$max_rss_kb, na.rm = TRUE),
      read_bytes = sum(table$read_bytes, na.rm = TRUE), write_bytes = sum(table$write_bytes, na.rm = TRUE),
      iowait_ticks = proc_iowait_ticks() - iowait_start,
      errors = sum(vapply(values, function(value) !is.null(value$error), logical(1L))),
      landcover_seconds = sum(table$landcover_seconds, na.rm = TRUE),
      dem_seconds = sum(table$dem_seconds, na.rm = TRUE),
      object_context_seconds = sum(table$object_context_seconds, na.rm = TRUE),
      zarr_write_seconds = sum(table$zarr_write_seconds, na.rm = TRUE),
      parquet_write_seconds = sum(table$parquet_write_seconds, na.rm = TRUE),
      rows = sum(table$rows, na.rm = TRUE), raw_bytes = sum(table$raw_bytes, na.rm = TRUE),
      output_bytes = sum(table$output_bytes, na.rm = TRUE), task_results = values
    )
  })
  list(
    benchmark_schema_version = "1.0.0", generated_at = kst_now(),
    page_cache = "uncontrolled_warm_cache_no_drop_caches", tasks = tasks, runs = runs
  )
}
