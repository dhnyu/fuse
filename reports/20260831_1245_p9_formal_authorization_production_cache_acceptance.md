# P9 Formal Authorization and Production Cache Acceptance

## Verdict

`P9_FORMAL_AUTHORIZATION_AND_PRODUCTION_CACHE_ACCEPTANCE_PASS_PUSHED` is the
publication verdict, conditional on the final report commit reaching
`origin/reduced`. All scientific, cache, lineage, resource, immutability, and
locking gates passed before publication. No optimizer, formal validation,
checkpoint, formal attempt, selected-FM materialization, evaluation, P10/P11,
or maintenance execution occurred.

Executed in Asia/Seoul on 2026-08-30 through 2026-08-31. The task was to close
the P9 production-cache and authorization gates without starting `cfg_main`.

## Source and lineage

- Starting repository commit: `8243bfcc46e1357f6ca9b8a90c0f90d3b84df87c`.
- Canonical P9 scientific publication commit:
  `eb90f6f667d1717684f47ddef30043992b70e788`.
- P9 implementation commit: `9e700754023c548d9940acba854f4559a05888a3`.
- Actual cache-build execution commit:
  `2c5b4904449842dea4d6c479067d6d05f952359f`.
- Formal-authority execution commit:
  `58de20063dec9c2df3da33d5a8438915059e4c7a`.
