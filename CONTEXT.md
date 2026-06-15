# FUSE Project Memory

Status date: 2026-06-15

This document is project memory. It records completed work, implementation state, experimental findings, current priorities, and unfinished work.

It is not the research vision. The theoretical motivation, research philosophy, and research questions are maintained in `research_vision.md`.

Authority order for future work:

```text
AGENTS.md
    -> research_vision.md
    -> CONTEXT.md / CONTEXT_v2.md
    -> reports/
    -> implementation details
```

The current project priority, from `AGENTS.md`, is architectural validation on a bounded study area, currently Gwanak-gu. Nationwide scaling is preserved as implementation history and future capacity, but it is not the active primary objective.

## Current Status Dashboard

| Area | Current state | Memory note |
|---|---|---|
| Research direction | Scene-first spatial representation learning | Defined in `research_vision.md`; do not duplicate theory here |
| Active top priority | Gwanak-gu architecture validation | Demonstrate end-to-end scene representation before scaling |
| Current architecture target | `Spatial Scene -> Scene-Aware Object Embedding -> Scene Embedding -> Scene Similarity` | This replaces object-only or scale-first roadmaps |
| Study-area focus | Gwanak-gu | Current bounded validation area because building geometry and Geo2Vec results are mature there |
| Reference scene scale | Approximately 500 m fixed-size spatial crops | Scene materialization still needs implementation |
| Primary object nodes | Buildings, road segments, polygon POIs | From `AGENTS.md`; point POIs and Street View are usually evidence modalities |
| Supporting evidence | Point POIs, Street View imagery, attributes, administrative context | Used to enrich objects and scenes |
| Data foundation | Strong | National buildings/POIs/facilities, Seoul roads/POIs/GSV, Gwanak buildings exist |
| Regional working data | Standardized validation subsets now exist | `~/fusedatalarge/working_data/<region_key>/` with reproducible script and README |
| Geometry embeddings | Strongest implemented representation channel | Shape-only and full Gwanak Geo2Vec evidence exists |
| Semantic embeddings | Not yet production | Source data exist; scene-aware semantic feature construction remains unfinished |
| Visual embeddings | Not yet production | Seoul Street View imagery/crops exist; embeddings and Gwanak scene linkage remain unfinished |
| Scene-aware object embeddings | Not implemented | Current critical architecture gap |
| Scene embeddings | Not implemented | Current critical architecture gap |
| Scene similarity evaluation | Not implemented | Current critical architecture gap |
| Nationwide scaling | Demonstrated to 1M for shape-only Geo2Vec | Supporting evidence, not current priority |

## Current Architecture Memory

The current architecture to validate is:

```text
Spatial Scene
    -> Scene-Aware Object Embedding
    -> Scene Embedding
    -> Scene Similarity
```

For the current Gwanak-gu implementation target, this means:

```text
Gwanak-gu study area
    -> fixed-size spatial scenes, approximately 500 m
    -> object extraction
       buildings, road segments, polygon POIs
    -> evidence attachment
       point POIs, Street View imagery, administrative/context attributes
    -> initial object embeddings
       geometry, semantics, visual/context features
    -> relation-aware object updating
       within-scene graph or attention model
    -> scene-aware object embeddings
    -> scene embedding
    -> scene similarity evaluation
```

Important design implications:

- Objects should be interpreted inside a scene, not as isolated national records.
- Building embeddings are intermediate products, not final outputs.
- Road segments and polygon POIs should be treated as primary scene objects when building the scene graph.
- Point POIs should generally be semantic evidence, not primary object nodes.
- Street View imagery should generally be visual evidence associated with roads, buildings, or scenes, not a primary object node unless a specific experiment requires it.
- Location should be represented relative to the scene whenever possible to reduce absolute-coordinate memorization.
- Evaluation must test whether scene representations preserve useful geographic information, not only whether an embedding reconstructs its input.

## What Has Been Completed

### National Data Foundations

VWorld building processing is complete at national scale.

- Scale: 14,388,938 building footprints.
- Stable key: `building_id`.
- Role: primary building entity system for object extraction and geometry channels.
- Canonical geometry: `~/fusedatalarge/processed/korea_buildings_vworld.gpkg`.
- Canonical attributes: `~/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet`.

