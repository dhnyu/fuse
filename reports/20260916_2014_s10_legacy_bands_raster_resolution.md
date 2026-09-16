Created (Asia/Seoul): 2026-09-16T20:14:58.817079+09:00

# S10 legacy ranking bands and raster resolution

## 1. FINAL STATUS

**PASS.** Published a new supplemental viewer with true full-order retrieval bands and a separate evidence receipt. Formal S10 acceptance/artifacts remain unchanged. Detailed thematic summaries are preserved. All previous 246 tests plus 12 new tests pass (**258 total**); full independent ranking/browser/raster verification passes.

Prompt summary: restore the legacy five-column Query / Rank1 / Top / Middle / Bottom inspection layout; reconstruct middle/bottom only from accepted normalized embeddings over the full eligible gallery; audit query/retrieval raster resolution; change display only, never formal scientific results.

## 2. Repository state

Repository `/members/dhnyu/fuse` (`~/fuse`), branch `reduced`.
Input HEAD `a0c3d72b8915f1bbfb5fbe702d759b9092207a5e`.
Initial worktree clean; fetched origin; divergence 0/0. Commit/push explicitly authorized.
Existing target definitions, stores, scientific configuration, model code and dependency network are unchanged. No targets execution or network regeneration was necessary.

## 3. Parent S10 acceptance

`s10_acceptance_5471f74031f267c4253df231`, **PASS**.
Acceptance file SHA256 remains `7db57622f33bb3027f68fe916e3ec1a8d6fbb7aa18a09e0945fe803de8d129f8`.

Generation:
`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/s10gen_a24b979d4c1557387cbbec35`.

28 accepted models/configurations, fixed 30 queries, common 9,000 evaluation gallery, normalized accepted embeddings, standard/non-local rules and formal Top50 are unchanged.

## 4. Legacy band semantics audit

The live augmentation inspector has augmentation-profile grids, not retrieval bands. Read-only Git history identified the actual retrieval inspector at **`10c02e4`**:

- `tools/retrieval_inspector/inspector.py:87`, `band_ranks()`.
- `tools/retrieval_inspector/app.js`, `columns()` and `columnHTML()`.
- `tools/retrieval_inspector/style.css`, comparison/column/strip/row/map rules.

The legacy function defines rank1, ranks 2–11, middle starting `(N−10)//2+1`, and last ten ranks. Those semantics are copied exactly. No historical embeddings, old gallery definitions or interrupted evidence are adopted.

The historical CSS is retained verbatim in `legacy_retrieval_10c02e4.css`, SHA256
`ff59ec46671059903133eb97acfd982870e4acf0748862e7b757d8e862f23436`.
The publisher extracts/scopes its base comparison rules: five columns (250px minimum), 1,300px minimum comparison width, 74px base column headers, 112px strips, five-by-two 47px mini buttons, 30px thumbnails, original row padding and map borders. Historical expanded-gallery badges/diagnostics are not included. Current header/controls and detailed-summary styling remain in place.

## 5. Formal Top50 limitation

The accepted Parquet artifacts contain only ranks 1–50 for each query/model/mode. They directly supply Rank1 and Top band but cannot identify true middle or bottom. No rank inside Top50 is relabelled as global middle/bottom; ranks 41–50 are never called Bottom band.

The final reconstruction verified **all 84,000 formal rows exactly**, including scene ID, score, distance, rank, mode and model/query identity.

## 6. Supplemental full-ranking/band reconstruction design

`bands.py` reads only accepted normalized float32 embedding vectors and common query/gallery metadata. Checkpoint loading, model inference, Fourier computation and input preprocessing are absent.

For each query:

1. Compute cosine using exactly the current formal NumPy operation `vectors @ vectors[query_index]` without renormalizing/changing vectors.
2. Use float64 EPSG:5186 center distance, exactly as formal S10.
3. Sort similarity descending with stable sorting over the already scene-ID-sorted gallery.
4. Exclude self; for non-local retain distance **≥2,000m**, including equality.
5. Check every overlapping formal Top50 row for exact equality; any mismatch fails closed.
6. Retain only the 31 band rows and eligible count.

