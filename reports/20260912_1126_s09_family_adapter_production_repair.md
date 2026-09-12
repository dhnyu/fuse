# S09 Family Adapter Production Repair

Created: 2026-09-12 11:26 Asia/Seoul.
Repository: /members/dhnyu/fuse; branch: reduced.
Input HEAD: f727c8c5c498ed5710616f449d3c23cc38740872.
Output implementation HEAD: cc1e8fedeba1f6d6769c6c23cc0f0eebfa506c07.
The subsequent report-only commit records this evidence; its identity is available from `git log -1 --format=%H -- reports/20260912_1126_s09_family_adapter_production_repair.md`.

## Verdict And Scope

**PASS_S09_FAMILY_ADAPTER_PRODUCTION_REPAIRED**

Authoritative design/completion report read completely:
`reports/20260912_1043_s09_family_adapter_component_provenance_completion.md`.
Its GLOBAL_RETRAIN_REQUIRED decision is binding. No selective provenance migration or legacy acceptance receipt was implemented.

Prompt summary: integrate the validated family projection, masking and DS-reader semantics into production modules, preserve immutable preparation and historical evidence, validate CPU/disposable DDP paths, bind a completely fresh campaign to a new global implementation SHA, and commit/push without formal training.

The dissertation's experimental setup (component/source ablations and controlled baselines), training-time masking specification, and current targets blueprint were inspected. Corrected behavior implements the existing intended scientific contract. S08 scientific definitions and checkpoint selection were not edited.

## Preconditions And Historical Preservation

Initial branch reduced, exact input HEAD, clean tracked worktree, and synchronized origin/reduced (0/0) verified. Live remote HEAD was checked. No active formal controller, DDP worker, or GPU compute workload; GPU pair/device locks available.

Before and after implementation:
- All 2,256 protected file SHA-256 values match the authoritative audit baseline, including original authorities/results, winner, ledgers/manifests, cache manifests/acceptance and formal S09 logs.
- All 18 selected original OFAT/comparison checkpoint payload SHA-256 values match their registered baseline.
- No original ledger, checkpoint, authority, winner or formal log was changed.
- Original winner s09winner_57f6e45b2afacbc41542550c remains historical evidence, not the winner of the future campaign.
- Failed B2 p9runv2_a15ca592e0d7233666bd7499 remains unchanged, 0/0 with no checkpoint.

The prior seven comparison closed ledgers are not relabelled as accepted. Neither they nor the original 11 accepted OFAT runs are reused in the new campaign.

## Canonical Family Boundary

`python/training_family_inputs.py` provides the frozen typed `Projection` descriptor and `project_family_sample(sample, FamilyContract)` API. The contract is checked against the canonical family registry.

The sole shared `assemble_family_batch` path is used by training views and full validation query/gallery assembly. It resolves accepted scene centers, projects immutable prepared samples, collates, and selects the corresponding cached Fourier rows. Online and EMA branches receive the same family projection; only the online branch receives modality masking.

Projection records original entity IDs, compact old-to-new row mapping, retained geometry rows, retained edge rows, global-to-local modality mapping, environmental source blocks and scene-raster source metadata. Original local_entity_id is never renumbered and remains the deterministic masking identity.

| Family | Retained entities | Active modalities | Object environment | Scene raster | Relations |
|---|---|---|---|---|---|
| All 11 OFAT / FM | B/R/P | r,g,s,e | LC+DEM | LC+DEM | heterogeneous |
| A1 | B/R/P | r | none | none | none |
| A2 | B/R/P | r,g | none | none | none |
| A3 | B/R/P | r,g,s,e | LC+DEM | none | none |
| A4 | B/R/P | r,g,s,e | LC+DEM | none | generic existing graph |
| A5 | B/R/P | r,g,s,e | LC+DEM | none | heterogeneous |
| B1 | B/R/P | r,g,s | none | none | heterogeneous |
| B2 | B/R | r,g,s | none | none | induced heterogeneous |
| B3 | B/P | r,g,s | none | none | induced heterogeneous |
| B4 | R/P | r,g,s | none | none | induced heterogeneous |
| B5 | B | r,g,s | none | none | induced heterogeneous |
| B6 | R | r,g,s | none | none | induced heterogeneous |
| B7 | P | r,s eligible; g unavailable | none | none | induced heterogeneous |
| B8 | B/R/P | r,g,s,e | LC only | LC only | heterogeneous |
| B9 | B/R/P | r,g,s,e | DEM only | DEM only | heterogeneous |
| SSV | B/R/P | r,s | none | none | none |
| DS | no entity encoder | none | dedicated raster | all-source 26 channels | none |