NGII POI processing is complete at national scale.

- Scale: 9,801,999 point POIs.
- Stable key: `poi_id`.
- Role: primary point-based semantic evidence for activities and facilities.
- Geometry: `~/fusedatalarge/processed/korea_poi_ngii_point.gpkg`.
- Attributes: `~/fusedatalarge/processed/korea_poi_ngii_attributes.parquet`.

KLIP/UPIS Togieeum facility/planning polygon processing is complete at national scale.

- Canonical downstream scale: 134,912 facility-filtered polygon POIs.
- Stable key: `polygon_poi_id`.
- Role: primary polygon POI object source for polygon POI analysis, shape embedding, multimodal embedding fusion, spatial scene representation learning, and downstream machine learning workflows.
- Canonical geometry: `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility.gpkg`.
- Canonical attributes: `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility_attributes.parquet`.
- CRS: EPSG:5186.
- Refinement note: the broader cleaned Togieeum polygon POI layer contained route-like transportation corridor polygons, primarily railway/subway corridor geometries. A geometry-based transportation refinement removed 1,127 route-like corridor polygons while preserving station-, terminal-, airport-, port-, parking-, depot-, and facility-like transportation polygons.
- Legacy broader-cleaned geometry: `~/fusedatalarge/processed/korea_polygon_poi_togieeum.gpkg`.
- Legacy broader-cleaned attributes: `~/fusedatalarge/processed/korea_polygon_poi_togieeum_attributes.parquet`.
- Historical broader KLIP/UPIS planning/facility merge products remain provenance for earlier national data-foundation work: `~/fusedatalarge/processed/korea_togieeum_polygon.gpkg` and `~/fusedatalarge/processed/korea_togieeum_polygon_attributes.parquet`.

OSM road and POI processing exists for Seoul and Korea-level auxiliary context.

- Seoul canonical roads: 107,912 features.
- Seoul Street View sampling network: 47,824 no-tunnel, no-service road features in current memory.
- Seoul OSM POIs: 70,842 point features and 20,229 polygon features.
- Korea OSM POIs: 364,071 point features and 185,369 polygon features.
- Current canonical root: `~/fusedatalarge/osm`.
- Role: road objects, Street View sampling frame, auxiliary POI context.

Standardized validation-region working data has been created under `~/fusedatalarge/working_data`.

- Purpose: regional subsets for spatial scene representation, validation, and downstream embedding workflows.
- README: `~/fusedatalarge/working_data/README.md`.
- Reproducible script: `~/fuse/scripts/working_data/create_validation_working_data.R`.
- Current region keys: `gwanak`, `seoul`, `daegu`, `jeju`, `gangneung`, `ganghwa`, `sejong`, `danyang`, `seongnam`, `incheon`, `daejeon`, `changwon`, `suwon`, and `korea`.
- Standard files per regional subset: `1_Building_vworld`, `2_pointPOI_osm`, `2_pointPOI_ngii`, `3_polygonPOI_osm`, `3_polygonPOI_togi`, `4_road_osm`, and `5_streetview`, using `.gpkg` plus `.parquet` for spatial layers and parquet only for Street View metadata.
- The `korea` directory is a symlink alias to nationwide source datasets and should not duplicate large nationwide files.
- A nationwide highway-tagged OSM road working source was derived under `~/fusedatalarge/working_data/_sources` because no documented nationwide canonical OSM road GPKG existed; source/raw OSM files were not modified.
- Street View working-data outputs contain metadata only and do not copy image files.

### Seoul Street View Acquisition

The Seoul Street View acquisition pipeline has been completed and validated for the final 40,000-panorama dataset.

Completed state:

- 40,000 accepted unique panoramas.
- 40,000 raw panoramas acquired.
- 160,000 directional semantic crops.
- Metadata-first acceptance and image materialization workflow implemented.
- Final metadata is the authoritative sampling product.

Important locations:

- Final metadata: `~/fusedata/streetview/final/gsv_seoul_metadata_final_40000.parquet`.
- Metadata and diagnostics: `~/fusedata/streetview/metadata/`.
- Large image store and manifests: `~/fusedatalarge/streetview/`.

