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
## Supplementary Gallery Integration

The optional `galleries` manifest field enables explicit `Canonical 1,600` and
`Supplemental 10,000` modes. Older canonical-only manifests remain supported.
Both modes retain the accepted ten queries, eight models, two retrieval settings,
and existing band definitions. Supplemental middle/bottom bands use their actual
candidate counts, not the canonical indices.

Supplemental assets resolve through an explicit union catalog. Their geographic
metadata is optional and does not require P11; unavailable district information
is labeled as such. Canonical metadata keeps its existing accepted source.
Only required band scenes are rendered, once per scene/render contract, and the
browser loads assets lazily. No new held-out metrics or downstream results are
defined by this mode.

The production entry point is `_targets_retrieval_gallery.R`, using the isolated
`/mnt/hdd002/dhnyu/fusedata/targets/retrieval-gallery` store. It is unavailable until
all three complete pilot records and the reviewed throughput/parity evidence are
provided. It must never be run against the canonical targets store.

Once a supplementary acceptance is published and registered in
`supplemental_output.json`, validate its binding and locate the dual-gallery HTML:

```bash
python tools/render_retrieval_inspector.py --supplemental
```

This command does not generate scenes, embeddings, or rankings. The default
command and `example_output.json` retain their canonical-only behavior.
