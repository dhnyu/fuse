Created (Asia/Seoul): 2026-09-16T19:08:55.101895+09:00

# S10 supplemental viewer layout refactor

## 1. FINAL STATUS

PASS. UI-only supplemental inspector published; original S10 scientific acceptance and pages remain unchanged. No formal stage was executed.

Purpose / prompt summary: adopt the augmentation inspector visual language for the accepted S10 retrieval results, with focused query/model/mode inspection, vector/raster/detail panels and categorical microcharts, without scientific recomputation or mutation.

## 2. Repository / branch / HEAD

- Repository: `/members/dhnyu/fuse` (`~/fuse`).
- Branch: `reduced`.
- Input HEAD: `1ca91648ef8d7986aac23beab711ceb986da89cd`.
- Initial worktree: clean; fetched `origin/reduced`; divergence 0/0.
- Changes are additive: no existing scientific or viewer source file modified.
- Commit/push authorized by this task; this report is included in the UI commit.

## 3. Current S10 artifact consumed

Parent acceptance: `s10_acceptance_5471f74031f267c4253df231`, status PASS.
Acceptance file SHA256: `7db57622f33bb3027f68fe916e3ec1a8d6fbb7aa18a09e0945fe803de8d129f8`.

Canonical generation:
`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/s10gen_a24b979d4c1557387cbbec35`.

Inputs: acceptance-bound query, gallery, model, ranking and render manifests; persisted original scene tensors bound through each accepted ranking → embedding manifest → prepared-input manifest; the accepted category dictionary pinned in the model manifest and original-input manifest. Embedded model configuration is read as metadata; no checkpoint payload is loaded. Existing embedding payloads are only checksum-verified, never used for score computation.

All 28 models, 30 fixed queries, common 9,000 gallery, both retrieval modes, and 84,000 published Top-50 rows remain intact. Display uses exactly the existing ranks 1–5 (8,400 rows across models/queries/modes).

Supplemental viewer:
`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_404735cf7d702a5704f0b8f1/index.html`.

30 query pages + index, 2,341 shared scene display assets, approximately 477 MiB. A separate `viewer_receipt.json` binds parent acceptance, consumed source manifest checksums, display implementation and output checksums. No accepted files are overwritten. Existing supplemental directories are also never overwritten. Only a directory with a complete receipt is publishable.

## 4. Augmentation inspector audit findings

`tools/augmentation_inspector/inspector.py` embeds its UI shell in `_template`: control strip, entity layer switches, aligned panel grids, vector/raster displays, compact summaries, detail tables, provenance and responsive CSS. Its current source header is white; the requested dark green header is an intentional S10 adaptation. Its four columns represent original/augmentation profiles, not retrieval ranks. Its historical data paths and transformation/scientific logic were not imported.

The existing S10 `viewer.py`, `app.js`, `style.css` display query + 28 model rows with standard/nonlocal Top-5 SVG cards. They read accepted artifacts and contain no computation fallback. Existing rendering is vector-only; S10 original-input tensors additionally contain stored land-cover fractions, standardized DEM, category indices and relation masks. These permit display-only colour mapping and summaries without accessing raw raster/vector sources or executing preprocessing.

Reviewed blueprint S10 non-selection contract and dissertation qualitative retrieval section. Existing methodological top/band examples do not change the explicitly authorized S10 Top-5 presentation; no sampling, evaluation or ranking protocol was changed.

## 5. Layout redesign summary

- Dark green header, restrained evidence badge, sticky compact controls, muted gray background and bordered aligned panels.
- Query selector + previous/next; OFAT/COMPARISON/All groups; all 28 model selections; Standard / Non-local ≥ 2 km selector.
- Summary strip shows query index, model, common gallery, published/displayed rank counts, retrieval setting and cosine interpretation.
- Six compact scene panels: Query and Rank 1–5. Selecting a rank enlarges it beside the fixed query.
- Both enlarged panels repeat Vector data, Raster data, Attributes & spatial relations and Detailed summaries.
- Building/Road/POI visibility controls existing SVG colours; LC/DEM visibility controls existing-tensor image displays.
- Model/mode persist across query navigation. No multi-model wall is the default.
- Source data identity is verified before display; corrupt/missing JSON clears panels and reports an error with no fallback.

## 6. Detailed summaries visualization design

