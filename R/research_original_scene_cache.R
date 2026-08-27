p3_original_cache_contract_paths <- function(root = getwd()) {
  root <- normalizePath(root, mustWork = TRUE)
  cfg <- yaml::read_yaml(file.path(root, "config/p3_original_scene_cache.yml"))
  c(config = file.path(root, "config/p3_original_scene_cache.yml"),
    vapply(cfg$schemas, function(x) file.path(root, x), character(1L)),
    helper = file.path(root, "R/research_original_scene_cache.R"),
    writer = file.path(root, "scripts/p3_deterministic_tar.py"),
    validator = file.path(root, "scripts/p3_validate_cache.py"))
}

p3_load_spec <- function(files, root = getwd()) {
  files <- normalizePath(files, mustWork = TRUE)
  cfg <- yaml::read_yaml(files[basename(files) == "p3_original_scene_cache.yml"])
  schemas <- setNames(vapply(cfg$schemas, function(x) files[basename(files) == basename(x)][[1L]], character(1L)), names(cfg$schemas))
  relative <- sub(paste0("^", normalizePath(root, mustWork = TRUE), "/"), "", files)
  implementation_hash <- p0_scientific_sha256(list(
    version = cfg$implementation_version,
    files = lapply(order(relative, method = "radix"), function(i) list(path = relative[[i]], sha256 = sha256_file(files[[i]])))
  ))
  list(config = cfg, files = files, schemas = schemas, implementation_hash = implementation_hash)
}

p3_json <- function(paths, name) jsonlite::read_json(artifact_path(paths, name), simplifyVector = FALSE)

p3_validate_offsets <- function(offsets, values_length) {
  offsets <- as.numeric(offsets); values_length <- as.numeric(values_length)
  if (!length(offsets) || offsets[[1L]] != 0 || anyNA(offsets) || any(!is.finite(offsets)) ||
      any(offsets < 0) || any(diff(offsets) < 0) || tail(offsets, 1L) != values_length ||
      any(offsets != floor(offsets))) stop("Serialization-v3 invalid ragged offsets", call. = FALSE)
  invisible(TRUE)
}

p3_validate_fixture_parity <- function(source, decoded) {
  required <- c("scene_id","split","entity_ids","geometry_wkb","relation_endpoints","relation_types",
                "source_node_ids","source_node_mapping","raster_shape","raster_channels","raster_values","geometry_coordinates")
  if (!all(required %in% names(source)) || !all(required %in% names(decoded))) stop("Serialization-v3 fixture fields missing",call.=FALSE)
  if (!is.double(decoded$geometry_coordinates)) stop("Serialization-v3 geometry float32 downcast",call.=FALSE)
  for (field in required) if (!identical(source[[field]], decoded[[field]])) stop("Serialization-v3 parity mismatch: ",field,call.=FALSE)
  invisible(TRUE)
}

