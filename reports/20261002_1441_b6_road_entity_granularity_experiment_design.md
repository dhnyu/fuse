# B6 road-entity granularity: repository audit and experiment design

## Stage A update — 2026-10-02 16:06 KST

**Stage A PASS; READY_FOR_STAGE_B_METHOD_SELECTION.** The historical audit/design below is preserved. The user subsequently authorized isolated implementation in the existing `~/fuse` B6 worktree. Measured results and remaining Stage B gates are recorded in [the Stage A execution report](20261002_1547_b6_stage_a_structural_diagnostic.md) and section 17 below. No training is authorized by this verdict.


Created: 2026-10-02 14:41 Asia/Seoul. Scope: branch setup, read-only implementation/artifact audit, and experiment design. No segmentation, training, campaign, cache publication, or dissertation edits were performed.

**Verdict: NEEDS METHODOLOGY DECISION before training implementation. A separate, optimizer-free structural diagnostic is the recommended next implementation task.** The evidence supports testing granularity, not asserting improvement. The most important competing explanation is missing road coverage: 144 of the 1,000 validation scenes have no roads. Under the current B6 encoder this implies an approximately 85.70% HIT@1 ceiling, extremely close to the dissertation's 85.65% result. Segmentation cannot recover information in those scenes.

## 1. Branch and scientific provenance

The initial attempt stopped on a dirty `reduced` tree, as requested. After the user reported completing their push, the repeated audit found a clean tree and the following state:

| Item | Verified value |
|---|---|
| Scientific-authority repository branch at entry | `reduced` |
| Local reduced HEAD | `851efd0c94120ff250f34502fceba73a45080281` |
| Cached origin/reduced and live remote reduced HEAD | Same SHA |
| Ahead / behind before branching | 0 / 0 |
| Commands executed | `git switch reduced`; `git switch -c B6`; `git push -u origin B6` |
| Result | New local B6 and origin/B6; upstream origin/B6; initial HEAD identical to reduced |
| Implementation audited | B6 at the SHA above |
| Dissertation working tree | Clean `reduced`, HEAD `6a43d30133db01a773f6b5d355fc1290b544072b` |
| Historical methodology pin in blueprint/current_methodology.yml | `cbb824f19be8355296603f8426ac241ce587ddcc` |
| Accepted methodology identity | `mta_2142a2914bc5c43ea8d6e312` |
| Accepted experiment plan | `s08plan_7cd58ffb65db3d43fd3fa234` |
| Accepted S09 campaign | `s09camp_d2f6749da19ad6aa56c2d303`, PASS, 28 training runs, zero evaluation runs |
| Accepted B6 authority | `s09auth_478c450cdf0e9fa4921ef485` |
| Accepted B6 checkpoint | `p9ck_237229722776926808cf862e`, selected epoch 90 |

The current dissertation sources are Typst, not TeX. Read `~/dhnyu-masters-dissertation/template/sections/chapters/methodology/{01-scene-construction,02-object-modal-embeddings,04-spatial-relations,05-scene-embedding}.typ`, `04-methodology-training.typ`, and `results/{01-experimental-setup,05-model-comparison-and-ablation}.typ`. `main.pdf` exists but has a September 24 modification time; this audit used current source text rather than treating that PDF as newer authority. No claim of a fresh PDF build or full dissertation semantic-hash reconciliation is made. Blueprint and acceptance provenance are historical pins, not the current dissertation Git HEAD; do not silently repin them.

External artifacts inspected, all read-only (prefix D = `/mnt/hdd002/dhnyu/fusedata`):

- `D/models/reduced/formal_plan/current_cbb824f19be83552/current_experiment_plan.json`.
- `D/models/reduced/training/canonical/campaign/s09camp_d2f6749da19ad6aa56c2d303/campaign_acceptance.json`.
- `D/models/reduced/training/authorities/s09auth_478c450cdf0e9fa4921ef485/training_authority.json`.
- `D/runtime/training_lifecycle/s09auth_478c450cdf0e9fa4921ef485/{campaign-result,acceptance}.json`.
- `D/models/reduced/training/canonical/finalizations/p9fin_632c80b256fb67b6f316a8a9/finalization_result.json`.
- `D/scene_data/reduced/observations/obs_ee28248872c4ab0ce8b3ea4f/production/acceptance/bsa_bd504b7e871945a5a6207664/{base_spatial_acceptance.json,scene_spatial_statistics.parquet}`.

Only the statistics Parquet payload was independently checksummed in this audit; SHA256 `c68120cf5c1a53a180bb0e6a37955561e29e4a593479c5c73db43822b3c184aa` matches the accepted manifest. Other PASS statements above report recorded acceptance, not a new full payload validation. No new commit was requested explicitly; the report is left as a local file on B6. The pushed branch contains the shared initial commit, not this uncommitted report. `/reports` is ignored by `.gitignore`; this one report is exposed for review with an explicit forced intent-to-add entry, without staging report content or changing the ignore rule.

## 2. Exact current B6 definition and result

`targets/s08_experiment_plan.R` and `R/experiment_plan.R::s08_current_lineage()` bind accepted P0–P6 parents. `python/current_methodology.py::source_contracts()` defines B6 as `(R,)`; `comparison_contracts()` specifies input removal and `induced_subgraph_preserve_existing_edges_only`. The accepted S08 row inherits FM mechanism flags, including `environmental` and `scene_raster: true`, but these are **not actual retained environmental inputs**.

`python/model_families.py::_family_registry()` removes the environmental modality when a B-family retains neither LC nor DEM. `SceneEncoder.__init__()` obtains no raster sources for B6, instantiates road semantic modules only, and builds scene fusion from three vector-type slots. Buildings and POIs have zero pooled slots; no raster CNN contributes. Active entity modalities are relative position, geometry, and semantics. The corrected runtime is `model_families.SceneEncoder`, not the generic `scene_model.ReducedSceneEncoder` or `scene_encoder.PrototypeSceneEncoder` viewed in isolation.

`python/training_family_inputs.py::project()` (line 207) preserves original local IDs for RNG identity, compacts tensor row indices and geometry offsets, filters relation endpoints to retained roads, and does **not** rerun SN top-k after source ablation. Thus B/P can affect which road-road SN edges were selected upstream, despite being absent from the B6 model. Rebuilding a road-only graph before top-k would change the experiment beyond road decomposition.

