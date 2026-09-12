# S09 Formal Comparison Order Repair

Created: 2026-09-12 13:18:44 KST (Asia/Seoul).
Repository: /members/dhnyu/fuse; branch: reduced.
Input HEAD: 3f6c5685bd5c0b975fb1ef518d9fb12a8a7ff83d.
Implementation commit: 44f2ed7fd1580dc6975f89fa7b10c7034b4d2a6e.
Implementation push: PASS (origin/reduced).
This report is recorded in a subsequent documentation-only commit.

## Verdict

PASS_S09_FORMAL_COMPARISON_ORDER_REPAIRED

Prompt scope: repair only operational formal comparison ordering, share it with smoke/report consumers, preserve scientific identities and historical evidence, validate and commit/push. No formal training or production target execution.

Authoritative smoke report read completely:
reports/20260912_1240_s09_all_model_ddp_smoke.md.
The current dissertation experimental-setup section was inspected: component configurations and SSV/DS precede the data-source-ablation section. Blueprint inspected before implementation.

## Preconditions

PASS: exact requested reduced HEAD, clean tracked worktree, local/origin equality and ahead/behind 0/0, live remote ref equality. Main research tar_outdated empty. Current S08/cache/acceptance/lineage and 80,472 prepared payload presence/registered-size checks passed through read-only resolve_inputs. Runtime SHA matched the requested value. No controller/DDP/GPU compute workload.

## Before And After

Old formal order:
FM,A1,A2,A3,A4,A5,B1,B2,B3,B4,B5,B6,B7,B8,B9,SSV,DS

New canonical formal and smoke order:
FM,A1,A2,A3,A4,A5,SSV,DS,B1,B2,B3,B4,B5,B6,B7,B8,B9

Exactly 17 unique models. SSV follows A5; DS follows SSV; B1 follows DS; B1-B9 form the trailing sequence.

## Order-Bearing Inventory And Changes

| Location | Classification | Action |
|---|---|---|
| python/training_campaign.py COMPARISON_IDS | Authoritative S09 operational order | Set dissertation order; sole shared constant |
| comparison_authorities / ordered_comparisons | Formal authority materialization | Validate exact set/cardinality, then select unchanged scientific rows by model ID in canonical order |
| python/s09_smoke.py COMPARISONS | Derived smoke order | Import COMPARISON_IDS; values and smoke seeds unchanged |
| scripts/training_campaign.py campaign-validate | Derived result/report order | Return validated result paths in model order |
| R/training_targets.R s09_accept_campaign | Derived acceptance summary order | Preserve canonical returned paths, remove lexicographic path sorting and duplicated order list |
| blueprint/targets_implementation_blueprint.md | Documentation | Explicit execution/display order and S08-array distinction |
| tests/python/test_training_campaign.py | Test expectations | Exact order/parity, uniqueness, invalid inventory, identity stability and all-result gate |
| tests/testthat/test-training-targets.R | Test expectations | Summary preserves validated order rather than filename order |
| python/training_progress.py | Chronological progress, counts/current model | No independent order list; follows executed branches, unchanged |
| R/experiment_plan.R / tests/testthat/test-s08-experiment-plan.R | Immutable S08 scientific serialization order | Unchanged |
| config/current_methodology.yml ordered_models / python/current_methodology.py | P0/S08 scientific inventory and serialization | Unchanged; not future S09 execution order |
| python/evaluation.py / evaluation.schema.json enums | Downstream inventory, outside this task | Unchanged; S10 not executed |
| README | No independent comparison sequence requiring repair | Unchanged |

No historical reports/logs were rewritten. The S08 serialized array remains authoritative scientific content; S09 operational ordering is applied after reading it. No model definition was changed or copied into a new scientific artifact.

## Authority And Seed Identity

Formal comparison seed derives from configuration_seed(base_root_seed, cmp_MODEL_ID), not list position. Model ID, winner hyperparameters, per-model scientific definition hash, parent lineage, selection hash and runtime SHA are unchanged.

Two independent checks passed:
1. Regression compares all 17 complete authority documents and run IDs under legacy versus new operational ordering.
2. Actual git HEAD version of comparison_authorities was loaded read-only and compared with the repaired function using the same current S08, runtime, synthetic winner and fixture parents: all 17 complete authority documents identical by model.

