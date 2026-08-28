# P5 Fixed Validation and Evaluation Queries

## 1. VERDICT

`P5_FIXED_VALIDATION_EVALUATION_QUERIES_PASS_PENDING_COMMIT`

P5 deterministic-query supplement, production payloads, independent acceptance, schema validation, deterministic replay, and no-op verification passed. This report is finalized with Git and push evidence after the implementation commit.

## 2. Repository Pre/Post State

- Execution date: 2026-08-28 (Asia/Seoul)
- Fuse pre-state: `reduced` at `ebac321b8105c32d249af41d8923930e38e8825a`, synchronized with `origin/reduced`, clean.
- Dissertation: `reduced` at `e66d17d65e97a5e3f50fa9a111a51559db05666f`, clean and unchanged.
- No pull, merge, rebase, reset, checkout, stash, force operation, or bare `tar_make()` was used.

## 3. Conflict Resolution and Supplement Decision

The user-approved `p5-fixed-query-v1` supplement resolves the earlier conflict: validation/evaluation queries do not use the training-only P4 K16/K8 bank. P5 generates two independent `main_1.0x` views directly from each accepted P3 validation/evaluation original under isolated `validation-query` and `evaluation-query` namespaces. The artifact schema is `1.0.0`.

## 4. Accepted P0-P4 Identities

| Parent | Accepted identity |
|---|---|
| P0 authority | `mta_f90fecff7bc7bb5d231cc79f` |
| P1 scene index / acceptance | `rsi_80031f1493c75163f91b7c71` / `sia_0a997e576367b1133517bf6a` |
| P2 observation / acceptance | `obs_cd00016f6b5bfd960b0a6842` / `bsa_e617ee0280a6edfa722994d3` |
| P3 cache / acceptance | `oscache_c89fa07e3d6cb1819a7994a6` / `osca_a55d2c02c3737c5f5557092a` |
| P4 supplement / master / K8 | `p4-determinism-v1` / `augbank_a470cb156612cff12fb316fc` / `abi_f9ff792612ca86f486576491` |

## 5. Seed Payload and RNG Derivation

The root digest is SHA-256 over compact canonical JSON with sorted keys: schema version, namespace, scene ID, query index, profile ID, P3 cache ID, augmentation-contract ID, and accepted augmenter implementation SHA-256. Operation/entity/attempt substreams derive from that root digest, then use the unchanged P4 counter-based digest-to-RNG conversion and draw order. Paths, timestamps, workers, shard count, host/user, store, staging, and device fields are excluded from scientific identity. P4 training fixtures remained byte-identical under the generalized seed helper.

## 6. Implemented Targets

1. `p5_deterministic_contract_files`
2. `fixed_query_methodology_contract`
3. `fixed_query_shard_plan`
4. `fixed_validation_query_plan`
5. `fixed_evaluation_query_plan`
6. `fixed_query_branch_plan`
7. `fixed_query_shard`
8. `fixed_query_shard_validation`
9. `fixed_query_acceptance_bundle`
10. `fixed_validation_query_acceptance`
11. `fixed_evaluation_query_acceptance`
12. `fixed_query_acceptance`

The final ancestry contains 72 P0-P5 authority/data targets. No P6+, maintenance, model execution, training, checkpoint, embedding, retrieval metric, or GPU target is an executable ancestor.

## 7. Validation/Evaluation Query and Gallery IDs

| Split | Query index | Gallery | Mapping | Split acceptance |
|---|---|---|---|---|
| validation | `fqi_00a6e199fa4514ae0d8c701d` | `fgg_325a8031c9428d72943848ff` | `fqpm_00f984944f2ef4886a01f594` | `fqsa_adee2b7d92f37f33ba9e3882` |
| evaluation | `fqi_55aa7d01752b5f3b1bdbd6c2` | `fgg_2fa46178130bfc397a9e722c` | `fqpm_1534ab2bf81f24a6a94c0cae` | `fqsa_3a2581d57c735d2e5ebc91fd` |

Query authority: `fqa_bee6289f2531ae48c6f3a550`. Aggregate acceptance: `fqaac_ee6a31db9941031d3db650f6`. Aggregate content SHA-256: `ee6a31db9941031d3db650f67d1fa7029b28e832236cf6e961b6ac5f5c53f004`.

## 8. Exact Populations

| Split | Originals | Queries | Gallery references | Query indices |
|---|---:|---:|---:|---|
| validation | 400 | 800 | 400 | `{0,1}` per scene |
| evaluation | 1,600 | 3,200 | 1,600 | `{0,1}` per scene |
| total | 2,000 | 4,000 | 2,000 | exactly two per scene |

