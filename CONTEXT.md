# Executive Summary

Last reconstructed: 2026-06-09.

FUSE is a multimodal geospatial representation-learning project. Its long-term
goal is spatial scene similarity evaluation: constructing representations that
can compare neighborhoods, districts, corridors, and other geographic scenes by
their geometry, semantics, visual context, and spatial relationships.

The current implementation focuses on object-level infrastructure, especially
building representations, because object embeddings are the building blocks for
future scene embeddings. Building embeddings are not the final scientific goal;
they are an intermediate representation on the path toward scene-level
representation and similarity learning.

Completed as of 2026-06-09:

- nationwide VWorld building processing, with 14,388,938 building footprints;
- nationwide NGII POI processing, with 9,801,999 point POIs;
- nationwide KLIP/UPIS Togieeum processing, with 470,928 facility/planning
  polygons;
- Seoul OSM road and POI processing;
- Seoul Google Street View metadata acceptance and large image acquisition for
  40,000 accepted panoramas;
- Gwanak Geo2Vec validation;
- Geo2Vec scaling studies through 1M buildings.

Unfinished work:

- production semantic embedding generation;
- Street View visual embedding generation;
- 5M Geo2Vec stress test;
- full nationwide production Geo2Vec run;
- final semantic graph;
- fused object embeddings;
- scene embedding generation and spatial scene similarity evaluation.

Most important findings so far:

- single-model Geo2Vec is methodologically superior to independent chunked
  embeddings;
- useful Geo2Vec SDF sample density appears to flatten around 800-1,600
  samples/building;
- SDF sample-generation worker scaling plateaus around 8 workers;
- disk-backed global Geo2Vec training scales to at least 1M buildings;
- metadata-first Street View acquisition produced a clean 40,000-panorama Seoul
  dataset;
- hybrid semantics are necessary because NGII, KLIP/UPIS, OSM, roads, and
  Street View each capture different parts of geographic meaning.

# Relationship to Research Vision

[research_vision.md](research_vision.md) is the first-class research framing
document. It explains why the project exists, the dissertation-level motivation,
research questions, object-to-scene hierarchy, and long-term scientific goal of
spatial scene similarity evaluation.

This `CONTEXT.md` is the project-memory document. It records implementation
history, experimental findings, major design decisions, infrastructure
evolution, current status, unresolved issues, and next practical milestones.

The intended hierarchy is:

```text
README.md
  concise project landing page

research_vision.md
  theoretical motivation, dissertation framing, research questions,
  object-to-scene hierarchy, long-term vision

CONTEXT.md
  project memory, completed work, experimental history, design decisions,
  implementation evolution, current status

AGENTS.md
  operational rules, data conventions, and working instructions
```

To reduce duplication, this file does not restate the full theoretical
motivation for scene representation. It preserves the implementation and
experimental knowledge needed by a future Codex session to continue the work.

# Project Memory Frame

FUSE is currently organized around object-level representation as a foundation
for scene-level similarity learning. The working object representation combines:

- geometric form: what the building footprint looks like;
- semantic function: what activities, facilities, institutions, and urban
  contexts are associated with the building;
- visual context: what the surrounding streetscape looks like from Google
  Street View;
- spatial context: how the building relates to roads, administrative areas,
  neighborhoods, open space, and other urban infrastructure.

The near-term engineering target is a fused object embedding. The higher-level
research target is scene representation and similarity evaluation:

```text
Spatial objects
  -> object embeddings
  -> scene embeddings
  -> spatial scene similarity evaluation
```

Current project work is closest to completion for geometric embeddings and
Street View acquisition. Semantic embedding and final multimodal fusion are
designed conceptually but not yet complete as production pipelines.

# Conceptual Architecture

## Building Representation

The project treats a building as a central entity connected to multiple
evidence sources:

```text
VWorld building footprint
  -> geometry embedding from Geo2Vec
  -> semantic context from POIs, facilities, roads, admin areas
  -> visual context from nearby Google Street View imagery
  -> future fused object embedding
  -> future scene embedding
```

Stable building identifiers are essential. The nationwide VWorld building
pipeline creates `building_id`, and future building-level outputs should join
through that key. Embedding-specific IDs such as `geo2vec_internal_id` are
internal run keys and should not replace `building_id`.

## Geometry

Geometry is the building's physical footprint and morphology.

Primary dataset:

- VWorld nationwide building footprints.

Method:

- Geo2Vec / GeoNeuralRepresentation, currently used in a shape-only mode.

Research role:

- capture footprint morphology independently of observed activity, road context,
  and absolute location;
- provide a clean geometry channel that can later be fused with semantic and
  visual channels.

Important conceptual decision:

- Shape-only Geo2Vec is not a full building representation. It is the
  morphology component of the final representation.

## Semantics

Semantics are the building's observed or contextual urban meaning.

Primary semantic sources:

- NGII POI points: internal activity and facility observations;
- KLIP/UPIS facility polygons: external institutional and planning context;
- OSM POIs and polygons: auxiliary amenities, places, and contextual features;
- roads: access, frontage, and road-class context;
- administrative boundaries: district, neighborhood, and validation context.

Research role:

- distinguish internal activity from external context;
- represent buildings with relation-aware evidence rather than flat labels;
- avoid treating missing observations as true absence of meaning.

Preferred semantic framing:

```text
internal_activity:
  NGII or OSM POIs inside or directly associated with a building

external_institutional_context:
  KLIP/UPIS planning and facility polygons intersecting or containing a building

spatial_morphology_context:
  roads, administrative areas, open space, neighborhood context

visual_context:
  Street View samples and image embeddings near the building
```

Example relation-aware token pattern:

```text
source:relation:level:value
```

Examples:

- `ngii:inside:class:restaurant`
- `upis:within:family:transport_facility`
- `osm:near:amenity:cafe`
- `road:frontage:class:primary`
- `admin:within:district:gwanak`

The exact token vocabulary is not finalized, but source and relation type should
remain visible in downstream features.

## Visual Context

Visual context comes from Google Street View.

Primary dataset:

- Seoul Google Street View metadata and imagery sampled from the road network.

Research role:

- capture visual streetscape features around buildings and roads;
- provide information not available in POIs, planning polygons, or geometry;
- support visual embedding models for multimodal fusion.

Important conceptual decision:

- Current directional crop names are fixed panorama-coordinate directions:
  front 0, right 90, rear 180, left 270. They are not road-relative or
  building-facing directions.

## Future Fusion and Scene Representation

The next project direction is to combine channels into fused object embeddings,
then aggregate objects and their relationships into scene embeddings. A likely
future pipeline is:

1. Use VWorld footprints as the building entity table.
2. Generate or load a geometry embedding for every building.
3. Build relation-aware semantic features from NGII, KLIP/UPIS, OSM, roads, and
   administrative context.
4. Generate visual embeddings from validated Street View image crops.
5. Link Street View samples to nearby buildings and roads.
6. Fuse geometry, semantic, and visual channels into object embeddings.
7. Aggregate object embeddings and relations into scene embeddings.
8. Validate scene embeddings with spatially robust similarity and
   generalization tasks.

# Major Design Decisions

## Use VWorld Buildings Instead of OSM Buildings

Decision:

- VWorld is the authoritative building footprint source.
- OSM buildings are not the primary building entity set.

Rationale:

- OSM building coverage and attribution are not reliable enough for a national
  building representation project.
- VWorld provides a more appropriate authoritative footprint foundation.
- OSM remains valuable for semantic and road context.

Implications:

- Building-level outputs should use VWorld `building_id`.
- OSM features should be treated as contextual evidence, not as replacement
  building entities.

## Separate Geometry and Attributes

Decision:

- Store large geometry in GeoPackage with a stable key.
- Store large attributes and analytical tables in Parquet with the same key.

Rationale:

- National-scale geometry and attributes are too large to duplicate casually.
- Geometry is expensive to load and often unnecessary for analytical joins.
- The split design makes validation, indexing, and downstream processing more
  manageable.

Implications:

- Future workflows must join by stable IDs.
- Do not place large attribute tables inside GeoPackage unless there is a
  specific interoperability reason.

## Standardize Spatial Analysis on EPSG:5186

Decision:

- EPSG:5186 is the preferred projected CRS for spatial operations and canonical
  processed outputs.

Rationale:

- The project operates primarily in Seoul and Korea, where projected metric
  operations are needed for distances, areas, buffers, and sampling.
- Consistent CRS reduces avoidable spatial errors.

Implications:

- Verify CRS before spatial operations.
- In R, use `sf::sf_use_s2(FALSE)` before project spatial processing.
- Reproject source datasets such as NGII, KLIP/UPIS, and OSM into EPSG:5186 for
  canonical outputs.