One-thread BLAS limits keep the tested numerical path fixed. The full order is transient in memory; it is not published as a replacement ranking artifact.

Final selected evidence: **52,080 rows** = 28 × 30 × 2 × 31. Query JSON evidence totals **13,849,062 bytes** (~13.2MiB), not a full ~15-million-row ranking archive.

Receipt `band_evidence_receipt.json` binds parent acceptance, exact accepted embedding manifest IDs, query/gallery identities, source checksums, band implementation hash, display-code hashes and selected-row output checksums. Viewer browser code is artifact-only; reconstruction is an explicit separate publisher operation.

New band scenes broaden display coverage to 8,628 scenes. Existing 2,341 scene JSON payloads are reused **byte-for-byte**. Additional scenes read already persisted S10 original-input tensors plus their exact SHA-bound P3 observed geometry/road records. The existing renderer serializes already clipped geometry to SVG; no spatial clipping, reprojection, category reconstruction, tensorization, raw raster extraction or scientific preprocessing occurs. LC/DEM colour mapping is the same existing display-only renderer, operating on stored values.

## 7. Exact band rank definitions

Let N be the full eligible candidate count after self/non-local exclusions.

| Band | Exact one-based ranks |
|---|---|
| Rank1 / Most similar | 1 |
| Top band | 2–11 |
| Middle band | `start=floor((N−10)/2)+1`; start through start+9 |
| Bottom band | N−9 through N |

The middle definition preserves the legacy half-rank left bias for odd N; no new center convention was invented. Candidate counts are common across models for the same query/mode.

Standard always N=8,999: middle **4,495–4,504**, bottom **8,990–8,999**.
Query 1 non-local N=8,827: middle **4,409–4,418**, bottom **8,818–8,827**.
Across all fixed queries, non-local N ranges **8,776–8,922**.

## 8. Scene comparison layout change

The default now has five legacy-style columns:
Query | Rank 1 / Most similar | Top band (10) | Middle band (10) | Bottom band (10).

Each band has its own five-by-two compact thumbnail strip with actual rank and hover scene ID/cosine/metres. Clicking a thumbnail updates that column's vector, raster, attributes and detailed thematic summaries. Query/Rank1 have equal-height strip spacers, maintaining alignment. The previous six-large-result-panel scene comparison is not used by the new entrypoint.

The detailed-summary `details()` / `thematicMap()` functions are reused unchanged. The only change to the old `app.js` is an initialization guard allowing the new band controller to use those existing functions. All six thematic types, unknown treatment, legends, geometry and raw lane bindings are retained. Existing publishers/tests remain available for prior-generation reproducibility.

## 9. Raster blur root cause

**No query-specific versus retrieval-specific resolution loss or bilinear blur was reproduced.** It would be incorrect to report a proven downsampling bug.

The prior viewer's measured Query and Rank1 paths were identical:

- LC: accepted 22×100×100 fractions → 100×100 PNG.
- DEM: accepted standardized 17×17 tensor → 17×17 PNG.
- Both roles used the same generator, scene-keyed immutable payload, image element and CSS.
- Both roles measured **292.828×292.828 CSS px**, with `image-rendering: pixelated` for LC **and** DEM.
- No retrieval-only thumbnail/downsampling, alternate raster source, lower export size, special canvas backing store, role-dependent DPR or query-SVG/retrieval-bitmap distinction existed.

A separate browser screenshot pixel test found **zero displayed RGB colours absent from the original PNG** for both Query and Rank1, before and after the change. Thus this measured browser did not introduce bilinear mixture colours even in the previous viewer.

The source itself is **class fractions**, not a hard-label categorical image. Its display blends class palette colours using those already stored fractions. In the representative scenes, cells with multiple nonzero class fractions were Query 1: 1,910/10,000; Rank1: 1,983; middle: 1,670; bottom: 800. Query/Rank1 PNGs already contained 180/187 distinct RGB colours, beyond the 22 class palette colours. These are stored display content differences, not evidence of lower spatial resolution. They can remain visually soft at boundaries after nearest scaling; removing them would require a prohibited class reassignment or value change. The subjective blur impression is not uniquely diagnosed beyond these measured facts.

