# P9 v1 Architecture Inventory

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

## Measurement scope

Direct P9 files are tracked paths whose basename or directory contract is P9-specific. Shared P6/P7 primitives bound by the P9 runtime manifest are listed separately and are not double-counted. Counts are reproducible from `git ls-files`, `targets::tar_manifest()`, parsed target commands, and external store inventories.

## Baseline counts

| Measure | v1 count | Notes |
|---|---:|---|
| Direct P9 implementation/config/schema files | 65 | 10 R/target scripts, 19 production Python scripts/modules, 6 config documents, 30 schemas. |
| P9 test files | 13 | 9 Python and 4 R files. |
| Named P9 tests | 77 | 65 Python test functions and 12 R `test_that()` blocks. |
| P9 historical reports | 19 | Through `20260831_2205`. |
| P9 target scripts | 3 | Main `_targets.R`, isolated `_targets_p9_formal.R`, recovery `_targets_p9_recovery.R`. |
| Main DAG P9 targets/edges | 28 / 52 | 50 internal and 2 inbound scientific-parent edges; main DAG total is 190 targets. |
| Isolated formal DAG targets/edges | 26 / 50 | Terminal closure is 25 targets/49 edges. |
| Recovery DAG targets/edges | 11 / 13 | Separate finalization/recovery path. |
| Dedicated P9 stores | 6 | 3 formal generations and 3 recovery generations, besides the main research store. |
| Formal/recovery authority identities | 12 | 9 formal execution authorities and 3 recovery authorities; all become v1-ineligible under retirement. |
| Reservation/attempt/run/recovery identity types | 8 | authority, reservation, preassigned attempt, run, authorization acceptance, recovery authority, recovery reservation, recovery operation; supersession and recovery acceptance add more artifact identities. |
| Mutable state artifact classes | 8 | formal attempt state, worker progress, formal lock owner/heartbeat; recovery operation state, recovery owner/heartbeat; legacy running state. |
| Lock/owner/heartbeat implementations | 3 | GPU pair lock, formal attempt lock, recovery transaction lock. |
| Finalization/recovery paths | 3 | inline successful formal finalization, checkpoint recovery selection, durable recovery transaction. |
| Acceptance/resolver implementations | 3 | formal attempt acceptance, recovery acceptance/`resolve_committed`, target artifact path exposure. |
| Atomic historical checkpoints/validations | 25 / 25 | Join audit is 25/25 `EXACT_MATCH`. |

## Component disposition

