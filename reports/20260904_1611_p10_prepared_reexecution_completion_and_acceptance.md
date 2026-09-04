# P10 Prepared Re-execution Completion and Acceptance

## Verdict

`P10_PREPARED_REEXECUTION_COMPLETION_AND_ACCEPTANCE_PASS_PUSHED`

Audit time: 2026-09-04 16:11 KST. The prepared-input execution exited with code
zero, all eight fixed models committed complete results, and final acceptance
`p10acc_6e5071beee7616750dec7907` validates and republishes idempotently without
changing its bytes or modification time.

## Repository State

- Starting Fuse commit: `2849f125a1ed77269a6a61eab1c8999d47396b05`
- Branch: `reduced`; initial origin synchronization: 0 ahead / 0 behind
- Dissertation: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, clean and unchanged
- Completed tmux session: `p10_prepared_reexecution_20260904`
- Execution attempt: `p10exec_7fee193dac532190c79e02c6`
- P10 authority: `p10auth_8b6919578aaa24fa8f1b98a2`

## Completion And Model Bindings

Exactly 8/8 configured results have immutable result metadata, embeddings,
complete ranks, qualitative outputs, UMAP coordinates, and HDBSCAN outputs.
Each P9 checkpoint was resolved from its canonical acceptance; no path fallback
or checkpoint reselection occurred.

| Configuration | P9 acceptance | Selected checkpoint |
|---|---|---|
| cfg_d128 | `p9accv2_a1c00e32a882ddc4b7e2677b` | `p9ck_56195e9ea3cd45d80cf5e23c` |
| cmp_a1_geometric_core | `p9accv2_9a207a914e17fbdc663f738a` | `p9ck_37979e7a36f6b189ecf674d0` |
| cmp_a2_semantic_enriched | `p9accv2_b603f92e47f7ffe6bdf3a5d3` | `p9ck_74cc9b14a7d294463bfd5a9c` |
| cmp_a3_object_context_enriched | `p9accv2_90763f5a22a6aab791c42290` | `p9ck_c0784d438146deeaee04fd34` |
| cmp_a4_raster_complete_non_relational | `p9accv2_b25055427137c88c820dcc51` | `p9ck_a71bec2d0fae827ee7c97879` |
| cmp_a5_relation_type_agnostic | `p9accv2_0a4ac70cbf2ebcba233c6084` | `p9ck_0ee547be5473315d457bf104` |
| cmp_ssv_like | `p9accv2_93c296bec0ffe6f1a3ccb8ee` | `p9ck_388bce700e35c96012e77b1a` |
| cmp_ds_like | `p9accv2_f4194b7c74f8dedb4c867e6b` | `p9ck_65cc78a1a97330f3af05fba4` |

## Validation Revalidation

The audit loaded each committed validation embedding/rank artifact, recomputed
the complete 800 by 400 ranking and aggregate metrics, and compared these with
both the committed revalidation and selected-checkpoint evidence. Every numeric
difference was exactly zero.

| Configuration | Expected loss | Reproduced loss | Expected margin | Reproduced margin |
|---|---:|---:|---:|---:|
| cfg_d128 | 0.1765069515 | 0.1765069515 | 0.3754689395 | 0.3754689395 |
| cmp_a1_geometric_core | 0.2201937288 | 0.2201937288 | 0.4141666889 | 0.4141666889 |
| cmp_a2_semantic_enriched | 0.2305538952 | 0.2305538952 | 0.3897022903 | 0.3897022903 |
| cmp_a3_object_context_enriched | 0.2446398735 | 0.2446398735 | 0.3784501553 | 0.3784501553 |
| cmp_a4_raster_complete_non_relational | 0.1861187816 | 0.1861187816 | 0.3722944260 | 0.3722944260 |
| cmp_a5_relation_type_agnostic | 0.2058894932 | 0.2058894932 | 0.3557559252 | 0.3557559252 |
| cmp_ssv_like | 0.2236431092 | 0.2236431092 | 0.3982822299 | 0.3982822299 |
| cmp_ds_like | 0.4145002365 | 0.4145002365 | 0.2472607940 | 0.2472607940 |

