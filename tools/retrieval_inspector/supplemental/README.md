# Supplemental S10 inspector

This viewer uses the live `tools/augmentation_inspector/inspector.py` CSS verbatim.
Its header/brand/controls, metadata strip, section/grid/panel DOM, input dimensions,
spacing, sticky header and responsive breakpoints are reused. The profile grid
is extended from four to six aligned columns: Query and published Rank 1–5.
There is no hero, thumbnail card strip, bar-chart wall or two-column focus view.

Sections repeat the same six scene columns: VECTOR DATA, RASTER DATA,
ATTRIBUTES & SPATIAL RELATIONS, DETAILED SUMMARIES. Linked wheel/drag vector zoom,
Reset zoom and Provenance follow the original inspector interactions. Detailed
summaries expand/collapse inside each scene column. Their maps remain fixed at
500 m, north up, independent of vector zoom.

The display publisher never executes the scientific pipeline. It reads accepted
rankings/SVGs and persisted S10 original-input tensors, following acceptance →
ranking → embedding manifest → original-input manifest. No checkpoint payloads
are loaded. The prior supplemental generation remains immutable:
`viewer_404735cf7d702a5704f0b8f1`.
Its existing LC/DEM images, fractions/legends and SVGs are reused exactly, with
checksum and source-manifest binding checks; no raster colour computation is run.

Thematic maps colour **actual existing SVG objects** using stored per-entity
indices: POI L1, building use, building structure, road rank and road lane. No inferred
categories, spatial joins, geometric matching, reprojection or clipping occur.
The accepted renderer emits one SVG child per original entity in ascending
local-entity-ID order, the exact order preserved by the accepted input tensor.
The publisher verifies same P3 payload hash, accepted ordering implementation
hashes, scene ID, entity count/order, row indices and SVG entity-type colours.
The browser clones these SVG elements, preserves all geometric attributes and
transforms, and changes paint only. Unknown/masked categories use neutral gray;
all category counts are shown in scrollable legends. Road lines retain their
existing widths. One thematic map per row keeps maps readable in six columns.

Road lanes come from the **raw LANES field in the exact accepted P3 parent
payload**, not from `road_numerical` (which contains standardized values).
The accepted S10 model manifest pins the scene-to-shard index. The publisher
verifies index and tar SHA256, parent identity and the exact ordered road entity
IDs before using raw stored values. It reads only the existing road parquet
member: no GIS source, spatial/nearest join, new attribute matching, inverse
normalization, rounding, imputation or inference. Missing values are gray; line
widths remain unchanged. Finite stored values, including zero or fractional
values if present, are displayed as recorded. Colour tones progress through
1/2/3/4+ lanes, while legends retain each distinct raw value and count.

All models show common original scene context, even modalities a selected model
does not consume. LC is the previously published fraction-blended display, not a
new dominant-class map. DEM displays stored standardized values, not metres.
No ranking, scores, distances, checkpoints, query/gallery or acceptance changes.

```sh
python tools/retrieval_inspector/supplemental/build.py \
  --generation /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/s10gen_a24b979d4c1557387cbbec35 \
  --output-root /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers
python -m http.server 8765 --bind 127.0.0.1 --directory /path/printed/by/publisher
```

Open `http://localhost:8765`. Serve through localhost or HTTPS for Web Crypto
checksum validation; direct file:// is unsupported. Missing/corrupt display JSON
fails closed. `--smoke-query-count 1` or 2 provides bounded previews at a separate
output root. Existing directories are never overwritten. Only a complete output
with `viewer_receipt.json` is publishable; an interrupted output must not be served.

The receipt binds display code (including live augmentation source), parent S10
acceptance, prior supplemental receipt, source manifests, exact parent payload hashes and output checksums.
It is a UI receipt, never a scientific acceptance. Existing target graph/runtime
sources are unchanged; no target make or network regeneration is needed.

```sh
python scripts/validate_s10_supplemental_viewer.py \
  --viewer /path/printed/by/publisher --generation /path/to/accepted/generation
pytest -q tests/python/test_s10_supplemental_viewer.py tests/python/test_s10_thematic_viewer.py
```
