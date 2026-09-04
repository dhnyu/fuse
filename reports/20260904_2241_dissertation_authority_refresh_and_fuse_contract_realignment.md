# Dissertation Authority Refresh and Fuse Contract Realignment

## Verdict

`DISSERTATION_AUTHORITY_REFRESH_AND_FUSE_CONTRACT_REALIGNMENT_PASS_PUSHED`

Audit time: 2026-09-04 22:41 KST. This unit refreshed methodology authority
and future-facing contracts only. It did not execute training, P9/P10,
downstream preprocessing, fold construction, embedding inference, or ridge
fitting.

## Repository State

- Fuse starting commit: `c90ea00d466eb1ab389827866114652655620382`
- Fuse branch/start synchronization: `reduced`, 0 ahead / 0 behind
- Dissertation fetched commit: `ebcd03a`
- Dissertation final authority commit:
  `4adbd49b6dacab589d2fa99d88ec5be83aceb287`
- Dissertation branch/final synchronization: `reduced`, 0 ahead / 0 behind
- Dissertation change: one methodology clarification in
  `results/05-hyperparameter-study.typ`; no scientific result or artifact was
  changed.

The fetched dissertation had already changed the selected architecture and
living-population methodology, but its dimension-study paragraph called d128
the shared OFAT main configuration. Immutable Fuse evidence proves that d64 was
the shared historical reference and d128 was separately executed and selected.
The dissertation was therefore minimally corrected to state that historical
distinction. Its final commit is the scientific authority used below.

## Authoritative Model

Authority `disauth_60a514578f57b9397ce71ee6` binds the final dissertation
source files and confirms:

- selected full model `cfg_d128`, acceptance
  `p9accv2_a1c00e32a882ddc4b7e2677b`, checkpoint
  `p9ck_56195e9ea3cd45d80cf5e23c`;
- `d=d_c=128`, `d_t=16`, `d_r=32`, `d_a=32`;
- POI hierarchy dimensions 8/12/16/16/24/32, common projection 32, and
  land-cover embedding 16;
- four attention heads of 32 dimensions and relation FFN 128 -> 256 -> 128;
- raster CNN channels 64 -> 128 -> 128 for both land cover and DEM, with GN8;
- final fusion 640 -> 256 -> 128 and final scene representation 128;
- four 128-dimensional mask embeddings and contrastive head 128 -> 256 -> 128;
- 128-dimensional modality encoders, fusion projections, pooling input, and
  information-preservation decoder inputs as listed in the dissertation.

Historical `cfg_main` remains the immutable d64 reference and is displayed as
`cfg_d64`. No authority, run, checkpoint, bundle, finalization, acceptance,
eligibility, report, or identity was renamed or rewritten.

## Contract Diff

| Fuse contract | Finding | Classification | Action |
|---|---|---|---|
| `model_architecture.yml`, `joint_model.yml`, `training_plan.yml` | Prototype-era bindings; architecture files already use d128 while training contract is historical | `DERIVED_ARTIFACT_IMMUTABLE` | Unchanged |
| `p8_formal_experiment_plan.yml` | d64 shared OFAT reference and old dissertation authority | `EXPECTED_HISTORICAL` | Unchanged |
| `p9_selected_fm_confirmation_matrix.json` | Immutable interaction-confirmation design | `DERIVED_ARTIFACT_IMMUTABLE` | Unchanged |
| `p9_v2_training_controller.yml` | Active preflight rejected the latest dissertation commit | `ACTIVE_CONTRACT_MUST_CHANGE` | Bound to commit `4adbd49...` and `disauth_60a...` |
| P9/P10 acceptances and `p10_evaluation.yml` | Completed cfg_d128 science under original authority | `DERIVED_ARTIFACT_IMMUTABLE` | Unchanged; no embeddings regenerated |
| `p11_methodology_decision.json` | Complete-support/90% living rule created under old authority | `DERIVED_ARTIFACT_IMMUTABLE` | Preserved; superseded for future living execution only |
| `p11_living_population_source_contract.json` | Same old living rule and source evidence | `DERIVED_ARTIFACT_IMMUTABLE` | Preserved; source evidence reused by v2 contract |
| Other P11 source contracts | SGIS, land value, and ECOSTRESS methods unchanged by dissertation | `DERIVED_ARTIFACT_IMMUTABLE` | Unchanged |
| `p11_downstream_preprocessing.yml` and `p11ds_fdb...` | Executed strict-contract lineage | `DERIVED_ARTIFACT_IMMUTABLE` | Unchanged |
| Active living methodology | Dissertation now permits partial spatial and temporal support | `ACTIVE_CONTRACT_MUST_CHANGE` | Added versioned v2 decision, source contract, and non-executable rematerialization contract |
| Old P11 schemas | Validate immutable v1 artifacts and old commit | `DERIVED_ARTIFACT_IMMUTABLE` | Preserved; added separate Draft 2020-12 v2 schemas |