## Held-out Comparison

All rows use exactly 3,200 queries and 1,600 gallery scenes. Delta columns are
model minus `cfg_d128`. Lower loss is better; larger margin/ranking metrics are
better.

| Configuration | Loss | Delta loss | Margin | Delta margin | MRR | HIT@1 | HIT@5 | HIT@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| cfg_d128 | 0.5894929171 | 0 | 0.2855600119 | 0 | 0.9970607758 | 0.9956250191 | 0.9996874928 | 1.0000000000 |
| cmp_a1_geometric_core | 0.6636334062 | +0.0741404891 | 0.3501115739 | +0.0645515621 | 0.9641897082 | 0.9618750215 | 0.9643750191 | 0.9674999714 |
| cmp_a2_semantic_enriched | 0.6621056199 | +0.0726127028 | 0.3288334012 | +0.0432733893 | 0.9645757079 | 0.9621875286 | 0.9649999738 | 0.9681249857 |
| cmp_a3_object_context_enriched | 0.7093244195 | +0.1198315024 | 0.3057616353 | +0.0202016234 | 0.9646538496 | 0.9621875286 | 0.9649999738 | 0.9681249857 |
| cmp_a4_raster_complete_non_relational | 0.6226891875 | +0.0331962705 | 0.2854558229 | -0.0001041889 | 0.9965963960 | 0.9953125119 | 0.9984375238 | 1.0000000000 |
| cmp_a5_relation_type_agnostic | 0.6515341401 | +0.0620412230 | 0.2724851072 | -0.0130749047 | 0.9970521331 | 0.9956250191 | 0.9996874928 | 1.0000000000 |
| cmp_ssv_like | 0.6577979922 | +0.0683050752 | 0.3347572982 | +0.0491972864 | 0.9639879465 | 0.9615625143 | 0.9640625119 | 0.9678124785 |
| cmp_ds_like | 1.0739976168 | +0.4845046997 | 0.1713503450 | -0.1142096668 | 0.9927264452 | 0.9896875024 | 0.9962499738 | 0.9984375238 |

`cfg_d128` has the lowest P10 loss and highest MRR. A1 has the largest margin
but substantially worse loss and ranking accuracy. A4 recovers most full-model
ranking performance; removing relation types in A5 worsens loss and margin
relative to A4 while preserving near-full-model rank accuracy. The SSV-like
controlled baseline follows A1-A3-like rank behavior. The DS-like controlled
baseline has the weakest loss and margin, despite strong top-k ranks. These are
generalization observations only: `cfg_d128` remains the pre-P10 selected full
model and P9 selection is not reopened.

## Qualitative Contract

- Contract: `p10qq_dd7d0775f5809a793575342b`
- Content SHA-256: `dd7d0775f5809a793575342b45c3f04116dec536de460903f37b34177ed52659`
- Standard candidates per query: 1,599
- Non-local exclusion: exactly 2,000 m
- Frozen scene IDs, in deterministic order:
  `scn_c0ba3bcd99b3f90218d1b3bc`,
  `scn_c00ff67c4e81b7220deb863e`,
  `scn_a4da2c5a766af8059e020492`,
  `scn_e64bbc2a87d2debcc8453f3d`,
  `scn_fc02fd6d3d4bc8637b16f12b`,
  `scn_d1f32d62dac7151c054d573b`,
  `scn_4960049e9b3a46f311538dbb`,
  `scn_643b50dae130626079585c93`,
  `scn_8c772d2081968ea7eeea0c80`, and
  `scn_ac42914e0e7cb935334e2873`.

For every model the audit reconstructed all ten standard and non-local results
from the frozen embeddings and exclusion masks and obtained byte-equivalent
canonical records. No query replacement occurred. The contract reports fixed
rank positions `top`, `one_third`, `two_thirds`, and `bottom` rather than an
adaptive top-k choice.

## Representation Analysis