## Treat NGII as the Primary Semantic Activity Source

Decision:

- NGII POIs are the primary observed activity/facility signal for building
  semantics.

Rationale:

- NGII provides dense national point coverage and detailed classification.
- It is more appropriate than OSM alone for Korean building activity
  representation.

Implications:

- OSM POIs should supplement NGII, not replace it.
- Semantic feature design should preserve NGII classification detail where
  possible.

## Use a Hybrid Semantic Framework

Decision:

- Building semantics should combine NGII, KLIP/UPIS, OSM, roads,
  administrative context, and eventually Street View.

Rationale:

- No single source captures building meaning.
- Internal activity and external institutional context are different scientific
  signals.
- A building may have no observed internal POI but still be semantically
  meaningful because of planning context, roads, or visual evidence.

Implications:

- Keep semantic channels separate.
- Preserve source and relation type in feature names.
- Treat missing observations carefully rather than converting them to false
  negative semantic labels.

## Use Metadata-First Street View Acquisition

Decision:

- Query Street View metadata and apply acceptance criteria before downloading
  imagery.

Rationale:

- Image acquisition consumes API quota, bandwidth, and storage.
- Metadata can enforce provider, capture year, distance, and uniqueness before
  any image download.

Implications:

- The accepted metadata table is the authoritative Street View sample.
- Image materialization is a downstream step validated against metadata and
  manifests.

## Use Fixed Panorama-Coordinate Street View Crops

Decision:

- Directional crops are generated at fixed headings: front 0, right 90, rear
  180, left 270.

Rationale:

- This is reproducible and does not require estimating road-relative or
  building-facing headings.

Implications:

- Do not interpret `front` as road-facing or building-facing.
- A road-relative crop pipeline would be a separate methodological variant.

## Use Single-Model Geo2Vec Instead of Independent Chunk Embeddings

Decision:

- Geo2Vec embeddings should be trained in one shared latent space for a given
  entity set.
- Independent chunk-trained embeddings are not a final method.

Rationale:

- Each independently trained chunk has its own latent coordinate system.
- Chunk embeddings can rotate, scale, or otherwise drift relative to one
  another.
- Gwanak validation showed single-model embeddings are much stronger than
  chunked embeddings.

Implications:

- Chunking is acceptable for I/O, sample generation, caching, validation, and
  export.
- Training must maintain one persistent model and one global entity embedding
  table.

## Use Disk-Backed Geo2Vec Scaling Architecture

Decision:

- Large-scale Geo2Vec should use deterministic ID maps, disk-backed SDF sample
  caches, checksums, checkpoint/resume, and partitioned embedding export.

Rationale:

- The public GeoNeuralRepresentation code materializes too much in memory and
  lacks production-scale restart behavior.
- National-scale training needs reproducible cache generation and robust
  failure recovery.

Implications:

- Cache manifests and checksums are part of the research record.
- Resume must validate ID-map and sample-cache consistency.
- Engineering optimizations must be distinguished from paper-faithful
  reproduction.

## Keep External Research Code Separate

Decision:

- External repositories such as `~/fuse_external/GeoNeuralRepresentation` are
  not copied into `~/fuse`.
- Project wrappers and adaptations live in `~/fuse`.

Rationale:

- Separation preserves reproducibility and makes methodological modifications
  visible.

Implications:

- If external source code is modified, document why, how it changes the method,
  and how reproducibility is affected.

# Current Research Status

Status date: 2026-06-09.

## Completed

Nationwide building processing:

- VWorld national building footprints have been processed into canonical
  geometry and attribute outputs.
- Scale: 14,388,938 buildings.
- This is the primary building entity set for future national representation.

Nationwide NGII processing:

- NGII POI points have been processed nationally.
- Scale: 9,801,999 points.
- This is the primary internal activity/facility dataset for semantic
  representation.

Nationwide KLIP/UPIS processing:

- KLIP/UPIS Togieeum facility polygons have been inventoried and processed.
- Scale: 470,928 facility/planning polygons.
- This is the primary external institutional/planning context dataset.

OSM road and POI processing:

- Seoul and national OSM POI outputs exist.
- Seoul road networks exist for canonical road storage and Street View sampling.
- OSM is used for roads and auxiliary semantic context.

