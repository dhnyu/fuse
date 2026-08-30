#!/usr/bin/env Rscript

required_packages <- c("targets", "visNetwork", "yaml", "jsonlite", "igraph")
status_levels <- c("error", "running", "outdated", "up_to_date")
status_palette <- c(error = "#B91C1C", running = "#D97706", outdated = "#BAE6FD", up_to_date = "#166534")
status_font <- c(error = "#FFFFFF", running = "#111827", outdated = "#0C4A6E", up_to_date = "#FFFFFF")
type_shapes <- stats::setNames(c("ellipse", "box", "diamond"), c("stem", "file", "function"))
`%||%` <- function(left, right) if (is.null(left)) right else left

script_path <- function() {
  file_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
  if (length(file_arg)) return(normalizePath(sub("^--file=", "", file_arg[[1L]]), mustWork = TRUE))
  normalizePath("tools/targets-network/render_targets_network.R", mustWork = TRUE)
}

parse_network_args <- function(args) {
  output <- list(output_dir = "artifacts/targets-network", focus = character(), degree = 1L,
                 store = NULL, phases = "tools/targets-network/target_phases.yml")
  for (arg in args) {
    if (grepl("^--output-dir=", arg)) output$output_dir <- sub("^--output-dir=", "", arg)
    else if (grepl("^--focus=", arg)) {
      value <- sub("^--focus=", "", arg)
      output$focus <- unique(Filter(nzchar, trimws(strsplit(value, ",", fixed = TRUE)[[1L]])))
    } else if (grepl("^--degree=", arg)) output$degree <- suppressWarnings(as.integer(sub("^--degree=", "", arg)))
    else if (grepl("^--store=", arg)) output$store <- sub("^--store=", "", arg)
    else if (grepl("^--phases=", arg)) output$phases <- sub("^--phases=", "", arg)
    else stop("Unknown argument: ", arg, call. = FALSE)
  }
  if (!nzchar(output$output_dir)) stop("--output-dir cannot be empty", call. = FALSE)
  if (is.na(output$degree) || output$degree < 0L) stop("--degree must be a non-negative integer", call. = FALSE)
  if (!nzchar(output$phases)) stop("--phases cannot be empty", call. = FALSE)
  output
}

assert_supported_environment <- function(store) {
  missing <- required_packages[!vapply(required_packages, requireNamespace, logical(1L), quietly = TRUE)]
  if (length(missing)) stop("Missing package(s): ", paste(missing, collapse = ", "), call. = FALSE)
  if (utils::packageVersion("targets") < "1.12.0") stop("targets >= 1.12.0 is required for public status APIs", call. = FALSE)
  if (!dir.exists(store)) stop("Target store does not exist: ", store, call. = FALSE)
  if (!targets::tar_exist_meta(store = store)) stop("Target store metadata is missing: ", store, call. = FALSE)
  invisible(TRUE)
}

map_metadata_names <- function(event_names, manifest_names, metadata) {
  event_names <- unique(event_names[!is.na(event_names) & nzchar(event_names)])
  direct <- intersect(event_names, manifest_names)
  branch_rows <- metadata[metadata$name %in% event_names & !is.na(metadata$parent), , drop = FALSE]
  unique(c(direct, intersect(branch_rows$parent, manifest_names)))
}

resolve_target_status <- function(target_names, outdated = character(), running = character(), errored = character()) {
  status <- stats::setNames(rep("up_to_date", length(target_names)), target_names)
  status[target_names %in% outdated] <- "outdated"
  status[target_names %in% running] <- "running"
  status[target_names %in% errored] <- "error"
  unname(status)
}

latest_target_metadata <- function(metadata, target_names) {
  result <- data.frame(name = target_names, seconds = NA_real_, bytes = NA_real_, time = as.POSIXct(NA),
                       error = NA_character_, warnings = NA_character_, stringsAsFactors = FALSE)
  stems <- metadata[metadata$name %in% target_names, , drop = FALSE]
  if (!nrow(stems)) return(result)
  stems <- stems[order(stems$name, stems$time, na.last = TRUE), , drop = FALSE]
  stems <- stems[!duplicated(stems$name, fromLast = TRUE), , drop = FALSE]
  index <- match(result$name, stems$name)
  for (field in intersect(c("seconds", "bytes", "time", "error", "warnings"), names(stems))) result[[field]] <- stems[[field]][index]
  result
}

