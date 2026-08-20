seoul_subset_task_names <- function() {
  c("building", "road", "poi", "landcover", "dem")
}

seoul_generated_output_paths <- function(config, report_file = NULL) {
  paths <- unname(unlist(config$paths$study[c(
    "boundary", "buffer400", "building", "road", "poi", "landcover", "dem", "manifest"
  )]))
  if (!is.null(report_file)) paths <- c(paths, report_file)
  paths
}

run_seoul_subset_task <- function(task, canonical_inputs, buffer_file, config, sqlite_helper, threads) {
  thread_state <- capture_native_thread_state()
  on.exit(restore_native_thread_state(thread_state), add = TRUE)
  set_native_thread_limits(threads)
  switch(
    task,
    building = subset_seoul_buildings(canonical_inputs, buffer_file, config),
    road = subset_seoul_roads(canonical_inputs, buffer_file, config, sqlite_helper),
    poi = subset_seoul_poi(canonical_inputs, buffer_file, config, sqlite_helper),
    landcover = subset_seoul_landcover(canonical_inputs, buffer_file, config, threads),
    dem = subset_seoul_dem(canonical_inputs, buffer_file, config, threads),
    stop("Unknown Seoul subset task: ", task, call. = FALSE)
  )
}

run_seoul_subset_tasks <- function(canonical_inputs, buffer_file, config, sqlite_helper, workers, threads) {
  tasks <- seoul_subset_task_names()
  expected <- unname(unlist(config$paths$study[tasks]))
  if (length(unique(expected)) != length(expected)) {
    stop("Independent subset tasks must write to distinct output files", call. = FALSE)
  }

  run_one <- function(task) {
    run_seoul_subset_task(task, canonical_inputs, buffer_file, config, sqlite_helper, threads)
  }
  if (workers == 1L) {
    results <- lapply(tasks, run_one)
  } else {
    previous_plan <- future::plan()
    on.exit(future::plan(previous_plan), add = TRUE)
    future::plan(future::multisession, workers = min(workers, length(tasks)))
    results <- future.apply::future_lapply(
      tasks,
      run_one,
      future.seed = TRUE,
      future.scheduling = 1
    )
  }
  names(results) <- tasks
  actual <- unname(unlist(results))
  if (!identical(actual, expected) || any(!file.exists(actual))) {
    stop("A Seoul subset task did not return its required output file", call. = FALSE)
  }
  results
}

preprocess_seoul_data <- function(workers = 5L, threads = 4L,
                                  paths_file = "config/paths.yml",
                                  methodology_file = "config/methodology.yml",
                                  sqlite_helper = "scripts/sqlite_subset.py") {
  specification <- fuse_parallel_spec(workers, threads)
  previous_plan <- future::plan()
  thread_state <- capture_native_thread_state()
  on.exit({
    future::plan(previous_plan)
    restore_native_thread_state(thread_state)
  }, add = TRUE)
  set_native_thread_limits(specification$threads)
  cat(sprintf(
    "[%s] target=seoul_data_preprocess crew_controller=controller_20 internal_workers=%d threads_per_worker=%d theoretical_maximum_cpu_cores=%d\n",
    kst_now(), specification$workers, specification$threads, specification$maximum_cores
  ))
  if (!file.exists(sqlite_helper)) stop("Missing SQLite subset helper: ", sqlite_helper, call. = FALSE)

  config <- load_pipeline_config(paths_file, methodology_file)
  config$methodology$runtime$workers <- specification$workers
  config$methodology$runtime$threads_per_worker <- specification$threads
  canonical_manifest <- read_canonical_manifest(config$paths$canonical$manifest)
  canonical_files <- unname(unlist(config$paths$canonical[c(
    "building", "road", "poi", "landcover", "dem"
  )]))
  canonical_inputs <- validate_canonical_inputs(canonical_manifest, canonical_files, config)

  boundary_files <- boundary_component_paths(config$paths$administrative$sido)
  boundary_source <- inspect_seoul_boundary_source(boundary_files, config, canonical_manifest)
  boundary_file <- create_seoul_boundary(boundary_source, config, canonical_manifest)
  buffer_file <- create_seoul_buffer(boundary_file, boundary_source, config, canonical_manifest)

  subsets <- run_seoul_subset_tasks(
    canonical_inputs = canonical_inputs,
    buffer_file = buffer_file,
    config = config,
    sqlite_helper = sqlite_helper,
    workers = specification$workers,
    threads = specification$threads
  )

  qc <- validate_seoul_subset(
    config,
    canonical_manifest,
    canonical_inputs,
    boundary_source,
    boundary_file,
    buffer_file,
    subsets$building,
    subsets$road,
    subsets$poi,
    subsets$landcover,
    subsets$dem
  )
  manifest_file <- write_seoul_data_manifest(qc, config)
  report_file <- write_study_subset_report(qc, manifest_file, config)
  outputs <- seoul_generated_output_paths(config, report_file)
  if (length(outputs) != 9L || any(!file.exists(outputs))) {
    stop("Seoul preprocessing did not produce all nine validated output files", call. = FALSE)
  }
  outputs
}
