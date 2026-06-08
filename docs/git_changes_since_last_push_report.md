# Changes Since Last Git Push

## 1. 기준 정보

- 현재 브랜치: `main`
- 비교 기준 upstream 또는 원격 브랜치: `origin/main` (`@{u}`)
- 현재 HEAD 및 원격 커밋: `27e92da (HEAD -> main, origin/main) geo2vec_embedding_1`
- upstream 상태: `main`은 `origin/main`과 같은 커밋을 가리키며, 마지막 push 이후 변경은 커밋되지 않은 작업 디렉터리 변경이다.
- 조사 시각: `2026-06-08 22:12:22 KST`
- 원격 저장소: `origin git@github.com:dhnyu/fuse.git`
- 사용한 주요 git 명령:
  - `git status`
  - `git status --short`
  - `git branch -vv`
  - `git log --oneline --decorate -n 10`
  - `git remote -v`
  - `git diff --stat @{u}`
  - `git diff --name-status @{u}`
  - `git diff @{u}`
  - `git ls-files --others --exclude-standard`
  - `git status --short --ignored tests/geo2vec_large_scale`

## 2. 전체 요약

- 변경 파일 수: 조사 시점 기준 25개
- 수정된 추적 파일 수: 1개 (`AGENTS.md`)
- 새로 생성된 추적 파일 수: 0개
- 삭제된 추적 파일 수: 0개
- 표준 exclude 기준 추적되지 않은 파일 수: 24개
- 무시된 자동 생성 파일: `tests/geo2vec_large_scale/__pycache__/` 아래 Python bytecode 14개
- 추적 파일 diff 규모: `AGENTS.md` 1개 파일, 123 insertions, 171 deletions
- 민감정보 패턴 확인: 변경 범위에서 `api key`, `secret`, `token`, `password`, `PRIVATE KEY`, GitHub PAT류 문자열 패턴 매칭 없음

핵심 변경사항:

1. `AGENTS.md`가 긴 데이터 카탈로그형 지침에서 저장소 역할, 외부 연구 저장소 규칙, 공간 데이터 저장 원칙, 임베딩 출력 위치를 압축한 운영 지침으로 재구성되었다.
2. `tests/geo2vec_large_scale/`에 전국 단위 Korea building Geo2Vec 확장을 위한 신규 프로토타입 코드와 보고서 세트가 추가되었다.
3. 신규 Geo2Vec 설계는 chunk별 독립 모델이 아니라 하나의 `Geo2Vec_Model(n_poly=N)`과 하나의 전역 entity embedding table을 유지하는 단일 latent space 방식을 명시한다.
4. SDF 샘플 생성은 대규모 메모리 적재 대신 deterministic disk-backed parquet shard cache로 바뀌는 방향이다.
5. 전역 `building_id -> geo2vec_internal_id` 매핑, SDF shard manifest, checksum, atomic write, checkpoint/resume, embedding export가 하나의 실험 파이프라인으로 연결되었다.
6. 50k/100k/300k/1M engineering stress test 보고서와 sample-density sensitivity/saturation 보고서가 추가되어 실험 결과와 다음 단계 판단 근거가 문서화되었다.
7. Gwanak 문서에 전국 단일 latent space 계산 전략 문서가 추가되어, 메모리/스토리지 추정, sampling 전략 비교, 구현 아키텍처, validation plan을 정리한다.
8. R 기반 XGBoost 검증 스크립트가 추가되어 Geo2Vec embedding으로 건물 geometry-derived target을 예측하는 downstream validation 경로가 생겼다.
9. `__pycache__`는 ignored 상태이지만 작업 디렉터리에 존재하므로 커밋 대상에서는 제외되어야 한다.

## 3. 범주별 변경사항

### Code changes

#### `tests/geo2vec_large_scale/geo2vec_large_scale_common.py`

- 상태: untracked
- 변경 내용 요약: 대규모 Geo2Vec 프로토타입의 공통 경로, seed, checksum, atomic JSON/parquet write, RSS/GPU memory 측정, checkpoint 탐색, deterministic seeding helper를 정의한다.
- 의미: `/members/dhnyu/fusedata/geo2vec_large_scale` 아래에 id maps, sample caches, training runs, embeddings, reports, metadata, logs를 분리하는 새 출력 루트 계약을 만든다. 기존 Gwanak validation 임시 경로에서 전국 확장용 canonical 실험 경로로 이동하는 기반이다.

