# Retrieval-Only 10K Gallery Implementation

## Verdict and scope

**RETRIEVAL_ONLY_10K_GALLERY_IMPLEMENTATION_PASS**

Report created at 20260906_0024 Asia/Seoul. Scientific production completed on
2026-09-05 at 23:31:12 KST. Commit/push and remote synchronization are the final
publication steps after this report; their outcome and commit SHA are reported
in the completion message, not presumed here.

Prompt summary: implement an isolated supplementary retrieval gallery containing
the accepted 1,600 evaluation scenes plus exactly 8,400 deterministic off-grid
additions, for all eight frozen models and the same ten accepted queries. Run
nested pilots before production, preserve canonical scientific authorities, add
inspector support, validate, report, and commit/push Fuse reduced only.

- Audit authority: [20260905_1617_evaluation_10k_expansion_feasibility_audit.md](20260905_1617_evaluation_10k_expansion_feasibility_audit.md), verdict CONDITIONAL.
- Starting Fuse branch: reduced, clean and synchronized; HEAD 41e159f4ba3b12fa0f3d7411a09d3b04116da7d8.
- Dissertation: reduced, HEAD 989c19d98e64ec129dc53b761c58a4d961fc3983; clean before and after, never edited.
- Canonical split remains **2,421 training / 400 validation / 1,600 evaluation**.
- Supplemental split is retrieval_only: **8,400** distinct new scenes.
- Union: **10,000** distinct scene IDs, canonical P10 order first, continuation-stream order second.
- No canonical evaluation replacement, augmentation, downstream preprocessing, model selection, or held-out metric redefinition.

## Immutable authorities

Final preservation compared all **7,134 protected files** with the pre-pilot
snapshot, byte for byte through SHA-256. The mid-production check also passed.
The protected snapshot is recorded in the validation receipt with SHA-256
4b71c774972f603fed682468487fff8755f68e8714ee8b8e660b5ba4f9e6a733.

| Authority | Preserved identity |
|---|---|
| P10 acceptance | p10acc_6e5071beee7616750dec7907 |
| Ten-query contract | p10qq_dd7d0775f5809a793575342b |
| P11 dataset | p11ds_39607da2de792ad6b3c9bb30 |
| P11-C | p11c_e78d7c740edc49f1f646ebc3 |
| P11-E | p11e_047e764ed7467b72ebe846df |
| P11-G | p11g_b1ad31498120f8f4a9445958 |
| P9 selected full model | cfg_d128 |

The latest dissertation methodology and targets blueprint were inspected before
implementation. The closed eight-model scope is supported by
blueprint/p9_v2/roadmap.md and the existing inspector's comparison purpose.
The roadmap's older next-step P11 text was not treated as authorization to rerun
P11; the user-pinned accepted P11 identities remain authoritative.
All-eight scope was frozen before seeing enlarged-gallery retrieval results.

## Supplementary authority and outputs

Production root, abbreviated ROOT below:

/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/retrag_29e75a5e81df82e0c3d93783

| Artifact | Identity or relative path |
|---|---|
| Methodology | retrag_29e75a5e81df82e0c3d93783; methodology.json |
| Methodology SHA-256 | f2d649ca25d35f5a0ab9bab4c4a962dfaf091d708dca7cb451ad3a1582bd681f |
| Supplemental index | index/supplemental_scene_index.parquet |
| Scene cache | retrcache_6755d530cbe7b60cbbbe9e5b |
| Prepared originals | retrpi_0ddeeca3b8b730973d185826 |
| Geometry cache | retrgeo_d03712c07836ef13ff880041 |
| Union | retrunion_cb9b276f6c7ec08332a12779 |
| Rankings | retrrank_7b941d2c9cc6280d756cfb3a |
| Inspector | retrieval_inspector_6771ec13a6934545e1c0faef |
| Supplementary acceptance | **retr10k_0672df44ea0fb5adceafbec9** |
| Acceptance SHA-256 | 122af70d8195df982d8d64c4443fe311dd1b1652ce7d3dd35b45fee8796619e8 |