Geometry is unavailable for P in every entity family. Dense unavailable P Fourier slots are scaffolding, not available geometric information.

## Aligned Geometry, Topology And Graphs

- Entity/type/semantic/numerical/missingness/availability arrays share the exact retained row selection. Unknown aligned fields fail closed.
- Polygon parts/components/rings/owners/offsets rebuild deterministically, preserving retained order. Multipart, holes, roads, empty geometry and ragged multi-scene fixtures are covered.
- Fourier magnitude/phase use the exact original retained row indices, with identity/count/order checks. Incomplete Fourier tuples fail at encoder entry.
- Road chain/node/offset references are filtered and remapped; no dangling road references. Empty roads/chains are valid. Nonempty invalid index dtype fails.
- Graph edges are an ordered subsequence of original FM edges: retain only two surviving endpoints, remap compact indices, preserve direction/multiplicity/relation masks including SN/CNT/WIT/INT/CON. No new edges are constructed.
- Inactive source-specific semantic encoder modules are not instantiated for B2-B7, avoiding unused source parameters at the DDP boundary. Full-source constructor order remains unchanged.
- Model-facing assembly strips inactive carriers and avoids a duplicate Fourier copy. Encoder checks reject forbidden types, inactive availability, invalid local mask indices, environmental/raster source mismatches and invalid relation endpoints. The original B-series excluded-source assertion remains present.

## Masking Correction

Global order is relative/geometry/semantic/environmental. Eligible modalities are prepared availability intersected with the active family. Original entity gate, probability, seed fields and stable IDs are unchanged. Empty eligibility returns -1. A chosen eligible GLOBAL modality is translated exactly once to its family-local replacement index.

Captured B1 epoch1/batch0/rank0 reproduced with actual data:

| View | Retained B/R/P | Environmental assignments before/after | Selected entities before/after | Dense geometry rows |
|---|---|---|---|---|
| 0 | 4159/510/7864 | 1126 / 0 | 3730 / 3730 | 12533 |
| 1 | 4128/509/7849 | 1107 / 0 | 3735 / 3735 | 12486 |

A1 cannot select g/s/e; A2 cannot select s/e. SSV global semantic2 becomes local semantic1; global geometry1 cannot be mistaken for semantics. A1/A2/B1/SSV corrected masked behavior intentionally differs from the legacy implementation. Old B1 canonical acceptance eligibility is not scientific masking equivalence.

## Environmental And DS Contracts

Environment is an explicit source-block mapping: LC23 columns and DEM3 columns where active. Inactive object/scene sources are absent from encoder input. Instrumented CPU dictionary reads verify B8 consumes only LC and B9 only DEM; B9 no longer reads LC before its source condition.

The production DS reader validates acceptance/content/production-manifest hashes, then the exact writer-defined `ds/ds_cache_manifest.json`. It recognizes accepted s09ds identities, not the incorrect p9ds prefix. All DS entry bindings are reconciled with the production manifest; payload lookup checks size/SHA/tensor identity/shape/finite values. No directory scanning or sibling fallback.

Resolved DS cache: s09ds_3a46fc8888a324bd4297feb7.
Training/query/gallery DS assembly and CPU [1,256] forwards PASS. No DS cache rewrite. DS encoder entry rejects entity carriers, assignments, geometry or incorrect raster batch shape.

## Real CPU And Equivalence Results

Final production modules passed 81 entity-model CPU records: all 11 OFAT and 16 entity comparison families, each on an actual training scene and validation query/gallery. DS adds 3 records, for 84 actual forwards. All outputs finite with the configuration's expected d (64/128/256).

- OFAT11, FM/A3/A4/A5: tested masked/unmasked outputs bit-exact to frozen original implementation.
- B8/B9: tested outputs bit-exact while forbidden environmental carriers are physically excluded from encoder inputs.
- A1/A2/B1/SSV: masked output changes observed as intended; tested unmasked validation outputs remain exact.
- B2-B7: actual projected input/forward PASS; no valid old full-source forward exists for equivalence comparison. B2 includes an empty projected scene fixture and nonempty full-epoch coverage.
- Twelve canonical fixed-reference tests cover FM/A3/A4/A5 x d64/128/256 initialization, training-mode dropout output and CPU RNG bytes. Reference source is input HEAD; CPU thread count is explicitly fixed to one for bit-level comparison. An initial unconstrained-thread comparison differed, so the reference execution environment was made explicit, not the equality requirement relaxed.