p3_build_contract <- function(original_cache_methodology_contract, reduced_methodology_authority, contract_files) {
  spec <- p3_load_spec(contract_files)
  authority <- p3_json(reduced_methodology_authority, "reduced_methodology_authority.json")
  module <- p3_json(original_cache_methodology_contract, "original_cache_methodology_contract.json")
  cfg <- spec$config
  if (authority$authority_id != cfg$authority_id || authority$overall_status != "PASS" ||
      module$contract_id != cfg$original_cache_contract_id || module$status != "PASS")
    stop("P3 authority/module contract mismatch", call. = FALSE)
  scientific <- list(
    role = "immutable_original_scene_cache", serialization = "Serialization-v3",
    epsg = 5186L, augmented_provenance = FALSE,
    precision = list(geometry = "float64_wkb", scene_coordinates = "float64", source_node_coordinates = "float64"),
    ragged = list(representation = "values_offsets", first_offset = 0L, monotone_non_decreasing = TRUE,
                  terminal_offset_equals_values_length = TRUE, empty_groups = TRUE, source_node_chain_truncation = FALSE),
    ordering = list(scene = "scene_id_radix", entity = "scene_id/entity_type/local_entity_id/source_entity_id_radix",
                    relation = "scene_id/source_local_entity_id/destination_local_entity_id/relation_mask/edge_id_radix",
                    source_node = "scene_id/road_local_entity_id/source_node_position", geometry_parts = "accepted_P2_WKB_order",
                    raster = cfg$serialization$raster_channel_order, shard = "branch_id_radix"),
    container = cfg$serialization$container, compression = cfg$serialization$compression,
    required_payloads = c("scene_spec", "membership", "vector", "scene_raster", "entity_raster_context", "relations", "source_topology"),
    prohibited = c("augmentation", "road_absorption", "model_tensor_conversion", "training", "GPU"),
    implementation_sha256 = spec$implementation_hash
  )
  content <- p0_scientific_sha256(scientific)
  value <- list(schema_version = cfg$schema_version, contract_id = paste0("osc_", substr(content, 1L, 24L)), status = "PASS",
                authority_id = authority$authority_id, module_contract_id = module$contract_id,
                module_contract_hash = module$module_content_sha256, scientific = scientific,
                implementation_sha256 = spec$implementation_hash, content_sha256 = content)
  root <- file.path(cfg$publication_root, "contracts", value$contract_id)
  p1_publish_immutable_bundle(root, "original_scene_cache_contract.json", function(stage) {
    path <- write_json_file(value, file.path(stage, "original_scene_cache_contract.json"))
    validate_json_schema_file(path, spec$schemas[["contract"]])
  })
}

p3_output_groups <- function(branch_id, vector, raster, relation, topology, membership_paths, plan_path) {
  pick <- function(x) x[[which(vapply(x, function(paths) any(grepl(branch_id, paths, fixed = TRUE)), logical(1L)))[[1L]]]]
  v <- pick(vector); r <- pick(raster); e <- pick(relation); t <- pick(topology)
  m <- membership_paths[grepl(branch_id, membership_paths, fixed = TRUE)]
  if (length(m) != 3L) stop("P3 membership branch mapping failed: ", branch_id, call. = FALSE)
  raster_root <- dirname(r[[1L]])
  groups <- list(
    list(prefix = "scene", root = dirname(plan_path), members = basename(plan_path)),
    list(prefix = "membership", root = dirname(m[[1L]]), members = sort(basename(m))),
    list(prefix = "vector", root = dirname(v[[1L]]), members = sort(basename(v)[grepl("observed[.]parquet$", basename(v))])),
    list(prefix = "raster", root = raster_root, members = c("scene_raster_index.parquet", "object_raster_context.parquet", "scene_landcover.zarr", "scene_dem.zarr")),
    list(prefix = "relations", root = dirname(e[[1L]]), members = sort(basename(e)[grepl("[.]parquet$", basename(e))])),
    list(prefix = "topology", root = dirname(t[[1L]]), members = "source_topology.parquet")
  )
  for (g in groups) for (member in g$members) if (!file.exists(file.path(g$root, member))) stop("P3 missing source payload: ", member, call. = FALSE)
  groups
}

