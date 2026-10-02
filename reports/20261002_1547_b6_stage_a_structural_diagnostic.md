# B6 Stage A road-entity granularity: execution and structural diagnostic

Created 2026-10-02 15:47 KST; final validation recorded 2026-10-02 16:06 KST.

## Scope and provenance

Optimizer-free, training-only structural pilot requested by the user. This implements scene-clipped road **entity subdivision**, not vertex densification, and compares Original/S100/S50/S25 under G/P-post/P-pre. S10/S5 are count/bound diagnostics only. The user subsequently authorized the existing `~/fuse` B6 worktree and requested consideration of 40 workers.

Entry branch `B6`; HEAD `851efd0c94120ff250f34502fceba73a45080281`; upstream `origin/B6`, ahead/behind 0/0. The only preexisting work was the explicitly authorized design report `reports/20261002_1441_b6_road_entity_granularity_experiment_design.md`. This report was preserved. `reduced` was neither checked out nor modified. Dissertation entry HEAD: `6a43d30133db01a773f6b5d355fc1290b544072b` (clean).

The implementation follows the existing design report, dissertation methods, and `blueprint/targets_implementation_blueprint.md`. The segmentation and sibling policies are explicitly experimental extensions; canonical B6 architecture, Fourier encoder, augmentation and accepted artifacts remain unchanged. Accepted B6 is still the induced full-source relation subgraph with d=d_c=256.

## Implementation and reproducibility

| File | Responsibility |
|---|---|
| `R/b6_road_segmentation.R` | Along-line component subdivision, deterministic child identity, parent/endpoint provenance, geometry QC |
| `R/b6_road_relations.R` | Exact SN candidates, G/P-post/P-pre, canonical INT/containment helpers, original-node CON, induced road graph metrics |
| `R/b6_stage_a.R` | Strict config/schema, parent resolution/checksums, hash sampling, accepted P3 extraction, Original gate, immutable publication |
| `R/b6_diagnostics.R` | Entity/position/geometry/graph metrics, resource measurements, fine-scale bounds, coverage/topology audits, acceptance |
| `python/b6_artifact_audit.py` | Read-only accepted P4/P5 lineage, accepted S10 empty vectors, selected validation ledger |
| `config/b6_road_granularity.yml` and schema | Frozen scientific settings, accepted parent paths, limits, independent output/store |
| `_targets_b6_road_granularity.R`, `targets/b6_road_granularity.R` | Isolated CPU-only DAG, no canonical campaign import |
| focused R/Python tests | Geometry, topology, policies, parity fixtures, output namespace, lineage |
| `tools/targets-network/b6_road_granularity_phases.yml` | Separate graph documentation mapping |
| `artifacts/targets-network-b6/targets-network.html` | Generated 15-target/38-edge dependency graph |

Concrete entry functions: `b6_split_parent()` / `b6_scene_entities()` implement the intervention; `b6_graph()` / `b6_repolicy()` define policies; `b6_parity_one()` gates all diagnostic branches; `b6_scene_run()` checks invariants and computes each scale; `b6_relation_metrics()` induces the road graph; `b6_publish()` enforces immutable publication; `b6_acceptance()` rechecks parents and final QC.

Run from repository root:

```r
targets::tar_make(
  script = "_targets_b6_road_granularity.R",
  store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-b6-road-granularity-stage-a"
)
```

The accepted P2 statistics SHA256 is `c68120cf5c1a53a180bb0e6a37955561e29e4a593479c5c73db43822b3c184aa`. P2: `bsa_bd504b7e871945a5a6207664`; P3: `osca_c177810e2c5165326a328b56`, cache `oscache_75a543f656ab777aada74fbd`. Selected P3 tar payloads and extracted members are checked against recorded SHA256. Parent receipts and selected P3 tar payloads are rechecked after execution. Parent paths and complete receipts are in the experimental manifest.

### Operation order and contract

Accepted scene clipping → observed parent components → cut at true source-node chainages → subdivide each interval by cumulative polyline length → independent children → reconstruct full-source relations → induce road-only B6 subgraph → diagnostics. No globally standardized network is generated. Intermediate vertices, bends, direction, disconnected parts and positive final residuals are preserved. Intersections cannot be crossed just to equalize lengths.

