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
  14,388,938 buildings under `~/fusedatalarge/processed`.
- NGII POIs: primary national activity/facility point source, processed at
  9,801,999 points under `~/fusedatalarge/processed`.
- KLIP/UPIS Togieeum polygons: national institutional and planning context,
  processed at 470,928 polygons under `~/fusedatalarge/processed`.
- OSM roads and POIs: road sampling, accessibility, and auxiliary semantic
  context under `~/fusedata/osm`.
- Google Street View: 40,000 accepted Seoul panoramas with raw images and
  directional crops under `~/fusedata/streetview` and
  `~/fusedatalarge/streetview`.
- Geo2Vec outputs: Gwanak validation embeddings and large-scale prototype
  artifacts under `~/fusedata/embeddings`,
  `~/fusedata/gwanak_test/validation`, and
  `~/fusedata/geo2vec_large_scale`.

## Current Status

Completed as of 2026-06-09:

- nationwide VWorld building processing;
- nationwide NGII POI processing;
- nationwide KLIP/UPIS facility polygon processing;
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

- `~/fusedata`: canonical project outputs, metadata, embeddings, and
  visualizations;
- `~/fusedatalarge`: raw large datasets, nationwide processed geometry, and
  large Street View imagery.

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