Important limitation:

- Current directional crop labels are fixed panorama-coordinate headings. They are not road-relative and not building-facing.

### Gwanak Geometry and Geo2Vec Validation

Gwanak-gu has the strongest architecture-validation foundation.

Completed Gwanak assets:

- Gwanak VWorld building subset: 38,547 buildings.
- Gwanak geometry: `~/fusedatalarge/processed/gwanak_buildings_vworld.gpkg`.
- Gwanak attributes: `~/fusedatalarge/processed/gwanak_buildings_vworld_attributes.parquet`.
- Chunked Geo2Vec baseline.
- Single-model shape-only Geo2Vec.
- Strict XGBoost validation with random split, 500 m spatial block CV, and dong holdout.
- Full `[location, shape]` Geo2Vec candidate pipeline and Gwanak evaluations.

The most important geometry finding is that one shared latent space is required. Independent chunk embeddings are not suitable as canonical comparable object embeddings.

### Geo2Vec Scaling Evidence

Large-scale shape-only Geo2Vec engineering prototypes have been completed at:

- 50k buildings.
- 100k buildings.
- 300k buildings.
- 1M buildings.

The 1M run succeeded with:

- 1,000,000 buildings.
- 24,044,361 SDF samples.
- One persistent global `Geo2Vec_Model(n_poly=1000000)`.
- One global embedding table.
- 1,000,000 finite 32D exported embeddings.
- Historical/default output root: `~/fusedata/geo2vec_large_scale/`.

This proves scalability capacity, but it is no longer the organizing current objective. Use it as supporting evidence after the Gwanak scene architecture is validated. The current active filesystem no longer contains the `~/fusedata/geo2vec_large_scale/` output tree; the scientific findings are preserved in reports.

### Documentation and Report Organization

Generated reports have been consolidated under `reports/`, with `reports/0000_INDEX.md` as the report index.

Important current documentation rule:

- Generated Markdown reports belong under `reports/`.
- Stable long-term docs may live under `docs/`.
- `CONTEXT_v2.md` is a candidate replacement memory document and should be reviewed before replacing `CONTEXT.md`.

## What Has Been Learned

### Geometry Representation

Single-model Geo2Vec beats independent chunked Geo2Vec in Gwanak strict validation.

Representative strict XGBoost results:

| Target | Chunked random R2 | Single-model random R2 | Single-model spatial CV R2 |
|---|---:|---:|---:|
| bbox area ratio | 0.302 | 0.738 | 0.733 |
| compactness | 0.218 | 0.604 | 0.613 |
| elongation | 0.368 | 0.754 | 0.747 |
| log area | 0.010 | 0.104 | 0.089 |
| log perimeter | 0.020 | 0.169 | 0.159 |

Interpretation:

- Shape-only Geo2Vec captures normalized footprint morphology.
- It is strongest for compactness, elongation, and bounding-box area ratio.
- It is weaker for absolute area and perimeter because shape normalization suppresses scale.
- It should be used as a geometry channel, not a complete object representation.

### Full Geo2Vec at Gwanak Scale

Full `[location, shape]` Geo2Vec has been implemented and evaluated at Gwanak scale.

Completed reports show:

- Shape branch uses per-entity centering/scaling after dataset normalization.
- Location branch uses dataset/global normalization only.
- Full export order is `[location, shape]`.
- Full dimension in the Gwanak experiments is 64D: 32D location + 32D shape.
- No handcrafted geometry variables were added to embeddings.

Key full-data R evaluation finding:

- Full Geo2Vec preserves location strongly and retains shape signal.
- Shape-only remains strongest for compactness and bbox aspect ratio.
- Location-only is strongest or comparable for centroid recovery and also carries area/perimeter signal.

Selected spatial-split R xgboost R2 from full-data evaluation:

| Target | Shape | Location | Full Geo2Vec |
|---|---:|---:|---:|
| area | 0.0605 | 0.0910 | 0.2094 |
| perimeter | 0.1999 | 0.0820 | 0.3014 |
| compactness | 0.8887 | 0.0298 | 0.8882 |
| bbox aspect ratio | 0.9265 | 0.0140 | 0.9250 |
| centroid x | -0.0423 | 0.9940 | 0.9943 |
| centroid y | 0.0091 | 0.9924 | 0.9929 |

