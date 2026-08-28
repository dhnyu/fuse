# Revised P4 Augmentation and P0-P6 Rebuild

## 1. VERDICT

`REVISED_P4_P0_P6_PASS_PUSHED`

The revised P4 augmentation, P5 fixed queries and P6 model/DataLoader lineage passed production, independent validation and repeated standard no-op checks. The Git commit and push identifiers are reported by the final task response because a commit cannot contain its own SHA.

## 2. Repository pre/post state

- Execution window: 2026-08-28 19:32 through 2026-08-29 01:36 Asia/Seoul.
- Fuse began at `reduced@77e186c5778b159d79632e1296e3212d7417120f`, synchronized with `origin/reduced` at 0/0.
- Dissertation remained clean and synchronized at `reduced@109355b3d744248ca14749c5f74511537970d660`.
- The only initial Fuse modification was generated `artifacts/targets-network/targets-network.html`: 3 insertions/3 deletions, working SHA-256 `9c71bf812e427d7a79c8f78af24299bb2c40625397e45571b53704b8f3a2a7b8`, HEAD SHA-256 `bd8e71a6883dca5233477db7b1bb040dc61ea7cb0306fe79c169169dd47c79af`.
- Source-to-network inspection and a temporary deterministic regeneration found identical 126-node/405-edge graph data and options; the diff changed only generated widget identifiers. It was classified `AUTHORIZED_PREEXISTING_GENERATED_NETWORK_DIFF`; no manual scientific, P7, maintenance or store state was embedded.
- No non-generated pre-existing change was found. Final official regeneration superseded that intermediate state; final network SHA-256 is `c059fac5b4973d9e9779cd13f638fb7ab74a33634ce849bd82b58c13547973b8`.

## 3. Dissertation authority commit

The imported Typst methodology, Appendix B and training configuration table were read from dissertation commit `109355b3d744248ca14749c5f74511537970d660`. P0 methodology authority rebuilt as `mta_c17568508b283afd3316e925`. No direct methodology conflict remained.

## 4. Blueprint changes

The P4 section now records `p4-augmentation-v2`, revised parameters, Bernoulli vertex selection, deterministic block masking and canonical config identity. P5 records `p5-fixed-query-v2`. P6 evidence records the accepted revised parents and replacement P6 IDs. P7 and later contracts were not changed or executed.

## 5. P4 v1 to v2 parameters

| Parameter | Weak | Main | Strong |
|---|---:|---:|---:|
| `r_rem` | 0.05 | 0.10 | 0.20 |
| `p_jit` | 0.10 | 0.20 | 0.40 |
| `Delta_jit` | 0.5 m | 1 m | 2 m |
| `delta_simp` | 0.5 m | 1 m | 2 m |
| `q_simp` | 0.90 | 0.90 | 0.90 |
| `p_catmask`, `p_catrep`, `p_lane`, `r_rasmask` | 0.05 | 0.10 | 0.20 |
| `sigma_DEM` | 0.5 m | 1 m | 2 m |
| `k_poirep`, `B_ras` | 4, 4 | 4, 4 | 4, 4 |

Relative to v1, the authorized main geometry jitter probability/displacement and simplification tolerance changed from 0.50/2 m/2 m to 0.20/1 m/1 m. Other retained removal, attribute, dependency, absorption, relation and fallback mechanics were regression-tested.

## 6. P4 v2 RNG and block-mask contract

- Supplement `p4-augmentation-v2`, schema `1.0.0`, uses a distinct dissertation- and implementation-bound RNG namespace.
- Eligible non-protected vertices are independently selected by Bernoulli draws; source-network vertices remain protected.
- Land-cover masking selects exactly `round(r_rasmask * N_valid)` valid cells over eight-neighbor adjacency, using round-robin growth, deterministic reseeding and at most four concurrently active fronts.
- Intentional mask and nodata remain distinct. Scene/entity paths reuse the identical realized LC mask and DEM noise field.
- Provenance records initial seeds, reseeds, selection/front-order digests, peak fronts, component count and exact selected count.

## 7. Pilot cases and quantitative results

- Root: `/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/augmentation_banks/pilots/p4_v2_canonical_streaming_20260828_2056`.
- Population: 24 representative training scenes, 63 branches, 1,152 candidates, 268,113,920 bytes.
- Wall time 1,646.9 seconds; peak RSS 1,629,764 KiB.
- Invalid geometry, preserved-relation, dangling-reference and schema violations were zero.
- Exact LC mask count and maximum-four-front checks passed; maximum observed active fronts was four. Fragmented-support reseeds and isolated-cell diagnostics were independently accepted.
- Weak-to-main-to-strong realized perturbation was monotone and deterministic replay was byte-identical.

## 8. P4 v1 versus v2 geometry fallback

