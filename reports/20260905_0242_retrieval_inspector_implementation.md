# Retrieval Inspector Implementation

## Verdict

`RETRIEVAL_INSPECTOR_IMPLEMENTATION_PASS_PUSHED`

The work implemented a read-only qualitative inspection layer over accepted P10 retrieval evidence. It did not create or alter scientific results.

## Purpose And Scope

- Inspect whether high-, middle-, and low-ranked scenes are visually and structurally plausible.
- Compare standard retrieval with the fixed 2 km non-local exclusion.
- Compare the same fixed query and rank-band state across the eight accepted models.
- Show vector, raster, attribute, and relation evidence together under controlled visual scales.

Prompt scope was limited to visualization. P9 selection, P10 acceptance, P11 evidence, and dissertation methodology were not changed.

## Authoritative Inputs

| Evidence | Identity |
|---|---|
| P10 acceptance | `p10acc_6e5071beee7616750dec7907` |
| P10 execution attempt | `p10exec_7fee193dac532190c79e02c6` |
| qualitative query contract | `p10qq_dd7d0775f5809a793575342b` |
| final full-model acceptance | `p9accv2_a1c00e32a882ddc4b7e2677b` |
| P3 original scene cache | `oscache_c89fa07e3d6cb1819a7994a6` |
| model population | `cfg_d128`, A1, A2, A3, A4, A5, SSV, DS |

The P10 acceptance file SHA-256 was `f43a7206be6814c35e517017b438a977561c5113be855bff8d884c3d4a52e8c0`. The cfg_d128 acceptance and commit-manifest SHA-256 values remained `91487744ad922af2b9721f6ec4f8439cc14e50ba7cbe6d1b4c70d272f3f52b97` and `55eecfecf1e54079494222589acb78185cf07c3794dad5d490925b7694975b66`.

## Retrieval Contract

- Fixed qualitative queries: 10/10, read back from P10.
- Gallery: 1,600 accepted original, unaugmented evaluation scenes.
- Standard candidates: exactly 1,599 per query after self-exclusion.
- Non-local candidates: 1,564-1,573 per query after excluding center distances below 2,000 m.
- Similarity: P10 cosine similarity; larger means more similar.
- Ordering: descending similarity, then scene ID as the deterministic tie-break.
- Bands: rank 1; ranks 2-11; ten contiguous ranks beginning at `floor((N-10)/2)+1`; final ten ranks.

The reconstructed rankings reproduced each committed P10 qualitative rank sample exactly. All 160 model/query/setting combinations passed candidate, self-exclusion, rank, distance, and deterministic-band checks.

## Implementation

- Generator: `tools/render_retrieval_inspector.py`
- Library and browser assets: `tools/retrieval_inspector/`
- Documentation: `tools/retrieval_inspector/README.md`
- Local example pointer: `tools/retrieval_inspector/example_output.json`
- Generated inspector: `artifacts/retrieval-inspector/retrieval_inspector_c612a074a9211c222eb9a811/index.html`

The generated artifact has 1,342 content-verified scene assets and is 506,216,671 bytes. It uses a compact ranking manifest and lazy per-scene JavaScript assets, so the browser loads only the current query and 30 band thumbnails/details. The output is local-file compatible and has no external network dependency or absolute source-data path.

## UI And Rendering

- Model and fixed-query selectors, previous/next model controls, and standard/non-local segmented controls preserve comparison state in the URL hash.
- Five columns show the query, rank 1, top ten, middle ten, and bottom ten.
- Each ten-scene band has clickable vector mini-map thumbnails and one synchronized detail view.
- Building, road, and POI layers share a fixed style and a north-up 500 m x 500 m EPSG:5186 frame.
- LC uses one fixed 22-class categorical palette with class-code legend; DEM uses one scale shared across the current five columns.
- Scene summaries include counts/areas/lengths, POI and land-cover composition, DEM range, and SN/CNT/WIT/INT/CON counts. Expandable summaries expose category breakdowns.
- Scene ID, district, center coordinates, similarity, rank, and query distance remain visible and scene IDs can be copied.

## Validation

| Check | Result |
|---|---|
| inspector/P10 focused Python tests | 23 passed |
| augmentation/P3/P10 regression tests | 35 passed |
| manifest conditions | 160/160 passed |
| scene asset checksum/readback | 1,342/1,342 passed |
| deterministic create-or-validate rerun | PASS; manifest bytes and mtime unchanged |
| headless Chrome smoke | PASS; 5 columns, 30 thumbnails |
| model/query/setting/band interaction | PASS |
| JavaScript console errors | 0 |
| missing browser assets | 0 |
| JSON/YAML parse | PASS |
| JavaScript syntax | PASS |
| `targets::tar_validate()` | PASS; no target execution |
| `git diff --check` | PASS |

The latest dissertation `reduced` authority was read at `989c19d98e64ec129dc53b761c58a4d961fc3983`. Its Spatial Scene Retrieval section agrees with the fixed-query, evaluation-gallery, self-exclusion, original-embedding, and 2 km non-local contracts. The inspector's additional ten-item rank bands are explicitly non-authoritative browsing views; they do not replace the dissertation's representative-position protocol.

## Prohibited Work

| Activity | Count |
|---|---:|
| Training | 0 |
| Fine-tuning | 0 |
| New embedding inference | 0 |
| P9 rerun | 0 |
| P10 scientific rerun | 0 |
| P11 downstream rerun | 0 |
| Checkpoint reselection | 0 |
| Model reselection | 0 |
| Dissertation mutation | 0 |

## Remaining Notes

The inspector is qualitative evidence review, not labelled retrieval relevance or a quantitative metric. The generated 506 MB directory is intentionally ignored by Git because it contains derived scene render assets; the deterministic example pointer and generator are versioned.

## Exact Next Work Unit

`RETRIEVAL_QUALITATIVE_ANALYSIS_AND_DISSERTATION_WRITEUP`