`targets/s09_training.R` ordinarily builds the prepared cache, executes OFAT, selects its winner, then executes the full comparison inventory. Do not invoke it for this experiment. `python/training_campaign.py::comparison_authorities()` inherits the winner's hyperparameters. The **actual accepted B6** has `d=d_c=256`, K_aug=8, intensity=1, EMA=0.999, peak LR=0.001, root seed **1629790839**. The config/blueprint main dimension of 128 is an OFAT baseline, not the accepted comparison dimension. The accepted authority resolves this distinction; copying the YAML defaults would not reproduce B6.

Recorded B6 retrieval loss is **1.0110323429107666**, separation margin **0.2867180109024048**, selected epoch **90**. B5/B7 recorded losses are 0.77216637134552 / 0.533249974250793. Dissertation result text reports HIT@1 B5=92.90%, B6=85.65%, B7=94.00%. B6 is weakest on loss and HIT@1, **not every metric**: B5's recorded margin 0.259667605161667 is below B6's. Do not flatten this distinction into an all-metric claim.

## 3. Current road lifecycle and ordering

The implementation path is:

```text
tracked study road links + original nodes (seoul_R.gpkg)
  -> accepted scene membership
  -> assign scene-local entity IDs to source memberships
  -> clip each source geometry to the 500 m scene, retaining one row per link
  -> compute observed geometry/attributes/bbox-center position
  -> build full-source relations and original-node topology (parallel branches)
  -> P3 serialize accepted observations, relations, topology and rasters
  -> P4 fixed training bank / P5 fixed queries:
       select removals, absorb eligible road donors into receivers
       -> perturb geometry -> perturb attributes/rasters
       -> rebuild derived observations and SN; preserve post-absorption topology relations
  -> P6 read original or materialize deltas, tensorize and center geometry
  -> S09 prepared full-source samples + Fourier feature cache
  -> family projection to roads and induced edges
  -> training view selection and entity-modality masking
  -> modality encoders/fusion -> relation contextualization -> type pooling -> scene vector
```

Evidence and details:

- `targets/s02_spatial_observations.R`, `R/spatial_observations.R::p2_build_vector_shard()` delegate to `R/vector_observations.R`. `assign_local_entity_ids()` (175) sorts B/R/P then UTF-8 source IDs and assigns zero-based int32 IDs. `clip_geometry_by_scene()` (204) uses `st_intersection`, preserving row cardinality. `build_role_observations()` (299) accepts LineString/MultiLineString. Multiple clipped pieces remain **one entity**, not one entity per part. There is no new network simplification or sfnetworks link construction in this path.
- `common_observation_columns()` (261) uses `geometry_bbox_centers()`. Relative coordinates are observed bounding-box center minus scene bounding-box center in EPSG:5186 metres. Geometric centroids can be supplementary diagnostics but are not model positions.
- Road attributes at `R/vector_observations.R:333–354`: LANES, ROAD_RANK, ROAD_TYPE, original F_NODE/T_NODE; source/observed length and endpoint retention. IDs come from the registered `source_id_column`; no regenerated geometry-derived parent identity should replace them.
- `R/spatial_observations.R::p2_build_topology_shard()` (385) stores original F/T chains, their coordinates, visibility and observed-vertex mapping, including original nodes outside the clipped geometry. A clipping-created endpoint is not an original node.
- `R/scene_cache.R` declares deterministic entity/relation/source-node ordering and prohibits augmentation/absorption at P3. Accepted topology reports exactly two source-node rows per original road entity; P4 may carry several chains after absorption.
- `python/model_data.py::{read_original_scene,apply_delta,read_training_view,read_fixed_query,tensorize_scene}` (328,358,429,439,488) reconstruct observed scenes. Geometry vertices are centered on each entity's bbox center; local IDs map to contiguous tensor rows separately. Multi-relation bits are OR-collapsed per ordered pair.
- `python/scene_encoder.py::segment_fourier()` (43) analytically sums length-weighted complex finite-line-segment responses using sinc. `geometry_fourier_features()` (195) sums all parts **within each road entity**, uses normalization length 500m and 8×16 frequencies, then log1p magnitude and cosine/sine phase (128+256 features). Adding collinear vertices without splitting entities should leave the line integral unchanged apart from numerical effects; it is not the intervention.
- `python/model_data.py::tensorize_scene()` passes ROAD_RANK/ROAD_TYPE categorical embeddings and standardized LANES plus its missing flag. Road length is not a road semantic numerical input. `model_families.SceneEncoder._semantic()` maps these to d. Freeze the accepted preprocessing/vocabulary; refitting lane statistics after repeating long-parent attributes would introduce a second change.
- `python/model_families.py::SceneEncoder.forward()` gates the three available B6 modalities, uses a sum of relation-type embeddings via `scene_encoder.relation_set_embedding()`, then three 4-head layers. `python/training_support.py::deterministic_relation_layer()` (218) normalizes attention over outgoing stored neighbors of source i and aggregates destination j's value plus relation message back into i. These are sparse graph neighborhoods, not all-pairs dense scene attention.
- `SceneEncoder._pool()` (162) performs learned softmax attention over road entities per scene. It is not parent-balanced or length-weighted pooling. `scene_fusion` maps the three concatenated vector-type slots to d; the contrastive head maps to d_c. Validation normalizes **scene_embedding**, not the contrastive projection (`training_worker.full_validation`, 249).

## 4. Observed coverage and diagnosis

Read-only aggregation of the accepted scene statistics, sample SD (ddof=1), linear-interpolated quantiles, including zeros:

| Split | Scenes | Road rows | Mean | Median | SD | p05 | p25 | p75 | p95 | Max | Zero-road scenes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Training | 2421 | 78457 | 32.407 | 29 | 26.767 | 0 | 8 | 50 | 83 | 141 | 338 |
| Validation | 1000 | 31843 | 31.843 | 28 | 26.971 | 0 | 9 | 49 | 80.05 | 156 | 144 |
| Evaluation | 9000 | 287604 | 31.956 | 29 | 26.867 | 0 | 7 | 50 | 80 | 162 | 1261 |
| All | 12421 | 397904 | 32.035 | 29 | 26.854 | 0 | 8 | 50 | 81 | 162 | 1743 |

These are scene memberships, not distinct nationwide links. They do not establish that road lengths are excessive: the length distribution remains to be measured. Median 29 also means “only a few roads in every scene” is unsupported; the hypothesis must be stratified by original count, length, and coverage.