The matched pilot main fallback count fell from 3,652 to 298 and strong from 44,290 to 1,495. Production v2 fallbacks were weak 8,494, main 8,372 and strong 15,998, all explicitly recorded with unresolved candidate failures zero.

## 9. Inspector

- Output: `artifacts/augmentation-inspector/p4-augmentation-inspector.html`.
- Size: 27,450,494 bytes; SHA-256 `165c588c28c97adde419f40647613d1bd3f49d9eaf213a0b3167e7fecda1f2da`.
- The same eight scene/view cases were preserved: `3d67.../3`, `861a.../3`, `d8e5.../4`, `9d22.../10`, `6df9.../8`, `d8e5.../15`, `000c.../0`, `10f3.../11`.
- Two generations were byte-identical. Generation took 7.66 seconds with 1,114,656 KiB peak RSS.
- Chromium `file://` desktop 1600px and mobile 390px checks found four nonblank vector canvases, four nonblank raster canvases, revised provenance, LC/DEM modes, attribute controls, no horizontal overflow and zero console errors.

## 10. New P4 identities

- Supplement: `p4-augmentation-v2`.
- Bank: `augbank_252ce67e6d74679b02871e57`.
- Acceptance: `aba_39de6c260a8e427767bc01d6`.
- Logical K8: `abi_66dfe52602ffe442336685e0`.
- Aggregate content SHA-256: `83ea470aa6656d57f15b34f344dd9f712a4f13728f991ca1d5e84654673e029b`.
- Scope: 2,421 training scenes, 116,208 K16 physical candidates, 58,104 K8 references, validation/evaluation membership zero.
- Payload: weak 5,522,186,240; main 5,594,982,400; strong 5,719,449,600; total 16,836,618,240 bytes.

## 11. P4 production Pass A/B/C

| Pass | Workers | Input | Complete | Native | Resource | Scientific | Unattempted | Peak concurrency | Peak RSS | Wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 40 | 288 | 288 | 0 | 0 | 0 | 0 | 40 | 18,116,308,992 B | 11,154.779 s |
| B | 10 | 0 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | not run |
| C | 5 | 0 | 0 | 0 | 0 | 0 | 0 | n/a | n/a | not run |

Every worker used one internal native thread. An initial Crew controller attempt crashed before stable mapped execution; its 40 exact child processes were safely stopped, stages were marked `INCOMPLETE_ABORTED_CREW_WORKER_CRASH`, and canonical publication count was zero. The accepted Pass A used the isolated tiered ledger and did not reuse those incomplete stages.

## 12. New P5 identities

- Supplement: `p5-fixed-query-v2`; authority `fqa_89741b3e7b3ff7e44597ca67`.
- Aggregate acceptance: `fqaac_9151e9e0a34525ac8ecdb444`.
- Validation: index `fqi_d7ec7e7a88237145e72e6f8a`, gallery `fgg_325a8031c9428d72943848ff`, mapping `fqpm_8b8ee2802d95bcc9df1b2f2f`, acceptance `fqsa_27565de68d9432e47fe7b99d`.
- Evaluation: index `fqi_6ecc67271d84706614942d31`, gallery `fgg_2fa46178130bfc397a9e722c`, mapping `fqpm_9f23c45ac43546d2fc05061d`, acceptance `fqsa_10b033797d7e225139d85f34`.
- Pass A completed 192/192 with 40 configured/observed workers, no failure, 23,554,674,688 B peak RSS and 428.369 seconds wall time. Pass B/C were not run.

## 13. Exact P5 populations

Validation contains 400 P3 originals, 800 main-1.0x queries and 400 gallery references. Evaluation contains 1,600 originals, 3,200 queries and 1,600 gallery references. Total query payload is 380,395,520 bytes. Query indices are exactly `{0,1}`; training membership, cross-split leakage, dangling references and P4 bank-member references are zero.

An initial validator invocation used an unresolved tracked sentinel instead of the branch config and rejected all 192 staging branches. That root was marked `INCOMPLETE_REJECTED_VALIDATOR_CONFIG`; it published no accepted artifact and is excluded from production statistics.

## 14. Canonical P4-P6 config identities

- P4 canonical config SHA-256: `0ceb97cb5c0b1cdb05f4f73fc8179b879c09e4a91b079f1407c2f63761259ff1`.
- P5 canonical config SHA-256: `9197e11882c8914005650bf9a6cb370fdfebc607b1d32f53af9cf9e28074b158`.
- P6 scientific config SHA-256 excluding operational paths: `499cda4904633b052a5b55e50212d7f8dc423fe7ece9bdb8e823e1d44c4d21f8`.
- Strict loaders reject duplicate keys, unsupported types/tags and non-finite values. Comments, indentation, mapping order and terminal blank lines do not change identity; semantic scalar or sequence changes do.