[Supplementary acceptance](/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/retrag_29e75a5e81df82e0c3d93783/acceptance/retr10k_0672df44ea0fb5adceafbec9.json)
binds eleven parent hashes: methodology, index, spatial truth, scene cache,
prepared inputs, geometry, embeddings, union, rankings, inspector, and validation.
Its strict schema explicitly requires unchanged canonical P10/P11, original-only
retrieval, no reopened model selection, and zero prohibited-work counts.

The methodology binds the accepted source snapshots, model/checkpoint identities,
preprocessing/category files, historical off-grid source, accepted P10 geometry
contract, pilot evidence, and implementation hashes. A final frozen-implementation
check passed after production. No frozen scientific implementation was edited
after production started.

## Deterministic continuation proof

R/retrieval_gallery.R replays the historical generator recovered from
git show 93b9e5f^:R/research_off_grid_source.R. Historical source implementation
SHA-256: 9cd90ae7e4f1cb8d02c80016df2312212cfc87f0e07709af678b2a9ba213858f.

- R RNGversion 4.0.0; Mersenne-Twister / Inversion / Rejection; seed 26082501.
- The historical 8,192-candidate batching and interleaved x/y draw order are retained.
- First batch: exactly 4,257 eligible candidates.
- Original first 2,000 accepted coordinates reproduce exactly as doubles.
- Additions consume accepted stream ordinals 2,001 through 10,400, including all
  2,257 previously unused eligible positions from the first batch.
- Total replay draws: 24,576 across three batches. Two complete continuation
  replays produced the same 8,400-row index, including exact coordinates.
- Index SHA-256: 0b629ee37249a653ae8c5cf24c35ab217e4d18dbf5a121c670cab09d56a3ce0a.
- Scene IDs use retrscn_ plus a deterministic content digest; role is retrieval_only.
  IDs and provenance retain accepted-stream ordinal, candidate ordinal, and raw
  float64 coordinates. No timestamps, temporary paths, rounding, reseeding,
  added spacing, or duplicate-resampling rule enters scene identity.
- Minimum distance to training centers: **50.0202741279123 m**, satisfying 50 m.
- Exact coordinate duplicates: 0; scene-ID collisions: 0.
- Seoul-domain violations: 0; complete 500 m footprint buffer violations: 0.
- Existing training, validation, and evaluation coordinates and IDs are unchanged.
  No additional validation-distance rule was invented.

Proof receipt: runtime/retrieval_gallery/pilot_sampling_v2_20260905 under
/mnt/hdd002/dhnyu/fusedata. The historical approved off-grid Parquet SHA-256 is
77c035505a2a0d22fb3aefff845c65b505d69b9ca89b5fda9ef36cc2e90177e4.

## Pilot gates and correction

All production gates passed before the 8,400-scene spatial run. Nested populations
were exact 100/500/1,000 prefixes, not unrelated samples. Pilots used separate
noncanonical runtime directories.

An early adapter defect was found and corrected before production: the accepted
relation builder sorts scene IDs, while its summary helper pairs results with
the supplied scene-specification order. The first supplemental adapter supplied
stream order. This misassigned per-scene summary rows even though edge tables
were keyed correctly. The initial 100 pilot and its reference comparison were
invalidated, and the initial 500 run was stopped.

The correction sorts each processing shard lexically, preserving stream order
in the index and union. Strict keyed edge/type/node-count checks now reject
misaligned summaries. All accepted canonical shard specifications already use
the required lexical order. No accepted relation kernel or relation semantics
were changed. Fresh corrected 100, 500, and 1,000 pilots passed.
The invalidation is recorded in pilot_ordering_invalidation_20260905.json.

Independent reference parity passed on four real pilot scenes spanning all five
relation types. SN, CNT, WIT, INT, CON, distance/predicate/tie and multi-relation
contracts remain unchanged. The relation implementation SHA-256 remains
5a24d243fa2fe75857bd28fae2a91346ef76b0850e77346079ee9c5102c746ac.

### Nested pilot measurements