extract_network_snapshot <- function(store, script = targets::tar_config_get("script")) {
  assert_supported_environment(store)
  manifest <- suppressMessages(targets::tar_manifest(fields = tidyselect::everything(), callr_function = NULL, script = script))
  network <- suppressMessages(targets::tar_network(targets_only = TRUE, outdated = FALSE, callr_function = NULL, script = script, store = store))
  metadata <- targets::tar_meta(targets_only = TRUE, store = store)
  progress <- targets::tar_progress(store = store)
  outdated <- suppressMessages(targets::tar_outdated(store = store, callr_function = NULL, script = script))
  manifest_names <- manifest$name
  running <- map_metadata_names(progress$name[progress$progress == "dispatched"], manifest_names, metadata)
  errored <- map_metadata_names(targets::tar_errored(store = store), manifest_names, metadata)
  statuses <- resolve_target_status(manifest_names, outdated, running, errored)
  current_meta <- latest_target_metadata(metadata, manifest_names)
  manifest <- manifest[order(manifest$name), , drop = FALSE]
  current_meta <- current_meta[match(manifest$name, current_meta$name), , drop = FALSE]
  statuses <- statuses[match(manifest$name, manifest_names)]
  vertices <- network$vertices[match(manifest$name, network$vertices$name), , drop = FALSE]
  if (anyNA(vertices$name)) stop("Manifest and network target nodes do not match", call. = FALSE)
  edges <- unique(network$edges[, c("from", "to"), drop = FALSE])
  edges <- edges[order(edges$from, edges$to), , drop = FALSE]
  list(manifest = manifest, vertices = vertices, edges = edges, metadata = current_meta,
       progress = progress, outdated = sort(intersect(outdated, manifest$name)),
       errored = sort(errored), running = sort(running), status = statuses)
}

read_phase_config <- function(path) {
  if (!file.exists(path)) stop("Phase mapping configuration does not exist: ", path, call. = FALSE)
  config <- yaml::read_yaml(path)
  if (!identical(config$schema_version, "1.0.0")) stop("Unsupported Phase mapping schema", call. = FALSE)
  if (!length(config$phases)) stop("Phase mapping must declare ordered phases", call. = FALSE)
  phase_ids <- vapply(config$phases, `[[`, character(1L), "id")
  if (anyDuplicated(phase_ids)) stop("Duplicate Phase identifiers are prohibited", call. = FALSE)
  if (!all(c("Foundation", paste0("P", 1:9)) %in% phase_ids)) stop("Phase mapping must include Foundation and P1 through P9", call. = FALSE)
  colors <- vapply(config$phases, `[[`, character(1L), "color")
  if (any(!grepl("^#[0-9A-Fa-f]{6}$", colors))) stop("Every Phase requires a six-digit color", call. = FALSE)
  exact <- config$exact %||% list()
  unknown_exact_phase <- setdiff(names(exact), phase_ids)
  if (length(unknown_exact_phase)) stop("Unknown exact Phase: ", paste(unknown_exact_phase, collapse = ", "), call. = FALSE)
  config$phase_ids <- phase_ids
  config$phase_colors <- stats::setNames(colors, phase_ids)
  config$exact <- exact
  config$rules <- config$rules %||% list()
  config
}

