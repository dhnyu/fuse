# FUSE Project Progress Summary

Date: 2026-05-19

## Project Overview

FUSE is developing a Seoul-scale data foundation for multimodal urban representation learning. The current implementation focuses on constructing reproducible spatial samples along the road network, linking those samples to Google Street View metadata and imagery, and extracting semantic OpenStreetMap (OSM) point-of-interest (POI) features for future fusion with visual scene representations.

The near-term research objective is to support place and scene representation learning from complementary urban signals:

- road-network-constrained spatial sampling;
- Street View panorama metadata and directional image crops;
- semantic POI attributes from OSM;
- grid-based spatial aggregation at 500 m resolution.

The system is currently an implemented data-construction and validation pipeline, not yet an embedding or downstream modeling pipeline.

## Implemented Pipeline

```text
Seoul boundary + 500 m grid
        |
        v
Geofabrik OSM roads -> canonical road archive -> non-tunnel sampling network
        |                                           |
        |                                           v
        |                              road candidate generation
        |                                           |
        |                                           v
        |                              Poisson-disk-style thinning
        |                                           |
        |                                           v
        |                         40,000 sampled road points + grid IDs
        |                                           |
        v                                           v
OSM POI semantic extraction              Street View metadata pilot
        |                                           |
        v                                           v
POI parquet/GPKG archives          panorama acquisition + directional crops
```

## Completed Infrastructure

| Component | Completed state |
|---|---|
| Seoul grid | 500 m grid built in EPSG:5186 with 2,631 cells. |
| Road sampling | Global Seoul road-point sampling implemented in R with reproducible greedy Euclidean thinning. |
| Road data architecture | OSM road storage split into raw, canonical, and operational sampling layers. |
| Tunnel handling | Canonical road archive retains tunnel roads and tunnel attributes; sampling network excludes tunnels only during operational network construction. |
| Street View metadata | Metadata-first pilot implemented against the official Google Street View metadata endpoint. |
| Panorama acquisition | 100-panorama benchmark implemented with cached panorama reuse, manifest writing, and failure logging. |
| Crop generation | Panorama-first workflow implemented: each panorama is stored once, then local front/right/rear/left perspective crops are generated using `py360convert`. |
| Semantic POIs | OSM point and polygon POI extraction implemented with deterministic semantic priority rules. |
| Data formats | Parquet is used for ML-ready tables; GPKG is used for GIS/QC and geometry-preserving canonical artifacts. |
| Reproducibility | Pipelines write manifests, metadata summaries, logs, and deterministic IDs. Lightweight tests are available for road sampling behavior. |

## Current Dataset Status

### Spatial Sampling

| Metric | Current value |
|---|---:|
| Final sampled road points | 40,000 |
| Sampled points with coordinates | 40,000 |
| 500 m grid cells | 2,631 |
| Grid cells containing sampled points | 2,245 |
| Minimum nearest-neighbor distance | 50.0 m |
| Median nearest-neighbor distance | 64.1 m |

Road-class composition of the 40,000 sampled points:

| Highway class | Sampled points |
|---|---:|
| residential | 19,314 |
| service | 10,109 |
| primary | 3,059 |
| secondary | 2,969 |
| tertiary | 2,446 |
| trunk | 1,113 |
| living_street | 497 |
| unclassified | 308 |
| motorway | 185 |

### Road Network Archives

| Dataset | Count / status |
|---|---:|
| Canonical Seoul roads | 107,912 features |
| Canonical tunnel roads retained | 1,686 features |
| Operational sampling-network roads | 75,532 features |
| Sampling-network tunnel roads | 0 |
| Sampling-network total length | 10,105,709 m |

During the road-storage refactor, the old filtered network and the new sampling network were compared after tunnel exclusion and Seoul-boundary clipping. They matched exactly in feature count, highway-class distribution, and total network length, preserving current Poisson sampling semantics.

### Semantic POIs

POIs are extracted from OSM `points` and `multipolygons` using the priority order:

```text
amenity, shop, tourism, leisure, office, healthcare,
public_transport, craft, man_made
```

| POI layer | Features | Main outputs |
|---|---:|---|
| Point POIs | 70,842 | GPKG + parquet |
| Polygon POIs | 20,229 | GPKG + parquet |
| Total POIs | 91,071 | ID mapping + summary distributions |

Top combined `poi_type` values:

| Rank | POI type | Count |
|---:|---|---:|
| 1 | restaurant | 14,641 |
| 2 | platform | 10,018 |
| 3 | hairdresser | 7,526 |
| 4 | parking | 5,357 |
| 5 | cafe | 3,668 |
| 6 | bicycle_rental | 2,720 |
| 7 | convenience | 2,609 |
| 8 | pitch | 2,242 |
| 9 | park | 2,191 |
| 10 | place_of_worship | 1,637 |

The canonical POI GPKG outputs now preserve semantic fields such as `poi_class`, `poi_type`, `name`, and additional available OSM tags, aligning GIS workflows with the richer parquet schema.

### Street View Pilot and Benchmark

| Metric | Current value |
|---|---:|
| Metadata pilot sample size | 1,000 road points |
| Metadata successes | 928 |
| Metadata failures / zero results | 72 |
| Metadata success rate | 92.8% |
| Unique panorama IDs in pilot | 928 |
| Panorama reuse ratio in pilot | 0.0 |
| Mean sample-to-panorama distance | 9.26 m |
| Median sample-to-panorama distance | 5.01 m |
| Capture year range | 2009-2025 |
| Median capture year | 2018 |
| Benchmark manifest panoramas | 100 |
| Benchmark panorama success | 100 / 100 |
| Benchmark crop success | 100 / 100 |
| Cached raw panorama files | 101 |
| Cached crops per direction | 101 front, 101 right, 101 rear, 101 left |