#### `tests/geo2vec_large_scale/inspect_building_geometry_inventory.py`

- 상태: untracked
- 변경 내용 요약: national building GeoPackage layer의 driver, CRS, feature count, geometry type, fields, extent와 bounded validity sample을 검사한다.
- 의미: 대규모 geometry를 전부 로드하지 않고도 입력 데이터 상태를 확인하는 사전 점검 단계다. 공간 처리 규칙의 "inspect before loading" 원칙에 맞는다.

#### `tests/geo2vec_large_scale/build_global_building_id_map.py`

- 상태: untracked
- 변경 내용 요약: `korea_buildings_vworld_attributes.parquet`에서 `building_id`를 읽어 stable mergesort 후 contiguous `geo2vec_internal_id`를 붙이고 parquet/json metadata를 쓴다.
- 의미: 모든 sample shard와 global embedding table이 공유하는 안정적인 id contract를 만든다. chunk별 모델을 피하고 하나의 latent space를 유지하는 데 필요한 핵심 전제다.

#### `tests/geo2vec_large_scale/generate_disk_backed_sdf_samples.py`

- 상태: untracked
- 변경 내용 요약: geometry subset과 id map을 결합해 normalized polygon SDF samples를 생성하고, shard별 parquet와 manifest를 atomic write로 저장한다. per-building seed는 `stable_hash(base_seed, building_id, geo2vec_internal_id, sample_config_version)` 형태다.
- 의미: 기존 all-at-once SDF materialization 대신 disk-backed sample cache를 도입한다. CPU 병렬 sampling, shard resume, checksum 검증을 통해 전국 규모 확장 시 메모리 폭발 위험을 낮춘다.

#### `tests/geo2vec_large_scale/validate_sample_cache.py`

- 상태: untracked
- 변경 내용 요약: sample shard schema/dtype, finite values, checksum, unknown id, train/validation split, per-building sample count를 검증하고 JSON/parquet report를 쓴다.
- 의미: trainer가 잘못된 shard나 불완전한 manifest로 시작하지 않도록 하는 validation gate 역할을 한다.

#### `tests/geo2vec_large_scale/check_sample_cache_overlap.py`

- 상태: untracked
- 변경 내용 요약: 두 sample cache manifest의 앞쪽 shard checksum과 row count를 비교한다.
- 의미: worker 수 변경이나 rerun 후 deterministic SDF generation이 유지되는지 확인하는 도구다. 재현성 검증에 직접 연결된다.

#### `tests/geo2vec_large_scale/train_global_geo2vec_from_sample_cache.py`

- 상태: untracked
- 변경 내용 요약: external `GeoNeuralRepresentation`의 `Geo2Vec_Model`과 `SDFLoss`를 사용해 sample parquet shard를 순차적으로 읽고 하나의 global model을 학습한다. checkpoint에는 model/optimizer state, epoch, global step, shard offset, RNG state, id-map checksum, sample-manifest checksum이 포함된다.
- 의미: 방법론적으로 중요한 변경이다. chunk별 독립 모델을 만들지 않고 전체 id table을 가진 하나의 모델을 계속 업데이트하므로 embedding vector가 같은 latent coordinate system에 놓인다. resume와 checkpoint retention도 장시간 전국 학습의 운영 리스크를 줄인다.

#### `tests/geo2vec_large_scale/export_global_geo2vec_embeddings.py`

- 상태: untracked
- 변경 내용 요약: checkpoint의 `poly_embedding_layer.weight`를 id map 순서대로 batch export하여 zstd parquet part와 manifest를 만든다.
- 의미: embedding export를 메모리 친화적인 증분 방식으로 처리한다. 출력은 `building_id`, `geo2vec_internal_id`, `geo2vec_000...` 열을 갖는 분석용 parquet 구조다.

#### `tests/geo2vec_large_scale/monitor_geo2vec_training.py`

- 상태: untracked
- 변경 내용 요약: training metrics, checkpoint, output size, throughput을 요약하는 monitoring report를 생성한다.
- 의미: 실험 진행 중 병목과 산출물 크기를 빠르게 확인하는 운영 도구다.

#### `tests/geo2vec_large_scale/run_sample_density_sensitivity.py`

- 상태: untracked
- 변경 내용 요약: Gwanak geometry에 대해 low/medium/high SDF sample density별 id map, sample cache, validation, training, embedding export를 순차 실행한다.
- 의미: 전국 production 설정 전에 sample density가 embedding 품질과 비용에 주는 영향을 통제된 Gwanak 환경에서 비교한다.

