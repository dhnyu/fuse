# B6 Stage B method selection and preparation

Created 2026-10-02 16:47 Asia/Seoul. Input commit: `302293b14a9b8bd3bb84550d982420f3f631dea9`, branch `B6`, upstream `origin/B6`, entry ahead/behind 0/0 and clean. This exact report filename was explicitly requested. Final commit is the commit containing this report.

## Scope and decision

**NEEDS_METHOD_DECISION. GPU pilot deferred by the user.** The request was to prepare the fixed Original/S50-G/S50-Ppre block, validate post-bank ownership and Original parity, then test bounded training updates only after all input gates pass. Upon discovering an unresolved accepted CON-to-child mapping, the user explicitly directed: “방법론 gate로 남기고 GPU pilot 보류; lineage·Original parity·계약 준비는 계속”. This report covers that amended scope. No formal or bounded training update was executed.

The dissertation methodology and `blueprint/targets_implementation_blueprint.md` were inspected read-only. Accepted B6 authority, rather than the base model defaults, supplies d=d_c=256. No canonical methodology was changed. Source provenance is frozen in the method contract; experimental authority issuance remains disabled.

## Frozen three-arm comparison

Exactly `B6-original`, `B6-S50-G`, `B6-S50-Ppre`; no S25/S100/P-post training arm. Segmentation concerns independent entities, not vertex densification. The scientific interpretation concerns road-containing scenes, not exceeding the empty-scene HIT@1 ceiling.

Accepted authority: `s09auth_478c450cdf0e9fa4921ef485`, under `/mnt/hdd002/dhnyu/fusedata/models/reduced/training/authorities/`. `python/training_configuration.py::materialize_hyperparameter_configuration` resolves accepted `cmp_B6` once, then the three arms share those settings. `python/b6_stage_b_preparation.py::contract` binds authority SHA256, configuration, implementation hashes and Stage A acceptance.

| Setting | Frozen value |
|---|---|
| d / d_c / heads / relation layers / dropout | 256 / 256 / 4 / 3 / 0.2 |
| K_aug / intensity | 8 / 1.0 |
| Root seed / experimental seed group | 1629790839 / b6-postbank-paired-v1 |
| Global batch / world size / per-rank batch | 32 / 2 / 16 |
| EMA / queue / temperature | 0.999 / 8192 / 0.1 |
| Peak LR / max epochs | 0.001 / 200 |
| Negative exclusion / modality masking | 750 m / 0.30 |
| Optimizer | AdamW; accepted weight decay, betas, epsilon and clipping unchanged |
| Schedule / objective | Accepted warmup/cosine schedule and contrastive objective unchanged |

Full resolved model/training values are recorded in the external contract. Canonical publication/staging destinations are removed from this non-executable scientific snapshot. The accepted selection implementation overrides the legacy YAML `patience_reset: selected_best_event`: reset requires a retrieval-loss decrease at least equal to tolerance. This discrepancy is documented, not silently adopted from base YAML.

## Post-bank order and ownership

Accepted P3 scene-clipped observed parents → accepted P4/P5 materialized receiver geometry and attributes → verified source-part ownership → future S50 subdivision → future full-source graph reconstruction → induced B6 road-only projection → model-ready input. No national network alteration or new augmentation bank is involved.

`python/b6_postbank_adapter.py::resolve_receiver` expands each P3 LineString/MultiLineString before mapping absorption. The accepted absorption ledger identifies receiver and donors; canonical donor ordering is reproduced. A receiver can own parts from multiple source parents. Recorded accepted jitter seed or simplification tolerance, protected source-node coordinates and scene bounds reconstruct the accepted transformation for verification. Exact complete WKB equality certifies correspondence; missing or mismatched provenance fails closed. This verification does not resample donor/removal choices, attempts or query identities. Output part ordinal alone is never sufficient evidence of ownership.

