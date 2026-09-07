# P0 Current Methodology Prepublication Audit

## Purpose and scope

- Execution time: 2026-09-08 02:34 KST
- Purpose: establish the semantic evidence and historical-artifact disposition required before publishing a P0 authority for the current dissertation.
- Fuse input: `reduced` at `76704e8450f9961a70b2fd0075c816a3b6d7b675`, synchronized with `origin/reduced` and clean before this migration.
- Dissertation authority candidate: `reduced` at `cbb824f19be8355296603f8426ac241ce587ddcc`, synchronized with `origin/reduced` and unmodified by this migration.
- Historical authority: `mta_f90fecff7bc7bb5d231cc79f`, dissertation commit `e66d17d65e97a5e3f50fa9a111a51559db05666f`.
- This audit performed source parsing, semantic comparison, and fixture/static validation only. It did not run `tar_make`, production preprocessing, training, evaluation, retrieval, or downstream computation.

## Dissertation evidence reviewed

The review covered `03-methodology-model.typ`, `04-methodology-training.typ`, all five files under `chapters/methodology/`, results experimental setup and hyperparameter study, their five imported results tables, and appendices A and B included by `main.typ`. Appendix C is no longer included. Generated bibliography inputs and the pinned `xarrow` presentation dependency do not participate in scientific hashes.

Stable semantic anchors resolve the following current evidence:

- `results/01-experimental-setup.typ:21`: 10,000 off-grid scenes, split 1,000 validation / 9,000 evaluation, with 50 m minimum distance.
- `results/01-experimental-setup.typ:29-173`: 17 comparisons, exact A1-A5 nesting, A4 generic mapping over exact FM directed edges, A5 heterogeneous labels, and input-level B1-B9 source removal.
- `04-methodology-training.typ:290`: optimization solely through the scene-level contrastive objective.
- `results/05-hyperparameter-study.typ:6`: five-axis shared-main OFAT with exactly eleven unique configurations.
- Imported dimension, training, and architecture tables: d=d_c=128, EMA 0.999, queue 8,192, temperature 0.1, peak LR 1e-3, and no reconstruction decoder rows.

## Old-vs-new scientific contract matrix

| Area | Historical active contract | Current dissertation contract | Classification |
|---|---|---|---|
| Off-grid population | 400 validation + 1,600 evaluation | 1,000 validation + 9,000 evaluation | SCIENTIFIC_CHANGE |
| Scene geometry | 500 m official-grid training windows; 50 m exclusion | Same | REUSABLE_EXACT at rule level |
| Base spatial entities/relations | B/R/P; SN/CNT/WIT/INT/CON | Same production predicates | REVALIDATE_ONLY |
| Original serialization | deterministic lossless Serialization-v3 | Same serialization semantics | REVALIDATE_ONLY |
| Augmentation | fixed view bank; historical canonical representation | Same scientific operations, canonical representation normalized | REVALIDATE_ONLY |
| Main model | d=d_c=64 with reconstruction decoders | d=d_c=128, no reconstruction subsystem | RECOMPUTE_REQUIRED |
| Training objective | contrastive + weighted information preservation | symmetric scene contrastive only | RECOMPUTE_REQUIRED |
| OFAT | historical six-axis/13-row plan including IP | five axes, exactly 11 unique rows, no IP | RECOMPUTE_REQUIRED |
| Component comparison | historical A1-A5 meanings | exact nested A1-A5 specified by current dissertation | RECOMPUTE_REQUIRED |
| Source ablation | no complete formal B1-B9 current plan | exact input-level B1-B9 retained-source sets | RECOMPUTE_REQUIRED |
| Evaluation | 400/1,600 populations and historical model set | 1,000/9,000 and 17 models | RECOMPUTE_REQUIRED |
| Downstream outputs | derived from historical P10 embeddings | methods may remain valid, inputs do not | HISTORICAL_ONLY pending new P10 |

## Canonical current contract

### Scene and evaluation

