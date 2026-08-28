p4_contract_paths <- function(root = getwd()) {
  root <- normalizePath(root, mustWork = TRUE)
  cfg <- yaml::read_yaml(file.path(root, "config/p4_deterministic_augmentation.yml"))
  c(config = file.path(root, "config/p4_deterministic_augmentation.yml"),
    vapply(cfg$schemas, function(x) file.path(root, x), character(1L)),
    helper = file.path(root, "R/research_fixed_augmentation_banks.R"),
    canonical_r = file.path(root, "R/research_canonical_config.R"),
    canonical_python = file.path(root, "python/canonical_config.py"),
    rng = file.path(root, "python/p4_deterministic_rng.py"),
    kernel = file.path(root, "python/p4_fixed_augmentation.py"),
    builder = file.path(root, "scripts/p4_build_fixed_bank.py"),
    validator = file.path(root, "scripts/p4_validate_fixed_bank.py"),
    aggregator = file.path(root, "scripts/p4_aggregate_bank.py"),
    smoke = file.path(root, "scripts/p4_smoke.py"),
    runner = file.path(root, "scripts/run_p4_tiered_bank.py"),
    targets = file.path(root, "targets/research_fixed_augmentation_banks.R"))
}

p4_load_spec <- function(files, root = getwd()) {
  files <- normalizePath(files, mustWork = TRUE)
  cfg <- yaml::read_yaml(files[basename(files) == "p4_deterministic_augmentation.yml"])
  schemas <- setNames(vapply(cfg$schemas, function(x) files[basename(files) == basename(x)][[1L]], character(1L)), names(cfg$schemas))
  relative <- sub(paste0("^", normalizePath(root, mustWork = TRUE), "/"), "", files)
  scientific <- grepl("^(config/p4_|config/schemas/p4_|python/(p4_|canonical_config)|scripts/p4_|R/research_canonical_config)", relative) &
    relative != "scripts/run_p4_tiered_bank.py"
  canonical_config_sha256 <- canonical_yaml_sha256(files[basename(files) == "p4_deterministic_augmentation.yml"],
                                                    c("publication_root", "execution"))
  implementation_hash <- p0_scientific_sha256(list(version = cfg$implementation_version,
    files = lapply(which(scientific)[order(relative[scientific], method = "radix")],
                   function(i) list(path = relative[[i]], sha256 = if (basename(files[[i]]) == "p4_deterministic_augmentation.yml") canonical_config_sha256 else sha256_file(files[[i]])))))
  list(config = cfg, files = files, schemas = schemas, implementation_hash = implementation_hash,
       canonical_config_sha256 = canonical_config_sha256,
       raw_config_sha256 = sha256_file(files[basename(files) == "p4_deterministic_augmentation.yml"]))
}

p4_read <- function(paths, name) jsonlite::read_json(artifact_path(paths, name), simplifyVector = FALSE)

p4_build_profile_plan <- function(augmentation_methodology_contract, reduced_methodology_authority, contract_files) {
  spec <- p4_load_spec(contract_files); cfg <- spec$config
  authority <- p4_read(reduced_methodology_authority, "reduced_methodology_authority.json")
  module <- p4_read(augmentation_methodology_contract, "augmentation_methodology_contract.json")
  if (authority$commit_sha != cfg$dissertation_commit || authority$overall_status != "PASS" ||
      module$status != "PASS" ||
      module$canonical_contract$geometry$maximum_attempts_per_entity != 10L ||
      !isTRUE(module$canonical_contract$geometry$failure_keeps_original_geometry))
    stop("P4 authority supplement conflicts with immutable methodology", call. = FALSE)
  expected <- list(
    weak_0.5x = c(.5,.05,.10,.5,.5,.05,.05,.05,.05,.5),
    main_1.0x = c(1,.10,.20,1,1,.10,.10,.10,.10,1),
    strong_2.0x = c(2,.20,.40,2,2,.20,.20,.20,.20,2))
  fields <- c("scale","removal_fraction","jitter_probability","jitter_displacement_m","simplification_tolerance_m",
              "categorical_mask_probability","categorical_replacement_probability","lane_probability","landcover_mask_fraction","dem_noise_sd_m")
  for (profile in cfg$profiles) if (!identical(as.numeric(unlist(profile[fields])), expected[[profile$profile_id]]))
    stop("P4 dissertation profile parameter mismatch: ", profile$profile_id, call. = FALSE)
  scientific <- list(supplement_version = cfg$supplement_version, authority_id = authority$authority_id,
    dissertation_commit = authority$commit_sha, augmentation_contract_id = module$contract_id, profiles = cfg$profiles,
    fixed_parameters = cfg$fixed_parameters, banks = cfg$banks, seed = cfg$seed,
    removal = cfg$removal, receiver_absorption = cfg$receiver_absorption,
    operation_order = cfg$operation_order, implementation_hash = spec$implementation_hash,
    canonical_config_sha256 = spec$canonical_config_sha256)
  hash <- p0_scientific_sha256(scientific); value <- c(list(schema_version=cfg$schema_version,
    supplement_version=cfg$supplement_version,status="PASS",profile_plan_id=paste0("app_",substr(hash,1L,24L)),
    authority_id=authority$authority_id,physical_k=16L,default_k=8L,content_sha256=hash,
    raw_config_sha256=spec$raw_config_sha256), scientific[c("dissertation_commit","augmentation_contract_id","profiles","fixed_parameters","banks","seed","removal","receiver_absorption","operation_order","implementation_hash","canonical_config_sha256")])
  root <- file.path(cfg$publication_root,"contracts",value$profile_plan_id)
  p1_publish_immutable_bundle(root,"augmentation_profile_plan.json",function(stage){
    path <- write_json_file(value,file.path(stage,"augmentation_profile_plan.json")); validate_json_schema_file(path,spec$schemas[["profile_plan"]])
  })
}