**Coverage ceiling inference:** zero-road original scenes and their augmentation queries have no retained B6 entities or rasters. In eval mode `_pool()` yields all-zero type slots and the same scene-fusion output for each. No scene ID/center is injected into that output. Their 144 identical gallery vectors cannot be individually distinguished. Stable ranking in `training_worker.retrieval_rank_diagnostics()` can place at most one of those sources first for identical queries. Even if every other source is perfect, HIT@1 ≤ (856+1)/1000 = **85.70%**. This is a code-and-count inference, not a fresh checkpoint inference run. The reported 85.65% is near this ceiling. Verify exact tied-query ranks with accepted artifacts in the next pilot before attributing any residual failures.

Long links could still reduce localization: one position token summarizes an extended shape, relations at distant portions share one endpoint token, and pooling assigns one vote-like attention item per link. Splitting can improve localization but also repeats semantic content, changes effective length weighting, and shortens the physical reach of a fixed three-hop graph. No causal claim follows from the existing B6 ranking alone.

## 5. What segmentation changes and what must remain invariant

| Quantity | Expected effect / required control |
|---|---|
| Entity and geometry rows | Increase; each positive-length child is independent, including multipart handling explicitly |
| Positions | New child bbox centers and relative embeddings; optionally measure centroid shifts separately |
| Intrinsic geometry | New centers, integrals, magnitude/phase per child; embeddings cannot be copied from parent |
| Semantics | Repeat parent ROAD_RANK/ROAD_TYPE/LANES/missingness; no new semantic information |
| Relations | New endpoints, SN rankings, local cross-parent interactions, sibling contact INT, possible topology changes |
| Pooling | Larger population; long parents gain more items without changing pooling code |
| Runtime | More nodes, relation rows, ragged offsets, Fourier rows and attention work |
| Identities | New child IDs, scene content identities, caches and downstream authorities |
| Physical support | Union of children must equal observed parent support within declared tolerance; no snapping/straightening |
| Length | Sum of child lengths equals each observed parent length; preserve overlap multiplicity across distinct parents |
| Scene population | Exact accepted scene IDs, 500m boundaries, split and query/gallery membership, including zero-road scenes |
| Preprocessing | Reuse accepted category mapping, lane normalization, CRS and frequency config; do not refit |
| Scientific training settings | Same B6 architecture, d=256, SSL objective, optimizer, schedule, EMA, queue, validation and selection |
| Augmentation | Same policy can be retained, but exact realizations and query geometry are not generally invariant if segmentation precedes augmentation |

Physical invariants are achievable for unaugmented observations using along-line substring subdivision. Byte-identical model queries and different road decomposition are mutually incompatible. The design must distinguish fixed query **identities and view policy** from fixed physical perturbations. This unresolved distinction is a training GO gate.

## 6. Relations: exact semantics and artificial sibling effects

`config/relation_graph.yml` and `R/spatial_relations.R` are the original-scene contract:

- `scene_sn_edges()` (152): exact observed-geometry minimum distance ≤100m; top-16 per source, distance quantized to 1e-9m then destination local ID, exactly 16 at cutoff ties; symmetrize if either endpoint selects. No sibling exclusion. This is not centroid distance. After symmetrization a node can have degree >16, although total directed SN rows ≤32N eligible nodes.
- `scene_intersection_edges()` (248): GEOS intersects for B/B, B/R, R/R, including boundary touch, crossing and overlap, expanded both ways. Consecutive children therefore gain INT at their shared split point, independently of SN. Curved/retracing siblings may have additional contacts.
- `scene_connectivity_edges()` (269): shared original F/T node ID whose original coordinate lies in the closed scene footprint; both directions. Clipped endpoints and coordinate coincidence alone cannot create CON. Grade-separated crossings can have INT without CON.
- `collapse_relation_edges()` (301): one row per ordered pair, bit mask SN=1, CNT=2, WIT=4, INT=8, CON=16, self-pairs forbidden. Count unique ordered pairs separately from per-bit counts; these counts are not additive. R–P relations apply only to uncontained POIs; R–B can have SN/INT. B6 contains only R–R SN/INT/CON after projection.

For straight equal-L children, pair index separation q gives minimum distance approximately max(0,(q−1)L). Consequently many siblings fall within 100m: S100 allows nearest and next-nearest children; S5 offers roughly 42 radius candidates for an interior child before top-k, while S50 offers roughly six. Top-16 prevents an unrestricted dense SN clique, but siblings can displace meaningful neighbors; inbound symmetrization and unbounded INT/CON still matter. Local IDs influence zero-distance ties. At endpoints crossing exactly at a split, one physical contact can appear on two children: do not “deduplicate” this away without a declared policy.

**Never inherit F_NODE/T_NODE as incidence on every child.** Doing so gives every sibling the same original endpoints and creates false CON cliques whenever an endpoint lies in the scene. Keep parent F/T only as lineage metadata; attach true incidence to the child(s) actually touching that original node. Cross-parent original topology must be preserved at real nodes, with no connections across clipping gaps. Synthetic internal nodes must have a separate namespace and origin flag.

Controlled alternatives (all keep the same full-source builder-before-B6-projection ordering):

| Candidate | Sibling SN | Sibling INT | CON | Interpretation |
|---|---|---|---|---|
| G / full-relations | Retain ordinary top-k | Retain geometric contact | Original nodes only, endpoint-correct | Closest literal geometry/relation-rule continuation; primary granularity comparison |
| P-post | Delete sibling SN bits after selection, no refill | Same as G | Same as G | Isolates retained sibling SN messages without reallocating neighbor slots |
| P-pre | Exclude same-parent candidates before top-k | Same as G | Same as G | Measures parent-aware neighborhood budget; differs from P-post by recovered external neighbors |
| P-no-contact (optional) | As predeclared P candidate | Also suppress purely artificial consecutive-sibling INT | Same as G | Measures artificial contact messages; risks disconnecting the parent internally |
| C-chain (optional topology sensitivity) | Cross with fixed G/P rule | Retain contact | Original-node CON plus consecutive internal children only | Explicitly changes CON semantics; requires methodology approval |

G preserves physical sequential contact through INT, but does not call synthetic contacts original-network CON. C-chain preserves sequence as CON, never an all-sibling clique, and keeps original endpoint topology. Neither is universally correct by fiat. Stage A should calculate G/P-post/P-pre; C-chain can be a labeled diagnostic counterfactual, not a default training policy. Parent-aware must always state whether filtering is before/after top-k and whether INT remains. Child fragments with the same parent but disjoint observed support must not receive sequential connections across an out-of-scene gap.

Two existing discrepancies must be reported, not silently fixed:

1. Active `python/augmentation_bank.py::sn_relations()` (440) uses exact float distance then local ID, without the original R builder's 1e-9 quantization. Preserve existing Original behavior and include near-tie fixtures; do not fold a tie-rule repair into segmentation.
2. `R/spatial_observations.R::p2_build_topology_shard()` stores both source nodes, including nonvisible ones. `augmentation_bank.scene_data()` (577) reads all of them; `invariant_relations()` (405) constructs CON from shared chain IDs without a footprint/visibility test. This differs from original `scene_connectivity_edges()` and the dissertation's retained-in-scene rule. Whether affected shared-outside-node pairs actually occur in accepted views was not scanned here. Stage A must audit this condition; changing it is a separate methodology/bug-resolution decision, not an incidental segmentation fix.

## 7. Segmentation scales and deterministic geometry contract

Diagnostic grid: Original, S100, S50, S25, S10, S5 (metres). Recommended first real-data pilot: **Original/S100/S50/S25**, with S10/S5 restricted to cheap count bounds and the smallest stress fixtures until budgets are measured. No evidence yet justifies declaring 5m either optimal or categorically infeasible.

Proposed structural operator for decision: segment within each accepted observed parent component, in its preserved source direction, at cumulative length L,2L,…; last positive piece ≤L. Keep every intervening polyline vertex. Do not interpolate a chord over a bend, bridge disconnected components, merge source links, cross a true original network node, or remove a tiny positive residual merely for aesthetics. Split at any evidenced internal true node before applying the length rule. Flag inconsistent node/geometry mapping for review rather than snapping it.

Retain parent source artifact/hash, source link ID, scene ID, component/visible-run index, start/end chainage, original-node incidence, synthetic cut ID, and segmentation policy/version/L. Stable child identity should hash these canonical fields (binary64/explicit serialization for chainage) and preserve a human-readable ordinal. Child local IDs follow deterministic scene/type/parent/component/ordinal ordering; maintain an explicit original-to-child mapping. Test reproducibility across worker/shard order and avoid lexicographic `_10` before `_2` surprises. B/P original IDs may shift under contiguous reindexing: preserve their original RNG identities in a separate field if pairing augmentations.

Scene-clipped anchoring versus global source-chainage anchoring is a declared choice: global anchoring produces the same cuts in overlapping scenes but requires source geometry and can alter counts near boundaries. Do not switch between these across scales. Original must remain the accepted multipart-one-entity baseline; component expansion alone is an extra effect, so include an optional “component-only” diagnostic if multipart prevalence is material.

## 8. Stage A: structural diagnostic, no training

Future implementation should create a dedicated experiment config, thin target script and external store, without importing the training campaign or maintenance pipeline. Inputs: accepted scene statistics, membership/P3 observations, true topology and artifact hashes. Output root proposal: `D/experiments/b6_road_granularity/<design_hash>/`, with staging then acceptance and immutable publish. Targets return fixed documented manifest/Parquet/QC paths only after validation. No GPU is needed for the geometry/relation census.

Start with a deterministic **32-scene training-only** pilot: hash-order sample eight available scenes in each original road-count stratum 0, 1–8, 9–49, ≥50; deterministic redistribution if a stratum is undersupplied. Add a separately tagged, bounded stress set for longest observed parent, most multipart components, maximum road count, boundary clipping, loops/retracing, original high-degree junctions, and shared original nodes outside the scene. Never mix the stress set into unbiased distribution estimates. No evaluation retrieval or scale choice from evaluation performance.

After resource acceptance, stream all 12,421 accepted originals one scene at a time, preserving split labels. Select feasible scales from training structural/cost evidence; report validation/evaluation structure descriptively only. Include zero-road scenes in denominators and report per-nonempty statistics separately. For every scale and relation treatment, store:

- Entity census: road count/scene mean, median, sample SD, p05/p25/p75/p95/max; source-parent count; observed total road length; child length distribution; children per parent; multipart count; zero/tiny child count; original-node preservation; child bbox-center and optional centroid dispersion. Weight pooled child and per-scene summaries explicitly.
- Graph census: unique ordered pair count, unordered pair count, total per scene and per road; R–R, R–B and R–P counts in the full-source graph; SN/CON/INT and other bit counts; same-parent counts by bit and pair; sibling fraction of R–R pairs (null when denominator zero); per-node out/in degree and p95/max; isolated roads; connected components; cross-parent degree; displaced/recovered external SN neighbors; physical three-hop reach. B6 R–B/R–P counts must be exactly zero after projection.
- Preserve both full-source graph and its B6-induced summary. A road-only-recomputed graph may be a separately labeled counterfactual to expose top-k competition, never the primary Original baseline.
- Augmentation audit on a small accepted-view sample: Original exact replay first; absorption rate, donor/receiver lineage, no-valid-receiver frequency, post-absorption child lengths/counts, perturbed length change, cut contact preservation, geometry retries/fallbacks, complexity branch changes, SN turnover, source-node visibility discrepancy, and zero-road queries. No optimizer calls.
- Coverage audit: zero/nonzero road originals and queries; identical embeddings/rank groups for empty scenes from existing validation artifacts if available. A future bounded forward may confirm the constant-vector inference; no new full evaluation inference is authorized by this report.

No segmentation census, augmented-view parity run, or forward benchmark was executed in this task. The only numerical census executed was the small accepted-statistics read in section 4.

## 9. Augmentation and query controls requiring a decision

The active implementation is `python/augmentation_bank.py`, invoked by `targets/s04_augmentation.R` / `R/bank_execution.R`, with `config/p4_deterministic_augmentation.yml`. The older `scene_augmentation.py` removal-closure code is not the accepted bank's road policy.

`compose_absorption()` (615) selects road donors among sampled removals, searches non-donor receivers sharing source-node IDs and matching ROAD_TYPE/ROAD_RANK, and appends donor geometry/chains to receiver multipart geometry. A road with no valid receiver remains; it is not blindly deleted. `augment_scene()` (649) then perturbs geometries with protected source nodes, checks CNT/WIT/INT/CON against the post-absorption reference, perturbs attributes/rasters, and regenerates SN. Source-ID keyed geometry/category randomness and scene-wide removal quotas change when children replace parents. Synthetic contact endpoints can also force rejection/fallback; internal cuts are not automatically protected source nodes.

Two designs answer different questions:

- **Pre-bank segmentation:** P3 child entities -> same bank policy -> new P4/P5 views. Closest preprocessing intervention, with mechanically changed removal/absorption/masking and geometry perturbations. Original-node-only CON can leave internal children without eligible receivers. C-chain can make siblings absorbable and undo segmentation. Max child length is guaranteed before augmentation, not after absorption. Freeze original complexity thresholds if the aim is to hold this fitted policy constant; refitting on child vertex counts is a separate variant. Measure all these effects rather than claiming identical realized augmentation.
- **Post-bank segmentation (paired-view sensitivity):** materialize the accepted original views first, then subdivide their realized road geometry and rebuild a full-source graph. This preserves physical perturbations and view identities, but is a different operation order. Absorbed geometry can have multiple original parents and receiver attributes; recover component-level donor lineage and never split across true nodes or reassign attributes silently. If provenance cannot recover those associations, this candidate is NO-GO. It is not an excuse to relabel the old bank acceptance as a child bank.

Recommendation: Stage A original-scene diagnostics first; explicitly choose the pre-bank primary versus post-bank paired sensitivity before implementing Stage B. Keep validation query/gallery **scene IDs and two query indices** fixed in both; record that pre-bank query payloads are regenerated. If exact existing query observations are mandatory, use the paired-view design with its stated order change. Neither byte-identical full inputs nor every random draw can remain invariant when tensor lengths change.

## 10. Stage B design only: controlled retraining and hypotheses

Provisional small comparison set, chosen only after Stage A cost/coverage review:

1. B6-original reproduction/control.
2. B6-S50-G and B6-S25-G (or S100 if finer scales fail budget gates).
3. Same selected scales with one predeclared parent-aware policy; recommend contrasting P-post and P-pre structurally before selecting training arms. A minimal first training decision can use one scale crossed with G and P-pre.

Keep model family B6 and its architecture unchanged; store segmentation/policy in a separate experimental identity, not in historical `cmp_B6`. Do not add these arms to the immutable 17-model plan. Do not rerun OFAT or retune each L.

| Hypothesis | Discriminating evidence / limitation |
|---|---|
| H1: coarse entities | Improvement on low-count, long-parent **nonempty** scenes, preserved under sibling control and associated with better cross-parent localization; whole-population HIT@1 has almost no headroom |
| H2: geometry inadequacy | Inspect child Fourier norms/phase, geometry modality gates and geometry-only similarity on fixed scenes; segmentation changes geometry as well as position, so null/positive retrieval alone cannot identify H2 |
| H3: semantic limitation | More entities without new semantics yields no useful improvement, especially with repeated ROAD_TYPE/RANK/LANES; compare existing road semantic composition strata |
| H4: artificial relations | Scale × G/P-post/P-pre interaction, sibling attention mass and external-neighbor displacement explain gains/losses; retaining INT means SN suppression is not a complete sibling control |
| Coverage alternative | Zero-road constant-vector group explains most HIT@1 deficit; unaffected by L; separate from all four above |

Optional later mechanistic controls, only with separate approval: geometry-modality intervention crossed with Original/one L; parent-balanced pooling; typed-edge versus fixed parent-level connectivity. These alter model/input rules and cannot be counted as the primary granularity-only comparison. Parent-geometry reuse on children would isolate some geometry effects but create a mismatched child representation, so label it a diagnostic control, not “correct geometry.” H2 versus H3 cannot be causally settled by segmentation alone.

Seed control requires implementation work: `python/training_configuration.py::configuration_seed()` hashes configuration ID, and `training_campaign.comparison_authorities()` uses it. Simply renaming arms changes seeds. Preserve the accepted resolved B6 seed 1629790839 for the first paired block under an explicit experimental seed-group contract; retain unique authority/run identities. If replicates are authorized, predeclare the same seed list for every arm, with no best-seed reporting. Children still have distinct masking identities (`training_family_inputs.family_modality_assignments`, 393); same RNG policy does not mean equal masks or dropout draws across different tensor shapes.

Freeze the accepted B6 resolved model/training configuration, not base defaults: d=d_c=256, 4 heads, 3 relation layers, dropout 0.2; K_aug=8/main_1.0x, two views/scene; global batch 32, world size 2, 76 updates/epoch, maximum 200 epochs; AdamW LR .001, weight decay .0001, betas .9/.999, eps 1e-8, grad norm ≤1; 760-update warmup / 14440 decay; temperature .1, negative exclusion 750m, EMA .999, queue capacity 8192 and resolved width 256; modality mask probability .30; float32 deterministic execution. Sources: accepted authority, `config/training.yml`, `config/training_controller.yml`, `training_configuration.materialize_hyperparameter_configuration()`.

Keep optimizer update count, batch scene order, view selection, queue update order, negatives and schedule fixed. If an arm cannot fit the same effective batch/protocol, do not quietly shrink it; reject the scale or preapprove an equivalence-tested resource adjustment. Maximum training cost is 15,200 optimizer updates/arm; actual early stopping may differ.

## 11. Metrics, descriptors and scientific acceptance

Reuse `python/training_worker.py::full_validation()` and `retrieval_rank_diagnostics()`: 2,000 fixed query identities against 1,000 original validation scenes; unit-normalized online scene embeddings, cosine similarity, cross-entropy at accepted temperature, mean positive minus largest nonmatching-gallery similarity, MRR and HIT@1/@5/@10 with stable ranks. Training's negative-distance mask must not be introduced into validation; the current validation code compares the full gallery.

Checkpoint selection is the **accepted S08 selection object** / `python/training_finalization.py::selection_contract_content()` and selector: validate every 5 epochs, minimize retrieval loss; losses are equivalent only for absolute difference strictly below 1e-4; maximize margin within equivalence, then earlier completed epoch. Patience is four events and resets only for loss decrease ≥1e-4. `config/training.yml` contains an older `patience_reset: selected_best_event` description; the accepted plan/finalizer is the exact rule to preserve, not that shorthand. HIT metrics and any new stratified metrics never select checkpoints.

Report whole-population accepted metrics, selected epoch and paired differences. Additionally report the **same-gallery** query diagnostics by original zero-road/nonempty status, original road-count bins and parent-length bins. Do not remove zero-road gallery entries or introduce a new primary metric. Group bootstrap uncertainty by source scene (two queries together), using a predeclared seed; repeated training seeds, if later authorized, assess training variance. The 1e-4 selection tolerance is not a statistical-significance threshold. Do not claim improvement from a single small numerical change or from selecting the best scale post hoc without reporting all arms.