POI L1 categories, building use, building structure and road rank use compact ranked bars with counts, accepted category labels/codes and stable categorical colours. Top five regular categories + Other are shown; Unknown is retained separately. Empty data is explicit.

Land cover uses the augmentation inspector palette, LC channel/code labels and percentage bars. Percentages summarize stored class fractions weighted by stored valid support. Display pixels blend class palette colours using stored fractions, without assigning a new dominant class or generating a new scientific raster.

DEM displays the already stored standardized mean tensor, not raw elevation in metres. Colours use a fixed −3 to +3 display scale; clipping affects only colour. Missing cells are transparent. No extraction, interpolation, resampling or new normalization occurs. All models show common original scene context, including modalities that some configurations do not consume; the UI explicitly states this.

Spatial relations show existing ordered-edge counts and stored relation-mask counts; relations are not computed anew.

## 7. Files changed

All new files:

- `tools/retrieval_inspector/supplemental/build.py`
- `tools/retrieval_inspector/supplemental/index.html`
- `tools/retrieval_inspector/supplemental/style.css`
- `tools/retrieval_inspector/supplemental/app.js`
- `tools/retrieval_inspector/supplemental/README.md`
- `scripts/validate_s10_supplemental_viewer.py`
- `tests/python/test_s10_supplemental_viewer.py`
- This report.

The original viewer, source runtime closure, targets graph, configurations, schemas and network HTML are unchanged. No targets execution/network regeneration is required for this independent supplemental publisher.

## 8. Validation / tests

- Python syntax and JavaScript `node --check`: PASS.
- Existing 206 tests + 12 new supplemental tests: **218 passed**, final run 17.13 seconds.
- New tests cover stored-summary values, tensor non-mutation, missing-category handling, vocabulary ordering, exact Top-5 selection, missing/duplicate/wrong-bound rows, invalid raster rejection, scientific import boundary and immutable/separate publication.
- Initial bounded smoke: one query, 113 scenes, desktop screenshot inspection; no horizontal overflow or application JS errors.
- Complete supplemental publication: 30 query pages, 2,341 scene assets; no scientific inference.
- Validator read-back: every supplemental file checksum verified; all **8,400 displayed rows exactly equal** the corresponding formal ranking rows, including score/distance/model/query/mode metadata.
- Chromium 1600×1100: query 1/2/30, main/DS/d256/B9, both modes, group inventories 11/17/28, Rank-5 focus, all five layer toggles, vector visibility, raster image loading and detail sections PASS; no horizontal overflow or JS errors.
- Chart DOM values match stored source display summaries, including Unknown and Other.
- Injected missing/corrupt query JSON both fail closed with zero displayed scenes and no fallback.
- Existing acceptance and original pages manifest read-back PASS: `s10_pages_7f93809f35bd121151a08142`, all 33 existing page/static files checksum-valid.
- All **43 accepted S10 runtime source hashes remain identical**.

The first browser harness attempted to inspect an element during asynchronous replacement; the harness was corrected to wait for binding completion. A fault-injection callback initially interpreted Playwright's request argument as the injected condition; the callback signature was corrected. These were validation harness errors; final tests above passed. No production artifacts were repaired or modified.

Not executed: full S10, S11, training, inference, raster derivation, ranking recomputation or targets make. Existing scientific unit tests run only local fixtures/contracts. Browser serving requires localhost or HTTPS for checksum verification via Web Crypto; direct file:// opening is not supported.

## 9. Scientific safety

Training NO. S11 NO. S09/checkpoint mutation NO. Checkpoint loading NO. Embedding inference NO. Geometry-feature computation NO. Retrieval ranking/distance filtering recomputation NO. Scientific raster derivation NO. Acceptance mutation NO. Query/gallery/model selection changes NO.

The original acceptance remains PASS and is neither replaced nor reinterpreted. The standalone display receipt is not scientific acceptance. Data and generated images/pages remain outside Git. Only UI source, tests, documentation and this report are committed. Temporary smoke assets and browser server are cleaned after verification; the supplemental publication is retained.

## 10. Next action

Inspect the supplemental viewer locally:

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_404735cf7d702a5704f0b8f1
```

Open `http://localhost:8765`. S11 remains blocked/fail-closed; no automatic next scientific stage is authorized by this UI task.
