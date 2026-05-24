# Final Google Street View Sampling Pipeline

This document specifies the production Street View acquisition workflow for Seoul road-constrained sampling. The prior 100-image benchmark is no longer the methodological basis for the final dataset; it remains useful only as a prototype for image stitching and crop generation.

## Goal

The final retained dataset must contain exactly 40,000 valid Google Street View panoramas and crops. A sampled location is retained only when its metadata and image acquisition both pass validation.

## Road Network

The OSM construction framework is preserved:

- Seoul boundary clipping is retained.
- EPSG:5186 projected geometry is retained for network construction and distance-based thinning.
- Road-constrained sampling is retained.
- Deterministic seeds are retained.
- Poisson-disk-style thinning is retained.

The operational sampling network now excludes:

- OSM tunnel roads where `tunnel` is `yes`, `true`, or `1`.
- OSM `highway=service` roads.
- Non-road pedestrian/cycle/path classes already excluded by the previous workflow.

Road-network composition after removing service roads is written to:

- `streetview/metadata/gsv_sampling_network_composition.parquet`

This parquet reports road feature counts, total length, and length fractions by retained OSM highway class. It documents the class composition change caused by removing service roads.

## Production Workflow

The workflow now validates Street View availability before finalizing the sample.

1. Build the operational Seoul road network.
2. Generate an oversampled road candidate pool, normally at least 150,000 candidates.
3. Query the Google Street View metadata endpoint in resumable batches.
4. Reject candidates failing any metadata constraint.
5. Deduplicate by `pano_id`.
6. Continue until exactly 40,000 accepted unique panoramas are available.
7. Download panoramas only for accepted records.
8. Validate panorama files and generate front/right/rear/left crops.
9. Write manifests, diagnostics, and final validation outputs.

The key implementation scripts are:

- `scripts/streetview/10_run_road_network_sampling_global.R`
- `scripts/streetview/20_build_gsv_candidate_pool.R`
- `scripts/streetview/30_run_gsv_metadata_acceptance.py`
- `scripts/streetview/40_materialize_gsv_images.py`
- `scripts/streetview/50_finalize_gsv_dataset.py`
- `scripts/streetview/60_validate_gsv_final_dataset.py`
- `scripts/visualization/render_gsv_final_coverage_map.R`

## Acceptance Criteria

A candidate is accepted only when all of the following are true:

- Metadata status is `OK`.
- `pano_id` is present.
- Copyright/source text indicates Google imagery.
- Capture year is present and is at least 2018.
- Distance from sampled road point to panorama location is at most 20 meters.
- `pano_id` has not already been accepted.

Image materialization is a later gate:

- The stitched panorama must be a readable image.
- The panorama file must exceed the minimum byte-size threshold.
- All four directional crops must be readable images.

If a previously accepted panorama later fails image acquisition, it is not considered final. The metadata acceptance script should be run with enough accepted reserve records to cover image failures, image materialization should be rerun, and `scripts/streetview/50_finalize_gsv_dataset.py` selects the first exactly 40,000 records with successful panorama and crop validation.

## Deduplication Strategy

The accepted metadata table enforces one record per `pano_id`. Candidate records are processed in deterministic candidate-rank order. The first valid candidate for a panorama is accepted, and later candidates resolving to the same `pano_id` are rejected with:

- `duplicate_pano_id`

This prioritizes panorama diversity rather than merely point diversity.

## Resumability and Caching

Metadata queries are checkpointed to:

- `streetview/metadata/gsv_metadata_checkpoint.parquet`

The checkpoint is append-safe by `candidate_id`. Rerunning the metadata script skips already queried candidates and recomputes accepted/rejected tables from the full checkpoint.

The image materialization script reuses valid existing panorama files and regenerates missing crops. Crop settings are standardized in `src/gsv_production.py`:

- crop size: 512 x 512
- horizontal/vertical field of view: 90 degrees
- pitch: 15 degrees
- headings: front 0, right 90, rear 180, left 270

## Outputs

Candidate and metadata outputs:

- `streetview/metadata/gsv_candidate_pool.parquet`
- `streetview/metadata/gsv_metadata_checkpoint.parquet`
- `streetview/metadata/gsv_accepted_metadata.parquet`
- `streetview/metadata/gsv_rejected_metadata.parquet`
- `streetview/metadata/gsv_metadata_rejection_summary.parquet`
- `streetview/metadata/gsv_diagnostics_report.md`

Image outputs:

- `streetview/panoramas/raw/{pano_id}.jpg`
- `streetview/crops/front/{pano_id}_front.jpg`
- `streetview/crops/right/{pano_id}_right.jpg`
- `streetview/crops/rear/{pano_id}_rear.jpg`
- `streetview/crops/left/{pano_id}_left.jpg`
- `streetview/manifests/gsv_image_manifest.parquet`
- `streetview/manifests/gsv_final_manifest.parquet`
- `streetview/metadata/gsv_final_coverage_map.html`

## Diagnostics

The diagnostics report and parquet summaries include:

- Valid and rejected counts.
- Rejection reasons.
- Panorama distance distribution.
- Capture year distribution.
- Road-class distribution.
- Panorama duplication statistics.
- Metadata success rate.

Spatial coverage is retained through grid identifiers on accepted records. After finalization, `scripts/visualization/render_gsv_final_coverage_map.R` renders the final accepted locations with the Seoul boundary and 500 m grid. Visualization scripts are intentionally outside the numbered production sequence because they are optional diagnostics rather than required acquisition stages.

## Scalability

The production run is expected to be computationally and financially expensive. Recommended production settings:

- Candidate pool: 150,000 to 250,000 road candidates.
- Metadata workers: start with 8 and adjust to API quota/rate limits.
- Metadata batch size: 500.
- Image workers: start with 6.
- Metadata checkpoint interval: every batch.

Storage estimates depend on tile zoom and JPEG quality. At zoom 2, raw panoramas are commonly several hundred KB each to more than 1 MB each; 40,000 panoramas plus four 512 px crops each can require tens of GB. Keep the parquet metadata outputs compressed with zstd and avoid duplicate geometry serialization.

## Reproducibility

Reproducibility is controlled by:

- deterministic R candidate seeds,
- fixed CRS and road-filtering rules,
- deterministic candidate ranks,
- deterministic first-valid `pano_id` acceptance,
- resumable metadata checkpoints,
- stable pano-centered filenames,
- fixed crop projection settings.

Google Street View availability and metadata can change over time. The checkpoint parquet is therefore part of the reproducibility record and should be archived with the final dataset.

## Example Commands

Build the oversampled candidate pool:

```bash
Rscript scripts/streetview/20_build_gsv_candidate_pool.R
```

Run a small metadata pilot without launching the full 40,000 target:

```bash
GOOGLE_MAPS_API_KEY=... python scripts/streetview/30_run_gsv_metadata_acceptance.py --target-count 100 --max-candidates 500
```

Materialize a small accepted-image pilot:

```bash
python scripts/streetview/40_materialize_gsv_images.py --limit 25
```

Finalize the exact-size valid dataset after image materialization:

```bash
python scripts/streetview/50_finalize_gsv_dataset.py
```

Validate the final metadata constraints:

```bash
python scripts/streetview/60_validate_gsv_final_dataset.py
```

Validate metadata plus image acquisition:

```bash
python scripts/streetview/60_validate_gsv_final_dataset.py --require-images
```

Render the final coverage map:

```bash
Rscript scripts/visualization/render_gsv_final_coverage_map.R
```
