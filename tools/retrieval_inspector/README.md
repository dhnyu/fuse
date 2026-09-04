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

`Local included` is standard retrieval over the other 1,599 evaluation originals. `Local excluded` removes candidates with center distance below 2,000 m. Both modes exclude the query itself and use only original, unaugmented evaluation-scene embeddings.

The five columns are the query, rank 1, ranks 2-11, ten contiguous ranks around the ranking midpoint, and the final ten ranks. For a ranking of length `N`, the middle band starts at one-based rank `floor((N - 10) / 2) + 1`. Thumbnail rank buttons select the detail shown in each band column.

Every vector map is north-up with a fixed 500 m x 500 m extent and common building, road, and POI styling. Layer checkboxes apply to all columns. LC uses one fixed 22-class palette. DEM uses one shared minimum/maximum over the five currently compared scenes. Attribute panels summarize buildings, roads, POIs, land cover, DEM, and SN/CNT/WIT/INT/CON relations from the matching accepted P3 scene.

## Limitations

Visual resemblance is interpretive and is not a labelled relevance judgment. Rank bands are a deterministic inspection view, not additional P10 metrics. The inspector must not be used to reopen checkpoint or model selection. P10's dissertation figure protocol used representative rank positions; this inspector adds non-authoritative top/middle/bottom bands for systematic human browsing while preserving the same queries, gallery, embeddings, similarity, and geographic filter.