assign_target_phases <- function(target_names, config) {
  target_names <- sort(unique(target_names))
  assignments <- stats::setNames(rep(NA_character_, length(target_names)), target_names)
  exact_seen <- character()
  for (phase in names(config$exact)) {
    values <- unlist(config$exact[[phase]], use.names = FALSE)
    duplicated_exact <- intersect(exact_seen, values)
    if (length(duplicated_exact)) stop("Targets assigned to multiple exact Phases: ", paste(sort(duplicated_exact), collapse = ", "), call. = FALSE)
    exact_seen <- c(exact_seen, values)
    assignments[intersect(values, target_names)] <- phase
  }
  rule_hits <- stats::setNames(vector("list", length(target_names)), target_names)
  for (index in seq_along(config$rules)) {
    rule <- config$rules[[index]]
    if (is.null(rule$phase) || !(rule$phase %in% config$phase_ids) || is.null(rule$pattern)) stop("Invalid Phase rule at index ", index, call. = FALSE)
    matches <- grep(rule$pattern, target_names, value = TRUE, perl = TRUE)
    if (!length(matches) && !isTRUE(rule$future)) stop("Phase rule matches no current target: ", rule$pattern, call. = FALSE)
    for (name in setdiff(matches, exact_seen)) rule_hits[[name]] <- c(rule_hits[[name]], rule$phase)
  }
  duplicate_rules <- names(Filter(function(value) length(unique(value)) > 1L, rule_hits))
  if (length(duplicate_rules)) stop("Targets assigned by multiple Phase rules: ", paste(sort(duplicate_rules), collapse = ", "), call. = FALSE)
  for (name in names(rule_hits)) if (is.na(assignments[[name]]) && length(rule_hits[[name]])) assignments[[name]] <- unique(rule_hits[[name]])
  unmapped <- names(assignments)[is.na(assignments)]
  if (length(unmapped)) stop("Unmapped current targets: ", paste(unmapped, collapse = ", "), call. = FALSE)
  assignments
}

target_type <- function(format) ifelse(format == "file", "file", "stem")

html_escape <- function(value) {
  value <- ifelse(is.na(value), "", as.character(value))
  value <- gsub("&", "&amp;", value, fixed = TRUE)
  value <- gsub("<", "&lt;", value, fixed = TRUE)
  value <- gsub(">", "&gt;", value, fixed = TRUE)
  value <- gsub('"', "&quot;", value, fixed = TRUE)
  gsub("'", "&#39;", value, fixed = TRUE)
}

format_metadata_value <- function(value) {
  if (length(value) == 0L || is.na(value) || !nzchar(as.character(value))) "not recorded" else as.character(value)
}

build_nodes <- function(snapshot, phase_assignments, phase_config) {
  manifest <- snapshot$manifest
  direct_dependencies <- table(factor(snapshot$edges$to, levels = manifest$name))
  direct_dependents <- table(factor(snapshot$edges$from, levels = manifest$name))
  phase <- unname(phase_assignments[manifest$name])
  types <- target_type(manifest$format)
  latest_error <- snapshot$metadata$error
  latest_success <- ifelse(is.na(latest_error) | !nzchar(latest_error),
                           format(snapshot$metadata$time, "%Y-%m-%d %H:%M:%S %Z", tz = "Asia/Seoul"), NA_character_)
  data.frame(id = manifest$name, label = paste0("[", phase, "]\n", manifest$name), status = snapshot$status,
             phase = phase, phase_order = match(phase, phase_config$phase_ids) - 1L,
             target_type = types, shape = unname(type_shapes[types]),
             background = unname(status_palette[snapshot$status]), font_color = unname(status_font[snapshot$status]),
             border = unname(phase_config$phase_colors[phase]), dependencies = as.integer(direct_dependencies),
             dependents = as.integer(direct_dependents), seconds = snapshot$metadata$seconds,
             bytes = snapshot$metadata$bytes, latest_error = ifelse(is.na(latest_error), "", latest_error),
             latest_success = ifelse(is.na(latest_success), "", latest_success), stringsAsFactors = FALSE)
}

build_edges <- function(snapshot) {
  edges <- snapshot$edges[order(snapshot$edges$from, snapshot$edges$to), , drop = FALSE]
  data.frame(id = sprintf("edge-%04d", seq_len(nrow(edges))), from = edges$from, to = edges$to,
             arrows = "to", stringsAsFactors = FALSE)
}