Seconds are measured elapsed time unless explicitly labeled worker-seconds.
Spatial stages execute within shards; their worker-seconds must not be summed
and presented as parallel makespan.

| Measurement | 100 / 4 workers | 500 / 8 workers | 1,000 / 16 workers |
|---|---:|---:|---:|
| Center replay prefix, seconds | 0.054 | 0.049 | 0.053 |
| Spatial makespan, seconds | 975.114 | 1,873.914 | 1,927.807 |
| Spatial scenes/sec | 0.103 | 0.267 | 0.519 |
| Membership, worker-seconds | 34.363 | 177.825 | 362.858 |
| Vector extraction, worker-seconds | 70.712 | 357.935 | 757.137 |
| Topology, worker-seconds | 8.824 | 43.971 | 91.550 |
| Relations, worker-seconds | 2,926.451 | 11,570.682 | 23,871.895 |
| Raster/context, worker-seconds | 103.493 | 543.570 | 1,138.780 |
| Original serialization, seconds | 0.184 | 0.849 | 1.689 |
| Tensor preparation, seconds | 95.866 | 250.403 | 255.818 |
| Batch assembly, seconds | 1.399 | 7.033 | 13.804 |
| Geometry preparation, seconds | 32.389 | 138.930 | 278.951 |
| Eight-model inference, seconds | 15.457 | 21.522 | 27.281 |
| Render all pilot scenes, seconds | 5.962 | 29.153 | 58.056 |
| Spatial shard p50 / p95, seconds | 761.765 / 944.013 | 629.101 / 997.271 | 637.688 / 1,043.130 |
| Tensor shard p50 / p95, seconds | 81.274 / 92.619 | 79.791 / 102.079 | 79.754 / 102.268 |
| Spatial peak aggregate RSS, GB | 3.080 | 5.780 | 11.529 |
| Input-stage peak aggregate child RSS, GB | 14.085 | 14.517 | 21.488 |
| Vector entities | 101,524 | 498,195 | 1,015,499 |
| Relation edges | 1,262,160 | 5,722,456 | 11,477,772 |
| Vector entities/worker-second | 1,435.7 | 1,391.9 | 1,341.2 |
| Relation edges/worker-second | 431.3 | 494.6 | 480.8 |
| Spatial output bytes | 56,214,889 | 266,487,641 | See per-stage receipt |
| Input/cache/geometry/render payload bytes | 511,340,315 | 2,505,318,755 | 5,059,075,301 |
| Input-stage payload MB/scene | 5.113 | 5.011 | 5.059 |

The complete benchmark receipt includes each stage's bytes, scenes per
worker-second, shard p50/p95, every model's throughput/forward/input-wait/VRAM,
and per-GPU utilization. It is hash-bound by the methodology:
runtime/retrieval_gallery/benchmark_summary_20260905.json.

Corrected receipts:
- pilot100_v2_20260905/pilot_result.json and pilot100_v3_inputs_20260905/input_pilot_result.json.
- pilot500_v2_20260905/pilot_result.json and pilot500_v2_inputs_20260905/input_pilot_result.json.
- pilot1000_v2_20260905/pilot_result.json and pilot1000_v2_inputs_20260905/input_pilot_result.json.
- Reference parity: pilot100_v2_parity_20260905.json.
- Reviewed production gate: approved_pilots.json.

The 500-to-1,000 comparison increased spatial throughput by 1.94x with 8-to-16
workers. Only then was a bounded 1,000-scene / 32-worker pilot run: **1,439.604 s**,
peak aggregate RSS **22.579 GB**, 25.3% lower elapsed time than 16 workers.
Full 16-vs-32 parity passed: **520/520 Parquet tables byte-identical** and all
**40 raster shard array-hash/attribute records identical**. Receipts are
pilot1000_w32_20260905/pilot_result.json and worker_16_32_parity_20260905.json.
Production therefore uses 32 spatial workers, not an unmeasured convention.

Serialization roundtrip, vector/source access, relation predicates and summaries,
raster support, prepared inputs, all eight model forwards, finite normalized
embeddings, and deterministic bounded repeats passed at each corrected scale.
Verified intermediate per-scene tensors were discarded only after batch checks;
100-scene embeddings before/after this storage cleanup were exactly equal.