Interpretation for current work:

- Full Geo2Vec is useful for Gwanak architecture validation because it provides both shape and location information.
- It must be handled carefully in scene modeling because absolute location can create leakage.
- Scene-aware object work should test shape-only, location-only, and full geometry variants.

### Geo2Vec Epoch and Gamma Findings

The Gwanak full Geo2Vec epoch-saturation report tested epochs 1, 3, 5, and 10.

Current bounded finding:

- Epoch 10 performed best among tested settings for the Gwanak full-branch setup.

The gamma/code-regularization ablation tested four settings at epoch 10:

| Setting | Shape code_reg_weight | Location code_reg_weight | Summary |
|---|---:|---:|---|
| A current controlled | 0.1 | 0.1 | Prior controlled setting |
| B paper-like | 1.0 | 0.0 | Best selected spatial full-embedding score |
| C none | 0.0 | 0.0 | Competitive on some metrics |
| D mixed | 0.1 | 0.0 | Competitive but not best consolidated setting |

Mean selected spatial full Geo2Vec R2:

| Setting | Ranger | XGBoost |
|---|---:|---:|
| A current | 0.6874 | 0.7185 |
| B paper-like | 0.7013 | 0.7281 |
| C none | 0.6983 | 0.7248 |
| D mixed | 0.6982 | 0.7264 |

Interpretation for current work:

- Use these findings as bounded Gwanak geometry-channel evidence.
- Do not convert them into a national scaling roadmap unless explicitly requested.
- For scene-first validation, treat geometry variant choice as an ablation: shape-only, location-only, full, and possibly full with location-leakage controls.

### Sample Density and Scaling

Gwanak sample-density experiments show that very low SDF density is engineering-only and not quality-saturated.

Mean R2 by samples/building:

| Mean samples/building | Mean R2 |
|---:|---:|
| 197.9 | 0.5778 |
| 403.9 | 0.6212 |
| 799.8 | 0.6291 |
| 1613.2 | 0.6426 |
| 3213.6 | 0.6543 |
| 5026.3 | 0.6616 |

Interpretation:

- Around 800 samples/building reached 95% of the best observed mean R2 in that study.
- Around 1,600 samples/building is a practical quality-oriented default.
- The curve still improved slightly up to 5,000 samples/building, but marginal gains were small relative to cost.

Worker benchmark finding:

- 8 workers is the stable default.
- 16 workers improved throughput by only about 1%.
- 24, 32, and 40 workers were slower.

Scaling interpretation:

- These findings are preserved for future production.
- They are not the current top priority because architecture validation now precedes national deployment.

### Street View Findings

Metadata-first Street View acquisition works.

Important findings:

- Final accepted panoramas: 40,000.
- Duplicate accepted pano IDs: 0.
- Accepted maximum distance: just under 20 m in current memory.
- Large image acquisition validation passed.

Interpretation:

- The accepted metadata table is the authoritative visual sampling product.
- Image materialization is downstream from metadata.
- The 40,000-panorama Seoul corpus can support visual embeddings.

Limitation:

- Current crops are fixed panorama-coordinate crops. They are reproducible but not road-relative or building-facing.

### Semantic Findings

Hybrid semantics are necessary.

The project should not rely on one semantic source because:

- NGII POIs provide dense observed activity/facility points.
- KLIP/UPIS polygons provide institutional, planning, transport, public facility, and open-space context.
- OSM provides auxiliary amenities, places, roads, and context.
- Administrative boundaries support validation and contextual grouping.
- Street View can add visible streetscape semantics after visual embedding.

Current semantic representation remains unfinished. The next semantic work should be scene-aware: semantic evidence should be attached to objects inside scenes with source and relation type preserved.

## Current Implementation State by Architecture Layer

### 1. Spatial Scene

Status: not yet materialized as a canonical scene table.

Available ingredients:

- Seoul 500 m grid exists.
- Gwanak boundary/building subset exists.
- Road and POI layers exist for Seoul.
- Gwanak can be treated as the current architecture-validation study area.