p4_run_smoke <- function(mode, profile_plan, original_scene_dataset_acceptance, contract_files) {
  spec <- p4_load_spec(contract_files); profile <- p4_read(profile_plan,"augmentation_profile_plan.json")
  p3 <- p4_read(original_scene_dataset_acceptance,"original_scene_dataset_acceptance.json")
  if(profile$status!="PASS"||p3$status!="PASS")stop("P4 smoke parent mismatch",call.=FALSE)
  key <- p0_scientific_sha256(list(mode=mode,profile=profile$content_sha256,p3=p3$aggregate_content_sha256,implementation=spec$implementation_hash))
  name <- if(mode=="road")"road_link_absorption_smoke.json" else "geometry_consistency_smoke.json"
  root <- file.path(spec$config$publication_root,"smoke",paste0("p4s_",substr(key,1L,24L)))
  p1_publish_immutable_bundle(root,name,function(stage){
    output <- file.path(stage,name); result <- system2(research_python_executable(),c(spec$files[basename(spec$files)=="p4_smoke.py"],"--mode",mode,"--output",output),stdout=TRUE,stderr=TRUE)
    if((attr(result,"status") %||% 0L)!=0L)stop("P4 smoke failed: ",paste(result,collapse=" | "),call.=FALSE)
    value <- jsonlite::read_json(output,simplifyVector=FALSE); value$smoke_id <- paste0("p4s_",substr(key,1L,24L)); value$mode<-mode; value$content_sha256<-key
    write_json_file(value,output)
  })
}

p4_parent_tar_records <- function(shard_files) {
  lapply(shard_files, function(paths) {
    manifest_path <- artifact_path(paths,"shard_manifest.json"); manifest <- jsonlite::read_json(manifest_path,simplifyVector=FALSE)
    payload <- artifact_path(paths,manifest$payload$filename)
    list(branch_id=manifest$branch_id,path=payload,sha256=manifest$payload$sha256,scene_ids=manifest$scene_ids)
  })
}

