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
- Comparisons: FM, A1-A5, B1-B9, SSV, and DS, exactly 17 configurations.
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
- `_targets_evaluation.R`: current s10 evaluation preparation and acceptance.

The previous s11 downstream implementation is retired pending a from-scratch
redesign; no active s11 target graph or entrypoint is retained. P9 v1 remains
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

Retired training interfaces are represented only by immutable retirement
evidence and immediate fail-closed entrypoints. Their executable implementations
are absent from the current source tree.