Needed:

- Define `scene_id`.
- Define scene geometry, likely fixed-size crops around grid cells or sampled anchors.
- Decide inclusion rules for buildings, roads, polygon POIs, point POIs, and Street View evidence.
- Store scene geometry and scene-object membership tables.
- Represent object positions relative to scene geometry.

Minimum Gwanak scene output:

- `scene_id`
- scene polygon or bounding box
- scene centroid
- scene scale metadata
- object membership tables keyed by `scene_id` and object stable IDs
- train/validation/test split metadata

### 2. Object Extraction

Status: source objects exist; scene-specific object extraction is not yet canonical.

Primary object nodes:

- Buildings.
- Road segments.
- Polygon POIs.

Supporting evidence:

- Point POIs.
- Street View imagery.
- Administrative context.
- Object attributes.

Needed:

- For each Gwanak scene, extract buildings, road segments, polygon POIs.
- Attach point POIs to objects or scenes through explicit relations such as inside, near, contained_by, or within_buffer.
- Attach Street View samples to roads, nearby buildings, or scenes through explicit relation metadata.
- Preserve stable IDs and relation types.

### 3. Initial Object Embeddings

Status: partially implemented.

Building geometry:

- Shape-only Gwanak Geo2Vec exists.
- Full `[location, shape]` Gwanak Geo2Vec exists as bounded implementation evidence.
- Shape/location/full variants should be evaluated in scene architecture validation.

Building semantics:

- Source data exist.
- No production semantic embedding table exists.
- Relation-aware semantic features still need implementation.

Building visual context:

- Street View images exist for Seoul.
- No production visual embedding table exists.
- Gwanak-specific Street View-to-object or Street View-to-scene linkage is not complete.

Road embeddings:

- Road geometries and attributes exist.
- No road embedding model is currently canonical.

Polygon POI embeddings:

- Canonical KLIP/UPIS Togieeum polygon POI inputs for downstream embedding are the facility-filtered files: `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility.gpkg` and `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility_attributes.parquet`.
- The broader cleaned files `~/fusedatalarge/processed/korea_polygon_poi_togieeum.gpkg` and `~/fusedatalarge/processed/korea_polygon_poi_togieeum_attributes.parquet` are legacy/provenance outputs and include 1,127 route-like transportation corridor polygons that should not be used by default for embedding.
- OSM polygon POI data also exist as auxiliary context.
- No polygon POI embedding model is currently canonical.

### 4. Scene-Aware Object Embedding

Status: not implemented.

This is the current main architecture gap.

Needed:

- A method to update object embeddings using within-scene context.
- A relation graph or attention structure connecting buildings, roads, and polygon POIs.
- A way to attach point POI and Street View evidence without treating them as primary nodes by default.
- Missingness indicators for absent or weak semantic/visual evidence.
- Ablations to compare isolated object embeddings against scene-aware object embeddings.

Candidate relation types:

- building-building: proximity, adjacency, same scene.
- building-road: nearest road, frontage candidate, distance band.
- road-road: intersection, connectivity, same class, proximity.
- building-polygon: contained_by, intersects, near.
- road-polygon: intersects, near, serves.
- polygon-polygon: overlap, containment, proximity.
- point POI evidence: inside building, near building, near road, within scene.
- Street View evidence: near road, near building, within scene.

### 5. Scene Embedding

Status: not implemented.

Needed:

- Aggregate scene-aware object embeddings into one vector per `scene_id`.
- Preserve enough metadata to interpret which objects and modalities contributed.
- Compare pooling strategies, such as mean pooling, attention pooling, graph pooling, or transformer readout.

Minimum first baseline:

- Build a simple scene embedding from aggregated building/road/polygon features.
- Use modality summaries and object-count features as transparent baselines.
- Compare against learned scene-aware embeddings later.

### 6. Scene Similarity Evaluation

Status: not implemented.

Needed:

- Similarity/retrieval metrics over scene embeddings.
- Random and spatial validation splits.
- Qualitative retrieval inspection.
- Ablations by modality and relation type.
- Leakage diagnostics for absolute location and administrative identity.