## CPU and GPU execution

Hardware: 24 physical / 48 logical CPU cores, approximately 754 GiB RAM, and two
RTX A6000 GPUs with 49,140 MiB each. Source handles are independent per spatial
process; native/BLAS/OpenMP/Arrow/data.table threads are bounded to one per worker.

| Stage | Backend and chosen configuration |
|---|---|
| Sampling, membership, clipping, topology, relations, raster | CPU, 32 processes, deterministic 25-scene shards |
| Scene serialization | CPU, accepted deterministic v3 tar layout |
| Tensor preparation | CPU, 16 processes from the completed 1,000-scene input pilot |
| Geometry/Fourier | Two GPUs, task sharding, accepted encoder implementation/math |
| Frozen model inference | Two persistent GPU processes, task-level model sharding, no DDP |
| Ranking/geographic masks | CPU NumPy/BLAS, query-by-gallery only |
| Inspector rendering | CPU, deduplicated required scenes; browser loads assets lazily |

Inference remains batch **8**, **float32**, inference mode, AMP off, TF32 off,
accepted deterministic settings, eight loader workers per GPU, pinned memory,
prefetch two. Optional batch-16/32 experiments were not needed: baseline inference
was already small relative to spatial processing, and no precision/batch parity
risk was introduced merely to chase utilization.

For the 1,000 pilot, per-model throughput was 164.8 to 255.3 scenes/sec; FM forward
time was 2.706 s, input wait 1.810 s, and peak allocated VRAM 572,355,072 bytes.
The full per-model pilot table is in the bound benchmark receipt.
For the 100 and 500 pilots, mean inference GPU utilization was respectively
3.70/2.45% and 10.03/8.49% on GPU0/GPU1; short-run startup and input overhead
dominated. Geometry utilization was approximately 36-38%.

Production measured GPU utilization:
- Geometry GPU0/GPU1 means 38.43% / 38.25%, p95 40% / 40%;
  peak used VRAM 499 / 507 MiB.
- Inference means 18.22% / 15.37%, p95 43% / 45%;
  peak used VRAM 1,761 / 1,783 MiB.
- Overall observed aggregate process RSS peaked at **23.054 GB**; host I/O wait
  p50 0.0%, p95 0.2%, max 4.2%. The observational process monitor includes its own
  small overhead and started after spatial launch, so this is an observed peak,
  not a claim of continuous instrumentation from the first millisecond.
- Telemetry: ROOT/geometry/gpu_samples.csv, ROOT/embeddings/gpu_samples.csv and
  runtime/retrieval_gallery/production_resources_retrag_29e75a5e81df82e0c3d93783.jsonl.

## Actual production workload

Production invocation: 2026-09-05 19:45:09 KST; completed 23:31:12 KST.
Full targets elapsed time: **3 h 46 m 3.4 s**, below the reviewed 5.5-hour planning
allowance (4.842-hour linear pilot projection). No failed production shards;
all 336 retry counts are zero.

| Stage | Measured kernel/makespan seconds | Targets task seconds where different |
|---|---:|---:|
| Center continuation proof including nested checks | 1.466 in preproduction replay | Authority gate/hash binding 54.9 |
| All spatial stages, 336 shards | 8,780.106 | 8,783.8 |
| Original v3 serialization/cache | 31.675 | 34.6 |
| Tensor preparation | 1,724.355 | Combined preparation 1,841.6 |
| Batch assembly | 114.339 | Included above |
| Geometry/Fourier | 2,211.120 | 2,219.5 |
| All-eight inference | 153.863 | 185.7 including checks/bindings |
| Union construction and old-row verification | Task timing | 16.3 |
| Ranking loop, tables and diagnostics | 1.421 | 25.6 including canonical baseline setup/checks |
| Inspector rendering | 372.142 | 375.9 |
| Final ranking/browser/preservation validation | Task timing | 19.0 |
| Acceptance publication | Task timing | 2.8 |