DEM is genuinely coarser (17×17) for **every** role. This is an accepted input characteristic, not a retrieval-only display defect.

## 10. Raster dimension audit table

Measured in Chromium at viewport 1,800×1,200, DPR=1, Query 1 / main / Standard. The selected middle/bottom are the first item of each true full-order band.

| Scene type | Source artifact | Stored dimensions | Rendered intrinsic dimensions | CSS dimensions | Interpolation |
|---|---|---:|---:|---:|---|
| Query LC | S10 original input / same display renderer | 22 × 100 × 100 | 100 × 100 | 325.797 × 325.797px | nearest, canvas 326²; smoothing OFF |
| Query DEM | S10 original input / same display renderer | 17 × 17 | 17 × 17 | 325.797 × 325.797px | continuous browser image scaling |
| Rank 1 LC | S10 original input / same display renderer | 22 × 100 × 100 | 100 × 100 | 325.797 × 325.797px | nearest, canvas 326²; smoothing OFF |
| Rank 1 DEM | S10 original input / same display renderer | 17 × 17 | 17 × 17 | 325.797 × 325.797px | continuous browser image scaling |
| Middle 4495 LC | S10 original input / same display renderer | 22 × 100 × 100 | 100 × 100 | 325.797 × 325.797px | nearest, canvas 326²; smoothing OFF |
| Middle 4495 DEM | S10 original input / same display renderer | 17 × 17 | 17 × 17 | 325.797 × 325.797px | continuous browser image scaling |
| Bottom 8990 LC | S10 original input / same display renderer | 22 × 100 × 100 | 100 × 100 | 326.797 × 326.797px | nearest, canvas 327²; smoothing OFF |
| Bottom 8990 DEM | S10 original input / same display renderer | 17 × 17 | 17 × 17 | 326.797 × 326.797px | continuous browser image scaling |

Scene IDs:

- Query: `scn_804d625229e303af92739d3f`
- Rank1: `scn_d4bb711ea72bd18180cc6172`
- Middle rank4495: `scn_da7d14547db83488ba3e80f8`
- Bottom rank8990: `scn_f9693587a2ed4ba9a710fffd`

The last legacy column has no right border, giving it ~1 CSS pixel additional width. Canvas backing follows actual device size (326² or 327² here); all LC sources remain the same 100². This tiny border/layout difference does not imply different scientific resolution. DPR=2 backing-size behavior was also validated.

## 11. Display fix / hardening

LC Scene comparison now always uses a shared canvas renderer:

- Intrinsic source remains 100×100 for query and every retrieved scene.
- Backing dimensions equal rounded CSS size × devicePixelRatio.
- `imageSmoothingEnabled=false` and pixelated canvas presentation.
- No new RGB mixture colours are introduced by nearest enlargement (verified on all five columns).
- Corrupt/mis-sized PNGs fail; no synthesized fallback.

DEM is explicitly separated: stored 17×17 values/images remain unchanged; browser display interpolation is allowed for this continuous layer. No scientific values are resampled or persisted differently.

This enforces a common display rule rather than claiming to repair an unobserved role-specific downsampling bug. Detailed-summary LC imagery/renderer remains unchanged as requested.

## 12. Ranking/raster tests

**258 tests passed in 17.58s**, retaining all previous 246 tests. Added tests cover exact legacy rank positions, full eligible counts, boundary equality, exact Top50 overlap, deterministic ties, invalid score/missing evidence/unnormalized-vector rejection, vector non-mutation, no inference/checkpoint imports, legacy band structure and shared raster rendering contracts.

Python syntax / JavaScript `node --check` / `git diff --check`: PASS.

Independent full read-back: all 52,080 selected band rows and all 84,000 formal Top50 rows matched an independent full tuple sort `(−score, scene_id)` over eligible candidates. All final output file checksums passed.

