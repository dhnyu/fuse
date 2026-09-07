# Current reduced methodology authority. The preceding P0 implementation remains
# readable for historical artifacts; these definitions are the active v2 contract.
p0_legacy_module_definitions <- p0_module_definitions

p0_semantic_selector <- function(path, anchor, required_tokens, end_anchor = NULL,
                                 forbidden_tokens = character()) {
  list(path = path, selector = "anchored_semantic_block", anchor = anchor,
       end_anchor = end_anchor, required_tokens = as.list(required_tokens),
       forbidden_tokens = as.list(forbidden_tokens))
}

p0_extract_semantic_block <- function(selector, source_set, repository_path) {
  known <- vapply(source_set$ordered_files, `[[`, character(1L), "path")
  if (!selector$path %in% known) stop("Methodology selector is outside imported source set: ", selector$path, call. = FALSE)
  text <- paste(readLines(file.path(repository_path, selector$path), warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  starts <- gregexpr(selector$anchor, text, fixed = TRUE)[[1L]]
  starts <- starts[starts > 0L]
  if (length(starts) != 1L) stop("Methodology selector anchor must occur exactly once: ", selector$anchor, call. = FALSE)
  start <- starts[[1L]]
  tail <- substring(text, start)
  if (!is.null(selector$end_anchor)) {
    finish <- regexpr(selector$end_anchor, tail, fixed = TRUE)[[1L]]
    if (finish < 2L) stop("Methodology selector end anchor is absent or ambiguous: ", selector$end_anchor, call. = FALSE)
    tail <- substring(tail, 1L, finish - 1L)
  }
  tokens <- unlist(selector$required_tokens, use.names = FALSE)
  absent <- tokens[!vapply(tokens, grepl, logical(1L), x = tail, fixed = TRUE)]
  if (length(absent)) stop("Methodology semantic token is absent: ", paste(absent, collapse = ", "), call. = FALSE)
  forbidden <- unlist(selector$forbidden_tokens, use.names = FALSE)
  present <- forbidden[vapply(forbidden, grepl, logical(1L), x = tail, fixed = TRUE)]
  if (length(present)) stop("Forbidden methodology semantic token is present: ", paste(present, collapse = ", "), call. = FALSE)
  normalized <- gsub("[[:space:]]+", " ", trimws(tail), perl = TRUE)
  c(selector, list(evidence_sha256 = digest::digest(normalized, algo = "sha256", serialize = FALSE)))
}

p0_current_architecture <- function() {
  list(
    latent_dimension = 128L, contrastive_dimension = 128L,
    entity_type_dimension = 16L, relation_dimension = 32L,
    attention = list(heads = 4L, head_dimension = 32L, ffn = as.list(c(128L, 256L, 128L)), layers = 3L),
    encoders = list(relative = "64->128->128", geometry = "(128,256)->(128,128)->128",
                    semantic_fusions = "B/R/P->128", object_environment = "26->128->128",
                    land_cover = "16x100x100->128", dem = "1x17x17->128"),
    final_scene_fusion = "640->256->128", contrastive_projection = "128->256->128",
    modality_mask_embeddings = "4x128", reconstruction_decoders = FALSE
  )
}

p0_component_contracts <- function() {
  modalities <- as.list(c("relative_position", "intrinsic_geometry", "semantics", "object_environmental_background"))
  list(
    FM = list(modalities = modalities, fusion = TRUE, relation = "heterogeneous", scene_raster = TRUE),
    A1 = list(modalities = as.list("relative_position"), fusion = FALSE, relation = "none", scene_raster = FALSE),
    A2 = list(modalities = as.list(c("relative_position", "intrinsic_geometry")), fusion = TRUE, relation = "none", scene_raster = FALSE),
    A3 = list(modalities = modalities, fusion = TRUE, relation = "none", scene_raster = FALSE),
    A4 = list(modalities = modalities, fusion = TRUE, relation = "generic_same_FM_directed_edges", scene_raster = FALSE),
    A5 = list(modalities = modalities, fusion = TRUE, relation = "heterogeneous", scene_raster = FALSE),
    SSV = list(modalities = as.list(c("relative_position", "semantics")), fusion = TRUE, relation = "none", scene_raster = FALSE),
    DS = list(modalities = list(), fusion = FALSE, relation = "none", scene_raster = "DS_multichannel_raster")
  )
}

p0_source_ablation_contracts <- function() {
  values <- list(B1=c("B","R","P"), B2=c("B","R"), B3=c("B","P"), B4=c("R","P"),
                 B5="B", B6="R", B7="P", B8=c("B","R","P","LC"), B9=c("B","R","P","DEM"))
  lapply(values, function(sources) list(retained_sources = as.list(sources), removal = "input_level",
    relation_graph = "FM_induced_subgraph_no_new_edges", fusion = "active_modalities_only",
    raster_pathways = "retained_raster_sources_only"))
}

p0_validate_current_implementation_contract <- function(root = ".") {
  config <- yaml::read_yaml(file.path(root, "config/current_methodology.yml"))
  definitions <- p0_module_definitions()
  scene <- definitions$scene$contract
  model <- definitions$model$contract
  training <- definitions$training$contract
  study <- definitions$hyperparameter_study$contract
  comparison <- definitions$comparison$contract
  checks <- c(
    identical(as.integer(unlist(config$scene_split[c("total_off_grid", "validation", "evaluation")])),
              c(10000L, 1000L, 9000L)),
    identical(as.integer(config$scene_split$minimum_training_center_distance_m),
              scene$off_grid_minimum_distance_m),
    identical(as.integer(c(config$model$d, config$model$d_c)),
              as.integer(c(model$dimensions$d, model$dimensions$d_c))),
    identical(config$model$information_preservation, model$information_preservation_subsystem),
    identical(config$model$reconstruction_decoders, model$architecture$reconstruction_decoders),
    identical(config$training$objective, "symmetric_scene_contrastive"),
    identical(as.integer(config$training$K_aug), training$main_k_aug),
    identical(as.numeric(config$training$augmentation_intensity), training$main_augmentation_intensity),
    identical(as.numeric(config$training$ema_momentum), training$ema_momentum),
    identical(as.numeric(config$training$peak_learning_rate), training$peak_learning_rate),
    identical(as.integer(unlist(config$hyperparameter_study$d)), as.integer(unlist(study$candidates$d))),
    identical(as.integer(unlist(config$hyperparameter_study$K_aug)), as.integer(unlist(study$candidates$K_aug))),
    identical(as.numeric(unlist(config$hyperparameter_study$augmentation_intensity)), as.numeric(unlist(study$candidates$intensity))),
    identical(as.numeric(unlist(config$hyperparameter_study$ema_momentum)), as.numeric(unlist(study$candidates$mu_EMA))),
    identical(as.numeric(unlist(config$hyperparameter_study$peak_learning_rate)), as.numeric(unlist(study$candidates$peak_learning_rate))),
    identical(unlist(config$comparison$ordered_models, use.names = FALSE), unlist(comparison$ordered_names, use.names = FALSE)),
    identical(lapply(config$comparison$retained_sources[names(p0_source_ablation_contracts())], unlist, use.names = FALSE),
              lapply(p0_source_ablation_contracts(), function(value) unlist(value$retained_sources, use.names = FALSE)))
  )
  if (!all(checks)) stop("Current implementation methodology contract diverges from P0 canonical authority", call. = FALSE)
  invisible(TRUE)
}

p0_module_definitions <- function() {
  definitions <- p0_legacy_module_definitions()
  exp_path <- "template/sections/chapters/results/01-experimental-setup.typ"
  hp_path <- "template/sections/chapters/results/05-hyperparameter-study.typ"
  train_path <- "template/sections/chapters/04-methodology-training.typ"
  dim_path <- "template/materials/tables/results-02-model-dimension-table.typ"
  arch_path <- "template/materials/tables/results-05-model-architecture-table.typ"
  train_table <- "template/materials/tables/results-04-training-configuration-table.typ"

  definitions$scene$citations <- list(p0_semantic_selector(exp_path,
    "Training scenes were constructed from the official 500 m national grid",
    c("No intermediate centers or overlapping sliding windows were introduced", "10,000 off-grid scenes", "1,000 validation scenes", "9,000 evaluation scenes", "= 50"), "#v(2em)"))
  definitions$scene$contract$training_scene_count <- NULL
  definitions$scene$contract$validation_scene_count <- 1000L
  definitions$scene$contract$evaluation_scene_count <- 9000L
  definitions$scene$contract$total_off_grid_scene_count <- 10000L
  definitions$scene$contract$field_origins <- list(train_grid = "official_500m_grid_centers_inside_Seoul")

  definitions$base_spatial$citations <- list(p0_semantic_selector(
    "template/sections/chapters/methodology/04-spatial-relations.typ", "== Relation-aware Entity Contextualization",
    c("SN", "CNT", "WIT", "INT", "CON")))
  definitions$original_cache$citations <- list(p0_semantic_selector(
    "template/sections/chapters/methodology/01-scene-construction.typ", "== Overview",
    c("spatial scene")))
  definitions$augmentation$citations <- list(p0_semantic_selector(train_path, "== Spatial Scene Augmentation",
    c("generated once before training", "remain fixed", "entity removal", "geometry perturbation", "raster perturbation"),
    "== Scene-level Contrastive Learning"))

  definitions$model <- list(citations = list(
    p0_semantic_selector(dim_path, "[$d$]", c("[Common latent dimension]", "[$128$]", "[$d_c$]")),
    p0_semantic_selector(arch_path, "// Geoentity modality encoders", c("Linear$(64,128)", "Final scene fusion", "Contrastive projection head"),
                         forbidden_tokens = c("decoder", "reconstruction"))
  ), contract = list(dimensions = list(d=128L, d_c=128L, d_t=16L, d_r=32L),
                     architecture = p0_current_architecture(), information_preservation_subsystem = FALSE))

  definitions$training <- list(citations = list(
    p0_semantic_selector(train_path, "== Training Objective and Optimization",
      c("optimized solely through the scene-level contrastive objective", "cal(L)=cal(L)_(upright(s c e n e))"),
      forbidden_tokens = c("information-preservation", "lambda_(upright(I P))", "reconstruction")),
    p0_semantic_selector(train_table, "// Scene-level contrastive learning", c("[$0.999$]", "[$8192$]", "[$0.1$]", "[$1 times 10^(-3)$]"))
  ), contract = list(objective = "symmetric_scene_level_contrastive_only", information_preservation = FALSE,
    reconstruction_loss = FALSE, reconstruction_decoder_path = FALSE, modality_masking = TRUE,
    momentum_encoder = TRUE, ema_momentum = 0.999, fifo_queue_capacity = 8192L,
    contrastive_projection_head = TRUE, main_k_aug = 8L, main_augmentation_intensity = 1.0,
    peak_learning_rate = 1e-3, contrastive_temperature = 0.1))

  definitions$evaluation$citations <- list(p0_semantic_selector(exp_path,
    "A total of 10,000 off-grid scenes", c("1,000 validation scenes", "9,000 evaluation scenes", "reserved for final evaluation"), "#v(2em)"))
  definitions$evaluation$contract$validation <- list(originals=1000L, augmented_queries=2000L, gallery=1000L)
  definitions$evaluation$contract$evaluation <- list(originals=9000L, augmented_queries=18000L, gallery=9000L)

  definitions$hyperparameter_study <- list(citations = list(p0_semantic_selector(hp_path,
    "The sensitivity of the proposed model to five key hyperparameters", c("eleven unique configurations", "{64,128,256}", "{4,8,16}", "{0.990,0.999}", "{1,2,3,5}"))),
    contract = list(design="shared_main_OFAT", axes=as.list(c("d","K_aug","augmentation_intensity","mu_EMA","peak_learning_rate")),
      unique_configuration_count=11L, main=list(d=128L,d_c=128L,K_aug=8L,intensity=1.0,mu_EMA=0.999,peak_learning_rate=1e-3),
      candidates=list(d=as.list(c(64L,128L,256L)),K_aug=as.list(c(4L,8L,16L)),intensity=as.list(c(0.5,1.0,2.0)),mu_EMA=as.list(c(0.990,0.999)),peak_learning_rate=as.list(c(1e-3,2e-3,3e-3,5e-3)))))

  definitions$comparison <- list(citations = list(p0_semantic_selector(exp_path, "Seventeen model configurations were evaluated",
    c("A1–A5", "B1–B9", "exactly the same directed edge instances", "maps every SN, CNT, WIT, INT, and CON relation label to a single generic relation type",
      "assigned their respective relation-type representations", "B1 retains all three entity sources", "B8 retains buildings, roads, POIs, and land cover",
      "B9 retains buildings, roads, POIs, and DEM", "input level", "induced subgraph"), "#v(2em)\n*Implementation.*")),
    contract = list(configuration_count=17L, ordered_names=as.list(c("FM",paste0("A",1:5),paste0("B",1:9),"SSV","DS")),
      component_variants=p0_component_contracts(), source_variants=p0_source_ablation_contracts(),
      source_removal="true_input_level", relation_filter="induced_subgraph_preserve_FM_edges_only"))

  definitions$downstream$citations <- list(p0_semantic_selector(
    "template/sections/chapters/results/04-downstream-representation-utility.typ", "=== Downstream Evaluation",
    c("Ridge regression", "frozen scene representations"), "=== Downstream Prediction Results"))
  definitions
}

p0_extract_citation <- function(citation, source_set, repository_path) {
  if (identical(citation$selector, "anchored_semantic_block")) {
    return(p0_extract_semantic_block(citation, source_set, repository_path))
  }
  stop("P0 v2 prohibits line-range methodology evidence", call. = FALSE)
}

p0_source_authority_file <- function(paths, basename_required) {
  paths <- normalizePath(paths, mustWork = TRUE)
  selected <- paths[basename(paths) == basename_required]
  if (length(selected) != 1L) stop("P0 source-authority component selection mismatch: ", basename_required, call. = FALSE)
  selected
}

build_p0_module_contract <- function(module_name, source_set_file, conflict_gate_file, spec) {
  definitions <- p0_module_definitions()
  if (!module_name %in% names(definitions)) stop("Unknown P0 methodology module: ", module_name, call. = FALSE)
  source_path <- p0_source_authority_file(source_set_file, "methodology_source_set.json")
  gate_path <- p0_source_authority_file(conflict_gate_file, "methodology_conflict_gate.json")
  source_set <- jsonlite::read_json(source_path, simplifyVector = FALSE)
  gate <- jsonlite::read_json(gate_path, simplifyVector = FALSE)
  if (!identical(source_set$status, "PASS") || !identical(gate$status, "PASS")) stop("P0 source authority is not accepted", call. = FALSE)
  definition <- definitions[[module_name]]
  citations <- lapply(definition$citations, p0_extract_citation, source_set=source_set,
                      repository_path=spec$dissertation$repository_path)
  scientific <- list(schema_version=spec$schema_version, module_name=module_name,
    authoritative_source_citations=citations, canonical_contract=definition$contract,
    source_set_id=source_set$source_set_id, extraction_validation_implementation_sha256=spec$implementation_sha256,
    unresolved_fields=list(), conflicting_fields=list(), status="PASS")
  content_hash <- p0_scientific_sha256(list(
    schema_version = spec$schema_version,
    module_name = module_name,
    canonical_contract = definition$contract
  ))
  value <- c(list(schema_version=spec$schema_version, contract_id=paste0("mmc_",substr(content_hash,1L,16L)), module_name=module_name),
             scientific[setdiff(names(scientific),c("schema_version","module_name"))], list(module_content_sha256=content_hash))
  p0_publish_json_component(value, p0_component_dir(spec,file.path("modules",module_name),value$contract_id),
                            paste0(module_name,"_methodology_contract.json"), spec$schemas[["module_contract"]])
}

build_reduced_methodology_conflict_gate <- function(source_set_file, spec) {
  p0_validate_current_implementation_contract(spec$root)
  source_set <- jsonlite::read_json(source_set_file, simplifyVector=FALSE)
  records <- lapply(seq_along(p0_module_definitions()), function(i) {
    name <- names(p0_module_definitions())[[i]]
    evidence <- lapply(p0_module_definitions()[[name]]$citations, p0_extract_semantic_block,
                       source_set=source_set, repository_path=spec$dissertation$repository_path)
    list(conflict_id=sprintf("p0_semantic_%03d",i), module=name, scientific_field="canonical_contract",
         normalized_values=list(p0_module_definitions()[[name]]$contract), sources=evidence,
         severity="info", classification="CONSISTENT", resolution_status="RESOLVED")
  })
  scientific <- list(schema_version=spec$schema_version,source_set_id=source_set$source_set_id,records=records,
                     blocking_conflict_count=0L,missing_evidence_count=0L,unclassified_conflict_count=0L,status="PASS")
  hash <- p0_scientific_sha256(scientific)
  value <- c(list(schema_version=spec$schema_version,conflict_gate_id=paste0("mcg_",substr(hash,1L,16L))),
             scientific[setdiff(names(scientific),"schema_version")],list(content_sha256=hash))
  p0_publish_json_component(value,p0_component_dir(spec,"conflict_gate",value$conflict_gate_id),
                            "methodology_conflict_gate.json",spec$schemas[["conflict_gate"]])
}

p0_build_final_authority <- function(source_authority, module_contracts, spec) {
  git_state <- p0_source_authority_file(source_authority, "methodology_git_state.json")
  source_set <- p0_source_authority_file(source_authority, "methodology_source_set.json")
  gate <- p0_source_authority_file(source_authority, "methodology_conflict_gate.json")
  training <- build_p0_module_contract("training", source_set, gate, spec)
  downstream <- build_p0_module_contract("downstream", source_set, gate, spec)
  authority <- build_reduced_methodology_authority(git_state, source_set, gate,
                                                    c(module_contracts, training, downstream), spec)
  c(training, downstream, authority)
}
