# P9-B Selected-Model Ablation Readiness

## Verdict

`P9_B_SELECTED_MODEL_ABLATION_READINESS_PASS_PUSHED`

This bounded gate prepares, but does not itself complete, the seven formal P9-B
comparison runs. The sole full-model parent is selected-FM acceptance
`p9accv2_1e1e842ee66f169f189725aa`, selected by
`p9sfm_dca5569ef50bd9bfb1940032`. The immutable input plan is
`p9bplan_747bbf5e1e12f831ea5fb101`.

## Implementation

- Added a deterministic plan-to-training-matrix adapter for exactly A1, A2,
  A3, A4, A5, SSV-like, and DS-like.
- Bound `model_family`, the complete transformation contract, plan identity,
  and selected-FM acceptance into each V2 scientific configuration.
- Added the winner acceptance as an optional training-authority parent without
  changing historical authority validation.
- Reused the existing V2 controller, worker, checkpoint handshake, ledger,
  bundle, finalizer, acceptance, eligibility, and resolver.
- Added an accepted-prefix sequential campaign runner. It never skips a row
  without validating its canonical resolver chain.
- Added `p9_model_families.py` to future scientific implementation and bundle
  source digests.

## Methodology mapping

The active dissertation defines nested A1-A5, plus controlled SSV-like and
DS-like models. The runtime registry implements their exact retained modalities,
IP terms, scene raster inclusion, generic-versus-heterogeneous relations, and
DS `C_cat+4` raster. All applicable hyperparameters inherit from selected-FM
IP1; DS alone uses `lambda_IP=0` because it has no modality-specific IP terms.

## Noncanonical two-GPU pilots

Each family performed four optimizer updates, queue/sampler progression, two
controller-owned checkpoint commits, and terminal ledger completion using the
production cache. No formal authority or canonical artifact was published.

| Configuration | Family | Updates | Checkpoints | Median update wall | Peak VRAM |
|---|---|---:|---:|---:|---:|
| `cmp_a1_geometric_core` | A1 | 4 | 2 | 0.678 s | 1.19 GB |
| `cmp_a2_semantic_enriched` | A2 | 4 | 2 | 0.779 s | 2.30 GB |
| `cmp_a3_object_context_enriched` | A3 | 4 | 2 | 0.779 s | 2.56 GB |
| `cmp_a4_raster_complete_non_relational` | A4 | 4 | 2 | 0.870 s | 3.30 GB |
| `cmp_a5_relation_type_agnostic` | A5 | 4 | 2 | 0.908 s | 5.65 GB |
| `cmp_ssv_like` | SSV | 4 | 2 | 0.761 s | 1.96 GB |
| `cmp_ds_like` | DS | 4 | 2 | 5.282 s | 0.22 GB |

All pilots recorded evaluation consumption 0, finite loss, and no OOM. DS is
substantially slower because its common 100x100 raster is deterministically
materialized on CPU for every batch; this does not change its scientific
contract and is not a comparison-selection input.

## Safety and mutations

| Activity | Count |
|---|---:|
| Noncanonical pilot optimizer updates | 28 |
| Noncanonical pilot checkpoints | 14 |
| Formal P9-B authority/run | 0 / 0 |
| Canonical P9-B checkpoint/acceptance | 0 / 0 |
| Held-out evaluation | 0 |
| P10/P11 | 0 / 0 |
| V1 execution | 0 |
| Historical/dissertation mutation | 0 / 0 |

## Launch contract

Formal execution order is A1, A2, A3, A4, A5, SSV-like, DS-like. Each row must
finish authority through resolver before the next starts. The campaign stops on
the first scientific, infrastructure, finalization, acceptance, or resolver
failure. No comparison participates in hyperparameter selection.

The first launch probe failed before authority publication because the base
contract's older P9-A eligibility did not contain selected-FM. The runner was
corrected to resolve the immutable eligibility identity from the selected-FM
decision. No authority, run, or scientific update was created by the failed
probe.

## Input prompt summary

Proceed from the completed selected-FM comparison to the exact next P9-B work
unit while preserving validation-only methodology, evaluation isolation, V1
retirement, and immutable canonical evidence.