validate_network_model <- function(snapshot, nodes, edges, phase_assignments) {
  target_names <- snapshot$manifest$name
  if (length(target_names) != length(unique(target_names))) stop("Manifest contains duplicate target names", call. = FALSE)
  if (!setequal(target_names, nodes$id) || nrow(nodes) != length(target_names)) stop("Every target must appear exactly once", call. = FALSE)
  if (!identical(sort(names(phase_assignments)), sort(target_names))) stop("Phase assignments do not match manifest", call. = FALSE)
  unknown <- setdiff(unique(c(edges$from, edges$to)), target_names)
  if (length(unknown)) stop("Network edges reference unknown nodes: ", paste(unknown, collapse = ", "), call. = FALSE)
  if (!identical(sum(nodes$status == "outdated"), length(snapshot$outdated))) stop("Rendered outdated count differs from independent tar_outdated()", call. = FALSE)
  graph <- igraph::graph_from_data_frame(edges[, c("from", "to")], directed = TRUE, vertices = target_names)
  if (!igraph::is_dag(graph)) stop("Target dependency graph contains a cycle", call. = FALSE)
  phase_levels <- unique(nodes$phase[order(nodes$phase_order)])
  list(node_count = nrow(nodes), edge_count = nrow(edges), dag = TRUE,
       weak_components = igraph::components(graph, mode = "weak")$no,
       status_counts = table(factor(nodes$status, levels = status_levels)),
       phase_counts = table(factor(nodes$phase, levels = phase_levels)))
}

focus_network <- function(network, focus, degree) {
  unknown <- setdiff(focus, network$vertices$name)
  if (length(unknown)) stop("Unknown focus target(s): ", paste(unknown, collapse = ", "), call. = FALSE)
  selected <- unique(focus)
  if (degree > 0L) for (step in seq_len(degree)) {
    adjacent <- network$edges$from[network$edges$to %in% selected]
    adjacent <- c(adjacent, network$edges$to[network$edges$from %in% selected])
    selected <- unique(c(selected, adjacent))
  }
  list(vertices = network$vertices[network$vertices$name %in% selected, , drop = FALSE],
       edges = network$edges[network$edges$from %in% selected & network$edges$to %in% selected, , drop = FALSE])
}

json_for_html <- function(value) {
  output <- jsonlite::toJSON(value, auto_unbox = TRUE, dataframe = "rows", na = "null", null = "null", digits = 16)
  output <- gsub("<", "\\\\u003c", output, fixed = TRUE)
  output <- gsub(">", "\\\\u003e", output, fixed = TRUE)
  gsub("&", "\\\\u0026", output, fixed = TRUE)
}

node_records <- function(nodes) {
  lapply(seq_len(nrow(nodes)), function(index) {
    row <- nodes[index, , drop = FALSE]
    error_text <- if (nzchar(row$latest_error)) row$latest_error else "none"
    success_text <- if (nzchar(row$latest_success)) row$latest_success else "not recorded"
    list(id = row$id, label = row$label, status = row$status, phase = row$phase, target_type = row$target_type,
         level = row$phase_order, shape = row$shape,
         color = list(background = row$background, border = row$border,
                      highlight = list(background = row$background, border = "#111827")),
         font = list(color = row$font_color, face = "Arial", size = 12L, multi = FALSE),
         borderWidth = 3L, margin = 8L,
         title = paste0("<b>", html_escape(row$id), "</b><br>status: ", html_escape(row$status),
                        "<br>Phase: ", html_escape(row$phase), "<br>type: ", html_escape(row$target_type),
                        "<br>dependencies: ", row$dependencies, "; dependents: ", row$dependents,
                        "<br>elapsed seconds: ", html_escape(format_metadata_value(row$seconds)),
                        "<br>object bytes: ", html_escape(format_metadata_value(row$bytes)),
                        "<br>latest error: ", html_escape(error_text),
                        "<br>latest successful build: ", html_escape(success_text)),
         details = list(name = row$id, status = row$status, phase = row$phase, type = row$target_type,
                        dependencies = row$dependencies, dependents = row$dependents,
                        seconds = format_metadata_value(row$seconds), bytes = format_metadata_value(row$bytes),
                        latest_error = error_text, latest_success = success_text))
  })
}

