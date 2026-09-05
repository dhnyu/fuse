# Retrieval Inspector 10K Update

## Verdict and Scope

**RETRIEVAL_INSPECTOR_10K_UPDATE_PASS**

Created: 20260906_0107, Asia/Seoul. Commit/push and remote synchronization follow the
completed validation gates; the final commit SHA and push result are recorded
in the completion message.

Prompt summary: make the accepted 10K gallery a first-class inspector mode,
retain the same query/model/setting/display state during gallery comparison,
integrate authoritative stability diagnostics, preserve scientific results,
validate desktop/mobile behavior, report, and commit/push Fuse reduced.

- Starting Fuse commit: f0f89ab0bffad6ff11c1350ba04885176a39d882.
- Branch: reduced; starting tree clean.
- Supplemental authority: retrag_29e75a5e81df82e0c3d93783.
- Supplemental acceptance: retr10k_0672df44ea0fb5adceafbec9.
- P10 acceptance: p10acc_6e5071beee7616750dec7907, unchanged.
- Fixed query contract: p10qq_dd7d0775f5809a793575342b, unchanged.
- Dissertation HEAD: 989c19d98e64ec129dc53b761c58a4d961fc3983; unchanged and clean.
- Scope: presentation and inspection only; no scientific production execution.

The latest dissertation retrieval section and targets blueprint were read.
The dissertation's representative-rank figure protocol differs from the
inspector's already accepted browsing bands. This task preserves the explicitly
requested inspector bands; it does not change the dissertation protocol.

## Output and Versioning

[Open the updated inspector](/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/retrag_29e75a5e81df82e0c3d93783/inspector/index.html).

The output directory is abbreviated INSPECTOR below:

/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/retrag_29e75a5e81df82e0c3d93783/inspector

- Presentation revision: **retrview_2e9f2e402e11da23bc0acdcd**.
- Revision directory: INSPECTOR/presentations/retrview_2e9f2e402e11da23bc0acdcd.
- Revision manifest SHA-256: 4606c60f59af1cb2b46fe827e45855317dae08cd8c6cf13dc1cdc6892458f181.
- New entry SHA-256: f74a6cacc0f72c59101c1dea7ce9eaf9843a63ced5568ef18453af1418099df2.
- Browser receipt SHA-256: c9bc1fd537454e9938bc1c1c08b27f71757048bda4bfa9a5367590adf7e8f91b.
- Accepted inspector manifest SHA-256 remains b6a9ab5daa689a94a9680854087720de450b3d79a54f1336c5cf836ba2eaaf1a.

The original inspector manifest is bound by the supplementary scientific
acceptance. It was not rewritten or relabeled as a new acceptance.
Versioned presentation scripts/styles and a hash-bound display copy of accepted
diagnostics are referenced by the requested index.html entry.
A new presentation.json pointer identifies the render revision.

The previous entry was preserved byte-identically at:

INSPECTOR/presentation_history/97bdfc00e5fc571fb4f4bcbbdc6bb8ed195e682378faa3576452d05107de5f73/index.html

Original manifest.json, manifest.js, app.js, style.css, all scene assets, all
ranking files, and all scientific acceptances remain unchanged. Only the
explicitly requested existing index.html entry changed. New presentation files
are not a second ranking output.

## Interface Changes

- Prominent Canonical 1,600 / Expanded 10,000 selector with previous/next controls.
- Previous/next model and query controls; exactly the accepted eight models and
  ten fixed queries. FM is explicitly labeled FM / cfg_d128.
- Gallery switching retains model, query, Standard/Non-local, B/R/P selections,
  LC/DEM, and selected positions within the top/middle/bottom bands.
- Header shows active gallery, total gallery size, actual candidate count,
  model, full query scene ID, query number/district, X/Y, retrieval setting and
  similarity direction.
- Retrieved candidates show rank, five-decimal similarity, query distance,
  scene ID and Canonical/Supplemental source label. Thumbnail tooltips carry the
  same evidence; every thumbnail displays its exact rank.
- Non-local candidates are explicitly marked Distance >= 2 km.
- The five-column query/rank-1/top/middle/bottom structure is preserved.
- Scene-location summaries expose district or Unavailable and center X/Y.
  Supplemental metadata does not require P11.
