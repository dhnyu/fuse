# Prototype Spatial Acceptance Implementation Report

## 판정과 실행 기준

- 최종 판정: **READY**
- 실행 시각: 2026-08-21 16:43--17:54 KST
- Fuse 시작 commit: `495ed46b8091a6c3ce8e25b3c017455af727fcbc`
- 구현 commit: `6be6e62a88b3f93965e35287424123ed332e1076`
- branch/push: `feature/research-scene-index`, `origin/feature/research-scene-index` push PASS
- dissertation scientific source of truth: `73c7f5a65ae18960ac1990af035bca9076210f69`
- 선행 보고서: `20260821_1651_prototype_spatial_acceptance.md`, `20260821_1724_prototype_spatial_acceptance.md`

I13 `prototype_spatial_acceptance`만 구현했다. I14 serialization, C01 full production, model, augmentation과 GPU 작업은 구현하거나 실행하지 않았다.

## 사용자 승인 사항과 I11

현재 Git raster schema SHA-256 `823139f7fcb7e3ca33b1cfdf7ddb449acb035c95f42bf41c71ae65c65e9a3a3f`를 authoritative로 사용했다. 승인된 선행 실행에서 `raster_observation_contract_files`와 I11 15개 branch만 재실행했다.

| 항목 | 결과 |
|---|---:|
| 이전 I11 dataset | `pro_962bf22308ce6bf123030f23` |
| 신규 I11 dataset | `pro_725c3336eb825a1f81bb2c13` |
| branch QC | 15/15 PASS |
| scenes / object rows | 320 / 237,121 |
| Zarr member mismatch | 0 / 2,190 |
| branch wall 합 / pipeline elapsed | 262.751 s / 52.8 s |
| max branch RSS | 891,540 KiB |
| write bytes | 325,529,600 |

기존 I11 immutable dataset의 2,280개 파일 checksum은 모두 유지됐다. I09/I10/I12는 재실행되지 않았고, 최종 `tar_outdated()`는 빈 집합이다.

## Building A11 Exact Alias

승인된 alias는 exact raw `블록구조`만 official `code=12`, `label=블럭구조`로 연결한다. fuzzy matching, trimming, 일반 spelling normalization, OOV token과 별도 category는 없다. Raw canonical/I10 A11은 변경하지 않았다.

| 검증 | 결과 |
|---|---:|
| official archive SHA-256 | `2c315da08a0421b0b0e310b1a5b543a801afd0f0a314f55d35cfee5082bb8f94` |
| inner workbook SHA-256 | `8b31820b1d97220ee121a89a627c615102b6fa7af344439b5f27738a65496ec8` |
| canonical Building SHA-256 | `1bdd52a764a5cdb53a3e1d6c9ec6e5da15180dc5cecb28183b5d077a8aab5b4c` |
| official code 12 rows / label | 1 / `블럭구조` |
| official `블록구조` rows | 0 |
| canonical `A11=블록구조` rows | 15,829, 전부 `A10=12` |
| canonical `A10=12` unexpected label | 0 |
| I10 affected observations / source entities / scenes | 2,630 / 2,372 / 111 |
| I10 split observations | training 2,233 / validation 214 / evaluation 183 |
| stable source-ID join mismatch | 0 |

Alias contract는 `config/spatial_acceptance_aliases.yml`과 `prototype_categorical_aliases.parquet`에 기록했다. A11 vocabulary의 code 12 entry는 index 2이며 한 번만 존재한다. 별도 `블록구조`, `OOV`, `UNKNOWN`, `UNK` entry와 unresolved/invalid category는 모두 0이다.

## I13 Target과 Artifact

I13은 static target, `controller_05`, 내부 1 worker x 1 thread, GPU 0이다. Function tracking을 제외한 direct target dependency는 정확히 다음 6개다.

- `prototype_observation_plan`
- `prototype_vector_observation_shard`
- `prototype_raster_observation_shard`
- `prototype_relation_shard`
- `methodology_contract`
- `spatial_acceptance_contract_files`

Spatial dataset ID는 `psa_4e43932fc998fed94385addc`다. Upstream IDs는 vector `pvo_21e4a50d364901b86d4d2575`, raster `pro_725c3336eb825a1f81bb2c13`, relation `pre_b94858c3ea31d9eb2376ee00`이다.

Published output은 manifest, entity dictionary, spatial QC, categorical vocabulary, normalization statistics, missing mapping, 320-row scene statistics, categorical alias table, structured JSONL log의 9개 파일이다. Same-filesystem staging, schema/QC 선검사, atomic rename, immutable collision 검사 규칙을 사용했다.

## Completeness와 Cross-QC

- aligned branch: I09/I10/I11/I12 각각 15, set/grouping mismatch 0
- scenes: 320, training/validation/evaluation 256/32/32
- entity dictionary: 237,121 rows, Building 81,693 / Road 7,898 / POI 147,530
- entity rows by split: training 187,513 / validation 26,976 / evaluation 22,632
- duplicate `(scene_id, local_entity_id)`: 0
- I10/I11/I12 key/type mismatch, dangling/cross-scene reference: 0
- vector/raster/relation branch QC: 각 15/15 PASS; recorded output size/checksum mismatch 0
- raster scene/object-context mismatch: 0; `d_objras=26` contract 유지
- relation ordered pairs: 2,756,444
- relation counts: SN 2,539,932; CNT 108,255; WIT 108,255; INT 44,412; CON 25,892
- multi-relation ordered pairs: 44,412
- self/dangling/duplicate/unknown-bit/symmetry/inverse/radius/regression violation: 0
- empty-edge scenes: 59, 모두 dictionary modalities와 320-row scene statistics에 명시적으로 보존

