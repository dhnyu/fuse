# Retrieval Inspector: Current and Legacy

## Current Inspector

```bash
python tools/render_retrieval_inspector.py
```

This is the normal workflow. It resolves and validates the **current repo-local
10K-capable inspector**, or builds it from accepted evidence if no package exists.
It prints `artifacts/retrieval-inspector/current/<inspector_id>/index.html`.

Open the printed HTML directly in a browser; no server is needed. It defaults
to **Expanded 10,000**, with **Canonical 1,600** available as a comparison mode.
The current application is not the legacy 1,600-only application.

The stable pointer is `artifacts/retrieval-inspector/current.json`. To explicitly
pack a new version after an authorized presentation update:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \
  python tools/render_retrieval_inspector.py --build-current
```

Only accepted manifests, rankings, diagnostics and rendered scene assets are
read. No embeddings are inferred or used to rerank. A new current pointer is
published only after the actual repo-local HTML passes browser validation.
`--overwrite` is rejected; existing content-addressed packages are immutable.

## Legacy Inspector

```bash
python tools/render_retrieval_inspector.py --legacy-canonical
```

This validates and locates the old 1,600-only application without regenerating
rankings or assets:

```text
artifacts/retrieval-inspector/legacy/retrieval_inspector_c612a074a9211c222eb9a811/index.html
```

The legacy directory is a relative alias to the original location:

```text
artifacts/retrieval-inspector/retrieval_inspector_c612a074a9211c222eb9a811/index.html
```

Both paths remain usable. Original HTML, JavaScript, CSS, manifests and 1,342
scene assets are untouched. `legacy.json` records the old ID, original path,
acceptance and core-file hashes. Legacy is retained for historical reproducibility,
not offered as the default inspector.

Terminology: **current** is the dual-gallery application; **expanded** is its
10,000-scene mode; **canonical** is its 1,600-scene comparison mode; **legacy** is
the old 1,600-only application. The internal/hash value `supplemental` remains a
backward-compatible identifier for the expanded mode, not a secondary application.

## Evidence and Packaging

Current evidence binds supplemental authority
`retrag_29e75a5e81df82e0c3d93783` and acceptance
`retr10k_0672df44ea0fb5adceafbec9`. Canonical P10 acceptance remains
`p10acc_6e5071beee7616750dec7907`; the query contract remains
`p10qq_dd7d0775f5809a793575342b`.

The current package contains real local HTML, JavaScript, CSS, manifest data,
diagnostic display data, presentation metadata and validation receipts. It is
not a redirect to external HTML. `accepted_manifest.json` retains the original
scientific inspector manifest byte-for-byte; `artifact.json` binds the new
presentation identity, implementation, authority, union/embedding/ranking
manifests, diagnostic hash, asset manifest and default gallery.

The 3,622 accepted scene assets are reused through a **validated relative
directory symlink** at `assets/`. The link resolves to the accepted external
inspector asset directory under `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/`.
Every referenced file is checked against its accepted SHA-256. Assets load lazily
by scene ID. Nothing renders 10,000 scenes or copies prepared tensors, geometry,
embeddings, ranking tables or scene caches into the repository.

The package requires that external data mount; moving the workspace or mount may
require rebuilding the placement-specific link. Machine paths, timestamps and
browser execution order are not part of the artifact identity. Heavy generated
packages remain ignored by Git; small current/legacy pointers, the legacy alias,
source and documentation are tracked. On another checkout the default command
builds a missing package when the accepted mount and preserved legacy artifact
are available; missing required evidence fails closed.

## Controls and Comparisons

The same ten fixed queries and eight models are available: FM / `cfg_d128`,
A1-A5, SSV and DS. Previous/next gallery, model and query controls retain other
state. Gallery switches retain query, model, setting, B/R/P layers, LC/DEM and
the selected position within each top/middle/bottom band.

Standard retrieval excludes self: 9,999 expanded or 1,599 canonical candidates.
Non-local retains center distance >= 2,000 m and displays the actual per-query
candidate count. Rank 1, ranks 2-11, central ten starting at
`floor((N-10)/2)+1`, and the final ten use each active candidate N.
Every candidate shows rank, similarity, distance, ID and Canonical/Supplemental
source; thumbnail tooltips include the same evidence.

The compact stability panel reads accepted `stability_diagnostics.json`: old
rank-1 ID/similarity and expanded rank; new rank-1 ID/source/similarity/distance;
top-10/top-100 overlap; and rank-1 minus rank-10 gap. It creates no aggregate score.

Maps remain north-up at fixed 500 m x 500 m extent, with common B/R/P symbols,
the accepted LC palette and a shared DEM scale over the five compared scenes.
Building coverage/count, road count/length, POI categories, LC composition,
DEM and SN/CNT/WIT/INT/CON summaries are retained. Supplemental district names
remain `Unavailable` where no accepted mapping exists; no P11 work is required.
Mobile uses horizontal scrolling rather than shrinking the five map columns.

URL hashes restore gallery, model, query, setting, top, middle, bottom, layers
(including no selected vector layers) and raster. Band values are zero-based
positions, not a promise to keep a scene absent from a different gallery's band.

## Interpretation Boundary

10K is the **current presentation default**, but remains a supplementary
retrieval-only gallery scientifically. Canonical P10/P11 evaluation is unchanged.
Expansion changes available candidates: lower overlap does not imply old
retrieval was wrong, and new candidates can outrank old ones simply because the
candidate universe is larger. The inspector establishes no model superiority.
The dissertation representative-rank figure protocol is not replaced by these
existing non-authoritative browsing bands.

## Validation and Compatibility

```bash
python tools/render_retrieval_inspector.py --validate artifacts/retrieval-inspector/current/<id>
python tools/render_retrieval_inspector.py --legacy-canonical
```

Current packing verifies 160 expanded and 160 canonical states against accepted
evidence, all band assets, and authoritative diagnostics; Chromium checks all
320 desktop states plus mobile, default gallery, transitions and URL restoration.

`--supplemental` is a compatibility option that still locates the external
accepted presentation and warns that it is not the current local workflow.
`--refresh-supplemental` retains the previous explicit external presentation
refresh behavior. Neither is needed for normal current use. Existing explicit
`--validate <legacy-path>` calls still work. `--output-root` now selects a
repo-local current/legacy artifact container, not a legacy ranking generator.
Do not rerun `_targets_retrieval_gallery.R` to update presentation artifacts.
