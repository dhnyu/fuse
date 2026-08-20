# Prototype Raster Observation Implementation

## 작업 목적과 범위

- 실행 시각: 2026-08-21 03:14--03:53 KST
- 구현 저장소 시작 HEAD: `3bab5ca5acfbc448bc18ff8a9b44086efdf4564a`
- 범위: I11 `prototype_raster_observation_shard`와 직접 필요한 contract, writer, fixture, verification만 구현했다.
- 제외: I10 재작성, I12 relation, I13 acceptance, serialization/model/full production.
- 입력: I09 15개 aligned spec, I10 `pvo_21e4a50d364901b86d4d2575`, `seoul_lc.tif`, `seoul_dem.tif`.

## 논문 및 입력 감사

논문의 object-level background encoder는 I10 observed geometry와 raster-cell overlap으로 LC class composition, DEM overlap-weighted mean/population SD, modality별 valid-support ratio를 정의한다. Scene raster 절과 architecture 표는 LC `100 x 100`, DEM `17 x 17`의 별도 branch를 고정한다. 구현 계약과 충돌은 없었다.

| 항목 | Land cover | DEM |
|---|---:|---:|
| CRS | EPSG:5186 | EPSG:5186 |
| grid | 7,571 x 6,224, 5 m | 1,263 x 1,038, 30 m |
| origin | (178789.3076, 567265.3832) | (178770, 567270) |
| dtype/nodata | Byte / 0 | Int16 / -32767 |
| 유효 범위 | class index 1--21; 22-class legend 완전 | -30--811 m |
| prototype coverage | 320 footprints 전부 포함 | 320 footprints 전부 포함 |

LC metadata의 `LC_VALUE_01`--`LC_VALUE_22`가 source code 110--720 legend와 일치했다. 실제 prototype scene은 두 raster 모두 full coverage였고 scene-level nodata cell은 0이었다.

## Raster observation 계약

### Scene level

- LC: 각 500 m footprint를 북->남 row, 서->동 column의 `100 x 100` local grid로 정확히 분할한다. 22개 categorical indicator를 면적 overlap으로 집계해 valid support로 정규화한 class composition `float32 (N,22,100,100)`과 `valid_support_ratio`, `valid_mask`를 저장한다. categorical interpolation, padding, silent zero-category는 없다.
- DEM: 동일 footprint의 독립 `17 x 17` local grid에 raw metre 값을 면적 overlap valid mean으로 집계한다. `float32 (N,17,17)`과 validity ratio/mask를 저장하며 normalization/imputation은 하지 않는다.
- 두 modality 모두 source grid를 임의 반올림하거나 서로에게 정렬하지 않는다.

### Object level

- support는 source geometry가 아니라 I10 observed geometry다.
- Building: raster cell과 clipped polygon의 정확한 교차 면적. Multipart와 hole을 그대로 반영한다.
- Road: line segment를 source grid boundary에서 분할한 정확한 교차 길이.
- POI: half-open cell convention(`x` left-closed/right-open, `y` top-closed/bottom-open)의 containing cell.
- LC: 22개 raw support와 valid-support 기준 composition, total/valid/nodata support와 ratio를 저장한다.
- DEM: raw metre overlap-weighted mean과 population SD, total/valid/nodata support와 ratio를 저장한다. full nodata이면 mean/SD는 null이고 validity가 원인을 표현한다.
- I10 `bbox`, provenance, checksum, geometry metadata는 explicit non-model role이며 object context에 포함하지 않는다.

## 저장 및 target 계약

`raster_observation_contract_files`는 config/schema/Python writer/requirements를 `format="file"`, `controller_05`로 추적한다. I11은
`pattern = map(prototype_observation_plan, prototype_vector_observation_shard)`, `iteration="list"`, `format="file"`, `controller_10`이며 branch 내부 `workers=1`, native threads=1, GPU=0이다.

각 aligned branch는 자체 staging에서 다음을 만든 뒤 QC/checksum 후 same-filesystem directory rename으로 publish한다.

- `scene_landcover.zarr`, `scene_dem.zarr`: Zarr v2, scene당 chunk, Blosc Zstd level 5 + bitshuffle, consolidated metadata.
- `scene_raster_index.parquet`: `scene_id`와 zero-based Zarr index, extent/grid/orientation.
- `object_raster_context.parquet`: geometry 없는 fixed 69-column schema, Zstd.
- `zarr_member_manifest.json`: 모든 member의 final path, relative path, size, SHA-256을 ordered array로 기록.
- `branch_manifest.json`, `branch_qc.json`, `branch_log.jsonl`.

Zarr 3.1.6/numcodecs 0.16.5/NumPy 2.4.6을 exact-pin한 writer environment가 format v2를 생성한다. Python Zarr/PyArrow, GDAL `gdalmdiminfo`, R `stars::read_mdim`/Arrow cross-read가 PASS했다.

## Performance pilot

고정된 low/median/high/tail 10-scene workload(10,785 entities), worker당 thread 1, page cache 비제어 상태로 실행했다. 물리 read가 0이어서 cold-cache 결과로 해석하지 않았다.

| concurrency | wall | max worker RSS | write | I/O wait ticks | errors |
|---:|---:|---:|---:|---:|---:|
| 5 | 7.980 s | 435.3 MiB | 11.55 MiB | 11 | 0 |
| 10 | 4.631 s | 433.2 MiB | 11.55 MiB | 10 | 0 |

10 workers가 더 빠르고 contention 증거가 없어 `controller_10`의 실제 concurrency 10을 유지했다.

## Prototype 실행 결과