These are regression proofs, not selective legacy-result reuse authorization.

## Disposable Production-Code DDP Gates

No formal targets/controller lifecycle or checkpoint-publication API was invoked. GPU locks and the canonical NCCL preflight were used, with CUDA_VISIBLE_DEVICES=0,1, P2P_DISABLE=1, IB_DISABLE=1, world2, per-rank16/global32, current DDP options and rank-derived RNG.

Each final scientific-code gate completed a full 76-update epoch and full validation (2,000 queries / 1,000 gallery). All preflight stages PASS: initialization, rank/device, ALLREDUCE, ALLGATHER, DDP construction and clean destruction.

| Metric | main | B2 (historical winning d256 used only as disposable test configuration) |
|---|---:|---:|
| Epoch seconds, rank0 | 145.474 | 80.858 |
| Rank0 mean loss | 6.0247276394 | 5.6767587850 |
| Rank1 mean loss | 6.0606615167 | 5.7007051581 |
| Validation loss | 3.6872527599 | 3.1001446247 |
| Validation margin | 0.0541765541 | 0.1101882681 |
| Validation seconds, rank0 | 44.875 | 28.280 |
| Peak allocated VRAM bytes, rank0/rank1 | 6012821504 / 7539745280 | 5381740544 / 6524926464 |
| Peak RSS KiB, rank0/rank1 | 7107720 / 7169584 | 6775988 / 6774660 |
| Updates / EMA updates | 76 / 76 | 76 / 76 |
| Queue valid/enqueued | 4864 / 4864 | 4864 / 4864 |
| Checkpoint publication | NO | NO |

Both ranks' online/target parameters remain finite. No source assertion, geometry/relation error or transport timeout. There were two qualification passes per family during integration; table values are the final scientific-code pass. The final log-generation-only addition was separately regression/full-suite tested; science/adapter/DS/controller/NCCL code did not change after these final passes.

Main is materially slower than the earlier ~52-53s benchmark. These runs include full projection/contract checks and overlapped CPU validation work; no isolated bottleneck attribution or formal ETA is claimed. B2 is near the prior ~77.3s reference. Correctness gates pass; production timing should be measured anew, not assumed from the old benchmark.

## Runtime Provenance And Fresh Campaign

Old global runtime: 0479d8ae41fb22a4c3c2f82360fa2d12cd0f59fd73d8a50ef0868d2eff1cf66d.
New global runtime: **baf19aa078973c19e19ed55c8ea6ee2f733db9d9b94a33b0c8e03e74fc695c9a**.

The canonical registry now includes family adapter, prepared/DS reader, geometry reader and scene encoder alongside existing runtime sources: 17 whole-file runtime hashes plus the separately registered authority-publication sources. R/Python resolution agrees exactly.

Disposable materialization against current accepted parents produced 11 unique fresh OFAT authorities, all distinct from historical IDs/runs. A synthetic winner fixture produced 17 distinct comparison authorities; this is not a production winner or acceptance.

Expected fresh main:
- authority: s09auth_4d2bb6e9c91c5e716897a7c9
- run: p9runv2_dd31b0e48cfb912868895c3b

No old checkpoint may warm-start these new run identities. Existing scientific run-key/ledger/checkpoint/resume primitives remain intact.

Additional necessary fresh-campaign fixes:
- Winner path is plan ID / runtime SHA / ofat_winner.json. It cannot collide with the old plan-only immutable winner path.
- Winner, comparison publication and campaign acceptance validate results against deterministically recomputed current authority IDs. Historical rows are rejected even if config/model names match.
- Winner and final campaign targets explicitly depend on runtime provenance.
- A future append-only CAMPAIGN_GENERATION_STARTED event separates completion counts/winner display by runtime. Same-runtime resume does not reset progress; existing formal history is never truncated. No such event was written to production during this task.

## S08, Cache And Currentness

S08 fresh in-memory rebuild/validation is recursively equal to the accepted artifact:
- plan: s08plan_7cd58ffb65db3d43fd3fa234
- content SHA: 7cd58ffb65db3d43fd3fa234fb5c6b7489640ea7e1e2a1bda76082f3ac3e81e3
- serialized SHA unchanged: 74ae70958b96dd663d300c6f7441a0653b1a7c5066d6e1bfe9b4b459d7781789
- 11 OFAT / 17 comparisons, lineage, inherited science and selection unchanged.

