Created (Asia/Seoul): 2026-09-16T19:45:55.472932+09:00

# S10 exact inspector layout and thematic maps

## 1. FINAL STATUS

**PASS** — display-only supplemental viewer, 30 pages / 2,341 shared scene assets, with all six thematic summaries on Query and Rank 1–5. Existing 218 tests retained; **246 tests pass**. Full browser and source binding validation pass.

Purpose / prompt summary: discard the prior custom retrieval UI, directly reuse the live augmentation inspector layout, replace detailed-summary bars with actual spatial thematic maps, and preserve all S10 scientific results and prior supplemental outputs.

Repository: `/members/dhnyu/fuse` (`~/fuse`), branch `reduced`.
Input HEAD: `b308c77dab55ede5d198642d4ff1a23e037407c8`.
Initial worktree clean; fetched origin, divergence 0/0. Commit/push explicitly authorized by this task.

## 2. Parent S10 acceptance

`s10_acceptance_5471f74031f267c4253df231`, **PASS**, unchanged.
SHA256: `7db57622f33bb3027f68fe916e3ec1a8d6fbb7aa18a09e0945fe803de8d129f8`.

Canonical generation:
`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/s10gen_a24b979d4c1557387cbbec35`.

The same 28 models, 30 queries, 9,000 gallery, both modes, Top 50 and 84,000 formal ranking rows remain authoritative. Scores, distances, checkpoint/embedding/Fourier identities and query/gallery bindings are unchanged. Display selects only existing ranks 1–5; all 8,400 displayed rows match formal rows exactly.

## 3. Previous supplemental viewer

`viewer_404735cf7d702a5704f0b8f1` is retained unchanged. All 2,405 files listed in its receipt were checksum-verified. Its existing SVG strings, LC/DEM image bytes, stored display fractions and summary values are reused. The new publisher no longer calls the legacy raster colour-mapping helper; no raster display is regenerated.

A display-only intermediate `viewer_36e0f54538c55de8e27dfecf` was published while the raw lane source audit was incomplete. It is retained without overwrite; the final deliverable below supersedes it and includes source-supported lane maps. Neither is scientific acceptance.

## 4. Exact augmentation-inspector layout reuse

Authority: live `tools/augmentation_inspector/inspector.py`, specifically `_template`, its embedded `<style>` and panel/control DOM. The CSS is **extracted verbatim at publication** into `augmentation.css`; the live source hash is included in the new viewer identity. No scientific augmentation code is imported/executed.

| Component | Live source / reused contract |
|---|---|
| Body | 14px/1.4 system UI; `#f5f7f7`; original ink, muted, line and panel tokens |
| Header | White, sticky, top 0, z-index 20; 12px 18px padding |
| Brand | Flex row; 12px gap; title 20px; subtitle uses original muted style |
| Controls | Same `.controls` / `.control` / `.layer-group` DOM; wrap; 10px gap |
| Inputs/buttons | Original 34px height, 9px horizontal padding, borders and 4px radius |
| Main | Maximum 1,800px width; 18px padding; centered |
| Metadata | Original `.case-meta` heading + code strip; no summary cards |
| Sections | Original `.section > h2`, 15px text, 9px 12px padding, `#263238` |
| Grid | Original `.grid4` border and 1px gaps; adapted to six equal columns |
| Panels | Original `.panel`, `.panel h3`, square `.canvas-wrap`, summaries and legends |
| Responsive | Original 1,050px two-column / 620px one-column breakpoints retained |
| Interaction | Linked vector wheel/drag, Reset zoom, Provenance; detail disclosure per column |

At 1,800px, the six columns are approximately 293px wide. The only grid-width adaptation is four augmentation profiles → six retrieval scenes. Below desktop width, columns follow the existing responsive grid pattern rather than adding horizontal scrolling. Thematic maps use one map per row within each scene column to preserve readable spatial patterns; fixed-height scrollable legends keep thematic rows aligned across scenes.

**Audit discrepancy recorded:** the actual live source has Vector transformation / Raster transformation / Attribute transformation and a provenance section. It has no thumbnail band, hero, or separately named Detailed summaries section. The implementation follows that real section/grid/panel structure, with retrieval labels and the requested Detailed summaries section appended in the same structure. No screenshot-only or historical layout was reconstructed.

Browser computed styles for header padding/stickiness/background, main width/padding, title typography, control gap/input dimensions and section heading styles match the live template exactly. Desktop screenshot inspection confirms the shared section-based hierarchy and aligned six-column maps. The reference screenshot captures the live template shell without running historical augmentation data/computation; this is a structural/style comparison, not a pixel-identical comparison of different scientific contents.