p4_build_bank_plan <- function(profile_plan, road_smoke, geometry_smoke, original_scene_serialization_shard,
                               original_scene_dataset_acceptance, contract_files) {
  spec<-p4_load_spec(contract_files);cfg<-spec$config;profile<-p4_read(profile_plan,"augmentation_profile_plan.json")
  p3<-p4_read(original_scene_dataset_acceptance,"original_scene_dataset_acceptance.json")
  if(p3$status!="PASS"||
     p4_read(road_smoke,"road_link_absorption_smoke.json")$status!="PASS"||p4_read(geometry_smoke,"geometry_consistency_smoke.json")$status!="PASS")
    stop("P4 bank-plan gate mismatch",call.=FALSE)
  parents<-p4_parent_tar_records(original_scene_serialization_shard);parents<-parents[order(vapply(parents,`[[`,character(1L),"branch_id"),method="radix")]
  resource_spec<-list(parent_tars=vapply(parents,`[[`,character(1L),"path"),cache_id=p3$cache_id,implementation_hash=spec$implementation_hash)
  temp_spec<-tempfile(fileext=".json");temp_resources<-tempfile(fileext=".json");write_json_file(resource_spec,temp_spec)
  result<-system2(research_python_executable(),c(spec$files[basename(spec$files)=="p4_build_fixed_bank.py"],"resources","--spec",temp_spec,"--output",temp_resources),stdout=TRUE,stderr=TRUE)
  unlink(temp_spec);if((attr(result,"status")%||%0L)!=0L)stop("P4 resource scan failed: ",paste(result,collapse=" | "),call.=FALSE)
  resources<-jsonlite::read_json(temp_resources,simplifyVector=FALSE);if(resources$training_scene_count!=2421L)stop("P4 training scene resource coverage failed",call.=FALSE)
  scientific<-list(profile_plan_hash=profile$content_sha256,cache_id=p3$cache_id,cache_acceptance_id=p3$acceptance_id,
    parents=lapply(parents,function(x)x[c("branch_id","sha256")]),resources=p0_scientific_sha256(resources),implementation_hash=spec$implementation_hash)
  fingerprint<-p0_scientific_sha256(scientific);bank_id<-paste0("augbank_",substr(fingerprint,1L,24L));plan_id<-paste0("abp_",substr(p0_scientific_sha256(list(bank_id,"plan")),1L,24L))
  root<-file.path(cfg$publication_root,bank_id);plan_dir<-file.path(root,"plans",plan_id);resources_name="training_resources.json"
  branches<-list();index<-0L
  for(prof in cfg$profiles)for(parent in parents){scenes<-unlist(resources$branch_training_scenes[[parent$branch_id]],use.names=FALSE);if(!length(scenes))next
    index<-index+1L;branch_id<-paste0("ab_",substr(p0_scientific_sha256(list(bank_id,prof$profile_id,parent$branch_id)),1L,24L))
    branches[[index]]<-list(schema_version=cfg$schema_version,bank_id=bank_id,plan_id=plan_id,branch_id=branch_id,profile=prof,
      cache_id=p3$cache_id,cache_acceptance_id=p3$acceptance_id,parent_branch_id=parent$branch_id,parent_tar=parent$path,parent_tar_sha256=parent$sha256,
      scene_ids=sort(scenes,method="radix"),implementation_hash=spec$implementation_hash,
      output_directory=file.path(root,"shards",prof$profile_id,branch_id),execution_pass="A",requested_workers=40L)
  }
  if(length(branches)!=288L||sum(vapply(branches,function(x)length(x$scene_ids),integer(1L)))!=7263L)stop("P4 branch plan coverage failed",call.=FALSE)
  plan<-list(schema_version=cfg$schema_version,status="PASS",supplement_version=cfg$supplement_version,bank_id=bank_id,plan_id=plan_id,parent_cache_id=p3$cache_id,parent_acceptance_id=p3$acceptance_id,
    scene_count=2421L,profile_count=3L,branch_count=288L,expected_candidates=116208L,
    branches=lapply(branches,function(x)list(branch_id=x$branch_id,profile_id=x$profile$profile_id,parent_branch_id=x$parent_branch_id,scene_ids=x$scene_ids)),scientific_fingerprint=fingerprint,implementation_hash=spec$implementation_hash)
  names<-c("augmentation_bank_plan.json",resources_name,paste0("spec-",vapply(branches,`[[`,character(1L),"branch_id"),".json"))
  paths<-p1_publish_immutable_bundle(plan_dir,names,function(stage){
    path<-write_json_file(plan,file.path(stage,names[[1L]]));validate_json_schema_file(path,spec$schemas[["bank_plan"]]);file.copy(temp_resources,file.path(stage,resources_name))
    for(i in seq_along(branches)){branches[[i]]$resources_path<-file.path(plan_dir,resources_name);write_json_file(branches[[i]],file.path(stage,names[[i+2L]]))}
  });unlink(temp_resources)
  lapply(branches,function(x){x$.path<-paths[basename(paths)==paste0("spec-",x$branch_id,".json")];x$resources_path<-paths[basename(paths)==resources_name];x$.plan_path<-paths[basename(paths)=="augmentation_bank_plan.json"];x})
}

