# FUSE Project AGENTS.md

## Read Before Working

Before making code changes, generating reports, or proposing new experiments, read:

1. AGENTS.md
2. CONTEXT.md
3. research_vision.md

Treat these documents as authoritative.

Priority order:

```text
AGENTS.md
    ↓
research_vision.md
    ↓
CONTEXT.md
    ↓
reports/
    ↓
implementation details
```

Do not infer project direction solely from code or recent reports.

---

# Research Priority

Current priority is architectural validation, not nationwide scaling.

The primary objective is to demonstrate a complete end-to-end spatial representation learning framework on a bounded study area (currently Gwanak-gu).

Current priority:

```text
Spatial Scene
    ↓
Scene-Aware Object Embedding
    ↓
Scene Embedding
    ↓
Scene Similarity Evaluation
```

Do not prioritize:

* nationwide production
* large-scale stress testing
* engineering scalability work
* optimization for national deployment

unless explicitly requested.

Architecture validation takes precedence over scaling.

---

# Research Vision

The project investigates how spatial scenes can be represented, compared, and retrieved using multimodal representation learning.

The final objective is not:

* building embeddings
* road embeddings
* POI embeddings

These are intermediate representations.

The ultimate target is:

```text
Spatial Scene Representation
        +
Scene Similarity Evaluation
```

All implementation decisions should support this goal.

---

# Spatial Scene Design

The fundamental unit of representation learning is a spatial scene.

A scene is typically represented as a fixed-size spatial crop.

Current reference scale:

* approximately 500 meters

A scene may contain:

* buildings
* road segments
* polygon POIs
* point POIs
* Street View imagery

Objects should be interpreted within scene context.

Avoid object-centric designs that ignore surrounding context.

Prefer scene-aware object representations.

---

# Object Representation Rules

Current primary object types:

* Building
* Road Segment
* Polygon POI

Supporting modalities:

* Point POI
* Street View imagery

Point POIs should generally be treated as semantic evidence.

Street View imagery should generally be treated as visual evidence.

Unless explicitly required:

* Point POIs are not primary object nodes.
* Street View images are not primary object nodes.

Preferred workflow:

```text
Geometry Encoding
        ↓
Semantic / Visual Fusion
        ↓
Relation-Aware Updating
        ↓
Scene-Aware Object Embedding
```

Object embeddings are intermediate products.

Scene embeddings remain the primary target.

---

# Current Conceptual Architecture

```text
Spatial Scene
        ↓
Object Extraction
        ↓
Initial Object Embeddings
(Geometry / Semantic / Visual)
        ↓
Scene-Aware Object Construction
        ↓
Relation-Aware Object Embeddings
        ↓
Scene Embedding
        ↓
Contrastive Learning
        ↓
Scene Similarity Evaluation
```

When proposing new code or experiments, ensure consistency with this architecture.

---

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

---

## fusedata

Canonical project outputs.

Location:

~/fusedata

Contains:

* processed datasets
* metadata parquet files
* embeddings
* validation outputs
* scene construction outputs
* analysis products
* visualization outputs

---

## fusedatalarge

Large-scale spatial datasets.

Location:

~/fusedatalarge

Contains:

* raw source datasets
* OSM source-derived base layers
* large geospatial reference datasets
* raw Street View imagery and crops
* nationwide processed datasets
* standardized regional working-data subsets

Current subpath policy:

```text
~/fusedatalarge/raw         raw source datasets
~/fusedatalarge/osm         OSM source-derived base layers
~/fusedatalarge/geodata     large geospatial reference datasets
~/fusedatalarge/streetview  raw Street View imagery and crops
~/fusedatalarge/processed   canonical heavy processed geometry outputs
~/fusedatalarge/working_data standardized regional subsets for validation and scene workflows
```

Canonical processed outputs:

~/fusedatalarge/processed

This directory is flat and should not contain subdirectories.

Standardized regional working-data subsets are stored under:

```text
~/fusedatalarge/working_data/<region_key>/
```

The reproducible generation script is:

```text
~/fuse/scripts/working_data/create_validation_working_data.R
```

The working-data README is:

```text
~/fusedatalarge/working_data/README.md
```

Regional subset directories use the standard file names:

```text
1_Building_vworld.gpkg
1_Building_vworld.parquet
2_pointPOI_osm.gpkg
2_pointPOI_osm.parquet
2_pointPOI_ngii.gpkg
2_pointPOI_ngii.parquet
3_polygonPOI_osm.gpkg
3_polygonPOI_osm.parquet
3_polygonPOI_togi.gpkg
3_polygonPOI_togi.parquet
4_road_osm.gpkg
4_road_osm.parquet
5_streetview.parquet
```

Street View working-data files contain metadata only. Do not copy Street View
image files into `working_data`.

---

# External Research Repositories

Location:

~/fuse_external

Contains third-party repositories used for:

* representation learning
* computer vision
* foundation models
* geospatial embeddings

Example:

GeoNeuralRepresentation

Repository:

~/fuse_external/GeoNeuralRepresentation

Rules:

* Do not copy external repositories into ~/fuse.
* Execute them in place.
* Keep project code separate from external repositories.
* Prefer wrappers over source modification.

Before modifying an external repository:

* document rationale
* document methodological impacts
* document reproducibility impacts


# Previous Researches

