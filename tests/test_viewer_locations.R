# Small noncanonical fixture tests for scene-center display metadata.
suppressPackageStartupMessages(library(sf))
source('R/viewer_locations.R')
Sys.setenv(PROJ_NETWORK='OFF')
rows <- data.frame(scene_id='fixture',center_x=190294.72045749245,center_y=539681.6337786105,epsg=5186)
one <- location_transform(rows); two <- location_transform(rows)
stopifnot(identical(one$coordinates,two$coordinates),all(is.finite(one$coordinates)),
          abs(one$coordinates[1,1]-126.89031)<0.00001,abs(one$coordinates[1,2]-37.45650)<0.00001,
          one$coordinates[1,1]>100,one$coordinates[1,2]<50)
rect <- function(x1,x2) st_polygon(list(matrix(c(x1,0,x2,0,x2,2,x1,2,x1,0),ncol=2,byrow=TRUE)))
b <- st_sf(code=c('11180','11190'),name=c('금천구','영등포구'),geometry=st_sfc(rect(0,2),rect(2,4),crs=5179))
points <- st_as_sf(data.frame(x=c(1,5,2),y=c(1,1,1)),coords=c('x','y'),crs=5179)
s <- location_assignment(points,b,'code','name')
stopifnot(s[[1]]$status=='unique_match',s[[1]]$name=='금천구',s[[2]]$status=='no_polygon_match',
          is.null(s[[2]]$code),s[[3]]$status=='boundary_ambiguous',is.null(s[[3]]$name),
          identical(s[[3]]$candidate_codes,list('11180','11190')))
d <- b;d$code<-c('11180520','11190520');d$name<-c('독산1동','양평1동')
a <- location_assignment(points,d,'code','name')
stopifnot(a[[1]]$name=='독산1동',location_hierarchy(s[[1]],a[[1]])=='consistent',
          location_hierarchy(s[[2]],a[[2]])=='not_comparable')
a[[1]]$code<-'99999520'
stopifnot(inherits(try(location_hierarchy(s[[1]],a[[1]]),silent=TRUE),'try-error'))
rows$epsg<-5179
stopifnot(inherits(try(location_transform(rows),silent=TRUE),'try-error'))
cat('PASS: coordinate, axis, deterministic, unique, zero, shared-edge, no nearest, names, hierarchy\n')
