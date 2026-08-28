# P4 Augmentation Inspector

## 1. VERDICT

`P4_AUGMENTATION_INSPECTOR_PASS_PUSHED` (commit and push details are completed below after publication).

## 2. Repository state

- Repository: `/members/dhnyu/fuse`
- Branch: `reduced`
- Starting HEAD: `d1c97ef47a44ad394b64d63ac5563382d6fe8472`
- Starting upstream divergence: ahead 0 / behind 0
- Starting working tree: clean
- Dissertation branch: `reduced`
- Dissertation HEAD: `e66d17d65e97a5e3f50fa9a111a51559db05666f`
- Dissertation working tree: clean

## 3. Accepted P3/P4 inputs

- P3 original cache: `oscache_c89fa07e3d6cb1819a7994a6`
- P3 acceptance: `osca_a55d2c02c3737c5f5557092a`
- P4 supplement: `p4-determinism-v1`
- P4 master bank: `augbank_a470cb156612cff12fb316fc`
- P4 acceptance: `aba_b6ee67e0d798020a6c418c05`
- P4 logical K8 index: `abi_f9ff792612ca86f486576491`
- Accepted population: 2,421 training scenes, three profiles, 116,208 physical candidates, 58,104 logical K8 references
- P3/P4 payload size contracts: 2,296,125,440 and 10,849,576,960 bytes

Before execution, path/size/mtime/SHA-256 snapshots were recorded for all 96 P3 tar payloads, all 288 P4 tar payloads, and both effective-index files.

## 4. Scope and non-scientific status

The inspector is a standalone read-only utility. It is not registered in `_targets.R`, does not contribute to artifact identity, and does not constitute scientific acceptance. It calls neither the P4 writer nor augmentation functions and performs no production recomputation.

## 5. Implemented files

- `tools/render_augmentation_inspector.py`
- `tools/augmentation_inspector/__init__.py`
- `tools/augmentation_inspector/inspector.py`
- `tools/README_augmentation_inspector.md`
- `tests/test_augmentation_inspector.py`
- `artifacts/augmentation-inspector/p4-augmentation-inspector.html`
- This report

## 6. Reader and shard lookup

P3 lookup uses the accepted `scene_to_shard.parquet`; P4 identity uses the accepted K16 logical index and branch manifests. Selected payload tar checksums and compact candidate-member checksums are verified before decoding. Parquet candidate predicates restrict materialization to the requested candidate. The whole 10.8 GB bank is never loaded into memory.

## 7. QC case-selection method

`qc-extremes` streams only `candidates.parquet` from each accepted branch, groups by scene/master-view identity across profiles, and applies deterministic metric ordering with scene-ID/view-ID tie breaks. Selected pairs:

| Reason | Scene | View | Metric |
|---|---|---:|---:|
| Geometry fallbacks | `scn_3d67b224edb14c737f1d1e47` | 3 | 657 |
| Absorbed donors | `scn_861aeaab434648ebcb527a0b` | 3 | 45 |
| Direct removals | `scn_d8e51d795e7ea8e6ad54aca2` | 4 | 2,196 |
| Cascade POI removals | `scn_9d22d885fc61fb64a01f9c50` | 10 | 1,865 |
| Geometry perturbations | `scn_6df9bdc205ef054db5eac21f` | 8 | 4,009 |
| Attribute perturbations | `scn_d8e51d795e7ea8e6ad54aca2` | 15 | 14,630 |
| LC changed cells | `scn_000c176a31e77df2d447faa2` | 0 | 3,500 |
| Median activity | `scn_10f3017200a57d5ca71598b9` | 11 | 5,287 |

DEM provenance exposes changed-cell count and selected-case maximum absolute difference. The compact global candidate table does not record per-candidate DEM maximum magnitude, so the preset does not infer that unavailable global ranking field.

## 8. Interactive layout

The offline page has four comparison columns (original, weak, main, strong) and vector, raster, and attribute bands. Global controls select cases, layers, raster variable/mode, provenance, and reset synchronized zoom. Desktop and 390 px mobile layouts were rendered without horizontal page overflow.

## 9. Vector comparison

Canvas panels share the exact EPSG:5186 500 m bounds and 1:1 aspect ratio. Pan/zoom state is shared. Building/road/POI layers are independently visible. Removed entities, absorbed donors, receivers, geometry changes, fallback geometry, and attribute-only changes use color plus line/symbol differences. Hover and entity-to-table filtering were exercised.

