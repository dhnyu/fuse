# Prototype Relation Implementation Report

## 작업 목적과 범위

- 목적: I09의 15개 aligned observation branch와 I10 `local_entity_id`를 사용해 320개 prototype scene의 I12 `prototype_relation_shard`를 구현하고 검증한다.
- 실행 시각: 2026-08-21 14:54--16:37 KST.
- fuse 기준: GitHub `origin/feature/research-scene-index`의 `7a3ab4b62ea5f8375efe4d2b31b2024755d281bd`에서 시작했다.
- 논문 기준: GitHub `dhnyu/dhnyu-masters-dissertation` `origin/main`의 `73c7f5a65ae18960ac1990af035bca9076210f69`과 `04-spatial-relations.typ`, applicability table을 scientific source of truth로 사용했다.
- 구현 commit: `35744cf42e2bd94b104fefc993d69cf4d5808b24`, branch `feature/research-scene-index`.
- 제외: I09/I10/I11 수정 또는 재실행, I13, serialization, model, full production, raster feature 소비, `seoul_data_preprocess` 연결.

## 최종 판정

`READY`.

15개 I12 branch manifest/QC가 모두 PASS했고, 320 scene 및 I10 node key 정렬, relation 계약, global inverse/symmetry, checksum, representative brute-force reference와 direct rebuild byte determinism이 통과했다. I09/I10/I11 artifact는 변경하거나 재실행하지 않았다.

## Relation 계약

ordered entity pair마다 한 행을 만들고 `uint8 relation_mask`로 복수 relation을 보존한다. bit position은 `SN=0`, `CNT=1`, `WIT=2`, `INT=3`, `CON=4`이며 self-edge는 금지한다. 출력은 `(scene_id, source_local_entity_id, destination_local_entity_id, relation_mask)` 순으로 고정한다.

| source -> destination | 허용 relation |
|---|---|
| Building -> Building | SN, INT |
| Building -> Road | SN, INT |
| Building -> POI(in) | CNT |
| Building -> POI(out) | SN |
| Road -> Building | SN, INT |
| Road -> Road | SN, INT, CON |
| Road -> POI(in) | 없음 |
| Road -> POI(out) | SN |
| POI(in) -> Building | WIT |
| POI(in) -> 기타 | 없음 |
| POI(out) -> Building/Road | SN |
| POI(out) -> POI(in) | 없음 |
| POI(out) -> POI(out) | SN |

- `SN`: EPSG:5186 observed geometry의 exact minimum distance, 100 m inclusive, source별 top-16. `1e-9 m` quantized distance와 destination `local_entity_id`로 tie를 결정하고 어느 한 방향이 선택하면 양방향을 보존한다.
- `CNT/WIT`: POI point가 observed Building에 strictly within일 때만 host를 부여한다. boundary POI는 `POI(out)`이다. 복수 host는 observed area, stable source ID, `local_entity_id` 순으로 선택하며 CNT와 WIT는 exact inverse다.
- `INT`: B-B, B-R, R-R에 GEOS `intersects`를 적용해 boundary contact, crossing, partial overlap을 포함하고 양방향을 보존한다.
- `CON`: R-R만 허용하며 두 observed link가 공유하는 original `F_NODE/T_NODE` ID의 source node 위치가 closed scene footprint 안에 있을 때만 양방향으로 부여한다. clipped endpoint와 동일 좌표의 다른 node ID는 사용하지 않는다.
- `INT+CON`, `SN+INT`, `SN+INT+CON` 등 multi-relation은 mask에서 손실 없이 유지한다.
- 공통 relation dataset ID는 `pre_b94858c3ea31d9eb2376ee00`이다. 각 branch input manifest checksum은 branch manifest에 별도로 보존한다.

## Road Topology 감사

입력은 `/mnt/hdd002/dhnyu/fusedata/study_data/seoul_R.gpkg`이며 `study_data_inputs`가 file checksum을 직접 추적한다.

| 검사 | 결과 |
|---|---:|
| links / unique LINK_ID | 66,854 / 66,854 |
| empty F_NODE / T_NODE | 0 / 0 |
| nodes / unique NODE_ID | 48,748 / 48,748 |
| node invalid / empty | 0 / 0 |
| node CRS | EPSG:5186 |
| dangling F_NODE/T_NODE | 0 |
| duplicate 또는 ambiguous NODE_ID | 0 |
| I10 Road source F/T 불일치 | 0 |
| clipped-endpoint false CON | 0 |

