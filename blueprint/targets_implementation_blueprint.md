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

S10 model branches use one GPU controller worker plus the existing per-device
GPU lock; CPU workers default to one, configurable by FUSE_S10_CPU_WORKERS.
Threads and batch size are recorded in the configuration (initially one each).
The operator sets BLAS/OpenMP limits from the same thread configuration. Total
CPU budget is `(CPU workers + GPU worker) × threads`, checked against host CPUs.
The conservative settings require an I/O/memory pilot before any expansion.
S10 uses `/mnt/hdd002/dhnyu/fusedata/targets/fuse-retrieval-s10`; S09 and maintenance
stores remain independent. Full inference requires separate authorization and
the explicit operator switch documented below; a successful smoke is not approval.

Retired training interfaces are represented only by immutable retirement
evidence and immediate fail-closed entrypoints. Their executable implementations
are absent from the current source tree.