Pure center generation was measured before production and the proven index was
copied immutably; it was not misleadingly timed as a second independent sample.

Spatial output: **8,189,551 entities**, **93,720,442 relation edges**.
Spatial shard p50/p95: **765.552 / 1,184.767 s**.
Tensor shard p50/p95: **79.067 / 105.046 s**.

| Spatial substage | Worker-seconds | Shard p50 / p95 seconds |
|---|---:|---:|
| Membership | 4,372.627 | 13.623 / 14.845 |
| Vector extraction | 9,348.726 | 27.446 / 37.773 |
| Topology | 1,169.821 | 3.500 / 4.222 |
| Raster/context | 13,709.398 | 41.843 / 49.241 |
| Relations | 236,290.617 | 678.893 / 1,097.368 |

Relation construction remains dominant. Existing source spatial queries, parsed
shard-local geometry and accepted assembly kernels are reused; no new algorithm
or changed predicate was introduced. Further index/geometry/vectorization work
is optional future optimization requiring independent exact parity. GPU spatial
processing, DDP, ANN/FAISS, and full NxN matrices were unnecessary complexity.

## Frozen model bindings and counts

Every model has exactly **8,400 x 128 float32 supplemental rows** and
**10,000 x 128 float32 union rows**. The accepted original 1,600 P10 rows were
copied directly from the tail of the accepted 4,800-row NPZ; no canonical
re-inference occurred. First-1,600 union bytes match the accepted arrays exactly.
Checkpoint identity and SHA, row ordering, scene mapping, finiteness, and
first-batch deterministic repeat were verified for every model.

| Model | Frozen checkpoint | Production wall / forward / input-wait seconds |
|---|---|---:|
| cfg_d128 | p9ck_56195e9ea3cd45d80cf5e23c | 42.425 / 18.709 / 12.312 |
| A1: cmp_a1_geometric_core | p9ck_37979e7a36f6b189ecf674d0 | 33.513 / 7.662 / 12.483 |
| A2: cmp_a2_semantic_enriched | p9ck_74cc9b14a7d294463bfd5a9c | 35.475 / 9.179 / 13.177 |
| A3: cmp_a3_object_context_enriched | p9ck_c0784d438146deeaee04fd34 | 35.472 / 9.658 / 13.073 |
| A4: cmp_a4_raster_complete_non_relational | p9ck_a71bec2d0fae827ee7c97879 | 37.243 / 11.436 / 13.097 |
| A5: cmp_a5_relation_type_agnostic | p9ck_0ee547be5473315d457bf104 | 42.557 / 18.209 / 13.234 |
| SSV: cmp_ssv_like | p9ck_388bce700e35c96012e77b1a | 31.058 / 9.374 / 20.074 |
| DS: cmp_ds_like | p9ck_65cc78a1a97330f3af05fba4 | 29.700 / 1.078 / 26.796 |

These model times overlap across GPUs and exclude some process/checkpoint setup;
their sum is not the total inference makespan. Peak allocated VRAM was 0.085
to 0.585 GB per model. Unit norms are within 1.8e-7 of one. No zero-vector or
low-entity scene was dropped.

## Retrieval and paired diagnostics

Exact accepted cosine definition: already normalized accepted original embeddings
are validated, not normalized a second time. A 10 x 10,000 score matrix and
10 x 10,000 float64 geographic-distance matrix are sufficient. Self is removed
by scene ID; ties use scene ID ascending after descending similarity. Non-local
retains distances >= 2,000 m, including the exact boundary.

All **80 standard query/model combinations have 9,999 candidates**.
All **80 non-local combinations** have the following query-specific counts,
identical across models:

| Fixed query scene ID | Non-local candidates |
|---|---:|
| scn_c0ba3bcd99b3f90218d1b3bc | 9,873 |
| scn_4960049e9b3a46f311538dbb | 9,825 |
| scn_643b50dae130626079585c93 | 9,792 |
| scn_8c772d2081968ea7eeea0c80 | 9,828 |
| scn_a4da2c5a766af8059e020492 | 9,784 |
| scn_ac42914e0e7cb935334e2873 | 9,842 |
| scn_c00ff67c4e81b7220deb863e | 9,795 |
| scn_d1f32d62dac7151c054d573b | 9,795 |
| scn_e64bbc2a87d2debcc8453f3d | 9,818 |
| scn_fc02fd6d3d4bc8637b16f12b | 9,781 |

Sixteen Parquet ranking artifacts contain **1,584,984 rows** total, all checked
against deterministic reruns, including score and distance equality.
Each row records query, rank, candidate ID, float32 similarity, distance and
canonical/supplemental source. Manifest records gallery/candidate counts and
self-exclusion. Ranking identity binds file hashes and the query contract.

Read-only final microbenchmark: exact ranking, including geographic masks and
both settings, took **32.85-38.56 ms per model** for all ten queries across three
repeats. No full 10,000 x 10,000 matrix or ANN index was constructed.
One union embedding matrix is 5.12 MB of float32 data; one query score matrix is
0.40 MB. A needless full pairwise float32 matrix would be 400 MB.

The following are descriptive means over the same ten fixed queries, not model
selection scores. Top-k columns are mean fractions of the old top-k retained.
Supplemental-best counts are out of ten. Old best remains in top-100 for all
160 paired cases.

| Model | Setting | Top-10 overlap | Top-100 overlap | Mean old-best new rank | Old best in top-10 | Supplemental best |
|---|---|---:|---:|---:|---:|---:|
| FM | Standard | 0.12 | 0.153 | 7.5 | 8/10 | 10/10 |
| FM | Non-local | 0.16 | 0.145 | 6.0 | 9/10 | 9/10 |
| A1 | Standard | 0.12 | 0.152 | 8.1 | 8/10 | 9/10 |
| A1 | Non-local | 0.12 | 0.156 | 7.6 | 8/10 | 8/10 |
| A2 | Standard | 0.15 | 0.155 | 6.4 | 9/10 | 10/10 |
| A2 | Non-local | 0.17 | 0.148 | 5.6 | 10/10 | 10/10 |
| A3 | Standard | 0.16 | 0.160 | 7.1 | 9/10 | 9/10 |
| A3 | Non-local | 0.14 | 0.150 | 7.1 | 8/10 | 9/10 |
| A4 | Standard | 0.14 | 0.164 | 5.1 | 8/10 | 8/10 |
| A4 | Non-local | 0.17 | 0.161 | 4.3 | 8/10 | 8/10 |
| A5 | Standard | 0.18 | 0.167 | 5.4 | 9/10 | 10/10 |
| A5 | Non-local | 0.19 | 0.156 | 4.8 | 9/10 | 6/10 |
| SSV | Standard | 0.15 | 0.169 | 6.3 | 7/10 | 7/10 |
| SSV | Non-local | 0.15 | 0.171 | 7.1 | 7/10 | 8/10 |
| DS | Standard | 0.20 | 0.185 | 4.9 | 9/10 | 9/10 |
| DS | Non-local | 0.22 | 0.177 | 7.0 | 7/10 | 9/10 |

All 160 records, including each old-best new rank, top-10/top-100 overlap,
new-best identity/source/similarity/distance, rank-1 minus rank-10 gap, and
similarity min/quartiles/max, are in ROOT/rankings/stability_diagnostics.json.
For FM, mean new-best similarity/distance is 0.83365 / 1.103 km standard and
0.70838 / 8.627 km non-local; mean rank-1/rank-10 gaps are 0.18294 and 0.08549.
These observations establish gallery-size sensitivity of the retrieved examples,
not a new conclusion about model superiority. Qualitative scientific analysis
and dissertation interpretation are deliberately deferred.

## Inspector

[Open the dual-gallery inspector](/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/retrag_29e75a5e81df82e0c3d93783/inspector/index.html).

Command: python tools/render_retrieval_inspector.py --supplemental.
The new small tools/retrieval_inspector/supplemental_output.json pointer verifies
acceptance SHA/ID and inspector binding before returning the static HTML.
The old example_output.json and default canonical generation mode are unchanged.