- Total off-grid scenes: 10,000.
- Validation: 1,000 originals, 2,000 fixed augmented queries, gallery 1,000.
- Evaluation: 9,000 originals, 18,000 fixed augmented queries, gallery 9,000.
- Training centers remain official 500 m grid centers inside Seoul; no intermediate centers are introduced.

### Model and training

- Main `d=128`, `d_c=128`, four attention heads, 32 dimensions per head, and 256-dimensional FFN hidden layer.
- The current architecture contains no reconstruction decoder or information-preservation subsystem.
- Training uses only the symmetric scene-level contrastive objective. Modality masking, momentum encoder, EMA, FIFO queue, and contrastive projection remain.

### Formal experiment contract

- OFAT candidates: d `{64,128,256}`; K_aug `{4,8,16}`; intensity `{0.5,1.0,2.0}`; EMA `{0.990,0.999}`; LR `{0.001,0.002,0.003,0.005}`.
- Main row: d=d_c=128, K_aug=8, intensity 1.0, EMA 0.999, LR 0.001.
- Removing the repeated main values yields exactly 11 unique configurations.
- Ordered comparisons: `FM,A1,A2,A3,A4,A5,B1,B2,B3,B4,B5,B6,B7,B8,B9,SSV,DS`.

## Semantic selector and resolver verdict

The v2 resolver follows the local Typst import closure, records declared generated bibliography paths as non-scientific generated dependencies, and records the pinned external `xarrow` import as non-scientific. It does not require either dependency to extract methodology. Every scientific selector uses an exact-one anchored block with required and, where needed, forbidden semantic tokens. Absolute line ranges are prohibited. Source provenance/evidence hashes remain in artifacts, while each module scientific hash is computed from its structured canonical contract, so line movement changes provenance without silently changing scientific identity.

## Historical artifact compatibility

| Artifact family | Verdict | Reason |
|---|---|---|
| Existing 2,000-row P1 off-grid source and scene index | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | Cannot satisfy the 10,000-row current split. |
| Existing P2/P3 observation/cache payloads | HISTORICAL_ONLY for current lineage | Population ancestry is 4,421 scenes; algorithms may be reused after new P1. |
| Existing P4/P5 banks and queries | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | Population and query cardinalities differ. |
| Existing P6/P7 model/training artifacts | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | d64 and/or IP-enabled scientific identity differs. |
| Existing nine-file P8 accepted bundle | HISTORICAL_ONLY | Historical plan has incompatible OFAT and comparison semantics. Bytes and names remain immutable. |
| Existing P9/P10 accepted results | HISTORICAL_ONLY / RECOMPUTE_REQUIRED | Model set, objective, and held-out populations differ. |
| Existing P11 outputs | HISTORICAL_ONLY | They remain valid only as results of the historical P10 lineage. |

No existing accepted artifact may be relabelled under the new authority. Exact rule-level reuse means revalidation or reuse of implementation logic, not reuse of an artifact with incompatible ancestry.

## Publication conditions and risks

Publication may proceed only if the current dissertation repository remains clean at the exact candidate commit, all semantic selectors resolve, every module contract validates against its schema, the predecessor/supersession identity is explicit, and current experiment-contract tests pass. Any ambiguity fails closed. The publication creates a new immutable authority generation; it does not overwrite `mta_f90fecff7bc7bb5d231cc79f`.

The main residual risk is operational: current P1-P11 payloads do not yet exist for the new population/model/experiment contract. Their future execution must be staged from P1 onward and must not fall back to historical paths.

## Verdict

**PASS_FOR_NEW_AUTHORITY_PUBLICATION_WITH_HISTORICAL_RECOMPUTE_REQUIRED.** The current dissertation is unambiguous and differs scientifically from the historical authority. P0 may publish a new superseding authority after automated semantic validation, but the downstream historical artifacts remain historical and expensive recomputation is deferred.

## Input prompt summary

Migrate Fuse methodology contracts to the current dissertation `reduced` branch: use 1,000/9,000 off-grid splits, remove IP/reconstruction, implement the exact 11-row OFAT and 17-model A/B comparison contract, preserve immutable historical artifacts, publish a superseding P0 authority only after semantic validation, and avoid expensive computation.