## 15. Final P0-P6 identities and supersession

- P0 authority: `mta_c17568508b283afd3316e925`.
- P1/P2/P3 scientific payloads remain reused, including P3 `oscache_c89fa07e3d6cb1819a7994a6` / `osca_a55d2c02c3737c5f5557092a`.
- P4 v1 `augbank_a470cb156612cff12fb316fc` / `abi_f9ff792612ca86f486576491` is immutable and superseded by the P4 v2 identities above.
- P5 v1 `fqa_bee6289f2531ae48c6f3a550` / `fqaac_ee6a31db9941031d3db650f6` is immutable and superseded by P5 v2.
- P6 replacement IDs: model `dma_c09fdf20f402774af8e4ac24`; preprocessing `ppc_4465193d7d1af28291492ee0`; DataLoader `dla_ac640dacf3adcc8f38219589`; smoke `dcs_14f14a5d63675f161e603c0b`; aggregate `mda_2dba53473f273769394a38f2`.
- P6 architecture is unchanged at 934,420 trainable/0 non-trainable parameters, `d=d_c=64`, `d_t=16`, `d_r=32`, three layers, four heads x 16, FFN 64-128-64 and dropout 0.2.

## 16. First and repeated tar_make results

- Explicit revised P4 final selection completed 578 targets and skipped 22 after the accepted bank branches existed. Immediate repeat skipped all 600 and built/rewrote zero.
- Explicit `model_data_acceptance` with normal ancestry completed 400 and skipped 605 in 12 minutes 20 seconds. It traversed the necessary P0-P6 lineage without `shortcut=TRUE`.
- Immediate repeated `model_data_acceptance` skipped all 1,005 reachable targets in 2.4 seconds, with builds zero and rewrites zero.

## 17. Standard tar_outdated results

The active revised P4/P5/P6 target set has outdated count zero. Remaining `tar_outdated()` names belong to declared legacy/future branches outside the accepted P0-P6 selection and do not occur in the final active ancestry.

## 18. Tests and schemas

- Python compile/AST and full suite: 152 passed.
- R full suite: PASS with exactly three pre-existing documented legacy skips and no new skip.
- Focused target-manifest test: 50 assertions passed.
- All JSON schemas structurally valid; changed YAML/JSON parse passed.
- Actual P4 and P5 acceptance artifacts passed their JSON Schemas; all 288 P4 and 192 P5 mapped independent validations passed in the target graph.
- One representative post-production P4 branch was independently reread and validated `PASS` outside the producer path.
- `targets::tar_validate()` passed. Final manifest/network tests and `git diff --check` passed.

## 19. Old artifact immutability

The pre/post snapshot covered 1,770 accepted files (about 13.98 GB): all selected P0-P2 authority/index/acceptance artifacts, 96 P3 shards, 288 old P4 shards, 192 old P5 shards and old P6 artifacts. Path, size, mtime and SHA-256 differences were all zero. Thus P0-P3 payload mutations, old P4 mutations, old P5 mutations and old P6 mutations are all zero.

## 20. P7/P8+/maintenance/GPU non-execution

Final P6 ancestry contains 48 targets and no P7, P8+, maintenance or GPU target. Target metadata created during this task contains zero forbidden target names. `nvidia-smi` reported zero compute processes at final verification. No optimizer, training, checkpoint, model evaluation or GPU operation was started. Unrelated pre-existing tmux sessions were not touched.

## 21. Changed files

Changes are limited to P0-P6 research orchestration, P4/P5 config and schemas, canonical config and immutable-parent helpers, P4/P5/P6 Python/R implementations, tiered runners, tests, blueprint, inspector source/README/generated representative HTML, final generated target network and this report. No target store, production payload, cache, checkpoint, credential or temporary pilot file is included.

## 22. Commit

Planned message: `Implement revised P4 augmentation and rebuild P0-P6 lineage`. The exact SHA is supplied in the final response after the commit is created.

## 23. Push verification

The push is permitted only after staged diff inspection and post-commit validation. Final local/origin SHA and ahead/behind are supplied in the final response.

## 24. Next action

The single next work unit is implementation and two-GPU prototype training under `p7-deterministic-training-v1`, using only aggregate P6 acceptance `mda_2dba53473f273769394a38f2`.

## Prompt summary

Implement revised P4 geometry intensities and deterministic LC block masks from dissertation commit `109355...`, validate a bounded pilot, publish full P4 v2 and P5 v2 immutable artifacts, rebuild the normal P0-P6 lineage with canonical configuration identities, verify no-op and immutability, then commit and push. Preserve and inspect the authorized pre-existing generated network diff; do not execute P7, maintenance or GPU work.
