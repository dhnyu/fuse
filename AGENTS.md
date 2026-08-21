# 논문 및 방법론

구현 전에 최신 논문 방법론을 확인한다.

- 저장소: `~/dhnyu-masters-dissertation/template`
- PDF: `main.pdf`
- 본문: `sections/`
- 참고문헌: `bibliography/`
- 표와 그림: `materials/`

논문과 구현 명세가 충돌하면 임의로 결정하지 말고 차이를 보고한다.

# 데이터

## 행정구역

경로: `/mnt/hdd002/dhnyu/fusedata/koreaadmin`

- 시도: `bnd_sido_00_2025_2Q.shp`
- 시군구: `bnd_sigungu_00_2025_2Q.shp`
- 읍면동: `bnd_dong_00_2025_2Q.shp`
- 공식 500m 격자: `빈격자(500m).shp`

공식 격자의 중심 간격은 500m이다. 논문의 250m stride 학습 lattice는 원본 격자의 정렬을 유지하면서 derived target에서 생성한다.

## 원본 데이터

경로: `/mnt/hdd002/dhnyu/fusedata/original_data`

- 건물: `Building_vworld_20260509.zip`
- 도로: `ITS_nodelink_20260612.zip`
- POI: `POI_ngii_20260525.zip`
- 토지피복: `egis_2025.zip`
- DEM: `SRTM_2014.zip`

## Canonical 핵심 데이터

경로: `/mnt/hdd002/dhnyu/fusedata/main_data`

생성 목표:

- 건물: `korea_B.gpkg`
- 도로: `korea_R.gpkg`
- POI: `korea_P.gpkg`
- 토지피복: `korea_lc.tif`
- DEM: `korea_dem.tif`

Canonical 데이터는 원본의 값, 식별자, 좌표계 및 provenance를 보존한다. Clipping, 좌표 변환, 모델용 결측 처리, category filtering, fuzzy deduplication, vocabulary 구성 및 표준화는 별도의 derived target에서 수행한다.

기존 outdated 산출물은 회귀 검증에만 사용하며 새로운 canonical 데이터의 입력으로 사용하지 않는다. 최종 파일은 임시 경로에서 생성하고 acceptance test를 통과한 뒤 publish한다.

상세 데이터 계약은 다음 파일을 따른다.

- `config/data_contracts/building.yml`
- `config/data_contracts/road.yml`
- `config/data_contracts/poi.yml`
- `config/data_contracts/landcover.yml`
- `config/data_contracts/dem.yml`

계약이 승인되기 전에는 전국 production을 실행하지 않는다. 승인 전에는 읽기 전용 조사, inventory 작성 및 지정된 pilot만 수행한다.

## 기존 산출물

다음 파일은 outdated이며 회귀 검증에만 사용한다.

- `korea_buildings_vworld.gpkg`
- `korea_buildings_vworld_attributes.parquet`
- `korea_itslink.gpkg`
- `korea_itsnode.gpkg`
- `korea_poi_ngii_clean.gpkg`
- `korea_poi_ngii_clean.parquet`
- `korea_landcover_egis2025.tif`
- `korea_landcover_egis2025_legend.parquet`
- `korea_srtm2014.tif`

# 구현 원칙

- 공간 전처리는 R을 우선 사용한다.
- 주요 패키지는 `data.table`, `arrow`, `sf`, `terra`, `sfnetworks`, `chopin`, `targets`이다.
- 딥러닝은 Python과 PyTorch를 사용한다.
- 파이프라인은 `targets`로 재현 가능하게 관리한다.
- 논문의 방법론 단위로 모듈을 분리한다.
- 각 모듈에 대응하는 논문 절과 수식을 주석으로 기록한다.
- 대규모 production 전에 소규모 pilot과 acceptance test를 수행한다.
- 병렬 worker 수는 고정하지 말고 I/O 및 메모리 pilot 결과에 따라 정한다.
- 사용자 소유 데이터와 기존 산출물을 덮어쓰거나 삭제하지 않는다.

# targets 구현 및 검증 절차

새 target을 만들거나 기존 target의 command, dependency, pattern, resources, format 또는 출력 계약을 변경할 때 다음 절차를 따른다.

## 구현 전

