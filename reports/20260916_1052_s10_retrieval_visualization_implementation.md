# S10 Retrieval Visualization implementation and S11 migration

## FINAL STATUS

**PASS — authorized implementation/static/tiny-smoke scope.** Full formal S10 inference was not run. **S11 remains BLOCKED by design**, pending separately authorized scientific-lineage/schema/lifecycle repair. This is not a claim of a formal 28-model S10 production acceptance.

Created 2026-09-16T10:52:49.318727+09:00 (Asia/Seoul). Purpose: implement the user's approved disposition of the audit block: independently construct S10 from canonical S09, move former S10 evaluation to S11 without repairing or adopting its stale evidence, validate a noncanonical pilot, then commit/push on reduced. Prompt summary: exact 28 accepted models, fixed explicit-seed 30 queries / common 9,000 originals, deterministic standard and non-local Top 50, artifact-only viewer, no selection/training/S11/full production execution.

## REPOSITORY STATE

- Repository `/members/dhnyu/fuse`, branch `reduced`.
- Input HEAD `818250d9fc5196617416cce584e15d8c629e1920`; initial worktree clean.
- Fresh `git fetch origin reduced` before publication succeeded; input divergence 0 ahead / 0 behind.
- Only task source/config/tests/docs and this report are intended for commit. The final commit SHA and push result are reported in the completion message; no self-referential commit hash is embedded here.
- Dissertation/blueprint scientific authority remains the reduced branch authority audited earlier. No dissertation or accepted methodology artifact was changed.

## S11 NUMBER-ONLY MIGRATION AND BLOCKED STATE

- `targets/s10_evaluation.R` moved to `targets/s11_evaluation.R`; the five target identities, list names and entrypoint references moved to s11.
- R/Python P10 execution functions, classes, errors, artifact prefixes and future p10 paths moved to p11. The current evaluation checkpoint consumer is explicitly `resolve_s11_checkpoint` / `s11_evaluation`; the historical downstream p11 helper was not repurposed.
- Scientific query seed preimage is frozen as `qualitative.scientific_seed_preimage_version: p10-qualitative-query-v1`. A regression test reconstructs the old seed bytes and confirms identical 10 selected query IDs after namespace migration. S10's 30-query contract does not replace this protocol.
- Config input paths, model acceptance placeholders, accepted-evaluation placeholders, validation tolerances, execution policy and historical interrupted-evidence fields are unchanged. Historical artifacts, reports, logs and paths were not renamed.
- The schema still requires `PENDING_RECOMPUTATION` / `RECOMPUTE_REQUIRED`; evaluation runtime rejects this state. The runtime's required bundle_record remains forbidden by the existing model-entry schema. Existing P3/P5/preprocessing lineage is not rebound to S09.
- Operational fail-closed checks now also stop input/geometry preparation before reading/adopting stale sources. This is a refusal guard, not a lineage or protocol repair. A test proves these guards run before catalog/cache access.
- Historical reexecute evidence cannot be silently adopted. S11 was not executed.
- Stale executable s10_evaluation/P10 naming is absent from the migrated execution surfaces. Intentional historical exceptions: frozen seed preimage; historical_lineage config/schema; immutable reports/artifacts; the existing accepted P0 `R/methodology_authority.R` downstream_scope_mapping (left untouched to preserve scientific authority); legacy graph-label patterns. Negative regression tests also name retired targets deliberately.

## S10 LINEAGE ARCHITECTURE

Canonical campaign `s09camp_d2f6749da19ad6aa56c2d303` is pinned by exact file SHA-256. Status PASS, training_runs 28, evaluation_runs 0. Runtime `d244e40a910e559cf2ac333609e3730bf19b368c7ea71ee31cb123eb138d0ac5`, S08 plan `s08plan_7cd58ffb65db3d43fd3fa234`, prepared-cache acceptance `s09ca_e2a1882eb206e1b5c930ddd5`.

Resolution follows campaign -> winner.candidate_results / comparison result references -> native acceptance handoff -> committed acceptance / finalization / run bundle -> exact selected payload locator. It reuses training_acceptance.resolve_accepted_checkpoint, including the native commit/bundle checks and payload hashes. Campaign and winner identities are checked against their own preimages. The current S09 registered runtime must match. No config-name checkpoint guessing, historical embedding adoption or stale evaluation lifecycle imports are used.

