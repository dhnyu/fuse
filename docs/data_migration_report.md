# Data Migration Report

## Completed Changes

- Moved the repository-internal `data/` tree to the sibling directory `../fusedata`.
- Added centralized path configuration:
  - `config/paths.yml`
  - `config/paths.R`
  - `src/fuse_paths.py`
- Refactored R scripts and reusable R functions to use `fuse_file()` and `fuse_dir()`.
- Refactored Python Street View scripts to use `pathlib` helpers from `src/fuse_paths.py`.
- Added lightweight validation utilities:
  - `scripts/validate_paths.R`
  - `scripts/validate_paths.py`
- Updated `README.md` with path setup, environment variables, Linux/Windows examples, validators, and symlink guidance.

## Files Modified

- `README.md`
- `R/road_environment_sampling.R`
- `scripts/build_seoul_grid_500m.R`
- `scripts/run_road_network_sampling_global.R`
- `scripts/render_leaflet_global.R`
- `scripts/extract_seoul_osm_pois.R`
- `tests/test_road_environment_sampling.R`
- `tests/test_gsv_metadata_pilot.py`
- `tests/test_obtain_gsv_one.py`
- `tests/test_obtain_gsv_100.py`

## Files Added

- `config/paths.yml`
- `config/paths.R`
- `src/fuse_paths.py`
- `scripts/validate_paths.R`
- `scripts/validate_paths.py`
- `docs/data_migration_plan.md`
- `docs/data_migration_report.md`

## Architecture Decisions

- Use `../fusedata` as the portable default data root because it keeps data close to the repository without placing artifacts inside Git.
- Use `FUSE_DATA_ROOT` as the explicit override for servers, shared storage, Windows drives, and symlink-free deployments.
- Keep a temporary legacy fallback to `./data` so older checkouts can still run while migration propagates.
- Keep language-specific helpers small and parallel, with `config/paths.yml` documenting the shared contract.
- Preserve efficient formats already in use: GPKG for vectors, Parquet for tabular outputs, and JPEG/PNG only for image diagnostics.

## Compatibility Notes

- Existing commands continue to work from the repository root.
- R driver scripts now source project files from the resolved repository root when run via `Rscript`.
- Python scripts can run from any working directory because they bootstrap `src/` from their file location.
- Outputs outside the repository are displayed relative to the data root when possible.
- The nested `pre_models/GeoNeuralRepresentation/data` directory was not moved because it belongs to an ignored external checkout.

## Validation Performed

- Added path validators that create/check configured directories, verify write access, and report expected file discovery.
- `python scripts/validate_paths.py`: passed, using `/members/dhnyu/fusedata`.
- `Rscript scripts/validate_paths.R`: passed, using `/members/dhnyu/fusedata`.
- Python syntax compilation for refactored Python files: passed.
- R syntax parsing for refactored R files: passed.
- `Rscript tests/test_road_environment_sampling.R`: passed on synthetic geometries.
- No expensive OSM extraction, road sampling, map rendering, or Street View acquisition pipeline was rerun.

## Remaining Technical Debt

- The R and Python helper maps are intentionally mirrored; future changes should update `config/paths.yml`, `config/paths.R`, and `src/fuse_paths.py` together or introduce generated helper constants.
- Some older narrative documentation in `docs/fuse_progress_summary.md` still describes the historical `data/` layout.
- The Street View scripts remain prototype-scale and still need batching, rate limiting, and recovery design before any full acquisition run.

## Suggested Future Improvements

- Add a small CI check that runs both path validators.
- Consider a generated constants step from `config/paths.yml` if the path catalog grows.
- Add a repo-local `.Renviron.example` and `.env.example` for `FUSE_DATA_ROOT`.
- Decide whether to keep legacy `./data` fallback after all collaborators migrate.