Child IDs hash scene ID, parent source ID, component index, ordinal, exact hexadecimal chainages, policy version and L. Worker/shard order does not enter the identity. Each child retains original local ID, source parent, semantic attributes including missing values, F/T lineage, node/cut endpoint flags. Original F/T are never copied as active incidence on all children. True nodes are recovered against observed support; synthetic cut identities use a separate namespace and do not enter CON.

Geometry tolerance is 1e-7 m absolute + 1e-10 relative for lengths, 1e-7 m Hausdorff support error. A projected source-node chainage within the coordinate tolerance of an existing vertex is snapped to that exact vertex chainage to avoid a floating-point zero-length sliver. Positive segmentation residuals are otherwise retained. This numerical case was found in the resource pilot and added to tests. Subdivision is replayed within every scene/scale and compared exactly.

Positions use bbox centers in EPSG:5186 metres relative to the scene center. Diagnostic occupancy uses a 10×10 grid of 50 m bins inside the 500 m scene, with the outer edge assigned to bin 9. Dispersion is RMS distance of road bbox centers from their mean. Nearest-neighbor distances also use bbox centers. These are structural measurements, not improved geometry quality claims.

SN preserves exact minimum observed-geometry distance ≤100 m, quantization to 1e-9 m before ordering, destination local ID tie-break, top-16 per source, and either-direction symmetrization. An indexed expanded-bbox broad phase avoids unnecessary exact-distance work but never substitutes bbox distance for geometry distance. P-post removes sibling SN after selection, without refill; P-pre excludes siblings before selection. Both retain sibling INT and real-node CON. Reusing G candidate distances for policy reconstruction is fixture-tested against independent fresh builds.

The full-source graph is rebuilt before B6 projection: B/P can consume top-k slots, exactly as accepted B6. Ordered mask rows count unique endpoint pairs; SN/INT/CON bits are reported separately and are not summed as edge counts. Graph components and three-hop physical reach use the induced road graph, with physical reach measured between bbox centers. This is a geometric graph-reach approximation, not measured neural receptive-field quality.

### Population and output contract

Training strata: 0, 1–8, 9–49, ≥50 original roads; eight scenes per stratum. Sampling uses SHA256 UTF-8 of `b6-stage-a-pilot-v1|20261002|scene_id`, ascending hash then scene ID. A deficient stratum is filled from the globally hash-ordered remaining training population. Stress scenes are tagged separately; no stress-only scene enters pilot summary distributions. Pilot means are equal-stratum diagnostic summaries, **not population-weighted estimates**.

Metadata stress selection scans training-only P2 roads for longest parent, highest road count, most multipart, clipping boundary and zero roads. Loop/retracing, high-degree, outside-node and tied-distance cases also have explicit fixtures and a selected-scene search. Missing real examples are reported as uncovered, not fabricated.

Each design has an immutable root under `/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity/<design_id>/`. Identity incorporates config and implementation hashes. All output publication is staging → QC → SHA manifest → atomic rename; an existing publication must match its manifest. The dedicated targets store is outside Git.

