# Canonical core preprocessing

This directory builds the five source-integrated canonical datasets defined in
`config/data_contracts/`. It does not create scene-level clipped features or model
inputs.

## Safety model

- Inputs and outdated outputs are read-only.
- Work is written below `/mnt/hdd002/dhnyu/fusedata/tmp/core_preprocessing`.
- A canonical filename collision fails only that dataset.
- A staged output is atomically renamed only after its acceptance checks pass.
- Parallel workers create independent shards; GeoPackage merge and final raster
  publication use a single writer.
- Worker-local GDAL, OpenMP, BLAS, and MKL thread counts are one.

## Commands

Run the bounded smoke workflow:

```bash
Rscript scripts/preprocess/run_production.R --mode=smoke
```

Run production under a persistent session:

```bash
tmux new-session -d -s fuse-core-preprocess \
  "cd /members/dhnyu/fuse && Rscript scripts/preprocess/run_production.R --mode=production 2>&1 | tee logs/preprocessing/production_$(date +%Y%m%d_%H%M%S).log"
```

The ordered entry points are inventory, Building, Road, POI, land cover, DEM,
and final validation. Dataset result JSON files and resumable shard markers are
stored below the staging `qc/` and `markers/` directories.
