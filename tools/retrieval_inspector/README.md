# P10 Retrieval Inspector

This read-only tool turns accepted P10 qualitative retrieval evidence into a local interactive comparison. It never loads a checkpoint, runs an encoder, changes a ranking metric, or creates scientific evidence. It is a qualitative inspection aid, not a quantitative ground-truth metric or a model-selection interface.

## Inputs

- P10 acceptance `p10acc_6e5071beee7616750dec7907`
- P10 execution attempt `p10exec_7fee193dac532190c79e02c6`
- qualitative query contract `p10qq_dd7d0775f5809a793575342b`
- the eight accepted P10 model results and their stored original-gallery embeddings
- accepted P3 original evaluation scenes and the accepted district assignment

The generator validates identities, hashes, populations, and the committed P10 qualitative samples before reconstructing complete rankings. It uses cosine similarity exactly as P10 did; larger values are more similar. No embedding inference occurs.

## Generate

From the repository root:

```bash
python tools/render_retrieval_inspector.py
```

The command prints the generated `artifacts/retrieval-inspector/<identity>/index.html` path. Open that file directly in a browser. No server or network connection is required. Scene assets are loaded lazily through relative paths, so Chromium-based browsers should be launched with local-file access enabled if their local security policy blocks sibling files.

Validate an existing output without reading or changing scientific artifacts:

```bash
python tools/render_retrieval_inspector.py --validate artifacts/retrieval-inspector/<identity>
```

## Interface

The model selector covers `cfg_d128`, A1-A5, SSV, and DS. The query selector covers all ten frozen P10 scenes and shows district and EPSG:5186 center coordinates. Previous/next buttons retain the query, retrieval setting, and selected band positions. State is stored in the URL hash.

`Standard` uses all other gallery scenes: 1,599 canonical or 9,999 expanded candidates. `Non-local >= 2 km` removes candidates with center distance below 2,000 m and shows the actual query-specific count. Both modes exclude the query itself and use only original, unaugmented scene embeddings.

The five columns are the query, rank 1, ranks 2-11, ten contiguous ranks around the ranking midpoint, and the final ten ranks. For a ranking of length `N`, the middle band starts at one-based rank `floor((N - 10) / 2) + 1`. Thumbnail rank buttons select the detail shown in each band column.

Every vector map is north-up with a fixed 500 m x 500 m extent and common building, road, and POI styling. Layer checkboxes apply to all columns. LC uses one fixed 22-class palette. DEM uses one shared minimum/maximum over the five currently compared scenes. Attribute panels summarize buildings, roads, POIs, land cover, DEM, and SN/CNT/WIT/INT/CON relations from the matching accepted P3 scene.

## Limitations

Visual resemblance is interpretive and is not a labelled relevance judgment. Rank bands are a deterministic inspection view, not additional P10 metrics. The inspector must not be used to reopen checkpoint or model selection. P10's dissertation figure protocol used representative rank positions; this inspector adds non-authoritative top/middle/bottom bands for systematic human browsing while preserving the same queries, gallery, embeddings, similarity, and geographic filter.
## Supplementary Gallery Integration

The optional `galleries` manifest field enables explicit `Canonical 1,600` and
`Expanded 10,000` modes. Older canonical-only manifests remain supported.
Both modes retain the accepted ten queries, eight models, two retrieval settings,
and existing band definitions. Supplemental middle/bottom bands use their actual
candidate counts, not the canonical indices.

Supplemental assets resolve through an explicit union catalog. Their geographic
metadata is optional and does not require P11; unavailable district information
is labeled as such. Canonical metadata keeps its existing accepted source.
Only required band scenes are rendered, once per scene/render contract, and the
browser loads assets lazily. No new held-out metrics or downstream results are
defined by this mode.

The accepted supplemental science was produced by `_targets_retrieval_gallery.R`.
Do not rerun that frozen production pipeline to update the inspector. Presentation
updates neither execute targets nor recompute rankings or scene assets.

Once a supplementary acceptance is published and registered in
`supplemental_output.json`, validate its binding and locate the dual-gallery HTML:

```bash
python tools/render_retrieval_inspector.py --supplemental
```

This command does not generate scenes, embeddings, or rankings. The default
command and `example_output.json` retain their canonical-only behavior.

## Expanded Gallery Presentation

The primary HTML is:

```text
/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/retrag_29e75a5e81df82e0c3d93783/inspector/index.html
```

The prominent gallery selector and previous/next gallery buttons switch between
the two candidate universes without resetting model, query, Standard/Non-local,
LC/DEM, vector layers, or the selected position within each rank band. Previous/
next model and query controls use the same state-preserving behavior. FM is
explicitly labeled `FM / cfg_d128`; the other seven accepted models are unchanged.

The header shows active gallery, total gallery size, candidate count, model,
full query ID, district, projected coordinates, retrieval setting and similarity
direction. Candidate headings show exact rank, similarity, geographic distance,
scene ID and a Canonical/Supplemental source label. Thumbnail tooltips contain
the same evidence. Non-local candidates are explicitly marked as at least 2 km.
The five scene columns and fixed 500 m map frames are retained. Narrow screens
scroll horizontally rather than shrinking the maps into unreadability.

The compact `1,600 vs 10,000` panel is bound to the accepted
`rankings/stability_diagnostics.json`. It shows the old rank-1 ID/similarity and
its expanded rank, the expanded rank-1 ID/source/similarity/distance, top-10 and
top-100 overlap, and the expanded rank-1 minus rank-10 similarity gap. Values
are read from accepted diagnostics and canonical evidence, not recomputed in
JavaScript. There is no aggregate model score.

URL hashes preserve `gallery`, `model`, `query`, `setting`, `top`, `middle`,
`bottom`, `layers` (B/R/P, including an empty selection), and `raster`. Band
selections are zero-based positions within their active ten-candidate band;
gallery switching retains the position, not a candidate that may be absent from
the new band. Reload and hash navigation restore controls as well as content.

The interpretation disclosure states the boundary: 10K is supplementary
retrieval-only evidence, canonical P10 and P11 remain unchanged, and gallery
expansion changes available candidates. Lower overlap does not mean old
retrieval was incorrect; new candidates can outrank old ones simply because
the candidate universe is larger. No inspector state establishes model superiority.

## Update the Presentation Only

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  python tools/render_retrieval_inspector.py --refresh-supplemental
```

This checks the acceptance and parent hashes, both galleries, all 160 expanded
query/model/setting combinations against stored ranking Parquets, authoritative
diagnostics, and all required asset hashes. It then prepares a content-addressed
`presentations/retrview_*/` revision and validates 320 desktop states plus mobile
states, lazy assets, gallery transitions, and URL restoration in Chromium.
Publication fails closed without complete browser validation.

Only the explicitly mutable `index.html` entry and `presentation.json` pointer
are replaced. The previous entry is retained byte-for-byte in
`presentation_history/<sha256>/index.html`. The accepted `manifest.json`,
`manifest.js`, original `app.js`/`style.css`, all 3,622 scene assets, ranking files,
and `retr10k_0672df44ea0fb5adceafbec9` acceptance are never rewritten. The new entry
references versioned presentation scripts/styles while still using the original
manifest and lazy scene assets. This is a render revision, not a replacement
scientific acceptance or a second ranking output.
