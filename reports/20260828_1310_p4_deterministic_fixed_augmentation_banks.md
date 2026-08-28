# P4 Deterministic Fixed Augmentation Banks

## 1. VERDICT

`P4_FIXED_AUGMENTATION_BANKS_PASS_PUSHED` is the intended terminal verdict. At report creation, implementation, production, acceptance, repeated no-op, and pre-commit validation are PASS. Commit and push results are recorded in the delivery response because a commit cannot contain its own SHA without changing that SHA.

## 2. Repository state

- Execution date: 2026-08-28 Asia/Seoul.
- Fuse branch: `reduced`; starting HEAD and `origin/reduced`: `716279b5ab1030e5e85b8e0d26a0d5b049383805`; starting ahead/behind `0/0`; starting tree clean.
- Dissertation branch: `reduced`; HEAD `e66d17d65e97a5e3f50fa9a111a51559db05666f`; tree clean.
- Research store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-research`.

## 3. Previous authority conflict

The earlier report `reports/20260828_0223_p4_fixed_augmentation_banks.md` recorded four unresolved byte-level mechanics and generated no bank. The user-approved supplement resolves them as entity-level geometry fallback, SHA-256 counter draws, floor removal counts, and canonical multi-donor receiver composition. The previous report remains unchanged as historical evidence.

## 4. Authority supplement revision

Supplement `p4-determinism-v1` is tracked by `config/p4_deterministic_augmentation.yml`, its JSON schema, and the P4 blueprint section. It changes no dissertation scientific operation and does not replace the immutable P0 authority. It defines only deterministic mechanics required to materialize P4.

## 5. P0-P3 verification

Verified accepted parents:

- P0 authority `mta_f90fecff7bc7bb5d231cc79f`.
- P1 scene index `rsi_80031f1493c75163f91b7c71`; acceptance `sia_0a997e576367b1133517bf6a`.
- P2 observation `obs_cd00016f6b5bfd960b0a6842`; acceptance `bsa_e617ee0280a6edfa722994d3`.
- P3 cache `oscache_c89fa07e3d6cb1819a7994a6`; acceptance `osca_a55d2c02c3737c5f5557092a`; Serialization-v3 `3.0.0`; 96 shards; 4,421 scenes; 2,296,125,440 bytes.

## 6. Implemented targets

The active P4 graph is:

1. `augmentation_profile_plan`
2. `road_link_absorption_smoke`
3. `geometry_consistency_smoke`
4. `augmentation_bank_plan`
5. `augmentation_bank_shard` (288 branches)
6. `augmentation_bank_shard_validation` (288 branches)
7. `augmentation_bank_acceptance`
8. `effective_augmentation_bank_index`
9. `augmentation_bank_benchmark`

Tracked supplement/config/schema inputs invalidate the required P4 lineage. Serialization-v2, obsolete online augmentation, P5+, maintenance, GPU, training, checkpoint, and evaluation targets are not active P4 ancestors.

## 7. Population and profiles

P4 covers the 2,421 training scenes only. Validation 400 and evaluation 1,600 scenes have zero training-bank membership. Weak `0.5x`, main `1.0x`, and strong `2.0x` each contain 38,736 physical views (`2,421 x 16`), totaling 116,208.

## 8. Digest-to-RNG contract

Randomness is derived from the canonical UTF-8/NFC seed payload and domain-separated SHA-256 counter blocks. Uniform integers use unsigned 64-bit rejection sampling; binary64 uniform values use 53 mantissa bits; Gaussian values use the Box-Muller cosine branch without spare caching; without-replacement selection uses partial Fisher-Yates over canonical stable IDs. Worker identity, scheduling, runtime path, timestamp, and global RNG state are excluded.

## 9. Removal-count contract

Direct removal count is `floor(f * N)`, clamped to `[0, N]`, with no forced minimum. Building-hosted POIs are cascade removals and do not consume the directly sampled quota. Production direct/cascade counts were:

| Profile | Direct | Cascade | Primary targets |
|---|---:|---:|---:|
| weak | 947,318 | 446,988 | 949,594 |
| main | 1,897,677 | 900,094 | 1,902,448 |
| strong | 3,807,262 | 1,803,580 | 3,819,106 |

## 10. Entity-level geometry fallback

Each selected entity uses deterministic attempts 1 through 10 and accepts the first valid result. After ten failures it retains the original post-removal/post-absorption geometry and matching derived values with complete attempt provenance. Fallbacks were weak 8,906, main 32,375, and strong 906,879; unresolved candidate failures were zero.

Attempt distributions:

| Profile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| weak | 12,092,174 | 511,187 | 92,507 | 24,197 | 8,373 | 3,560 | 1,805 | 1,035 | 607 | 9,373 |
| main | 10,315,706 | 1,303,896 | 414,848 | 170,195 | 81,764 | 44,156 | 25,921 | 16,161 | 10,734 | 39,691 |
| strong | 6,315,878 | 1,730,457 | 940,893 | 586,073 | 397,327 | 284,518 | 212,575 | 163,639 | 129,907 | 1,012,260 |

## 11. Multi-donor receiver composition

Receiver parts precede donor parts; donors are ordered by canonical road ID and original part index. Geometry component boundaries and nested source-node chain offsets are retained. The complete donor-to-receiver map is fixed before relation remapping. Donor receivers, chains, cycles, cross-type/hierarchy assignments, and unresolved receivers are rejected.

## 12. Physical K16 bank

- Master-bank ID: `augbank_a470cb156612cff12fb316fc`.
- Acceptance ID: `aba_b6ee67e0d798020a6c418c05`.
- Physical candidates: 116,208, with zero missing or duplicate candidates.
- Aggregate content SHA-256: `7e4a629367de14159264c9cb7bc6254e16715d14460037770409a384dd790151`.

## 13. Logical K2/K4/K8/K16 indices

Logical subsets are prefixes of each scene/profile K16 master and contain no duplicated payload. Effective index ID is `abi_f9ff792612ca86f486576491`; its 217,890 rows cover K2/K4/K8/K16. K8 references total 58,104, 19,368 per profile. Prefix/linkage violations are zero.

## 14. Receiver absorption

| Profile | Absorbed donors | Receiver groups | Unique receivers |
|---|---:|---:|---:|
| weak | 28,582 | 28,133 | 23,056 |
| main | 56,793 | 55,032 | 38,101 |
| strong | 112,911 | 105,433 | 54,796 |

Absorbed-donor provenance equals absorbed-donor count for every profile. Invalid receivers and receiver cycles are zero.

## 15. Geometry/derived consistency

All stored geometry remains float64. Invalid geometry, float32 downcast, and derived-value violations are zero. The maximum independently measured geometry-derived error is `0.0`.

## 16. Relation consistency

SN is reconstructed from final geometry; CNT/WIT/INT/CON use the authority-defined preservation/remapping contract. Dangling endpoints, applicability violations, topology violations, and relation validation failures are zero. Final relation counts are:

| Profile | SN | CNT | WIT | INT | CON |
|---|---:|---:|---:|---:|---:|
| weak | 391,045,682 | 17,064,972 | 17,064,972 | 5,982,674 | 4,106,346 |
| main | 380,857,246 | 16,209,884 | 16,209,884 | 5,795,758 | 3,988,368 |
| strong | 360,426,518 | 14,586,521 | 14,586,521 | 5,427,014 | 3,753,222 |

## 17. Artifact identity/publication

Artifact root is `/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/augmentation_banks/augbank_a470cb156612cff12fb316fc/`. Branches write to isolated staging, validate schema/scientific checksums, then publish atomically. Immutable collision and incomplete-publication violations are zero.

Payload size is 10,849,576,960 bytes: weak 2,721,812,480; main 3,354,890,240; strong 4,772,874,240.

## 18. Tiered workers

All workers used one internal/native thread. Pass A was the mandatory full production pass. Its external fail-soft ledger is `execution/pass_a_40_20260828_0504/ledger.json` under the bank root.

| Pass | Workers | Input branches | Completed | Native failed | Resource failed | Scientific failed | Unattempted | Peak concurrency | Peak RSS | Wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 40 | 288 | 288 | 0 | 0 | 0 | 0 | 40 | 70,676,267,008 bytes aggregate | 15,564.65 s |
| B | 10 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | not run |
| C | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | not run |

The ledger content SHA-256 is `0762072ad50e703c04e589951b5f5ed33b3fef08620f5fe8cd7cbcbd04a27e80`. Earlier Crew-based preflights produced no canonical branch and were quarantined because target-level crash handling could not satisfy the required branch-isolation/retry policy. They are excluded from Pass A statistics.

## 19. Tests and validation

- R/Python syntax and YAML/JSON parsing: PASS.
- Focused P4 Python tests: 22 PASS.
- Focused P4 R tests: 12 expectations PASS.
- Full Python suite: 97 PASS.
- Full R suite: PASS with three documented legacy-lineage skips.
- Actual acceptance, effective-index, and benchmark JSON Schema validation: PASS.
- `tar_manifest()`: nine canonical P4 targets present; 288 generation and 288 validation branches.
- `tar_validate()`: PASS.
- P4 `tar_outdated()`: zero.
- Dependency network HTML regenerated from the current manifest.

## 20. Repeated no-op

The immediate repeated explicit selection completed in 2.2 seconds with 1,359 targets skipped and zero recomputation. Payload path/size/mtime and SHA snapshots were identical. Bank, acceptance, effective-index, benchmark, and aggregate checksums were unchanged.

## 21. P3 immutability

All 96 P3 tar files have identical normalized path, size, mtime, and SHA-256 before and after P4. P3 cache manifest SHA-256 remains `8b620d9682160dc5e7126ca880dd7a55a97258fcc43aad3752f1de8bae1d2368`; P3 acceptance SHA-256 remains `349b11dfeff27bb58925298a2065d374e7a67b3ef9051ac3dadc480a0a3329c7`. Mutation count is zero.

## 22. P5+/maintenance/GPU non-execution

P5+ target execution count is zero. Maintenance target execution count is zero. GPU target/work count is zero. Existing unrelated system processes were not modified.

## 23. Files changed

Changes are limited to P4 R/Python helpers, research target registration, deterministic config and schemas, P4 tests, the approved P4 blueprint evidence, regenerated target-network HTML, and this report. No target store, bank payload, staging output, execution log, credential, or cache file is included in Git.

## 24. Warnings

The initial Crew execution mechanism could not isolate native worker failure without target-level retries. Production therefore used the dedicated fail-soft branch runner, preserving the same scientific branch identity and immutable publication contract. Pass A then completed without branch failure. No unresolved scientific warning remains.

## 25. Commit

- Planned message: `Implement deterministic P4 augmentation banks`.
- Starting commit: `716279b5ab1030e5e85b8e0d26a0d5b049383805`.
- The exact resulting SHA is reported after commit; embedding a commit's own SHA in its content is self-referential.

## 26. Push verification

Push, fetch, local/remote SHA equality, ahead/behind, and final clean-tree results are reported after the commit and push complete.

## 27. Recommended next action

After successful commit/push synchronization, the next single work unit is `P5 Fixed Validation and Evaluation Queries implementation`.

## Input prompt summary

Implement the user-approved `p4-determinism-v1` supplement and P4 fixed augmentation banks from the accepted P3 cache; generate three training profiles with physical K16 and logical nested subsets; execute full production with mandatory 40-worker Pass A and fail-soft recovery tiers; validate determinism, topology, relations, geometry-derived values, and P3 immutability; then commit and push only after complete PASS.