Possible bounded Gwanak evaluation tasks:

- Retrieve scenes with similar building morphology distributions.
- Retrieve scenes with similar semantic composition.
- Retrieve scenes with similar road/context structure.
- Predict held-out scene attributes.
- Compare random split vs spatial holdout.
- Test whether scene-aware object embeddings improve over object-only aggregation.

## Data Inventory for Current Work

### Core Gwanak Scene Validation Data

Gwanak buildings:

- Geometry: `~/fusedatalarge/processed/gwanak_buildings_vworld.gpkg`.
- Attributes: `~/fusedatalarge/processed/gwanak_buildings_vworld_attributes.parquet`.
- Scale: 38,547 buildings.
- Current use: geometry channel, scene object extraction, validation labels.

Gwanak Geo2Vec outputs:

- Shape-only and full Geo2Vec products were historically written under `~/fusedata/gwanak_test/validation/` and `~/fusedata/geo2vec_large_scale/`.
- These output trees are not currently present in the active filesystem; use the reports as provenance unless the derived outputs are restored or regenerated.
- Current use: initial building geometry embeddings and geometry-channel ablations.

Seoul roads and grid:

- Seoul canonical roads: `~/fusedatalarge/osm/canonical/seoul_roads_canonical.gpkg`.
- Seoul Street View sampling network: `~/fusedatalarge/osm/sampling/seoul_roads_sampling_network.gpkg`.
- Seoul 500 m grid derived-output location: `~/fusedata/grid_500m/seoul_grid_500m.gpkg`.
- The grid output is not currently present in the active filesystem and should be regenerated only when needed.
- Current use: Gwanak scene extraction, road objects, validation splits, Street View linkage.

Seoul Street View:

- Final metadata: `~/fusedata/streetview/final/gsv_seoul_metadata_final_40000.parquet`.
- Large imagery: `~/fusedatalarge/streetview/`.
- Current use: visual evidence; embeddings/linkage unfinished.

### National Data Preserved for Future Scaling

Nationwide VWorld:

- Geometry: `~/fusedatalarge/processed/korea_buildings_vworld.gpkg`.
- Attributes: `~/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet`.

Nationwide NGII:

- Geometry: `~/fusedatalarge/processed/korea_poi_ngii_point.gpkg`.
- Attributes: `~/fusedatalarge/processed/korea_poi_ngii_attributes.parquet`.

Nationwide KLIP/UPIS:

- Canonical downstream polygon POI geometry: `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility.gpkg`.
- Canonical downstream polygon POI attributes: `~/fusedatalarge/processed/korea_polygon_poi_togieeum_facility_attributes.parquet`.
- Legacy broader-cleaned polygon POI geometry: `~/fusedatalarge/processed/korea_polygon_poi_togieeum.gpkg`.
- Legacy broader-cleaned polygon POI attributes: `~/fusedatalarge/processed/korea_polygon_poi_togieeum_attributes.parquet`.
- Historical broader planning/facility merge geometry: `~/fusedatalarge/processed/korea_togieeum_polygon.gpkg`.
- Historical broader planning/facility merge attributes: `~/fusedatalarge/processed/korea_togieeum_polygon_attributes.parquet`.

Large-scale Geo2Vec:

- Historical/default root: `~/fusedata/geo2vec_large_scale/`.
- Current role: completed scalability evidence preserved in reports and reusable implementation infrastructure. The output tree is not currently present in the active filesystem.

## Relevant Implementation Reports

Read these reports when continuing architecture validation:

1. `reports/20260608_0307_gwanak_geo2vec_strict_validation_xgboost.md`
2. `reports/20260609_0000_geoneuralrepresentation_shape_location_audit.md`
3. `reports/20260610_0359_gwanak_full_geo2vec_pipeline_and_evaluation.md`
4. `reports/20260610_0427_gwanak_full_geo2vec_epoch_saturation.md`
5. `reports/20260610_0447_geo2vec_parallel_runner_and_r_evaluation_refactor.md`
6. `reports/20260610_0505_gwanak_full_geo2vec_full_r_evaluation.md`
7. `reports/20260610_0533_gwanak_full_geo2vec_gamma_ablation.md`
8. `reports/20260608_0000_geo2vec_sample_density_saturation.md`
9. `reports/20260608_0000_sdf_worker_scaling_benchmark.md`
10. `reports/20260608_0000_korea_geo2vec_large_scale_pipeline_1m.md`

