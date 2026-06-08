# Repositories

## fuse

Project code repository.

Location:
~/fuse

Contains:

* spatial processing pipelines
* embedding workflows
* GIS analysis code
* project documentation

## fusedata

Canonical project outputs.

Location:
~/fusedata

Contains:

* processed datasets
* metadata parquet files
* embeddings
* visualization outputs

## fusedatalarge

Large-scale spatial datasets.

Location:
~/fusedatalarge

Contains:

* raw source datasets
* nationwide processed geometry datasets

Canonical processed nationwide outputs:

~/fusedatalarge/processed

This directory is flat and should not contain subdirectories.

# External Research Repositories

Location:

~/fuse_external

Contains third-party repositories used for representation learning, foundation models, computer vision, and geospatial embeddings.

Example:

* GeoNeuralRepresentation

  * Repository:
    ~/fuse_external/GeoNeuralRepresentation
  * Reference paper:
    ~/references/fuse_ref/'Chu 및 Shahabi - Geo2Vec Shape- and Distance-Aware Neural Representation of Geospatial Entities.pdf'

Rules:

* Do not copy external repositories into ~/fuse.
* Execute them in place from ~/fuse_external.
* Keep project code separate from external repositories.
* Prefer wrappers and extension code inside ~/fuse.

When using an external method:

* Review both the repository implementation and the associated paper.
* Do not rely solely on code or solely on the paper.
* Verify that implementation choices remain consistent with the published methodology.

Before modifying an external repository:

* Document the reason for modification.
* Document expected methodological impacts.
* Document reproducibility impacts.
* Prefer wrappers over direct source-code changes.

When scaling published methods:

* Separate methodological changes from engineering changes.
* Clearly distinguish:

  * paper-faithful reproductions
  * scalability experiments
  * production pipelines
  * modified methodologies

Engineering optimizations should not be treated as equivalent to the published method unless verified.

# Programming Environment

## R

Preferred packages:

* tidyverse
* collapse
* data.table
* arrow
* sf
* terra
* future_mirai

## Python

Preferred packages:

* geopandas
* shapely
* rasterio
* pyarrow
* pandas
* numpy

# Spatial Processing Rules

Preferred CRS:

EPSG:5186

Before spatial operations:

* verify CRS consistency
* use sf::sf_use_s2(FALSE) in R

For large datasets:

* inspect before loading
* prefer chunked processing
* prefer parquet over CSV
* avoid geometry duplication

# Spatial Data Storage Design

Preferred outputs:

* Parquet: attributes and analytical tables
* GeoPackage: geometry
* HTML: interactive visualizations

Large processed datasets should follow:

* GeoPackage: geometry + stable key
* Parquet: attributes + same key

Examples of stable keys:

* building_id
* poi_id
* road_id
* grid_id

Do not store large attribute tables inside GeoPackage unless necessary.

# Canonical Project Resources

Inspect existing resources before creating replacements.

Examples:

* ~/fusedata/osm/canonical
* ~/fusedata/streetview
* ~/fusedata/geodata/koreanadm
* ~/fusedatalarge/processed
* ~/fuse_external

# Reproducibility

Prefer deterministic workflows.

When random sampling is used:

* set explicit seeds
* document seeds
* preserve validated outputs
* avoid changing canonical datasets unless requested

# Embeddings

Embedding outputs should be stored in:

~/fusedata/embeddings

Use stable identifiers:

* building_id
* poi_id
* road_id
* grid_id