edge_records <- function(edges) lapply(seq_len(nrow(edges)), function(index) list(
  id = edges$id[[index]], from = edges$from[[index]], to = edges$to[[index]], arrows = "to",
  color = list(color = "rgba(100,116,139,0.28)", highlight = "#334155"), width = 1L,
  smooth = list(enabled = TRUE, type = "cubicBezier", roundness = 0.18)))

render_controls <- function(statistics, phase_config) {
  status_cards <- paste(vapply(status_levels, function(status) sprintf(
    '<button class="summary-card" data-status="%s"><span class="swatch" style="background:%s"></span><span>%s</span><strong id="count-%s">%d</strong></button>',
    status, status_palette[[status]], gsub("_", " ", status), status, statistics$status_counts[[status]]
  ), character(1L)), collapse = "")
  phase_values <- as.integer(statistics$phase_counts[phase_config$phase_ids]); phase_values[is.na(phase_values)] <- 0L
  phase_options <- paste(sprintf('<option value="%s">%s (%d)</option>', html_escape(phase_config$phase_ids),
                                 html_escape(phase_config$phase_ids), phase_values), collapse = "")
  status_options <- paste(sprintf('<option value="%s">%s</option>', status_levels, gsub("_", " ", status_levels)), collapse = "")
  phase_legend <- paste(vapply(seq_along(phase_config$phase_ids), function(index) sprintf(
    '<span class="legend-item"><span class="phase-ring" style="border-color:%s"></span>%s</span>',
    phase_config$phase_colors[[index]], html_escape(phase_config$phase_ids[[index]])), character(1L)), collapse = "")
  paste0('<header><div><h1>Fuse targets status and Phase network</h1><p>', statistics$node_count,
         ' targets · ', statistics$edge_count, ' dependencies · ', statistics$weak_components,
         ' weak components · DAG</p></div><div class="summary">', status_cards, '</div></header>',
         '<section class="toolbar" aria-label="Network filters"><label>Target search<input id="target-search" list="target-names" placeholder="Type a target name"></label><datalist id="target-names"></datalist>',
         '<label>Phase<select id="phase-filter"><option value="all">All phases</option>', phase_options, '</select></label>',
         '<label>Status<select id="status-filter"><option value="all">All statuses</option>', status_options, '</select></label>',
         '<div class="quick"><button data-quick="all">All</button><button data-quick="outdated">Outdated only</button><button data-quick="running">Running only</button><button data-quick="error">Error only</button></div>',
         '<button id="fit-network" class="fit">Reset / fit</button></section>',
         '<section class="legends"><div><strong>Status</strong>',
         paste(vapply(status_levels, function(status) sprintf('<span class="legend-item"><span class="swatch" style="background:%s"></span>%s</span>', status_palette[[status]], gsub("_", " ", status)), character(1L)), collapse = ""),
         '</div><div><strong>Phase border</strong>', phase_legend,
         '</div><div><strong>Target type</strong><span class="legend-item"><span class="shape ellipse"></span>stem</span><span class="legend-item"><span class="shape box"></span>file</span></div>',
         '<div><strong>Selected lineage</strong><span class="legend-item"><span class="edge-line upstream"></span>upstream</span><span class="legend-item"><span class="edge-line downstream"></span>downstream</span></div></section>')
}