## Vocabulary와 Missing Mapping

Vocabulary는 prototype observed subset이 아니라 official source codebook 전체다. Source category 수는 A9 509, A11 22, ROAD_RANK 7, ROAD_TYPE 5, POI L1--L6 4/17/358/999/1,398/148이다. Training observation counts는 Building attributes 62,059, Road attributes 6,342, POI 각 level 119,112이며 validation/evaluation은 index 또는 frequency를 변경하지 않는다.

`MISSING/MASK` indices는 A9 509/510, A11 22/23, ROAD_RANK 7/8, ROAD_TYPE 5/6, POI L1 4/5, L2 17/18, L3 358/359, L4 999/1000, L5 1398/1399, L6 148/149다. Raw observation의 `MASK`는 0이다.

Generic NULL/NA/empty는 `MISSING`이다. POI는 `VALUE`, `TERMINAL_DASH`, `NULL`, `EMPTY` states를 구분하며 official dash code는 L3 `A000`, L4 `D00/D01/D02`, L5 `F00/F01/F02/F03/F04/F06/F12/F13/F14/F15`, L6 `G00`이다. State/value contradiction과 codebook 밖 non-missing 값은 hard failure이며 실제 failure는 0이다.

## Training Numerical Statistics

모든 estimator는 training 256 scenes만 사용하며 float64 population SD(`N` denominator), no clipping이다. Vector/object DEM은 scene-entity row weighted, scene DEM은 valid pixel-instance weighted다. Missing은 estimator에서 제외하고 downstream standardized zero + indicator 1을 사용한다.

| Attribute | Transform | Valid / Missing | Mean | Raw SD | Applied scale | Constant |
|---|---|---:|---:|---:|---:|---|
| Building observed area | log1p | 62,059 / 0 | 4.3056289 | 1.0120654 | 1.0120654 | false |
| Building observed gross floor area | log1p | 47,534 / 14,525 | 5.3765451 | 1.2621011 | 1.2621011 | false |
| Road lanes | identity | 6,342 / 0 | 1.7537055 | 0.9983657 | 0.9983657 | false |
| Object DEM mean | identity | 187,513 / 0 | 34.7214865 | 20.5370077 | 20.5370077 | false |
| Object DEM SD | identity | 187,513 / 0 | 0.1784532 | 0.6347952 | 0.6347952 | false |
| Scene DEM pixels | identity | 73,984 / 0 | 96.4610433 | 122.7612749 | 122.7612749 | false |

Land-cover code/composition과 LC/DEM support ratio는 standardize하지 않는다. Validation/evaluation leakage, zero-valid required field와 negative/invalid numerical input은 0이다.

## 실행과 결정성

- 최종 I13 target wall: 76.902 s; max RSS 2,657,796 KiB; process read/write bytes 0 / 1,859,584
- `tar_make`: I13 + scoped contract 2개 completed, upstream 68 skipped
- R parse, Python `py_compile`, JSON/YAML parse: PASS
- alias/I13 fixtures와 전체 `Rscript tests/testthat.R`: PASS
- `tar_manifest()` 20 targets, `tar_network()` 510 edges, `tar_validate()`: PASS
- shuffled branch/input direct reconstruction: 기존 immutable directory 재사용 PASS
- manifest/QC를 포함한 8 scientific files: path와 SHA-256 byte identity PASS
- manifest output size/SHA mismatch: 0
- dependency renderer: `artifacts/targets-network/targets-network.html` 갱신 PASS; I13/scoped dependency 존재, I14/C01 없음

실패 및 수정 이력은 I11 trailing-LF freshness blocker, 미확정 vocabulary/normalization blocker, A11 official/raw spelling blocker, runtime RSS helper name 오류, attribute 비적용 entity가 training `MISSING` count에 포함되던 집계 오류다. 각각 승인된 재실행, machine-readable contract, exact alias/stable-ID join, repository helper 사용, entity-type scoped 집계로 수정했고 최종 전체 검증을 다시 실행했다.

## 미실행 검사와 남은 위험

Cold-cache 측정을 위해 system page cache를 초기화하지 않았다. Full 12,690-scene production, I14 serialization tensor, DataLoader/model 소비와 GPU 검증은 실행하지 않았다. I14에서 empty-edge scene의 빈 edge tensor, vocabulary/missing indicator 적용과 source-codebook identity 전달을 검증해야 한다. Upstream raw artifact와 scientific 방법은 변경하지 않았다.

다음 단계는 I14 `prototype_serialization_plan`이며 이번 작업에서는 구현하지 않았다.

## 입력 프롬프트 요약

사용자는 Building raw A11 `블록구조`를 official code 12/label `블럭구조`로 매핑하는 exact scientific alias를 승인했고, canonical A10/A11와 I10 stable source ID를 전수검증한 뒤 I13을 구현·실행·결정성 검증하고 READY일 때만 작업 파일을 commit/push하도록 요청했다.