~/references/fuse_ref/

Some core papers:
'Chu 및 Shahabi - Geo2Vec Shape- and Distance-Aware Neural Representation of Geospatial Entities.pdf' (Geo2Vec)
'Gong 등 - 2025 - A Multi-Scale Hybrid Scene Geometric Similarity Measurement Method Using Heterogeneous Graph Neural.pdf' (Heterogenous Attention Network)
'Guo 등 - 2024 - SpatialScene2Vec A self-supervised contrastive representation learning method for spatial scene sim.pdf'
'Li 등 - 2026 - Learning Street View Representations with Spatiotemporal Contrast.pdf'
'Li 등 - 2022 - SpaBERT A Pretrained Language Model from Geographic Data for Geo-Entity Representation.pdf'
'Liu 등 - 2025 - Representation learning for geospatial data.pdf'
'Mai 등 - 2020 - Multi-Scale Representation Learning for Spatial Feature Distributions using Grid Cells.pdf'
'Mai 등 - 2023 - Towards general-purpose representation learning of polygonal geometries.pdf'
'Mai 등 - 2024 - SRL Towards a General-Purpose Framework for Spatial Representation Learning.pdf'
'Siampou 등 - 2025 - Poly2Vec Polymorphic Fourier-Based Encoding of Geospatial Objects for GeoAI Applications.pdf'
'Wijegunarathna 등 - 2026 - Omni Geometry Representation Learning Versus Large Language Models for Geospatial Entity Resolution.pdf'
'Yu 등 - 2024 - PolygonGNN Representation Learning for Polygonal Geometries with Heterogeneous Visibility Graph.pdf'
'Yuan 등 - 2026 - A review of representation and similarity measurement methods for geospatial scenes.pdf'
'Zhang 및 Zhao - Representation Learning on Spatial Networks.pdf'
---

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

---

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
* Default CPU workers: 40
* Reduce workers only when memory, I/O, or software constraints require it.
* Explicitly report worker counts used in generated reports.
---

# Data Storage Design

Preferred outputs:

* Parquet → attributes
* GeoPackage → geometry
* HTML → visualization

Large datasets should follow:

```text
Geometry
    ↓
GeoPackage

Attributes
    ↓
Parquet
```

Use stable identifiers:

* building_id
* road_id
* poi_id
* polygon_poi_id
* scene_id

Avoid storing large attribute tables inside GeoPackage.

Canonical polygon POI source for downstream embedding and analysis:

```text
Geometry:
~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility.gpkg

Attributes:
~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility_attributes.parquet
```

This facility-filtered Togieeum polygon POI dataset is the recommended source
for polygon POI analysis, shape embedding, multimodal embedding fusion, spatial
scene representation learning, and downstream machine learning workflows. It
removes 1,127 route-like transportation corridor polygons from the broader
cleaned Togieeum layer while preserving station-, terminal-, airport-, port-,
parking-, depot-, and facility-like transportation polygons. CRS is EPSG:5186.

Legacy broader-cleaned Togieeum polygon POI outputs remain useful as provenance
and for auditing the transport-corridor refinement:

```text
Geometry:
~/fusedatalarge/processed/korea_polygon_poi_togieeum.gpkg

Attributes:
~/fusedatalarge/processed/korea_polygon_poi_togieeum_attributes.parquet
```

# Hardware Environment

Primary research server:

- CPU: 48 physical cores
- RAM: 768 GB
- GPU 0: NVIDIA RTX A6000 (48 GB VRAM)
- GPU 1: NVIDIA RTX A6000 (48 GB VRAM)

Available resources are substantially larger than typical desktop environments.

Unless explicitly requested otherwise:

- Prefer parallel processing for large workloads.
- Use up to 40 CPU workers when the workload is embarrassingly parallel.
- Prefer chunked parallel processing over sequential processing for nationwide datasets.
- Prefer GPU acceleration when supported by the underlying method.
- Do not artificially limit computation to laptop-scale assumptions.

Exceptions:
- Small validation tasks
- Debugging runs
- Smoke tests
- Reproducibility checks
---

# Embeddings

Embedding outputs should be stored in:

~/fusedata/embeddings

Use stable identifiers.

Examples:

* building_id
* road_id
* poi_id
* scene_id

Maintain reproducible metadata describing:

* embedding dimensions
* training configuration
* source datasets
* generation date

---

# Reproducibility

Prefer deterministic workflows.

When randomization is used:

* set explicit seeds
* document seeds
* preserve validated outputs
* avoid modifying canonical datasets

Separate clearly:

* paper-faithful reproductions
* methodological extensions
* scalability experiments
* production pipelines

Do not treat engineering optimizations as methodological improvements unless verified.

---

# Documentation Management

Stable project documents:

* README.md
* AGENTS.md
* CONTEXT.md
* research_vision.md

Long-term documentation:

~/fuse/docs

Generated reports:

~/fuse/reports

Generated Markdown files must:

* be written only under reports/
* use sortable filenames

Format:

```text
YYYYMMDD_HHMM_short_description.md
```

Example:

```text
20260614_2130_scene_embedding_architecture_review.md
```

Do not create generated reports inside:

* src/
* scripts/
* tests/
* experiment directories

When creating a report:

* inspect existing reports first
* update when appropriate
* avoid duplicate reports