| Path | Symbols/targets | Responsibility and artifacts | State/plane | Current consumer | v2 disposition |
|---|---|---|---|---|---|
| `_targets.R` | 28 `p9*` targets | Main cache authorization, cache materialization, formal authority, formal execution, selected checkpoint, acceptance. | Mixed; control invokes science | Main research DAG | RETIRE P9 execution portion; retain unrelated graph. |
| `targets/research_p9_infrastructure.R` | `p9_infrastructure_*` | Readiness contract file set and readiness publication. | Immutable/control | Main DAG, formal authority | ADAPT accepted readiness as immutable parent. |
| `targets/research_p9_formal_authorization.R` | 24 targets | Cache plan/build/acceptance plus corrected authority/reservation and inline run/finalization. | Mixed | Main DAG | REPLACE with v2 coarse graph. |
| `R/research_p9_infrastructure.R` | `build_p9_infrastructure_readiness` | Validates P8/P7 and P9 infrastructure contracts. | Control | Main DAG | ADAPT parent validation only. |
| `R/research_p9_formal_authorization.R` | `p9_*` publication/execution helpers | Plans cache, publishes authority, invokes trainer, exposes run artifacts. | Mixed | Main target definitions | REPLACE; split planes. |
| `python/p9_infrastructure.py` | plan/readiness/model-family helpers | P9-A/P9-B planning, evaluation ancestry gates, bounded readiness. | Scientific contract | Infrastructure scripts/tests | RETAIN scientific validation helpers; remove orchestration coupling. |
| `python/p9_data.py` | P9 data/cache adapters | Production cache consumption and evaluation-query denial. | Scientific | Trainer/model smoke | RETAIN/ADAPT. |
| `python/p9_model_families.py` | P9 model families | Model architecture and family routing. | Scientific | Trainer/smoke | RETAIN. |
| `scripts/p9_infrastructure.py` | CLI | Readiness publication entry point. | Control | R target | ADAPT to bundle input validator. |
| `scripts/p9_model_family_smoke.py` | CLI | Bounded model-family smoke. | Scientific | Tests/manual gates | RETAIN as test-only. |
| `scripts/p9_bounded_main_pilot.py` | pilot CLI | Bounded cache/model/DDP pilot and GPU locks. | Mixed | Infrastructure audit | RETIRE from formal control; retain test fixtures selectively. |
| `scripts/p9_production_cache.py` | cache CLIs | Production cache plan/materialization/validation. | Scientific data preparation | Main P9 cache targets | RETAIN frozen cache tooling; no v2 training write path. |
| `config/p9_infrastructure.yml` | readiness/config | Population, sampler, execution, selection, prohibitions. | Immutable scientific config | Infrastructure | ADAPT into canonical scientific config. |
| `config/p9_formal_authorization.yml` | original authorization config | Cache and formal authorization inputs. | Immutable historical control | Main authorization | FREEZE legacy. |
| `config/p9_formal_reauthorization.yml` | corrected authorization config | Corrected runtime and prior supersession. | Immutable historical control | Main authorization | FREEZE legacy. |
| `config/p9_global_batch_sampler_contract.json` | sampler contract | Corrected 2,421-scene collision-free global batching. | Immutable scientific | Formal authority/trainer | RETAIN as parent contract. |
| `config/schemas/p9_cache_*.schema.json` (4) | cache schemas | Reuse graph, identity, resource, shard plan. | Immutable data contract | Cache planner | RETAIN for cache history; adapt only if future cache changes. |
| `config/schemas/p9_production_cache_*.schema.json` (3) | cache authority/acceptance/startup | Cache build authority, cache acceptance, startup evidence. | Control | Cache/formal gates | RETAIN accepted evidence; replace new authority schema. |
| `config/schemas/p9_infrastructure_readiness.schema.json` | readiness schema | P9 readiness acceptance. | Control | Main/formal roots | RETAIN accepted parent. |
| `config/schemas/p9_training_configuration.schema.json` | training config | Scientific configuration row. | Scientific | P8/P9 | ADAPT into bundle scientific config. |
| `config/schemas/p9_run.schema.json`, `p9_execution_record.schema.json` | run/execution | Combined run and execution identity. | Mixed | Formal runner | REPLACE with ledger/run bundle. |
| `config/schemas/p9_checkpoint_manifest.schema.json`, `p9_validation_history.schema.json`, `p9_checkpoint_selection.schema.json` | checkpoint/validation | Older checkpoint, history, selection formats. | Scientific | Main P9 path | MIGRATE evidence; replace runtime schemas. |
| `_targets_p9_formal.R` | 26 targets | Isolated roots, authorization publication, one formal run, artifact leaves. | Mixed | Formal store | REPLACE with eight-target v2 graph. |
| `targets/research_p9_formal_execution.R` | `p9x_*`, 26 targets | Root validation, authorization, formal invocation, six final artifacts. | Mixed | Isolated graph | REPLACE. |
| `R/research_p9_formal_execution_isolated.R` | `p9x_*` | Runtime validation, authorization CLI, trainer CLI, artifact resolution. | Control | Isolated targets | REPLACE with controller/bundle/finalizer APIs. |
| `python/p9_formal_isolated_authorization.py` | publication helpers | Root inventory, supersession, authority/reservation/preassignment/acceptance. | Control | Authorization CLI | REPLACE; preserve manifests as historical evidence. |
| `scripts/p9_formal_isolated_authorization.py` | CLI | Publishes isolated authorization bundle. | Control | R target | RETIRE. |
| `python/p9_formal_execution.py` | `FormalAttemptLock`, checkpoint/state/selector helpers | Locking, mutable progress resolution, checkpoint IO, validation and acceptance payloads. | Mixed | Formal trainer | SPLIT: retain scientific checkpoint semantics, replace control/finalization. |
| `scripts/p9_formal_training.py` | controller/worker/startup CLIs | Controller, DDP trainer, validation, checkpoint, early stopping, final output publication. | Mixed | Isolated formal target | REPLACE with scientific executor plus one controller. |
| `python/p9_identity_diagnostics.py` | diagnostic helpers | Rank/base/cache/view identity diagnostics. | Scientific diagnostic | Trainer/tests | RETAIN read-only diagnostics. |
| `config/p9_formal_isolated_runtime.yml` | runtime roots/contracts | Store generation, accepted parents, cache, training and validation contracts. | Mixed immutable | Isolated graph | MIGRATE scientific fields; freeze control bindings. |
| `config/p9_formal_isolated_publication.yml` | runtime digest/publication | Runtime file manifest, checkpoint and locking contracts. | Control | Isolated authority publisher | FREEZE legacy; replace with v2 authority manifest. |
| `config/schemas/p9_formal_training_authority.schema.json` | authority | Formal authority. | Control | Isolated runner | REPLACE. |
| `config/schemas/p9_formal_execution_authority.schema.json` | execution authority | Corrected formal execution authority. | Control | Main path | RETIRE duplicate generation. |
| `config/schemas/p9_formal_attempt_reservation_v2.schema.json`, `p9_cfg_main_attempt_reservation.schema.json` | reservations | Duplicate attempt reservation contracts. | Mutable/control | Formal controller | REMOVE; authority plus run identity and lock suffice. |
| `config/schemas/p9_isolated_preassigned_attempt.schema.json` | attempt preassignment | Preallocates attempt identity. | Control | Isolated controller | REMOVE. |
| `config/schemas/p9_isolated_execution_authorization_acceptance.schema.json` | authorization acceptance | Accepts authority publication. | Control | Isolated controller | REMOVE; authority validation is intrinsic. |
| `config/schemas/p9_formal_execution_supersession.schema.json` | supersession | Marks older execution identities ineligible. | Immutable/control | Authority validators | RETAIN legacy history; v2 uses acceptance status/index. |
| `config/schemas/p9_formal_running_state.schema.json`, `p9_formal_failed_state.schema.json` | mutable/terminal state | Collapsed controller/scientific state. | Mutable/control | Formal controller | REPLACE with ledger state dimensions. |
| `config/schemas/p9_formal_validation_event.schema.json` | validation event | Validation-only record without atomic checkpoint binding. | Scientific | Trainer/finalizer | REPLACE with atomic combined event. |
| `config/schemas/p9_formal_resume_checkpoint.schema.json`, `p9_formal_terminal_execution.schema.json`, `p9_formal_attempt_acceptance.schema.json` | resume/final/accept | Resume and inline finalization chain. | Mixed | Formal target leaves | REPLACE. |
| `config/schemas/p9_isolated_immutable_root_inventory.schema.json` | parent inventory | Immutable root binding. | Control | Isolated authority | ADAPT into source inventory digest. |
| `_targets_p9_recovery.R` | 11 targets | Separate recovery authorization, selection, finalization and acceptance. | Control | Recovery store | RETIRE; ordinary finalization reruns finalizer. |
| `targets/research_p9_checkpoint_recovery.R` | 11 targets | Recovery DAG declaration. | Control | Recovery script | RETIRE. |
| `R/research_p9_checkpoint_recovery.R` | `p9r_*` | Publishes recovery authority, joins candidates, invokes transaction. | Control | Recovery targets | RETIRE after importer validation. |
| `python/p9_checkpoint_recovery.py` | `audit_pairs`, recovery payload | Read-only validation/checkpoint join and selection. | Scientific evidence/finalization | Recovery controller | ADAPT logic into importer and pure finalizer tests. |
| `python/p9_recovery_transaction.py` | `RecoveryLock`, `RecoveryTransactionController`, `resolve_committed` | Large recovery-only lock/state/commit/resolver protocol. | Control | Recovery CLI | REPLACE with pure finalizer and short acceptance commit. |
| `scripts/p9_checkpoint_recovery_authorization.py` | publish/execute CLIs | Recovery authority/reservation/operation and durable transaction. | Control | Recovery R helper | RETIRE. |
| `tests/test_p9_*.py` (3) | 22 tests | Infrastructure, model families, authorization. | Test | CI | ADAPT retained scientific tests. |
| `tests/python/test_p9_*.py` (6) | 43 tests | Bootstrap, formal execution, isolated authorization, identity, recovery/crash. | Test | CI | REBALANCE around plane boundaries, ledger, finalizer, publisher. |
| `tests/testthat/test-p9-*.R` (4) | 12 tests | Main/isolated/recovery target and authorization behavior. | Test | CI | REPLACE with eight-target closure tests. |
| `reports/20260830_1419_p9_*.md`, `reports/20260831_*p9*.md` (19) | reports | Audit, execution, failure, correction, recovery history. | Immutable evidence | Human audit/migration | RETAIN unchanged. |