- `blueprint/targets_implementation_blueprint.md`와 최신 논문 방법론을 확인한다.
- target의 입력, 출력, dependency, 파일 형식, QC 조건과 병렬처리 자원을 먼저 정의한다.
- 논문이나 blueprint와 구현이 충돌하면 임의로 방법론을 변경하지 말고 차이를 보고한다.
- `seoul_data_preprocess`는 maintenance pipeline으로 취급하며 연구 pipeline의 target과 dependency로 연결하지 않는다.
- maintenance pipeline과 research pipeline은 서로 다른 target script, 실행 진입점 및 targets store를 사용한다.

## 코드 배치

- target 정의는 `targets/`에 둔다.
- 재사용 가능한 계산 함수는 `R/` 또는 `python/`에 둔다.
- target command에는 가능한 한 orchestration만 남기고 긴 계산 로직을 직접 넣지 않는다.
- 각 파일 target은 고정되고 문서화된 출력 경로를 사용한다.
- 여러 파일을 반환하는 target은 모든 파일의 존재와 QC 통과를 확인한 뒤 경로를 반환한다.
- 중간 파일은 staging 경로에서 생성하고 검증 완료 후 최종 경로에 publish한다.

## 병렬처리와 자원

- 각 target은 `_targets.R`에 등록된 controller 중 적절한 controller를 `resources`에 명시한다.
- worker 수와 target 내부 thread 수를 별도로 기록한다.
- 총 예상 CPU 사용량은 대략 `동시 workers × target당 threads`로 계산하고 가용 CPU를 초과하지 않게 한다.
- GPU target에는 전용 GPU controller와 GPU lock을 사용한다.
- 하나의 GPU에 여러 학습 process를 무분별하게 동시에 배치하지 않는다.
- target 내부 병렬처리를 사용하는 경우 nested parallelism과 BLAS/OpenMP oversubscription을 방지한다.
- worker, thread, GPU 수는 configuration 또는 환경변수로 재현 가능하게 설정한다.

## 검증 순서

변경 범위에 맞게 아래 검증을 순서대로 수행한다.

1. 변경된 R 및 Python 파일의 parse 또는 syntax 검사
2. 관련 단위 테스트와 데이터 계약 테스트
3. `targets::tar_manifest()`로 target 정의 확인
4. `targets::tar_network()` 또는 이에 준하는 방법으로 dependency 확인
5. `targets::tar_validate()` 실행
6. 변경된 target과 필요한 upstream dependency 실행
7. 실행 결과의 파일 존재, schema, CRS, row count, checksum 및 QC 확인
8. 필요하면 전체 research pipeline에 대해 `tar_make()` 실행
9. 성공 후 dependency network HTML 갱신

대규모, 장시간 또는 GPU production 실행은 작은 fixture 또는 pilot 검증을 먼저 통과해야 한다. 예상 시간이나 자원 사용량이 큰 경우 전체 실행 전에 사용자에게 범위와 예상 비용을 알린다.

`tar_make()` 실행 중 오류가 발생하면 로그와 `targets::tar_meta()`를 확인하여 원인을 수정하고 다시 실행한다. 이미 성공한 target을 불필요하게 강제 재실행하지 않는다. 다음 상황에서는 자동 수정을 중단하고 사용자에게 보고한다.

- 논문 방법론 또는 blueprint 변경이 필요한 경우
- 원본이나 사용자 소유 데이터를 삭제·이동·덮어써야 하는 경우
- 대규모 산출물을 처음부터 다시 생성해야 하는 경우
- 필요한 입력, 권한, 패키지 또는 GPU가 없는 경우
- 수정 방향이 결과의 과학적 의미를 바꿀 수 있는 경우

## dependency network

target 구조가 변경되면 다음 명령으로 dependency network를 갱신한다.

    Rscript tools/targets-network/render_targets_network.R

생성된 HTML이 현재 manifest와 일치하는지 확인한다. target 추가·삭제·이름 변경·dependency 변경이 있었는데 그래프가 갱신되지 않은 상태로 작업을 완료하지 않는다.

## 완료 조건

target 관련 작업은 다음 조건을 모두 만족해야 완료된 것으로 본다.

- 변경된 코드가 parse된다.
- 관련 테스트가 통과한다.
- `tar_validate()`가 통과한다.
- 요청된 target 실행이 성공한다.
- 산출물의 파일 및 데이터 계약 QC가 통과한다.
- dependency network HTML이 최신 상태다.
- 실패, 경고, 실행하지 않은 검증 및 남은 위험이 최종 보고에 명시되어 있다.
- 저장소에 대용량 데이터, credential, targets store 또는 임시 산출물이 포함되지 않았다.

