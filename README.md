# Seoul Road Environment Sampling

This repository contains an R workflow for global road-network-constrained Poisson-disk-style sampling across Seoul.

The current pipeline:

- builds a 500 m Seoul grid in EPSG:5186
- reads/caches OpenStreetMap roads from Geofabrik via `osmextract`
- filters road classes used for urban road-environment sampling
- constructs a unified Seoul road network
- generates dense regular candidate points along roads
- applies reproducible greedy Euclidean thinning to avoid clustered samples
- assigns final points to 500 m grids only after sampling
- writes a no-geometry parquet output
- renders an interactive Leaflet diagnostic map

## Repository Layout

Tracked source files are intentionally lightweight:

- `R/road_environment_sampling.R`: reusable functions
- `scripts/build_seoul_grid_500m.R`: builds the 500 m Seoul grid
- `scripts/run_road_network_sampling_global.R`: runs the full global road-network sampling workflow
- `scripts/render_leaflet_global.R`: rerenders only the Leaflet visualization from existing outputs
- `tests/test_road_environment_sampling.R`: lightweight global sampling tests

Generated outputs, cached OSM extracts, spatial files, parquet files, Leaflet HTML, and local reference corpora are ignored by Git.

## Reproducible Workflow

Run the lightweight tests:

```bash
Rscript tests/test_road_environment_sampling.R
```

Build the 500 m grid:

```bash
Rscript scripts/build_seoul_grid_500m.R
```

Run the full sampling workflow:

```bash
Rscript scripts/run_road_network_sampling_global.R
```

Rerender only the Leaflet map without rerunning OSM downloads or sampling:

```bash
Rscript scripts/render_leaflet_global.R
```

Useful environment variables:

- `SEOUL_TARGET_SAMPLE_COUNT`: final target point count, default `40000`
- `SEOUL_CANDIDATE_SPACING_M`: regular spacing for road candidates, default `10`
- `SEOUL_MIN_SAMPLE_SPACING_M`: greedy Euclidean thinning distance, default `50`
- `SEOUL_SAMPLE_SEED`: deterministic shuffle seed, default `20260517`
- `SEOUL_CANDIDATE_WORKERS`: parallel workers for road candidate generation, default `40`
- `SEOUL_CANDIDATE_CHUNK_SIZE`: road features per candidate-generation chunk, default `2000`
- `SEOUL_FORCE_GRID=true`: rebuild the 500 m grid
- `SEOUL_FORCE_OSM=true`: refresh the cached Geofabrik road extract
- `SEOUL_SAMPLES_PARQUET`: parquet path used by the Leaflet-only renderer
- `SEOUL_LEAFLET_MAX_POINTS`: sampled points rendered in Leaflet, default `30000`

The Leaflet diagnostic map intentionally renders only the Seoul boundary, 500 m grid boundaries, and sampled points. Road geometries are excluded from the interactive map to keep browser rendering stable; roads are still used by the sampling pipeline.

## Ignored Outputs

The `.gitignore` excludes generated and heavyweight artifacts, including:

- `data/`: all generated grids, OSM extracts, parquet outputs, debug GPKGs, and Leaflet files
- `*.gpkg`, shapefile sidecars, GeoJSON, rasters, parquet, Arrow/Feather, and CSV files
- Leaflet/htmlwidget exports such as `*.html` and `*_files/`
- image exports such as `*.png`
- `fuse_ref/`: local PDF/reference corpus
- `pre_models/`: external model checkout and large model data
- R session files and local caches

Existing outputs are not deleted by this setup. They remain available locally but are intentionally untracked because they are reproducible, large, machine-specific, or derived from external data.

## Optional renv

This repository can be initialized with `renv` if you want package-version pinning:

```r
install.packages("renv")
renv::init()
renv::snapshot()
```

The local `renv/library/` directory is ignored; `renv.lock` should be tracked if you initialize it.
