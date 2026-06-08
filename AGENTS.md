# Data Repositories

## fuse

Project code repository: ~/fuse
contains spatial data processing scripts, embedding pipelines, and GIS workflows.

## fusedata

Project data repository: ~/fusedata
contains canonical processed spatial datasets, processed metadata parquets and interactive htmls

## fusedatalarge

Project data repository: ~/fusedatalarge
contains large raw datasets.

Large processed spatial outputs should be written to:
~/fusedatalarge/processed

(This processed directory is flat and should not contain subdirectories.)

## fuse_external

External research repositories: ~/fuse_external

Contains third-party GitHub repositories used for embedding generation,
representation learning, computer vision, and geospatial foundation models.

Examples:

- GeoNeuralRepresentation (for geometric embeddings of geospatial point/line/polygon objects)

Rules:

- Do not copy external repositories into ~/fuse.
- Reference and execute them in place from ~/fuse_external.
- Keep external repositories isolated from project code.
- Modifications to external repositories should be documented before changing source code.

# Programming Environment

## R preferences

- Use tidyverse and collapse for data manipulation.
- Use data.table and arrow for fast processing and parquet reading/writing.
- Use future_mirai for parallel processing (server memory has 700GB and 48 workers)
- Use sf and terra for geospatial data processing (gpkg is preferred for writing than shp)

## python preferences

- geopandas, shapely, rasterio, pyarrow, pandas, numpy

## Spatial Processing Rules

Preferred CRS: EPSG:5186
Before distance, area, buffering, or spatial join operations, verify CRS consistency.
For R workflows: sf::sf_use_s2(FALSE)

For large spatial datasets:

- inspect file size before loading
- prefer chunked processing
- prefer parquet over CSV
- avoid unnecessary geometry duplication

## Output Preferences

Preferred formats:

- Parquet for analytical tables
- GeoPackage (.gpkg) for spatial data
- HTML for interactive visualizations

Avoid creating shapefiles unless compatibility is required.
Always inspect existing outputs before creating new files.
Prefer extending existing workflows rather than creating duplicate pipelines.

# External Data Resources

The repository code is located in ~/fuse.
Several datasets are stored outside the repository because of their size.

The datasets listed in this document are project resources.
When relevant to the task, inspect these directories and files directly.
Do not assume file names or contents. Verify them by exploring the filesystem.

## Administrative Boundaries

Location:
~/fusedata/geodata/koreanadm

Contains:
- bnd_sido_00_2024_2Q.shp
- bnd_sigungu_00_2024_2Q.shp
- bnd_dong_00_2024_2Q.shp

Use when:
- administrative classification is required
- spatial joins are required
- regional aggregation is required

## Openstreetmap POI and road network data 

Location:
~/fusedata/osm/canonical

Contains:
- point POIs
- polygon POIs
- road network datasets

This is the default spatial semantic data source. Unless explicitly requested otherwise, use this dataset first before searching for alternative POI sources.

## Additional POI data

Location:
~/fusedatalarge/POI_ngii (NGII; contains a very large set of Point POIs.)
~/fusedatalarge/togieeum (togieeum; contains a very large set of Polygon POIs.)

## Streetview data

Location:
~/fusedatalarge/streetview/panoramas/raw (raw downloaded streetview images)
~/fusedatalarge/streetview/crops (cropped downloaded streetview images)
~/fusedata/streetview (contains Street View metadata parquet files)

## Building Data

Location:
~/fusedatalarge/Building_vworld

Contains:
- VWorld building footprints
- Seoul building polygons

Use when:
- building geometry is required
- building-level spatial analysis is required
- building embedding generation is required

## other

Location:
~/fusedatalarge/togieeum/TN_RIVER_BT (contains river polygons)

## Reproducibility

Prefer deterministic workflows.

Whenever random sampling is used:

- set explicit random seeds
- document seed values
- preserve canonical outputs
- avoid changing previously validated datasets unless requested

## Important Project Assets

These datasets are considered canonical project resources.

Examples include:

- ~/fusedata/osm/canonical
- ~/fusedata/streetview
- ~/fusedatalarge/streetview
- ~/fusedatalarge/Building_vworld
- ~/fusedata/geodata/koreanadm

Inspect existing resources before creating replacements.

## General Working Principles

When uncertain, inspect the filesystem before making assumptions.

Use commands such as:

- ls
- find
- tree
- ogrinfo
- unzip -l

to verify datasets, directory structures, and file contents before proceeding.

## Spatial Data Storage Design

When saving spatial datasets, minimize attribute columns in GeoPackage outputs.

Large processed spatial outputs belong in the flat directory:
~/fusedatalarge/processed

Preferred design:

- GeoPackage (.gpkg): geometry + stable key column and minimal lightweight classification columns only
- Parquet (.parquet): full non-geometry attributes + the same key column

The key column must be included in both files so that geometry and attributes can be joined later.

Use a stable unique ID when possible, for example:

- building_id
- poi_id
- road_id
- grid_id

Do not store large attribute tables inside GeoPackage unless explicitly required.

## Processed Outputs

Processed canonical outputs are stored in:

~/fusedatalarge/processed

which includes
~/fusedatalarge/processed/korea_buildings_vworld.gpkg (building data)
~/fusedatalarge/processed/korea_poi_ngii_point.gpkg (point POI data)
~/fusedatalarge/processed/korea_togieeum_polygon.gpkg (polygon POI data)

Before generating new nationwide datasets, inspect existing processed outputs to avoid duplication.

## Representation Learning Resources

External embedding and foundation-model repositories are stored in:

~/fuse_external

Before implementing a new embedding workflow:

- inspect existing external repositories
- reuse existing pretrained models when appropriate
- avoid reimplementing published embedding methods
- document embedding dimensions, pretrained weights, and training settings
- save generated embeddings as parquet files with stable IDs

Embedding outputs should be stored in:

~/fusedata/embeddings

Use stable identifiers such as:

- building_id
- poi_id
- road_id
- grid_id