Input roots come from the pinned S09 training controller and are cross-checked against accepted authority parents. P1/P6/P3 acceptance supplies the evaluation pool and EPSG:5186 centers. Preprocessing is the current training-fit ppc_603236bfd673bda81a56d7c3, original cache oscache_75a543f656ab777aada74fbd. Source pins bind config, category, preprocessing, P3 acceptance and index bytes. Formal final acceptance rereads canonical population and compares the complete gallery rows and source identity.

The source dependency target binds the local S10 import closure and excludes evaluation.py/evaluation_inputs.py. A separate parent-file target tracks accepted metadata, bundles, source pins and exact selected checkpoint payloads. The S09 training graph is never an execution ancestor.

### Exact accepted model inventory

This table is read from the canonical campaign lineage, not inferred from filenames. Native validation and payload checks passed for all 28. Ranking model_id uses configuration identity so the 11 OFAT FM-family rows remain distinct; the viewer displays comparison family labels.

| Group | Configuration | Family | Checkpoint | Acceptance | Payload SHA-256 |
|---|---|---|---|---|---|
| OFAT | main | FM | `p9ck_497f5c2a25fad3da3d66a2cb` | `p9accv2_70134ebaef5303965040cd49` | `ff2711306b071c55b5dad01dc654e5079de19ece8ba7fa4001f8b66b9dd79248` |
| OFAT | ofat_d_64 | FM | `p9ck_240fb65da3942957b18e0daa` | `p9accv2_4004ea54ba29bb1e06b98ee9` | `8dec75ed88831219b1ad9e4cd78f654f611f8aef442683540fa11aab2d05ac28` |
| OFAT | ofat_d_256 | FM | `p9ck_e246c0af46ffa5b3393258fe` | `p9accv2_511001063403ccf4477703f0` | `3e94d954b8a0a0578716976f98c4eb5466c289a0118ec3b40ac9824a0a771f1b` |
| OFAT | ofat_K_aug_4 | FM | `p9ck_a3c9539eb3cbb8f71411fc79` | `p9accv2_1e6d333c96351fc3c07a1a61` | `3ac8209fa7908c5ae9eee90ef8c1d7545ef6766b97107d3e450d3982d65ebfd6` |
| OFAT | ofat_K_aug_16 | FM | `p9ck_b28905e7b510847ae2d1081c` | `p9accv2_97ad6918e133090c4d996e5c` | `b2f71f0ae539c41dd457b967a7b3fcc5658e7569c3169ca3a9dc98d3bd752509` |
| OFAT | ofat_augmentation_intensity_0.5 | FM | `p9ck_4ea2917b7791a7735c868a4c` | `p9accv2_bc27015e92ce8dc850028d8b` | `6a5688bd3120347fbb1e35a5c2fcd87ae05d281426918eabbe169f12e65562e5` |
| OFAT | ofat_augmentation_intensity_2.0 | FM | `p9ck_a814331f4019b990102be657` | `p9accv2_12e232fa14866fd64192f9fa` | `f42693ab7369071347538be8ddd671b33e37ab0090aa99bcd3487316ed992e0c` |
| OFAT | ofat_ema_momentum_0.99 | FM | `p9ck_46ba821d3ae83a3240a9bbea` | `p9accv2_e9398e686de9bfe2c61360d5` | `9d0175606c4aaba777840e678e79ff34df9f958b882659d559a89bf5f8319d86` |
| OFAT | ofat_peak_learning_rate_0.002 | FM | `p9ck_1a31659d4782922c24a71ee3` | `p9accv2_4919f67af1215c17af018b5e` | `52c7fc2fcce3c5125d14ab19e2afe5712bd4266087642b2ae27a102cccf4ae23` |
| OFAT | ofat_peak_learning_rate_0.003 | FM | `p9ck_36c222ba9521993c3d5293c4` | `p9accv2_77d3ea36aaad8451f33cca6c` | `15c9207fa63a681374a26c800b5c8649538e097dcb9f0962184773bb1de7ade1` |
| OFAT | ofat_peak_learning_rate_0.005 | FM | `p9ck_eeefc87dd8814c719c583a99` | `p9accv2_56204d35954481398e749bb0` | `6c4c04fc07b5492ad90d98e16e9f0f06e2ac8b62732d77bd4217953e0d37c187` |
| COMPARISON | cmp_FM | FM | `p9ck_8ff9d205b9ff93e4d985ab06` | `p9accv2_b885ef3b63cf88667d2727bd` | `b4a8e6f224536525679d83c574d5458f4887ed262b5914bcafbf9446304fed22` |
| COMPARISON | cmp_A1 | A1 | `p9ck_904b0a93255d6e458dc81bfa` | `p9accv2_6907dc00e5e9d062ee23d62a` | `8a00f264293ce8a571a4ab909b50ba24a85065d3b2217ec6d8bb8e38b080b54c` |
| COMPARISON | cmp_A2 | A2 | `p9ck_87594fa902e28f77b1ed901f` | `p9accv2_face8fba0d48b0d9c6276ae3` | `2494e3bfad839b3ff022e3e7cf70558fbedb971f17303678df9e780833332ae7` |
| COMPARISON | cmp_A3 | A3 | `p9ck_b682072fd76970b13c2fa29c` | `p9accv2_9a9af1c46fc1f15aef6a6aa9` | `a07e60b1f792acbc355d12183a1dac3b219883ae5914fcf9af4d5b4d98a2f040` |
| COMPARISON | cmp_A4 | A4 | `p9ck_0497f0119f6224d780d32157` | `p9accv2_b57df3c38bbe08d927ba1a6b` | `28df238b89ed74a0e3b389ca62ca661812eb8ec0da1addb446520f8d104b5a1c` |
| COMPARISON | cmp_A5 | A5 | `p9ck_919e8c7b1377499e4ce4e4b5` | `p9accv2_b4a15536526be8223ab60f73` | `06e6fdd7a98db8caa24fdd4bb41d835fb12299351be5e79c2b21e0bc429e4614` |
| COMPARISON | cmp_SSV | SSV | `p9ck_d0bfb874f8556c59d9dee297` | `p9accv2_64e2ed353b8a4361b96804f6` | `f1bb1d2d6d424cb377fb21a193e0a60186dbcb669a0b6a476b8a26971e568040` |
| COMPARISON | cmp_DS | DS | `p9ck_3c1db24ad9e37fe5d44ede16` | `p9accv2_163b248f396b53075399f127` | `8f1033dbe02a1a6dd9d2cda84ad6cb673bfbe8f652bc75d8c9a438dadf2e45ad` |
| COMPARISON | cmp_B1 | B1 | `p9ck_3c17b5a61bcd9d35da31c25f` | `p9accv2_2691558f5e4ebc098a82278a` | `84f7dcb76f13373486aacd35592e3d85fbe5238771846d34229b2c6928b9dc97` |
| COMPARISON | cmp_B2 | B2 | `p9ck_3f3d6638d5f0bf2b5374872c` | `p9accv2_277c132ede877af980735158` | `3d1b83c566ea9713e8f3dfc420d2d2acdbd97f0ddc7d8df1c6451e9376cf0eb4` |
| COMPARISON | cmp_B3 | B3 | `p9ck_209af13ac47ce0e9e62da29a` | `p9accv2_1be3b0761b122f980b905c00` | `30a68f9ae54b85642b3351351e4277033111cc31f430bef174e34ff3c6054417` |
| COMPARISON | cmp_B4 | B4 | `p9ck_5c3a067c89df79942a4e77b1` | `p9accv2_58a0272dff688af41ec070c2` | `c693b98fcd50c8b2879fb74068ba78405177da64d3086db61c1b91759adcfe4e` |
| COMPARISON | cmp_B5 | B5 | `p9ck_8be70fee99b8748eb5f61a44` | `p9accv2_12f609e794926031bd5aae6d` | `8e348bc8567d808a06f1801ce88309f85787360d2b26e1b9d2000b1a0eed6260` |
| COMPARISON | cmp_B6 | B6 | `p9ck_237229722776926808cf862e` | `p9accv2_f654088d89095bc86d64abaf` | `c7657eb5f7ca3f24fa0a61cc7a688f224f3bca149178f45bbb85a6d1338c3e6a` |
| COMPARISON | cmp_B7 | B7 | `p9ck_7b72794a10fd6f4bb4e37f1e` | `p9accv2_29345a2963460db075414900` | `e9530d8641848b7889575714aa2c219f2f870bd6252349e314892c8d3071d5ed` |
| COMPARISON | cmp_B8 | B8 | `p9ck_9441de18c2c03a4c17fbc60a` | `p9accv2_76e3daf5881aed89b7ef2f78` | `49be63a3272f676069df968bc877aa4ae35204267a4a0e0d3f30af7b786ce3dc` |
| COMPARISON | cmp_B9 | B9 | `p9ck_b00bfbc343d74b0d5ae36b16` | `p9accv2_160bab2e02c98ee983198499` | `f32cf794865ccce0f6a50b8e1c479ff9e9cc57d56bbcb7e39a85343d55ae484f` |

