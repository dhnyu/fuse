# Street View Pipeline

This directory contains the core production Street View workflow.

Scripts are numbered by execution order:

- `10_run_road_network_sampling_global.R` builds the road-constrained baseline sample.
- `20_build_gsv_candidate_pool.R` builds an oversampled candidate pool for metadata-aware acceptance.
- `30_run_gsv_metadata_acceptance.py` queries and filters Street View metadata.
- `40_materialize_gsv_images.py` downloads accepted panoramas and generates crops.
- `50_finalize_gsv_dataset.py` selects the exact final valid dataset.
- `60_validate_gsv_final_dataset.py` validates final metadata and optional image outputs.

Inputs come from configured OSM, Seoul boundary, grid, and Street View metadata/image caches. Outputs are parquet manifests, raw panoramas, crops, diagnostics, and final validation reports under the configured data root.