#### `tests/geo2vec_large_scale/run_sample_density_saturation.py`

- 상태: untracked
- 변경 내용 요약: 더 높은 sample density 구간에서 saturation 여부를 실험하는 runner다.
- 의미: 논문 방법론의 adaptive SDF sample 밀도와 engineering cost 사이의 tradeoff를 정량화하려는 확장 실험이다.

#### `tests/geo2vec_large_scale/run_epoch_saturation.py`

- 상태: untracked
- 변경 내용 요약: epoch 수 증가에 따른 embedding 품질/비용 변화를 실험하는 runner다.
- 의미: sample density만이 아니라 training duration이 downstream validation에 주는 영향을 분리해 보기 위한 도구다.

#### `tests/geo2vec_large_scale/summarize_sample_density_sensitivity.py`

- 상태: untracked
- 변경 내용 요약: sample-density sensitivity 결과를 요약 테이블로 정리한다.
- 의미: 실험 산출물을 보고서화하고 density별 효율/품질을 비교하는 후처리 단계다.

#### `tests/geo2vec_large_scale/summarize_epoch_saturation.py`

- 상태: untracked
- 변경 내용 요약: epoch saturation 실험 결과를 요약한다.
- 의미: 학습 epoch 증가의 marginal gain과 runtime cost를 판단하는 근거를 만든다.

#### `tests/geo2vec_large_scale/validate_density_embeddings_xgboost.R`

- 상태: untracked
- 변경 내용 요약: Geo2Vec embeddings를 사용해 `log_area`, `log_perimeter`, `compactness`, `elongation`, `bbox_area_ratio`를 XGBoost로 예측한다. random split, spatial block CV, dong holdout을 포함하고 결과를 parquet/csv로 저장한다.
- 의미: embedding 품질을 geometry-derived downstream task로 검증한다. 공간 block 및 행정동 holdout을 포함하므로 단순 random split보다 더 엄격한 일반화 확인이 가능하다.

### Configuration changes

#### `AGENTS.md`

- 상태: modified
- 변경 내용 요약: 기존의 상세 데이터 리소스 목록과 일반 working principle을 줄이고, repository 역할, 외부 연구 repository 사용 규칙, R/Python 선호 패키지, 공간 처리 규칙, 저장 형식, canonical resources, reproducibility, embeddings 위치를 간결한 구조로 재작성했다.
- 의미: 작업 지침이 더 압축되고 범용화되었다. 다만 기존 `Streetview`, `Building Data`, `Additional POI data`, 행정 boundary 파일명 등 구체적인 데이터 위치 설명 일부가 제거되어, 향후 자동 작업자가 특정 자료를 찾을 때 즉시성이 낮아질 수 있다.

### Documentation changes

#### `tests/geo2vec_large_scale/README.md`

- 상태: untracked
- 변경 내용 요약: Large-scale SDF-Geo2Vec prototype의 원칙, pipeline 순서, sample cache format, bottleneck, failure recovery, stage plan을 설명한다.
- 의미: 신규 prototype 디렉터리의 entry point 문서다. 특히 independent chunk models가 잘못된 latent space를 만든다는 방법론적 이유를 명시한다.

#### `tests/gwanak_test/docs/korea_geo2vec_single_latent_space_computing_strategy.md`

- 상태: untracked
- 변경 내용 요약: 전국 Korea building Geo2Vec을 하나의 latent space로 계산하기 위한 전략 문서다. online sampler, disk-backed cache, hybrid cache, two-stage strategy, geometry encoder alternative를 비교하고, 메모리/스토리지 추정과 구현 아키텍처를 제시한다.
- 의미: 신규 코드의 설계 문서 역할을 한다. 즉시 실행 권고는 deterministic subset에서 global id map을 먼저 만들고, disk-backed SDF cache prototype으로 Gwanak single-model 결과를 재현하는 것이다.

#### `tests/geo2vec_large_scale/korea_geo2vec_large_scale_pipeline_prototype_report.md`

- 상태: untracked
- 변경 내용 요약: 초기 50k prototype의 구현 코드, inventory, id map, SDF cache, training, checkpoint/resume, embedding export, bottleneck assessment를 정리한다.
- 의미: 신규 architecture가 작은 규모에서 작동했는지와 다음 단계로 넘어가기 위한 조건을 기록한다.