원본 node layer가 존재하고 ID 및 위치 계약이 완전하므로 clipped endpoint 대체는 사용하지 않았다. source GPKG SHA-256과 artifact ID는 각 scientific manifest에 기록했다.

## Target과 산출물

`prototype_relation_shard`는 `pattern = map(prototype_observation_plan, prototype_vector_observation_shard)`, `controller_10`, branch 내부 `1 worker x 1 thread`다. 직접 dependency는 다음 네 개뿐이다.

1. `prototype_observation_plan -> prototype_relation_shard`
2. `prototype_vector_observation_shard -> prototype_relation_shard`
3. `study_data_inputs -> prototype_relation_shard`
4. `relation_contract_files -> prototype_relation_shard`

I11 raster dependency는 없다. 각 branch는 edge Parquet, node-index Parquet, 0-edge scene을 포함한 scene statistics Parquet, scientific manifest JSON, runtime QC JSON, structured JSONL log를 same-filesystem staging에서 생성한 뒤 atomic publish한다. 기존 immutable directory가 있으면 세 scientific Parquet의 checksum이 동일할 때만 재사용한다. edge Parquet에는 geometry가 없다.

## 선행 정렬과 전역 QC

- I10 15 branch manifest/QC: 모두 PASS.
- I09/I10/I12 branch set: 15개 exact match; scene set 320개 exact match.
- I12 node counts: Building 81,693, Road 7,898, POI 147,530, 총 237,121.
- `(scene_id, local_entity_id)` duplicate: 0.
- ordered pair: 2,756,444; duplicate edge key/edge ID: 0.
- self-edge, cross-scene, dangling endpoint, endpoint type mismatch: 모두 0.
- applicability, unknown mask bit, SN radius/top-k/tie-order 위반: 모두 0.
- CNT/WIT inverse, SN/INT/CON symmetry 위반: 모두 0.
- output checksum/size mismatch: 0.
- contained POI 108,255; outside POI 39,275; host area tie 23.
- POI(out)-POI(out) SN 561,342.
- scene edge count min/median/p95/max: 0 / 1,054 / 33,474.4 / 58,366.

## Relation 통계

아래 수는 ordered pair mask에서 해당 bit가 켜진 횟수다.

| relation | edge count |
|---|---:|
| SN | 2,539,932 |
| CNT | 108,255 |
| WIT | 108,255 |
| INT | 44,412 |
| CON | 25,892 |

- multi-relation ordered pair: 44,412.
- empty-edge scene: 59.
- SN radius candidates: 21,568,506; directed top-k retained selections: 2,041,483.
- SN distance min/median/p95/max: 0 / 11.35981 / 41.63851 / 99.99807 m.
- CON serialized shared-node evidence의 unique value: 4,026.

## 병렬처리 Pilot과 실행

pilot은 entity count 1, 14, 141, 1,916, 5,056인 5개 scene을 각각 두 번 실행한 warm-cache workload다.

| workers | wall s | peak worker RSS KiB | nodes/s | edges/s | write bytes | I/O wait ticks | errors |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 101.016 | 391,908 | 141.1 | 1,254.9 | 2,760,704 | 143 | 0 |
| 10 | 98.701 | 388,700 | 144.4 | 1,284.4 | 2,760,704 | 152 | 0 |

10 workers가 2.3% 빨랐고 RSS/GEOS contention 증가가 없어 실제 concurrency를 10으로 확정했다. pilot 누적 vector read는 5/10 workers에서 8.403/8.745 s, topology read 0.156/0.160 s, exact relation 281.759/282.779 s, Parquet write 0.350/0.359 s였다. page cache를 파괴적으로 초기화하지 않았으며 cold-cache 성능은 측정하지 않았다. OS process read counter는 warm cache 때문에 0이었다. 후보 생성과 relation별 predicate subphase는 별도 wall timer로 분리하지 않고 candidate count와 aggregate exact-relation 시간으로 기록했다.

최종 `tar_make(prototype_relation_shard)` wall time은 23분 4초였다. branch scientific wall 합계는 7,063.5초, branch min/median/max는 144.6/529.4/658.4초, maximum RSS는 729,028 KiB, write bytes 합계는 59,973,632 bytes였다. 두 tail branch는 crew가 첫 attempt 후 자동 retry했으나 최종 `tar_meta()` error/warning과 branch QC failure는 0이었다.

## Reference와 결정성

