# Supplemental S10 inspector

Focused Query + published Rank 1–5 inspector, using the augmentation inspector's
control strip, panel grid, tokens and raster palette. All 28 models and both modes
remain selectable for each of the 30 fixed queries.

This additive publisher leaves the original viewer, target graph, runtime source
closure, accepted pages and scientific acceptance unchanged. It only consumes
accepted rankings, existing vector SVGs, and persisted S10 original-input tensors.
No checkpoints, inference, geometry features, ranking or geographic filtering are
executed. Loading a tensor with `torch.load(..., weights_only=True)` reads a stored
scene input, never a checkpoint.

The accepted ranking → embedding manifest → prepared manifest chain binds the
scene tensors. The category dictionary is checked against the accepted model
manifest's source pin and prepared manifest. Every consumed manifest/payload is
checksum-verified. The browser also verifies JSON payload hashes and clears the
view on missing/corrupt payloads. Serve on localhost (or HTTPS) for Web Crypto.

```sh
python tools/retrieval_inspector/supplemental/build.py \
  --generation /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/s10gen_a24b979d4c1557387cbbec35 \
  --output-root /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers
python -m http.server 8765 --bind 127.0.0.1 --directory /path/printed/by/publisher
```

Open `http://localhost:8765`. The 30 query pages retain model/mode selection when
navigating. Group selectors offer OFAT / COMPARISON / All; scene buttons enlarge
any of the five candidates alongside the query. Building/Road/POI visibility acts
on existing SVG layer colours; LC/DEM toggles control stored-raster display panels.

`--smoke-query-count 1` (or 2) publishes a bounded noncanonical UI preview to a
separate output root. Existing output directories are never overwritten. Only a
complete publication receives `viewer_receipt.json`; an interrupted directory is
not a published viewer and must not be served. Scientific source paths are never
publication destinations.

Display semantics:

- Shared original scene context is shown even for models that omit a modality.
- POI L1, building use/structure and road rank counts decode stored indices using
  accepted vocabulary ordering; missing values are explicit. Charts show the top
  five categories plus Other and retain Unknown separately.
- Land cover uses the stored 22 class-fraction channels. Pixel colours are a
  fraction-weighted blend of the augmentation inspector palette, without a new
  class assignment. Composition percentages use stored valid-support weights.
- DEM displays stored standardized means, **not elevation metres**. A fixed
  −3 to +3 colour scale clips colours only. No raster derivation, resampling,
  interpolation, extraction or normalization is run.
- Relations show existing ordered-edge counts and stored bit-mask counts, without
  computing spatial relations. Summaries are display aggregations, not new metrics.

The display-code identity, parent acceptance checksum, consumed source manifest
checksums and all output file checksums are recorded in `viewer_receipt.json`.
This is a supplemental UI receipt, never a replacement scientific acceptance.

Validation:

```sh
python scripts/validate_s10_supplemental_viewer.py \
  --viewer /path/printed/by/publisher --generation /path/to/accepted/generation
pytest -q tests/python/test_s10_supplemental_viewer.py
```