Every returned part carries original source ID/local ID/part index/hash, receiver ID, donor/receiver role, materialized geometry hash, source-chain node coordinates/position, on-support and off-part node lists, and receiver semantics/missingness. `receiver_semantics` preserves accepted receiver ROAD_RANK/ROAD_TYPE/LANES including overrides and masks; absorbed donors do not replace these values. Synthetic part boundaries are explicitly not original nodes. The adapter is isolated; canonical augmentation code is untouched.

**Ownership verdict: POST_BANK_FEASIBLE with the new lineage adapter for the audited population; complete segmented training input remains method-gated.** This distinguishes resolved component ownership from unresolved logical connectivity.

## Accepted CON gate

Stage B preserves accepted P4/P5 connectivity semantics for paired comparability, including existing accepted outside-node behavior. Original uses stored accepted relation masks; it does not impose P2 visibility rules or reconstruct relations with Stage A rules.

Concrete accepted counterexample: view `augv_2bf305fd65d508a89be664e8`, scene `scn_997807ff7272323d5174a1e6`, shared source node `1020026002`. Road local262 has length 8.15089020574085 m and node distance 182.39288308486542 m; local267 has length 274.1907167532005 m and node distance 183.68858839905485 m. Accepted CON exists although the original node is outside the observed support. No physical S50 child can touch that node. Dropping CON, broadcasting it to every child, or selecting an arbitrary child each changes scientific semantics.

`require_physical_node_lift` fails closed in this case. No logical child-incidence rule has been selected. The census field `outside_con_node_pair_rows` counts off-support shared-source-node CON ADD rows; it is **not** a count of unique nodes, all final CON pairs, or exclusively nodes outside scene bounds. This diagnostic must not be interpreted more broadly.

## Original parity and population

`original_adapter` applies the canonical `training_family_inputs.project(..., 'B6')` to an unmodified copy of the accepted prepared sample. `parity_chunk` verifies each accepted payload SHA256, compares all projected tensor bytes/dtypes/shapes and metadata, checks road order/local IDs, geometry offsets/coordinates, semantics, availability and relation endpoints/masks, and confirms the source sample is unchanged.

This is exact accepted prepared-control pass-through parity, **not independent raw raster/materialization reconstruction**. It is appropriate for the control because the control reuses those accepted payloads. S50 adapter parity is not claimed.

The deterministic initial sample contains 256 training views from Stage A's 32 scenes plus 64 queries and 32 galleries from hash-selected validation scenes. Expansion to the full inventory is conditional on sample parity, measured projected CPU cost ≤900 seconds and per-process RSS <8 GiB. The inventory is exactly 19,368 training K8 entries + 2,000 fixed validation queries + 1,000 original galleries = **22,368**. Membership is checked against accepted P4 K8 and P5 identities. Evaluation, other augmentation intensities, K>8 and DS-only entries are excluded from the historical 80,472-entry cache.

## Relations and RNG

The future S50 full-source graph contract retains B/P entities and top-k competition before B6 projection. G uses minimum geometry distance ≤100 m, top-16, distance quantization 1e-9 m, destination local-ID ties and either-direction symmetry, following Stage A. P-pre excludes same-original-source-parent road candidates before top-k. Donors from different original sources remain different parents even after absorption into one semantic receiver. Sibling INT remains; synthetic cuts never create CON. Original retains accepted P4 float-distance-selected edges unchanged: the S50 quantized rule is explicit, not silently substituted into control parity.

Stage A `R/b6_road_relations.R::b6_graph` / `b6_repolicy` remain the validated structural policy implementation. No post-bank S50 production graph is published while CON is unresolved. P-post remains a structural diagnostic only.

`shared_training_config` preserves the accepted root seed. Arm names are not passed back through configuration-name seed derivation. `child_rng_identity` binds scene, accepted view, original source parent, part and exact child chainages; G/Ppre policy labels are excluded. `paired_modality_assignments` supplies these RNG identities to canonical masking without mutating graph IDs; Original uses canonical IDs unchanged. Root-seed/rename and paired-policy masking fixtures pass. This wrapper is not yet connected to an authorized training runner. Accepted epoch/scene/view ordering is the required future contract, not a measured training execution result.

