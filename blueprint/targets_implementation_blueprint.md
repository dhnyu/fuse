# Current reduced targets implementation blueprint

## Authority

The `reduced` dissertation at commit
`cbb824f19be8355296603f8426ac241ce587ddcc` is the scientific authority.
`s00_methodology_authority` publishes the current semantic contract. Operational
source-layout supersessions are allowed only when every module scientific hash is
identical to its predecessor.

## Scientific invariants

- Off-grid scenes: 10,000, split into 1,000 validation and 9,000 evaluation.
- Off-grid exclusion distance: 50 m.
- Main dimensions: `d = 128`, `d_c = 128`.
- Training objective: symmetric scene-level contrastive objective only.
- Current training retains modality masking, momentum encoder, EMA, FIFO queue,
  and the contrastive projection head.
- Formal OFAT: five axes and exactly 11 unique configurations.
- Comparisons: exactly 17 configurations; operational execution/display order is
  FM, A1-A5, SSV, DS, B1-B9 (canonical `training_campaign.COMPARISON_IDS`).
  The immutable S08 definition-array order is not an execution ordinal or seed.
- Source ablation removes inputs and uses the induced relation subgraph.

## Active main DAG

The main research entrypoint is `_targets.R`; it does not include maintenance,
training execution, evaluation, or downstream execution.

| Stage | Declaration | Responsibility | Cache boundary |
|---|---|---|---|
| s00 | `targets/s00_methodology.R` | Dissertation resolution and methodology authority | Immutable semantic authority |
| s01 | `targets/s01_scene_index.R` | Source registration and scene-index construction | Accepted scene index |
| s02 | `targets/s02_spatial_observations.R` | Membership, vector/raster observations, and relations | Validated branch artifacts and spatial acceptance |
| s03 | `targets/s03_scene_cache.R` | Deterministic original-scene serialization | Independent shard validation and dataset acceptance |
| s04 | `targets/s04_augmentation.R` | Fixed augmentation bank | Validated bank shards and bank acceptance |
| s05 | `targets/s05_fixed_queries.R` | Fixed validation/evaluation queries | Validated query shards and query acceptance |
| s06 | `targets/s06_model_inputs.R` | Model-ready inputs and architecture validation | Model-data acceptance |
| s08 | `targets/s08_experiment_plan.R` | Current 11-row/17-model experiment plan | Immutable current experiment plan |

The Seoul canonical-data maintenance entrypoint is `_targets_maintenance.R` and
uses a separate store.

## Dedicated execution entrypoints

- `_targets_training.R`: current s09 campaign lifecycle in the dedicated
  `/mnt/hdd002/dhnyu/fusedata/targets/fuse-training-s09` store. Its explicit
  operator is `Rscript scripts/run_training_targets.R campaign`; the graph
  builds the accepted CPU prepared cache, executes 11 OFAT runs, publishes the
  validation-selected winner, and only then enables 17 comparison runs. Formal
  progress is append-only in `logs/s09/campaign_status.tsv` and per-run TSVs;
  `logs/s09/current_status.txt` is the atomically replaced operator summary.
  Runtime provenance binds all fresh authorities. Winner publication is isolated
  by plan ID and runtime SHA; winner and campaign acceptance reject historical
  authority IDs. The corrected family adapter requires a full fresh campaign,
  not checkpoint or result reuse from the legacy global runtime. Immutable
  prepared payloads are reused downstream through family-aware projection.
- S09 Fresh Formal Training — COMPLETE / PASS. Canonical campaign
  `s09camp_d2f6749da19ad6aa56c2d303`, 11 OFAT + 17 comparisons, is immutable.
- `_targets_retrieval_visualization.R`: S10 Retrieval Visualization, a separate
  graph/store consuming this exact S09 acceptance without running training.
  Exactly 30 evaluation originals are sampled without replacement from sorted
  9,000 evaluation IDs using explicit PCG64 seed **20260916**. The immutable
  common gallery is the full current evaluation pool. Original-scene inference
  uses accepted S09 preprocessing and family projection. Unit-normalized scene
  embeddings produce cosine rankings (descending score, ascending scene ID),
  excluding self; non-local candidates must be at least 2,000 m away in EPSG:5186.
  Top 50 for all 28 models / 30 queries / 2 modes yields 84,000 Parquet rows.
  Thirty query-centric pages show Top 5 by default and share a model-independent
  scene render cache. `tools/retrieval_inspector` only consumes formal artifacts.
  S10 is qualitative interpretation, never model selection: no winner changes,
  checkpoint changes, retuning, B8/B9 special selection or S11 protocol changes.
  See `config/retrieval_visualization.yml` and `tools/retrieval_inspector/README.md`.
