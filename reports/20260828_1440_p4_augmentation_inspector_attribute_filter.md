# P4 Augmentation Inspector Attribute Filter

## 1. VERDICT

`P4_AUGMENTATION_INSPECTOR_FILTER_PASS_PUSHED`

## 2. Repository state

- Repository: `/members/dhnyu/fuse`
- Branch: `reduced`
- Starting HEAD: `d75af6f136e9481b98742b63c860b4a0a09cb464`
- Starting divergence: ahead 0 / behind 0
- Starting working tree: clean
- Dissertation: `reduced`, clean
- Existing HTML: 29,268,417 bytes, SHA-256 `80488530a0def5d36d8a1db3fcfc8f925f302f992d8a45b8024c7ad036698a82`

## 3. Scope

This change improves only the standalone inspector's attribute-filter design and interaction. It does not modify `_targets.R`, scientific P0-P4 code/config/schema, accepted P3/P4 artifacts, blueprint methodology, maintenance code, or P5+.

## 4. UI changes

The toolbar now follows this desktop order: Profile, Entity type, Operation, Attribute, Search entity ID or value, Changed only, Reset filters. Controls have visible labels, keyboard-native elements, focus outlines, visually distinct disabled state, responsive wrapping, and bounded widths.

## 5. Attribute dropdown behavior

`attributeFilter` is populated solely from the active case's embedded `attribute_name` rows. Names are trimmed, null/blank names are excluded, duplicate names are collapsed, and canonical ascending order is used. Option labels include dependent row counts while option values retain the pure attribute name.

The first case exposes 11 representative attributes:

`A11`, `A9`, `CLASS_L1_CODE`, `CLASS_L2_CODE`, `CLASS_L3_CODE`, `CLASS_L4_CODE`, `CLASS_L5_CODE`, `CLASS_L6_CODE`, `LANES`, `ROAD_RANK`, `ROAD_TYPE`.

## 6. Dependent-filter logic

Option candidates reflect current case, profile, entity type, operation, and changed-only state while excluding the attribute selector's own current value. A vanished selection resets to `All attributes`. Case changes also reset attribute selection. With `main_1.0x -> R -> PERTURB`, the only option is `LANES`; with `main_1.0x -> R -> REPLACE`, the selector is disabled with `No attributes available`.

## 7. Search-scope correction

Search now examines only entity ID, original value, and augmented value. It no longer searches profile, entity type, operation, attribute name, whole-row JSON, or provenance keys that embed attribute names. Matching remains case-insensitive and rendered values remain HTML escaped.

## 8. Empty state and reset behavior

Zero-result filters display `No attribute changes match the current filters.` as an explicit table row. `resetAttributeFilters` restores all dropdowns, clears search, checks changed-only, returns to page one, clears selected entity, and restores profile ascending sort. Filter changes update rows, attribute counts, matching/total counts, active-filter summary, pagination, and button disabled states.

## 9. Generated HTML

- Path: `artifacts/augmentation-inspector/p4-augmentation-inspector.html`
- Size: 29,272,385 bytes
- SHA-256: `84194c8a9a15af4e0ffee8709829f8a9f26afc67774975292c16ba9b61caeb93`
- Embedded cases: 8
- P3 cache: `oscache_c89fa07e3d6cb1819a7994a6`
- P4 bank: `augbank_a470cb156612cff12fb316fc`
- P4 logical index: `abi_f9ff792612ca86f486576491`

## 10. Selected case stability

All prior scene/view pairs remained unchanged, in the same order:

1. `scn_3d67b224edb14c737f1d1e47 / 3`
2. `scn_861aeaab434648ebcb527a0b / 3`
3. `scn_d8e51d795e7ea8e6ad54aca2 / 4`
4. `scn_9d22d885fc61fb64a01f9c50 / 10`
5. `scn_6df9bdc205ef054db5eac21f / 8`
6. `scn_d8e51d795e7ea8e6ad54aca2 / 15`
7. `scn_000c176a31e77df2d447faa2 / 0`
8. `scn_10f3017200a57d5ca71598b9 / 11`

## 11. Chromium validation

Playwright opened the file directly using `file://` in Google Chrome.

- Default `All attributes`: PASS
- Profile/entity/operation/changed-only dependent option refresh: PASS
- Attribute selection and count-consistent table filtering: PASS
- Attribute disappearance reset: PASS
- Attribute-name exclusion from search: PASS
- Entity-ID/value search: PASS
- Explicit empty state: PASS
- Reset filters and page reset: PASS
- Case-change attribute reset: PASS
- Matching/total/page indicators: PASS
- Vector layers, synchronized zoom/reset, LC/DEM, actual/difference, provenance, case selector: PASS
- Console/page errors: 0
- Desktop 1600 x 1000: PASS
- Mobile 390 x 844, horizontal overflow 0: PASS

## 12. Deterministic generation

Two consecutive `qc-extremes --max-cases 8` generations were byte-identical with the SHA-256 above. Scientific embedded data and selected case identities were unchanged.

## 13. P3/P4 immutability

- P3 shard mutations: 0 / 96
- P4 shard mutations: 0 / 288
- P4 logical-index mutations: 0 / 2 files
- Research target metadata path/size/mtime/checksum changes: 0
- Master bank and logical K8 identities: unchanged

## 14. P5+/maintenance/GPU non-execution

- `tar_make()` calls: 0
- P5+ executions: 0
- Maintenance executions/metadata changes: 0
- GPU target/work/processes: 0

## 15. Tests

- Python compile/AST: PASS
- Focused inspector tests: 14 PASS
- Combined Python tests: 111 PASS
- Related R P4 tests: 12 PASS, 0 failures/warnings/skips
- HTML static validation: PASS
- Chromium desktop/mobile interaction validation: PASS
- Deterministic regeneration: PASS
- `targets::tar_validate()`: PASS, non-executing
- Secret/absolute-path/external-URL scan: PASS
- `git diff --check`: PASS

## 16. Files changed

- `tools/render_augmentation_inspector.py`
- `tools/augmentation_inspector/inspector.py`
- `tools/README_augmentation_inspector.md`
- `tests/test_augmentation_inspector.py`
- `artifacts/augmentation-inspector/p4-augmentation-inspector.html`
- This report

No scientific payload, target store, extracted shard, screenshot, browser cache, log, or temporary file is included.

## 17. Commit

- Message: `Improve augmentation attribute filters`
- Implementation SHA: `e38781a4d9e965b474d2345cd2f96ee462b46f3b`
- Committed files: the inspector renderer and module, focused tests, README, regenerated representative HTML, and this report
- Staged diff review and `git diff --cached --check`: PASS

## 18. Push verification

- Normal push to `origin/reduced`: PASS
- Post-push fetch: PASS
- Local `reduced`: `e38781a4d9e965b474d2345cd2f96ee462b46f3b`
- `origin/reduced`: `e38781a4d9e965b474d2345cd2f96ee462b46f3b`
- Ahead/behind: `0/0`
- Fuse and dissertation working trees after implementation push: clean

## 19. Recommended next action

`P5 Fixed Validation and Evaluation Queries implementation`

## Input prompt summary

Add a dependent attribute-name dropdown, narrow free-text search to entity IDs and values, provide explicit empty/reset/count states, regenerate the same accepted eight-case HTML, validate interactions and immutability, and commit/push only after all checks pass.