Cache: s09cache_dc4e9e271e40ffe8ae17967c.
Acceptance: s09ca_e2a1882eb206e1b5c930ddd5.
Recomputed cache identity from current lineage, canonical membership and unchanged builder script SHA resolves to that existing directory. All 80,472 prepared files exist with registered sizes. Acceptance/manifest hashes validate; checksum-valid actual samples were read. No fresh full 296GiB payload rehash was performed. Metadata/identity/inventory check took ~26.8s.

The builder's existing-directory branch validates and returns its immutable acceptance before creating staging or calling payload generation. Source changes may cause lightweight target reevaluation; no physical rebuild is required. `scripts/prepare_training_cache.py`, preparation payload semantics and cached Fourier/DS contents were not changed.

Read-only currentness:
- Main: 61 targets / 212 edges, manifest/validate PASS, outdated empty, including after implementation commit.
- Training: 29 targets / 80 edges, acyclic, manifest/validate PASS.
- Training current targets: s09_training_contract and s09_current_experiment_plan.
- All other 27 training stems outdated/pending, including cache source/acceptance validation, runtime provenance, resolved contract and the complete fresh authority/lifecycle/winner/comparison chain. Existing cache will be validated/reused, not regenerated.
- Historical error metadata remains. Training network displays 1 error, 26 other outdated, 2 current; the live outdated set includes the error target. Renderer validation now correctly accounts for this display precedence without editing store metadata.

Main and dedicated training network HTML were regenerated and match their manifests. A training phase-map configuration supports the separate graph.

## Validation And Files

PASS:
- `git diff --check` / staged diff check.
- `python -m compileall -q python scripts tests/python`.
- R parse of changed helpers/targets/tests/renderer and root entrypoints.
- JSON/YAML parse (64 config JSON, 34 config YAML; new fixture and phase map also parsed).
- Full `python -m pytest -q`: **570 passed**, 93.08s final release run.
- Full `Rscript tests/testthat.R`: PASS, no failures/warnings/skips reported in final release log.
- Focused runtime/currentness, lifecycle/resume, family/source/masking, DS corruption/binding, log generation, S08 isolation and network tests.
- Actual 84 CPU forwards, captured B1 two-view regression, canonical bit-level references.
- Main/B2 disposable DDP epoch + full validation.
- Main/training manifest, validate, DAG and read-only currentness.
- Historical preservation after-check and final GPU lock/no-worker checks.

Production changes:
`python/training_family_inputs.py`, `model_families.py`, `training_worker.py`, `training_prepared_cache.py`, `training_campaign.py`, `training_progress.py`; `scripts/training_campaign.py`; runtime registry; `R/training_targets.R`; `targets/s09_training.R`.
Supporting changes: canonical tests/reference fixture, blueprint, training phase map, network renderer error/outdated validation and generated main/training HTML.
No S08 scientific config, cache builder, model kernel, optimizer/scheduler/EMA/queue/loss/selection definition, GPU transport settings or batch/seed policy was changed.

Evidence workspace:
`/tmp/fuse_family_production_20260912_1059/`
Key files: forward_results.json, ds_results.json, b1_results.json, final_main_ddp_rank0/1.json, final_B2_ddp_rank0/1.json, final_*_nccl_preflight.json, final_*_ddp.stdout/stderr/exit, identity_results.json, preservation_results.json, python_tests_release.log, r_tests_release.log. All disposable outputs remain separate from formal logs/artifacts.

## Git And Next Boundary

Implementation commit cc1e8fedeba1f6d6769c6c23cc0f0eebfa506c07 pushed to origin/reduced: PASS. Worktree clean and ahead/behind0/0 verified after that push. This report is recorded in a subsequent report-only commit; final remote equality is checked after its push and reported to the operator.

Formal campaign executed = NO.
Production checkpoint/results/authorities/acceptance published = NO.
Prepared cache rebuilt = NO.
Target-store metadata manually edited = NO.
Historical evidence mutations = ZERO.
S10/evaluation/downstream/maintenance executed = NO.

The next separately authorized action is a completely fresh guarded S09 campaign:
**fresh OFAT main epoch0 -> 11 fresh OFAT -> new winner -> all17 fresh comparisons epoch0 -> campaign acceptance**.
Use the existing immutable cache. Do not resume B2, import old checkpoints, reuse old comparison results, or assume ofat_d_256 wins again. No formal training was started by this repair.