p4_run_tiered_bank <- function(plan, contract_files) {
  spec <- p4_load_spec(contract_files)
  if (length(plan) != 288L) stop("P4 tiered execution requires 288 planned branches", call. = FALSE)
  bank_id <- plan[[1L]]$bank_id
  plan_dir <- dirname(plan[[1L]]$.plan_path)
  bank_root <- dirname(dirname(plan_dir))
  attempt_id <- paste0(format(Sys.time(), "%Y%m%d_%H%M%S"), "_", Sys.getpid())
  execution_root <- file.path(bank_root, "executions", paste0("tiered_", attempt_id))
  dir.create(execution_root, recursive = TRUE, showWarnings = FALSE)
  runner <- spec$files[basename(spec$files) == "run_p4_tiered_bank.py"]
  previous_ledger <- NULL
  ledgers <- character()
  logs <- character()
  passes <- list(A = 40L, B = 10L, C = 5L)
  for (pass_name in names(passes)) {
    if (pass_name != "A") {
      previous <- jsonlite::read_json(previous_ledger, simplifyVector = FALSE)
      retryable <- sum(unlist(previous$status_counts[c("FAILED_NATIVE", "FAILED_RESOURCE", "UNATTEMPTED")], use.names = FALSE))
      if (retryable == 0L) break
    }
    workers <- passes[[pass_name]]
    pass_slug <- tolower(pass_name)
    ledger <- file.path(execution_root, paste0("pass_", pass_slug, "_ledger.json"))
    log <- file.path(execution_root, paste0("pass_", pass_slug, ".log"))
    staging <- file.path(bank_root, "staging", paste0("pass_", pass_slug, "_", workers), attempt_id)
    args <- c(runner, "--plan-dir", plan_dir, "--pass-name", pass_name,
              "--workers", as.character(workers), "--staging-root", staging,
              "--ledger", ledger)
    if (!is.null(previous_ledger)) args <- c(args, "--retry-ledger", previous_ledger)
    status <- system2(research_python_executable(), args, stdout = log, stderr = log)
    if (!file.exists(ledger)) stop("P4 tiered runner did not publish a ledger for Pass ", pass_name, call. = FALSE)
    value <- jsonlite::read_json(ledger, simplifyVector = FALSE)
    if (value$status_counts$FAILED_SCIENTIFIC > 0L || identical(status, 2L))
      stop("P4 Pass ", pass_name, " scientific failure; see ", log, call. = FALSE)
    ledgers <- c(ledgers, ledger); logs <- c(logs, log); previous_ledger <- ledger
  }
  final <- jsonlite::read_json(previous_ledger, simplifyVector = FALSE)
  unresolved <- sum(unlist(final$status_counts[c("FAILED_NATIVE", "FAILED_RESOURCE", "FAILED_SCIENTIFIC", "UNATTEMPTED")], use.names = FALSE))
  if (unresolved != 0L) stop("P4 tiered execution exhausted recovery passes with unresolved branches", call. = FALSE)
  summary <- list(schema_version = "1.0.0", status = "PASS", bank_id = bank_id,
                  plan_id = plan[[1L]]$plan_id, branch_count = 288L,
                  pass_ledgers = basename(ledgers), final_completed = final$status_counts$COMPLETED)
  summary_path <- write_json_file(summary, file.path(execution_root, "tiered_execution_summary.json"))
  normalizePath(c(summary_path, ledgers, logs), mustWork = TRUE)
}

