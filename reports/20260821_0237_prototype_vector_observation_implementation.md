# Prototype Vector Observation Implementation Report

## 목적과 범위

- 실행 시각: 2026-08-21 02:08--02:38 KST
- 구현 시작 commit: `5cf0a32e8c7346c194ac1234e6ea7abc819c3534`
- 논문 commit: `73c7f5a65ae18960ac1990af035bca9076210f69`
- 범위: I09 `prototype_observation_plan`, I10 `prototype_vector_observation_shard`
- 제외: raster, relation, entity dictionary, serialization, model, full production

I08 `pmd_11e42af544521399c8ff8880` / `pma_30d60ec2e39094d4eb7fb835`를
read-only로 재검증했다. 9 branch, 27 membership Parquet checksum, 320 scenes,
256/32/32 split, B/R/P `81,693 / 7,898 / 147,530` rows와 source ID 연결이 모두
PASS였다.

## GeoParquet writer 결정

설치 버전은 R Arrow 22.0.0, sfarrow 0.4.1, sf 1.1.0, GDAL 3.12.2,
GEOS 3.14.1, Python PyArrow 22.0.0, GeoPandas 1.1.3, Shapely 2.1.2다.
GDAL build에는 Parquet/Arrow vector write driver가 없고 DuckDB는 설치되어 있지 않다.
sfarrow는 구형 metadata 경고가 있고 GeoParquet 1.1 PROJJSON CRS를 읽을 때 CRS를
복구하지 못했다.

따라서 `python/write_geoparquet.py`의 GeoPandas/PyArrow writer를 확정했다.
GeoParquet 1.1.0, WKB, EPSG:5186 PROJJSON, primary column
`observed_geometry`, covering bbox, zstd, row group 65,536 계약이다. Python
GeoPandas/PyArrow round-trip과 metadata를 검사하며, R은 Arrow WKB와 GeoParquet
metadata를 검증한 뒤 `st_as_sfc(..., crs=5186)`로 표준 파일을 읽는다. Fixture의
동일 입력 2회 output SHA-256이 동일했다. GDAL/DuckDB cross-read는 환경 capability
부재로 실행하지 않았다.

## Observation 계약

- Building: exact 500 m footprint clip, polygonal positive area만 유지한다. `A9`,
  `A11`, raw `A14`, `A14_source_state`를 보존한다. `observed_area_m2`를 clip에서
  재계산하고 `observed_gross_floor_area_m2 = A14 * observed_area_m2 / source_area_m2`로
  A14를 배분한다. `A14 <= 0` 또는 NA는 unavailable이다.
- Road: lineal positive length만 유지하고 `LANES`, `ROAD_RANK`, `ROAD_TYPE`,
  `F_NODE`, `T_NODE`를 보존한다. source/observed length, observed endpoints,
  endpoint count와 source-node endpoint retained flag를 계산한다. topology/CON은
  생성하지 않는다.
- POI: closed scene boundary point를 포함하며 좌표를 이동하거나 clip하지 않는다.
  `POI_CL_DC`와 L1--L6 code/label/state를 보존한다. vocabulary/missing mapping은
  수행하지 않는다.
- 공통: source/observed WKB SHA-256, scene/observed bbox center, relative center,
  coordinate/component/hole count를 기록한다. sinusoidal encoding과 augmentation은
  수행하지 않는다.
- `local_entity_id`: scene별 B, R, P type rank와 UTF-8 source ID 순으로 정렬한
  0-based int32다. 입력/branch/worker 순서에 독립적이다.
- tolerance: coordinate `1e-7 m`, polygon QC `1e-4 m2`, line QC `1e-7 m`, relative
  measure `1e-10`. 이는 IEEE-754/GEOS boundary roundoff QC 전용이며 geometry
  buffer나 snap을 사용하지 않는다.

## Target과 shard

| target | dependency | format/pattern | controller | 내부 병렬도 | output |
|---|---|---|---|---|---|
| `prototype_observation_plan` | I05, I08, observation contract | RDS list | `controller_05` | 1x1 | atomic JSON specs |
| `prototype_vector_observation_shard` | I09, I08, I01, contract | file / `map(I09)` | `controller_10` | 1x1 | B/R/P GeoParquet + manifest/QC/log |

I09는 source coordinate/component/WKB byte와 exact membership을 사용한다. 최종
plan은 15 branches, dense singleton 3개, branch당 최대 40 scenes와 20,000
entities다. Regular branch cost max/median은 1.000023으로 균형을 이뤘다. I11/I12가
같은 immutable scene grouping을 사용하도록 spec에 `shared_grouping`을 기록했다.