Reversing the input scientific array produces the same canonical output list without mutating the input plan. Missing/extra/duplicate inventory fails. No ordinal enters scientific identity. Campaign acceptance content order changes intentionally; individual result/authority identity does not.

GLOBAL_RETRAIN_REQUIRED remains binding. Identity stability for this order-only change does not authorize reuse of the historical scientifically affected campaign. Future execution starts fresh OFAT main epoch 0, all 11 fresh OFAT, a new winner, then all 17 fresh comparisons.

## Provenance

Runtime SHA before and after:
baf19aa078973c19e19ed55c8ea6ee2f733db9d9b94a33b0c8e03e74fc695c9a

Existing registry already separates authority_publication_sources from runtime_sources. Campaign source changes are traceable through that first-class provenance value and naturally reevaluate authority targets without changing the scientific runtime hash.

Authority-publication provenance before:
99a8bd23bbe02982c4f2d5540b4cd7002f19a453e1c540fbdc9e53b8a0eee6b7

Authority-publication provenance after:
03333370f61d7029b38d41e86f6500d11347946251d7d5c97ebf46fe2632a9d4

No source-registry exclusion or provenance policy change was needed. Smoke-only code was not added to formal runtime provenance. No model/data/loss/masking/optimizer/EMA/queue/validation science file changed. Full GPU smoke was therefore not rerun.

## Campaign And Progress

Existing dynamic branching consumes the canonically ordered authority collection. Winner barrier and aggregate all-17 acceptance validation are unchanged. No inter-comparison scientific dependency was introduced. Chronological progress records receive the current model from those branches. Final acceptance records retain model order rather than opaque authority-path lexicographic order, and can be consumed directly for ordered result tables.

Target declarations, names, patterns and edges are unchanged. Training graph remains 29 targets / 80 edges, acyclic. Main graph remains 61 targets / 212 edges. No structural dependency-network change occurred, so no HTML regeneration was necessary. Disposable existing branching tests exercise legal expansion and winner/comparison barriers; production targets were not executed.

## Validation

- git diff --check: PASS.
- Python compileall for changed Python modules/tests: PASS.
- R parse R/training_targets.R: PASS; changed R test parsed/executed successfully.
- Config/schema parse: not applicable; no YAML/JSON/schema changed.
- Focused Python campaign/smoke tests: 71 passed.
- Full Python pytest: 628 passed in 97.31 seconds.
- Focused R training-target tests: 60 expectations, 0 failures/warnings/skips.
- Full Rscript tests/testthat.R: PASS.
- _targets.R manifest/validate/DAG: PASS.
- _targets_training.R manifest/validate/DAG: PASS, 29/80.
- Main research-store tar_outdated: empty before, after code changes and after implementation commit.
- Actual prior-function versus repaired authority comparison: 17/17 identical by model.
- Formal/smoke order parity: PASS.
- Full 28-case smoke rerun: NO, order metadata only; existing 28/28 evidence remains applicable to unchanged production runtime.

## Preservation

S08: s08plan_7cd58ffb65db3d43fd3fa234.
Serialized SHA: 74ae70958b96dd663d300c6f7441a0653b1a7c5066d6e1bfe9b4b459d7781789.

Cache: s09cache_dc4e9e271e40ffe8ae17967c.
Acceptance: s09ca_e2a1882eb206e1b5c930ddd5.
80,472 payloads available; no regeneration or full 296 GiB rehash.

Before/after preservation verifier returned PRESERVATION_PASS 2274 10: historical S08/OFAT/winner/checkpoint/comparison/failed-run/cache/log evidence and training-store files unchanged. Evidence recorded only under logs/s09/smoke/20260912_runner_qualification/preservation_order_before_result.json and preservation_order_after_result.json. No ledger/checkpoint/authority/current-status history mutated.

## Safety And Next Action

- Formal training executed: NO.
- GPU/DDP execution: NO.
- Production targets executed: NO.
- Production authority/finalization/acceptance/checkpoint publication: NO.
- Target-store mutation: NO.
- Prepared cache rebuild: NO.
- S10/downstream: NO.
- Implementation commit/push: PASS.
- Next action requires separate authorization: fresh OFAT main epoch 0 -> 11 fresh OFAT -> new winner -> FM,A1,A2,A3,A4,A5,SSV,DS,B1,B2,B3,B4,B5,B6,B7,B8,B9 -> campaign acceptance.