- Dissertation binding: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`.
- P9 readiness: `p9ready_521c12a65d9b2984fac2cf11`.
- P8 acceptance: `p8acc_c9f16a07275aadfae928d329`.
- P7 runtime acceptance: `p7rta_c780441a553abe26772827d0`.

The only change after the accepted P9 publication and before this work was the
target-network visualization commit. Its changes were confined to renderer,
phase metadata, tests, generated HTML, and a report. It did not change training,
data materialization, model, optimizer, validation, augmentation, schema, or
scientific configuration semantics.

## Scoped outdated-cause audit

`p7_cold_path_runtime_contract_files` and
`p8_experiment_plan_contract_files` were invalidated by an over-broad inventory
that included `blueprint/targets_implementation_blueprint.md`. Downstream P9 and
visualization prose changed that file, while the accepted P7 runtime and P8
scientific publication bundles remained byte-identical. Canonical readback of
the accepted identities passed and P9 readiness bound the required P7/P8 IDs.
No one of the 124 historical outdated targets was rebuilt.

## Cache plan and reuse graph

Plan artifacts:

- Reuse graph: `p9crg_92a86bc73543a605b97d3964`.
- Identity contract: `p9cic_2cf5f42c0692ca551c5f313e`.
- Resource plan: `p9crp_db40e4103aa6dfcc5fea2e9d`.
- Shard plan: `p9csp_e44df96c35f941c32822a646`.
- Cache-build authority: `p9cba_5c472951ac896e82a0a0f555`.

The union has exactly 78,672 logical realized-view entries:

`2,421 * 16 + 2,421 * 8 + 2,421 * 8 + 800 + 400 = 78,672`.

| Family | Role/profile | Entries | Geometry physical bytes | DS physical bytes |
|---|---|---:|---:|---:|
| main K16 | training, 1.0x | 38,736 | 54,710,931,216 | 40,402,732,608 |
| weak K8 | training, 0.5x | 19,368 | 28,416,350,088 | 20,201,366,304 |
| strong K8 | training, 2.0x | 19,368 | 25,375,619,976 | 20,201,366,304 |
| validation query | fixed query | 800 | 1,143,427,744 | 834,422,400 |
| validation gallery | original | 400 | 617,315,920 | 417,211,200 |
| **Total** | | **78,672** | **110,263,644,944** | **82,057,098,816** |

Main K2/K4/K8 use canonical indexes into K16 with 4,842/9,684/19,368
entries and zero candidate differences. Their overlapping payloads are not
copied. Weak, main, and strong profiles are distinct realized scientific bytes.
Model-only factors (`d`, `d_c`, EMA, `lambda_IP`, peak LR, dropout) reuse the
same inputs. FM and A1-A5 consume subsets of the shared realized views; SSV uses
a subset. DS is a separate deterministic `26x100x100` float32 derived payload,
but does not duplicate upstream observations. Every family is consumed by the
accepted 20-attempt plan.

Cache scientific identity binds layout/schema 3.0.0, immutable
scene/candidate/view/profile and source digests, geometry and DS contracts,
dtype, shape, order, and raw bytes. Rank, worker count, batch order, GPU, and
host are excluded as execution-only values.

## Materialization and resources

- Production cache: `p9cache_f8b16c49f2c63216609b013b`.
- Geometry cache: `p7gc_bc51685a494911392ee6489f`.
- DS cache: `p9ds_1e26585c61122cf7c758088a`.
- Entries: 78,672/78,672 for each derived family.
- Shards: 64 canonical index-modulo shards, 1,229-1,230 entries each.
- Total physical bytes: 391,466,804,516 (including 198,819,220,674 bytes of
  fixed-index prepared staging retained for eager reading).
- Geometry raw bytes: 109,912,676,352; DS raw bytes: 81,818,880,000.
- Build wall: 43,796.85 seconds (12 h 9 min 56.85 s).
- Selected workers: 32; aggregate producer high-water RSS observed about
  163.4 GiB. The conservative admission ceiling was 238.07 GiB.
- Free bytes after publication: 20,419,913,928,704; free inodes: 363,979,890.
- Planned peak additional bytes: 344,300,699,371. Actual retained total was
  13.7% higher, within the authorized 35% plan-overrun gate and with ample disk
  headroom.

The original controller exited after all scientific payload files completed
because runtime resource metadata contained integer dictionary keys that the
canonical serializer correctly rejected. No partial cache was marked valid.
The serialization contract was corrected, all 157,344 payload files were
checksum-validated, and the complete cache was atomically finalized. A selected
target rerun returned the existing manifest in 1.8 seconds and did not launch a
second build.

## Complete validation

The full validation covered all entries, not a sample:

- Missing, duplicate, orphan: 0/0/0.
- Shard checksum failures: 0.
- Manifest/index disagreements: 0.
- Invalid DEM support: 0.
- Shape/dtype/schema failures: 0.
- P7 overlap: 2,144 compared, byte differences 0.
- K-subset overlap byte differences: 0.
- Repeat-build scientific differences: 0.
- Rank-dependent differences: 0.

Read-only two-rank preload used 19,968 entries per rank. Observed cold and warm
walls were 14.511 s and 14.507 s; rank worker walls differed by less than 0.04 s.
No optimizer or retrieval validation was started by this benchmark.

## Published authorization

- Production-cache acceptance: `p9ca_99725ef4c56f8b11b4d71935`.
- Formal P9 authority: `p9a_c16721ffbce259df3f723cdd`.
- `cfg_main` reservation: `p9res_c0f73b80e4f90ed3cc8a3346`.
- Reservation status: `AUTHORIZED_NOT_STARTED`.
- Configuration identity:
  `9ca251b54d6f29379990ae35ffa743f1db2643cf671a8f468fad58becdfd07cb`.
- Duplicate key:
  `0b708391b910174f80ce979562aa0949378449ba548cfa6e62da4a6cc6eeacd4`.
- Seed: 1,749,989,426.
- P9-A configurations: 13; unresolved P9-B templates: 7; P9-B authorities: 0.
- Topology: world size 2, global batch 32, rank batch 16.
- Budget: 200 epochs maximum, 76 updates/epoch, validation every 5 epochs,
  patience 4 events.
- Selection: validation retrieval loss, margin within `1e-4`, then earlier
  epoch. Evaluation ancestry is false.

The lock implementation passed synthetic atomic acquisition, single-owner DDP,
duplicate rejection, exact-resume recognition, heartbeat/liveness, explicit
stale-recovery, and terminal release tests. No production attempt lock exists,
because the reserved run has not started.

## Targets and no-op

Fourteen explicit P9 targets represent parents, cache plan, build authority,
materialization, validation, acceptance, formal authority, and reservation.
The formal authority directly depends on accepted parent references and cache
acceptance. No optimizer target is reachable from this authorization graph.

The selected first publication completed without rebuilding cache. Immediate
repeat execution skipped all 14 targets: builds 0, rewrites 0, GPU execution 0,
staging creation 0. The immutable validation readback verifies manifest SHA,
cache ID, entry count, all failure counters, and prohibited execution counters
without rewriting non-deterministic timing evidence.

Target network: 178 nodes, 551 edges, four weak components; error 0, running 0,
outdated 124, up-to-date 54. Two consecutive renders were byte-identical.

## Validation results

- Focused P9 Python tests: PASS.
- Full Python suite: 222 passed.
- Full R/testthat suite: PASS, exactly three documented legacy skips.
- Python AST/compile, R parse, YAML/JSON parse: PASS.
- All new JSON schemas and canonical JSON readback: PASS.
- `targets::tar_validate()`: PASS.
- Target manifest/network inspection: PASS.
- Read-only dissertation Typst compile: PASS; only known unavailable-font
  warnings were emitted.
- `git diff --check`: PASS.

## Immutability and prohibited execution

Before/after inventories covered 2,392 accepted model files and 1,266 existing
target-store objects. All pre-existing checksums matched. P1-P8 artifacts, old
P8 bundle, accepted checkpoints, and existing target-store payloads had mutation
count 0. The only store changes were metadata/objects for the explicitly selected
new P9 authorization targets.

| Prohibited action | Count |
|---|---:|
| Optimizer updates / formal training steps | 0 |
| Formal validation retrieval runs | 0 |
| Formal checkpoints | 0 |
| P9-A/P9-B attempts started | 0 |
| Selected-FM materialization | 0 |
| Held-out evaluation queries consumed | 0 |
| P10/P11 or maintenance execution | 0 |
| GPU training processes | 0 |

GPU locks are unlocked and no GPU compute process remains. The dissertation
worktree was unchanged.

## Changed files

Changes are limited to the P9 authorization R/Python orchestration, config,
eight schemas, target declarations, focused tests, phase/network metadata,
generated target-network HTML, and this report. No cache, checkpoint, target
store, log, staging payload, or credential is tracked by Git.

## Next authorized work

The exact next work unit is `P9_CFG_MAIN_FORMAL_ATTEMPT_EXECUTION`, using formal
authority `p9a_c16721ffbce259df3f723cdd`, reservation
`p9res_c0f73b80e4f90ed3cc8a3346`, duplicate key
`0b708391b910174f80ce979562aa0949378449ba548cfa6e62da4a6cc6eeacd4`, and
production-cache acceptance `p9ca_99725ef4c56f8b11b4d71935`. That task must
atomically acquire the reserved lock and start `cfg_main`; this task deliberately
does not provide or invoke an optimizer command.