Fixed products include selection/pilot_scenes.parquet, stress/stress_scenes.parquet, parity/original_parity.json, diagnostics/scene_scale_metrics.parquet, relation_summary.parquet, road_node_metrics.parquet, child_lineage.parquet, fine_scale_bounds.parquet, cost_measurements.parquet, cost_summary.json, coverage/coverage_summary.json, topology_audit/*.parquet, artifact_audit/augmentation_lineage_audit.json and acceptance/acceptance.json. Small per-scene branch products support independent execution. Extracted input snapshots and all generated data remain outside Git. No new Fourier cache is generated.

### Resource policy

CPU-first, one thread per target. Initial one-worker measurements: largest selected full-source Original graph, 2,626 entities, 58.751 s and peak RSS 552,980,480 bytes; its S25 diagnostic, 74.810 s and peak RSS 562,147,328 bytes. This supported the user-requested maximum 40 workers on 48 available CPUs and approximately 743 GiB available RAM. Even the declared conservative per-worker 12 GiB cap gives 480 GiB at 40 workers. Actual simultaneous scene branches are bounded by the selected population. Extraction stays one task. The final per-scene timing includes scheduling contention; it is not a 40× speedup claim.

Limits: 3,600 s per diagnostic scene branch, 12 GiB peak RSS, 10 GiB per published output group. Fourier feature bytes are an analytic 1,536 bytes per road row; no GPU/forward/backward/optimizer was executed. Full-source SN row bound is min[N(N−1),32N]; unrestricted road relation bound is R(R−1). S10/S5 child counts use actual component/true-node interval lengths without materializing graphs. Sibling lower bounds use consecutive child pairs; upper bounds allow all siblings. No training wall-time extrapolation is made.

## Measured results and decision

Original parity **PASS for all 37 selected scenes**: 32 stratified training pilot scenes and five additional training stress scenes. Exact full-source endpoint/mask equality covers SN/INT/CON and their collapsed multi-bit rows before road projection. Source/local IDs, entity ordering, road WKB, total length and absolute/relative bbox-center position pass. The dedicated graph completed successfully in **12 min 17.8 s** (87 executed stem/branch targets). Final acceptance is **PASS**; design ID `b6a_f5d6a32cdd09cf5688b0666a`.

### Coverage and accepted artifact audit

Accepted zero-road counts were reverified: training **338/2,421**, validation **144/1,000**, evaluation **1,261/9,000**. Existing S10 B6 evaluation vectors contain exactly one unique **bitwise** vector among the 1,261 zero-road rows; maximum difference is zero. The vectors SHA256 matches the accepted manifest (`2744a81244dae3cf57e0a870f8f3c7c43669d5257766e2b12ef99b9e565b0edc`). No checkpoint loading or inference was executed.

The validation ceiling **(856+1)/1,000 = 85.70%** remains an inference under the existing deterministic tie/self-match protocol, consistent with the dissertation's 85.65%. This does not constitute new verification of the 144 validation query rank distribution: no accepted per-query validation vector/rank payload was located. The selected epoch-90 ledger confirms retrieval loss 1.0110323429107666 and separation margin 0.2867180109024048, but stores aggregate metrics. Segmentation cannot supply absent road information; Stage B should investigate road-containing scenes without changing the accepted model-selection metric.

### Post-bank feasibility and topology discrepancy

Verdict: **POST_BANK_FEASIBLE_WITH_ADDITIONAL_LINEAGE**. Bounded accepted P4 sample: 27 absorbed rows / 27 receiver-view mappings; P5 sample: 44 absorbed rows / 41 receiver-view mappings. All sampled component-ownership checks pass. Donor/source IDs, receiver IDs, original node IDs and perturbed node coordinates survive. The materialized receiver owns its accepted perturbed attributes: assigning donor LANES to absorbed components would change the augmentation policy.

However, `python/augmentation_bank.py` serializes topology `component_index` per source chain, which is not guaranteed to index every clipped MultiLineString geometry part. A later adapter must explicitly expand P3 parent part ranges, retain ownership through absorption and preserve the materialized receiver semantics. The bounded sample is not a certification of the whole bank. No P4/P5 code or bank was changed; pre-bank training has not been selected.

The Original/P4 outside-node discrepancy affects selected scenes. The audit distinguishes a pair sharing an outside node from a pair **also** connected through another node inside the scene. Such existing CON is valid. Only additional pairs missing from Original enter the outside-node counterfactual. The bounded P4 audit finds **58 CON ADD rows across accepted views** matching this counterfactual; this is not 58 unique graph pairs. No canonical fix was attempted. Stage B must explicitly preserve or separately test the accepted view semantics rather than silently changing them.


### Pilot entity growth (measured; 32 scenes, equal-stratum sample)

| Scale | Roads total | Mean | Median | SD | p05 | p25 | p75 | p95 | Max | Total ratio |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Original | 783 | 24.47 | 8.0 | 28.48 | 0.0 | 1.5 | 49.75 | 74.05 | 94 | 1.0 |
| S100 | 1044 | 32.62 | 12.0 | 36.32 | 0.0 | 1.5 | 68.5 | 93.85 | 118 | 1.333 |
| S50 | 1547 | 48.34 | 21.5 | 52.18 | 0.0 | 2.25 | 93.75 | 134.25 | 167 | 1.976 |
| S25 | 2552 | 79.75 | 39.0 | 84.64 | 0.0 | 3.0 | 152.25 | 222.25 | 265 | 3.259 |

### Pilot relation growth (measured)

Ordered R–R pairs are unique mask rows after B6 projection; per-bit totals overlap. R–B/R–P are separately measured **before** projection; both are exactly zero after projection. Sibling fractions below are ratios of summed bit counts, not averages of scene percentages.

| Scale | Policy | R–R pairs | SN bits | INT bits | CON bits | Sibling SN | Sibling INT | Full R–B | Full R–P |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Original | G | 6188 | 6188 | 2606 | 2540 | 0.0% | 0.0% | 16708 | 9900 |
| Original | P-post | 6188 | 6188 | 2606 | 2540 | 0.0% | 0.0% | 16708 | 9900 |
| Original | P-pre | 6188 | 6188 | 2606 | 2540 | 0.0% | 0.0% | 16708 | 9900 |
| S100 | G | 8434 | 8434 | 3130 | 2540 | 6.6% | 16.6% | 18818 | 11596 |
| S100 | P-post | 8400 | 7880 | 3130 | 2540 | 0.0% | 16.6% | 18818 | 11596 |
| S100 | P-pre | 8494 | 7974 | 3130 | 2540 | 0.0% | 16.6% | 18958 | 11702 |
| S50 | G | 13672 | 13672 | 4136 | 2540 | 13.3% | 36.9% | 22808 | 13936 |
| S50 | P-post | 13380 | 11854 | 4136 | 2540 | 0.0% | 36.9% | 22808 | 13936 |
| S50 | P-pre | 13886 | 12360 | 4136 | 2540 | 0.0% | 36.9% | 23348 | 14258 |
| S25 | G | 26168 | 26168 | 6146 | 2540 | 21.9% | 57.5% | 29642 | 17608 |
| S25 | P-post | 23978 | 20442 | 6146 | 2540 | 0.0% | 57.5% | 29642 | 17608 |
| S25 | P-pre | 26572 | 23036 | 6146 | 2540 | 0.0% | 57.5% | 31586 | 18632 |

### Neighborhood effects

Recovered counts include external R–R/R–B/R–P ordered neighbors after symmetrization. Displacement counts use directed pre-symmetrization selections. Mean cross-parent degree and reach below average nonempty-scene means (24 scenes). P-post does not refill any slot and leaves every external G SN pair unchanged.

| Scale | External selections displaced | External SN recovered P-pre | G cross degree | P-post cross degree | P-pre cross degree | G 3-hop reach m | P-pre 3-hop reach m |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Original | 0 | 0 | 5.778 | 5.778 | 5.778 | 231.57 | 231.57 |
| S100 | 463 | 217 | 5.793 | 5.793 | 5.867 | 199.55 | 199.34 |
| S50 | 1527 | 937 | 6.307 | 6.307 | 6.583 | 163.68 | 160.31 |
| S25 | 4920 | 4078 | 6.954 | 6.954 | 7.795 | 131.94 | 129.99 |

### S10/S5 cheap bounds (not realized graphs)

| Scale | Exact children total | Mean | Max | Sibling lower | Sibling upper | Max pressure upper | Fourier bytes estimate | R–R row upper |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S10 | 5815 | 181.72 | 605 | 10062 | 79818 | 44 | 8931840 | 2202046 |
| S5 | 11139 | 348.09 | 1149 | 20710 | 319194 | 88 | 17109504 | 8055668 |

### Physical invariants

All-scene maximum per-parent length error: 1.14e-13 m; Hausdorff support error: 2.91e-11 m. Pilot total observed length: 53724.206366 m, preserved at every scale. Zero-length children: 0; tiny positive pieces (<1 mm) across segmented pilot variants: 2.

### Measured resource summary

Configured workers: 40; computation threads: 1. Maximum scene-branch wall time: 494.469 s; sum of scene-branch times: 3818.597 s (not overall wall time). Peak diagnostic worker-lifetime RSS: 0.471 GiB. Compact diagnostic output: 1,199,721 bytes.

| Measurement | p50 | p95 | Max |
| --- | --- | --- | --- |
| scene_elapsed | 21.792 | 439.3356 | 494.469 |
| serialization | 0.071 | 0.201 | 0.291 |

| Scale | Split p50 s | Split p95 s | Split max s | G relation p50 s | G relation p95 s | G relation max s |
| --- | --- | --- | --- | --- | --- | --- |
| Original | 0.001 | 0.002 | 0.002 | 2.657 | 104.322 | 116.782 |
| S100 | 0.404 | 3.093 | 3.741 | 2.067 | 107.329 | 119.831 |
| S25 | 0.343 | 2.976 | 3.746 | 2.984 | 109.855 | 119.654 |
| S50 | 0.316 | 3.122 | 3.754 | 2.3 | 105.65 | 117.256 |

Times include CPU contention at the configured concurrency. Branch elapsed includes deterministic subdivision replay, metrics, all scales/policies and serialization; graph timing excludes subsequent graph metrics. RSS is process high-water memory, not a precise allocation delta. The one-worker pilot and a during-run snapshot (39 worker processes, ~13 GiB total RSS) support the resource bound. Worker runtime service threads were idle; computation stayed single-threaded. No model forward/Fourier compute benchmark or training-time estimate was performed.

### Interpretation and recommended first scale

Recommend **L=50 m** for Stage B method selection. It nearly doubles road tokens (1.976×) with 2.209× as many G road-pair rows, while S25 grows tokens 3.259× and pairs 4.229×. S50 lowers mean road bbox-center nearest-neighbor distance from 28.49 to 17.11 m and increases mean occupied 50 m bins from 15.92 to 24.42 among the 24 nonempty pilot scenes. These show finer spatial sampling, not improved discrimination. Bbox-center dispersion remains similar (150.57 → 151.83 m).

S50 G includes 1,818 sibling SN bits (13.30% of SN) and 1,526 sibling INT bits (36.90% of INT). P-post removes the former but preserves all latter bits; 1,526 sibling pairs remain because INT is retained. P-pre restores **506 external ordered road–road SN pairs** compared with G/P-post, plus cross-type neighbors (937 recovered R-origin external neighbors in total). S25 has 57.53% sibling INT: finer entities make the graph increasingly dominated by within-parent contacts even after sibling SN removal.

CON stays exactly **2,540 ordered bits** in the pilot and **940** in the separate stress set at every scale/policy. Same-parent CON is zero throughout these selected scenes. Original node incidence is preserved, no synthetic cut enters CON, and no false sibling CON clique occurs. S50 has 37 summed graph components and two isolated road entities under all three policies; its maximum degree is 25 (G/P-pre) and 23 (P-post). Degree may exceed 16 because selection is symmetrized and other relation bits remain.

The mean three-hop bbox-center reach decreases from 231.57 m (Original) to 163.68 m (S50 G), or 160.31 m (P-pre). Segmentation therefore changes both local resolution and the physical span of a fixed-depth graph. It also repeats semantics and changes pooling weights. These remain coupled intervention mechanisms; entity count alone does not establish H1. Stage A characterizes the H4 relation confound but does not determine H1 versus H2/H3 or retrieval benefit.

Keep **G versus P-pre** as the primary relation comparison. P-post remains scientifically useful as a secondary diagnostic: it isolates removing sibling SN without giving external candidates the vacated slots. It is not required in the minimum first training block. Keep S100 as a lower-dose structural reference and S25 as a stronger sensitivity candidate; do not independently tune either. Exclude S10/S5 from the initial training block and broad graph materialization. Their counts are 7.427× / 14.226× Original with much greater potential sibling pressure; this is sufficient to defer them, not proof that they are computationally impossible or scientifically useless.

### Stage B gates and verdict

**READY_FOR_STAGE_B_METHOD_SELECTION**. Stage A structural acceptance is PASS. This is **not authorization or readiness to launch training immediately**. The minimum future block is `B6-original`, `B6-S50-G`, `B6-S50-Ppre`, conditional on:

1. Implementing and independently validating the post-bank component/attribute/node lineage adapter, or explicitly selecting a different augmentation order with its changed invariants documented. Do not silently choose pre-bank training.
2. Resolving treatment of the accepted P4 outside-node CON discrepancy in an experimental view contract; preserve historical artifacts. Source-node visibility and absorbed receiver ownership need paired-view tests.
3. Issuing new experimental scene/view/model-ready/prepared/Fourier/relation identities and S09 authority; do not relabel P2/P3/P4/P5/P6 or existing S09/S10/S11/S12 products.
4. Freezing accepted B6 d=d_c=256, populations, scene/view identities, negative policy, seeds, optimizer/LR schedule, EMA, queue, objective, augmentation policy and model settings. No per-L retuning. Validate memory and training-step cost only in a separately authorized bounded pilot.
5. Reusing the accepted validation selection contract: minimize retrieval loss; absolute loss difference strictly <1e-4 defines equivalence, then maximize separation margin, then earlier epoch; four-event patience with the accepted loss-decrease reset rule. Report MRR, HIT@1, existing HIT@K and selected epoch without using new road-stratified diagnostics as selectors.

Future analyses should use the existing S11/S12 road length/density, orientation, dispersion, degree and network/intersection descriptors where available, and paired nonempty-scene diagnostics with the same gallery. Keep the zero-road population unchanged. A positive B6 result does not justify an FM representation change without a separate experiment; the full-source results here are diagnostic only.

Training is NO-GO if Original parity, geometry/lineage invariants, immutable artifact separation or the fixed scientific protocol cannot be maintained. Stop on an ambiguous absorbed component or a requirement to repair canonical topology. A structural PASS says nothing about whether segmentation will improve retrieval.

### Validation, limitations and preservation

- R parse and config/schema validation PASS; focused B6 testthat tests PASS; relevant spatial-observation and scene-cache regression suites PASS.
- Python compile PASS; focused lineage plus existing augmentation-bank/RNG pytest suites: **28 passed**.
- `tar_manifest()` 15 targets; graph 38 dependency edges, one weak component, acyclic; dedicated `tar_validate()` PASS.
- Dedicated Stage A execution PASS; subsequent execution skipped all 87 valid targets. SHA256 comparison before/after confirms **436 experimental files byte-stable**. Every scene/scale also independently reruns subdivision and checks identical child structures during generation; cached rerun is not presented as recomputing all graph distances.
- Dependency HTML regenerated with current manifest/store. `git diff --check` PASS.
- Numerical endpoint-sliver and outside-node audit bookkeeping failures were corrected and retested before the accepted run. An early slow exact-distance implementation was interrupted and replaced with a parity-tested indexed broad phase. Earlier partial experiment roots are not accepted results.
- One validation rerun used the deprecated targets `summary` reporter, which automatically selected `balanced`; this operational warning did not affect results.
- Validation per-query tied ranks unavailable; only existing evaluation zero-road embeddings verified. No full-bank lineage certification, new Fourier cache, GPU benchmark, model-forward benchmark or training-time extrapolation.
- `cost_summary.json` reports diagnostic serialization/output bytes, not a new accepted model-ready input size. The geometry payload estimates below are explicitly analytic. Full-source non-road geometry dominates preprocessing time here, so near-flat graph-build timings cannot predict road-only model cost.
- R 4.5.3, sf 1.1.0 (GEOS 3.14.1 / GDAL 3.12.2 / PROJ 9.7.1), data.table 1.17.8, arrow 22.0.0, targets 1.12.0, crew 1.3.0, igraph 2.2.3, testthat 3.3.1, jsonvalidate 1.5.0.

Final output QC confirms 148 scene-scale rows, 444 scene-scale-policy rows, unique child IDs, positive chainages, exact child/lineage row agreement, zero-road invariance and zero projected B/P edges. All experimental publication manifests PASS.

No training, checkpoint creation, canonical artifact publication, dissertation edit or reduced-branch change occurred. The authorized `~/fuse` B6 worktree contains the task source/config/test/report changes. The exact final commit SHA is reported in the completion message; entry/input SHA above remains the reproducible baseline.

### Analytic serialized geometry and encoder work proxies

2D WKB LineString bytes = 9 + 16×coordinate count. Multipart parents add container/part headers; Original is bounded below/above. Children are LineStrings, so their WKB byte formula is exact for uncompressed geometry only. IDs, attributes, relations, compression and container metadata are excluded. Fourier interval-frequency work is approximately (coordinates−parts)×128, with a separate 384-float32/1,536-byte output row per road. This is an operation/size estimate, not a measured encoder time. At fixed d, future sparse model work depends on both N d² and E d; no wall time is projected.

| Scale | Geometry WKB bytes lower–upper | Fourier output bytes | Interval×128 proxy |
| --- | --- | --- | --- |
| Original | 48,903–55,959 | 1,202,688 | 234,496 |
| S100 | 59,572–59,572 | 1,603,584 | 267,776 |
| S50 | 80,195–80,195 | 2,376,192 | 332,160 |
| S25 | 121,400–121,400 | 3,919,872 | 460,800 |

### Pilot IDs (training only)

| Scene ID | Stratum | Original roads |
| --- | --- | --- |
| `scn_0c757b954b09a7bf328f4e62` | 0 | 0 |
| `scn_d349c00c012d1cb0f4f94550` | 0 | 0 |
| `scn_27ad2804f26e0d2a8243c33f` | 0 | 0 |
| `scn_dc0e9aedcea903282099cd03` | 0 | 0 |
| `scn_c02b8328d296f123c361fbf3` | 0 | 0 |
| `scn_174df9b77f44ee3766ca01d9` | 0 | 0 |
| `scn_12ebeab0b440b7ab6fd2d86c` | 0 | 0 |
| `scn_9232d36e5157090340d39df0` | 0 | 0 |
| `scn_9696eeb20506b95cc36a5b1c` | 1-8 | 2 |
| `scn_0a7dd27cd915656567c1139d` | 1-8 | 2 |
| `scn_e4fabdfba93e2743810326a0` | 1-8 | 4 |
| `scn_c85eb7f46a8592dfbf495882` | 1-8 | 2 |
| `scn_25f956536f512560cb84d833` | 1-8 | 5 |
| `scn_15516ed8bd4e2eb809aec109` | 1-8 | 5 |
| `scn_329e9c90c43564916dd075f4` | 1-8 | 7 |
| `scn_6626e29fa051f854df50b500` | 1-8 | 2 |
| `scn_eb3c7d83a6e1a90ceac841ae` | 50+ | 53 |
| `scn_6577adc6f39ed3cab7202950` | 50+ | 94 |
| `scn_ade658f5901daf491fcb6ff5` | 50+ | 70 |
| `scn_327d2861858ba3c92d23d3cc` | 50+ | 68 |
| `scn_4674fbf166572e8be199b4cf` | 50+ | 59 |
| `scn_c4ac713e5acdfaaf46baf96d` | 50+ | 79 |
| `scn_e95cc1f329f756fbb876b236` | 50+ | 53 |
| `scn_0ed48e49dd88db564e90549c` | 50+ | 52 |
| `scn_bc9264feecbcbe03317ad027` | 9-49 | 49 |
| `scn_3d579ad8720addc9e2bf9805` | 9-49 | 39 |
| `scn_2e5cec036723d1deb3929bc0` | 9-49 | 9 |
| `scn_997807ff7272323d5174a1e6` | 9-49 | 26 |
| `scn_7690d0b6ea66c604896ea955` | 9-49 | 29 |
| `scn_3907bc5d70bd31fe97249228` | 9-49 | 20 |
| `scn_2f8ea4fa28080911bf95135f` | 9-49 | 13 |
| `scn_e8c9b5c83903234c2e0c2d05` | 9-49 | 41 |

### Separate stress sample and coverage

| Tag | Scene ID / coverage |
| --- | --- |
| longest_parent | `scn_5dcc929324ee80229d989442` |
| highest_road_count | `scn_6db4277538786e14f46dd933` |
| most_multipart | `scn_80e4d92cf54755ac7dadfc5d` |
| boundary_clipping | `scn_0001e1ea41cf9fe111b1ca35` |
| zero_roads | `scn_0051bbd6f0c666f04db744a3` |
| loop/retracing | Both `scn_5dcc929324ee80229d989442` and `scn_80e4d92cf54755ac7dadfc5d`; also explicit closed/retracing fixtures |
| original high-degree junction | 19 selected scenes; maximum degree 4; T/four-way fixtures |
| shared outside node | 16 selected scenes; 100 additional ordered pairs across all selected scenes; four pair/node rows already connected inside excluded |
| tied/near-tied SN distances | Exact/quantized near-tie fixtures with >16 eligible destinations; no separate population census of real ties |
| >16 sibling candidates | 20 adjacent 5 m child fixture verifies top-k pressure and P-pre/P-post; fine-scale population bounds only |

The last two stress conditions are controlled fixtures, not additional randomly sampled scenes. Full observed topology tags are in `topology_audit/stress_observed.parquet`. Stress-only graph/entity metrics remain available under `group=stress` and are excluded from every pilot growth table above.

## Stage B preparation handoff (2026-10-02)

The isolated Stage B preparation is documented in [the Stage B readiness report](20261002_b6_stage_b_method_selection_and_readiness.md). Full accepted K8/query lineage resolved 693,292 materialized parts with zero ownership ambiguity; Original prepared-control parity passed 22,368/22,368 entries. An accepted off-support source-node CON requires a child-incidence methodology decision before S50 input publication. The user explicitly deferred the GPU pilot while authorizing continued lineage/parity/contract preparation. Verdict: `NEEDS_METHOD_DECISION`. Stage A measurements and accepted artifacts are unchanged.