Training membership, P4 K8/K16 membership references, duplicate IDs, missing/orphan references, and cross-split leakage are all zero. Total immutable query payload is 411,361,280 bytes across 192 branches.

## 9. Query-Positive Mapping

Independent validation confirmed exactly one P3 positive per query, exactly two queries per gallery scene, matching split/scene lineage, distinct query indices and root seed digests, canonical query/gallery ordering, and complete P3 shard/member checksums.

## 10. Augmentation/Geometry/Raster/Relation/Topology Validation

All 4,000 payloads were independently read and checked for profile/namespace parity, float64 geometry, raster shape/dtype/channel, entity identity, dependency cascade, receiver absorption provenance, source-node topology, geometry-derived consistency, reconstructed SN, preserved CNT/WIT/INT/CON semantics, and zero dangling references. All 192 shard manifests and validators passed.

## 11. P4 Backward Parity

Focused P4/P5 Python regression tests passed 42 cases. Generalizing the seed entry point preserved accepted P4 seed derivation, operation/draw ordering, and fixture payload bytes. P4's 288 canonical shard path/size/mtime/SHA-256 snapshot remained unchanged.

## 12. Worker Pass A/B/C Results

| Pass | Workers | Input branches | Completed | Native/resource/scientific failed | Unattempted | Result |
|---|---:|---:|---:|---:|---:|---|
| A | 40 | 192 | 192 | 0 / 0 / 0 | 0 | PASS |
| B | 10 | 0 | 0 | 0 / 0 / 0 | 0 | Not run |
| C | 5 | 0 | 0 | 0 / 0 / 0 | 0 | Not run |

Pass A ran in tmux session `fuse-p5-final-pass-a`, reached 40 simultaneous branch processes, used one internal thread per worker, and completed in 12 minutes 5.5 seconds. Ninety-five empty, dot-prefixed staging directories from isolated attempts remain outside accepted lineage; they contain no accepted payload and were not deleted. Canonical branch count is exactly 192.

## 13. Repeated No-op Verification

After blueprint evidence reconciliation, all 202 accepted payload/index/acceptance files retained identical size, mtime, and SHA-256. The immediate second explicit selection skipped all 1,174 ancestry targets in 2.3 seconds, rewrote zero payloads, and left P5 outdated count at zero.

## 14. P3/P4 Immutability

Pre/post snapshots of all 96 P3 and 288 P4 tar payloads matched exactly for path, size, mtime, and SHA-256. P3 mutation: 0. P4 mutation: 0. The P5 reconciliation revalidated immutable references but did not rewrite canonical parent or P5 payload bytes.

## 15. P6+/Maintenance/GPU Non-execution

- P6+ scientific target executions: 0
- Maintenance target/store executions: 0
- Model/DataLoader/forward, embedding, retrieval metric, training, and checkpoint executions: 0
- GPU target/operation executions: 0
- User GPU compute processes observed: 0

## 16. Tests and Schema Results

- R parse: PASS for all changed R files.
- Python compile: PASS for all changed Python files.
- YAML/JSON parse: PASS.
- Actual artifact JSON Schema: supplement 1, plan 1, shard 192, split acceptance 2, aggregate acceptance 1, all PASS.
- Focused Python P5/P4 tests: 42 PASS.
- Focused R P5 tests: 18 expectations PASS.
- Full Python suite: 131 PASS.
- Full R suite: 680 PASS, 3 pre-existing documented legacy skips, 0 failures/warnings.
- `targets::tar_validate()`: PASS.
- Dependency network regenerated and validated.
- `git diff --check`: PASS.

## 17. Changed Files

Changes are limited to P5 R/Python implementation and target registration, tracked P5 config and schemas, P5 tests, the P5 blueprint supplement/evidence, the research target-network HTML, and this report. No target store, generated query payload, cache, credential, or temporary file is included in Git.

## 18. Warnings and Unresolved Matters

The 95 empty staging directories are execution residue only and are not referenced by manifests or target metadata. They were retained to avoid destructive cleanup during acceptance. No scientific blocker remains.

## 19. Commit SHA/Message

Implementation commit: pending. Planned message: `Implement P5 fixed evaluation queries`.

## 20. Push/Local-Remote Synchronization

Pending commit and fast-forward push verification.

## 21. Recommended Next Action

After successful push synchronization, the single next work unit is **P6 Model and DataLoader implementation**.

## Input Prompt Summary

The user approved an independent P5 deterministic-query supplement, required two fixed `main_1.0x` validation/evaluation views generated from P3 originals with P4 augmenter parity, exact 800/3,200 query populations, immutable publication, independent validation, tiered workers, repeated no-op, P3/P4 immutability, and commit/push only after complete PASS.
