network_script <- file.path(fuse_test_root, "tools/targets-network/render_targets_network.R")
source(network_script, local = TRUE)

synthetic_phase_config <- function(exact = list(Foundation = "a"), rules = list()) {
  ids <- c("Foundation", paste0("P", 1:9))
  list(
    phase_ids = ids,
    phase_colors = stats::setNames(rep("#475569", length(ids)), ids),
    exact = exact,
    rules = rules
  )
}

synthetic_snapshot <- function() {
  manifest <- data.frame(
    name = c("a", "b", "c"), format = c("rds", "file", "rds"),
    stringsAsFactors = FALSE
  )
  list(
    manifest = manifest,
    vertices = data.frame(name = manifest$name),
    edges = data.frame(from = c("a", "b"), to = c("b", "c")),
    metadata = data.frame(
      name = manifest$name, seconds = c(1, 2, NA), bytes = c(10, 20, NA),
      time = as.POSIXct(c("2026-01-01", "2026-01-02", NA), tz = "UTC"),
      error = c(NA, NA, "<script>alert('x')</script>"), warnings = NA_character_
    ),
    progress = data.frame(name = character(), progress = character()),
    outdated = "b", errored = character(), running = character(),
    status = c("up_to_date", "outdated", "up_to_date")
  )
}

test_that("target network options and focus selection are deterministic", {
  options <- parse_network_args(c("--focus=a,b", "--degree=2", "--output-dir=out", "--phases=phases.yml"))
  expect_equal(options$focus, c("a", "b"))
  expect_equal(options$degree, 2L)
  expect_equal(options$output_dir, "out")
  expect_equal(options$phases, "phases.yml")

  network <- list(
    vertices = data.frame(name = c("a", "b", "c", "d")),
    edges = data.frame(from = c("a", "b", "c"), to = c("b", "c", "d"))
  )
  focused <- focus_network(network, "b", 1L)
  expect_setequal(focused$vertices$name, c("a", "b", "c"))
  expect_equal(focused$edges, data.frame(from = c("a", "b"), to = c("b", "c")))
  expect_error(focus_network(network, "missing", 1L), "Unknown focus target")
})

test_that("status precedence and outdated classification are exact", {
  names <- c("clean", "old", "live", "bad")
  expect_equal(
    resolve_target_status(names, outdated = c("old", "live", "bad"), running = c("live", "bad"), errored = "bad"),
    c("up_to_date", "outdated", "running", "error")
  )
})

test_that("Phase exact overrides precede rules and invalid mappings fail closed", {
  config <- synthetic_phase_config(
    exact = list(P8 = "p8_exact"),
    rules = list(list(phase = "P9", pattern = "^p", future = FALSE))
  )
  expect_equal(assign_target_phases(c("p8_exact", "p9_rule"), config), c(p8_exact = "P8", p9_rule = "P9"))

  duplicate <- synthetic_phase_config(exact = list(P8 = "same", P9 = "same"))
  expect_error(assign_target_phases("same", duplicate), "multiple exact Phases")

  overlap <- synthetic_phase_config(
    exact = list(), rules = list(
      list(phase = "P8", pattern = "^shared", future = FALSE),
      list(phase = "P9", pattern = "shared$", future = FALSE)
    )
  )
  expect_error(assign_target_phases("shared", overlap), "multiple Phase rules")
  expect_error(assign_target_phases("unknown", synthetic_phase_config(exact = list())), "Unmapped current targets")
})

test_that("future Phase rules may be unmatched but current rules may not", {
  future <- synthetic_phase_config(
    exact = list(Foundation = "a"),
    rules = list(list(phase = "P9", pattern = "^future_", future = TRUE))
  )
  expect_equal(assign_target_phases("a", future), c(a = "Foundation"))
  current <- future
  current$rules[[1]]$future <- FALSE
  expect_error(assign_target_phases("a", current), "matches no current target")
})

test_that("node type shapes and deterministic edge direction are stable", {
  snapshot <- synthetic_snapshot()
  phases <- synthetic_phase_config(exact = list(Foundation = "a", P1 = "b", P2 = "c"))
  assignments <- assign_target_phases(snapshot$manifest$name, phases)
  nodes <- build_nodes(snapshot, assignments, phases)
  edges <- build_edges(snapshot)
  expect_equal(nodes$target_type, c("stem", "file", "stem"))
  expect_equal(nodes$shape, c("ellipse", "box", "ellipse"))
  expect_equal(edges$from, c("a", "b"))
  expect_equal(edges$to, c("b", "c"))
  expect_true(all(edges$arrows == "to"))
  expect_identical(edges, build_edges(snapshot))
})

test_that("HTML contains required controls and escapes metadata", {
  snapshot <- synthetic_snapshot()
  phases <- synthetic_phase_config(exact = list(Foundation = "a", P1 = "b", P2 = "c"))
  assignments <- assign_target_phases(snapshot$manifest$name, phases)
  nodes <- build_nodes(snapshot, assignments, phases)
  edges <- build_edges(snapshot)
  stats <- validate_network_model(snapshot, nodes, edges, assignments)
  html <- render_network_html(nodes, edges, phases, stats)
  for (required in c("Target search", "phase-filter", "status-filter", "Outdated only",
                     "Running only", "Error only", "Status", "Phase border", "Target type",
                     "upstream", "downstream", "Reset / fit")) {
    expect_match(html, required, fixed = TRUE)
  }
  expect_false(grepl("<script>alert('x')</script>", html, fixed = TRUE))
  expect_match(html, "\\u003cscript", fixed = TRUE)
})

test_that("atomic renderer does not rewrite identical bytes", {
  path <- tempfile(fileext = ".html")
  write_if_changed_atomic("stable", path)
  first <- file.info(path)$mtime
  first_md5 <- unname(tools::md5sum(path))
  Sys.sleep(1.1)
  write_if_changed_atomic("stable", path)
  expect_equal(file.info(path)$mtime, first)
  expect_equal(unname(tools::md5sum(path)), first_md5)
})

test_that("current graph Phase and outdated counts independently agree", {
  withr::local_dir(fuse_test_root)
  store <- yaml::read_yaml(file.path(fuse_test_root, "config/research_paths.yml"))$targets$research_store
  snapshot <- extract_network_snapshot(store, script = file.path(fuse_test_root, "_targets.R"))
  config <- read_phase_config(file.path(fuse_test_root, "tools/targets-network/target_phases.yml"))
  assignments <- assign_target_phases(snapshot$manifest$name, config)
  nodes <- build_nodes(snapshot, assignments, config)
  edges <- build_edges(snapshot)
  stats <- validate_network_model(snapshot, nodes, edges, assignments)
  independent <- suppressMessages(targets::tar_outdated(
    store = store, script = file.path(fuse_test_root, "_targets.R"), callr_function = NULL
  ))
  expect_equal(stats$node_count, 190L)
  expect_equal(stats$edge_count, 577L)
  expect_equal(unname(stats$status_counts[["outdated"]]), length(intersect(independent, snapshot$manifest$name)))
  expect_equal(length(assignments), length(unique(snapshot$manifest$name)))
  expect_true(all(c("P8", "P9") %in% assignments))
})