render_network_html <- function(nodes, edges, phase_config, statistics, title = "Fuse targets network") {
  vis_root <- system.file("htmlwidgets/lib/vis", package = "visNetwork")
  vis_css <- paste(readLines(file.path(vis_root, "vis-network.min.css"), warn = FALSE), collapse = "\n")
  vis_js <- paste(readLines(file.path(vis_root, "vis-network.min.js"), warn = FALSE), collapse = "\n")
  payload <- list(nodes = node_records(nodes), edges = edge_records(edges), phases = phase_config$phase_ids)
  controls <- render_controls(statistics, phase_config)
  css <- paste0('*{box-sizing:border-box}body{margin:0;background:#F8FAFC;color:#0F172A;font:14px Arial,sans-serif}',
    '.page{display:grid;grid-template-rows:auto auto auto minmax(620px,1fr);height:100vh}',
    'header{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:14px 20px;background:#fff;border-bottom:1px solid #CBD5E1}',
    'h1{font-size:20px;margin:0 0 4px}header p{margin:0;color:#64748B}.summary{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}',
    '.summary-card{display:grid;grid-template-columns:10px auto auto;gap:6px;align-items:center;border:1px solid #CBD5E1;background:#fff;padding:6px 8px;border-radius:6px;color:#334155}',
    '.summary-card strong{font-variant-numeric:tabular-nums}.toolbar{display:flex;align-items:end;gap:10px;padding:10px 20px;background:#F1F5F9;border-bottom:1px solid #CBD5E1;flex-wrap:wrap}',
    'label{display:grid;gap:4px;font-size:11px;font-weight:700;color:#475569;text-transform:uppercase}input,select,button{font:inherit}',
    'input,select{height:34px;border:1px solid #94A3B8;border-radius:5px;background:#fff;padding:0 9px;min-width:160px}#target-search{width:280px}',
    '.quick{display:flex;gap:5px}.quick button,.fit{height:34px;border:1px solid #94A3B8;border-radius:5px;background:#fff;padding:0 10px;cursor:pointer}',
    '.legends{display:flex;gap:20px;padding:8px 20px;background:#fff;border-bottom:1px solid #CBD5E1;align-items:center;flex-wrap:wrap;font-size:12px}.legends>div{display:flex;gap:8px;align-items:center;flex-wrap:wrap}',
    '.legend-item{display:inline-flex;align-items:center;gap:4px;color:#475569}.swatch{width:10px;height:10px;border-radius:2px;display:inline-block}.phase-ring{width:12px;height:12px;border:3px solid;border-radius:50%}',
    '.shape{display:inline-block;width:14px;height:10px;border:2px solid #475569}.shape.ellipse{border-radius:50%}.shape.box{border-radius:1px}',
    '.edge-line{width:20px;border-top:3px solid}.edge-line.upstream{border-color:#2563EB}.edge-line.downstream{border-color:#DB2777}',
    '.workspace{display:grid;grid-template-columns:minmax(0,1fr) 290px;min-height:0}.network{height:100%;min-height:620px;background:#fff}.details{padding:16px;border-left:1px solid #CBD5E1;background:#F8FAFC;overflow:auto}',
    '.details h2{font-size:14px;margin:0 0 12px}.details dl{display:grid;grid-template-columns:95px 1fr;gap:8px;margin:0}.details dt{font-weight:700;color:#475569}.details dd{margin:0;overflow-wrap:anywhere}.muted{color:#64748B}',
    '@media(max-width:900px){.page{height:auto}.workspace{grid-template-columns:1fr}.details{border-left:0;border-top:1px solid #CBD5E1}.network{height:70vh}header{align-items:flex-start;flex-direction:column}}')
  app_js <- paste0('"use strict";const graphData=JSON.parse(document.getElementById("graph-data").textContent);',
    'const originalNodes=graphData.nodes;const originalEdges=graphData.edges;const nodes=new vis.DataSet(originalNodes);const edges=new vis.DataSet(originalEdges);',
    'const network=new vis.Network(document.getElementById("targets-network"),{nodes:nodes,edges:edges},{layout:{hierarchical:{enabled:true,direction:"LR",sortMethod:"directed",levelSeparation:210,nodeSpacing:44,treeSpacing:72,blockShifting:true,edgeMinimization:true,parentCentralization:true}},physics:{enabled:false},interaction:{hover:true,navigationButtons:true,keyboard:true,multiselect:false,tooltipDelay:250},edges:{selectionWidth:2}});',
    'const byId=Object.fromEntries(originalNodes.map(n=>[n.id,n]));const datalist=document.getElementById("target-names");originalNodes.forEach(n=>{const o=document.createElement("option");o.value=n.id;datalist.appendChild(o);});',
    'function visibleIds(){const p=document.getElementById("phase-filter").value,s=document.getElementById("status-filter").value;return new Set(originalNodes.filter(n=>(p==="all"||n.phase===p)&&(s==="all"||n.status===s)).map(n=>n.id));}',
    'function clearLineage(){edges.update(originalEdges.map(e=>({...e,color:{color:"rgba(100,116,139,0.28)",highlight:"#334155"},width:1,dashes:false})));}',
    'function applyFilters(){const v=visibleIds();nodes.update(originalNodes.map(n=>({id:n.id,hidden:!v.has(n.id)})));edges.update(originalEdges.map(e=>({id:e.id,hidden:!(v.has(e.from)&&v.has(e.to))})));clearLineage();network.unselectAll();showDetails(null);}',
    'function lineage(start,reverse){const seen=new Set(),queue=[start];while(queue.length){const cur=queue.shift();originalEdges.forEach(e=>{const next=reverse?(e.to===cur?e.from:null):(e.from===cur?e.to:null);if(next&&!seen.has(next)&&next!==start){seen.add(next);queue.push(next);}});}return seen;}',
    'function highlightLineage(id){clearLineage();const up=lineage(id,true),down=lineage(id,false);edges.update(originalEdges.map(e=>{if(up.has(e.from)&&(up.has(e.to)||e.to===id))return{id:e.id,color:{color:"#2563EB",highlight:"#2563EB"},width:3,hidden:false};if((e.from===id||down.has(e.from))&&down.has(e.to))return{id:e.id,color:{color:"#DB2777",highlight:"#DB2777"},width:3,hidden:false};return{id:e.id,color:{color:"rgba(148,163,184,0.18)",highlight:"#64748B"},width:1};}));}',
    'function showDetails(id){const panel=document.getElementById("details-content");if(!id){panel.innerHTML="<p class=muted>Select a target to inspect current metadata and lineage.</p>";return;}const d=byId[id].details;panel.textContent="";const dl=document.createElement("dl");[["Target",d.name],["Status",d.status],["Phase",d.phase],["Type",d.type],["Dependencies",d.dependencies],["Dependents",d.dependents],["Elapsed seconds",d.seconds],["Object bytes",d.bytes],["Latest error",d.latest_error],["Latest success",d.latest_success]].forEach(pair=>{const dt=document.createElement("dt"),dd=document.createElement("dd");dt.textContent=pair[0];dd.textContent=String(pair[1]);dl.append(dt,dd);});panel.appendChild(dl);}',
    'network.on("selectNode",p=>{const id=p.nodes[0];highlightLineage(id);showDetails(id);});network.on("deselectNode",()=>{clearLineage();showDetails(null);});',
    'document.getElementById("phase-filter").addEventListener("change",applyFilters);document.getElementById("status-filter").addEventListener("change",applyFilters);',
    'document.querySelectorAll("[data-quick]").forEach(b=>b.addEventListener("click",()=>{document.getElementById("phase-filter").value="all";document.getElementById("status-filter").value=b.dataset.quick;applyFilters();network.fit({animation:false});}));',
    'document.querySelectorAll("[data-status]").forEach(b=>b.addEventListener("click",()=>{document.getElementById("status-filter").value=b.dataset.status;applyFilters();network.fit({animation:false});}));',
    'document.getElementById("fit-network").addEventListener("click",()=>{document.getElementById("phase-filter").value="all";document.getElementById("status-filter").value="all";document.getElementById("target-search").value="";applyFilters();network.fit({animation:false});});',
    'document.getElementById("target-search").addEventListener("change",e=>{const id=e.target.value;if(!byId[id])return;document.getElementById("phase-filter").value="all";document.getElementById("status-filter").value="all";applyFilters();network.selectNodes([id]);network.focus(id,{scale:1.15,animation:false});highlightLineage(id);showDetails(id);});',
    'window.addEventListener("error",e=>{document.body.dataset.javascriptError=e.message;});showDetails(null);network.fit({animation:false});')
  paste0('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>', html_escape(title), '</title><style>', vis_css, css, '</style></head><body>',
         '<main class="page">', controls, '<section class="workspace"><div id="targets-network" class="network" aria-label="Directed targets dependency network"></div>',
         '<aside class="details"><h2>Target details</h2><div id="details-content"></div></aside></section></main>',
         '<script type="application/json" id="graph-data">', json_for_html(payload), '</script><script>', vis_js, '</script><script>', app_js, '</script></body></html>\n')
}