#### `tests/geo2vec_large_scale/korea_geo2vec_large_scale_pipeline_100k_report.md`

- 상태: untracked
- 변경 내용 요약: 100k prototype 성공, deterministic parallel SDF sampling, cache validation, global model training, mid-shard resume, embedding export 결과를 문서화한다.
- 의미: shard resume와 parallel SDF sampling이 100k 규모에서 안정적으로 작동했다는 근거다.

#### `tests/geo2vec_large_scale/korea_geo2vec_large_scale_pipeline_300k_report.md`

- 상태: untracked
- 변경 내용 요약: 300k engineering stability test 성공, checkpoint retention, resume smoke test, throughput scaling, 1M 진행 전 must-fix를 정리한다.
- 의미: 100k에서 300k로 scaling했을 때 CPU-side SDF sampling이 주요 병목임을 확인하고, trainer validation hardening 필요성을 기록한다.

#### `tests/geo2vec_large_scale/korea_geo2vec_large_scale_pipeline_1m_report.md`

- 상태: untracked
- 변경 내용 요약: 1M engineering stress test 성공과 output root 재구성, code hardening, overlap check, checkpointing, embedding export, 5M 진행 조건을 정리한다.
- 의미: architecture가 1M까지 운영 가능하다는 근거를 제공한다. 동시에 5M은 production quality가 아니라 보수적 engineering stress test로 해석해야 한다고 제한한다.

#### `tests/geo2vec_large_scale/sdf_worker_scaling_benchmark_report.md`

- 상태: untracked
- 변경 내용 요약: 100k subset에서 SDF worker 수별 throughput, determinism, I/O wait를 비교하고 5M run에 8 workers를 권고한다.
- 의미: 병렬 worker 수를 늘리는 것이 항상 이득이 아니라는 운영 판단 근거다.

#### `tests/geo2vec_large_scale/geo2vec_sample_density_sensitivity_report.md`

- 상태: untracked
- 변경 내용 요약: low/medium/high SDF density의 efficiency와 downstream validation 결과를 비교한다.
- 의미: low engineering density는 최종 품질 설정으로 보기 어렵고, medium 이상 또는 bounded high-density check가 필요하다는 판단 근거를 제공한다.

#### `tests/geo2vec_large_scale/geo2vec_sample_density_saturation_report.md`

- 상태: untracked
- 변경 내용 요약: 약 200부터 5,000 samples/building까지 density를 확장해 downstream R2 flattening을 분석한다.
- 의미: 품질 지향 production embedding에는 약 1,600 samples/building 설정을 practical default 후보로 제시한다. cache size와 runtime cost가 크게 증가하므로 full Korea 적용 전 별도 검증이 필요하다.

### Data/output/log changes

#### Repository 내부

- 상태: untracked/ignored
- 변경 내용 요약: 표준 git 대상에는 data parquet, GeoPackage, checkpoint, image, log 대용량 파일이 추가되지 않았다. 다만 ignored `tests/geo2vec_large_scale/__pycache__/` 아래 Python bytecode 14개가 존재한다.
- 의미: 커밋 대상 대용량 산출물은 현재 보이지 않는다. `__pycache__`는 자동 생성물이므로 계속 ignore 상태로 두는 것이 맞다.

#### Repository 외부 참조 산출물

- 상태: repo 밖 산출물 참조
- 변경 내용 요약: 신규 코드와 보고서들은 `/members/dhnyu/fusedata/geo2vec_large_scale` 아래 id maps, sample caches, training runs, embeddings, reports, metadata, logs를 생성하거나 참조한다. 일부 과거 stage 보고서는 `/members/dhnyu/fusedata/gwanak_test/validation` 경로도 참조한다.
- 의미: 실제 대용량 parquet sample cache, checkpoint, embedding 산출물은 repository 밖 canonical output area에 두는 설계다. 커밋 전에는 repo 안에 실수로 산출물이 들어오지 않았는지 계속 확인해야 한다.

### Tests or validation changes

#### `tests/geo2vec_large_scale/validate_sample_cache.py`

- 상태: untracked
- 변경 내용 요약: SDF sample cache에 대한 schema, checksum, finite value, id coverage 검증을 자동화한다.
- 의미: 대규모 학습 전 데이터 무결성 확인 단계다.

#### `tests/geo2vec_large_scale/check_sample_cache_overlap.py`