## Cache and publication contracts

Accepted prepared parent: `s09cache_dc4e9e271e40ffe8ae17967c`, under `/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/prepared_cache/`. Inventory entries bind parent prepared SHA256 and existing Fourier record references. Original may reuse these references without relabeling historical authority. No full historical cache is copied.

Experimental root: `/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b/<design_id>/`; independent store `/mnt/hdd002/dhnyu/fusedata/targets/fuse-b6-road-granularity-stage-b`. Products: `contract/method_contract.json`, `inventory/inventory.json`, `inventory/cache_contract.json`, `lineage/lineage_audit.json`, `lineage/pilot_resource.json`, `parity/original_parity.json`, `readiness/readiness.json`, each with checksummed manifest. Publication uses staging, validation and atomic rename; existing products require checksum readback. Earlier incomplete development identities are not accepted readiness products.

Model-ready identities bind method, arm and inventory. Future prepared identities additionally bind tensor schema/content; Fourier identities bind child geometry, entity order, normalization 500 m, accepted 128-frequency/384-feature specification, implementation and parent hashes. Existing encoder and frequencies are unchanged. **S50 model-ready and Fourier payloads are NOT_GENERATED; experimental training authority is NOT_ISSUED.** Recipes alone do not constitute completed cache acceptance.

## Validation and future interpretation

Future validation remains the accepted 2,000 queries / 1,000 original gallery, normalized embeddings and cosine similarity, retrieval loss, margin, MRR and HIT@1/5/10. `training_finalization.selection_contract_content` binds minimum loss, strict absolute difference <1e-4 equivalence, greater margin then earlier epoch, four-event patience and accepted reset semantics. Road-stratified metrics cannot select checkpoints.

Predeclared analyses: whole validation; road-nonempty; original road-count 1–8/9–49/50+; original observed parent-length strata; zero-road queries. Parent-length bins use scene mean original-parent length with boundaries 0/50/100/250/500/infinity, empty separate. External descriptors remain road_density, road_orientation_dispersion, mean_road_segment_length, road_location_dispersion, road_type_composition, road_hierarchy_composition, relation_composition and mean_relational_degree, all derived from original parents. Synthetic split nodes are never intersections; mechanical child-count increase is not improved representation alignment.

Stage A's read-only coverage remains 338/2,421 training, 144/1,000 validation and 1,261/9,000 evaluation scenes without roads. The inferred 85.70% whole-validation HIT@1 ceiling and reported accepted 85.65% remain authoritative. This task does not repeat checkpoint inference or independently remeasure validation tied ranks. Empty representations are not altered.

## Implementation and checks

New isolated modules: `python/b6_postbank_adapter.py`, `python/b6_stage_b_preparation.py`, `R/b6_stage_b_preparation.R`; config/schema under `config/`; `_targets_b6_stage_b_preparation.R` and `targets/b6_stage_b_preparation.R`; focused Python/R tests; separate network phase mapping and generated HTML. Six CPU targets cover source hashes, method, inventory, lineage, Original parity and gated readiness. No full-training, early-stopping, checkpoint-selection or GPU target is reachable.

The canonical reader/augmentation/family/configuration modules are dependencies, not modified files. Source checksums are included in content identity and target invalidation. Detailed measurements and final validation receipts follow below.

## Measured results and resources

Final design ID: **`b6b_d5d52fa75ab30db61957a391`**. Parent Stage A design: `b6a_f5d6a32cdd09cf5688b0666a`.

| Gate / measurement | Result |
|---|---:|
| Accepted augmented views inspected | 21,368 |
| Materialized receiver roads / geometry parts | 660,010 / 693,292 |
| Multipart receivers / absorbed receivers | 32,115 / 30,329 |
| Original gallery scenes / original gallery parts | 1,000 / 31,942 |
| Ambiguous components | **0** |
| Zero-road augmented views unchanged | 2,992 |
| Off-support shared-node CON ADD node/pair rows | 49,044 |
| Original exact prepared/projection parity | **22,368 / 22,368 PASS** |
| Minimal inventory entries per future arm | 22,368 |