Seoul Street View acquisition:

- A final 40,000-panorama Seoul Street View metadata dataset exists.
- Large image acquisition is complete and validated.
- Raw panoramas and directional semantic crops are available.
- The completion validation dated 2026-05-25 passed.

Gwanak Geo2Vec validation:

- Gwanak VWorld building subset is complete.
- Chunked Geo2Vec embeddings were generated as an operational baseline.
- Single-model Geo2Vec embeddings were generated and validated.
- Strict validation showed single-model embeddings outperform chunked
  embeddings.

Geo2Vec scaling studies:

- Global-model prototypes completed at 50k, 100k, 300k, and 1M buildings.
- Worker scaling was tested.
- Sample density sensitivity and saturation studies were completed.

## In Progress or Designed but Not Complete

Semantic embedding generation:

- The conceptual framework is mature.
- The final production semantic graph or semantic embedding table was not found.
- Relation-aware feature design still needs implementation and validation.

Visual embedding generation:

- Street View images are acquired and validated.
- A final visual embedding table was not found.
- Image model choice, crop aggregation, and building linkage remain open.

Multimodal fusion:

- Fusion is the long-term research goal.
- No final fused object representation was found.
- No scene embedding or spatial scene similarity evaluation framework was found.
- Evaluation tasks for fused object and scene embeddings still need to be
  defined and run.

Epoch-saturation Geo2Vec:

- Some epoch-saturation artifacts exist under the large-scale Geo2Vec output
  tree.
- No final markdown report was recovered.
- Treat this as incomplete until summarized and validated.

## Not Yet Completed

5M Geo2Vec stress test:

- Not found as of 2026-06-09.
- The recommended next engineering test is about 800 SDF samples/building with
  the global-model cache architecture.

Nationwide production Geo2Vec:

- A full 14,388,938-building production run was not found.
- The 1M run validates architecture, not national completion.

Final semantic graph:

- Not found.
- Needs integration of VWorld buildings, NGII POIs, KLIP/UPIS polygons, OSM,
  roads, admin areas, and Street View associations.

Final fused representation:

- Not found.
- Requires geometry embeddings, semantic embeddings, visual embeddings, object
  fusion, scene aggregation, and a similarity-evaluation strategy.

# Major Experimental Findings

## Single-Model Geo2Vec Beats Chunked Geo2Vec

The most important Geo2Vec methodological finding is that independent chunk
embeddings are not suitable as canonical object embeddings. They can be
generated quickly, but each chunk learns its own latent space. Strict Gwanak
validation showed that a single shared model outperforms chunked embeddings
across all tested geometry targets and validation schemes.

Representative Gwanak strict XGBoost findings:

- Single-model random-split R2:
  - bbox area ratio: 0.738;
  - compactness: 0.604;
  - elongation: 0.754;
  - log area: 0.104;
  - log perimeter: 0.169.
- Chunked random-split R2:
  - bbox area ratio: 0.302;
  - compactness: 0.218;
  - elongation: 0.368;
  - log area: about 0.010;
  - log perimeter: about 0.020.

Lesson:

- Latent-space consistency matters more than using more dimensions.

## Geo2Vec Density Saturates Around 800-1600 Samples per Building

Gwanak sample-density experiments showed that very low SDF sample density is
useful for engineering tests but not final quality. Performance improves
substantially through several hundred samples/building and then begins to
flatten.

Important saturation results:

- about 198 samples/building: mean R2 0.5778;
- about 404 samples/building: mean R2 0.6212;
- about 800 samples/building: mean R2 0.6291;
- about 1,613 samples/building: mean R2 0.6426;
- about 3,214 samples/building: mean R2 0.6543;
- about 5,026 samples/building: mean R2 0.6616.

Lesson:

- Use about 800 samples/building for engineering stress tests.
- Use about 1,600 samples/building as the first quality-oriented production
  candidate.
- Do not treat low-density 1M results as final-quality embeddings.

## Geo2Vec Worker Scaling Plateaus Around 8 Workers

SDF sample generation was benchmarked with 8, 16, 24, 32, and 40 workers on a
100k-building workload.

Finding:

- All worker counts produced valid equivalent outputs.
- 16 workers was only about 1% faster than 8.
- 24, 32, and 40 workers were slower.

Lesson:

- Use 8 workers for the next 5M stress test unless there is a specific reason
  to retest parallelism.