- 실행 명령: `FUSE_CONTROLLER_10_WORKERS=10 Rscript scripts/run_targets.R prototype_raster_observation_shard`
- pipeline wall: 51.3 s; I11 branch time 합 261.3 s, median 22.1 s, p95 23.7 s, max 24.0 s.
- peak branch RSS: 932,772 KiB; process I/O 합 read 4 KiB, write 310.4 MiB. Read 수치는 warm page cache의 영향이다.
- artifact: `pro_962bf22308ce6bf123030f23`, 15 branches, 320 scenes.
- output root: `/mnt/hdd002/dhnyu/fusedata/scene_data/v1/index/idx_717d7ae7a88e370a79cf9bd4/prototype/pro_17040a91f3aee12b91c0bcd4/observations/pro_962bf22308ce6bf123030f23/raster/branches/`.
- scene arrays: LC `(N,22,100,100)`, DEM `(N,17,17)`, 모든 scene shape/dtype 동일.
- Zarr: 2,190 member, 6,486,623 bytes; 모든 member checksum PASS.
- object context: 237,121 rows = Building 81,693 + Road 7,898 + POI 147,530; I10 key와 누락/추가/중복 0.
- object partial nodata: LC B 5,935/R 687/P 0; DEM B 3,198/R 1,090/P 0. Full-nodata object는 모든 type 0.
- object DEM mean 범위: B 1--616 m, R 4--375 m, P 3--707 m.
- scene DEM range: -3.269896--706.083984 m; LC unknown category 0; scene-level LC/DEM nodata scene 0.

## Correctness와 결정성

- Synthetic fixture: aligned/off-grid LC, unknown class, constant/gradient/off-grid/partial/full-nodata DEM, polygon/hole/multipart/small polygon, line/multipart/grid boundary, point, weighted mean/SD를 통과했다.
- 독립 analytical overlap reference: representative 10 scenes(low, median, B p95, POI p95, max B, max POI, boundary-near, max LC diversity, max DEM relief, raster-edge)의 stored LC float32 array가 exact equality, DEM 최대 절대오차 0이었다.
- 독립 GEOS/terra cell reference: 객체 표본 21건의 LC fraction 최대오차 0, DEM mean 최대오차 `1.716e-12 m`, SD 최대오차 `1.463e-12 m`.
- 전체 branch manifest/QC, 2,190 Zarr member checksum, I10/I11 scene/entity key, schema/role invariant가 PASS했다.
- 동일 입력 direct rebuild: branch `pob_05bae59d2fae4fb29972a0a3`가 기존 content-addressed 경로를 재사용했고 representative file SHA-256가 모두 동일했다.

## 실패와 수정 이력

1. 초기 full-raster object extraction은 dense branch에서 느렸고 terra polygon coverage가 작은 support residual을 만들었다. Raster를 observed-geometry bbox window로 제한하고 Building은 GEOS cell intersection, Road는 analytical segment split으로 구현해 strict support tolerance를 만족했다.
2. 첫 full run은 zero-entity scene을 context scene-set 누락으로 오인했다. Scene index는 320개 완전성을 요구하고 context는 I10 key subset과 exact equality를 요구하도록 QC를 수정했다.
3. 첫 direct rebuild가 `zarr_member_manifest.json` checksum 불일치를 검출했다. `Map()`의 staging-path list names가 JSON object key로 직렬화된 것이 원인이었다. names를 제거한 ordered array contract와 regression test를 추가하고 새 content ID로 I11만 재실행했다.
4. production 실행에서 한 branch가 crew retry 1회를 거쳐 PASS했다. branch sidecar에는 scientific warning이 없고 최종 checksum/QC는 PASS했다. Full production 전에 transient worker 종료 원인을 장시간 pilot에서 다시 관찰한다.
5. 첫 full test suite는 research manifest의 기존 14-target 기대값 때문에 실패했다. I11의 두 target을 포함한 16-target 순서를 fixture에 반영하고 재실행했다.
6. Zarr library minor update가 같은 artifact ID 아래 byte contract를 바꾸지 않도록 NumPy/numcodecs/Zarr를 설치 환경의 exact version으로 pin했다. Requirements hash 변경으로 I11만 새 content ID에 재실행했으며 1,920개 data chunk는 pin 전 artifact와 동일했다.

## 검증 및 미실행 검사

수행: 변경 R parse, Python syntax, raster contract/schema tests, synthetic fixtures, R/Python/GDAL cross-reader, `tar_manifest`, `tar_network`, `tar_validate`, 5/10 pilot, I11 `tar_make`, 전체 branch/key/checksum audit, independent reference, direct rebuild determinism, dependency HTML render.

미실행: destructive cold-cache benchmark, I12/I13, training normalization/imputation, raster augmentation, serialization/model, 12,690-scene production. 요청 범위상 실행하지 않았다.

## 남은 위험과 다음 단계

- I12 relation은 I09/I10 aligned branch와 동일 `local_entity_id`를 사용해야 하며 I11 `bbox`/provenance를 feature로 소비하면 안 된다.
- I13에서 vector/raster/relation 전체 scene/local-ID equality와 branch manifest를 다시 aggregate gate로 검증해야 한다.
- Full production 전 10-worker 장시간 raster I/O/RSS pilot과 crew transient retry 원인 관찰이 필요하다.
- Training 단계에서 LC composition/valid ratio 및 DEM mean/SD/valid ratio의 normalization/imputation 계약을 별도로 확정한다.

## 최종 판정

`READY`. I11 prototype raster observation은 논문 계약, 저장 계약, branch QC, cross-reader, 독립 reference 및 결정성 검증을 통과했다. 다음 승인 단위는 I12 `prototype_relation_shard`다.