Analysis contract `p10ana_8fc83be04542d925a4574e3c` has content SHA-256
`8fc83be04542d925a4574e3c87f18a29a9be2e844c0eb37333e9cebf0c0f0f3d`.
Each result contains 1,600 by 2 UMAP coordinates and 1,600 HDBSCAN labels and
probabilities, all hash-bound to the committed result.

Frozen settings are UMAP 0.5.9.post2 (`n_neighbors=15`, `min_dist=0.1`, cosine,
two dimensions, seed 20260904, one job) and HDBSCAN 0.8.40
(`min_cluster_size=30`, `min_samples=10`, Euclidean, EOM, single cluster
disabled). The execution environment binds PyTorch 2.12.0, NumPy 2.4.6,
scikit-learn 1.7.2, UMAP 0.5.9.post2, HDBSCAN 0.8.40, and PyArrow 22.0.0.

## Prepared Inputs And Acceptance

- Prepared input cache: `p10pi_da45b59753b561948fea78f5`
- Prepared geometry cache: `p10geo_8cdab54a6886cb8217c0088b`
- Full payload verification: PASS; no dynamic fallback
- Consumption: `p10cons_7d0eba832b70d545fc5d3eb4`, the original and only
  transition from 0 to 1
- Acceptance: `p10acc_6e5071beee7616750dec7907`
- Acceptance file SHA-256:
  `f43a7206be6814c35e517017b438a977561c5113be855bff8d884c3d4a52e8c0`
- Duplicate finalization/readback: same identity, bytes, and mtime; no rewrite

The acceptance binds the authority, attempt, eight model evaluations, eight
validation revalidations, both prepared caches, fixed evaluation and qualitative
evidence, analysis contract, environment, and original consumption identity.

## Validation

- Focused completion plus P10 tests: 18 passed, 0 failed.
- Complete P9 v2 and P10 Python regression: 379 passed, 0 failed.
- Related P9 campaign/formal/retirement Python regression: 115 passed, 0 failed.
- Relevant R P10/retirement/V2 target tests: 22 passed, 0 failed.
- `tar_validate()`: main, P9 formal, P9 recovery, P9 V2 training, and P10 passed;
  no target execution occurred.
- Schema, Python/R parse/import, JSON/YAML parse, Markdown links, and
  `git diff --check`: PASS.

## Immutability And Prohibited Work

The pre-optimization P10 inventory revalidated byte-for-byte. The accepted P10
attempt contains 27 immutable files; its readback inventory digest is
`da9b6adb251cbbc6b928add1554ec0f023d8a4848011d4432317d1d11d0e235a`.
The cfg_main acceptance remains
`ad1fe493610f92fe97aa6f4b40048ff8d56e54d9e074cff74c43fe243df0a713`,
the V1 retirement manifest remains
`4fd252ecfefa7436b0665b97cabe5976f3000a827d8ad229d8f0a17b161aac91`,
and the historical V1 source inventory remains
`282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c`.

| Prohibited activity | Count |
|---|---:|
| Training / optimizer updates | 0 / 0 |
| Checkpoint creation or reselection | 0 |
| P9 reruns / hyperparameter tuning | 0 / 0 |
| Additional held-out model or consumption events | 0 / 0 |
| New qualitative queries / cache regeneration | 0 / 0 |
| Dissertation mutation | 0 |
| P11 execution | 0 |

## Exact Next Work Unit

`P11 Downstream Evaluation`: prepare accepted downstream targets, generate
frozen scene embeddings through the canonical resolver/P10 acceptance chain,
construct deterministic spatially disjoint folds, enforce leakage and coverage
gates, and evaluate spatial ridge-regression probes with complete out-of-fold
predictions. Do not fine-tune the encoder or substitute random folds.

## Prompt Summary

Confirm completion of prepared attempt `p10exec_7fee193dac532190c79e02c6`,
independently validate all eight quantitative, qualitative, and representation
outputs, reproduce validation and held-out aggregates, verify prepared-cache and
single-consumption provenance, validate and read back one idempotent P10
acceptance, report results without reopening P9 selection, and do not execute
P11.