The explicit selector offers Canonical 1,600 and Supplemental 10,000 with the
same ten queries, eight models, standard/non-local setting, vector layers,
LC/DEM, attributes, and five relation counts.
Rank bands remain rank 1, ranks 2-11, deterministic central ten, and final ten;
middle/bottom positions derive from each actual candidate count.

Only **3,622 unique required scenes** were rendered, not all 10,000. Existing
**1,342 canonical scene assets are byte-identical** to the old inspector assets.
Assets are keyed by scene ID and bound render implementation, reused across
query/model/setting combinations and loaded lazily in the browser.
Supplemental district metadata is explicitly Unavailable; no P11 work is needed.
Canonical district metadata is read from existing accepted artifacts only.

Chromium 148.0.7778.96: 42 gallery/model/setting/query states checked, no console
or page errors, no missing required assets, nonblank canvases. Desktop 1600x1000
and mobile 390x844 screenshots were visually inspected. Mobile controls fit;
the five-column comparison remains horizontally scrollable to preserve readable
maps. Screenshots are ROOT/validation/{canonical_desktop,supplemental_desktop,
supplemental_mobile}.png. No dev server is needed for this static inspector.

## Storage and source support

Preproduction available storage was approximately **20,336 GB**, comfortably
above the enforced 120 GiB working-headroom gate. Reviewed persistent projection
was 46.98 GB. Actual complete production root is **44,378,110,006 bytes
(44.378 GB decimal)**; data are external to Git.

| Component | Bytes | Decimal GB |
|---|---:|---:|
| Membership | 52,419,382 | 0.052 |
| Vector observations | 1,741,359,496 | 1.741 |
| Topology | 41,885,614 | 0.042 |
| Relations | 2,037,700,570 | 2.038 |
| Raster/context | 523,531,449 | 0.524 |
| Entire spatial root including QC/specs/logs | 4,450,940,169 | 4.451 |
| Supplemental original v3 scene cache/catalog | 4,404,269,221 | 4.404 |
| Prepared model inputs | 21,460,634,786 | 21.461 |
| Geometry cache | 12,583,530,101 | 12.584 |
| Supplemental embeddings and metadata | 37,657,338 | 0.038 |
| Union arrays/catalog/mapping | 45,924,806 | 0.046 |
| Ranking tables/manifests/diagnostics | 33,864,730 | 0.034 |
| Inspector assets/static files/manifests | 1,357,571,149 | 1.358 |

Spatial subcomponents are included in the spatial-root total, not additional
storage. Validation's eight main stage totals are 44.374 GB; the 44.378 GB full
root also includes methodology/index/validation/acceptance. Prepared inputs and
geometry dominate. Own transient per-scene tensors (21,516,005,376 bytes) were
removed only after checked batch publication. Pilot artifacts remain isolated
outside Git; the production total excludes those retained audit fixtures.

All twelve accepted study inventory source files were SHA-verified, including
Seoul boundary/buffer, B/R/P, LC/DEM and official-grid support. No source version,
category vocabulary, preprocessing statistics, or missing-value rule was refit.
All spatial QC passed. Whole-scene nodata counts: LC 0, DEM 0. Object-context
nodata counts: LC 210,212, DEM 138,039; these use the existing accepted masks and
preprocessing rules, not a new scene exclusion or imputation policy.
Raster QC warnings: 0.

## Implementation, restart, and validation

New isolated pipeline:
- _targets_retrieval_gallery.R; targets/retrieval_gallery_targets.R;
  R/retrieval_gallery_targets.R.
- R/retrieval_gallery.R and isolated retrieval schemas.
- python/retrieval_gallery_{pipeline,inputs,gpu,ranking}.py and scripts for
  orchestration, bounded pilots, parity and benchmark summaries.
- Dedicated store: /mnt/hdd002/dhnyu/fusedata/targets/retrieval-gallery.
- Canonical _targets.R remains unchanged and does not auto-register this graph.
- The only shared spatial API extension is optional topology output-directory
  and schema arguments with unchanged canonical defaults.