Use the large-scale reports as engineering evidence, not as current priority justification.

## Current Unfinished Work

### Critical Architecture Gaps

The following are required for the current Gwanak architecture-validation objective:

1. Canonical Gwanak scene definition and scene table.
2. Scene-object membership tables for buildings, roads, and polygon POIs.
3. Scene-aware relation schema.
4. Building semantic feature/embedding pipeline for Gwanak scenes.
5. Street View visual embedding generation.
6. Street View-to-road, Street View-to-building, or Street View-to-scene linkage.
7. Road object features or embeddings.
8. Polygon POI object features or embeddings.
9. Scene-aware object embedding model or baseline.
10. Scene embedding baseline.
11. Scene similarity evaluation and retrieval diagnostics.
12. Leakage diagnostics for absolute location and administrative identity.

### Channel-Specific Gaps

Geometry:

- Shape-only and full Geo2Vec exist for Gwanak.
- Need scene-relative position features.
- Need geometry ablations inside the scene architecture.
- Need decision on how much absolute location to allow.

Semantics:

- Source data exist.
- Need relation-aware semantic features keyed by object and `scene_id`.
- Need missingness handling.
- Need source-specific metadata retained through fusion.

Visual:

- Images/crops exist.
- Need visual embeddings.
- Need linkage to roads/buildings/scenes.
- Need crop-type metadata and model provenance.

Relations:

- Need graph schema.
- Need edge construction rules.
- Need distance/buffer thresholds or learned relation design.

Evaluation:

- Need scene-level retrieval tasks.
- Need random and spatial validation splits.
- Need ablations by modality and relation type.
- Need qualitative retrieval review outputs.

## Current Top Priority: Gwanak-gu Architecture Validation

The next work should validate the architecture on Gwanak-gu before any national deployment work.

### Priority 1: Build the Gwanak Scene Substrate

Objective:

- Materialize spatial scenes and scene-object memberships.

Expected outputs:

- Gwanak `scene_id` table.
- Scene geometries at approximately 500 m scale.
- Scene membership tables for buildings, roads, polygon POIs, point POI evidence, and Street View evidence.
- Scene split metadata for random/spatial evaluation.

Scientific value:

- Converts the project from object infrastructure to scene-first implementation.

Implementation difficulty:

- Moderate. Data exist, but scene definitions and joins need careful, deterministic implementation.

### Priority 2: Build Scene-Aware Object Inputs

Objective:

- Create initial object-level inputs that can be updated in scene context.

Expected outputs:

- Building geometry embedding variants: shape-only, location-only, full where available.
- Building semantic features from NGII/OSM/KLIP/UPIS relation evidence.
- Road features or road embeddings.
- Polygon POI features or embeddings.
- Visual feature placeholders or embeddings, depending on GPU/model availability.

Scientific value:

- Establishes multimodal object inputs without treating them as final outputs.

Implementation difficulty:

- Moderate to high because semantic and visual linkage are not yet productionized.

### Priority 3: Implement First Scene-Aware Object Embedding Baseline

Objective:

- Test whether object representations improve when interpreted inside scenes.

Expected outputs:

- Relation graph or attention-ready edge table.
- Baseline scene-aware object embeddings.
- Ablations comparing object-only vs scene-aware variants.

Scientific value:

- Directly validates the current architecture's central claim.

Implementation difficulty:

- High, but bounded by Gwanak scope.

### Priority 4: Build First Scene Embedding and Similarity Evaluation

Objective:

- Produce one embedding per scene and evaluate similarity/retrieval.

Expected outputs:

- Scene embedding table keyed by `scene_id`.
- Similarity matrix or nearest-neighbor retrieval table.
- Retrieval case-study outputs.
- Quantitative diagnostics under random and spatial splits.

Scientific value:

- Provides the first end-to-end demonstration of the research architecture.

Implementation difficulty:

- High, because validation design matters as much as model code.