## Shared runtime dependencies

The formal runtime manifest also binds `python/canonical_config.py`, `python/p6_data.py`, `python/p6_model.py`, `python/p7_geometry_cache.py`, `python/p7_training.py`, `python/prototype_encoder.py`, `python/rotating_padding_sampler.py`, `scripts/p7_prototype_training.py`, `config/p6_model_dataloader.yml`, and `config/p7_deterministic_training.yml`. These are scientific-plane dependencies. V2 must reference their source inventory digest but should not copy their control-plane patterns.

## External artifacts and stores

| External path/type | Count/status | Mutable? | Disposition |
|---|---:|---|---|
| Main research store `targets/fuse-research` | one store | targets metadata mutable | No v2 scientific dependency. |
| Formal stores `targets/fuse-p9-formal*` | 3 generations | historical metadata | Freeze/read-only label. |
| Recovery stores `targets/fuse-p9-recovery*` | 3 generations | historical metadata | Freeze/read-only label. |
| Formal attempt roots | 3 started historical attempts plus preassignments | terminal evidence immutable; progress was mutable | Preserve; importer reads one run only. |
| Formal lock namespace | `.lock`, `.owner.json`, `.heartbeat.json` per duplicate key | owner/heartbeat mutable | Freeze records; v2 uses one training lock class. |
| Recovery lock namespace | lock, owner, heartbeat, operation state | mutable if executed | Never execute v1; v2 publication uses separate short lock. |
| Production cache | 314,695 files; 391,466,804,516 bytes | accepted immutable | Retain read-only parent. |

## Downstream status

V2-E migrated P9-B, selected-FM, held-out evaluation, P10, and P11 to the
single `resolve_accepted_checkpoint(acceptance_identity)` contract. V2-G
published canonical acceptance `p9accv2_d93b01ef13c3f26a22287ce7`; V2-I
retired `resolve_committed()` and all manual, latest, v1 identity, store-path,
bundle-path, and finalization-path entry forms. V1 consumers are historical
inspection surfaces only and cannot provide downstream checkpoint evidence.
