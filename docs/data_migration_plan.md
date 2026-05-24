# Data Migration Plan

## Current Path Structure

Before migration, all generated and cached artifacts lived inside the repository:

```text
fuse/
  data/
    geodata/
    grid_500m/
    osm/
      raw/
      canonical/
      sampling/
      metadata/
      logs/
      tmp/
    sampling_global/
    streetview/
      metadata/
      panoramas/
      crops/
      manifests/
      logs/
      previews/
      debug/
```

The nested `pre_models/GeoNeuralRepresentation/data` directory belongs to the external model checkout and is not part of the main FUSE data migration.

## Proposed New Structure

Keep source code, docs, and lightweight assets in the repository. Store generated data in a sibling directory by default:

```text
fuse/
  R/
  scripts/
  src/
  config/
    paths.yml
    paths.R
  docs/
  tests/

fusedata/
  geodata/
  grid_500m/
  osm/
  sampling_global/
  streetview/
```

The default data root is `../fusedata` relative to the repository root. `FUSE_DATA_ROOT` can override this on local machines, remote servers, and Windows.

## Central Path Strategy

- `config/paths.yml` documents the shared path contract.
- `config/paths.R` provides `fuse_repo_root()`, `fuse_data_root()`, `fuse_dir()`, and `fuse_file()` for R.
- `src/fuse_paths.py` provides matching `pathlib` helpers for Python.
- External `../fusedata` is preferred when it exists.
- Legacy `./data` remains a fallback for temporary backward compatibility.
- If neither exists, new outputs are created under `../fusedata`.

## Scripts Requiring Modification

- `R/road_environment_sampling.R`: default inputs/outputs now use centralized keys.
- `scripts/build_seoul_grid_500m.R`: grid input/output paths use `fuse_file()`.
- `scripts/run_road_network_sampling_global.R`: grid, OSM, sampling, debug, and map paths use centralized helpers.
- `scripts/render_leaflet_global.R`: reads existing outputs through centralized helpers and environment overrides.
- `scripts/extract_seoul_osm_pois.R`: PBF, GADM, canonical, metadata, logs, and temp paths use centralized helpers.
- `tests/test_gsv_metadata_pilot.py`: sample, metadata, summary, duplication, year distribution, and log paths use `fuse_paths`.
- `tests/test_obtain_gsv_one.py`: sample, metadata, panorama, crop, preview, and log paths use `fuse_paths`.
- `tests/test_obtain_gsv_100.py`: metadata, panorama, crop, manifest, log, and debug paths use `fuse_paths`.
- `tests/test_road_environment_sampling.R`: sources project code from the resolved repository root.

## Hardcoded Path and Working Directory Risks

- R drivers previously used `source("R/...")` and literal `data/...` paths, which assumed the repo root as working directory.
- Python Street View scripts previously built paths from `REPO_ROOT / "data/..."`, which broke once data moved outside the repository.
- Output messages and manifest records previously used `relative_to(REPO_ROOT)`, which fails for external data roots.
- Existing docs still referenced `data/` and needed updating.

## Output Directories

The migrated output directories are:

- `fusedata/grid_500m`
- `fusedata/geodata`
- `fusedata/osm/raw`
- `fusedata/osm/canonical`
- `fusedata/osm/canonical/gpkg`
- `fusedata/osm/canonical/parquet`
- `fusedata/osm/sampling`
- `fusedata/osm/metadata`
- `fusedata/osm/logs`
- `fusedata/osm/tmp`
- `fusedata/sampling_global`
- `fusedata/sampling_global/debug`
- `fusedata/streetview/metadata`
- `fusedata/streetview/panoramas/raw`
- `fusedata/streetview/crops/{front,right,rear,left}`
- `fusedata/streetview/manifests`
- `fusedata/streetview/logs`
- `fusedata/streetview/previews`
- `fusedata/streetview/debug`

## Reproducibility Considerations

- The seed-controlled sampling logic is unchanged.
- Data paths are configurable through `FUSE_DATA_ROOT`, not machine-specific absolute paths.
- Existing generated artifacts were moved, not recomputed.
- Lightweight validators check path discovery and write permissions without rerunning OSM or Street View workflows.
- Scripts create output parent directories automatically.
- Required inputs fail with explicit messages when missing.

## Before/After Examples

R before:

```r
grid_path <- "data/grid_500m/seoul_grid_500m.gpkg"
```

R after:

```r
grid_path <- fuse_file("seoul_grid_500m")
```

Python before:

```python
SAMPLES_PARQUET = REPO_ROOT / "data/sampling_global/seoul_road_network_samples.parquet"
```

Python after:

```python
SAMPLES_PARQUET = data_file("samples_global_parquet")
```

Environment override:

```bash
export FUSE_DATA_ROOT=/path/to/fusedata
Rscript scripts/validate_paths.R
python scripts/validate_paths.py
```

Windows PowerShell:

```powershell
$env:FUSE_DATA_ROOT = "D:\fusedata"
python scripts\validate_paths.py
```