## QUERY / GALLERY / INFERENCE / RANKING CONTRACT

- Explicit PCG64 query seed **20260916**, independent of stage names, model metrics and retrieval results. Uniform sampling without replacement from sorted 9,000 evaluation original scene IDs; preserve draw order, exactly 30. Immutable query index/ID/center/split/seed plus source, generation and runtime bindings. Acceptance rejects seed drift inside a generation.
- Common gallery: all 9,000 accepted evaluation originals. Coordinates are verified EPSG:5186 metres; no training or validation candidates. Query itself is excluded.
- Common deterministic original tensors are prepared once in a separate target with pinned preprocessing/category and payload manifests. No augmented scenes or historical prepared evaluation caches are used.
- Each model uses its exact accepted online weights, S09 family/source projection, eval mode, inference_mode, disabled gradients/dropout, explicit seeds, deterministic algorithms and disabled TF32. Optimizer state is not used. CPU threads and numerical/GPU runtime are recorded.
- Cosine similarity over finite unit-normalized scene embeddings; descending similarity with exact scene-ID ascending tie break. Non-local retains distance >= 2000 m; distance is Euclidean between accepted centers. Candidate shortage below 50 fails instead of silently truncating.
- Formal output expectation: 28 × 30 × 2 × 50 = **84,000 rows**. This expectation is enforced in code and has not been produced by this task.