- 상태: untracked
- 변경 내용 요약: 서로 다른 cache run 사이 overlap shard의 checksum/row count 일치 여부를 확인한다.
- 의미: deterministic sampling이 worker 수나 재실행 조건에 영향을 받지 않는지 검증한다.

#### `tests/geo2vec_large_scale/validate_density_embeddings_xgboost.R`

- 상태: untracked
- 변경 내용 요약: downstream supervised validation을 수행하고 parquet/csv 결과를 쓴다.
- 의미: embedding이 geometry shape 정보를 실제로 보존하는지 평가하는 실험 검증 단계다.

#### 보고서에 기록된 validation 결과

- 상태: untracked documentation
- 변경 내용 요약: 100k, 300k, 1M reports는 `py_compile`, cache validation, checkpoint/resume, finite embedding export 성공을 기록한다.
- 의미: 현재 추가된 코드가 실제로 여러 stage에서 실행된 흔적이 있다. 다만 이 보고서는 문서 기록을 확인한 것이며, 이번 조사 과정에서 전체 파이프라인을 재실행하지는 않았다.

### Untracked files

표준 exclude 기준 `git ls-files --others --exclude-standard`에 잡힌 파일은 다음 24개다.

- `tests/geo2vec_large_scale/README.md`
- `tests/geo2vec_large_scale/build_global_building_id_map.py`
- `tests/geo2vec_large_scale/check_sample_cache_overlap.py`
- `tests/geo2vec_large_scale/export_global_geo2vec_embeddings.py`
- `tests/geo2vec_large_scale/generate_disk_backed_sdf_samples.py`
- `tests/geo2vec_large_scale/geo2vec_large_scale_common.py`
- `tests/geo2vec_large_scale/geo2vec_sample_density_saturation_report.md`
- `tests/geo2vec_large_scale/geo2vec_sample_density_sensitivity_report.md`
- `tests/geo2vec_large_scale/inspect_building_geometry_inventory.py`
- `tests/geo2vec_large_scale/korea_geo2vec_large_scale_pipeline_100k_report.md`
- `tests/geo2vec_large_scale/korea_geo2vec_large_scale_pipeline_1m_report.md`
- `tests/geo2vec_large_scale/korea_geo2vec_large_scale_pipeline_300k_report.md`
- `tests/geo2vec_large_scale/korea_geo2vec_large_scale_pipeline_prototype_report.md`
- `tests/geo2vec_large_scale/monitor_geo2vec_training.py`
- `tests/geo2vec_large_scale/run_epoch_saturation.py`
- `tests/geo2vec_large_scale/run_sample_density_saturation.py`
- `tests/geo2vec_large_scale/run_sample_density_sensitivity.py`
- `tests/geo2vec_large_scale/sdf_worker_scaling_benchmark_report.md`
- `tests/geo2vec_large_scale/summarize_epoch_saturation.py`
- `tests/geo2vec_large_scale/summarize_sample_density_sensitivity.py`
- `tests/geo2vec_large_scale/train_global_geo2vec_from_sample_cache.py`
- `tests/geo2vec_large_scale/validate_density_embeddings_xgboost.R`
- `tests/geo2vec_large_scale/validate_sample_cache.py`
- `tests/gwanak_test/docs/korea_geo2vec_single_latent_space_computing_strategy.md`

Ignored generated files:

- `tests/geo2vec_large_scale/__pycache__/` 아래 `*.cpython-314.pyc` 14개
- 상태: ignored, 자동 생성 Python bytecode
- 의미: 커밋하지 않는 것이 적절하다. `git status --short --ignored tests/geo2vec_large_scale`에서 `!! tests/geo2vec_large_scale/__pycache__/`로 확인된다.

## 4. 중요한 diff 해석

### `AGENTS.md` 지침 재구성

`AGENTS.md`는 세부 데이터 위치 목록 중심에서 프로젝트 운영 원칙 중심으로 바뀌었다. 새 구조는 `fuse`, `fusedata`, `fusedatalarge`, `fuse_external`의 역할을 명확히 나누고, 외부 연구 저장소를 `~/fuse`에 복사하지 말고 wrapper/extension code를 `~/fuse` 안에 두라는 규칙을 강조한다.

이 변경은 GeoNeuralRepresentation 같은 외부 방법론을 사용할 때 특히 중요하다. 신규 Geo2Vec prototype은 external repo를 직접 수정하기보다 `tests/geo2vec_large_scale` 쪽 wrapper 스크립트에서 실행하는 구조이므로, 변경된 지침과 방향이 맞다.