## 10. Raster comparison

Native 100 x 100 land-cover and 17 x 17 DEM grids are embedded without resampling. Land cover uses one categorical palette and categorical changed/unchanged/masked difference. DEM uses common actual limits and one symmetric difference limit. Raster hover reports row/column, EPSG:5186 cell center, original value, augmented value, and difference.

## 11. Attribute comparison

Profile summary cards and a searchable, filterable, sortable, paginated detailed table expose recorded changes only. HTML escaping, null/masked distinction, long-value tooltips, map-click filtering, and provenance keys are implemented.

## 12. Provenance display

The drawer includes P3/P4 IDs, scene/view identity, P3/P4 shard IDs, candidate IDs, branch payload checksums, candidate-slice checksums, K8 membership, fallback/absorption summaries, relation counts, attempt histograms, and validation status. Unrecorded scientific values are labeled `Not recorded`.

## 13. Offline/security validation

- External URL/CDN/tile/font/API references: 0
- Absolute server paths in HTML: 0
- Analytics or remote requests: 0
- Embedded payload is JSON encoded with `<` escaped
- Existing output requires `--overwrite`; final replacement is atomic
- Credential/token/path scan: PASS

## 14. Browser interaction validation

Google Chrome via Playwright loaded the HTML directly over `file://`.

- JavaScript console/page errors: 0 after fixing an initially detected constant-name error
- Case selector, vector layer toggles, LC/DEM selector, actual/difference selector: PASS
- Synchronized vector zoom and reset: PASS
- Attribute search/filter/pagination: PASS
- Provenance toggle: PASS
- Canvas pixel nonblank check: PASS
- Desktop 1600 x 1000 and mobile 390 x 844 responsive checks: PASS
- Representative screenshot was retained only in `/tmp`, not Git

## 15. Generated HTML

- Path: `artifacts/augmentation-inspector/p4-augmentation-inspector.html`
- Embedded cases: 8
- Size: 29,268,417 bytes
- SHA-256: `80488530a0def5d36d8a1db3fcfc8f925f302f992d8a45b8024c7ad036698a82`
- Standalone/offline validation: PASS

## 16. Output size/runtime/RSS

- Final generation wall time: 10.16 seconds
- Peak RSS: 1,475,316 KiB
- HTML size: 27.91 MiB
- No geometry simplification, raster downsampling, or external asset fetch was used

## 17. P3/P4 immutability

Post-execution snapshots exactly matched all pre-execution path, size, mtime, and SHA-256 records:

- P3 tar mutations: 0 / 96
- P4 tar mutations: 0 / 288
- P4 logical-index mutations: 0 / 2 files
- P3/P4 manifest modifications: 0

## 18. P5+/maintenance/GPU non-execution

- `tar_make()` calls: 0
- P5+ target executions: 0
- Research target metadata files changed during the work window: 0
- Maintenance metadata files changed during the work window: 0
- GPU targets/work: 0
- Active GPU compute processes at final check: 0

## 19. Tests

- Python compile/AST: PASS
- Inspector focused tests: 12 PASS
- Combined Python suite (inspector, P4, existing Python tests): 109 PASS
- Related R P4 test file: 12 PASS, 0 warnings/skips/failures
- `targets::tar_validate()`: PASS (non-executing)
- Deterministic independent regeneration: byte-identical PASS
- Generated HTML static validation: PASS
- Chromium browser interaction and responsive validation: PASS
- `git diff --check`: PASS

One diagnostic invocation initially used a nonexistent R test filename; the correct tracked P4 test file was then executed successfully. It produced no repository or artifact change.

## 20. Files committed

Only the inspector source, module, README, focused tests, representative HTML, and this report are included. Target stores, P3/P4 data, temporary extractions, screenshots, logs, caches, and credentials are excluded.

## 21. Commit

- Message: `Add P4 augmentation inspector`
- SHA: recorded after commit

## 22. Push verification

Recorded after fast-forward push and fetch verification.

## 23. Recommended next action

`P5 Fixed Validation and Evaluation Queries implementation`

## Input prompt summary

Implement a read-only, on-demand, offline interactive HTML inspector over accepted P3/P4 artifacts; generate and browser-validate an eight-case QC result; prove scientific artifact immutability and non-execution; then commit and push only after all checks pass.