고정 5-scene x 2 repetition pilot 결과는 다음과 같다. Page cache 상태라 physical
read bytes는 0이어서 cold-cache throughput은 확정하지 않았다.

| concurrency | tasks | wall seconds | max worker RSS KiB | write bytes | iowait ticks | errors |
|---:|---:|---:|---:|---:|---:|---:|
| 5 | 10 | 7.913 | 419,952 | 4,759,552 | 12 | 0 |
| 10 | 10 | 4.255 | 423,364 | 4,759,552 | 6 | 0 |

따라서 controller pool 10을 유지했다.

## 산출물과 QC

Observation dataset은 `pvo_21e4a50d364901b86d4d2575`이며 다음 root에 있다.

`/mnt/hdd002/dhnyu/fusedata/scene_data/v1/index/idx_717d7ae7a88e370a79cf9bd4/prototype/pro_17040a91f3aee12b91c0bcd4/observations/pvo_21e4a50d364901b86d4d2575/`

| type | rows | coordinates | fully contained | clipped | multipart | holes | Parquet bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| Building | 81,693 | 619,346 | 74,077 | 7,616 | 106 | 13 | 23,045,459 |
| Road | 7,898 | 27,664 | 4,993 | 2,905 | 27 | 0 | 2,323,058 |
| POI | 147,530 | 147,530 | 147,530 | 0 | 0 | 0 | 15,735,665 |

모든 15 branch manifest/QC가 PASS이고 45 GeoParquet checksum, GeoParquet 1.1
metadata, EPSG:5186, schema, membership key, scene-local ID uniqueness가 일치한다.
Branch wall-time 합은 187.112초, 전체 병렬 pipeline wall은 I09 재계획 포함 약
81초, 최대 branch RSS는 605,608 KiB, write bytes 합은 75,460,608이다. `/proc`
physical read bytes는 page cache 때문에 0이었다.

Low/median, B/P p95+, 최대 B/P, boundary-near, multipart/hole을 포함한 8 fixed
scenes의 14,091 rows를 source entity별 독립 `st_intersection()`으로 비교했다.
Membership key, geometry equality(`1e-7 m`), area(`1e-4 m2`), length(`1e-7 m`)의
failure는 모두 0이다. 15 branch direct rebuild는 45 GeoParquet의 byte SHA-256을
모두 재현했으며 27.971초가 걸렸다.

## 실패와 수정 이력

1. Zero-entity scene을 aggregate membership row가 없다는 이유로 scope 밖으로
   오판한 prerequisite를 I08 `scene_count=320`과 membership subset 검증으로 수정했다.
2. 최초 cost threshold가 41 shards를 만들어 실제 분포 기준 18,000으로 조정했고
   15 shards/3 singleton으로 확정했다.
3. GEOS overlay를 다시 overlay하는 containment QC가 수치 sliver를 만들었다. Convex
   axis-aligned scene의 bbox coordinate invariant로 교체했다.
4. `sf::st_normalize()`를 canonical WKB 정렬로 잘못 해석한 오류를 pilot에서
   발견했다. 이 함수가 좌표를 unit range로 바꾸므로 완전히 제거했다. 이 오류가
   있던 실행은 branch QC 전에 실패하여 publish된 I10 artifact가 없다. 최종
   artifact는 raw EPSG:5186 little-endian WKB를 사용한다.

## 미실행 검사와 다음 위험

- 시스템 전체 cache를 변경하는 cold-cache benchmark는 실행하지 않았다.
- GDAL Parquet driver와 DuckDB spatial이 없어 해당 cross-read는 실행하지 않았다.
- I11은 GeoParquet physical `bbox` struct column을 attribute 집계에서 제외하고 표준
  WKB reader를 재사용해야 한다.
- I12는 `local_entity_id`와 source road nodes를 사용하되 clipped endpoints를 CON
  topology node로 오인하지 않아야 한다.
- I13 전까지 global vector/raster/relation cross-artifact acceptance는 의도적으로
  없다. 이번 단계는 branch-local PASS만 보장한다.

## 판정

`READY`. I09/I10은 논문 clipping/A14 계약, exact membership correspondence,
GeoParquet 1.1 interoperability, branch-local recovery와 byte determinism을
충족했다. 다음 승인 단위는 같은 I09 plan을 map하는 I11 raster observation과 I12
relation이다.