## Disk-Backed Global Geo2Vec Scales to 1M Buildings

The large-scale Geo2Vec prototype successfully trained global models at 50k,
100k, 300k, and 1M buildings.

Important 1M result:

- 1,000,000 buildings;
- 24,044,361 SDF samples;
- 5,400 training steps;
- last validation L1 about 0.03554;
- exported 1M finite embeddings.

Lesson:

- The architecture is viable beyond Gwanak scale.
- The next unknown is not whether a global model can work at 1M, but how the
  system behaves at 5M and full national scale with higher sample density.

## Metadata-First Street View Acquisition Is Effective

The Street View workflow successfully created a 40,000-panorama Seoul dataset
through metadata-first filtering.

Important findings:

- final accepted panoramas: 40,000;
- duplicate accepted pano IDs: 0;
- metadata success rate in diagnostics: 0.964533;
- accepted panorama distance median: 4.383 m;
- accepted maximum distance: 19.999 m;
- large image acquisition validation: PASS.

Lesson:

- Metadata-first acceptance avoids wasteful image acquisition and gives a clean
  sample with provider, year, distance, and deduplication guarantees.

## Fixed Street View Crop Headings Are Reproducible but Limited

Current crop headings are fixed panorama-coordinate views. This avoids ambiguity
and supports reproducible image extraction.

Lesson:

- Current crops are useful for general streetscape visual embeddings.
- They should not be interpreted as road-facing or building-facing views.
- Any future road-relative or building-facing crop design should be documented
  as a distinct method.

## Hybrid Semantics Are Necessary

Semantic framework analysis concluded that no single semantic source is
sufficient.

Findings:

- NGII gives dense observed activity/facility points.
- KLIP/UPIS provides institutional and planning context that POIs miss.
- OSM contributes useful auxiliary amenities and places.
- Roads and administrative areas provide contextual structure.
- Street View adds visual evidence not captured by tabular or vector data.

Lesson:

- Building semantics should be relation-aware and multi-source.
- Missing internal POIs should not be interpreted as semantic emptiness.

# Data Assets

This section lists only the major datasets needed to continue the project. For
storage rules and conventions, read `AGENTS.md`.

## VWorld Buildings

Purpose:

- authoritative building entity set and footprint geometry;
- source for geometry embeddings and building-level joins.

Scale:

- 14,388,938 nationwide buildings;
- Gwanak experimental subset: 38,547 buildings.

Canonical locations:

- nationwide geometry:
  `~/fusedatalarge/processed/korea_buildings_vworld.gpkg`;
- nationwide attributes:
  `~/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet`;
- Gwanak geometry:
  `~/fusedatalarge/processed/gwanak_buildings_vworld.gpkg`;
- Gwanak attributes:
  `~/fusedatalarge/processed/gwanak_buildings_vworld_attributes.parquet`.

Research use:

- building morphology;
- Geo2Vec shape embeddings;
- base building nodes for semantic and visual fusion.

## NGII POIs

Purpose:

- primary internal activity and facility signal for buildings.

Scale:

- 9,801,999 nationwide point POIs.

Canonical locations:

- geometry:
  `~/fusedatalarge/processed/korea_poi_ngii_point.gpkg`;
- attributes:
  `~/fusedatalarge/processed/korea_poi_ngii_attributes.parquet`.

Research use:

- building activity inference;
- semantic graph edges from buildings to POIs;
- relation-aware semantic tokens.

## KLIP/UPIS Togieeum Facility Polygons

Purpose:

- external institutional, planning, public facility, transport, open-space, and
  urban facility context.

Scale:

- 470,928 nationwide polygons across UQ151-UQ159 facility/planning families.

Canonical locations:

- geometry:
  `~/fusedatalarge/processed/korea_togieeum_polygon.gpkg`;
- attributes:
  `~/fusedatalarge/processed/korea_togieeum_polygon_attributes.parquet`.

Research use:

- planning and institutional context for buildings;
- semantic context where internal POIs are absent;
- external facility relation features.

## OSM Roads and POIs

Purpose:

- roads for sampling, accessibility, and frontage context;
- auxiliary POI/place semantics.

Scale:

- Seoul canonical roads: 107,912 features;
- current Seoul Street View sampling network: 47,824 no-tunnel, no-service road
  features;
- Seoul OSM POIs: 70,842 point and 20,229 polygon features;
- Korea OSM POIs: 364,071 point and 185,369 polygon features.