p3_build_plan <- function(original_scene_cache_contract, base_spatial_acceptance,
                          base_spatial_observation_plan, base_vector_observation_shard,
                          base_raster_observation_shard, base_relation_graph_shard,
                          base_source_topology_shard, base_spatial_membership_acceptance,
                          contract_files) {
  spec <- p3_load_spec(contract_files); cfg <- spec$config
  contract <- p3_json(original_scene_cache_contract, "original_scene_cache_contract.json")
  p2 <- p3_json(base_spatial_acceptance, "base_spatial_acceptance.json")
  membership <- p3_json(base_spatial_membership_acceptance, "aggregate_membership_manifest.json")
  checks <- c(contract$status == "PASS", p2$status == "PASS", p2$acceptance_id == cfg$base_spatial_acceptance_id,
              p2$original_observation_id == cfg$original_observation_id, p2$scene_count == 4421L,
              length(base_spatial_observation_plan) == cfg$sharding$expected_shards)
  if (!all(checks)) stop("P3 accepted P2 parent mismatch", call. = FALSE)
  plans <- base_spatial_observation_plan[order(vapply(base_spatial_observation_plan, `[[`, character(1L), "branch_id"), method = "radix")]
  parent_records <- lapply(plans, function(x) list(branch_id = x$branch_id, scene_ids = x$scene_ids,
    scene_spec_sha256 = sha256_file(x$.path)))
  scientific <- list(schema_version = cfg$schema_version, authority_id = cfg$authority_id,
    contract_id = contract$contract_id, contract_hash = contract$content_sha256,
    scene_index_id = cfg$scene_index_id, scene_acceptance_id = cfg$scene_acceptance_id,
    base_spatial_acceptance_id = p2$acceptance_id, base_spatial_acceptance_sha256 = sha256_file(artifact_path(base_spatial_acceptance, "base_spatial_acceptance.json")),
    original_observation_id = p2$original_observation_id, sharding = cfg$sharding,
    ordered_branches = parent_records, implementation_hash = spec$implementation_hash)
  fingerprint <- p0_scientific_sha256(scientific)
  cache_id <- paste0("oscache_", substr(fingerprint, 1L, 24L)); plan_id <- paste0("ocp_", substr(p0_scientific_sha256(list(cache_id, "plan")), 1L, 24L))
  root <- file.path(cfg$publication_root, cache_id)
  branches <- lapply(seq_along(plans), function(i) {
    x <- plans[[i]]; branch_id <- x$branch_id
    groups <- p3_output_groups(branch_id, base_vector_observation_shard, base_raster_observation_shard,
                               base_relation_graph_shard, base_source_topology_shard,
                               unlist(membership$membership_parquets), x$.path)
    list(schema_version = cfg$schema_version, cache_id = cache_id, plan_id = plan_id, branch_id = branch_id,
         shard_ordinal = i - 1L, scene_ids = x$scene_ids, split_counts = x$split_counts,
         source_groups = groups,
         output = list(directory = file.path(root, "shards", branch_id), payload = paste0(branch_id, ".tar")),
         execution = list(pass = "A", requested_workers = cfg$execution$pass_a_workers, threads = 1L))
  })
  plan <- list(schema_version = cfg$schema_version, plan_id = plan_id, cache_id = cache_id, status = "PASS",
               authority_id = cfg$authority_id, contract_id = contract$contract_id,
               base_spatial_acceptance_id = p2$acceptance_id, original_observation_id = p2$original_observation_id,
               scene_count = 4421L, split_counts = list(training = 2421L, validation = 400L, evaluation = 1600L),
               shard_count = length(branches), ordering = cfg$sharding$ordering,
               branches = lapply(branches, function(x) list(branch_id=x$branch_id, shard_ordinal=x$shard_ordinal, scene_ids=x$scene_ids, split_counts=x$split_counts)),
               scientific_fingerprint = fingerprint, implementation_hash = spec$implementation_hash)
  plan_dir <- file.path(root, "plans", plan_id)
  names <- c("original_scene_serialization_plan.json", paste0("spec-", vapply(branches, `[[`, character(1L), "branch_id"), ".json"))
  paths <- p1_publish_immutable_bundle(plan_dir, names, function(stage) {
    path <- write_json_file(plan, file.path(stage, names[[1L]])); validate_json_schema_file(path, spec$schemas[["plan"]])
    for (i in seq_along(branches)) write_json_file(branches[[i]], file.path(stage, names[[i + 1L]]))
  })
  lapply(branches, function(x) { x$.path <- paths[basename(paths) == paste0("spec-", x$branch_id, ".json")]; x$.plan_path <- paths[basename(paths) == "original_scene_serialization_plan.json"]; x })
}

