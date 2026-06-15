# Scene Grid Workflow

This directory contains grid-generation workflows for spatial scene construction.

Scene grids define fixed-size spatial crops that can be used to attach buildings, roads, polygon POIs, point POI evidence, and Street View metadata to a common `scene_id`. They are part of the scene-first representation-learning workflow, not final model outputs.

## Grid Types

The standard scene size is 500 m x 500 m in EPSG:5186.

Two grid types are supported by `create_scene_grids.R`:

- `nonoverlap`: 500 m cells with 500 m stride.
- `overlap_stride250m`: 500 m cells with 250 m stride.

The non-overlapping grid is intended as the canonical analysis and evaluation grid. It avoids duplicate spatial coverage and gives cleaner interpretation for scene similarity, retrieval, downstream prediction, and validation splits.

The overlapping grid is intended for training augmentation only. It increases the number of scene crops and exposes models to shifted local contexts, but adjacent overlapping cells share substantial spatial content.

Evaluation splits should avoid leakage from overlapping scenes. If overlapping grids are used in training, validation and test scenes should be separated spatially or derived from the non-overlapping grid.

## Boundary Handling

Grid cells are not clipped to the study-area boundary. Each retained cell remains a full 500 m square.

Cells are retained when they intersect the boundary. The workflow adds `coverage_ratio`, defined as:

```text
intersection area with boundary / full cell area
```

Keeping full square geometries preserves a consistent scene scale and avoids edge cells with different geometry sizes. Boundary effects can be handled downstream using `coverage_ratio`, `intersects_boundary`, and `within_boundary`.

## Required Columns

Each output grid contains:

- `scene_id`
- `region`
- `grid_type`
- `cell_size_m`
- `stride_m`
- `area_m2`
- `centroid_x`
- `centroid_y`
- `intersects_boundary`
- `within_boundary`
- `coverage_ratio`

## Script

```text
scripts/grid/create_scene_grids.R
```

Parameters use `--key=value` syntax:

- `--boundary-path`: boundary vector file path.
- `--boundary-layer`: optional layer name for multi-layer files.
- `--boundary-filter-column`: optional attribute column used to select a region from a larger boundary layer.
- `--boundary-filter-value`: optional attribute value used to select a region.
- `--output-dir`: directory where grid GeoPackages are written.
- `--region`: region key used in attributes and file names.
- `--target-crs`: target projected CRS. Default is EPSG:5186.
- `--cell-size-m`: scene cell size in meters. Default is 500.
- `--strides-m`: comma-separated stride values. Default is `500,250`.
- `--report-path`: Markdown generation report path.

The script creates missing directories, validates written outputs, prints a short report, and saves the same report to disk.

## Gwanak-gu Example

The default command generates the Gwanak-gu grids from the Korean sigungu administrative boundary using `SIGUNGU_CD=11210`:

```bash
Rscript scripts/grid/create_scene_grids.R
```

Equivalent explicit command:

```bash
Rscript scripts/grid/create_scene_grids.R \
  --boundary-path=/members/dhnyu/fusedatalarge/geodata/koreanadm/bnd_sigungu_00_2024_2Q.shp \
  --boundary-filter-column=SIGUNGU_CD \
  --boundary-filter-value=11210 \
  --output-dir=/members/dhnyu/fusedatalarge/working_data/gwanak \
  --region=gwanak \
  --target-crs=5186 \
  --cell-size-m=500 \
  --strides-m=500,250
```

Expected Gwanak outputs:

```text
/members/dhnyu/fusedatalarge/working_data/gwanak/gwanak_scene_grid_500m_nonoverlap.gpkg
/members/dhnyu/fusedatalarge/working_data/gwanak/gwanak_scene_grid_500m_overlap_stride250m.gpkg
```

## Another Region Example

Example for Seoul using a single-region boundary file:

```bash
Rscript scripts/grid/create_scene_grids.R \
  --boundary-path=/members/dhnyu/fusedatalarge/geodata/seoul_boundary.gpkg \
  --boundary-filter-column= \
  --boundary-filter-value= \
  --output-dir=/members/dhnyu/fusedatalarge/working_data/seoul \
  --region=seoul \
  --target-crs=5186 \
  --cell-size-m=500 \
  --strides-m=500,250
```

For boundaries that contain multiple regions, provide `--boundary-filter-column` and `--boundary-filter-value` so the generated grid covers only the intended study area.