## Git 작업

- 먼저 `git status`와 diff를 검토하고 이번 작업에 해당하는 파일만 stage한다.
- `git add .`, `git add -A`, `git add --all`을 사용하지 않는다.
- 데이터 파일, `_targets/` store, 로그, checkpoint 및 임시 산출물을 commit하지 않는다.
- commit 전에 테스트 결과와 생성된 dependency network를 다시 확인한다.
- commit 및 push는 사용자가 현재 작업에서 명시적으로 요청한 경우에만 수행한다.
- 사용자가 commit과 push를 모두 요청했고 모든 완료 조건이 통과한 경우에만 push한다.
- 검증 실패 상태에서는 push하지 않는다.
- 기본 branch에서 직접 작업 중이라면 사용자의 명시적 지시가 없는 한 새 작업 branch를 사용한다.
- push 후 commit SHA, branch, 실행한 검증과 미실행 검증을 보고한다.

# 저장소 디렉터리 관리

저장소의 파일은 다음 원칙에 따라 배치한다.

- `R/`: 재사용 가능한 R 함수와 논문 방법론 구현
- `python/`: 딥러닝 모델, 학습 및 평가 코드
- `scripts/`: 직접 실행하는 작업별 진입 스크립트
- `scripts/preprocess/`: 원본 데이터에서 canonical 데이터를 생성하는 전처리 스크립트
- `config/`: 경로, 전처리 및 모델 설정 파일
- `tests/`: 함수 및 데이터 계약 검증 코드와 소규모 fixture
- `reports/`: 감사, 검증, 실험 및 작업 결과 보고서
- `logs/`: 장시간 실행 작업의 표준 출력과 오류 로그

필요한 디렉터리가 없으면 해당 작업을 처음 구현할 때 생성한다. 목적이 불분명한 새 최상위 디렉터리는 만들지 않는다.

원본 ZIP에서 canonical GPKG/TIF를 생성하는 작업은 `scripts/preprocess/`에서 관리한다. 논문의 공간장면 구성, 관계 생성, 모델 입력 생성, 학습 및 평가는 재사용 가능한 모듈과 R `targets` 파이프라인으로 관리한다.

대규모 원본 데이터, staging 파일, 모델 입력 데이터, GPKG, GeoTIFF, GeoParquet, checkpoint 및 기타 생성 산출물은 Git 저장소에 저장하지 않는다. 해당 파일은 `AGENTS.md`와 설정 파일에 지정된 `/mnt/hdd002/dhnyu/fusedata/` 하위 경로에 저장한다.

일시적인 진단 파일과 중간 산출물을 저장소 최상위에 만들지 않는다. 임시 파일은 시스템 임시 디렉터리 또는 작업별 외부 staging 경로에 저장하고, 작업 완료 후 안전하게 정리한다. 사용자 소유 파일과 기존 산출물은 임의로 이동, 이름 변경, 덮어쓰기 또는 삭제하지 않는다.

## 보고서 파일 규칙

모든 Markdown 보고서는 `reports/`에 저장하며 다음 파일명을 사용한다.

`YYYYMMDD_HHMM_<descriptive-name>.md`

예:

- `20260819_2356_implementation_feasibility.md`
- `20260820_0823_core_data_audit.md`
- `20260820_1640_building_preprocessing_qc.md`

날짜와 시간은 보고서 파일을 최초 생성한 시점의 Asia/Seoul 시간을 사용한다. `<descriptive-name>`은 영문 소문자와 숫자, underscore만 사용하며 보고서 내용을 명확하게 나타내야 한다.

기존 보고서를 덮어쓰지 않는다. 동일 작업을 다시 수행한 경우 새로운 생성 시각으로 별도 보고서를 작성한다. 기존 보고서에 사용자가 명시적으로 수정을 요청한 경우에만 해당 파일을 수정한다.

보고서 안에는 최소한 다음 정보를 기록한다.

- 작업 목적과 범위
- 실행 시각
- 입력 데이터 또는 Git commit
- 수행한 검사나 처리
- 주요 결과
- 경고 및 미해결 사항
- 최종 판정 또는 다음 단계
- 입력 프롬프트 요약

로그 파일은 `logs/`에 저장하며 보고서와 같은 시간 접두사를 사용하는 것을 권장한다.

`YYYYMMDD_HHMM_<descriptive-name>.log`