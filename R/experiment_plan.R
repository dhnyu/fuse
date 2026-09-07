# Current dissertation experiment specification. Superseded P8 builders are
# intentionally absent from the executable source tree.
current_experiment_plan_sources <- function(root = ".", dissertation_root = path.expand("~/dhnyu-masters-dissertation")) {
  local <- c(
    "config/current_methodology.yml", "python/current_methodology.py",
    "config/schemas/current_experiment_plan.schema.json",
    "R/experiment_plan.R", "targets/s08_experiment_plan.R"
  )
  dissertation <- c(
    "template/sections/chapters/results/01-experimental-setup.typ",
    "template/sections/chapters/results/05-hyperparameter-study.typ",
    "template/sections/chapters/04-methodology-training.typ",
    "template/materials/tables/results-02-model-dimension-table.typ",
    "template/materials/tables/results-04-training-configuration-table.typ",
    "template/materials/tables/results-05-model-architecture-table.typ"
  )
  normalizePath(c(file.path(root, local), file.path(dissertation_root, dissertation)), mustWork = TRUE)
}

build_current_experiment_plan <- function(sources, root = ".") {
  expected <- current_experiment_plan_sources(root)
  if (!identical(normalizePath(sources, mustWork = TRUE), expected)) stop("Current experiment-plan source tracking mismatch", call. = FALSE)
  cfg <- yaml::read_yaml(file.path(root, "config/current_methodology.yml"))
  dissertation_head <- system2("git", c("-C", path.expand("~/dhnyu-masters-dissertation"), "rev-parse", "HEAD"), stdout = TRUE)
  if (!identical(dissertation_head[[1L]], cfg$dissertation_commit)) stop("Current experiment-plan dissertation commit mismatch", call. = FALSE)
  final_dir <- file.path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_plan", paste0("current_", substr(cfg$dissertation_commit, 1L, 16L)))
  output <- publish_deterministic_directory(final_dir, "current_experiment_plan.json", function(stage) {
    path <- file.path(stage, "current_experiment_plan.json")
    status <- system2(research_python_executable(), c(
      "-B", "python/current_methodology.py",
      "--config", shQuote(normalizePath(file.path(root, "config/current_methodology.yml"), mustWork = TRUE)),
      "--output", shQuote(path)
    ))
    if (!identical(status, 0L) || !file.exists(path)) stop("Current experiment-plan construction failed", call. = FALSE)
  })
  value <- jsonlite::read_json(output, simplifyVector = FALSE)
  validate_json_schema_file(output, file.path(root, "config/schemas/current_experiment_plan.schema.json"))
  if (!identical(value$status, "PASS") || length(value$hyperparameter_configurations) != 11L || length(value$comparison_configurations) != 17L) stop("Current experiment-plan validation failed", call. = FALSE)
  normalizePath(output, mustWork = TRUE)
}