## TARGET GRAPH / RESOURCES / ARTIFACT SCHEMA

Dedicated `_targets_retrieval_visualization.R`, external store `/mnt/hdd002/dhnyu/fusedata/targets/fuse-retrieval-s10`.

15 targets: contract, sources, S09 acceptance, parent files, model manifest, gallery manifest, query manifest, model IDs, original inputs, embeddings, rankings, render cache, comparison pages, summary, final acceptance. Embedding and ranking branches are per accepted configuration. Common original inputs precede all inference branches. No S11, training execution or maintenance target appears in the dependency graph.

One GPU controller worker (controller_gpu_02 role), shared gpu0 lock compatible with S09, and initially one CPU worker (controller_05). Threads=1 and batch_size=1 are explicit. CPU worker count is configurable; the declared CPU worker/thread budget is checked against host capacity. Full input preparation and inference are separately gated by FUSE_S10_FULL_AUTHORIZED; a metadata target make cannot start them.

Fixed generation root `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/<generation_id>/`:

- model_manifest.json, gallery_manifest.json, query_manifest.json.
- original_inputs/<scene_id>.pt and manifest.json (common model-independent tensors).
- embeddings/<configuration_id>/vectors.npy and manifest.json.
- rankings/<configuration_id>/rankings.parquet and manifest.json.
- renders/<scene/render hash>.svg and manifest.json.
- pages/query_01.html … query_30.html, index.html, app.js, style.css, manifest.json.
- summary.json and acceptance.json.

All manifests use a schema-validated versioned envelope with kind, artifact ID, SHA-256, runtime/generation/scope, and payload path/byte-count/SHA records. Schema validation precedes manifest publication. Staged sibling writes use create-or-validate links; differing existing bytes fail rather than overwrite. Every file target returns all verified payload paths plus its manifest.

Parquet columns: model_id (configuration key), model_group, checkpoint_id, query_id, retrieval_mode, rank, gallery_scene_id, similarity, geographic_distance_m, excluded_by_nonlocal, model/query/gallery manifest IDs, runtime_id, generation_id and scope. Additional embedding-distance values are not computed.