Production has deterministic 25-scene shards, immutable verified-file seals,
job hashes and retry receipts. Completed shards are checksum-verified before
reuse. Normal failed subprocess shards can retry identical inputs without
recomputing successful shards. An unverified partial directory after a parent
crash, or an incomplete later cache stage, fails closed for explicit recovery
review; it is not silently accepted or scientifically reconfigured.
A postproduction tar_make skipped **all 14 targets**, confirming normal reuse.

Validation results:
- Python: **36 passed**, covering accepted P10/inspector and supplemental pilot,
  ranking, pipeline, browser, union preservation and strict acceptance schema.
- R: **215 assertions passed**, 0 failures/warnings/skips, covering membership,
  raster, relation, base spatial, v3 serialization, supplemental ordering and
  dependency renderer.
- Python AST (14 files), R parse (10 files), YAML (2 files), JSON (6 files): PASS.
- Strict supplementary acceptance schema and all parent bindings: PASS.
- tar_validate(): PASS; independent tar_outdated(): empty.
- Network: 14 targets, 14 edges, one component; 14 up-to-date, zero running/error/
  outdated. Output: artifacts/targets-network-retrieval-gallery/targets-network.html.
- git diff --check: PASS.
- Final frozen implementation/source authority check: PASS.
- Historical protected-file preservation: 7,134/7,134 identical.
- Dissertation HEAD/status: unchanged/clean.

Two reporting/test issues were corrected without touching frozen scientific
production: an existing network test's stale fixed 190-node/577-edge expectation
was replaced by agreement with the actual manifest (unmodified HEAD also had a
different graph size); and graph inspection now runs in isolated R subprocesses
to prevent repeated in-process sourcing from falsely flagging completed targets
as outdated. A new completed-fixture regression passes. The final generated
network agrees with independent isolated inspection.

An initial testthat::test_local invocation was unsuitable because this repository
is not an R package; the documented test_dir invocation passed. A tracked
bytecode file regenerated by the R test subprocess was restored to its starting
bytes and is not included in the commit. No scientific artifacts were restored,
overwritten, or retargeted.

Not executed: full training suite/jobs, canonical P9/P10/P11 tar_make, downstream
processing, optional batch-size search, UMAP/HDBSCAN, and dissertation writeup.
These are outside scope rather than missing acceptance gates. Remaining
limitations are optional district display unavailability and explicit manual
review for unverified partial-stage crash recovery.

## Prohibited-work accounting

| Activity | Actual count |
|---|---:|
| Training | 0 |
| Fine-tuning | 0 |
| Checkpoint reselection | 0 |
| Model reselection | 0 |
| P9 rerun | 0 |
| Canonical P10 acceptance mutation | 0 |
| P11 rematerialization | 0 |
| Ridge/MLP fitting | 0 |
| Target transformation changes | 0 |
| Canonical 1,600 evaluation replacement | 0 |
| Dissertation mutation | 0 |

Also zero: new augmented queries/P5 generation, canonical 1,600-scene inference,
SGIS/living-population/land-value/ECOSTRESS processing, fold rematerialization,
new canonical held-out loss/MRR/HIT/margin, and UMAP/HDBSCAN computation.
Bounded deterministic first-batch forward repeats are validation of supplemental
inputs, not training or canonical re-inference.

## Decision and next work unit

Implementation and supplementary acceptance PASS. All-eight inference added
little time compared with spatial preprocessing and preserved the intended
FM/ablation/baseline inspector comparison. The canonical scientific evaluation
and all historical acceptances remain unchanged.

Only source/config/schema/tests, the generated dependency HTML, the small
accepted-output pointer, and this report are intended for the Fuse reduced
commit. No scene data, cache, model, checkpoint, targets store, log, or inspector
asset payload is committed. Commit/push is authorized only after these gates.

Exact next work unit:
**RETRIEVAL_10K_QUALITATIVE_ANALYSIS_AND_DISSERTATION_WRITEUP**

That analysis/writeup is not executed in this work unit.