Reuse original observation descriptors from `R/scene_descriptors.R` and `config/s11_representation_analysis.json`: road_density, road_orientation_dispersion (length-weighted finite-segment axial dispersion), mean_road_segment_length, road_location_dispersion (bbox-center RMS), road_type_composition, road_hierarchy_composition, relation_composition and mean_relational_degree. Keep **original-parent descriptors** fixed as external explanatory variables. Child length/dispersion/type frequencies mechanically change and belong in a separate structural panel, not a claim of better alignment. Road density and length-weighted orientation should remain stable under geometry-preserving subdivision. Add original-node degree/intersection count as a clearly separate diagnostic using retained true-node incidence; never count synthetic cuts as real intersections.

Positive scientific evidence requires a valid controlled run plus coherent loss/margin and nonempty-scene diagnostics, with uncertainty and relation-policy sensitivity disclosed. A null result is valid; it does not prove H2 or H3. Given the coverage ceiling, a large aggregate HIT@1 improvement would first trigger an input-leakage/population audit.

## 12. Expected computational cost and bounded benchmark

For positive observed component lengths ell_j, the proposed clipped-component operator has N_L = sum_j ceil(ell_j/L). Original N is the number of parent memberships, including multipart parents as one. Obtain ell_j before projecting a runtime budget. A straight 500m parent yields 5/10/20/50/100 children for S100/S50/S25/S10/S5; a winding road can exceed 500m within a scene. This illustration is not a measured workload multiplier.

A split adds child endpoints/offset metadata and one Fourier row per child. Feature output alone is 384 float32 values = 1536 bytes per road entity per view, excluding tensors, manifests and Python overhead. Geometry integration work scales with coordinate intervals ×128 frequencies plus entity overhead; it is not exactly proportional to child count. Cached training avoids recomputing Fourier every step, but preprocessing, disk and RAM costs grow. Sparse relation layers scale roughly O(N d² + E d) per layer; SN selection is capped before symmetrization, but geometry candidate search and INT/CON can become much larger. False endpoint copying can create O(m²) sibling CON and must fail QC.

Bounded future measurement: fixed scene batch order, Original plus candidate L; time geometry split, graph build, serialization, Fourier computation, cache load and model forward separately. Record compressed bytes, coordinate/part/feature rows, unique edges and bit counts, CPU wall time/RSS, forward time and GPU peak allocated/reserved memory after warmup and synchronization. CPU one worker/one thread initially; choose parallelism from measured RSS/I/O, with BLAS/OpenMP capped. A forward benchmark uses inference mode and no optimizer; GPU lock/controller and availability checks are mandatory. Backprop memory is not inferred as equal to forward memory; training budget needs a separately authorized bounded training-memory check later.

Publish p50/p95/max costs and extrapolate by strata/view counts, not only mean scene. Suggested **provisional engineering gates**: no truncation, no dropped scenes, ≤70% available RAM/VRAM at target batch, and initial pilot ≤1 hour/≤10 GiB new artifacts. Freeze actual resource limits in the future config after checking hardware; these numbers are proposed ceilings, not current machine measurements. Do not invent a wall-clock training estimate before timing the bounded workload. S10/S5 expansion stops at budgets rather than silently omitting dense scenes. All-scene all-scale production is not authorized by this design task.

## 13. Cache and lineage consequences

| Artifact | Reuse decision |
|---|---|
| Canonical source/study inputs, accepted scene index and split | Read-only reuse; no new national preprocessing or maintenance dependency |
| Original membership/source lineage | Reuse as parent map; child membership/IDs require new artifacts |
| P2 observed roads/topology/relations | New child datasets; full-source SN competition means even B/P-related edges can change |
| P3 original scene cache | Existing cache remains input/reference; publish derived child scenes under new identities |
| P4 bank | Pre-bank design requires new bank/acceptance and child-aware lineage; old deltas cannot apply to new IDs |
| P5 fixed queries | Same scene IDs/query indices; new payload identities. Paired-view design may reuse old realized geometry as input only |
| Raster inputs | Physical scene rasters reusable with hash evidence; child object contexts require recomputation for full-source diagnostics; B6 does not consume them |
| Vocabulary/normalization | Freeze accepted values; bind to new dataset without pretending preprocessing was refit |
| P6 model-ready samples | New entity arrays, offsets, topology, relations, availability rows and acceptance |
| S09 prepared cache | New content/parents/manifest. Cannot mutate or rename accepted s09cache_dc4e9e271e40ffe8ae17967c |
| Fourier cache | New child centers/coordinates/order/lineage keys and values; unchanged payload reuse only with exact identity checks |
| S09 authority/checkpoints | New experimental plan, seed-group policy, runtime hash, authority and run namespace; historical B6 unchanged |
| S10 | New embeddings/rankings for future child models; reuse gallery scene membership/rendering inputs only; no canonical generation overwrite |
| S11/S12 | Original physical descriptors potentially reusable by checked identity; changed representation/child-graph descriptors, alignments and figures need new artifacts and explicit experimental consumers |

Evidence: `training_geometry_cache.cache_record()` (36) hashes geometry layout, role/scene/view/profile, bank/index/authority/preprocessing/acceptance, scientific coordinates, entity order, geometry config and implementation. `scripts/prepare_training_cache.py::canonical_specs()` hard-codes 80,472 entries for the existing multi-profile prepared cache; a small experiment cannot impersonate this inventory. `training_campaign.cache_identity()` hashes parents and membership; `training_cache_storage.py` only supports **byte-identical physical replicas**, not changed scientific inputs. `R/experiment_plan.R::s08_current_lineage()` enforces matching P0–P6 parents. New decomposition must enter these identities explicitly.

`config/training_controller.yml` requires branch reduced and immutable canonical paths. Design a separate experimental runner/authority, not a relaxation of the production guard. Blueprint records historical `_targets_evaluation.R` as blocked and distinct from the approved FM-only S11 representation graph; neither should be unblocked/adopted as a side effect. S12 config pins accepted comparison embeddings; no substitution into historical B6 slots.

## 14. Subsequent implementation touchpoints

No files in this list were changed in this task. Prefer additive experiment wrappers with explicit config injection and unchanged Original parity:

| Area | Existing evidence/touchpoints | Future work |
|---|---|---|
| Segmentation/lineage | `R/vector_observations.R::{assign_local_entity_ids,clip_geometry_by_scene,build_role_observations}`, `R/spatial_observations.R::p2_build_topology_shard`, `config/vector_observation.yml` | New reusable `R/b6_road_segmentation.R`, child geometry/ID/parent contract; preserve true topology |
| Relations | `R/spatial_relations.R::{scene_sn_edges,scene_intersection_edges,scene_connectivity_edges,collapse_relation_edges}`, `config/relation_graph.yml` | Experimental sibling policy before/after top-k, incidence adapter and per-bit diagnostics; canonical rules frozen |
| Serialization | `R/scene_cache.R`, `python/model_data.py::{apply_delta,tensorize_scene}`, schemas under `config/schemas/` | Carry child/parent/component/cut provenance and ragged topology; support children without original nodes |
| Augmentation/queries | `python/augmentation_bank.py::{compose_absorption,augment_scene,invariant_relations,sn_relations}`, `R/augmentation.R`, `R/bank_execution.R`, `R/fixed_queries.R` | Chosen operation order; lineage-aware receiver eligibility and RNG mapping; preserve policy version in new config |
| Model routing/cache | `python/training_family_inputs.py`, `python/model_families.py`, `python/training_geometry_cache.py`, `scripts/prepare_training_cache.py` | Reuse unchanged encoders; new dataset bindings and small experiment cache inventory; assert induced graph parity |
| Training authority | `python/training_campaign.py`, `python/training_configuration.py`, `R/training_targets.R`, `targets/s09_training.R` | Separate experimental entrypoint and seed grouping; do not execute/expand canonical campaign |
| Diagnostics | `R/scene_descriptors.R`, `python/training_worker.py` validation functions | Reuse definitions; add separate structural summaries/coverage analysis |
| Orchestration | `targets/`, `_targets.R` controllers, `tools/targets-network/render_targets_network.R` | Proposed dedicated `targets/b6_road_granularity.R`, separate script/store, CPU/GPU resources and updated network HTML when implemented |
| Tests/config | `tests/testthat/`, `tests/python/`, `config/` | Fixtures and new `config/b6_road_granularity.yml`; no large data in Git |

These are inspection/modification candidates, not a requirement to edit every module. Keep reusable model math and canonical family registry unchanged wherever an input adapter suffices. New target contracts must define inputs, fixed output paths, schema/CRS/QC, dependencies and resources before coding, then follow AGENTS.md parse/tests/manifest/network/tar_validate/pilot/QC/network-HTML sequence. This task changed no target, so rebuilding its graph or running tar_make would be unnecessary and outside scope.

## 15. Risks, recommended first pilot, and GO / NO-GO gates

Main risks: coverage ceiling masquerading as granularity weakness; unknown long-link prevalence; sibling SN competition and INT contact; false CON from copied parent IDs; original/P4 topology semantics divergence; augmentation absorbing children back together or refusing donors; changed nonroad RNG through local reindexing; receiver semantics on multi-parent geometry; type-pooling length bias; graph receptive-field shrinkage; zero-length/multipart clipping bugs; unstable IDs at length thresholds; lineage collisions; comparing d128 experiments against accepted d256 B6; changing seeds by experiment names; canonical campaign trigger through shared targets.

Recommended next pilot is the training-only 32-scene Original/S100/S50/S25 structural audit with G/P-post/P-pre, plus bounded edge-case fixtures. Compute S10/S5 child-count/cost bounds first. Include a deterministic audit of zero-road validation ranks from existing outputs. Do not train merely because entity counts increased.

**GO for structural implementation** when its separate namespace/store, accepted parent hashes, child ID/geometry contract, clipping anchor and diagnostic relation candidates are explicit. Required fixtures: straight/bent links, multipart re-entry, closed loop, tiny residual, original T-junction, grade-separated crossing, boundary node, coincident coordinates with different IDs, outside shared node, zero-road scene, tied SN distances, and more than 16 siblings. Original must reproduce accepted entities/geometry/relations exactly. No disconnected-component bridging, no real-node loss, no duplicate/self edge, symmetric SN/INT/CON, and byte-stable reruns.

Proposed geometry acceptance uses `config/vector_observation.yml` tolerances: coordinate/absolute length 1e-7m and relative measure 1e-10. Check per-parent length, support symmetric difference/Hausdorff within an explicitly documented numerical method, no positive-length overlap among siblings beyond original multiplicity, max child length ≤L+tolerance, exact parent attributes, EPSG:5186 and immutable parent checksums. Do not compare only dissolved union lengths, which could hide duplicate road rows.

**NO-GO for training until all of the following are resolved:**

1. Choose clipped versus source-chainage anchoring, multipart policy and augmentation operation order; state which query invariants are physical versus identity-only.
2. Predeclare G and the precise parent-aware comparison; decide whether synthetic CON is a separate sensitivity arm. No arbitrary relabeling of internal cuts as original nodes.
3. Audit shared-outside-node P4 CON and near-distance-tie discrepancy. If consequential, separate correction/rebaseline from segmentation rather than silently repairing the accepted control.
4. Freeze accepted d256 B6 resolved settings, seed grouping, preprocessing, scene/view population and checkpoint rule in an experimental authority; keep S09 campaign unchanged.
5. Pass Original parity, geometry/topology/data-contract tests and resource pilot; choose scales from structural/cost evidence without evaluation retrieval tuning.
6. Explain achievable headroom under zero-road coverage; predeclare whole-population metrics plus diagnostic strata and uncertainty, without a new selection metric.
7. Receive a subsequent request authorizing training; this task provides no training authorization.

**NO-GO at any stage** if execution requires overwriting historical artifacts, silently altering reduced/dissertation methodology, dropping difficult scenes, changing core hyperparameters per L, or rebuilding large accepted products as a side effect. Fail closed and report.

## 16. Dissertation implications and task verification

- Exploratory diagnostic: document child construction, relation/cost/coverage findings externally; no thesis definition changes required.
- Supplementary sensitivity: add experiment construction, lineage, augmentation and sibling policy, fixed controls, coverage ceiling and null/positive findings; preserve canonical B6 results.
- Canonical B6 replacement: explicitly revise source-ablation entity definition and all affected results/provenance. A segmented B6 would no longer be strictly the original FM road input with other sources removed; explain that comparability change instead of overwriting its row.
- FM road modification: independent full-source experiment required because R–B/R–P competition, raster context, cross-type relations and augmentation all change. A positive B6 sensitivity result cannot authorize FM replacement.

Verification performed: document section/fence and existing-path checks (PASS after correcting the checker to strip line-number suffixes); Git diff whitespace check; clean/synchronized branch preflight and live remote read; B6 creation/push/upstream verification; source/target/config tracing; current Typst methodology/results read; accepted plan/authority/finalization reads; checksummed small statistics census. No disposable segmentation prototype was needed. No implementation tests, tar_manifest/tar_network/tar_validate/tar_make, segmentation measurements, training, GPU benchmark, full cache checksum sweep, fresh checkpoint inference, or 17-model campaign were run. No target or dependency changed; existing network HTML was not regenerated. This report is the only intended working-tree addition; no large data, credentials, logs, target stores or temporary artifacts were added.