## Deferred Work

The following work is not deleted, but it is not the current priority:

- 5M Geo2Vec stress test.
- Full nationwide production Geo2Vec.
- National deployment optimization.
- Large-scale stress testing beyond what is needed for Gwanak architecture validation.
- Road-relative or building-facing Street View crop redesign.
- Nationwide visual embedding expansion.

These should be revisited after the Gwanak scene-first architecture has a working end-to-end baseline and evaluation report.

## Repository Guide

Important root files:

- `AGENTS.md`: authoritative working rules and current priority.
- `research_vision.md`: authoritative research vision.
- `CONTEXT.md`: current canonical memory until replaced.
- `CONTEXT_v2.md`: proposed refactored memory.
- `README.md`: short repository overview.

Important implementation directories:

- `scripts/buildings/`: VWorld building processing.
- `scripts/poi/` and `scripts/POI/`: NGII and OSM POI processing.
- `scripts/togieeum/`: KLIP/UPIS facility polygon processing.
- `scripts/streetview/`: Street View sampling, metadata acceptance, image materialization, validation.
- `scripts/embedding/`: Geo2Vec preparation and wrapper scripts.
- `tests/gwanak_test/`: Gwanak Geo2Vec validation scripts.
- `tests/geo2vec_large_scale/`: Geo2Vec scaling, full-branch candidate workflows, R evaluation, and related diagnostics.
- `src/`: reusable Python helpers.
- `R/`: reusable R spatial helpers.
- `config/`: shared path configuration.
- `reports/`: generated reports and project memory support.
- `docs/`: stable methodological documentation and assets.

Important scripts for the current priority:

- `tests/geo2vec_large_scale/evaluate_geo2vec_embeddings.R`
- `tests/geo2vec_large_scale/build_gwanak_evaluation_split.py`
- `tests/geo2vec_large_scale/run_gwanak_full_geo2vec_pipeline.py`
- `tests/geo2vec_large_scale/run_gwanak_full_geo2vec_epoch_saturation.py`
- `tests/geo2vec_large_scale/run_gwanak_full_geo2vec_gamma_ablation.py`
- `scripts/streetview/30_run_gsv_metadata_acceptance.py`
- `scripts/streetview/45_materialize_gsv_large_semantic_images.py`
- `scripts/streetview/80_validate_gsv_large_semantic_images.py`

Scripts that likely need to be added next:

- Gwanak scene construction.
- Gwanak scene-object membership extraction.
- Semantic evidence attachment to scene objects.
- Street View evidence linkage to Gwanak scene objects.
- Scene graph construction.
- Scene embedding baseline.
- Scene similarity evaluation.

## External Research Method Context

Geo2Vec depends on:

- `~/fuse_external/GeoNeuralRepresentation`.

Rules:

- Do not copy external repositories into `~/fuse`.
- Prefer wrappers inside `~/fuse`.
- If modifying external code, document rationale, methodological impact, and reproducibility impact.
- Distinguish paper-faithful reproduction, FUSE methodological extension, scalability experiment, and production pipeline.

Current Geo2Vec interpretation:

- Shape-only Geo2Vec is a morphology channel.
- Full `[location, shape]` Geo2Vec is available as a bounded Gwanak implementation/evaluation product.
- Absolute location is useful for diagnostics but risky for scene similarity if it causes place memorization.
- For scene-first validation, geometry embeddings should be evaluated as ablation inputs, not final outputs.

## Maintenance Rules for Future Sessions

Update this memory when:

- A canonical Gwanak scene table is created.
- Scene-object membership outputs are created.
- A semantic feature or embedding table becomes canonical.
- A visual embedding table becomes canonical.
- A scene-aware object embedding experiment is completed.
- A scene embedding or similarity evaluation is completed.
- A major experimental result changes a design decision.
- A report supersedes old implementation status.

When updating:

- Preserve completed facts and validated findings.
- Record current state and unfinished gaps clearly.
- Avoid duplicating `research_vision.md`.
- Avoid turning project memory into a proposal.
- Distinguish active priority from deferred work.
- Keep national scaling evidence, but do not let it dominate the current roadmap unless explicitly requested.