주의할 점은 기존 `AGENTS.md`에 있던 일부 구체 자료 설명이 삭제되었다는 것이다. 예를 들어 행정 boundary 파일명, Street View raw/crop 위치, VWorld building source 위치, river polygon 위치 등은 더 이상 상세히 적혀 있지 않다. 자동 작업자가 특정 데이터셋을 찾는 작업에서는 `Canonical Project Resources` 목록만으로 부족할 수 있다.

### 전역 ID map과 단일 latent space 계약

신규 코드의 중심은 `build_global_building_id_map.py`와 `train_global_geo2vec_from_sample_cache.py`다. 전자는 deterministic `building_id -> geo2vec_internal_id` parquet를 만들고, 후자는 `n_poly = max(geo2vec_internal_id) + 1`인 하나의 `Geo2Vec_Model`을 생성한다.

이 설계는 "chunk는 I/O와 sample cache 단위로만 나누고, 모델은 나누지 않는다"는 의미다. chunk별 독립 모델을 학습하면 각 chunk embedding이 서로 다른 latent coordinate system에 놓일 수 있으므로 전국 building embedding을 직접 비교할 수 없다. 현재 신규 설계는 모든 shard minibatch가 같은 model parameter와 같은 entity table을 업데이트하므로 이 문제를 피한다.

### SDF sample 생성 방식 변경

`generate_disk_backed_sdf_samples.py`는 geometry를 shape-normalize한 뒤 vertex, boundary Gaussian, length-proportional, uniform grid sample을 만들고 signed distance를 계산한다. 출력 schema는 `geo2vec_internal_id`, `x`, `y`, `sdf`, `split`, `sample_kind`, `sample_index`로 고정된다.

기존 all-at-once 방식과 달리 sample을 parquet shard에 쓰고 manifest에 checksum, row count, worker count, elapsed time 등을 기록한다. 이는 전국 규모에서 Python dictionary와 CPU tensor를 한 번에 materialize하는 위험을 줄이는 engineering change다. 방법론적으로는 Geo2Vec shape branch를 유지하면서 운영 방식을 바꾸는 것으로 해석된다.

### Checkpoint/resume hardening

`train_global_geo2vec_from_sample_cache.py`는 checkpoint에 RNG state, shard offset, sample offset, id-map checksum, sample-manifest checksum을 포함한다. resume 시 checksum을 비교하고 같은 global embedding table을 복원한다.

이 변경은 장시간 학습에서 interruption 이후 같은 run을 이어가기 위한 필수 조건이다. 또한 `--keep-checkpoints`로 checkpoint retention을 설정할 수 있어 5M 이상 실험에서 checkpoint 파일이 무제한 쌓이는 위험을 줄인다.

### Export와 validation의 분리

`export_global_geo2vec_embeddings.py`는 checkpoint에서 embedding table을 추출해 parquet parts로 내보낸다. `validate_density_embeddings_xgboost.R`는 이 embedding을 downstream task에 사용한다.

이 분리는 training artifact와 analytical output을 분리한다. 연구 파이프라인 관점에서는 checkpoint를 모델 재개용 산출물로, parquet embedding을 분석/검증용 산출물로 다룰 수 있다.

### 실험 설정과 stage progression

보고서들은 50k, 100k, 300k, 1M 순서의 engineering stress test progression을 기록한다. 100k와 300k는 Gwanak validation 경로를 일부 사용했고, 1M 보고서는 output root를 `/members/dhnyu/fusedata/geo2vec_large_scale`로 재구성했다고 설명한다.

이 흐름은 "production pipeline"이라기보다 "scalability experiment"에 가깝다. 문서도 5M 및 full Korea 실행을 final quality run이 아니라 conservative engineering stress test로 취급한다.

## 5. 위험요소와 확인 필요 사항

