# Stage A observational diagnostics. No model forward, optimizer or checkpoint.
b6_entity_metrics <- function(scene,v) {
  road<-v$entities[v$entities$entity_type=="R",];g<-sf::st_geometry(road);n<-nrow(road)
  lengths<-as.numeric(sf::st_length(g));centers<-if(n) t(vapply(g,b6_center,numeric(2))) else matrix(numeric(),0,2)
  counts<-table(road$parent_source_id);parts<-lapply(g,b6_parts)
  nearest<-if(n>1) {d<-as.matrix(stats::dist(centers));diag(d)<-Inf;apply(d,1,min)} else rep(NA_real_,n)
  dispersion<-if(n) sqrt(mean(rowSums(sweep(centers,2,colMeans(centers))^2))) else NA_real_
  bins<-if(n) {z<-floor(sweep(centers,2,scene$bounds[1:2])/50);z[]<-pmin(9,pmax(0,z));apply(z,1,paste,collapse=":")} else character()
  lin<-v$lineage
  summary<-c(list(parent_count=nrow(scene$roles$road),child_count=n,child_parent_ratio=b6_ratio(n,nrow(scene$roles$road)),
    total_length_m=sum(lengths),multipart_parent_count=sum(scene$roles$road$observed_component_count>1),
    zero_length_children=sum(lengths<=0),tiny_residual_count=sum(lengths>0 & lengths<.001),
    true_node_incidence=nrow(v$incidence),synthetic_cut_endpoints=if(nrow(lin)) sum(lin$start_synthetic+lin$end_synthetic) else 0,
    length_error=v$max_length_error,support_error=v$max_support_error,bbox_dispersion_m=dispersion,occupied_50m_bins=length(unique(bins)),
    nn_bbox_mean_m=if(n>1) mean(nearest) else NA_real_,geometry_rows=n,fourier_row_estimate=n,fourier_bytes_estimate=n*1536,
    coordinate_count=sum(vapply(parts,function(p) sum(vapply(p,nrow,integer(1))),integer(1))),part_count=sum(lengths(parts))),
    setNames(b6_stats(lengths),paste0("child_length_",names(b6_stats(lengths)))),
    setNames(b6_stats(as.numeric(counts)),paste0("children_per_parent_",names(b6_stats(as.numeric(counts))))))
  nodes<-data.table::data.table(local_entity_id=road$local_entity_id,parent_source_id=road$parent_source_id,
    bbox_x=centers[,1],bbox_y=centers[,2],relative_x=centers[,1]-mean(scene$bounds[c(1,3)]),relative_y=centers[,2]-mean(scene$bounds[c(2,4)]),
    nn_bbox_m=nearest,length_m=lengths)
  list(summary=summary,nodes=nodes)
}
b6_rss <- function() {
  line<-readLines("/proc/self/status");as.numeric(gsub("[^0-9]","",line[grepl("^VmHWM:",line)]))*1024
}
b6_scene_run <- function(scene,scale) {
  L<-if(scale=="Original") Inf else as.numeric(sub("S","",scale));start<-proc.time()[3]
  v<-b6_scene_entities(scene,L);seg_time<-proc.time()[3]-start
  metrics<-b6_entity_metrics(scene,v)
  # Byte/content determinism within each scene, independent of target cache hits.
  replay<-b6_scene_entities(scene,L)
  stopifnot(identical(v,replay),abs(metrics$summary$total_length_m-sum(scene$roles$road$observed_length_m))<=1e-7+sum(scene$roles$road$observed_length_m)*1e-10)
  # Every original node on the observed road remains incident on an appropriate child.
  if(is.finite(L)) {
    old<-scene$incidence;roads<-scene$roles$road
    expected<-unique(paste(roads$source_entity_id[match(old$local_entity_id,roads$local_entity_id)],old$node_id))
    actual<-unique(paste(v$entities$parent_source_id[match(v$incidence$local_entity_id,v$entities$local_entity_id)],v$incidence$node_id))
    if(!setequal(expected,actual)) stop("B6 original topology not preserved: ",scene$id)
  }
  graphs<-list();summaries<-list();nodes<-list();times<-list()
  for(policy in c("G","P-post","P-pre")) {
    before<-proc.time()[3];graph<-if(policy=="G") b6_graph(v,policy) else b6_repolicy(v,graphs$G,policy);seconds<-proc.time()[3]-before
    graphs[[policy]]<-graph;m<-b6_relation_metrics(v,graph)
    summaries[[policy]]<-data.table::as.data.table(c(list(scene_id=scene$id,group=scene$group,scale=scale,policy=policy),m$summary))
    node<-merge(metrics$nodes,m$nodes,by="local_entity_id",all=TRUE);node[,`:=`(scene_id=scene$id,scale=scale,policy=policy,group=scene$group)];nodes[[policy]]<-node
    times[[policy]]<-data.table::data.table(scene_id=scene$id,group=scene$group,scale=scale,policy=policy,segmentation_seconds=seg_time,relation_seconds=seconds,peak_rss_bytes=b6_rss())
  }
  external<-function(graph,selected=FALSE) {
    x<-if(selected) graph$selected else graph$edges[bitwAnd(mask,1L)!=0,.(source,destination)]
    e<-v$entities;a<-match(x$source,e$local_entity_id);b<-match(x$destination,e$local_entity_id)
    sib<-e$entity_type[a]=="R" & e$entity_type[b]=="R" & e$parent_source_id[a]==e$parent_source_id[b];sib[is.na(sib)]<-FALSE
    paste(x$source[!sib & e$entity_type[a]=="R"],x$destination[!sib & e$entity_type[a]=="R"])
  }
  recovered<-length(setdiff(external(graphs[["P-pre"]]),external(graphs$G)))
  displaced<-length(setdiff(external(graphs[["P-pre"]],TRUE),external(graphs$G,TRUE)))
  stopifnot(setequal(external(graphs$G),external(graphs[["P-post"]])))
  relation<-data.table::rbindlist(summaries);relation[,`:=`(external_sn_recovered_pre=recovered,external_selected_displaced=displaced)]
  lin<-v$lineage;if(nrow(lin)) lin[,`:=`(scale=scale,group=scene$group)]
  list(entity=data.table::as.data.table(c(list(scene_id=scene$id,group=scene$group,scale=scale),metrics$summary)),
    relations=relation,nodes=data.table::rbindlist(nodes),lineage=lin,cost=data.table::rbindlist(times))
}
b6_count_bounds <- function(scene,L) {
  # No child geometries or graphs: exact interval counts under the splitting rule.
  counts<-numeric();component_counts<-numeric();top<-scene$topology
  roads<-scene$roles$road
  for(i in seq_len(nrow(roads))) {
    local<-roads$local_entity_id[i];nd<-unique(top[road_local_entity_id==local,.(node_id=source_node_id,x=source_node_x_5186,y=source_node_y_5186)])
    n<-0
    for(xy in b6_parts(sf::st_geometry(roads)[[i]])) {
      cuts<-b6_node_chainages(xy,nd,1e-7);m<-sum(ceiling(diff(cuts)/L));n<-n+m;component_counts<-c(component_counts,m)
    }
    counts<-c(counts,n)
  }
  n<-sum(counts);other<-nrow(scene$entities)-nrow(roads);all<-n+other
  data.table::data.table(scene_id=scene$id,group=scene$group,scale=paste0("S",L),child_count_exact=n,
    sibling_candidate_upper=sum(counts*(counts-1)),sibling_candidate_lower=2*sum(pmax(0,component_counts-1)),
    max_sibling_pressure_upper=max(c(0,counts-1)),fourier_bytes_estimate=n*1536,
    full_sn_row_upper=min(all*(all-1),32*all),rr_relation_row_upper=n*(n-1),
    bound_kind="counts_exact; sibling/all-pair bounds; no S10/S5 graph")
}
b6_coverage <- function(cfg,parents) {
  b6_path(parents,"parents.json");d<-data.table::as.data.table(arrow::read_parquet(cfg$parent$statistics))
  counts<-d[,.(scene_count=.N,zero_roads=sum(road_count==0)),by=split]
  stopifnot(counts[split=="training",zero_roads]==338,counts[split=="validation",zero_roads]==144,counts[split=="evaluation",zero_roads]==1261)
  b6_publish(cfg,"coverage",function(stage) b6_write_json(list(counts=counts,validation_hit1_upper_bound=(1000-144+1)/1000,
    inference="empty B6 inputs have identical eval-mode scene output; no new inference",reported_hit1=.8565),file.path(stage,"coverage_summary.json")))
}
b6_topology_audit <- function(cfg,inputs) {
  scenes<-readRDS(b6_path(inputs,"scenes.rds"));rows<-list();stress<-list();pairs<-list()
  for(s in scenes) {
    t<-s$topology;b<-s$bounds
    outside<-t[source_node_x_5186<b[1]|source_node_x_5186>b[3]|source_node_y_5186<b[2]|source_node_y_5186>b[4]]
    shared<-outside[,.(degree=data.table::uniqueN(road_local_entity_id)),by=source_node_id][degree>1]
    oldcon<-s$edges[has_con==TRUE]
    p<-data.table::rbindlist(lapply(shared$source_node_id,function(node) {
      ids<-sort(unique(outside[source_node_id==node,road_local_entity_id]));z<-data.table::CJ(source=ids,destination=ids)[source!=destination];z[,`:=`(scene_id=s$id,node_id=node)];z
    }),fill=TRUE)
    # An outside-shared pair may also share another real node INSIDE the scene.
    # That original CON is valid; count only genuinely additional pairs.
    existing<-if(nrow(p)) paste(p$source,p$destination)%in%paste(oldcon$source_local_entity_id,oldcon$destination_local_entity_id) else logical()
    additional<-if(nrow(p)) unique(p[!existing]) else p
    if(nrow(additional)) pairs[[s$id]]<-additional
    degree<-t[,.(degree=data.table::uniqueN(road_local_entity_id)),by=source_node_id]
    loop<-any(vapply(sf::st_geometry(s$roles$road),function(g) any(vapply(b6_parts(g),function(x) anyDuplicated(paste(x[,1],x[,2]))>0,logical(1))),logical(1)))
    rows[[s$id]]<-data.table::data.table(scene_id=s$id,group=s$group,outside_shared_nodes=nrow(shared),outside_con_counterfactual_pairs=nrow(additional),outside_pairs_already_connected_inside=sum(existing),maximum_original_degree=max(c(0,degree$degree)),loop_retracing=loop)
    for(tag in c(if(loop) "loop_retracing",if(nrow(shared)) "shared_outside_node",if(any(degree$degree>=3)) "high_degree_junction"))
      stress[[length(stress)+1L]]<-data.table::data.table(scene_id=s$id,tag=tag,scope="selected_training_scenes")
  }
  b6_publish(cfg,"topology_audit",function(stage) {
    arrow::write_parquet(data.table::rbindlist(rows),file.path(stage,"topology_audit.parquet"))
    arrow::write_parquet(if(length(pairs)) data.table::rbindlist(pairs) else data.table::data.table(source=integer(),destination=integer(),scene_id=character(),node_id=character()),file.path(stage,"outside_pairs.parquet"))
    arrow::write_parquet(if(length(stress)) data.table::rbindlist(stress) else data.table::data.table(scene_id=character(),tag=character(),scope=character()),file.path(stage,"stress_observed.parquet"))
  })
}
b6_artifact_audit <- function(cfg,selection,topology) {
  b6_publish(cfg,"artifact_audit",function(stage) {
    status<-system2("python",c("python/b6_artifact_audit.py","--pilot",shQuote(b6_path(selection,"pilot_scenes.parquet")),
      "--outside-pairs",shQuote(b6_path(topology,"outside_pairs.parquet")),"--output",shQuote(file.path(stage,"augmentation_lineage_audit.json"))))
    if(status!=0) stop("B6 read-only artifact audit failed")
  })
}
b6_acceptance <- function(cfg,parents,inputs,parity,diagnostics,coverage,audit,topology) {
  stopifnot(b6_read_json(b6_path(parity,"original_parity.json"))$status=="PASS")
  receipts<-b6_read_json(b6_path(inputs,"input_receipts.json"))
  # Verify parent byte identities after execution, without modifying them.
  p<-b6_read_json(b6_path(parents,"parents.json"))
  for(path in names(p$hashes)) if(b6_file_hash(path)!=p$hashes[[path]]) stop("B6 historical parent changed")
  tar_rows<-unique(vapply(receipts,`[[`,character(1),"path"))
  for(path in tar_rows) {r<-Filter(function(x) x$path==path,receipts)[[1]];if(b6_file_hash(path)!=r$tar_sha256) stop("B6 P3 parent changed")}
  entity<-data.table::as.data.table(arrow::read_parquet(b6_path(diagnostics,"scene_scale_metrics.parquet")))
  relation<-data.table::as.data.table(arrow::read_parquet(b6_path(diagnostics,"relation_summary.parquet")))
  cost<-b6_read_json(b6_path(diagnostics,"cost_summary.json"))
  stopifnot(all(entity$zero_length_children==0),all(entity$length_error<=1e-6),all(entity$support_error<=1e-7),
    all(relation$projected_rb==0),all(relation$projected_rp==0),cost$elapsed_seconds<=cfg$resources$maximum_seconds,cost$peak_rss_bytes<=cfg$resources$maximum_rss_gib*1024^3)
  # Non-sibling policies must remove all sibling SN while retaining sibling INT.
  stopifnot(all(relation[policy!="G",same_parent_sn]==0))
  z<-relation[,.(n=data.table::uniqueN(same_parent_int)),by=.(scene_id,scale)];stopifnot(all(z$n==1))
  files<-c(parents,inputs,parity,diagnostics,coverage,audit,topology)
  scientific<-files[!basename(files)%in%c("cost_measurements.parquet","cost_summary.json","manifest.json")]
  b6_publish(cfg,"acceptance",function(stage) {
    b6_write_json(list(status="PASS",verdict="READY_FOR_STAGE_B_METHOD_SELECTION",design_id=cfg$design_id,
      original_parity="PASS",historical_parents_unchanged=TRUE,deterministic_child_replay=TRUE,original_topology_preserved=TRUE,
      synthetic_con=FALSE,training_executed=FALSE,checkpoints_created=FALSE,canonical_publication=FALSE,
      scientific_payloads=lapply(scientific,function(p) list(path=p,sha256=b6_file_hash(p))),
      warnings=c("Stratified pilot is not population weighted; stress separate", "No validation per-query rank payload located; evaluation empty vectors verified instead",
        "Post-bank audit bounded, multipart source-chain mapping needs explicit adapter", "No training runtime estimate; S10/S5 bounds only")),file.path(stage,"acceptance.json"))
  })
}
# Independent scene branches; full Original gate precedes every subdivision task.
b6_diagnostic_one <- function(cfg,job,parity) {
  stopifnot(b6_read_json(b6_path(parity,"original_parity.json"))$status=="PASS")
  b6_publish(cfg,paste0("diagnostic-",job$id),function(stage) {
    s<-readRDS(job$path);start<-proc.time()[3];result<-list()
    for(scale in cfg$scales) {
      result[[scale]]<-b6_scene_run(s,scale)
      if(proc.time()[3]-start>cfg$resources$maximum_seconds || b6_rss()>cfg$resources$maximum_rss_gib*1024^3) stop("B6 scene resource limit")
    }
    outputs<-c(entity="scene_scale_metrics.parquet",relations="relation_summary.parquet",nodes="road_node_metrics.parquet",lineage="child_lineage.parquet",cost="cost_measurements.parquet")
    serial<-proc.time()[3]
    for(key in names(outputs)) {
      rows<-data.table::rbindlist(lapply(result,`[[`,key),fill=TRUE)
      if(!ncol(rows)) rows<-data.table::data.table(scene_id=character(),scale=character())
      arrow::write_parquet(rows,file.path(stage,outputs[[key]]),compression="zstd")
    }
    arrow::write_parquet(data.table::rbindlist(lapply(c(10,5),function(L)b6_count_bounds(s,L))),file.path(stage,"fine_scale_bounds.parquet"),compression="zstd")
    b6_write_json(list(scene_id=s$id,elapsed_seconds=proc.time()[3]-start,serialization_seconds=proc.time()[3]-serial,
      peak_rss_bytes=b6_rss(),output_bytes=sum(file.info(list.files(stage,full.names=TRUE))$size)),file.path(stage,"scene_cost.json"))
  })
}
b6_diagnostics_collect <- function(cfg,branches,jobs) {
  paths<-unlist(branches)
  stopifnot(sum(basename(paths)=="scene_cost.json")==length(jobs))
  b6_publish(cfg,"diagnostics",function(stage) {
    for(name in c("scene_scale_metrics.parquet","relation_summary.parquet","road_node_metrics.parquet","child_lineage.parquet","cost_measurements.parquet","fine_scale_bounds.parquet")) {
      rows<-data.table::rbindlist(lapply(sort(paths[basename(paths)==name]),function(p)data.table::as.data.table(arrow::read_parquet(p))),fill=TRUE)
      sort_columns<-intersect(c("scene_id","scale","policy","local_entity_id","child_ordinal"),names(rows))
      data.table::setorderv(rows,sort_columns)
      arrow::write_parquet(rows,file.path(stage,name),compression="zstd")
    }
    costs<-data.table::as.data.table(arrow::read_parquet(file.path(stage,"cost_measurements.parquet")))
    groups<-costs[,.(relation_p50=median(relation_seconds),relation_p95=as.numeric(quantile(relation_seconds,.95)),relation_max=max(relation_seconds),
      segmentation_p50=median(segmentation_seconds),segmentation_p95=as.numeric(quantile(segmentation_seconds,.95)),segmentation_max=max(segmentation_seconds)),by=.(group,scale,policy)]
    scene_costs<-data.table::rbindlist(lapply(paths[basename(paths)=="scene_cost.json"],function(p)data.table::as.data.table(b6_read_json(p))))
    b6_write_json(list(workers=cfg$resources$workers,threads=1,elapsed_seconds=max(scene_costs$elapsed_seconds),
      elapsed_semantics="maximum branch wall seconds, not whole graph duration",summed_scene_seconds=sum(scene_costs$elapsed_seconds),
      scene_elapsed=b6_stats(scene_costs$elapsed_seconds),serialization=b6_stats(scene_costs$serialization_seconds),
      peak_rss_bytes=max(scene_costs$peak_rss_bytes),rss=b6_stats(scene_costs$peak_rss_bytes),
      output_bytes=sum(file.info(list.files(stage,full.names=TRUE))$size),groups=groups,
      fourier="size_estimate_only",gpu_used=FALSE,model_forward_measured=FALSE,training_wall_time_projection=NULL),file.path(stage,"cost_summary.json"))
  })
}