The benchmark manifest records image sizes, retry counts, cache reuse, crop-generation status, debug contact-sheet paths, and simple crop-quality diagnostics. A one-panorama prototype is also cached, which explains the 101 local panorama files versus the 100-row benchmark manifest.

## Current Data Architecture

```text
data/
  geodata/
    seoul_boundary.gpkg
    seoul_adjacent_regions.gpkg
    gadm/
  grid_500m/
    seoul_grid_500m.gpkg
    seoul_grid_500m_map.png
  osm/
    raw/
      geofabrik_south-korea-latest.osm.pbf
      geofabrik_south-korea-latest.gpkg
    canonical/
      seoul_roads_canonical.gpkg
      gpkg/seoul_pois_point.gpkg
      gpkg/seoul_pois_polygon.gpkg
      parquet/seoul_pois_point.parquet
      parquet/seoul_pois_polygon.parquet
    sampling/
      seoul_roads_sampling_network.gpkg
    metadata/
      poi_id_mapping.parquet
      layer_summary.parquet
      poi_class_distribution.parquet
      poi_type_distribution.parquet
    logs/
      extraction.log
  sampling_global/
    seoul_road_network_samples.parquet
    seoul_road_network_sampling_map.html
    seoul_road_network_sampling_map.png
  streetview/
    metadata/
    panoramas/raw/
    crops/front/
    crops/right/
    crops/rear/
    crops/left/
    manifests/
    logs/
    debug/
```

This structure separates source data, reusable canonical archives, task-specific sampling derivatives, and generated imagery/metadata.

## Validation and Benchmark Evidence

- Road sampling unit test passes: `tests/test_road_environment_sampling.R`.
- Sampling test validates candidate generation, Poisson-style thinning, grid assignment, and output schema on a controlled synthetic network.
- Operational road-network refactor was validated against the previous non-tunnel filtered network:
  - same road feature count: 75,532;
  - same highway-class distribution;
  - same total length: 10,105,709 m.
- POI extraction verifies:
  - nonzero point and polygon POI counts;
  - expected semantic fields in parquet;
  - expected semantic fields in GPKG;
  - no geometry columns stored in parquet;
  - retained OSM semantic tags.
- Street View metadata pilot writes:
  - row-level metadata parquet;
  - pilot summary parquet;
  - panorama duplication counts;
  - capture-year distribution.
- Panorama benchmark writes:
  - raw panorama JPGs;
  - four directional crops per panorama;
  - parquet manifest;
  - debug contact sheets for crop projection inspection.

## Important Technical Decisions

### Metadata-first Street View acquisition

The Street View workflow first queries metadata before attempting imagery. This estimates coverage, panorama uniqueness, capture dates, and point-to-panorama offsets without immediately downloading imagery at scale.

### Panorama-first image storage

The image workflow stores each panorama once and derives directional crops locally. This avoids redundant requests for multiple headings and keeps future visual representation experiments tied to a stable panorama identifier.

### Local perspective projection

Directional front/right/rear/left crops are generated locally from equirectangular panoramas using `py360convert`. This makes crop generation reproducible and independent of repeated remote image requests once panoramas are cached.

### Canonical vs operational road layers

The road archive intentionally retains tunnel roads and key OSM attributes. Tunnel exclusion is applied only when constructing the operational sampling network, because tunnels are undesirable for Street View road sampling but still valid archive features.

### Parquet-first ML tables, GPKG for GIS/QC

Parquet is used for model-facing tabular data and metadata summaries. GPKG is retained for geometry-preserving artifacts and GIS inspection. Recent POI changes ensure semantic attributes are preserved in both workflows.

### OSM as semantic source for POIs

The project no longer treats OSM as a general geometry-foundation dataset. Building geometry is expected to come later from higher-quality authoritative sources. OSM POIs are currently used primarily as semantic place indicators for future multimodal fusion.

## Current Remaining Tasks

1. Scale Street View acquisition beyond the 100-panorama benchmark with explicit batching, quota handling, retry policy, and recovery from partial runs.
2. Add image-quality filtering for panoramas and directional crops before model training.
3. Extract visual embeddings from cached Street View crops using a selected vision backbone.
4. Build spatial joins or neighborhood summaries linking sampled road points, POIs, grid cells, and imagery.
5. Develop semantic POI representation features, including count, density, type-mixture, and learned embeddings.
6. Design and evaluate multimodal fusion models combining Street View imagery, POI semantics, and spatial context.
7. Add versioned dataset manifests for major generated artifacts to support reproducibility across experiments.

## Primary Implemented Files

| Path | Role |
|---|---|
| `R/road_environment_sampling.R` | Core road-network sampling, thinning, grid assignment, and map utilities. |
| `scripts/streetview/10_run_road_network_sampling_global.R` | End-to-end Seoul road sampling workflow. |
| `scripts/grid/10_build_seoul_grid_500m.R` | Seoul 500 m grid generation. |
| `scripts/visualization/render_leaflet_global.R` | Lightweight map diagnostic rendering from existing samples. |
| `scripts/POI/10_extract_seoul_osm_pois.R` | Semantic OSM POI extraction and canonical parquet/GPKG export. |
| `tests/test_road_environment_sampling.R` | Lightweight validation of road sampling logic. |
| `tests/test_gsv_metadata_pilot.py` | Metadata-only Google Street View pilot. |
| `tests/test_obtain_gsv_one.py` | One-panorama acquisition prototype. |
| `tests/test_obtain_gsv_100.py` | 100-panorama benchmark and crop-generation workflow. |