## 5. Removed/replaced previous custom layout

Removed the large dark hero, independent summary card strip, Rank card/thumbnail wall, selected-rank focus interaction, two-column Focused inspection and ranked horizontal bars.

The default view now aligns Query | Rank 1 / Most similar | Rank 2 | Rank 3 | Rank 4 | Rank 5 through:

1. Scene identity / stored score / distance / mode, then VECTOR DATA.
2. RASTER DATA (existing LC and DEM displays).
3. ATTRIBUTES & SPATIAL RELATIONS (stored counts / masks).
4. DETAILED SUMMARIES (six actual spatial maps with categorical legends).

Controls select fixed query, model group, model, retrieval setting and five visible layers. Previous/next navigation preserves model/mode. Thematic maps always remain 500m, north-up; linked zoom applies only to the vector inspection panels.

## 6. Per-entity attribute availability audit

| Attribute | Per-entity source | Availability | Thematic map |
|---|---|---|---|
| POI category | Accepted S10 input `entities.poi_category[:,0]` (CLASS_L1), indexed by `poi_row_index` | A: per-point/entity values | YES |
| Building use | `entities.building_category[:,0]` (A9), `building_row_index` | A: per-polygon/entity values | YES |
| Building structure | `entities.building_category[:,1]` (A11), same building rows | A: per-polygon/entity values | YES |
| Road rank | `entities.road_category[:,0]` (ROAD_RANK), `road_row_index` | A: per-road values | YES |
| Road lane | Raw `LANES` in exact accepted P3 parent tar member `vector/road_observed.parquet`; ordered road IDs verified against S10 input | A: raw per-road values in accepted source payload; S10 tensor alone stores standardized values | YES |
| Land cover | Existing display raster and its stored fraction legend; verified against accepted input fractions/support | Stored spatial raster, not inferred entity assignments | YES, unchanged image |

No attribute here is painted from aggregate counts. Other stored attributes such as ROAD_TYPE and deeper POI levels exist but were not added to scope. Unknown/masked categorical values are neutral gray; legend counts come from the actual stored assignments.

## 7. Thematic maps implemented

- POI category: existing point geometry coloured by stored L1 category.
- Land cover: previous display image reused byte-for-byte, previous palette and legend retained. No dominant-class assignment.
- Building use: existing polygons coloured by A9 values.
- Building structure: the same polygons recoloured by A11 values.
- Road rank: existing polylines coloured by stored rank; count only, no new length metric.
- Road lane: the same polylines coloured by raw stored lane values; count legends.

All geometries are copied from the accepted S10 SVG. The accepted renderer serialized one SVG child per original entity in sorted local entity ID order; the accepted input tensor preserves that same order. The publisher checks the accepted implementation hashes for renderer/reader/tensorization, same P3 payload hash, scene ID, entity count/order, typed row indices and SVG B/R/P paint identity before binding values. No nearest/spatial join, geometric matching or coordinate reconstruction is performed.

Browser colouring changes only fill/stroke and adds display metadata/title. Geometry strings, part structure, point coordinates, transforms, clipping state and line widths remain exactly unchanged. Tests compare the complete geometric attribute signatures before/after colouring. Legends retain all categories in a scrollable area rather than assigning an aggregate Other category to objects.

## 8. Road lane availability/result

The initial tensor-only audit found `road_numerical[:,0]` standardized values and a missing mask, not raw lane counts. That alone was insufficient for a lane-category map; inverse scaling/rounding was not attempted.

The requested **source-payload audit** then confirmed raw `LANES` in the S10-bound P3 original road records. This is the existing accepted source, not a new GIS source. Resolution follows:

accepted S10 model manifest → SHA-pinned `scene_to_shard.parquet` → exact P3 parent tar → stored road rows.

The accepted cache is `oscache_75a543f656ab777aada74fbd`; all 96 consumed parent tar hashes are verified and recorded in the new UI receipt. Parent identity must equal each S10 original input's `lineage.parent`; ordered road entity IDs must equal the tensor's road rows. Values are then read directly from those records, with no new attribute matching or inference.

Actual published display scenes contain raw values 1, 2, 3, 4, 5, 6 and 8. There are 365 displayed scenes without roads; their road maps/legends are empty, not imputed. Legend categories retain exact values; ordinal colour tones use 1 / 2 / 3 / 4+ without changing values. Tests additionally cover missing, zero and fractional stored values to prohibit silent rounding/imputation. Missing is gray; road line widths are unchanged.