write_if_changed_atomic <- function(content, output_file) {
  dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
  if (file.exists(output_file) && identical(readChar(output_file, file.info(output_file)$size, useBytes = TRUE), content)) return(normalizePath(output_file, mustWork = TRUE))
  temporary <- tempfile(pattern = ".targets-network-", tmpdir = dirname(output_file), fileext = ".html")
  on.exit(if (file.exists(temporary)) unlink(temporary), add = TRUE)
  writeChar(content, temporary, eos = NULL, useBytes = TRUE)
  if (!file.rename(temporary, output_file)) stop("Could not publish dependency HTML: ", output_file, call. = FALSE)
  normalizePath(output_file, mustWork = TRUE)
}

render_targets_network <- function(output_dir, focus = character(), degree = 1L, store = targets::tar_config_get("store"),
                                   phase_file = "tools/targets-network/target_phases.yml") {
  snapshot <- extract_network_snapshot(store)
  phase_config <- read_phase_config(phase_file)
  assignments <- assign_target_phases(snapshot$manifest$name, phase_config)
  nodes <- build_nodes(snapshot, assignments, phase_config)
  edges <- build_edges(snapshot)
  statistics <- validate_network_model(snapshot, nodes, edges, assignments)
  outputs <- write_if_changed_atomic(render_network_html(nodes, edges, phase_config, statistics), file.path(output_dir, "targets-network.html"))
  if (length(focus)) {
    focused <- focus_network(list(vertices = snapshot$vertices, edges = snapshot$edges), focus, degree)
    keep <- focused$vertices$name
    focus_nodes <- nodes[nodes$id %in% keep, , drop = FALSE]
    focus_edges <- edges[edges$from %in% keep & edges$to %in% keep, , drop = FALSE]
    focus_snapshot <- snapshot
    focus_snapshot$manifest <- snapshot$manifest[snapshot$manifest$name %in% keep, , drop = FALSE]
    focus_snapshot$outdated <- intersect(snapshot$outdated, keep)
    focus_statistics <- validate_network_model(focus_snapshot, focus_nodes, focus_edges, assignments[keep])
    slug <- paste(gsub("[^A-Za-z0-9_-]", "-", focus), collapse = "-")
    outputs <- c(outputs, write_if_changed_atomic(render_network_html(focus_nodes, focus_edges, phase_config, focus_statistics,
      paste0("Fuse targets near: ", paste(focus, collapse = ", "))), file.path(output_dir, paste0("targets-network-focus-", slug, ".html"))))
  }
  attr(outputs, "statistics") <- statistics
  outputs
}

main <- function() {
  project_root <- normalizePath(file.path(dirname(script_path()), "..", ".."), mustWork = TRUE)
  setwd(project_root)
  options <- parse_network_args(commandArgs(trailingOnly = TRUE))
  if (is.null(options$store)) options$store <- yaml::read_yaml("config/research_paths.yml")$targets$research_store
  outputs <- render_targets_network(options$output_dir, options$focus, options$degree, options$store, options$phases)
  statistics <- attr(outputs, "statistics")
  message("Created dependency HTML:\n", paste0("- ", outputs, collapse = "\n"),
          "\nSnapshot: ", statistics$node_count, " targets, ", statistics$edge_count, " edges, ",
          statistics$weak_components, " weak components; statuses ",
          paste(names(statistics$status_counts), statistics$status_counts, sep = "=", collapse = ", "))
}

if (sys.nframe() == 0L) main()