Input prompt summary: create and push B6 from clean reduced; audit actual road-only behavior and design a controlled entity-splitting experiment, especially sibling SN/CON effects, diagnostic scales, invariant controls, cache lineage and future validation, without implementing segmentation, training, modifying accepted results or editing the dissertation.

## 17. Stage A implementation and measured results (2026-10-02)

The authorized Stage A implementation is complete on `B6` in `~/fuse`, starting at `851efd0c94120ff250f34502fceba73a45080281`. No secondary worktree was created. The experiment uses `config/b6_road_granularity.yml`, `R/b6_road_segmentation.R`, `R/b6_road_relations.R`, `R/b6_stage_a.R`, `R/b6_diagnostics.R`, `python/b6_artifact_audit.py` and the independent `_targets_b6_road_granularity.R` / `targets/b6_road_granularity.R` graph. Canonical source modules are read-only dependencies; no canonical preprocessing behavior changed.

Accepted experimental identity: **`b6a_f5d6a32cdd09cf5688b0666a`**. Root: `/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity/b6a_f5d6a32cdd09cf5688b0666a/`; acceptance: `acceptance/acceptance.json`, PASS. Dedicated store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-b6-road-granularity-stage-a`. Source/config hashes, parent checksums and payload manifests preserve lineage. Historical accepted P2/P3/P4/P5/P6/S09/S10/S11/S12 products were not rewritten or relabeled.

Operation order is now explicit for Stage A: **accepted scene clipping → observed component/true-node intervals → cumulative-length child entities → full-source graph → induced road graph**. This does not resolve Stage B augmentation order. Child lineage preserves source/local IDs, semantic values and missingness, chainages, parts, true-node incidence and separate synthetic-cut identity. Length/support, repeat identity, no bridging, no false CON, symmetry and source projection checks PASS. Sibling INT remains by design.

Original parity passed for all **37 scenes**: 32 hash-selected training scenes (eight per specified stratum), plus five separate training stress scenes. Exact relation endpoints/masks, ordering/IDs, geometry, length and absolute/relative bbox centers matched accepted P3. There was no scientific parity failure. Maximum length/support errors in the segmented results were 1.14e-13 m / 2.91e-11 m; two positive sub-millimetre pieces were retained, zero zero-length children.

| Scale | Pilot road entities | Ratio | G ordered R–R pairs | Ratio | G sibling SN | Sibling INT (all policies) |
| --- | --- | --- | --- | --- | --- | --- |
| Original | 783 | 1.000 | 6,188 | 1.000 | 0% | 0% |
| S100 | 1,044 | 1.333 | 8,434 | 1.363 | 6.57% | 16.61% |
| S50 | 1,547 | 1.976 | 13,672 | 2.209 | 13.30% | 36.90% |
| S25 | 2,552 | 3.259 | 26,168 | 4.229 | 21.88% | 57.53% |

These are measured equal-stratum pilot aggregates, not population-weighted estimates or retrieval improvement. S50 G/P-post/P-pre ordered road pairs are **13,672 / 13,380 / 13,886**. P-post preserves external SN without refill; P-pre restores **506 external ordered road–road SN pairs** at S50, with 937 recovered external R-origin neighbors including B/P. Pilot CON is unchanged at 2,540 ordered bits across every scale and policy. Both projected R–B and R–P counts are exactly zero. Full-source cross-type diagnostics remain separate.

S10/S5 were **not fully materialized**: exact pilot child counts are 5,815 / 11,139, with separately labeled sibling/graph bounds and Fourier byte estimates. First-scale recommendation is **S50**, with G versus P-pre; retain P-post as an optional mechanism diagnostic, S100/S25 as sensitivity references, and defer S10/S5 from the first block. S50 changes physical three-hop reach (mean 231.57 → 163.68 m under G), repeats semantics and changes pooling population: these remain confounds to interpret, not proof of H1. Stage A cannot resolve H1 versus H2/H3.

The zero-road census was reconfirmed: training338/2421, validation144/1000, evaluation1261/9000. Existing accepted S10 evaluation embeddings have one bitwise-identical vector across all 1,261 zero-road rows. Validation per-query vectors/ranks were unavailable; the 85.70% validation ceiling remains a supported inference consistent with reported85.65%, not newly measured validation ranks. No inference or checkpoint load was performed.

Post-bank verdict: **POST_BANK_FEASIBLE_WITH_ADDITIONAL_LINEAGE**. Sampled accepted P4/P5 receiver mappings pass (27/41 receiver views), but clipped multipart part ranges must be recovered from P3 because serialized topology component indices track source chains. Preserve accepted receiver attributes through absorption, and explicitly recover true-node incidence. The Original/P4 outside-node discrepancy is present: 100 additional ordered pairs in the selected-scene counterfactual, with 58 matching CON ADD rows in sampled P4 views. It was audited, not repaired. A pair also connected inside the scene was correctly excluded from this counterfactual.

Resources: initial one-worker pilot supported the user-requested **up to40 workers ×1 computation thread**. Final graph wall time **12m17.8s**; scene-branch p50/p95/max **21.792 /439.336 /494.469s**; diagnostic worker peak RSS **0.471GiB**; a running snapshot observed39 worker processes and approximately13GiB summed RSS. Serialization p50/p95/max **0.071 /0.201 /0.291s**. Compact aggregate diagnostics are approximately1.20MB. These timings do not estimate training cost.

Validation: R parse, config/schema, focused testthat and relevant spatial/cache regressions PASS; Python compile and28 relevant pytest tests PASS;15-target/38-edge DAG and `tar_validate()` PASS; dedicated graph and output/lineage QC PASS. A cached rerun skipped87 valid targets and all436 experimental files retained identical SHA256. The separate network HTML is current (15/15 up to date). No unrelated pipeline was executed.

**READY_FOR_STAGE_B_METHOD_SELECTION**, not immediate training. Subject to the augmentation/lineage and experimental authority gates in the execution report, the minimum future block is `B6-original`, `B6-S50-G`, `B6-S50-Ppre`. Keep the accepted validation/checkpoint rule and all non-granularity scientific settings fixed; do not retune scales independently. Any later accepted B6 sensitivity remains separate from canonical B6 or FM until explicitly approved. Dissertation edits, training, checkpoint creation, canonical artifact changes and reduced changes all remain **NO**.