## 9. Tests / browser validation

**246 passed in 16.21s**: all previous 218 tests plus 28 new tests. No existing test was removed or relaxed. New coverage includes literal layout reuse, entity membership for four categorical maps, neutral unknown handling, no mutation, missing-source fallback behavior, wrong source/frame/order/type/category rejection, raw lane assignments without inverse scaling, lane parent/entity/scene mismatch rejection and corrupt parent payload rejection.

Python syntax and `node --check`: PASS. `git diff --check`: PASS.

Bounded smoke: one fixed query / 113 scene displays, including lane maps; six columns, 30 vector thematic maps + 6 LC maps, no JS errors.

Final viewer validation:

- All output checksums verified.
- All 8,400 displayed Top-5 rows exactly equal formal ranking rows (scores, distances, query/model/mode included).
- 50 representative scenes (all 30 queries + 20 additional scenes): category row indices, entity IDs, counts and assignments match stored tensors; raw lane membership matches exact SHA-verified P3 records; LC legend fractions match stored fractions/support exactly.
- Previous SVG/LC/DEM/summary data identical; input tensors and source files remain read-only.
- Query 1/2/30, main/d256/DS/B9, both modes, all Rank 1–5 columns, five layer toggles, disclosures, linked zoom/reset, provenance and model groups PASS.
- Browser verifies every painted object's category/color and unchanged geometric attribute signature for tested scenes.
- No application JS errors, missing images or horizontal overflow at desktop widths 1,440 / 1,600 / 1,800px.
- Missing/corrupt query JSON fails closed without fallback.
- Published augmentation CSS is byte-identical to the live embedded CSS; computed layout properties match.
- Existing acceptance and 33 accepted page/static files remain checksum-valid; all 43 accepted scientific runtime source hashes remain identical.

An initial new structural test searched for literal `class="panel"`, whereas the live source creates panels via `className='panel'`; that test was corrected to the actual source construction. No product code/scientific artifact repair was needed for that test issue.

Validation artifacts (local, ignored; not committed):
`logs/20260916_1945_s10_viewer_thematic_desktop.png`,
`logs/20260916_1945_s10_viewer_thematic_layout_reference.png`,
`logs/20260916_1945_s10_viewer_thematic_browser.log`,
`logs/20260916_1945_s10_viewer_thematic_tests.log`.

No targets make, inference, training or S11 execution was performed. Targets definitions/network remain unchanged, so graph regeneration was unnecessary. Browser requires localhost or HTTPS for Web Crypto; file:// is unsupported. No pixel-difference claim is made between different scene contents.

## 10. New viewer path

Final ID: **`viewer_f8d14a826a75bc8451f219c5`**.

`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_f8d14a826a75bc8451f219c5/index.html`

30 query pages + index, 2,341 scene display assets, approximately 733 MiB.
Receipt: same directory, `viewer_receipt.json`. This receipt is UI provenance, not scientific acceptance.

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_f8d14a826a75bc8451f219c5
```

Open `http://localhost:8765`. No scientific command is needed.

## 11. Files changed

- `tools/retrieval_inspector/supplemental/build.py`
- `tools/retrieval_inspector/supplemental/thematic.py` (new)
- `tools/retrieval_inspector/supplemental/lane_source.py` (new)
- `tools/retrieval_inspector/supplemental/index.html`
- `tools/retrieval_inspector/supplemental/style.css`
- `tools/retrieval_inspector/supplemental/app.js`
- `tools/retrieval_inspector/supplemental/README.md`
- `scripts/validate_s10_supplemental_viewer.py`
- `tests/python/test_s10_thematic_viewer.py` (new)
- This report.

The live augmentation inspector is unchanged. Scientific source files, configurations, schemas, targets graph, existing accepted viewer and scientific artifacts are unchanged. Generated displays and screenshots remain outside Git.

## 12. Scientific safety

Inference NO; checkpoint loading NO; embedding calculation NO; ranking recomputation NO; geographic filtering recomputation NO; preprocessing recomputation NO; raster recomputation NO; S10 rerun NO; S09/checkpoint mutation NO; S11 NO; model selection NO.

Allowed operations were source hash verification, reading stored rows/tensors/SVGs, exact-ID/order validation, category-to-colour display mapping and categorical count/legend presentation. Lane maps use only the already accepted direct source payload. Scientific acceptance remains PASS and immutable; no scientific acceptance was reissued or reinterpreted.

Temporary smoke servers and task-owned smoke assets are cleaned. The next action is human inspection of this supplemental viewer; no scientific pipeline continuation is implied.