`UNRESOLVED_CONTRADICTION = 0` after the dissertation clarification and
versioned Fuse contracts.

## Living Population

The latest dissertation explicitly authorizes the following future rule:

1. Sum finite available intersecting 250 m grid observations by overlap area.
2. Treat suppressed/unavailable observations as missing, never zero.
3. Do not extrapolate from observed support to unobserved scene area.
4. Record spatial support for every valid scene-hour.
5. Average available scene-hours within each frozen temporal class.
6. Exclude missing hours from the mean and retain temporal coverage metadata.
7. Require at least one valid scene-hour; zero-observation scenes are
   ineligible for that target only.

New immutable contracts:

- methodology decision `p11meth_42070c9b832c232a6e989d25`, content SHA-256
  `42070c9b832c232a6e989d25c862bbd2c701db6c60c5953be6a215f9207345ce`;
- living source contract `p11src_ff2f5bb24376968aedfdfecc`, content SHA-256
  `ff2f5bb24376968aedfdfecc3b5cc34cfce07ed9b19741b198c6593d64fa47b3`;
- contract-only future plan `config/p11_downstream_preprocessing_v2.yml`.

The plan is deliberately non-executable in this unit. The current accepted
dataset remains `p11ds_fdb1f34c6daeda259e803e37`; it was not superseded or
rematerialized. The next implementation must correct the full grid-hour
universe semantics identified by P11-A3 before publication.

## Historical Immutability

- Existing P11 methodology file SHA-256:
  `a7a583e81bdecfee097ee8aa57977a220a4d8c4343deb20476883e84e0ed65a5`
- Existing living contract file SHA-256:
  `23b2cc890c8966f8a37c6b02d2c25f3f7d5a505cb2b9722d7f35937e5662bab2`
- Existing dataset reference file SHA-256:
  `e2c68ba6a40f566ee86b562f9495ef73ed826f473530073d7e190ed278af3249`
- Existing dataset acceptance SHA-256:
  `726fd5e1d9969a01fff797ccdff16bd7d7ae5e090591ea478850d11aa4079a8b`
- P10 acceptance remains `p10acc_6e5071beee7616750dec7907`; accepted file
  SHA-256 remains
  `f43a7206be6814c35e517017b438a977561c5113be855bff8d884c3d4a52e8c0`.
- P8 plan and all canonical P9/P10 scientific evidence were read only.

## Validation

- New authority/methodology/source-contract focused tests: 7 passed.
- Full relevant P9 v2/P10/P11 Python regression: 405 passed, 0 failed.
- Relevant R P11, V2 training-target, V1-retirement, and model-loader tests:
  49 passed, 0 failed.
- `tar_validate()`: main, P9 formal, P9 recovery, P9 V2 training, P10, and
  P11 preprocessing scripts passed against temporary stores; no targets ran.
- Python AST: 179 files; R parse: 101 files; JSON: 152 files; YAML: 61 files.
- Three new schemas validated as Draft 2020-12.
- Content-addressed identity and dissertation source hash readback: passed.
- `git diff --check`: passed.
- Typst PDF rebuild: not run because the installed Snap rejects the valid
  `/members/dhnyu` account home before invoking Typst. The changed Typst source
  was diff-checked; this environment limitation is non-scientific residual risk.

## Prohibited Work

| Activity | Count |
|---|---:|
| Training / optimizer updates | 0 / 0 |
| Checkpoint creation or reselection | 0 |
| P9/P10 rerun | 0 |
| New embeddings | 0 |
| Downstream preprocessing / dataset regeneration | 0 / 0 |
| Fold generation | 0 |
| Ridge fitting / OOF prediction / downstream metrics | 0 / 0 / 0 |
| Historical artifact mutation | 0 |
| Dissertation methodology clarification | 1 file |

## Exact Next Work Unit

`P11_LIVING_POPULATION_PARTIAL_SUPPORT_REMATERIALIZATION`: implement and test
the dissertation-authorized full grid-hour universe, available-support scene
aggregation, coverage metadata, and at-least-one-valid-hour eligibility;
rematerialize only the four living-population targets; prove the other seven
targets unchanged; and publish a new content-addressed downstream dataset that
supersedes but does not mutate `p11ds_fdb1f34c6daeda259e803e37`.

Do not generate spatial folds or fit ridge probes until that dataset passes.