- All existing building coverage/count, road count/length, POI/category, LC,
  DEM and SN/CNT/WIT/INT/CON summaries remain available.
- No optional extra image-comparison mode was added; the compact paired
  rank-1 evidence panel avoids crowding the five scene columns.

Vector drawing, geometry path handling, raster drawing, DEM color interpolation
and scene summary functions are byte-identical to the original implementation.
Maps remain north-up, fixed 500 m by 500 m, with the same symbol rules and frame
scale. LC retains the accepted palette; DEM retains a common scale over the
five currently compared scenes. There is no per-scene zoom or rescaling.

On mobile the controls and diagnostics fit the viewport; the five readable map
columns remain horizontally scrollable.

## Counts and Bands

| Mode | Gallery | Standard candidates | Non-local candidates |
|---|---:|---:|---|
| Canonical | 1,600 | 1,599 | Existing accepted query-specific counts |
| Expanded | 10,000 | 9,999 | Existing accepted query-specific counts, 9,781-9,873 |

Both modes retain exactly ten queries, eight models and two settings.
Each mode has **160 primary query/model/setting states**.

For candidate count N, the existing deterministic bands are retained:
rank 1; top ranks 2-11; central ten starting at floor((N-10)/2)+1;
bottom ranks N-9 through N. Non-local bands use the actual filtered N.
Gallery switches retain the selected zero-based band position, not a candidate
that may no longer occur in the new band's candidate universe.

## Authoritative Diagnostics

The compact 1,600 vs 10,000 panel reads the accepted:

/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/retrag_29e75a5e81df82e0c3d93783/rankings/stability_diagnostics.json

Diagnostic SHA-256:
549f01524941ecf6344b8051eb6eef7a4b539dba56b395aa019be3ea5fe09df7.

The binding is verified through the accepted ranking manifest and supplementary
acceptance. Each of the 160 diagnostic records is joined to the same accepted
canonical rank-1 evidence, without reranking.

Displayed fields: old rank-1 ID/similarity, its expanded rank, expanded rank-1
ID/source/similarity/distance, top-10 and top-100 overlap, and expanded rank-1
minus rank-10 similarity gap. Formatting percentages/decimals is presentation
only. No diagnostic or aggregate model score is recomputed in the browser.

The interpretation disclosure states that 10K is supplementary retrieval-only
evidence, P10/P11 remain unchanged, gallery expansion changes the candidate
universe, lower overlap does not imply incorrect old retrieval, and new
candidates can outrank old ones simply because the gallery is larger.
No model-superiority claim or scientific interpretation was added.

## URL and Loading Behavior

The hash encodes gallery, model, query, setting, top, middle, bottom, layers,
and raster. Reload and hashchange restore both internal state and visible
controls. Tests included nondefault band positions 3/6/9, DEM, a disabled road
layer, changed query/model, non-local retrieval, and an empty vector-layer set.

Gallery switching preserves all non-gallery state. Loading promises are
deduplicated per scene, and only active query/band assets are requested.
The direct primary-entry smoke test loaded **32 scene assets initially**,
not the 10,000-scene population. Across exhaustive browsing, the existing
**3,622 unique required assets** were used. No scene asset was regenerated.

## Validation Results

| Check | Result |
|---|---|
| Canonical ranking/model/query readback against accepted old inspector | PASS, 160 states |
| Expanded readback against accepted ranking Parquets | PASS, 160 states |
| Band item rank/ID/similarity/distance/source/asset checks | PASS, 9,920 entries across both modes |
| Standard counts, self-exclusion, source mapping, >= 2 km | PASS |
| Accepted diagnostic hash and rank-1/old-best-rank bindings | PASS, 160 records |
| Canonical scene assets | 1,342 unchanged |
| Total required scene assets | 3,622 unchanged, missing 0 |
| Browser desktop | PASS, 320 states at 1600 x 1100 |
| Browser mobile | PASS, 32 states at 390 x 844 |
| Gallery state transitions and URL/hash restoration | PASS |
| Shared DEM scale and canvas rendering | PASS |
| Console errors / page errors | 0 / 0 |
| Failed requests / broken links | 0 / 0 |
| Direct published entry and initial lazy loading | PASS, 32 scene requests |
| Empty vector-layer URL restoration | PASS |
| Python tests | 14 passed, final run 9.08 seconds |
| Python AST parse | PASS, 5 changed/new Python files |
| JavaScript node --check | PASS |
| JSON parse | PASS, accepted manifest and three presentation receipts/manifests |
| git diff --check | PASS |

