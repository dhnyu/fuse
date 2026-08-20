# Prototype Membership Implementation Report

## 작업 목적과 범위

Targets blueprint의 두 번째 승인 단위 I06--I08을 구현하고 320개 prototype scene에서
Building, Road, POI exact membership을 실행·승인했다. Geometry clipping, observed
attribute 재계산, raster, relation, serialization, model 및 12,690-scene production은
구현하거나 실행하지 않았다.

- 실행 시각: 2026-08-21 01:32--02:01 KST
- 구현 시작 commit: `7ebd5c2660949476bf9cb6f1147bdfb0dd03cf46`
- 논문 commit: `73c7f5a65ae18960ac1990af035bca9076210f69`
- 입력: `pro_17040a91f3aee12b91c0bcd4`, `inp_2130597372e7425fd844127a`
- 최종 membership dataset: `pmd_11e42af544521399c8ff8880`
- 최종 acceptance: `pma_30d60ec2e39094d4eb7fb835`

## 선행 감사

Prototype은 training 256, validation 32, evaluation 32로 정확히 320개였고
`scene_id`/`scene_footprint_id`가 유일했다. 모든 footprint는 EPSG:5186의 valid
500 m square였다. Source layer audit 결과는 다음과 같으며 ID NULL/empty/duplicate와
invalid/empty geometry는 모두 0이었다.

| type | layer | source ID | source rows |
|---|---|---|---:|
| Building | `buildings` | `building_feature_id` | 723,818 |
| Road | `links` | `LINK_ID` | 66,854 |
| POI | `points` | `NF_ID` | 1,604,622 |

## Membership Predicate 계약

- Building: scene와 entity interior가 DE-9IM `T********`을 만족해 retained clip의
  면적이 양수인 경우만 포함한다. Point/line boundary-only contact는 제외한다.
- Road: 동일한 interior/interior predicate로 retained clip 길이가 양수인 경우만
  포함한다. Endpoint 또는 boundary-only line contact는 제외한다.
- POI: closed scene footprint와 `intersects`이면 포함하며 boundary point도 포함한다.
- Numerical buffer/epsilon은 사용하지 않는다. Multipart는 source entity 하나로
  유지하며 여러 scene에 반복 소속될 수 있다.
- Invalid, empty, geometry collection과 duplicate source ID는 repair/drop하지 않고
  branch를 실패시킨다. Current source에는 해당 사례가 없다.
- Unique key는 `(scene_id, entity_type, source_entity_id)`이며 geometry는 membership
  Parquet에 저장하지 않는다.

## Target과 Dependency

| target | dependency | format/iteration | controller | 내부 병렬도 | output |
|---|---|---|---|---:|---|
| `membership_contract_files` | 없음 | `file` | `controller_05` | 1x1 | config/schema paths |
| I06 `prototype_membership_plan` | prototype, inventory, config | `rds/list` | `controller_05` | 1x1 | atomic JSON specs |
| I07 `prototype_membership_shard` | `map(I06)`, study files, config | `file/list` | `controller_20` | 1x1 | B/R/P Parquet, manifest/QC/log |
| I08 `prototype_membership_acceptance` | I06, all I07, prototype, inventory | `file` | `controller_05` | 1x1 | aggregate manifest/plan/index/stats/cost/QC |

`targets 1.12.0`은 정적 `format="file"` stem을 직접 `map()`하지 못하므로 I06은
JSON을 외부 publish한 뒤 작은 spec list를 targets store에 반환한다. I07 branch
artifact는 `format="file"`로 추적된다. `seoul_data_preprocess`는 graph에 없다.

## Shard와 병렬처리

Proxy cost 4,000 이상인 dense scene 4개는 singleton, 나머지 316개는 LPT로
64/64/64/64/60 scene의 5개 shard에 배치했다. 일반 shard estimated cost는
43,664--43,665이고 actual membership rows는 43,660--43,664였다. 전체 9개 branch의
actual max/median row ratio는 1.000092, proxy/actual Spearman correlation은 0.961442다.

고정 low/median/high/tail 4-scene workload를 5회 반복한 20 tasks의 concurrency pilot:

| workers | wall seconds | max worker RSS | read bytes | iowait ticks | errors |
|---:|---:|---:|---:|---:|---:|
| 5 | 0.607 | 197,900 KiB | 0 | 0 | 0 |
| 10 | 0.412 | 198,008 KiB | 0 | 0 | 0 |
| 20 | 0.315 | 198,040 KiB | 0 | 0 | 0 |