Acceptance verifies exact models/queries/gallery, complete common bindings, finite normalized embeddings, ranking recomputation/readback, duplicate/self/non-local/order invariants, complete pages/render files, canonical parent and checkpoint bytes, source/runtime integrity, non-selection guardrails and immutable rerun identity. Noncanonical smoke receives a different artifact kind and cannot satisfy formal count/scope requirements.

## VIEWER ARCHITECTURE

The empty inspector directory now contains a new artifact consumer, not restored historical code. It reads checked manifests and stored Parquet rows and switches presentation only. Missing/corrupt evidence fails; no checkpoint loader, embedding inference, cosine calculation, ranking or distance-filter fallback exists in the viewer. AST/import restrictions are tested.

Each of 30 formal query pages groups 11 OFAT and 17 comparisons in the requested order, with default Top 5 cards and a standard/non-local switch. Captions show rank, scene ID, published cosine score and distance. Mobile cards scroll horizontally; long IDs wrap. Shared scene SVGs are keyed by scene ID, raw scene-payload identity, renderer code and parameter hashes. Scientific ranking identity and render-cache identity are separate.

Initial thumbnails show observed buildings, roads and POIs in a fixed 500 m north-up frame. **Limitation:** this first viewer is vector-only; LC/DEM detail panels are not implemented. It does not claim to visualize every model modality. No raster data or scene data was committed to Git.

## TESTS / VALIDATION

- Changed Python AST, changed R parse and JavaScript syntax: PASS.
- Config and immutable-artifact schemas: PASS, including pending S11 contract validation and prepublication rejection of invalid S10 schemas.
- Python: **180 passed** across test_retrieval_visualization, test_evaluation, test_checkpoint_resolution, test_training_family_projection and test_training_family_encoder.
- Coverage includes deterministic 30-query sampling/duplicate rejection, common manifests, exact 2 km boundary, ties/sort, self exclusion, finite normalization, shortage/Top-k, corrupt ranks/manifests/files, checkpoint resolver and historical rejection, wrong counts/missing models, immutable Parquet rerun, viewer no-recomputation/missing-artifact failure, S11 seed preservation and fail-closed preparation, and no S11 runtime closure.
- R test-retrieval-targets, test-evaluation-targets and test-target-network: PASS. Main, S10 and S11 tar_validate passed; S10/S11 manifests and target-only networks inspected.
- Actual S10 tar_make limited to contract/source/S09 acceptance metadata: 3 completed initially; final source refresh 1 completed / 2 skipped. No model-manifest publication or full preparation/inference target was requested.
- A temporary R two-branch/two-file fixture verified downstream dynamic map preserves per-model file vectors; 5 targets/branches completed and temporary store cleaned.
- All 28 native accepted checkpoint chains verified read-only in the smoke preflight.
- Final real smoke: main and cmp_DS, 2 queries, 6 current evaluation originals, Top 2, **16 rows**. Two inference passes per model produced byte-identical embeddings. Ranking validation, render/page manifests and noncanonical acceptance passed. Chromium verified both modes, visible lazy-loaded images, browser errors absent, mobile navigation; final screenshot was visually inspected.
- Final smoke acceptance: `s10_smoke_acceptance_c8ad4e35eacfe79f4652622b`.
- Final smoke elapsed 226.302 s; common preparation 84.276 s; both inference passes across both models 6.948 s. Temporary `/tmp/fuse-s10-smoke-zlu7v_fr` removed automatically. Review screenshot and task-created ignored bytecode are cleaned after inspection.
- git diff --check passed. No checkpoint/model/source mutation was needed to fix any test.

Intermediate failures were repaired: P3 index has no split column (accepted P1 supplies split); legacy test regex treated every p11 name as downstream; the main phase map was inappropriate for an isolated graph (dedicated phase config added); source edits during an early pilot correctly tripped runtime identity; browser test initially raced hidden lazy images and now awaits visible resources. Final gates above supersede those failed development attempts.

Dependency HTML refreshed and matched current manifests:

