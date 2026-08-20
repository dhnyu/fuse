# Research Scene Index Implementation Report

## 작업 목적과 범위

최종 targets blueprint의 첫 승인 단위인 `study_data_inputs`,
`methodology_contract`, `spatial_scene_index`, `prototype_scene_selection`을 구현하고
실제 서울 study data에서 실행·검증했다. Membership, clipping, raster chip, relation,
serialization, model/training/evaluation은 구현하거나 실행하지 않았다.

- 실행 시각: 2026-08-21 01:14--01:24 KST
- 구현 시작 commit: `88c3f19a259a2c095df23f9c1fd04b62b80af888`
- 논문 commit: `73c7f5a65ae18960ac1990af035bca9076210f69`
- 입력 프롬프트 요약: maintenance target과 분리된 research graph에서 네 초기 target,
  지원 함수/config/schema/test를 구현하고 실제 실행, QC, network 갱신, commit/push까지 수행.

## 구현 Target과 Dependency

| target | 구분 | 직접 dependency | format | controller | 내부 병렬도 | GPU |
|---|---|---|---|---|---:|---:|
| `research_config_files` | 보조 | 없음 | `file` | `controller_05` | 1x1 | 0 |
| `research_implementation_files` | 보조 | 없음 | `file` | `controller_05` | 1x1 | 0 |
| `study_data_inputs` | 핵심 | `research_config_files` | `file` | `controller_05` | 1x1 | 0 |
| `study_data_inventory` | 보조 | config, inputs | `file` | `controller_05` | 1x1 | 0 |
| `methodology_contract` | 핵심 | config, implementation, inputs, inventory | `file` | `controller_05` | 1x1 | 0 |
| `spatial_scene_index` | 핵심 | config, inputs, methodology | `file` | `controller_05` | 1x1 | 0 |
| `prototype_scene_selection` | 핵심 | config, inputs, methodology, scene index | `file` | `controller_05` | 1x1 | 0 |

`seoul_data_preprocess`는 root `_targets.R`에 없으며 `_targets_maintenance.R`과
`fuse-maintenance` store에만 존재한다. Research store는 `fuse-research`다.

## 주요 산출물

- Input inventory: `/mnt/hdd002/dhnyu/fusedata/scene_data/v1/input_contracts/inp_2130597372e7425fd844127a/study_data_inventory.json`
- Methodology contract: `/mnt/hdd002/dhnyu/fusedata/scene_data/v1/contracts/mth_d3b51aa3399d56734be03be7/methodology_contract.json`
- Record-only provenance: 같은 contract directory의 `methodology_provenance.json`
- Scene index root: `/mnt/hdd002/dhnyu/fusedata/scene_data/v1/index/idx_717d7ae7a88e370a79cf9bd4/`
- Prototype root: scene index root 아래 `prototype/pro_17040a91f3aee12b91c0bcd4/`

Content-addressed directory별로 staging 작성, round-trip/QC, atomic directory rename을
수행했다. 기존 동일 ID bundle은 덮어쓰지 않고 determinism comparison 후 재사용한다.

## 실행 명령과 시간

```bash
Rscript tests/testthat.R
Rscript -e 'targets::tar_manifest(); targets::tar_network(); targets::tar_validate()'
Rscript scripts/run_targets.R prototype_scene_selection
Rscript tools/targets-network/render_targets_network.R
```

커밋된 최종 설정을 사용한 production-size 초기 graph 실행은 32.4초였다. Target
metadata 기준 `study_data_inventory` 2.5초, `methodology_contract` 1.7초,
`spatial_scene_index` 4.7초, `prototype_scene_selection` 18.1초였다. 동일 seed 독립
재계산은 scene index 4.88초, prototype 17.04초였고 기존 artifact와 일치했다.
모든 계산은 CPU-only, target 내부 worker 1, thread 1이었다. Peak RSS와 disk queue
depth는 이번 target에 계측 hook이 없어 기록하지 못했다.

## QC 결과

| 검사 | 결과 |
|---|---|
| 12 input files 존재/비어 있지 않음/manifest path·size·SHA-256 | `PASS` |
| B/R/P/boundary/buffer layer와 geometry type, vector/raster CRS | `PASS` |
| boundary valid, exact 400 m buffer, raster buffer coverage | `PASS` |
| JSON Schema 2020-12 methodology contract | `PASS` |
| Official-grid native phase, EPSG:5179 250 m derived alignment | `PASS` |
| Scene EPSG:5186, valid 500 m square, center within Seoul | `PASS` |
| Footprints covered by 400 m buffer | `PASS` |
| Scene index count | `12,690` (`9,690/1,000/2,000`) |
| Minimum off-lattice distance | `50.028365753819 m` (`>=50 m`) |
| Retrieval query/candidate contract | `10`, query별 `1,999` |
| `scene_id`/`scene_footprint_id` uniqueness | `PASS` |
| Prototype count | `320` (`256/32/32`) |
| Prototype density/boundary/composition/tail coverage | `PASS` |
| Same-seed scene/query/proxy selection recomputation | `PASS` |
| targets network HTML 7 vertices/14 edges, maintenance node 없음 | `PASS` |

Prototype proxy는 exact membership가 아니다. Building/Road geometry와 POI/Road-node
point를 각 한 번 bulk read한 뒤 GEOS spatial index로 scene별 intersection count를
계산했다. Selection에는 low/middle/high/tail, boundary-near/interior 및 dominant
Building/Road/POI/empty 구성이 포함된다.

## 실패와 수정 이력

1. `study_data_inventory`: buffer layer를 `buffer400`으로 가정해 open 실패.
   `research_paths.yml`에 실제 layer contract를 추가해 해결했다.
2. `study_data_inventory`: `sf::st_read(n_max=1)`이 일부 datasource에서 geometry 없는
   schema path를 반환. `SELECT * ... LIMIT 1` read로 교체했다.
3. `methodology_contract`: `check-jsonschema` executable 부재. 설치된 Python
   `jsonschema 4.26.0` fallback과 JSON Schema 자체 validation을 추가했다.
4. `spatial_scene_index`: `data.table` 외부 column vector에 `..columns`가 빠짐. 수정 후
   전체 index와 prototype이 통과했다.

## 경고, 미실행 검사와 남은 위험

- `sfarrow 0.4.1`은 GeoParquet metadata 구현이 초기 specification을 추적한다는
  경고를 출력한다. R round-trip과 Python GeoPandas 1.1.3/PyArrow 22.0.0
  cross-reader 검증은 모두 통과했다. Membership 구현 전 writer 교체 필요 여부를
  재검토한다.
- Peak RSS, disk I/O throughput과 full membership cost는 아직 benchmark하지 않았다.
- District code는 현 단계 source contract에 없어 `district_code=NA`; downstream
  district-aware 분석 전에 별도 data contract가 필요하다.
- 구현 반복 중 생성된 이전 content-addressed contract/index version은 사용자 데이터
  삭제 금지 원칙에 따라 보존했다. Targets store는 위에 기록한 최종 ID만 참조한다.
  실패 실행의 `.stage-*` 임시 directory는 최종 검증 전에 정리했다.
- 이번 범위 밖인 scene membership 이후 target은 실행하지 않았다.

## 최종 판정과 다음 단계

`READY`. 네 초기 scientific target과 보조 file contracts는 실제 데이터에서 성공했고
QC와 동일-seed 결정성 검사를 통과했다. 다음 구현 대상은 blueprint I06
`prototype_membership_plan`이며, 그 전에 GeoParquet writer compatibility와 prototype
cost statistics를 shard plan 입력으로 고정한다.
