# P4 Augmentation Inspector

This standalone utility provides human visual QC for accepted P3 original scenes and P4 fixed augmentation banks. It is deliberately outside the scientific `targets` graph: it reads immutable artifacts, embeds only requested scene/view cases, and never regenerates augmentation data. Visual inspection supplements, but does not replace, P4 scientific acceptance.

## Requirements

- Accepted P3 cache `oscache_c89fa07e3d6cb1819a7994a6`
- Accepted P4 bank `augbank_a470cb156612cff12fb316fc`
- Logical index `abi_f9ff792612ca86f486576491`
- Python packages already used by the pipeline: `numpy`, `pyarrow`, `shapely`, `PyYAML`, and `zarr`

The default artifact root is resolved from `config/p4_deterministic_augmentation.yml`. Set `FUSE_REDUCED_SCENE_ROOT` or use the explicit root options for a compatible mirror. The generated HTML never includes those filesystem paths.

## Usage

Render one accepted training scene and master view:

```bash
python tools/render_augmentation_inspector.py \
  --scene-id scn_000c176a31e77df2d447faa2 \
  --master-view-id 0 \
  --output artifacts/augmentation-inspector/scene_example_view_0.html
```

Render the deterministic QC preset:

```bash
python tools/render_augmentation_inspector.py \
  --preset qc-extremes \
  --max-cases 8 \
  --output artifacts/augmentation-inspector/p4-augmentation-inspector.html
```

Existing output is protected. Add `--overwrite` only when intentionally replacing a generated inspector. Validate an existing file without reading artifacts:

```bash
python tools/render_augmentation_inspector.py \
  --validate-only \
  --output artifacts/augmentation-inspector/p4-augmentation-inspector.html
```

Open the resulting file directly in a browser using `file://`; no local server or network connection is required.

## Interface

The four columns compare the original scene with weak (`0.5x`), main (`1.0x`), and strong (`2.0x`) candidates for one scene and master-view identity.

**Vector transformation** uses a fixed EPSG:5186 500 m extent. Building, road, and POI layers can be toggled. Zoom and pan are synchronized across columns. Removed entities remain as red dashed ghosts; absorbed road donors are purple; receivers are teal; perturbed geometry is orange; fallbacks use a black dashed outline. Hover shows entity identity and geometry statistics. Clicking an entity filters the attribute table.

**Raster transformation** switches between land cover and DEM. Actual land-cover classes use one shared palette; masked cells use a fixed dark hatch. Land-cover difference is categorical changed/unchanged/masked, never arithmetic. DEM actual values share one scale, while differences use one symmetric scale. Native 100 x 100 and 17 x 17 grids are embedded without resampling or smoothing.

**Attribute transformation** provides profile summaries and a searchable, sortable, paginated table. `null`, masked values, and recorded strings remain distinct. Filters cover profile, entity type, operation, and changed-only rows.

The provenance drawer records artifact IDs, candidate IDs, branch and candidate-slice checksums, K8 membership, fallback counts, absorption counts, relation summaries, and validation status. `Not recorded` means the scientific payload contains no such field; the inspector does not infer it.

Geometry fallback means all ten deterministic entity-level perturbation attempts failed and P4 retained that entity's original geometry. Road donor/receiver styling follows the accepted receiver-group absorption provenance; the original P3 topology is never edited.

## QC preset

`qc-extremes` streams only the compact `candidates.parquet` member from each accepted branch. It deterministically ranks scene/view pairs by fallback, absorption, direct and cascade removal, geometry and attribute perturbation, land-cover activity, median activity, and low-activity control behavior. Ties use scene ID and then master-view ID. Each selected pair loads the same original, weak, main, and strong identities.

## Troubleshooting

- An unknown or validation/evaluation scene is rejected because P4 contains training banks only.
- View IDs must be in `0..15`.
- Artifact ID, population, branch coverage, and selected shard checksums must match accepted manifests.
- Use `--overwrite` for an existing output. Publication is still atomic through a sibling temporary file.
- A checksum error indicates artifact mutation or the wrong immutable root. Do not bypass it or regenerate augmentation through this tool.