- artifacts/targets-network/targets-network.html: 61 main targets, 212 edges.
- artifacts/targets-network/s10/targets-network.html: 15 targets, 44 edges.
- artifacts/targets-network/s11/targets-network.html: 5 targets, 7 edges.

Dedicated graphs use a tested definition-only renderer mode with no target execution/store mutation; all nodes marked outdated mean definitions only, not a failed scientific run. Generated HTML is Git-ignored per repository policy; renderer/configuration sources are committed.

Not run: full 28 × 9,000 S10 preparation/inference, formal 84,000-row production acceptance, S11 evaluation or lineage repair, any S09/training rerun. No full research tar_make was needed for this isolated stage change.

## SCIENTIFIC SAFETY

Training NO; S09 mutation NO; checkpoint mutation NO; full S10 production NO; S11 execution NO; stale/historical embedding adoption NO; model/winner selection NO; hyperparameter retuning NO. B8/B9 receive ordinary comparison treatment. S10 outputs cannot alter the independent S11 query/gallery/protocol.

No formal S10 generation directory had been published at final precommit inspection. Only dedicated S10 metadata-store entries exist outside the repository. Large data, stores, logs, temporary artifacts and credentials are excluded from the commit.

## COST / NEXT AUTHORIZED ACTION

Current small pilot is strongly original-I/O-bound. A naive linear scaling of preparation alone is approximately 35 hours (9,000/6 × 84.276 s); scaling the measured main/DS inference average to 252,000 model-scene inferences is about 20 hours. These are **illustrative extrapolations, not reliable full-campaign estimates**: six scenes/two families do not characterize all scene densities, 28 families, disk traffic, rendering, full verification or GPU memory. Rendering/acceptance overhead adds time. No full-production memory/throughput pilot or worker scaling was performed. The shared original cache removes the much larger cost of retensorizing originals independently for all 28 models.

The command that WOULD run full S10 after separate explicit authorization is:

    Rscript scripts/run_retrieval_visualization.R --authorize-full-inference

Terminal target: s10_retrieval_visualization_acceptance. Expected output: common fixed manifests and original tensors, 28 embedding/ranking partitions, 84,000 Top-50 rows, shared thumbnails, 30 comparison pages, summary and hash-bound acceptance. This command was **not executed**. S11 still requires its separate lineage-repair task; no approval is inferred from this implementation PASS.

## FILES CHANGED

- `R/evaluation_targets.R`
- `R/retrieval_visualization.R`
- `README.md`
- `_targets_evaluation.R`
- `_targets_retrieval_visualization.R`
- `blueprint/targets_implementation_blueprint.md`
- `config/evaluation.yml`
- `config/retrieval_visualization.yml`
- `config/schemas/evaluation.schema.json`
- `config/schemas/retrieval_artifact.schema.json`
- `config/schemas/retrieval_visualization.schema.json`
- `python/checkpoint_resolution.py`
- `python/evaluation.py`
- `python/evaluation_inputs.py`
- `python/retrieval_artifacts.py`
- `python/retrieval_inference.py`
- `python/retrieval_lineage.py`
- `python/retrieval_pipeline.py`
- `python/retrieval_ranking.py`
- `python/retrieval_render.py`
- `scripts/evaluate_scene_encoder.py`
- `scripts/prepare_evaluation_inputs.py`
- `scripts/retrieval_visualization.py`
- `scripts/run_retrieval_visualization.R`
- `scripts/smoke_retrieval_visualization.py`
- `targets/s10_evaluation.R`
- `targets/s10_retrieval_visualization.R`
- `targets/s11_evaluation.R`
- `tests/python/test_checkpoint_resolution.py`
- `tests/python/test_evaluation.py`
- `tests/python/test_retrieval_visualization.py`
- `tests/testthat/test-evaluation-targets.R`
- `tests/testthat/test-retrieval-targets.R`
- `tools/retrieval_inspector/README.md`
- `tools/retrieval_inspector/app.js`
- `tools/retrieval_inspector/style.css`
- `tools/retrieval_inspector/viewer.py`
- `tools/targets-network/render_targets_network.R`
- `tools/targets-network/retrieval_phases.yml`
- `tools/targets-network/target_phases.yml`
- `tools/targets-network/training_phases.yml`
- `reports/20260916_1052_s10_retrieval_visualization_implementation.md` (this report).