Canonical locations:

- Seoul canonical roads:
  `~/fusedata/osm/canonical/seoul_roads_canonical.gpkg`;
- Seoul Street View sampling network:
  `~/fusedata/osm/sampling/seoul_roads_sampling_network.gpkg`;
- OSM POIs:
  `~/fusedata/osm/canonical/gpkg/` and
  `~/fusedata/osm/canonical/parquet/`.

Research use:

- Street View sampling frame;
- road context and accessibility;
- auxiliary semantic features.

## Seoul Street View

Purpose:

- visual streetscape context for multimodal representation.

Scale:

- 40,000 accepted unique Seoul panoramas;
- 40,000 raw panoramas acquired;
- 160,000 directional semantic crops.

Canonical locations:

- final metadata:
  `~/fusedata/streetview/final/gsv_seoul_metadata_final_40000.parquet`;
- metadata and diagnostics:
  `~/fusedata/streetview/metadata/`;
- large image store and manifests:
  `~/fusedatalarge/streetview/`.

Research use:

- visual embeddings;
- road and neighborhood visual context;
- future building-to-street multimodal associations.

## Seoul Grid and Administrative Boundaries

Purpose:

- spatial balancing, sampling diagnostics, joins, and validation folds.

Scale:

- Seoul 500 m grid documented as 2,631 cells.

Canonical locations:

- grid:
  `~/fusedata/grid_500m/seoul_grid_500m.gpkg`;
- Korean administrative data:
  `~/fusedata/geodata/koreanadm/`;
- Seoul boundary:
  `~/fusedata/geodata/seoul_boundary.gpkg`.

Research use:

- Street View sample balancing;
- spatial block validation;
- district and administrative holdout tests.

## Geo2Vec Embeddings and Artifacts

Purpose:

- building footprint geometry embeddings.

Canonical locations:

- Gwanak chunked baseline:
  `~/fusedata/embeddings/gwanak_buildings_geo2vec_shape_full.parquet`;
- Gwanak single-model preferred embedding:
  `~/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_shape_single_model_lightweight.parquet`;
- large-scale prototype outputs:
  `~/fusedata/geo2vec_large_scale/`.

Research use:

- morphology channel of the final building representation;
- validation of geometric embedding quality;
- scaling testbed for national embeddings.

# Repository Architecture

The repository is code and documentation only. Heavy generated outputs live in
`~/fusedata` and `~/fusedatalarge`.

Important local areas:

- `AGENTS.md`: operational rules and storage conventions for future Codex
  sessions. Read it before running or editing workflows.
- `CONTEXT.md`: this long-term research memory.
- `README.md`: short project landing page.
- `config/`: shared path configuration for R and Python.
- `R/`: reusable R spatial helpers, especially road-environment sampling.
- `src/`: reusable Python helpers, especially Street View production utilities.
- `scripts/`: project workflows for grid, OSM/POI, buildings, Togieeum,
  Street View, visualization, validation, and embeddings.
- `docs/`: project notes and methodological documentation.
- `tests/gwanak_test/docs/`: Gwanak Geo2Vec experiment reports.
- `tests/geo2vec_large_scale/`: large-scale Geo2Vec prototype code and reports.

Important workflow families:

- building processing from VWorld;
- semantic source processing from NGII, KLIP/UPIS, and OSM;
- road sampling and Street View acquisition;
- Geo2Vec embedding generation and scaling;
- validation and experiment reporting.

# External Research Method Context

Geo2Vec work depends on the external repository:

- `~/fuse_external/GeoNeuralRepresentation`.

Reference paper:

- stored under `~/references/fuse_ref/`.

Project interpretation:

- GeoNeuralRepresentation implements a Geo2Vec-style neural SDF decoder with
  entity latent vectors.
- FUSE currently uses it for shape-only building footprint embeddings.
- Public code is useful for methodology but not production-scale processing
  without wrappers.

Important constraints:

- Do not copy the external repository into `~/fuse`.
- Prefer wrappers inside `~/fuse`.
- If modifying external code, document the reason and methodological impact.
- Keep paper-faithful reproduction, engineering scaling, and modified methods
  clearly separated.

# Open Methodological Questions

Semantic representation:

- What is the best representation form for semantic context: sparse
  relation-aware tokens, graph embeddings, learned text/category embeddings, or
  hybrid engineered features?