One-process lineage pilot: 2.460 s, peak RSS 1,165,942,784 bytes. After that pilot, eight processes with one thread each inspected the census. Across 96 branch jobs, elapsed time p50/p95/max = **3.528 / 5.010 / 5.241 s**; per-process peak RSS p50/p95/max = **1,628,536,832 / 1,754,337,280 / 1,808,166,912 bytes**. The latter is a per-process high-water mark, not aggregate simultaneous host RSS. No need to expand to the authorized maximum of 40 workers was demonstrated.

Final target wall times: method 1.7 s, inventory 4.5 s, lineage 53.5 s, Original parity 29.0 s, readiness 1.7 s; total graph 91.7 s. These are warm filesystem-cache observations after development readbacks, not cold-start forecasts. Original parity pilot 2.310 s; summed worker seconds 176.349; peak per-process RSS 739,409,920 bytes. The inventory is about 45.82 MB and the parity receipts about 7.71 MB, stored externally. Only compact source/config/test/report/network files enter Git.

| Training-cost field | Original | S50-G | S50-Ppre |
|---|---|---|---|
| Bounded updates / timing / forward / backward | Not executed | Not executed | Not executed |
| Peak allocated/reserved VRAM | Not measured | Not measured | Not measured |
| Queue/EMA/finite gradient/loss checks | Not exercised | Not exercised | Not exercised |
| Batch/world size | Contract 32/2 | Contract 32/2 | Contract 32/2 |
| Actual resource equivalence / S50 multiplier | Not established | Not established | Not established |

No training wall-time extrapolation is made. Batch size was not reduced and gradient accumulation was not substituted. The two-GPU pilot remains required after method and S50 cache gates close.

## Final validation and handoff

Python syntax, R parse, frozen YAML/JSON schema, 87 focused Python tests (including canonical augmentation/RNG/configuration/family regressions), six focused Stage B R expectations, target manifest/network DAG acyclicity and dedicated `tar_validate` passed. Dedicated six-target execution passed. A repeated `tar_make` skipped all six valid targets; all seven published payload checksums remained identical. This proves immutable reuse, not independent GPU/training reproducibility. The regenerated network HTML contains six targets/six edges, all up to date, no errors. Stage A structural regression and final preservation checks are recorded with the commit validation.

Development checks exposed a query inventory key mismatch and a projection API tuple handling error in the new checker; both were corrected before the accepted run. Neither is reported as scientific tensor mismatch. No unresolved validation failure remains in the amended CPU preparation scope. S50 post-bank relation/Fourier and training tests are explicitly unexecuted because their prerequisite methodology is undecided.

**Final verdict: NEEDS_METHOD_DECISION.** Required next step is an explicit accepted-CON child-incidence policy for off-support source nodes. Then implement and validate S50-G/Ppre post-bank relations, publish their model-ready/prepared/Fourier payloads, integrate the shared seed adapter, and run the separately gated two-GPU bounded update pilot with global batch 32/world size 2. The minimum future block remains Original/S50-G/S50-Ppre, with L=50 m inherited from Stage A; this is not training authorization or evidence of better retrieval.

Full training executed = NO; bounded optimizer updates = NO; formal checkpoints created = NO; canonical S09 campaign executed = NO; canonical artifacts modified = NO; dissertation modified = NO; reduced modified = NO. The B6 worktree contains only this task's changes.

Final preservation receipt: Stage A structural regression passed 64 expectations (70 R expectations including Stage B); all 352 Stage A manifest payload references retained their SHA256. `reduced` remained `851efd0c94120ff250f34502fceba73a45080281`. Dissertation HEAD remained `6a43d30133db01a773f6b5d355fc1290b544072b`, clean. Accepted prepared/P3/P4/P5 payloads were accessed read-only and verified against their parent checksums; none were published or rewritten by this graph. `git diff --check` passed. No generated cache, store, log or checkpoint is included in the commit.
