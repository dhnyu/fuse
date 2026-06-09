# Repository Structure Refactor

## What Changed

Executable workflow scripts were reorganized from a flat `scripts/` directory into stage-oriented subdirectories:

- `scripts/grid/` for grid preprocessing.
- `scripts/POI/` for OSM point-of-interest extraction.
- `scripts/geometry/` as a placeholder for future geometry embedding workflows.
- `scripts/streetview/` for the numbered production road and Street View pipeline.
- `scripts/visualization/` for optional diagnostic maps.
- `scripts/validation/` for lightweight independent checks.

Reusable helper layers were not moved:

- `R/`
- `src/`

## Why This Is Better

The new structure separates executable workflow stages from reusable implementation code. This makes onboarding easier because collaborators can identify which scripts are production entrypoints, which scripts are optional diagnostics, and which files are reusable libraries.

The layout also reduces ambiguity for automated agents: numbered scripts communicate execution order, while unnumbered utility scripts signal that they are independently callable.

## Execution Order Philosophy

Numbered scripts represent stage order within a workflow:

- `10_`: early preprocessing or baseline sampling.
- `20_`: downstream candidate generation.
- `30_`: metadata validation and filtering.
- `40_`: image materialization.
- `50_`: final manifest construction.
- `60_`: final validation.

Visualization and validation scripts are intentionally unnumbered. Visualization is optional and diagnostic-oriented. Validation utilities are cheap, independent checks that can be run before or after any stage.

## Directory Responsibilities

`scripts/grid/` builds spatial grid products used by later sampling and visualization.

`scripts/POI/` prepares semantic OSM point-of-interest products.

`scripts/geometry/` is reserved for future polygon, multipolygon, and geometry embedding workflows, including possible GeoNeuralRepresentation integration.

`scripts/streetview/` contains the core road-constrained and Street View production pipeline.

`scripts/visualization/` renders optional Leaflet diagnostics and final coverage maps.

`scripts/validation/` checks path configuration, write permissions, expected files, and final dataset invariants without launching expensive acquisition work.

## Remaining Architectural Limitations

The production Street View workflow is resumable through parquet checkpoints and manifests, but it is not yet backed by a transactional task database. This is acceptable for single-operator runs but may need stronger locking for concurrent production operators.

Legacy prototype scripts remain in `tests/` for small development checks. They are not the final production acquisition pathway.

Some generated logs and historical manifests may still reference older local paths from earlier repository layouts. New documentation and command examples use the reorganized stage hierarchy.

## Future Extensibility

The staged hierarchy leaves room for additional workflows without flattening the repository again. Likely future additions include:

- geometry embedding scripts under `scripts/geometry/`,
- road-bearing and road-relative crop heading generation under `scripts/streetview/`,
- image-quality diagnostics under `scripts/validation/` or `scripts/visualization/`,
- multimodal feature extraction stages after final Street View materialization.

The guiding rule is to keep executable orchestration in `scripts/` and reusable logic in `R/` or `src/`.
