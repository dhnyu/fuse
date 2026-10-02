# Dissertation 3.3: exact geometry SN, relation sets, sparse three-hop neighborhoods.
# Read-only canonical helpers: containment and INT; experimental SN independently
# exposes candidate/selection provenance and explicit sibling policy.
b6_empty_edges <- function() data.table::data.table(source=integer(),destination=integer(),mask=integer())
b6_collapse <- function(x) {
  if(!nrow(x)) return(b6_empty_edges())
  x<-x[,.(mask=Reduce(bitwOr,as.integer(mask))),by=.(source,destination)]
  data.table::setorder(x,source,destination);x
}
b6_graph <- function(value,policy="G") {
  stopifnot(policy %in% c("G","P-post","P-pre"))
  e<-value$entities;n<-nrow(e);ids<-e$local_entity_id
  cfg<-list(scientific=yaml::read_yaml("config/relation_graph.yml"))
  classification<-classify_relation_pois(e,cfg);state<-classification$state
  eligible<-which(state!="P_in");selected<-list();candidates<-list();k<-0L
  # Indexed rectangular broad phase is a superset of the 100m disk query.
  # The exact geometry distance filter/ranking below remains the scientific rule.
  boxes<-sf::st_sfc(lapply(sf::st_geometry(e[eligible,]),function(g) {
    b<-as.numeric(sf::st_bbox(g))+c(-100,-100,100,100)
    sf::st_polygon(list(rbind(c(b[1],b[2]),c(b[3],b[2]),c(b[3],b[4]),c(b[1],b[4]),c(b[1],b[2]))))
  }),crs=5186)
  all_hits<-sf::st_intersects(boxes,e[eligible,])
  for(block_index in split(seq_along(eligible),ceiling(seq_along(eligible)/128))) {
    block<-eligible[block_index]
    js_list<-lapply(seq_along(block),function(q) {js<-eligible[all_hits[[block_index[q]]]];js[js!=block[q]]})
    sizes<-lengths(js_list);flat<-unlist(js_list,use.names=FALSE)
    distances<-if(length(flat)) as.numeric(sf::st_distance(e[rep(block,sizes),],e[flat,],by_element=TRUE)) else numeric()
    cursor<-0L
    for(q in seq_along(block)) {
      i<-block[q];js<-js_list[[q]];if(!length(js)) next
      d<-distances[seq.int(cursor+1L,cursor+length(js))];cursor<-cursor+length(js)
      sib<-e$entity_type[i]=="R" & e$entity_type[js]=="R" & !is.na(e$parent_source_id[js]) & e$parent_source_id[i]==e$parent_source_id[js]
      sib[is.na(sib)]<-FALSE
      c<-data.table::data.table(source=ids[i],destination=ids[js],distance=d,sibling=sib)[distance<=100]
      k<-k+1L;candidates[[k]]<-c
      if(policy=="P-pre") c<-c[sibling==FALSE]
      c[,distance_key:=round(distance/1e-9)*1e-9];data.table::setorder(c,distance_key,destination)
      selected[[k]]<-head(c,16)[,.(source,destination)]
    }
  }
  candidate<-if(length(candidates)) data.table::rbindlist(candidates) else data.table::data.table(source=integer(),destination=integer(),distance=numeric(),sibling=logical())
  directed<-if(length(selected)) data.table::rbindlist(selected) else b6_empty_edges()[,.(source,destination)]
  sn<-unique(data.table::rbindlist(list(directed,directed[,.(source=destination,destination=source)])))
  if(policy=="P-post" && nrow(sn)) {
    a<-match(sn$source,ids);b<-match(sn$destination,ids)
    sib<-e$entity_type[a]=="R" & e$entity_type[b]=="R" & e$parent_source_id[a]==e$parent_source_id[b];sib[is.na(sib)]<-FALSE
    sn<-sn[!sib]
  }
  sn[,mask:=1L]
  ir<-scene_intersection_edges(e,cfg)
  intr<-ir[,.(source=source_local_entity_id,destination=destination_local_entity_id,mask=relation_bit)]
  ct<-scene_containment_edges(classification,cfg)
  contain<-ct[,.(source=source_local_entity_id,destination=destination_local_entity_id,mask=relation_bit)]
  incidence<-value$incidence
  con<-if(nrow(incidence)) data.table::rbindlist(lapply(split(incidence$local_entity_id,incidence$node_id),function(x) {
    x<-sort(unique(x));if(length(x)<2) return(NULL)
    z<-data.table::CJ(source=x,destination=x);z[source!=destination,mask:=16L];z[source!=destination]
  }),fill=TRUE) else b6_empty_edges()
  edges<-b6_collapse(data.table::rbindlist(list(sn,intr,contain,con),fill=TRUE))
  if(any(edges$source==edges$destination)) stop("B6 self edge")
  for(bit in c(1L,8L,16L)) {
    z<-edges[bitwAnd(mask,bit)!=0]
    if(!setequal(paste(z$source,z$destination),paste(z$destination,z$source))) stop("B6 asymmetric relation")
  }
  list(edges=edges,candidates=candidate,selected=directed)
}
b6_ratio <- function(x,y) if(y>0) x/y else NA_real_
b6_stats <- function(x) {
  if(!length(x)) return(as.list(setNames(rep(NA_real_,8),c("mean","median","sd","p05","p25","p75","p95","max"))))
  as.list(c(mean=mean(x),median=median(x),sd=if(length(x)>1) sd(x) else 0,
            setNames(as.numeric(quantile(x,c(.05,.25,.75,.95))),c("p05","p25","p75","p95")),max=max(x)))
}
b6_relation_metrics <- function(value,graph) {
  e<-value$entities;edges<-graph$edges;roads<-e$local_entity_id[e$entity_type=="R"]
  types<-setNames(e$entity_type,e$local_entity_id);parents<-setNames(e$parent_source_id,e$local_entity_id)
  a<-types[as.character(edges$source)];b<-types[as.character(edges$destination)]
  rr<-edges[a=="R" & b=="R"]
  same<-parents[as.character(rr$source)]==parents[as.character(rr$destination)]
  sn<-bitwAnd(rr$mask,1L)!=0;int<-bitwAnd(rr$mask,8L)!=0;con<-bitwAnd(rr$mask,16L)!=0
  out<-tabulate(match(rr$source,roads),nbins=length(roads));incoming<-tabulate(match(rr$destination,roads),nbins=length(roads))
  cross<-tabulate(match(rr$source[!same],roads),nbins=length(roads))
  net<-igraph::graph_from_data_frame(as.data.frame(rr[,.(source=as.character(source),destination=as.character(destination))]),directed=FALSE,vertices=data.frame(name=as.character(roads)))
  components<-igraph::components(net)
  centers<-if(length(roads)) t(vapply(sf::st_geometry(e[e$entity_type=="R",]),b6_center,numeric(2))) else matrix(numeric(),0,2)
  reach<-vapply(seq_along(roads),function(i) {
    others<-as.integer(igraph::ego(net,order=3,nodes=i)[[1]])
    max(c(0,sqrt(rowSums((centers[others,,drop=FALSE]-matrix(centers[i,],length(others),2,byrow=TRUE))^2))))
  },numeric(1))
  avail<-graph$candidates[sibling==FALSE, .N, by=source];avail_count<-avail$N[match(roads,avail$source)];avail_count[is.na(avail_count)]<-0
  list(summary=list(full_ordered_pairs=nrow(edges),rr_pairs=nrow(rr),unordered_pairs=nrow(rr)/2,relation_mask_rows=nrow(rr),
    sn=sum(sn),int=sum(int),con=sum(con),same_parent_pairs=sum(same),same_parent_sn=sum(same&sn),same_parent_int=sum(same&int),same_parent_con=sum(same&con),
    sibling_pair_fraction=b6_ratio(sum(same),nrow(rr)),sibling_sn_fraction=b6_ratio(sum(same&sn),sum(sn)),sibling_int_fraction=b6_ratio(sum(same&int),sum(int)),
    rb_pairs=sum((a=="R" & b=="B") | (a=="B" & b=="R")),rp_pairs=sum((a=="R" & b=="P") | (a=="P" & b=="R")),
    projected_rb=0L,projected_rp=0L,degree_mean=if(length(out)) mean(out) else NA_real_,degree_p95=if(length(out)) as.numeric(quantile(out,.95)) else NA_real_,degree_max=max(c(0,out)),
    isolated_roads=sum(out==0),components=components$no,largest_component=max(c(0,components$csize)),mean_component=if(length(components$csize)) mean(components$csize) else NA_real_,
    cross_parent_degree_mean=if(length(cross)) mean(cross) else NA_real_,nodes_below_16_external_candidates=sum(avail_count<16),reach_3hop_mean_m=if(length(reach)) mean(reach) else NA_real_,reach_3hop_max_m=max(c(0,reach))),
    nodes=data.table::data.table(local_entity_id=roads,out_degree=out,in_degree=incoming,cross_parent_degree=cross,non_sibling_candidates=avail_count,reach_3hop_m=reach),
    rr=rr)
}
# Policy-only reconstruction from the exact G candidate distances. This avoids
# repeating spatial I/O/distance work; fixture tests compare against fresh builds.
b6_repolicy <- function(value,base,policy) {
  stopifnot(policy%in%c("P-pre","P-post"))
  e<-value$entities;candidate<-data.table::copy(base$candidates)
  if(policy=="P-pre") {
    c<-candidate[sibling==FALSE];c[,distance_key:=round(distance/1e-9)*1e-9]
    data.table::setorder(c,source,distance_key,destination)
    directed<-c[,head(.SD,16),by=source][,.(source,destination)]
    sn<-unique(data.table::rbindlist(list(directed,directed[,.(source=destination,destination=source)])))
  } else {
    directed<-base$selected
    sn<-base$edges[bitwAnd(mask,1L)!=0,.(source,destination)]
    a<-match(sn$source,e$local_entity_id);b<-match(sn$destination,e$local_entity_id)
    same<-e$entity_type[a]=="R" & e$entity_type[b]=="R" & e$parent_source_id[a]==e$parent_source_id[b];same[is.na(same)]<-FALSE
    sn<-sn[!same]
  }
  sn[,mask:=1L];other<-data.table::copy(base$edges);other[,mask:=bitwAnd(mask,30L)];other<-other[mask!=0]
  list(edges=b6_collapse(data.table::rbindlist(list(sn,other))),candidates=candidate,selected=directed)
}