- `_targets_evaluation.R`: S11 Formal Evaluation (formerly S10), **BLOCKED**.
  Number and future namespace only were migrated. Input lineage has not been
  rebound to S09; schema still requires PENDING_RECOMPUTATION / RECOMPUTE_REQUIRED
  and runtime rejects it. The required runtime bundle_record is still forbidden
  by the current model-entry schema. Historical interrupted/reexecute evidence
  cannot be silently adopted. A separate lineage/schema/lifecycle repair is
  required before execution. Existing scientific qualitative seed preimage is
  explicitly frozen to `p10-qualitative-query-v1`; renumbering must not resample
  queries. S11 has no dependency on S10 query/ranking artifacts and its scientific
  protocol remains unchanged.

The historical S11 downstream implementation is retired pending a from-scratch
redesign; the S11 name now denotes the blocked evaluation graph above. P9 v1 remains
fail-closed through the centralized R/Python retirement registry and operator
CLI guards; obsolete root retirement entrypoints are absent.

## Source layout

- `R/`: reusable methodology and orchestration helpers.
- `targets/`: thin declarative stage definitions.
- `python/`: current model, training, and evaluation libraries.
- `scripts/`: current operator-facing commands plus explicit retirement guards.
- `config/`: current contracts and immutable historical references needed for validation.
- `tests/`: current unit/contract tests and minimal retirement-guard tests.

The canonical R loader is `R/current_source_registry.R`. Both `_targets.R` and
test helpers consume this registry.

## Execution policy

P1-P6 production must not begin until the current methodology authority and all
stage configs validate. Every large or GPU operation requires fixture/pilot
validation first. Artifact writers stage, validate, and atomically publish fixed
paths. Immutable historical artifacts are never rewritten or relabeled.

S10 file contracts: generation root is
`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/<generation_id>/`.
Fixed names are `model_manifest.json`, `gallery_manifest.json`,
`query_manifest.json`, `original_inputs/{<scene_id>.pt,manifest.json}`,
`geometry_features/{<geometry_config_sha256>/<shard_ordinal>.pt,manifest.json}`,
`embeddings/<configuration_id>/{vectors.npy,manifest.json}`,
`rankings/<configuration_id>/{rankings.parquet,manifest.json}`,
`renders/{<cache_id>.svg,manifest.json}`, `pages/{query_01.html…query_30.html,index.html,
app.js,style.css,manifest.json}`, `summary.json`, `acceptance.json`.
Every file target returns the manifest plus all payload files after checksum QC.
Manifest publication is the completion marker; writes use temporary sibling
files, create-or-validate publication and immutable collision rejection.
The common original-input target tensorizes each scene once before model branches;
it has its own pinned preprocessing/category hashes and validates source payloads.
It is also gated by full-execution authorization so metadata validation cannot
accidentally prepare the entire 9,000-scene population.

The common `s10_retrieval_geometry_features` GPU target follows original inputs
and precedes embeddings. It calls the unchanged GPU Fourier function scene-wise
at batch=1, storing only pre-MLP float32 magnitude [N,128] and phase [N,256].
Twenty-five geometry-active configurations share the current identical settings;
A1, SSV and DS do not read geometry payloads. Different geometry settings form
separate hash-keyed groups. Learned projections, family row projection and model
forward remain unchanged. No checkpoint participates in feature computation.

The immutable cache binds each original payload/manifest, preprocessing ID/hash,
entity ordering, geometry config, implementation source hash and runtime/generation.
One deterministic 100-scene PyTorch shard is retained at a time. Shape/schema,
finite values, payload/tensor checksums and model-group bindings are checked.
Same-ID different-byte publication fails. Creation metadata is deterministic;
wall time is telemetry outside identity. No historical S09 geometry cache is used.
The cache GPU target has the same lock/controller and full-execution gate as
inference. Bounded benchmarks are noncanonical and limited to 100 originals.

