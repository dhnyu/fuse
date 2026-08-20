#!/usr/bin/env Rscript

required_packages <- c("targets", "visNetwork", "htmlwidgets")

script_path <- function() {
  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg)) return(normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE))
  normalizePath("tools/targets-network/render_targets_network.R", mustWork = TRUE)
}

parse_network_args <- function(args) {
  output <- list(
    output_dir = "artifacts/targets-network",
    focus = character(),
    degree = 1L
  )
  for (arg in args) {
    if (grepl("^--output-dir=", arg)) {
      output$output_dir <- sub("^--output-dir=", "", arg)
    } else if (grepl("^--focus=", arg)) {
      value <- sub("^--focus=", "", arg)
      output$focus <- unique(Filter(nzchar, trimws(strsplit(value, ",", fixed = TRUE)[[1L]])))
    } else if (grepl("^--degree=", arg)) {
      output$degree <- suppressWarnings(as.integer(sub("^--degree=", "", arg)))
    } else {
      stop("Unknown argument: ", arg, call. = FALSE)
    }
  }
  if (!nzchar(output$output_dir)) stop("--output-dir cannot be empty", call. = FALSE)
  if (is.na(output$degree) || output$degree < 0L) stop("--degree must be a non-negative integer", call. = FALSE)
  output
}

target_group <- function(names) {
  result <- rep("initialization", length(names))
  result[names == "seoul_data_preprocess"] <- "preprocessing"
  result[grepl("boundary|buffer400", names)] <- "boundary"
  result[grepl("building", names)] <- "buildings"
  result[grepl("road", names)] <- "roads"
  result[grepl("poi", names)] <- "pois"
  result[grepl("landcover|dem", names)] <- "rasters"
  result[grepl("subset_qc|data_manifest|report", names)] <- "validation"
  result
}

focus_network <- function(network, focus, degree) {
  unknown <- setdiff(focus, network$vertices$name)
  if (length(unknown)) stop("Unknown focus target(s): ", paste(unknown, collapse = ", "), call. = FALSE)
  selected <- unique(focus)
  if (degree > 0L) {
    for (step in seq_len(degree)) {
      adjacent <- network$edges$from[network$edges$to %in% selected]
      adjacent <- c(adjacent, network$edges$to[network$edges$from %in% selected])
      selected <- unique(c(selected, adjacent))
    }
  }
  list(
    vertices = network$vertices[network$vertices$name %in% selected, , drop = FALSE],
    edges = network$edges[network$edges$from %in% selected & network$edges$to %in% selected, , drop = FALSE]
  )
}

build_widget <- function(network, title) {
  nodes <- data.frame(
    id = network$vertices$name,
    label = network$vertices$name,
    group = target_group(network$vertices$name),
    title = sprintf(
      "<b>%s</b><br>status: %s<br>seconds: %s<br>bytes: %s",
      network$vertices$name,
      ifelse(is.na(network$vertices$status), "not recorded", network$vertices$status),
      ifelse(is.na(network$vertices$seconds), "not recorded", network$vertices$seconds),
      ifelse(is.na(network$vertices$bytes), "not recorded", format(network$vertices$bytes, scientific = FALSE))
    ),
    shape = "box",
    stringsAsFactors = FALSE
  )
  edges <- data.frame(
    from = network$edges$from,
    to = network$edges$to,
    arrows = rep("to", nrow(network$edges)),
    stringsAsFactors = FALSE
  )
  widget <- visNetwork::visNetwork(nodes, edges, main = title, width = "100%", height = "900px")
  palette <- c(
    preprocessing = "#0F766E",
    initialization = "#6B7280",
    boundary = "#0F766E",
    buildings = "#B45309",
    roads = "#1D4ED8",
    pois = "#7E22CE",
    rasters = "#15803D",
    validation = "#B91C1C"
  )
  for (group in names(palette)) {
    widget <- visNetwork::visGroups(widget, groupname = group, color = palette[[group]])
  }
  widget |>
    visNetwork::visEdges(smooth = list(enabled = TRUE, type = "cubicBezier", roundness = 0.25)) |>
    visNetwork::visOptions(
      highlightNearest = list(enabled = TRUE, degree = 1, hover = TRUE),
      nodesIdSelection = list(enabled = TRUE, useLabels = TRUE, main = "Target search")
    ) |>
    visNetwork::visHierarchicalLayout(direction = "LR", sortMethod = "directed", levelSeparation = 210) |>
    visNetwork::visPhysics(enabled = FALSE) |>
    visNetwork::visLegend(useGroups = TRUE, position = "right")
}

save_widget_atomic <- function(widget, output_file) {
  dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
  temporary <- tempfile(pattern = ".targets-network-", tmpdir = dirname(output_file), fileext = ".html")
  temporary_dependencies <- paste0(tools::file_path_sans_ext(temporary), "_files")
  on.exit({
    if (file.exists(temporary)) unlink(temporary)
    if (dir.exists(temporary_dependencies)) unlink(temporary_dependencies, recursive = TRUE)
  }, add = TRUE)
  htmlwidgets::saveWidget(widget, file = temporary, selfcontained = TRUE)
  if (!file.rename(temporary, output_file)) stop("Could not publish dependency HTML: ", output_file, call. = FALSE)
  normalizePath(output_file, mustWork = TRUE)
}

render_targets_network <- function(output_dir, focus = character(), degree = 1L) {
  network <- targets::tar_network(
    targets_only = TRUE,
    outdated = FALSE,
    callr_function = NULL
  )
  full_file <- file.path(output_dir, "targets-network.html")
  outputs <- save_widget_atomic(build_widget(network, "fuse targets dependency network"), full_file)
  if (length(focus)) {
    focused <- focus_network(network, focus, degree)
    slug <- paste(gsub("[^A-Za-z0-9_-]", "-", focus), collapse = "-")
    focused_file <- file.path(output_dir, paste0("targets-network-focus-", slug, ".html"))
    outputs <- c(outputs, save_widget_atomic(
      build_widget(focused, paste0("fuse targets near: ", paste(focus, collapse = ", "))),
      focused_file
    ))
  }
  outputs
}

main <- function() {
  missing <- required_packages[!vapply(required_packages, requireNamespace, logical(1L), quietly = TRUE)]
  if (length(missing)) stop("Missing package(s): ", paste(missing, collapse = ", "), call. = FALSE)
  project_root <- normalizePath(file.path(dirname(script_path()), "..", ".."), mustWork = TRUE)
  setwd(project_root)
  options <- parse_network_args(commandArgs(trailingOnly = TRUE))
  outputs <- render_targets_network(options$output_dir, options$focus, options$degree)
  message("Created dependency HTML:\n", paste0("- ", outputs, collapse = "\n"))
}

if (sys.nframe() == 0L) main()
