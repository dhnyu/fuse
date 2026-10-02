# Stage A orchestration only; accepted P2/P3 -> independent experimental products.
# Scientific references: dissertation 3.1, 3.3; design report sections 5-9/12-15.
b6_read_json <- function(p) jsonlite::read_json(p,simplifyVector=FALSE)
b6_write_json <- function(x,p) writeLines(b6_json(x),p,useBytes=TRUE)
b6_safe_root <- function(root) {
  expected<-"/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity"
  if(!identical(root,expected)) stop("B6 experimental output namespace only")
  p<-root
  while(!dir.exists(p)) p<-dirname(p)
  if(normalizePath(p,mustWork=TRUE)!=p) stop("B6 symlink root forbidden")
  root
}
b6_source_paths <- function() c("R/b6_road_segmentation.R","R/b6_road_relations.R","R/b6_stage_a.R",
 "R/b6_diagnostics.R","python/b6_artifact_audit.py","R/spatial_relations.R","config/relation_graph.yml","config/b6_road_granularity.yml","config/schemas/b6_road_granularity.schema.json",
 "targets/b6_road_granularity.R","_targets_b6_road_granularity.R")
b6_config <- function(paths) {
  cfg<-yaml::read_yaml("config/b6_road_granularity.yml")
  jsonvalidate::json_validate(b6_json(cfg),"config/schemas/b6_road_granularity.schema.json",engine="ajv",error=TRUE)
  stopifnot(isTRUE(cfg$no_training),isTRUE(cfg$no_canonical_publication),identical(cfg$scales,c("Original","S100","S50","S25")),
    cfg$resources$workers>=1,cfg$resources$workers<=40,cfg$resources$threads==1,cfg$sn$radius_m==100,cfg$sn$top_k==16,cfg$sn$quantization_m==1e-9,
    cfg$tolerance$coordinate_m==1e-7,cfg$tolerance$length_absolute_m==1e-7,cfg$tolerance$measure_relative==1e-10,
    cfg$position_grid_m==50,identical(cfg$store,"/mnt/hdd002/dhnyu/fusedata/targets/fuse-b6-road-granularity-stage-a"))
  b6_safe_root(cfg$output_root)
  cfg$source_hashes<-as.list(setNames(vapply(paths,b6_file_hash,character(1)),paths))
  cfg$design_id<-paste0("b6a_",substr(b6_hash(b6_json(cfg)),1,24));cfg$root<-file.path(cfg$output_root,cfg$design_id)
  cfg
}
b6_publish <- function(cfg,name,build) {
  b6_safe_root(cfg$output_root)
  if(!identical(cfg$root,file.path(cfg$output_root,cfg$design_id)) || !grepl("^b6a_[a-f0-9]{24}$",cfg$design_id)) stop("B6 root identity")
  dir.create(cfg$root,recursive=TRUE,showWarnings=FALSE)
  destination<-file.path(cfg$root,name)
  if(dir.exists(destination)) {
    manifest<-b6_read_json(file.path(destination,"manifest.json"))
    paths<-vapply(manifest$files,function(x) {
      p<-file.path(destination,x$name);if(!file.exists(p)||b6_file_hash(p)!=x$sha256) stop("B6 immutable collision/corruption");p
    },character(1))
    return(c(paths,file.path(destination,"manifest.json")))
  }
  stage<-tempfile(paste0(".stage-",name,"-"),tmpdir=cfg$root);dir.create(stage)
  on.exit(if(dir.exists(stage)) unlink(stage,recursive=TRUE),add=TRUE)
  build(stage)
  files<-sort(list.files(stage,full.names=TRUE));if(!length(files)) stop("B6 empty publication")
  if(sum(file.info(files)$size)>cfg$resources$maximum_output_bytes) stop("B6 output budget")
  manifest<-list(design_id=cfg$design_id,status="PASS",files=lapply(files,function(p) list(name=basename(p),size_bytes=file.info(p)$size,sha256=b6_file_hash(p))))
  b6_write_json(manifest,file.path(stage,"manifest.json"))
  if(!file.rename(stage,destination)) stop("B6 immutable publish failed")
  c(file.path(destination,basename(files)),file.path(destination,"manifest.json"))
}
b6_path <- function(paths,name) {p<-paths[basename(paths)==name];stopifnot(length(p)==1,file.exists(p));p}
b6_parent_check <- function(cfg) {
  stopifnot(b6_file_hash(cfg$parent$statistics)==cfg$parent$statistics_sha256)
  p2<-b6_read_json(cfg$parent$p2_acceptance);p3<-b6_read_json(cfg$parent$p3_acceptance)
  stopifnot(p2$status=="PASS",p3$status=="PASS",p3$base_spatial_acceptance_id==p2$acceptance_id,p3$scene_count==12421)
  paths<-unlist(cfg$parent[c("p2_acceptance","p3_acceptance","statistics")])
  b6_publish(cfg,"parents",function(stage) b6_write_json(list(p2=p2$acceptance_id,p3=p3$acceptance_id,
    hashes=as.list(setNames(vapply(paths,b6_file_hash,character(1)),paths))),file.path(stage,"parents.json")))
}
b6_sampling <- function(cfg,parents) {
  b6_path(parents,"parents.json")
  d<-data.table::as.data.table(arrow::read_parquet(cfg$parent$statistics));x<-d[split=="training"]
  x[,stratum:=ifelse(road_count==0,"0",ifelse(road_count<=8,"1-8",ifelse(road_count<=49,"9-49","50+")))]
  x[,sample_hash:=vapply(scene_id,function(s) b6_hash(paste(cfg$sampling$namespace,cfg$sampling$seed,s,sep="|")),character(1))]
  data.table::setorder(x,sample_hash,scene_id);chosen<-x[,head(.SD,cfg$sampling$per_stratum),by=stratum]
  if(nrow(chosen)<32) chosen<-data.table::rbindlist(list(chosen,head(x[!scene_id%in%chosen$scene_id],32-nrow(chosen))),use.names=TRUE)
  data.table::setorder(chosen,stratum,sample_hash)
  stopifnot(nrow(chosen)==32,!anyDuplicated(chosen$scene_id),all(chosen$split=="training"))
  b6_publish(cfg,"selection",function(stage) arrow::write_parquet(chosen,file.path(stage,"pilot_scenes.parquet"),compression="zstd"))
}
b6_stress <- function(cfg,parents,selection) {
  b6_path(parents,"parents.json");pilot<-arrow::read_parquet(b6_path(selection,"pilot_scenes.parquet"))
  # Training-only census of cheap road metadata; geometry stress is searched within
  # the bounded pilot plus these extreme metadata candidates, never evaluation.
  files<-sort(list.files(file.path(cfg$parent$p2_root,"vector/branches"),pattern="road_observed.parquet",recursive=TRUE,full.names=TRUE))
  rows<-data.table::rbindlist(lapply(files,function(p) {
    d<-data.table::as.data.table(arrow::read_parquet(p,col_select=c("scene_id","split","source_entity_id","observed_length_m","observed_component_count","is_clipped")))
    d[split=="training"]
  }))
  data.table::setorder(rows,scene_id,source_entity_id)
  stats<-data.table::as.data.table(arrow::read_parquet(cfg$parent$statistics))[split=="training"]
  pick<-function(tag,ids) data.table::data.table(tag=tag,scene_id=if(length(ids)) sort(unique(ids))[1] else NA_character_,scope="training_metadata_census")
  stress<-data.table::rbindlist(list(pick("longest_parent",rows[observed_length_m==max(observed_length_m),scene_id]),
    pick("highest_road_count",stats[road_count==max(road_count),scene_id]),pick("most_multipart",rows[observed_component_count==max(observed_component_count),scene_id]),
    pick("boundary_clipping",rows[is_clipped==TRUE,scene_id]),pick("zero_roads",stats[road_count==0,scene_id])))
  # Remaining adversarial cases have mandatory synthetic fixtures; real examples
  # are discovered and tagged in the selected-scene diagnostics.
  stress<-data.table::rbindlist(list(stress,data.table::data.table(tag=c("loop_retracing","high_degree_junction","shared_outside_node","tied_SN","more_than_16_siblings"),scene_id=NA_character_,scope="fixture_plus_selected_scene_search")))
  b6_publish(cfg,"stress",function(stage) arrow::write_parquet(stress,file.path(stage,"stress_scenes.parquet"),compression="zstd"))
}
b6_extract <- function(cfg,parents,selection,stress) {
  b6_path(parents,"parents.json")
  pilot<-data.table::as.data.table(arrow::read_parquet(b6_path(selection,"pilot_scenes.parquet")))
  stress_rows<-data.table::as.data.table(arrow::read_parquet(b6_path(stress,"stress_scenes.parquet")))
  wanted<-sort(unique(c(pilot$scene_id,na.omit(stress_rows$scene_id))))
  manifest<-b6_read_json(file.path(cfg$parent$p3_root,"manifests/original_scene_cache_manifest.json"))
  b6_publish(cfg,"inputs",function(stage) {
    receipts<-list();scenes<-list()
    for(shard in manifest$shards) {
      ids<-intersect(unlist(shard$scene_ids),wanted);if(!length(ids)) next
      root<-file.path(cfg$parent$p3_root,"shards",shard$branch_id);sm<-b6_read_json(file.path(root,"shard_manifest.json"))
      stopifnot(sm$status=="PASS",sm$payload$sha256==shard$payload$sha256)
      tar<-file.path(root,shard$payload$filename)
      if(b6_file_hash(tar)!=shard$payload$sha256) stop("B6 P3 checksum")
      names<-c("vector/building_observed.parquet","vector/road_observed.parquet","vector/poi_observed.parquet", "relations/relation_edges.parquet","relations/relation_node_index.parquet","topology/source_topology.parquet",paste0("scene/spec-",shard$branch_id,".json"))
      tmp<-tempfile("b6-read-");dir.create(tmp)
      utils::untar(tar,files=names,exdir=tmp)
      tables<-list()
      for(name in names) {
        rec<-Filter(function(x) x$path==name,sm$members)[[1]];p<-file.path(tmp,name)
        if(b6_file_hash(p)!=rec$sha256) stop("B6 P3 member checksum")
        receipts[[length(receipts)+1L]]<-list(path=tar,member=name,sha256=rec$sha256,tar_sha256=shard$payload$sha256)
        if(grepl("parquet$",name)) {d<-data.table::as.data.table(arrow::read_parquet(p));tables[[name]]<-d[scene_id%in%ids]}
      }
      spec<-b6_read_json(file.path(tmp,tail(names,1)))
      for(id in ids) {
        roles<-lapply(c("building","road","poi"),function(role) {
          d<-tables[[paste0("vector/",role,"_observed.parquet")]][scene_id==id]
          g<-sf::st_as_sfc(structure(as.list(d$observed_geometry),class="WKB"),crs=5186)
          d[,observed_geometry:=NULL];sf::st_sf(as.data.frame(d),geometry=g)
        });names(roles)<-c("building","road","poi")
        ss<-Filter(function(x) x$scene_id==id,spec$scenes)[[1]]
        entities<-relation_scene_sf(relation_entity_table(roles));top<-tables[["topology/source_topology.parquet"]][scene_id==id]
        bounds<-as.numeric(unlist(ss[c("xmin","ymin","xmax","ymax")]))
        incidence<-top[source_node_x_5186>=bounds[1]&source_node_x_5186<=bounds[3]&source_node_y_5186>=bounds[2]&source_node_y_5186<=bounds[4],.(local_entity_id=as.integer(road_local_entity_id),node_id=source_node_id)]
        scenes[[id]]<-list(id=id,entities=entities,roles=roles,topology=top,bounds=bounds,
          incidence=unique(incidence),edges=tables[["relations/relation_edges.parquet"]][scene_id==id],
          nodes=tables[["relations/relation_node_index.parquet"]][scene_id==id],
          group=if(id%in%pilot$scene_id) "pilot" else "stress")
      }
      unlink(tmp,recursive=TRUE)
    }
    stopifnot(setequal(names(scenes),wanted))
    saveRDS(scenes[sort(names(scenes))],file.path(stage,"scenes.rds"),compress=FALSE)
    for(id in names(scenes)) saveRDS(scenes[[id]],file.path(stage,paste0(id,".rds")),compress=FALSE)
    b6_write_json(receipts,file.path(stage,"input_receipts.json"))
  })
}
b6_jobs <- function(inputs) {
  paths<-inputs[grepl("/scn_[a-f0-9]+\\.rds$",inputs)]
  lapply(sort(paths),function(p) list(id=sub(".rds$","",basename(p)),path=p))
}
b6_parity_one <- function(cfg,job) {
  s<-readRDS(job$path);v<-b6_scene_entities(s);g<-b6_graph(v)
  expected<-s$edges[,.(source=as.integer(source_local_entity_id),destination=as.integer(destination_local_entity_id),mask=as.integer(relation_mask))]
  data.table::setorder(expected,source,destination)
  if(!identical(as.data.frame(g$edges),as.data.frame(expected))) stop("BLOCKED Original relation parity: ",s$id)
  ids<-s$entities$local_entity_id;nodes<-s$nodes[match(ids,local_entity_id)];road<-s$roles$road
  stopifnot(identical(as.character(nodes$source_entity_id),as.character(s$entities$source_entity_id)),identical(as.integer(nodes$local_entity_id),as.integer(ids)))
  measured<-as.numeric(sf::st_length(road));centers<-if(nrow(road)) t(vapply(sf::st_geometry(road),b6_center,numeric(2))) else matrix(numeric(),0,2)
  center_error<-max(c(0,abs(centers-cbind(road$observed_center_x_5186,road$observed_center_y_5186))))
  relative_error<-max(c(0,abs(sweep(centers,2,c(mean(s$bounds[c(1,3)]),mean(s$bounds[c(2,4)])))-cbind(road$relative_center_x_m,road$relative_center_y_m))))
  stopifnot(all(abs(measured-road$observed_length_m)<=1e-7+road$observed_length_m*1e-10),center_error<=1e-7,relative_error<=1e-7,
    identical(sf::st_as_binary(sf::st_geometry(v$entities[v$entities$entity_type=="R",])),sf::st_as_binary(sf::st_geometry(road))))
  b6_publish(cfg,paste0("parity-",s$id),function(stage) b6_write_json(list(status="PASS",scene_id=s$id,group=s$group,
    roads=nrow(road),ordered_pairs=nrow(expected),max_center_error=center_error,max_relative_error=relative_error),file.path(stage,"scene_parity.json")))
}
b6_parity_aggregate <- function(cfg,branches,jobs) {
  paths<-unlist(branches);paths<-paths[basename(paths)=="scene_parity.json"]
  rows<-lapply(paths,b6_read_json);stopifnot(length(rows)==length(jobs),all(vapply(rows,function(x)x$status=="PASS",logical(1))))
  b6_publish(cfg,"parity",function(stage) b6_write_json(list(status="PASS",scenes=rows),file.path(stage,"original_parity.json")))
}