p3_build_shard <- function(plan_branch, contract_files) {
  spec <- p3_load_spec(contract_files); cfg <- spec$config
  Sys.setenv(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", BLIS_NUM_THREADS="1",
             VECLIB_MAXIMUM_THREADS="1", NUMEXPR_NUM_THREADS="1", GDAL_NUM_THREADS="1", ARROW_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
  data.table::setDTthreads(1L); started <- Sys.time(); final <- plan_branch$output$directory
  publish_deterministic_directory(final, c(plan_branch$output$payload, "shard_manifest.json", "execution.json"),
    compare_basenames = c(plan_branch$output$payload, "shard_manifest.json"), writer = function(stage) {
      raw_manifest <- file.path(stage, "raw_manifest.json")
      status <- system2(research_python_executable(), c(spec$files[basename(spec$files)=="p3_deterministic_tar.py"], "--spec", plan_branch$.path,
        "--output", file.path(stage, plan_branch$output$payload), "--manifest", raw_manifest), stdout=TRUE, stderr=TRUE)
      if ((attr(status,"status") %||% 0L) != 0L) stop("P3 shard writer failed: ", paste(status, collapse=" | "), call.=FALSE)
      raw <- jsonlite::read_json(raw_manifest, simplifyVector=FALSE); unlink(raw_manifest)
      logical <- p0_scientific_sha256(raw$members)
      manifest <- list(schema_version=cfg$schema_version,status="PASS",cache_id=plan_branch$cache_id,plan_id=plan_branch$plan_id,
        branch_id=plan_branch$branch_id,shard_ordinal=plan_branch$shard_ordinal,scene_ids=plan_branch$scene_ids,split_counts=plan_branch$split_counts,
        payload=raw$payload,members=raw$members,logical_content_sha256=logical,
        validation=list(member_roundtrip="PASS",geometry_precision="float64_wkb",source_node_chain="variable_length_values_offsets",augmentation_present=FALSE))
      path <- write_json_file(manifest,file.path(stage,"shard_manifest.json")); validate_json_schema_file(path,spec$schemas[["shard"]])
      write_json_file(list(pass="A",workers=cfg$execution$pass_a_workers,threads=1L,started_at=format(started,tz="UTC",usetz=TRUE),
        finished_at=format(Sys.time(),tz="UTC",usetz=TRUE),wall_seconds=as.numeric(difftime(Sys.time(),started,units="secs")),pid=Sys.getpid()),file.path(stage,"execution.json"))
    })
}

p3_validate_shard <- function(shard_files, contract_files) {
  spec <- p3_load_spec(contract_files); manifest <- p3_json(shard_files, "shard_manifest.json")
  validate_json_schema_file(artifact_path(shard_files,"shard_manifest.json"), spec$schemas[["shard"]])
  payload <- artifact_path(shard_files, manifest$payload$filename)
  if (sha256_file(payload) != manifest$payload$sha256 || unname(file.info(payload)$size) != manifest$payload$size_bytes) stop("P3 payload checksum mismatch",call.=FALSE)
  out <- tempfile(fileext=".json")
  status <- system2(research_python_executable(), c(spec$files[basename(spec$files)=="p3_validate_cache.py"],"--payload",payload,
    "--manifest",artifact_path(shard_files,"shard_manifest.json"),"--output",out),stdout=TRUE,stderr=TRUE)
  if ((attr(status,"status") %||% 0L) != 0L) stop("P3 independent shard validation failed: ",paste(status,collapse=" | "),call.=FALSE)
  value <- jsonlite::read_json(out,simplifyVector=FALSE); unlink(out); value
}

p3_build_roundtrip <- function(plan, shard_files, shard_validation, contract_files) {
  spec <- p3_load_spec(contract_files); validations <- lapply(shard_files,p3_validate_shard,contract_files=contract_files)
  if (length(shard_validation) != length(shard_files) || !all(vapply(shard_validation,function(x)x$status=="PASS",logical(1L)))) stop("P3 structural shard validation incomplete",call.=FALSE)
  manifests <- lapply(shard_files,p3_json,name="shard_manifest.json")
  branches <- vapply(manifests,`[[`,character(1L),"branch_id"); planned <- vapply(plan,`[[`,character(1L),"branch_id")
  scenes <- unlist(lapply(manifests,`[[`,"scene_ids"),use.names=FALSE)
  if (!setequal(unname(branches),unname(planned)) || length(scenes)!=4421L || anyDuplicated(scenes)) stop("P3 shard/scene coverage mismatch",call.=FALSE)
  value <- list(schema_version=spec$config$schema_version,status="PASS",cache_id=plan[[1L]]$cache_id,
    shard_count=length(manifests),scene_count=length(scenes),exact_member_byte_parity=TRUE,
    geometry_float64_binary_equality=TRUE,raster_payload_byte_equality=TRUE,relation_endpoint_type_byte_equality=TRUE,
    source_topology_byte_equality=TRUE,offset_contract=TRUE,all_shards_independently_read=all(vapply(validations,function(x)x$status=="PASS",logical(1L))),
    logical_content_sha256=p0_scientific_sha256(lapply(manifests,function(x)list(branch_id=x$branch_id,hash=x$logical_content_sha256))))
  root <- file.path(spec$config$publication_root,plan[[1L]]$cache_id,"validation",paste0("rtv_",substr(value$logical_content_sha256,1L,24L)))
  p1_publish_immutable_bundle(root,"original_scene_geometry_roundtrip.json",function(stage) write_json_file(value,file.path(stage,"original_scene_geometry_roundtrip.json")))
}

p3_build_index <- function(plan, shard_files, roundtrip, contract_files) {
  spec <- p3_load_spec(contract_files); rt <- p3_json(roundtrip,"original_scene_geometry_roundtrip.json")
  manifests <- lapply(shard_files,p3_json,name="shard_manifest.json")
  rows <- data.table::rbindlist(lapply(manifests,function(x)data.table::data.table(scene_id=unlist(x$scene_ids),branch_id=x$branch_id,
    shard_ordinal=as.integer(x$shard_ordinal),cache_id=x$cache_id,payload_filename=x$payload$filename,payload_sha256=x$payload$sha256)))
  data.table::setorder(rows,scene_id); if(nrow(rows)!=4421L||anyDuplicated(rows$scene_id)||rt$status!="PASS")stop("P3 cache index failed",call.=FALSE)
  hash <- p0_scientific_sha256(as.list(rows)); id <- paste0("oci_",substr(hash,1L,24L)); root <- file.path(spec$config$publication_root,plan[[1L]]$cache_id,"index",id)
  p1_publish_immutable_bundle(root,c("scene_to_shard.parquet","index_manifest.json"),function(stage){
    arrow::write_parquet(rows,file.path(stage,"scene_to_shard.parquet"),compression="zstd",use_dictionary=TRUE)
    write_json_file(list(schema_version=spec$config$schema_version,status="PASS",index_id=id,cache_id=plan[[1L]]$cache_id,scene_count=nrow(rows),content_sha256=hash),file.path(stage,"index_manifest.json"))
  })
}

p3_build_cache_manifest <- function(plan, shard_files, index, roundtrip, base_spatial_acceptance, contract_files) {
  spec<-p3_load_spec(contract_files); manifests<-lapply(shard_files,p3_json,name="shard_manifest.json"); rt<-p3_json(roundtrip,"original_scene_geometry_roundtrip.json")
  p2<-p3_json(base_spatial_acceptance,"base_spatial_acceptance.json"); idx<-p3_json(index,"index_manifest.json")
  ordered<-manifests[order(vapply(manifests,`[[`,character(1L),"branch_id"),method="radix")]
  aggregate<-p0_scientific_sha256(list(cache_id=plan[[1L]]$cache_id,shards=lapply(ordered,function(x)list(branch_id=x$branch_id,payload=x$payload$sha256,logical=x$logical_content_sha256)),index=idx$content_sha256,roundtrip=rt$logical_content_sha256))
  value<-list(schema_version=spec$config$schema_version,status="PASS",cache_id=plan[[1L]]$cache_id,authority_id=spec$config$authority_id,
    scene_index_id=spec$config$scene_index_id,scene_acceptance_id=spec$config$scene_acceptance_id,base_spatial_acceptance_id=p2$acceptance_id,
    original_observation_id=p2$original_observation_id,scene_count=4421L,split_counts=list(training=2421L,validation=400L,evaluation=1600L),
    shard_count=length(ordered),shards=lapply(ordered,function(x)list(branch_id=x$branch_id,scene_ids=x$scene_ids,payload=x$payload,logical_content_sha256=x$logical_content_sha256)),
    index_id=idx$index_id,roundtrip_status=rt$status,total_payload_bytes=sum(vapply(ordered,function(x)x$payload$size_bytes,numeric(1L))),aggregate_content_sha256=aggregate)
  root<-file.path(spec$config$publication_root,plan[[1L]]$cache_id,"manifests")
  p1_publish_immutable_bundle(root,"original_scene_cache_manifest.json",function(stage)write_json_file(value,file.path(stage,"original_scene_cache_manifest.json")))
}

p3_accept_dataset <- function(plan, shard_files, roundtrip, index, cache_manifest, base_spatial_acceptance, contract_files) {
  spec<-p3_load_spec(contract_files); cache<-p3_json(cache_manifest,"original_scene_cache_manifest.json"); p2<-p3_json(base_spatial_acceptance,"base_spatial_acceptance.json")
  rt<-p3_json(roundtrip,"original_scene_geometry_roundtrip.json"); idx<-p3_json(index,"index_manifest.json")
  relations<-p2$relation_counts
  expected<-list(SN=45515296L,CNT=2014337L,WIT=2014337L,INT=698310L,CON=468520L)
  actual<-setNames(vapply(names(expected),function(n)as.numeric(relations[[n]]),numeric(1L)),names(expected))
  if(!all(actual == unlist(expected,use.names=TRUE))||cache$scene_count!=4421L||cache$shard_count!=96L||rt$status!="PASS"||idx$scene_count!=4421L)stop("P3 production acceptance invariant failed",call.=FALSE)
  scientific<-list(cache_id=cache$cache_id,aggregate=cache$aggregate_content_sha256,parent=p2$acceptance_id,relation_counts=as.list(actual),schema_version=spec$config$schema_version)
  hash<-p0_scientific_sha256(scientific); id<-paste0("osca_",substr(hash,1L,24L))
  value<-list(schema_version=spec$config$schema_version,acceptance_id=id,cache_id=cache$cache_id,status="PASS",authority_id=spec$config$authority_id,
    base_spatial_acceptance_id=p2$acceptance_id,original_observation_id=p2$original_observation_id,scene_count=4421L,
    split_counts=list(training=2421L,validation=400L,evaluation=1600L),shard_count=96L,relation_counts=as.list(actual),
    entity_counts=p2$entity_counts,topology=p2$topology,roundtrip=list(status=rt$status,all_scenes=TRUE,exact_member_byte_parity=TRUE,source_topology=TRUE),
    aggregate_content_sha256=cache$aggregate_content_sha256,scientific_fingerprint=hash)
  root<-file.path(spec$config$publication_root,cache$cache_id,"acceptance",id)
  p1_publish_immutable_bundle(root,"original_scene_dataset_acceptance.json",function(stage){path<-write_json_file(value,file.path(stage,"original_scene_dataset_acceptance.json"));validate_json_schema_file(path,spec$schemas[["acceptance"]])})
}
