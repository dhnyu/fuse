# Reuse S11 original-parent definitions for validation-only external diagnostics.
source('R/scene_descriptors.R')
b6f_validation_descriptors <- function(input, output, categories) {
  stopifnot(!file.exists(output),startsWith(normalizePath(input),'/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b_training/'))
  cfg<-jsonlite::read_json(file.path(input,'index.json'),simplifyVector=FALSE)
  cats<-jsonlite::read_json(categories,simplifyVector=FALSE)
  all<-list()
  for (branch in cfg$branches) {
    roads<-as.data.frame(arrow::read_parquet(file.path(input,branch,'roads.parquet')))
    edges<-as.data.frame(arrow::read_parquet(file.path(input,branch,'edges.parquet')))
    nodes<-as.data.frame(arrow::read_parquet(file.path(input,branch,'nodes.parquet')))
    for(scene in unlist(cfg$scenes_by_branch[[branch]])) {
      r<-roads[roads$scene_id==scene,,drop=FALSE]
      geometry<-sf::st_as_sfc(structure(r$observed_geometry,class='WKB'),crs=5186)
      lengths<-as.numeric(sf::st_length(geometry))
      relation<-s11_relation_descriptors(edges[edges$scene_id==scene,c('source_local_entity_id','destination_local_entity_id','relation_mask'),drop=FALSE],nodes$local_entity_id[nodes$scene_id==scene])
      all[[scene]]<-list(scene_id=scene,road_count=nrow(r),road_density=sum(lengths)/1000/.25,
        road_orientation_dispersion=s11_road_orientation(geometry)$value,
        mean_road_segment_length=s11_mean(lengths)$value,
        road_location_dispersion=s11_location_dispersion(geometry)$value,
        road_type_composition=s11_resolve_categories(r$ROAD_TYPE,cats$entries,'ROAD_TYPE')$value,
        road_hierarchy_composition=s11_resolve_categories(r$ROAD_RANK,cats$entries,'ROAD_RANK')$value,
        relation_composition=relation$relation_composition$value,
        mean_relational_degree=relation$mean_relational_degree$value)
    }
  }
  stopifnot(length(all)==1000L)
  jsonlite::write_json(unname(all[sort(names(all))]),output,auto_unbox=TRUE,null='null',digits=NA,pretty=TRUE)
}
args<-commandArgs(trailingOnly=TRUE)
if(length(args)==3L)b6f_validation_descriptors(args[[1]],args[[2]],args[[3]])