S10 model branches use one GPU controller worker plus the existing per-device
GPU lock; CPU workers default to one, configurable by FUSE_S10_CPU_WORKERS.
Threads are recorded in the configuration; batch_size=1 is a scientific contract.
The operator sets BLAS/OpenMP limits from the same thread configuration. Total
CPU budget is `(CPU workers + GPU worker) × threads`, checked against host CPUs.
The conservative settings require an I/O/memory pilot before any expansion.
The S10 original reader traverses accepted P3 shards deterministically, filters
Arrow tables before Python conversion, and retains only one shard's tables and
raster extraction at a time. Published original tensors remain scene-ID ordered
individual `.pt` files; S09 prepared training/validation views are not evaluation
originals. Vector-only SVG rendering avoids loading unused raster/graph inputs.
Common-input hashes are verified once per ranking-validation invocation, with no
persistent verification cache and no removal of acceptance checks.

Batch expansion remains a known prohibited optimization: zero-edge scenes differ
when collated with edge-bearing scenes under the existing relation-layer branch.
Keep batch_size=1. Do not change the frozen S09 model/runtime to repair this in a
performance task, or treat batched output as scientifically interchangeable.
This finding does not modify the canonical S09 acceptance. Full S10 remains gated.
S10 uses `/mnt/hdd002/dhnyu/fusedata/targets/fuse-retrieval-s10`; S09 and maintenance
stores remain independent. Full inference requires separate authorization and
the explicit operator switch documented below; a successful smoke is not approval.

Retired training interfaces are represented only by immutable retirement
evidence and immediate fail-closed entrypoints. Their executable implementations
are absent from the current source tree.

## Authorized S10 100-query revision (2026-09-18)

The existing 30-query contract, generation and acceptance above remain immutable.
The user explicitly authorized a separate 100-query policy after disclosure that
`sec:spatial-scene-retrieval` currently describes ten queries. This extension is
qualitative inspection only; it does not revise the dissertation, S09 or S11.

`_targets_s10_query_revision.R` / `targets/s10_query_revision.R` use the separate
store `/mnt/hdd002/dhnyu/fusedata/targets/fuse-s10-query-revision`. Its six file
targets are contract, sources, immutable parent manifests, canonical object
counts, ranking acceptance and supplemental viewer. Controller `controller_05`
uses one worker and one internal BLAS/OpenMP thread, based on the read-only pilot.
There is no GPU controller, checkpoint resolution/loading or inference target.

Inputs are acceptance `s10_acceptance_5471f74031f267c4253df231`, its 28 normalized
9,000-scene embedding arrays, original gallery, and hash-bound P3 vector shards.
`object_count = |B|+|R|+|P|` counts original observed entity records before model
family projection. Within each lexical scene-ID stratum, PCG64 seed 20260916 draws
`min(5, available_sparse)` scenes with count <10, followed by enough count >=10
scenes to reach 100, without replacement; draw order is retained. No further
stratification or old-query preservation is applied. Counts bind P3 checksums.

Output paths are fixed by the content-derived generation identity beneath
`config/s10_query_revision.json:publication_root`: `object_counts_manifest.json`,
`query_manifest.json`, `rankings/<model>/manifest.json`, `rankings.parquet`, and
`acceptance.json`. File bytes are staged and create-or-validate published;
acceptance is written last. The original models/gallery/embedding manifests are
referenced under their original IDs and original query bindings, never rebound
or falsely relabeled as newly inferred. New ranking manifests explicitly bind
both the new query manifest and the original accepted embedding parent.
Acceptance checks canonical count recomputation, deterministic selection,
unchanged centers/population, and exact deterministic read-back of 280,000 Top50
rows. Ranking semantics and tie handling are unchanged.

The supplemental viewer has a separate content-derived directory under
`viewer_root`, a staging directory and receipt-last publication. It checks all
formal Top50 rows when reconstructing Rank1, ranks 2–11, true middle and true
bottom. It reuses exact original display/9,000-center location bytes where
available, and serializes only missing display scenes from accepted originals.
It publishes 100 query JSON files, 100 query HTML pages plus index, display scene
JSONs and receipts. Every file target returns its complete verified file set.
Browser validation is a separate read-only completion gate. S09, S11, maintenance
and the old S10 graph/store have no execution dependency on this revision.
