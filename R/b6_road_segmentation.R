# Experimental only. Dissertation 3.1 observed geometry/bbox center; 3.3 relations.
# Operation: accepted scene clipping -> per-component along-line subdivision.
# No source-network mutation and no Fourier/model/augmentation implementation.
b6_hash <- function(x) digest::digest(x, algo = "sha256", serialize = FALSE)
b6_file_hash <- function(p) digest::digest(file = p, algo = "sha256")
b6_json <- function(x) jsonlite::toJSON(x, auto_unbox = TRUE, null = "null", na = "null", digits = NA)
b6_parts <- function(g) {
  if (inherits(g, "LINESTRING")) return(list(unclass(g)))
  if (inherits(g, "MULTILINESTRING")) return(lapply(unclass(g), unclass))
  stop("B6 road must be lineal")
}
b6_center <- function(g) { b <- as.numeric(sf::st_bbox(g)); c((b[1]+b[3])/2, (b[2]+b[4])/2) }
b6_node_chainages <- function(xy, nodes, tol) {
  d <- diff(xy); lengths <- sqrt(rowSums(d*d)); chain <- c(0,cumsum(lengths)); hits <- numeric()
  if (nrow(nodes)) for (j in seq_len(nrow(nodes))) for (i in which(lengths > 0)) {
    p <- c(nodes$x[j],nodes$y[j]); t <- sum((p-xy[i,])*d[i,])/lengths[i]^2
    if (t >= 0 && t <= 1 && sqrt(sum((p-(xy[i,]+t*d[i,]))^2)) <= tol) {
      h <- chain[i]+t*lengths[i]
      # Projected source nodes within coordinate tolerance of an existing vertex
      # use that exact chainage: avoid a numerically zero endpoint sliver.
      vertex <- which.min(abs(chain-h))
      if(abs(chain[vertex]-h)<=tol) h <- chain[vertex]
      hits <- c(hits,h)
    }
  }
  sort(unique(c(0,hits,tail(chain,1))))
}
b6_substring <- function(xy, a, b) {
  lengths <- sqrt(rowSums(diff(xy)^2)); z <- c(0,cumsum(lengths))
  at <- function(s) {
    exact <- which(z == s)
    if (length(exact)) return(xy[exact[1],])
    i <- tail(which(z < s & seq_along(z) < length(z)),1)
    xy[i,] + (s-z[i])/lengths[i]*(xy[i+1,]-xy[i,])
  }
  rbind(at(a),xy[z > a & z < b,,drop=FALSE],at(b))
}
b6_split_parent <- function(g, scene_id, parent_id, local_id, L, nodes,
                            tol=1e-7, version="b6-observed-v1") {
  stopifnot(is.finite(L),L>0)
  out <- list(); k <- 0L
  for (component in seq_along(b6_parts(g))) {
    xy <- b6_parts(g)[[component]][,1:2,drop=FALSE]
    if (any(!is.finite(xy)) || nrow(xy)<2 || sum(sqrt(rowSums(diff(xy)^2)))<=0) stop("B6 zero-length input")
    true_cuts <- b6_node_chainages(xy,nodes,tol)
    cuts <- true_cuts
    for (i in seq_len(length(true_cuts)-1L)) {
      a<-true_cuts[i]; b<-true_cuts[i+1]
      cuts<-c(cuts,a+seq_len(max(0,ceiling((b-a)/L)-1L))*L)
    }
    cuts<-sort(unique(cuts)); ordinal<-0L
    for (i in seq_len(length(cuts)-1L)) {
      a<-cuts[i]; b<-cuts[i+1]; if(b<=a) stop("B6 zero-length child")
      ordinal<-ordinal+1L; k<-k+1L; coords<-b6_substring(xy,a,b)
      endpoint_nodes<-lapply(c(1L,nrow(coords)),function(q) {
        if(!nrow(nodes)) return(character())
        sort(unique(as.character(nodes$node_id[sqrt((nodes$x-coords[q,1])^2+(nodes$y-coords[q,2])^2)<=tol])))
      })
      key<-b6_json(list(version=version,scene_id=scene_id,parent_source_id=parent_id,
        component_index=component,child_ordinal=ordinal,start_chainage=sprintf("%a",a),end_chainage=sprintf("%a",b),L=L))
      out[[k]]<-list(child_id=paste0("b6child_",b6_hash(key)),scene_id=scene_id,
        parent_source_id=parent_id,original_local_entity_id=as.integer(local_id),component_index=component,
        child_ordinal=ordinal,start_chainage=a,end_chainage=b,L=L,policy_version=version,
        start_true_node=length(endpoint_nodes[[1]])>0,end_true_node=length(endpoint_nodes[[2]])>0,
        start_synthetic=a>0 && !length(endpoint_nodes[[1]]),
        end_synthetic=b<tail(true_cuts,1) && !length(endpoint_nodes[[2]]),
        start_nodes=endpoint_nodes[[1]],end_nodes=endpoint_nodes[[2]],geometry=sf::st_linestring(coords))
    }
  }
  child<-sf::st_sfc(lapply(out,`[[`,"geometry"),crs=5186)
  original<-sf::st_sfc(g,crs=5186)
  lengths<-as.numeric(sf::st_length(child)); total<-as.numeric(sf::st_length(original))
  if(any(lengths<=0) || any(lengths>L+tol) || abs(sum(lengths)-total)>tol+total*1e-10) stop(sprintf("B6 length preservation parent=%s min=%.17g max=%.17g error=%.17g total=%.17g",parent_id,min(lengths),max(lengths),abs(sum(lengths)-total),total))
  # Directed Hausdorff and linear lengths jointly preserve support, including retracing multiplicity.
  support_error<-as.numeric(sf::st_distance(sf::st_union(child),original,which="Hausdorff"))
  if(!is.finite(support_error) || support_error>tol) stop("B6 support preservation")
  attr(out,"length_error")<-abs(sum(lengths)-total);attr(out,"support_error")<-support_error
  out
}
b6_scene_entities <- function(scene,L=Inf) {
  e<-scene$entities
  for(field in intersect(c("ROAD_RANK","ROAD_TYPE","LANES"),names(scene$roles$road))) {
    e[[field]]<-scene$roles$road[[field]][match(e$local_entity_id,scene$roles$road$local_entity_id)]
  }
  e$parent_source_id<-ifelse(e$entity_type=="R",e$source_entity_id,NA_character_)
  e$original_local_entity_id<-e$local_entity_id
  if(is.infinite(L) || !nrow(e)) return(list(entities=e,lineage=data.table::data.table(),incidence=scene$incidence,max_length_error=0,max_support_error=0))
  rows<-list();lineage<-list();incidence<-list();geoms<-list();k<-0L;le<-se<-0
  for(i in seq_len(nrow(e))) {
    if(e$entity_type[i]!="R") {k<-k+1L; rows[[k]]<-sf::st_drop_geometry(e[i,]);geoms[[k]]<-sf::st_geometry(e)[[i]];next}
    parent_nodes<-scene$topology[road_local_entity_id==e$local_entity_id[i]]
    nodes<-unique(parent_nodes[,.(node_id=source_node_id,x=source_node_x_5186,y=source_node_y_5186)])
    children<-b6_split_parent(sf::st_geometry(e)[[i]],scene$id,e$source_entity_id[i],e$local_entity_id[i],L,nodes)
    le<-max(le,attr(children,"length_error"));se<-max(se,attr(children,"support_error"))
    for(ch in children) {
      k<-k+1L; row<-sf::st_drop_geometry(e[i,]);row$source_entity_id<-ch$child_id
      row$F_NODE<-NA_character_;row$T_NODE<-NA_character_ # parent F/T retained ONLY in lineage
      rows[[k]]<-row;geoms[[k]]<-ch$geometry
      lin<-ch[setdiff(names(ch),c("geometry","start_nodes","end_nodes"))]
      for(field in intersect(c("ROAD_RANK","ROAD_TYPE","LANES"),names(e))) lin[[field]]<-e[[field]][i]
      lin$parent_F_NODE<-e$F_NODE[i];lin$parent_T_NODE<-e$T_NODE[i];lin$local_entity_id<-k-1L
      lin$start_node_ids<-paste(ch$start_nodes,collapse="|");lin$end_node_ids<-paste(ch$end_nodes,collapse="|")
      lin$start_cut_id<-if(ch$start_synthetic) paste0("b6cut_",b6_hash(b6_json(list(scene$id,e$source_entity_id[i],ch$component_index,sprintf("%a",ch$start_chainage))))) else NA_character_
      lin$end_cut_id<-if(ch$end_synthetic) paste0("b6cut_",b6_hash(b6_json(list(scene$id,e$source_entity_id[i],ch$component_index,sprintf("%a",ch$end_chainage))))) else NA_character_
      lineage[[length(lineage)+1L]]<-lin
      for(node in union(ch$start_nodes,ch$end_nodes)) {
        nd<-nodes[node_id==node]; if(nd$x[1]>=scene$bounds[1] && nd$x[1]<=scene$bounds[3] && nd$y[1]>=scene$bounds[2] && nd$y[1]<=scene$bounds[4])
          incidence[[length(incidence)+1L]]<-data.table::data.table(local_entity_id=k-1L,node_id=node)
      }
    }
  }
  x<-data.table::rbindlist(rows,fill=TRUE);x$local_entity_id<-seq_len(nrow(x))-1L
  list(entities=sf::st_sf(as.data.frame(x),geometry=sf::st_sfc(geoms,crs=5186)),
    lineage=data.table::rbindlist(lineage,fill=TRUE),incidence=if(length(incidence)) unique(data.table::rbindlist(incidence)) else data.table::data.table(local_entity_id=integer(),node_id=character()),
    max_length_error=le,max_support_error=se)
}