실제 scene 3개를 exhaustive sf/GEOS reference로 계산해 optimized 결과와 비교했다.

| scene | nodes | ordered pairs | FP | FN | mask/distance/evidence mismatch |
|---|---:|---:|---:|---:|---:|
| `scn_312d0408dbb0addca127f9d9` | 73 | 1,074 | 0 | 0 | 0 |
| `scn_30b22ad87dc370ddb2cae951` | 102 | 1,924 | 0 | 0 | 0 |
| `scn_16d190ee116931ae54df3f52` | 141 | 2,778 | 0 | 0 | 0 |

distance 최대 오차는 0 m였다. evidence 비교는 CNT/WIT host, shared original node ID, SN source/destination rank를 포함한다.

`pob_ea34022631583b86c74cd6cc`를 같은 입력으로 직접 재구축했다. 150.886초 후 기존 immutable output path를 재사용했고 edge/node/statistics Parquet 및 manifest/QC/log 6개 파일의 실행 전후 SHA-256이 모두 동일했다. 따라서 branch ID, relation dataset ID, row order, edge ID, mask, host, rank, Parquet bytes 및 scientific manifest content가 결정적이다.

## 수행한 검증

- 변경 R 및 validation script parse PASS, JSON schema parse PASS.
- relation config/schema 및 synthetic fixture test PASS.
- 전체 `Rscript tests/testthat.R` PASS.
- road topology source audit PASS.
- `tar_manifest()`, `tar_network()`, `tar_validate()` PASS.
- 5/10-worker pilot PASS, concurrency 10 채택.
- I12 `tar_make()` 15/15 PASS; I09/I10 skipped, I11 미선택.
- branch manifest/QC/checksum, endpoint equality, global applicability/inverse/symmetry/multi-mask audit PASS.
- representative exhaustive reference 및 direct rebuild determinism PASS.
- `Rscript tools/targets-network/render_targets_network.R` PASS.
- dependency HTML `/members/dhnyu/fuse/artifacts/targets-network/targets-network.html`이 current manifest의 I12와 네 dependency edge를 포함함을 확인했다.

## 실패와 수정 이력

1. 최초 감사에서 POI(out)-POI(out) SN과 boundary-contact INT가 당시 요청과 논문 사이에서 충돌해 BLOCKED로 중단했다. 이번 지시로 논문 정의를 명시적으로 채택했다.
2. global audit script의 nested JSON/data.table join 오류를 수정했다. artifact 계산에는 영향이 없었다.
3. 최초 I12 실행 후 branch별 vector manifest hash가 relation dataset ID를 15개로 분리함을 발견했다. branch manifest는 checksum을 계속 기록하되 dataset identity에서는 이를 제거하고, 공통 ID로 I12만 새 immutable 경로에 재실행했다.
4. crew tail branch retry가 있었으나 최종 branch error/warning/QC failure는 없었다.

## 실행하지 않은 검사와 남은 위험

- cold-cache benchmark와 page-cache reset은 실행하지 않았다.
- pilot의 SN candidate generation, exact distance, CNT/WIT/INT/CON을 각각 독립 wall timer로 분리하지 않았다.
- exhaustive reference는 전체 320 scene이 아니라 고정 representative 3 scene에 수행했다. 전체 artifact는 별도의 global structural/scientific audit를 전수 수행했다.
- I13은 아직 구현하지 않았다. I13에서 I10/I11/I12의 scene/local-ID dictionary equality, common dataset IDs, raster/relation manifest 집합과 59개 empty-edge scene 처리를 aggregate gate로 다시 확인해야 한다.
- 기존 I11 target은 현재 source graph 관점에서 queued/outdated로 표시되지만 사용자 제한에 따라 재실행하지 않았다. 기존 published I11 15 branch QC는 PASS이며 I12 dependency가 아니다.
- 이전 branch별-ID I12 immutable outputs는 삭제하거나 덮어쓰지 않았다. I13은 공통 ID `pre_b94858c3ea31d9eb2376ee00`만 소비해야 한다.

## 입력 프롬프트 요약

GitHub 최신 fuse와 dissertation을 확인하고 논문의 applicability table에 맞춰 POI(out)-POI(out) SN과 boundary-contact INT를 포함한 I12를 구현하며, original road-node CON, strict POI host, top-16 symmetric SN, uint8 multi-mask, 15 aligned dynamic shards, pilot/QC/reference/determinism/targets network를 완료한 경우에만 관련 파일을 commit/push하라는 요청이다.
