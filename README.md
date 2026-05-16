# Seoul Road Environment Sampling

This repository contains an R workflow for probabilistic road-environment sampling over 1 km grid cells in Seoul.

The current pipeline:

- builds a 1 km Seoul grid in EPSG:5186
- reads/caches OpenStreetMap roads from Geofabrik via `osmextract`
- filters road classes used for urban road-environment sampling
- clips roads to each grid cell
- computes road-length proportions by highway class
- draws 10 reproducible line samples per grid cell
- writes a no-geometry parquet output
- renders an interactive Leaflet diagnostic map

## Repository Layout

Tracked source files are intentionally lightweight:

- `R/road_environment_sampling.R`: reusable functions
- `scripts/build_seoul_grid_1km.R`: builds the 1 km Seoul grid
- `scripts/run_road_environment_sampling_1km.R`: runs the full sampling workflow
- `scripts/render_leaflet_1km.R`: rerenders only the Leaflet visualization from existing outputs
- `tests/test_road_environment_sampling.R`: lightweight function and chunk-processing tests

Generated outputs, cached OSM extracts, spatial files, parquet files, Leaflet HTML, and local reference corpora are ignored by Git.

## Reproducible Workflow

Run the lightweight tests:

```bash
Rscript tests/test_road_environment_sampling.R
```

Build the 1 km grid:

```bash
Rscript scripts/build_seoul_grid_1km.R
```

Run the full sampling workflow:

```bash
Rscript scripts/run_road_environment_sampling_1km.R
```

Rerender only the Leaflet map without rerunning OSM downloads or sampling:

```bash
Rscript scripts/render_leaflet_1km.R
```

Useful environment variables:

- `SEOUL_SAMPLE_WORKERS`: number of `future.mirai` workers, default `12`
- `SEOUL_SAMPLE_CHUNK_SIZE`: grids per chunk, default `200`
- `SEOUL_SAMPLES_PER_GRID`: samples per grid, default `10`
- `SEOUL_FORCE_GRID=true`: rebuild the 1 km grid
- `SEOUL_FORCE_OSM=true`: refresh the cached Geofabrik road extract
- `SEOUL_LEAFLET_MAX_ROADS`: road features rendered in Leaflet, default `20000`
- `SEOUL_LEAFLET_MAX_POINTS`: sampled points rendered in Leaflet, default `10000`

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