p4_build_bank_shard <- function(plan_branch, contract_files, tiered_execution) {
  spec<-p4_load_spec(contract_files);Sys.setenv(OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",BLIS_NUM_THREADS="1",VECLIB_MAXIMUM_THREADS="1",NUMEXPR_NUM_THREADS="1",GDAL_NUM_THREADS="1",ARROW_NUM_THREADS="1",PYTHONDONTWRITEBYTECODE="1");data.table::setDTthreads(1L)
  summary <- p4_read(tiered_execution, "tiered_execution_summary.json")
  if (summary$status != "PASS" || summary$bank_id != plan_branch$bank_id)
    stop("P4 tiered execution summary does not authorize branch validation", call. = FALSE)
  final<-plan_branch$output_directory;payload<-paste0(plan_branch$branch_id,".tar")
  existing <- file.path(final, c(payload, "branch_manifest.json", "execution.json"))
  if (all(file.exists(existing))) {
    manifest <- jsonlite::read_json(existing[[2L]], simplifyVector = FALSE)
    validate_json_schema_file(existing[[2L]], spec$schemas[["shard"]])
    if (!identical(manifest$branch_id, plan_branch$branch_id) ||
        !identical(manifest$bank_id, plan_branch$bank_id) ||
        !identical(manifest$payload$sha256, sha256_file(existing[[1L]]))) {
      stop("P4 canonical branch identity/checksum mismatch: ", plan_branch$branch_id, call. = FALSE)
    }
    return(normalizePath(existing, mustWork = TRUE))
  }
  stop("P4 tiered execution did not publish canonical branch: ", plan_branch$branch_id, call. = FALSE)
}

p4_validate_bank_shard <- function(shard_files, contract_files) {
  spec<-p4_load_spec(contract_files);manifest<-p4_read(shard_files,"branch_manifest.json");validate_json_schema_file(artifact_path(shard_files,"branch_manifest.json"),spec$schemas[["shard"]])
  output<-tempfile(fileext=".json");result<-system2(research_python_executable(),c(spec$files[basename(spec$files)=="p4_validate_fixed_bank.py"],"--manifest",artifact_path(shard_files,"branch_manifest.json"),"--output",output),stdout=TRUE,stderr=TRUE)
  if((attr(result,"status")%||%0L)!=0L)stop("P4 independent validation failed: ",paste(result,collapse=" | "),call.=FALSE)
  value<-jsonlite::read_json(output,simplifyVector=FALSE);unlink(output);value
}

p4_accept_bank <- function(plan, shard_files, shard_validation, original_scene_dataset_acceptance, contract_files) {
  spec<-p4_load_spec(contract_files);p3<-p4_read(original_scene_dataset_acceptance,"original_scene_dataset_acceptance.json")
  if(length(shard_files)!=288L||length(shard_validation)!=288L||!all(vapply(shard_validation,function(x)x$status=="PASS",logical(1L))))stop("P4 validated branch coverage incomplete",call.=FALSE)
  manifests<-vapply(shard_files,function(x) artifact_path(x,"branch_manifest.json"),character(1L));root<-file.path(spec$config$publication_root,plan[[1L]]$bank_id)
  temp_spec<-tempfile(fileext=".json");temp_accept<-tempfile(fileext=".json");temp_index<-tempfile(fileext=".parquet");temp_index_manifest<-tempfile(fileext=".json")
  write_json_file(list(supplement_version=spec$config$supplement_version,bank_id=plan[[1L]]$bank_id,cache_id=p3$cache_id,cache_acceptance_id=p3$acceptance_id,
                       manifests=unname(manifests),validations=unname(shard_validation)),temp_spec)
  result<-system2(research_python_executable(),c(spec$files[basename(spec$files)=="p4_aggregate_bank.py"],"--spec",temp_spec,"--acceptance",temp_accept,"--index-parquet",temp_index,"--index-manifest",temp_index_manifest),stdout=TRUE,stderr=TRUE)
  unlink(temp_spec);if((attr(result,"status")%||%0L)!=0L)stop("P4 aggregate acceptance failed: ",paste(result,collapse=" | "),call.=FALSE)
  acceptance<-jsonlite::read_json(temp_accept,simplifyVector=FALSE);validate_json_schema_file(temp_accept,spec$schemas[["acceptance"]])
  destination<-file.path(root,"acceptance",acceptance$acceptance_id)
  paths<-p1_publish_immutable_bundle(destination,c("augmentation_bank_acceptance.json","effective_bank_index.parquet","effective_bank_index.json"),function(stage){
    file.copy(temp_accept,file.path(stage,"augmentation_bank_acceptance.json"));file.copy(temp_index,file.path(stage,"effective_bank_index.parquet"));file.copy(temp_index_manifest,file.path(stage,"effective_bank_index.json"))
  });unlink(c(temp_accept,temp_index,temp_index_manifest));paths
}

p4_publish_effective_index <- function(bank_acceptance, contract_files) {
  spec<-p4_load_spec(contract_files);manifest<-p4_read(bank_acceptance,"effective_bank_index.json");validate_json_schema_file(artifact_path(bank_acceptance,"effective_bank_index.json"),spec$schemas[["index"]]);bank_acceptance
}

p4_benchmark_bank <- function(bank_acceptance, effective_index, contract_files) {
  spec<-p4_load_spec(contract_files);accept<-p4_read(bank_acceptance,"augmentation_bank_acceptance.json");index<-p4_read(effective_index,"effective_bank_index.json")
  if(accept$status!="PASS"||index$status!="PASS")stop("P4 benchmark parent rejection",call.=FALSE)
  hash<-p0_scientific_sha256(list(bank=accept$aggregate_content_sha256,index=index$content_sha256,implementation=spec$implementation_hash));value<-list(schema_version=spec$config$schema_version,status="PASS",benchmark_id=paste0("abb_",substr(hash,1L,24L)),bank_id=accept$bank_id,acceptance_id=accept$acceptance_id,index_id=index$index_id,read_validation="PASS",deterministic_pair_access="PASS",content_sha256=hash)
  root<-file.path(spec$config$publication_root,accept$bank_id,"benchmark",value$benchmark_id)
  p1_publish_immutable_bundle(root,"augmentation_bank_benchmark.json",function(stage){path<-write_json_file(value,file.path(stage,"augmentation_bank_benchmark.json"));validate_json_schema_file(path,spec$schemas[["benchmark"]])})
}