Chromium version: 148.0.7778.96. The complete staged browser run observed
3,627 unique resource URLs, including scene assets and static resources.
The browser receipt is in the revision directory. Desktop canonical/expanded
and mobile screenshots are also there; expanded desktop/mobile images were
visually inspected after successful publication.

Tests run:

    PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=python:tools pytest -q tests/python/test_retrieval_inspector.py tests/python/test_retrieval_gallery_browser.py tests/python/test_retrieval_inspector_presentation.py tests/python/test_retrieval_gallery_ranking.py

Additional tests fail closed on immutable-file collisions, hash mismatch and
incomplete browser publication gates, and prohibit scientific-execution entry
points in the presentation module.

Two staged browser runs were rejected before entry publication: a file-URL
history/base-path interaction, corrected by using the current document URL for
hash updates; and an overly strict pixel test that rejected valid empty-vector
scenes. The corrected test verifies rendered alpha/dimensions, while exact
drawing-function regression guards the unchanged rendering semantics.
Neither failure changed accepted evidence or the old entry.

An initial preservation-check command incorrectly compared structured
hash/size records with strings. Correcting the checker to use the stored
sha256 and size fields produced the preservation result below; there was no
underlying scientific artifact mutation.

No R or target definitions changed. R pipeline execution, tar_make and dependency
network regeneration were not applicable and were not run. The frozen science
replay remains associated with f0f89ab; UI revision is not authorization to rerun
supplemental production. The unchanged dissertation figure methodology is not
rewritten by these inspection bands.

## Preservation Evidence

Snapshot before this task:
runtime/retrieval_gallery/inspector_update_before_20260906.json under
/mnt/hdd002/dhnyu/fusedata.

Final receipt:
runtime/retrieval_gallery/inspector_update_preservation_20260906.json.

Of **10,813 existing files checked**, **10,812 remain byte-identical**.
The sole changed existing file is the requested inspector/index.html entry,
whose previous bytes are archived under its exact SHA-256. This includes
preservation of the existing 7,134-file historical protection set.

Scene assets rewritten: 0. New scene assets: 0. Acceptance mutations: 0.
Canonical and supplemental ranking files, union embeddings, scene identities,
query contract and original inspector evidence all remain unchanged.
The dissertation remains clean at its starting commit.

## Prohibited-Work Counts

| Activity | Actual |
|---|---:|
| Training | 0 |
| Fine-tuning | 0 |
| Checkpoint reselection | 0 |
| Model reselection | 0 |
| New scene generation | 0 |
| New embedding inference | 0 |
| P9 rerun | 0 |
| Canonical P10 rerun | 0 |
| P11 rerun | 0 |
| Downstream fitting | 0 |
| Dissertation mutation | 0 |

Also zero: scientific reranking, canonical held-out metric recomputation,
similarity/threshold changes, new query selection, checkpoint changes and
scientific acceptance mutation. Small synthetic ranking unit tests do not
publish scientific evidence.

## Use and Next Step

Validate and locate the updated static HTML:

    python tools/render_retrieval_inspector.py --supplemental

For a future authorized presentation-only refresh:

    PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python tools/render_retrieval_inspector.py --refresh-supplemental

No server is needed. README documents both gallery modes, source labels,
diagnostics, state preservation, rank bands and interpretation boundaries.

Only inspector source, tests and this report are included in the Fuse reduced
commit. External generated presentation files, scene assets, scientific data,
checkpoints and targets stores are excluded.

Exact next useful work unit: **RETRIEVAL_10K_QUALITATIVE_ANALYSIS**.
It is not executed here; no dissertation results were written.
