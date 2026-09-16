# Supplemental S10 retrieval viewer

The current entrypoint is `build_bands.py`. It publishes **separate supplemental
band evidence**, then an artifact-only viewer. It never executes formal S10,
loads checkpoints, runs inference/Fourier features, or preprocesses original data.
The parent remains `s10_acceptance_5471f74031f267c4253df231`.

## Full-order bands

Band positions and the five-column comparison DOM/strip come from the historical
retrieval inspector at `10c02e4`. Its source CSS is preserved as
`legacy_retrieval_10c02e4.css`; only comparison rules are copied into the output.
Live augmentation-inspector header/control styles and the existing detailed
summary renderer are retained.

The default columns are Query | Rank 1 / Most similar | Top band (10) |
Middle band (10) | Bottom band (10). Each band has the original 5×2 compact strip;
clicking a thumbnail replaces that column's vector/raster/attribute/detail scene.

For each model/query/mode, accepted normalized vectors are ordered over the full
9,000 evaluation gallery by cosine descending, scene ID ascending. Self is
excluded; non-local additionally requires geographic distance ≥2,000m. If the
eligible count is N:

- Rank 1: full eligible rank 1.
- Top: ranks 2–11.
- Middle: 10 ranks starting at `floor((N−10)/2)+1` (legacy definition).
- Bottom: ranks N−9 through N.

All formal Top50 rows must match exactly before publication. Only the 31 selected
rows per model/query/mode are published, with eligible count, actual full rank,
scene ID, cosine score and geographic distance. `band_evidence_receipt.json`
binds accepted embedding IDs, source hashes and band-selection implementation;
it does **not** replace formal acceptance. The browser cannot reconstruct ranks.

## Display sources and raster scaling

Existing scene JSONs from `viewer_f8d14a826a75bc8451f219c5` are reused unchanged.
New band scenes read the already persisted S10 original-input tensors and exact
SHA-bound P3 parent vector records. Previously clipped observed geometry is only
serialized to SVG using the existing renderer; no clipping, reprojection, input
tensorization, spatial join or scientific raster derivation is performed.

Every scene uses the same display path: LC 22×100×100 stored fractions become the
same fraction-blended 100×100 PNG as earlier; DEM uses the stored standardized
17×17 values. Previously generated PNG bytes are reused whenever present. No
new dominant-class assignment or normalization occurs. LC scene-comparison
canvases use device-pixel-sized backing stores with `imageSmoothingEnabled=false`;
DEM images use continuous browser display scaling. Scientific values are never
resampled or changed. Fraction-mixture colours already exist in the stored
display; nearest scaling does not remove those colours.

Detailed summaries are unchanged: actual stored SVG entities coloured by POI L1,
building use/structure, road rank, and raw LANES, plus the existing LC display and
legends. Unknown categories remain gray. Lane values come directly from the
accepted parent payload, verified against ordered road entity IDs; they are not
recovered from standardized values. All models show common original scene
context, including modalities a selected model may not consume.

## Publish and inspect

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python tools/retrieval_inspector/supplemental/build_bands.py \
  --generation /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/s10gen_a24b979d4c1557387cbbec35 \
  --output-root /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers
python -m http.server 8765 --bind 127.0.0.1 --directory /path/printed/by/publisher
```

Open `http://localhost:8765`. Localhost/HTTPS is required for browser checksum
verification; file:// is unsupported. Missing/corrupt artifacts fail closed.
`--smoke` publishes a noncanonical one-query/main preview, using the same complete
eligible ordering. Existing directories are never overwritten. Only a complete
`viewer_receipt.json` marks a finished publication; interrupted outputs must not
be served. Scientific and previous supplemental generations are immutable.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python scripts/validate_s10_bands_viewer.py \
  --viewer /path/printed/by/publisher --generation /path/to/accepted/generation \
  --audit-output /tmp/s10-bands-validation.json
pytest -q tests/python/test_s10_retrieval_bands.py
```

The earlier `build.py` and its tests remain available for reproducing prior
six-column display contracts; new band views use `build_bands.py`. Neither invokes
the targets graph. No target store or network change is required.

## Scene-center locations (metadata-only publication)

For the accepted legacy-band viewer `viewer_f33db05a1507064733ee8702`, use the
separate location publisher. **Do not rerun `build_bands.py` to add locations**:
that older publisher reconstructs bands from embedding arrays. The location
publisher has no model/scientific imports and consumes existing band bytes only.

```sh
python tools/retrieval_inspector/supplemental/build_locations.py
python scripts/validate_s10_locations_viewer.py \
  --viewer /path/printed/by/location/publisher \
  --audit-root /mnt/hdd002/dhnyu/fusedata/tmp/fuse/location-browser-audit
python -m pytest -q tests/python/test_s10_viewer_locations.py
```

`config/s10_viewer_locations.json` pins the parent acceptance, viewer receipt,
band receipt, accepted gallery, and all five shapefile components for each of the
2025-06-30 district and administrative-dong sources. Existing pins must not be
silently refreshed when a source changes. Source checksum mismatch fails closed.

The R `sf` helper reads the accepted gallery's full-precision EPSG:5186 easting /
northing centers, transforms once to OGC:CRS84 longitude/latitude and EPSG:5179,
and uses `st_covered_by` against the boundaries. PROJ network access is disabled.
Zero matches and shared-boundary matches have explicit unavailable/ambiguous
metadata, with all candidate names/codes retained and no nearest fallback.
Hierarchy mismatch fails. This Seoul publication requires 9,000 unique matches
at both levels before publishing; exceptions are not filled automatically.

`location_metadata.json` contains one row keyed by each of the 9,000 gallery
scene IDs, independently of model/query/mode. `ADM_NM` is preserved as an
administrative-dong name, e.g. 독산1동, never converted to a legal-dong name or
street address. Geographic coordinates remain full precision in the sidecar;
only browser text rounds them to five decimals. Every visible column has the
same location slot before Vector data, updated from its selected scene ID.

The publisher verifies every parent display-file checksum, copies assets as
unchanged bytes (not writable hard links), and writes a **new** immutable viewer
directory. Parent scenes, band query JSON, SVG and embedded raster bytes remain
identical. A new supplemental receipt binds the location sidecar, source/library
versions, code and output hashes; it is not a new S10 scientific acceptance.
The receipt is written last. Never serve incomplete directories without it.
An existing identical generation is validated/reused; differing bytes fail.

The location validator starts its own localhost HTTP server and Chromium. It
checks immutable byte reuse, gallery-center bindings, query/model/mode switches,
all three bands, the five documented examples, status rendering, layout,
rasters/thematic panels and controls. It does not load checkpoint/tensor payloads
or compute ranks. Browser screenshots and validation JSON belong outside Git.