- 커밋하면 안 될 대용량 파일: 현재 표준 git status에는 parquet sample cache, checkpoint, embedding part 같은 대용량 산출물이 보이지 않는다. 하지만 신규 코드가 `/members/dhnyu/fusedata/geo2vec_large_scale`에 대규모 산출물을 생성하므로, 커밋 전 `git status --short`와 `git ls-files --others --exclude-standard`를 다시 확인해야 한다.
- 자동 생성 파일: `tests/geo2vec_large_scale/__pycache__/` 아래 bytecode가 존재한다. 현재 ignored 상태라 커밋 대상은 아니지만, `.gitignore`가 바뀌면 유입될 수 있다.
- 민감정보 가능성: 변경 범위에서 일반적인 secret/token/password/API key 패턴은 발견되지 않았다. 보고서에는 민감정보 값을 기록하지 않았고, 발견된 값도 없다.
- 재현성 영향: deterministic seed `20260608`, stable hash, checksum, atomic writes가 들어가 재현성은 강화되었다. 다만 multiprocessing SDF sampling, external repository dependency, PyTorch/CUDA nondeterminism은 완전히 제거된 것은 아니므로 stage별 checksum과 validation report가 중요하다.
- 방법론 영향: disk-backed cache와 chunked I/O는 engineering optimization이다. 보고서들이 명시하듯 독립 chunk model을 쓰지 않는 한 single latent space 방법론은 유지되지만, sample density 설정은 embedding 품질에 큰 영향을 준다.
- 아직 검증되지 않은 코드: 문서상 py_compile과 stage run 성공 기록은 있으나, 이번 조사에서는 R workflow 규칙에 따라 전체 pipeline을 재실행하지 않았다. 신규 report 내용을 신뢰하되, 커밋 전 최소 syntax check 또는 targeted smoke test를 다시 수행하는 것이 좋다.
- 문서와 코드의 불일치 가능성: `README.md`는 prototype outputs가 `/members/dhnyu/fusedata/gwanak_test/validation/` 아래 있어야 한다고 쓰지만, 공통 helper는 `/members/dhnyu/fusedata/geo2vec_large_scale`를 기본 output root로 둔다. 1M report는 이 reorganization을 설명하므로 README가 최신 경로 정책을 따라가도록 갱신할 필요가 있다.
- `.gitignore` 또는 Git LFS 적용 필요: 현재 repo 내부 대용량 파일은 없지만, 향후 checkpoint `*.pt`, sample cache `*.parquet`, embedding parts, logs가 repo 안에 생성될 경우 ignore 규칙이 필요하다. 대용량 산출물은 기존 프로젝트 규칙대로 `~/fusedata` 또는 `~/fusedatalarge`에 두는 것이 맞다.
- 외부 repository 의존성: trainer/exporter는 `/members/dhnyu/fuse_external/GeoNeuralRepresentation`의 `models.Geo2Vec`을 import한다. 실행 환경에는 해당 external repo와 의존 패키지가 있어야 한다.

## 6. 최종 요약

이번 변경의 핵심 의미는 Korea building Geo2Vec을 전국 규모로 확장하기 위한 연구/engineering prototype이 새로 추가되었다는 것이다. 방향은 명확하다: building id를 전역적으로 고정하고, SDF samples만 shard/cache로 나누며, 학습은 하나의 global Geo2Vec model과 하나의 embedding table에서 수행한다. 이 설계는 chunk별 독립 embedding space 문제를 피하면서, parquet cache와 checkpoint/resume으로 대규모 운영 리스크를 낮추려는 변경이다.

다음에 커밋하기 전 해야 할 일:

1. `tests/geo2vec_large_scale/README.md`의 output path 정책을 현재 `geo2vec_large_scale_common.py` 기본값과 맞춘다.
2. `__pycache__`가 계속 ignored인지 확인한다.
3. 신규 Python/R 스크립트 중 커밋 대상과 단순 실험 산출 문서를 구분한다.
4. 외부 산출물 parquet/checkpoint/log가 repo 안에 들어오지 않았는지 다시 확인한다.
5. 가능하면 신규 Python 파일에 대해 lightweight syntax validation을 수행한다.

push 전에 확인할 명령어 제안:

```bash
git status --short
git status --short --ignored tests/geo2vec_large_scale
git diff --stat @{u}
git diff --name-status @{u}
git ls-files --others --exclude-standard
python -m py_compile tests/geo2vec_large_scale/*.py
rg -n "api[_-]?key|secret|token|password|passwd|credential|PRIVATE KEY|github_pat|ghp_" AGENTS.md tests/geo2vec_large_scale tests/gwanak_test/docs/korea_geo2vec_single_latent_space_computing_strategy.md
```

이 보고서 파일 `docs/git_changes_since_last_push_report.md`는 조사 후 새로 생성된 산출물이며, 위 변경 수 집계에는 보고서 생성 전 기준 변경분을 사용했다.