Page cache 때문에 physical read throughput은 측정되지 않았다. 20 workers가 가장
빨랐고 RSS/iowait 악화가 없어 production run은 `controller_20` 최대 20 branch,
branch 내부 worker/thread 1을 사용했다. Runtime concurrency는 scientific ID에서
제외했다. 전체 final graph wall time은 33.8초였다. 일반 branch wall time은
8.13--8.28초, singleton은 0.45--0.49초였고 branch max RSS는 최대 523,768 KiB였다.

## Exact Membership 통계

| type | total rows | scene min | median | p95 | max | zero-entity scenes |
|---|---:|---:|---:|---:|---:|---:|
| Building | 81,693 | 0 | 25.5 | 1,206 | 1,781 | 85 |
| Road | 7,898 | 0 | 14 | 84 | 170 | 94 |
| POI | 147,530 | 0 | 23.5 | 1,967 | 4,784 | 54 |

총 membership row는 237,121개다. Zero count는 scene 누락이 아니라
`membership_statistics_by_scene.parquet`의 명시적 0으로 저장된다.

## QC와 결정성

- 9/9 branch manifest/QC `PASS`, 320 scenes plan scope exactly once: `PASS`
- 27 membership Parquet schema 동일, checksum 일치, duplicate key 0: `PASS`
- 모든 `scene_id`가 prototype에 존재하고 source ID가 B/R/P source layer에 존재: `PASS`
- Split completeness 256/32/32와 branch/aggregate counts: `PASS`
- Fixed 12-scene independent per-scene brute-force comparison: false positive 0,
  false negative 0
- 동일 입력으로 plan rebuild: branch IDs 동일
- 9개 branch direct rebuild: staged B/R/P Parquet SHA-256가 기존 artifact와 모두 동일
- Existing content-address artifact는 overwrite하지 않고 비교 후 재사용
- R source 38개 parse, 전체 `testthat`, `tar_manifest()`, `tar_network()`,
  `tar_validate()`와 R/PyArrow artifact cross-check: `PASS`
- Dependency HTML: `/members/dhnyu/fuse/artifacts/targets-network/targets-network.html`
  (11 nodes, 26 edges, maintenance node 없음)
- 최종 동일-input `tar_make()`는 19개 stem/branch metadata를 모두 skip했고
  `tar_outdated()`는 0이었다.

## 실패와 수정 이력

1. Plan bbox matrix에 column names가 없어 실패: explicit bbox names를 설정했다.
2. Singleton `scene_ids`가 JSON scalar로 unbox됨: JSON array로 고정했다.
3. 초기 LPT bin 수가 scene cap을 고려하지 않아 low-cost shard가 생김:
   `ceiling(regular/max_scenes)` 하한을 추가했다.
4. `format="file"` static plan stem의 direct `map()`이 targets 제약으로 실패:
   atomic JSON + `rds/list` stem 계약으로 수정했다.
5. Acceptance branch ID vector와 determinism checksum vector의 path names 때문에
   content는 같지만 `identical()`이 실패: 비교 전 names를 제거했다.

성공한 branch artifact를 삭제하거나 덮어쓰지 않았다. 구현 반복에서 생성된 이전
content-address version도 사용자 데이터 삭제 금지 원칙에 따라 보존했다.

## 미실행 검사와 남은 위험

- Cold-cache disk benchmark와 block-device별 throughput/queue depth는 실행하지 않았다.
  Pilot의 read bytes 0은 page cache 영향이며 production cold-I/O 근거가 아니다.
- Brute-force는 계약에 따른 고정 12-scene 표본이며 320개 전체를 별도 full-scan으로
  중복 계산하지 않았다. Aggregate 자체는 320개 전부 exact predicate다.
- Membership은 geometry 없는 Arrow Parquet이므로 기존 sfarrow 경고와 무관하다.
  I09--I10 observed clipped geometry를 쓰기 전에 GeoParquet writer compatibility를
  결정해야 한다.
- Full 12,690-scene shard sizing은 이번 prototype cost model을 검토한 뒤 별도 승인한다.

## 산출물과 최종 판정

Acceptance root:
`/mnt/hdd002/dhnyu/fusedata/scene_data/v1/index/idx_717d7ae7a88e370a79cf9bd4/prototype/pro_17040a91f3aee12b91c0bcd4/membership/pmd_11e42af544521399c8ff8880/acceptance/pma_30d60ec2e39094d4eb7fb835/`

`READY`. I06--I08은 실제 prototype에서 schema, partial recovery, source reference,
brute-force correctness와 byte determinism gate를 통과했다. 다음 승인 단위는 I09
`prototype_observation_plan`과 I10 `prototype_vector_observation_shard`이며, 구현 전에
GeoParquet writer를 확정한다.
