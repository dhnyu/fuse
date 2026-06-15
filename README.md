# FUSE

FUSE is a research codebase for multimodal geospatial representation learning.
The long-term goal is spatial scene similarity evaluation: learning
representations that can compare neighborhoods, districts, corridors, and other
geographic scenes by their structure, function, and visual context.

Object embeddings, especially building embeddings, are an intermediate layer in
that goal. The current implementation focuses on building-scale infrastructure
because buildings provide a stable object system for constructing higher-level
scene representations.

## Project Overview

The current project builds the object-level foundation for future scene
embeddings:

- geometry: VWorld building footprints and Geo2Vec-style shape embeddings;
- semantics: NGII POIs, KLIP/UPIS facilities, OSM POIs, roads, and
  administrative context;
- visual context: Google Street View panoramas and directional crops;
- future fusion: object embeddings aggregated into scene representations for
  spatial similarity evaluation.

## Conceptual Architecture

```text
Spatial objects
  VWorld buildings, NGII POIs, KLIP/UPIS facilities, OSM roads/POIs,
  administrative areas, Google Street View samples
        |
        v
Object embeddings
  geometry + semantics + visual context
        |
        v
Scene embeddings
  aggregated object and relation representations
        |
        v
Spatial scene similarity evaluation
```

## Major Datasets

- VWorld buildings: authoritative national building footprints, processed at
  14,388,938 buildings under `~/fusedatalarge/processed`; raw archives live
  under `~/fusedatalarge/raw/Building_vworld`.
- NGII POIs: primary national activity/facility point source, processed at
  9,801,999 points under `~/fusedatalarge/processed`; raw archives live under
  `~/fusedatalarge/raw/POI_ngii`.
- KLIP/UPIS Togieeum polygon POIs: canonical facility-filtered national
  polygon POI source for downstream embedding and analysis. Geometry is
  `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility.gpkg`;
  attributes are
  `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility_attributes.parquet`.
  This EPSG:5186 layer contains 134,912 polygon POIs after removing 1,127
  route-like transportation corridor polygons from the broader cleaned
  Togieeum layer. The legacy broader-cleaned files remain available as
  `~/fusedatalarge/processed/korea_polygon_poi_togieeum.gpkg` and
  `~/fusedatalarge/processed/korea_polygon_poi_togieeum_attributes.parquet`;
  raw archives live under `~/fusedatalarge/raw/togieeum`.
- Administrative and boundary reference geodata: large reference layers live
  under `~/fusedatalarge/geodata`.
- OSM roads and POIs: road sampling, accessibility, and auxiliary semantic
  context under `~/fusedatalarge/osm` because these are treated as source-like
  base layers.
- Google Street View: 40,000 accepted Seoul panoramas. Metadata and analysis
  products live under `~/fusedata/streetview`; raw images, crops, and large
  manifests live under `~/fusedatalarge/streetview`.
- Geo2Vec outputs: Gwanak validation embeddings and large-scale prototype
  artifacts are derived outputs. Their historical/default locations are
  `~/fusedata/embeddings`, `~/fusedata/gwanak_test/validation`, and
  `~/fusedata/geo2vec_large_scale`, but these output trees are not currently
  present in the active filesystem.

## Current Status

Completed as of 2026-06-09:

- nationwide VWorld building processing;
- nationwide NGII POI processing;
- nationwide KLIP/UPIS facility-filtered polygon POI processing;
- Seoul OSM road and POI processing;
- Seoul Street View metadata acceptance and large image acquisition;
- Gwanak Geo2Vec validation;
- Geo2Vec scaling studies through 1M buildings.

In progress or not yet complete:

- production semantic embedding generation;
- Street View visual embedding generation;
- 5M Geo2Vec stress test;
- full nationwide production Geo2Vec embedding run;
- final semantic graph;
- final fused object representation;
- scene embedding generation;
- spatial scene similarity evaluation framework.

## Repository Layout

```text
fuse/
  AGENTS.md                  project operating rules for future agents
  CONTEXT.md                 detailed research memory and status
  README.md                  this landing page
  config/                    shared R/Python path configuration
  R/                         reusable R spatial helpers
  src/                       reusable Python helpers
  scripts/                   project workflows
    buildings/               VWorld building processing
    poi/ and POI/            NGII and OSM POI processing
    togieeum/                KLIP/UPIS facility processing
    streetview/              Street View sampling and acquisition
    embedding/               Geo2Vec preparation/wrappers
    grid/                    Seoul grid workflows
    validation/              lightweight validation utilities
    visualization/           maps and diagnostics
  docs/                      project notes and methodology docs
  tests/gwanak_test/docs/    Gwanak Geo2Vec experiment reports
  tests/geo2vec_large_scale/ large-scale Geo2Vec prototypes and reports
```

Generated data are intentionally stored outside the repository:

- `~/fusedata`: derived outputs, metadata, embeddings, validation outputs,
  scene construction outputs, analysis products, and visualizations.
- `~/fusedatalarge/raw`: raw source datasets.
- `~/fusedatalarge/osm`: OSM source-derived base layers.
- `~/fusedatalarge/geodata`: large geospatial reference datasets.
- `~/fusedatalarge/streetview`: raw Street View imagery and crops.
- `~/fusedatalarge/processed`: canonical heavy processed geometry outputs.

## Working Notes

Path handling is centralized in:

- `config/paths.yml`;
- `config/paths.R`;
- `src/fuse_paths.py`.

The preferred projected CRS for spatial analysis is EPSG:5186.

## Further Reading

- [research_vision.md](research_vision.md): theoretical motivation,
  dissertation framing, research questions, object-to-scene hierarchy, and
  long-term scientific vision.
- [CONTEXT.md](CONTEXT.md): project memory, completed work, experimental
  history, design decisions, infrastructure evolution, and current status.
- [AGENTS.md](AGENTS.md): operational rules, data-location conventions, and
  working instructions for future agent sessions.