- How should conflicting or overlapping POI/facility signals be weighted?
- How should missing internal POIs be encoded without implying absence of
  activity?

Street View to building linkage:

- How should road-sampled panoramas be associated with buildings?
- Should linkage use nearest building, frontage, visibility, buffer-based
  aggregation, street segment association, or a learned attention mechanism?
- Should future crops be road-relative or building-facing?

Geo2Vec production:

- Will the 5M stress test confirm that the 1M architecture scales cleanly?
- What density is affordable for full national production?
- How should epoch count interact with sample density in final production?

Fusion and validation:

- What tasks best validate a fused object representation?
- What tasks best validate a scene representation for similarity evaluation?
- Which validation schemes are needed beyond random splits?
- How can evaluation avoid leaking spatial or administrative context?

Method claims:

- Which outputs are paper-faithful Geo2Vec reproductions?
- Which outputs are FUSE engineering adaptations?
- Which outputs should be described as production pipelines rather than
  methodological claims?

# Future Priorities

## 1. Reconcile Documentation

Several older docs are stale relative to current outputs.

Needed updates:

- Street View docs that say full image acquisition was not launched should be
  updated or clearly marked historical.
- Large-scale Geo2Vec docs that point to older output roots should point to
  `~/fusedata/geo2vec_large_scale`.
- Epoch-saturation artifacts should be summarized or removed from the active
  research narrative.

## 2. Build the Semantic Embedding Pipeline

Next research step:

- implement the hybrid semantic framework for buildings.

Minimum viable output:

- building-level semantic feature or embedding table keyed by `building_id`;
- explicit semantic channels for internal activity, external institutional
  context, OSM auxiliary context, roads, and admin context;
- documented handling of missing observations.

## 3. Generate Visual Embeddings

Next research step:

- use the validated 40,000-panorama Street View dataset to create visual
  embeddings.

Key choices:

- model family;
- whether to embed raw directional crops or semantic crops;
- how to aggregate multiple directions;
- how to link road-level imagery to buildings.

## 4. Run 5M Geo2Vec Stress Test

Next engineering step:

- run the global-model Geo2Vec pipeline on 5M buildings.

Recommended starting configuration:

- about 800 SDF samples/building;
- 8 workers for sample generation;
- disk-backed cache;
- checkpoint/resume validation;
- partitioned embedding export.

Goal:

- validate scaling behavior before full nationwide production.

## 5. Run Nationwide Production Geo2Vec

Next production geometry step:

- generate geometry embeddings for all 14,388,938 VWorld buildings.

Recommended starting point:

- use lessons from the 5M stress test;
- consider about 1,600 SDF samples/building for quality-oriented production;
- document density, epochs, seed, cache checksums, and validation results.

## 6. Build the Fused Object Representation

Near-term representation milestone:

- combine geometry, semantic, visual, road, and administrative context into a
  fused object embedding.

Expected output:

- object-level fused embedding table keyed by `building_id` for buildings;
- channel-specific metadata;
- validation report comparing geometry-only, semantics-only, visual-only, and
  fused representations.

## 7. Build Scene Embeddings and Similarity Evaluation

Long-term research milestone:

- aggregate object embeddings and spatial relations into scene representations;
- evaluate spatial scene similarity in a learned representation space.

Expected output:

- scene-level embedding table or model outputs;
- documented scene definitions and scales;
- similarity retrieval and clustering evaluations;
- comparison against geography-aware validation schemes.

## 8. Define Robust Evaluation Tasks

Future validation should include:

- random splits;
- spatial block splits;
- administrative holdout;
- possibly temporal or source holdout if time-varying data become available.

Evaluation should test both:

- whether embeddings encode known geometry/semantic properties;
- whether they generalize spatially without simply memorizing location.

# Maintenance Notes for Future Sessions

Use this file as the research-memory document. It should be updated when:

- a major dataset is added, replaced, or reprocessed;
- a new embedding run becomes canonical;
- an experiment changes a methodological decision;
- a stale report is superseded;
- a final semantic, visual, or fused representation is produced.

When updating, prefer:

- research implications over file inventories;
- decisions and rationale over command logs;
- validated outcomes over intentions;
- dates for all status claims;
- clear distinction between completed, in-progress, and proposed work.

Do not duplicate all operational rules from `AGENTS.md`; keep only research
context here.
