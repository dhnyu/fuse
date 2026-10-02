withr::local_dir(normalizePath("../.."))
# Self-contained experimental tests; no accepted data or canonical writes.
source("R/spatial_relations.R")
source("R/b6_road_segmentation.R")
source("R/b6_road_relations.R")
source("R/b6_stage_a.R")
b6_test_nodes <- function() data.table::data.table(node_id=character(),x=numeric(),y=numeric())
b6_test_split <- function(x,L=50,nodes=b6_test_nodes()) b6_split_parent(x,"fixture","R1",0L,L,nodes)
testthat::test_that("along-line subdivision preserves bends, residuals, parts and identity", {
  shapes<-list(sf::st_linestring(rbind(c(0,0),c(100,0))),sf::st_linestring(rbind(c(0,0),c(20,0),c(20,100))),
    sf::st_multilinestring(list(rbind(c(0,0),c(25,0)),rbind(c(100,0),c(180,0)))),
    sf::st_linestring(rbind(c(0,0),c(100.000001,0))),
    sf::st_linestring(rbind(c(0,0),c(50,0),c(0,0))))
  for(g in shapes) {
    a<-b6_test_split(g);b<-b6_test_split(g)
    testthat::expect_identical(a,b)
    testthat::expect_equal(sum(vapply(a,function(x) as.numeric(sf::st_length(x$geometry)),numeric(1))),as.numeric(sf::st_length(g)),tolerance=1e-7)
    testthat::expect_equal(length(unique(vapply(a,`[[`,character(1),"child_id"))),length(a))
  }
  testthat::expect_length(b6_test_split(shapes[[1]]),2)
  testthat::expect_length(b6_test_split(shapes[[4]]),3)
  testthat::expect_length(b6_test_split(shapes[[3]]),3)
  bend<-b6_test_split(shapes[[2]])[[1]]$geometry
  testthat::expect_true(any(bend[,1]==20 & bend[,2]==0))
  testthat::expect_error(b6_test_split(sf::st_linestring(rbind(c(0,0),c(0,0)))),"zero-length")
})
testthat::test_that("true-node cuts and synthetic endpoint lineage are distinct", {
  nodes<-data.table::data.table(node_id=c("F","J","T"),x=c(0,30,100),y=0)
  a<-b6_test_split(sf::st_linestring(rbind(c(0,0),c(100,0))),50,nodes)
  testthat::expect_equal(vapply(a,`[[`,numeric(1),"end_chainage"),c(30,80,100))
  testthat::expect_true(a[[1]]$start_true_node);testthat::expect_true(a[[1]]$end_true_node)
  testthat::expect_true(a[[2]]$end_synthetic);testthat::expect_false(a[[2]]$end_true_node)
})
b6_fixture <- function(lines,parents=as.character(seq_along(lines)),incidence=data.table::data.table(local_entity_id=integer(),node_id=character())) {
  n<-length(lines);e<-sf::st_sf(local_entity_id=seq_len(n)-1L,source_entity_id=as.character(seq_len(n)),entity_type=rep("R",n),
    parent_source_id=parents,observed_area_m2=NA_real_,geometry=sf::st_sfc(lines,crs=5186))
  list(entities=e,incidence=incidence)
}
testthat::test_that("G P-post P-pre preserve INT, original CON, and multi-bit rows", {
  lines<-lapply(0:19,function(i) sf::st_linestring(rbind(c(i*5,0),c((i+1)*5,0))))
  lines<-c(lines,list(sf::st_linestring(rbind(c(0,20),c(100,20)))))
  v<-b6_fixture(lines,c(rep("parent",20),"other"));g<-b6_graph(v);post<-b6_graph(v,"P-post");pre<-b6_graph(v,"P-pre")
  testthat::expect_true(any(bitwAnd(g$edges$mask,9L)==9L))
  testthat::expect_equal(sum(bitwAnd(g$edges$mask,16L)!=0),0)
  testthat::expect_identical(g$edges[bitwAnd(mask,8L)!=0,.(source,destination)],post$edges[bitwAnd(mask,8L)!=0,.(source,destination)])
  testthat::expect_true(nrow(pre$edges[bitwAnd(mask,1L)!=0])>=nrow(post$edges[bitwAnd(mask,1L)!=0]))
  for(x in list(g,post,pre)) testthat::expect_false(any(x$edges$source==x$edges$destination))
  testthat::expect_lte(max(table(g$selected$source)),16)
})
testthat::test_that("ties quantize before ID and selection symmetrizes", {
  lines<-lapply(0:18,function(i) sf::st_linestring(rbind(c(0,if(i==0) 0 else 10+i*1e-12),c(1,if(i==0) 0 else 10+i*1e-12))))
  v<-b6_fixture(lines);x<-b6_graph(v)
  testthat::expect_equal(x$selected[source==0]$destination,1:16)
  testthat::expect_setequal(paste(x$edges$source,x$edges$destination),paste(x$edges$destination,x$edges$source))
  canonical<-scene_sn_edges(v$entities,rep("R",19),list(scientific=yaml::read_yaml("config/relation_graph.yml")))$edges
  testthat::expect_setequal(paste(canonical$source_local_entity_id,canonical$destination_local_entity_id),paste(x$edges$source,x$edges$destination))
})
testthat::test_that("T/four-way original incidence; crossings/coincidence alone are not CON", {
  v<-b6_fixture(list(sf::st_linestring(rbind(c(-20,0),c(0,0))),sf::st_linestring(rbind(c(0,0),c(20,0))),
    sf::st_linestring(rbind(c(0,0),c(0,20))),sf::st_linestring(rbind(c(0,0),c(0,-20)))))
  v$incidence<-data.table::data.table(local_entity_id=0:2,node_id="J")
  testthat::expect_equal(sum(bitwAnd(b6_graph(v)$edges$mask,16L)!=0),6)
  v$incidence<-data.table::data.table(local_entity_id=0:3,node_id="J")
  testthat::expect_equal(sum(bitwAnd(b6_graph(v)$edges$mask,16L)!=0),12)
  v$incidence$node_id<-as.character(0:3)
  testthat::expect_equal(sum(bitwAnd(b6_graph(v)$edges$mask,16L)!=0),0)
  testthat::expect_equal(sum(bitwAnd(b6_graph(v)$edges$mask,8L)!=0),12)
})
testthat::test_that("publication cannot target canonical namespaces", {
  testthat::expect_error(b6_safe_root("/mnt/hdd002/dhnyu/fusedata/models/reduced"),"namespace")
  testthat::expect_error(b6_safe_root("/tmp/experimental"),"namespace")
  text<-paste(readLines("targets/b6_road_granularity.R"),collapse="\n")
  testthat::expect_false(grepl("s09_|optimizer|checkpoint",text))
})
testthat::test_that("cached candidate policy reconstruction matches independent fresh geometry builds", {
  lines<-lapply(0:20,function(i) sf::st_linestring(rbind(c(i*5,0),c(i*5+5,0))))
  v<-b6_fixture(lines,c(rep("same",18),"a","b","c"));g<-b6_graph(v)
  for(p in c("P-pre","P-post")) testthat::expect_identical(b6_repolicy(v,g,p)$edges,b6_graph(v,p)$edges)
})
testthat::test_that("projected endpoint roundoff does not manufacture zero-length residual", {
  xy<-rbind(c(200000.1,450000.2),c(200010.3,450007.4))
  nd<-data.table::data.table(node_id=c("F","T"),x=xy[,1],y=xy[,2])
  child<-b6_test_split(sf::st_linestring(xy),25,nd)
  testthat::expect_length(child,1)
  testthat::expect_true(child[[1]]$start_true_node && child[[1]]$end_true_node)
  testthat::expect_identical(unclass(child[[1]]$geometry),xy)
})
testthat::test_that("clipped support cannot inherit an outside node or coordinate-only CON", {
  g<-sf::st_linestring(rbind(c(0,0),c(100,0)))
  nd<-data.table::data.table(node_id=c("outside","true"),x=c(-20,100),y=0)
  child<-b6_test_split(g,50,nd)
  testthat::expect_false(child[[1]]$start_true_node)
  testthat::expect_false(child[[1]]$start_synthetic)
  testthat::expect_true(child[[2]]$end_true_node)
  testthat::expect_false(any(vapply(child,function(x)"outside"%in%c(x$start_nodes,x$end_nodes),logical(1))))
  crossing<-b6_fixture(list(sf::st_linestring(rbind(c(-10,0),c(10,0))),sf::st_linestring(rbind(c(0,-10),c(0,10)))))
  edges<-b6_graph(crossing)$edges
  testthat::expect_equal(sum(bitwAnd(edges$mask,8L)!=0),2)
  testthat::expect_equal(sum(bitwAnd(edges$mask,16L)!=0),0)
})
testthat::test_that("child identity is independent of traversal and no multipart bridge exists", {
  g<-sf::st_multilinestring(list(rbind(c(0,0),c(20,0)),rbind(c(90,0),c(110,0))))
  a<-b6_test_split(g,10);other<-b6_split_parent(g,"fixture","R2",1L,10,b6_test_nodes());b<-b6_test_split(g,10)
  testthat::expect_identical(a,b)
  testthat::expect_length(intersect(vapply(a,`[[`,character(1),"child_id"),vapply(other,`[[`,character(1),"child_id")),0)
  testthat::expect_true(all(vapply(a,function(x)as.numeric(sf::st_length(x$geometry))<=10,logical(1))))
  testthat::expect_false(any(vapply(a,function(x)min(x$geometry[,1])<90 && max(x$geometry[,1])>20,logical(1))))
})
testthat::test_that("children inherit semantics/missingness but not parent active F/T incidence", {
  v<-b6_fixture(list(sf::st_linestring(rbind(c(0,0),c(100,0)))))
  v$entities$F_NODE<-"F";v$entities$T_NODE<-"T"
  road<-v$entities;road$ROAD_RANK<-"103";road$ROAD_TYPE<-"000";road$LANES<-NA_real_
  scene<-list(id="fixture",entities=v$entities,roles=list(road=road),bounds=c(0,-1,100,1),
    topology=data.table::data.table(road_local_entity_id=0L,source_node_id=c("F","T"),source_node_x_5186=c(0,100),source_node_y_5186=0),
    incidence=data.table::data.table(local_entity_id=0L,node_id=c("F","T")))
  x<-b6_scene_entities(scene,25)
  testthat::expect_equal(x$entities$ROAD_RANK,rep("103",4))
  testthat::expect_true(all(is.na(x$entities$LANES)))
  testthat::expect_true(all(is.na(x$entities$F_NODE)))
  testthat::expect_equal(x$incidence$local_entity_id,c(0L,3L))
  testthat::expect_equal(x$lineage$parent_F_NODE,rep("F",4))
  testthat::expect_equal(nrow(b6_graph(x)$edges[bitwAnd(mask,16L)!=0]),0)
})