Immutability checks: original acceptance unchanged; 33 accepted page/static files valid; all 43 scientific runtime source hashes identical; all 2,406 prior viewer files unchanged; all 2,341 overlapping thematic scene JSON payloads byte-identical.

## 13. Browser validation

PASS for Query 1/2/30; main, d256, DS, B9; Standard and Non-local; five columns; 10 thumbnails in each band; first/middle/last thumbnail selection in each band updating the exact expected scene/rank; LC/DEM toggles; detailed summaries expand/collapse; all thematic map types; asset loading.

No application JS errors or horizontal overflow at 1,800px and 1,600px desktop widths. DPR=1 and DPR=2 checked. LC canvas colour-membership checks introduce zero new RGB values. Injected corrupt raster decoding fails closed and clears the view. Desktop screenshot visually inspected.

Bounded smoke used main / one query / both modes: 62 band rows, 50 unique display scenes. Full supplemental publication completed in **304.65 seconds**; this was display/evidence generation, not full S10 execution.

Evidence (local ignored logs, not committed):

- `logs/20260916_2014_s10_legacy_bands_audit.json`
- `logs/20260916_2014_s10_legacy_bands_desktop.png`
- `logs/20260916_2014_s10_legacy_bands_pixel_audit.json`
- `logs/20260916_2014_s10_legacy_bands_tests.log`
- `logs/20260916_2014_s10_legacy_bands_publication.log`

A Pillow deprecation notice arose only in the bounded screenshot-colour diagnostic (`getdata`); it did not affect results or publisher/browser behavior. The subjective historical blur could not be reproduced as an asymmetric resolution/interpolation defect; this limitation is explicit above.

## 14. New viewer path

Viewer **`viewer_f33db05a1507064733ee8702`**.
Band evidence **`s10_supplemental_bands_5aee156c71f64e4e70258d89`**.

`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_f33db05a1507064733ee8702/index.html`

30 query pages + index; 8,628 scenes. Total display files ~4.70GB (including standalone SVG assets), while band JSON is only ~13.2MiB. Both receipts are in this directory. Previous generations remain immutable.

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_f33db05a1507064733ee8702
```

Open `http://localhost:8765`. Localhost/HTTPS is required for Web Crypto; file:// is unsupported. No scientific stage command is needed.

## 15. Files changed

- `tools/retrieval_inspector/supplemental/bands.py`
- `tools/retrieval_inspector/supplemental/build_bands.py`
- `tools/retrieval_inspector/supplemental/scene_sources.py`
- `tools/retrieval_inspector/supplemental/bands.html`
- `tools/retrieval_inspector/supplemental/bands.css`
- `tools/retrieval_inspector/supplemental/bands_app.js`
- `tools/retrieval_inspector/supplemental/legacy_retrieval_10c02e4.css`
- `tools/retrieval_inspector/supplemental/app.js` (initialization guard only)
- `tools/retrieval_inspector/supplemental/README.md`
- `scripts/validate_s10_bands_viewer.py`
- `tests/python/test_s10_retrieval_bands.py`
- This report.

## 16. Scientific safety

Training NO. Checkpoint loading NO. Inference/embedding generation NO. Fourier NO. Original preprocessing NO. Scientific raster derivation/resampling/class assignment NO. S09/checkpoint mutation NO. S11 NO. Full S10 execution NO. Scientific acceptance/ranking mutation NO. Model selection NO.

**Authorized supplemental computation YES:** cosine/distance/order reconstruction from accepted embeddings and unchanged gallery metadata, with exact formal Top50 consistency and a separate evidence receipt. It is not hidden inside browser rendering and is not relabelled formal S10 acceptance.

Original scene tensors and observed geometry are read only. New SVG/PNG/HTML files are supplemental display artifacts outside Git. No existing viewer or scientific artifact was overwritten. Task-owned smoke files/servers are cleaned after verification; new published viewer is retained. The next action is human inspection, not automatic S11 execution.
