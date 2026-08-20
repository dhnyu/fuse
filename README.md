# fuse

`fuse`의 study-data maintenance와 논문 research pipeline은 target script와
targets store 수준에서 분리되어 있다. 루트 `_targets.R`은 승인된 서울 study
files에서 시작하는 research pipeline만 조립하며 `seoul_data_preprocess`를 등록하거나
참조하지 않는다.

## 코드 구조

- `R/`: 재사용 가능한 함수. 함수 파일에는 `tar_target()`을 두지 않는다.
- `targets/research_scene_index.R`: source contract와 scene-index target을 선언한다.
- `targets/research_membership.R`: prototype membership plan/branch/acceptance를 선언한다.
- `targets/research_observation.R`: aligned observation plan과 vector observation branch를 선언한다.
- `targets/research_raster_observation.R`: aligned raster observation branch를 선언한다.
- `_targets.R`: research pipeline과 CPU controller만 등록한다.
- `_targets_maintenance.R`: `seoul_data_preprocess` 전용 maintenance graph다.
- `tools/targets-network/`: target을 계산하지 않고 dependency HTML을 생성한다.
- `artifacts/targets-network/`: 생성된 HTML. 재생성 가능한 산출물이므로 Git에서 제외한다.
- `scripts/run_targets.R`: research store를 사용하는 `tar_make()` 진입점이다.
- `scripts/run_maintenance_targets.R`: 별도 maintenance store 진입점이다.
- `scripts/preprocess/`: targets graph에 포함되지 않는 전국 canonical ingest 코드다.

현재 research 구현은 scene index, prototype membership, prototype vector/raster observation 승인 단위로 구성된다.

| 구분 | target | 역할 |
|---|---|---|
| 보조 | `research_config_files` | config와 JSON Schema를 `format="file"`로 추적 |
| 보조 | `research_implementation_files` | methodology contract 구현 source hash 추적 |
| 핵심 | `study_data_inputs` | study artifacts 8개와 official-grid components 4개 추적 |
| 보조 | `study_data_inventory` | read-only input/schema/CRS/coverage 검증 JSON |
| 핵심 | `methodology_contract` | scientific contract와 record-only thesis provenance |
| 핵심 | `spatial_scene_index` | training 250 m lattice와 fixed off-lattice index |
| 핵심 | `prototype_scene_selection` | 320-scene pre-membership proxy 표본 |
| 보조 | `membership_contract_files` | membership scientific/runtime config와 JSON Schema 추적 |
| 핵심 | `prototype_membership_plan` | 320 scenes의 cost-balanced 9-branch spec |
| 핵심 | `prototype_membership_shard` | B/R/P exact membership 일반 Parquet dynamic branch |
| 핵심 | `prototype_membership_acceptance` | checksum/source ID/brute-force/aggregate QC gate |
| 보조 | `observation_contract_files` | vector scientific/runtime/schema/writer/implementation 추적 |
| 핵심 | `prototype_observation_plan` | vector/raster/relation 공통 15-branch scene grouping |
| 핵심 | `prototype_vector_observation_shard` | B/R/P clipped observation GeoParquet 1.1 dynamic branch |
| 보조 | `raster_observation_contract_files` | raster scientific/runtime/schema/Zarr writer contract 추적 |
| 핵심 | `prototype_raster_observation_shard` | aligned scene LC/DEM Zarr와 object context Parquet dynamic branch |

## Research Pipeline 실행

Prototype raster observation까지 실행한다. 각 branch 내부 worker/thread는 1이다.
Membership은 `controller_20`, vector clipping과 raster extraction은 `controller_10`을 사용한다.

```bash
FUSE_CONTROLLER_10_WORKERS=10 \
Rscript scripts/run_targets.R prototype_raster_observation_shard
```

Research store는 `/mnt/hdd002/dhnyu/fusedata/targets/fuse-research`, derived artifact는
`/mnt/hdd002/dhnyu/fusedata/scene_data/v1`에 저장된다. Scene index는 GeoParquet,
contract/manifest/QC는 JSON, membership과 object raster context는 geometry 없는 Parquet,
observed geometry는 GeoParquet 1.1.0 WKB, scene raster는 Zarr v2다. 모든 대규모 산출물은 staging에서 검증한 뒤
content-addressed directory로 atomic publish한다.

`prototype_membership_plan`은 branch spec JSON을 외부에 publish한 뒤 작은 spec list를
`format="rds", iteration="list"`로 반환한다. `targets 1.12.0`은 정적
`format="file"` stem을 직접 `map()`하는 것을 허용하지 않기 때문이다. I07은
`pattern=map(prototype_membership_plan)`이며 branch output은 `format="file"`이다.
I09도 같은 atomic JSON + small RDS list convention을 사용한다. I10은
`pattern=map(prototype_observation_plan)`, I11은 aligned
`pattern=map(prototype_observation_plan, prototype_vector_observation_shard)`이며 둘 다
`format="file"`이다.

Maintenance는 research graph와 다른 script/store를 명시적으로 사용한다.

```bash
Rscript scripts/run_maintenance_targets.R seoul_data_preprocess
```

Maintenance store는 `/mnt/hdd002/dhnyu/fusedata/targets/fuse-maintenance`다. Research
target을 실행해도 maintenance target이 실행되거나 outdated되지 않는다.

`R/preprocessing_utils.R`는 canonical ingest 전용이다. 방법론 `_targets.R`은
이 파일을 source하지 않아 두 파이프라인의 이름과 실행 상태가 섞이지 않는다.

## Dependency HTML

전체 graph:

```bash
Rscript tools/targets-network/render_targets_network.R
```

특정 target 중심 graph를 함께 생성:

```bash
Rscript tools/targets-network/render_targets_network.R \
  --focus=spatial_scene_index --degree=1
```

출력은 `artifacts/targets-network/targets-network.html` 및 선택 시
`targets-network-focus-*.html`이다. HTML의 target 선택 상자로 이름을 검색할
수 있고 확대·이동 및 인접 target 강조가 가능하다. 자세한 옵션은
`tools/targets-network/README.md`를 참고한다.

## 병렬 실행

Research `_targets.R`은 `controller_05`,
`controller_10`, `controller_20`, `controller_40`을 `crew_controller_group()`으로
등록한다. Controller 이름은 CPU 할당량이 아니라 동시에 실행 가능한 crew worker
pool이다. Static plan/acceptance는 `controller_05`, membership dynamic branch는
`controller_20`, vector/raster observation dynamic branch는 `controller_10`을 사용한다. 모든 research target 내부 병렬도는
`workers=1`, `threads=1`, GPU 0개다.

Maintenance의 `controller_20`은 CPU 20개를 target에 직접 할당하는 설정이 아니라,
해당 target을 실행할 수 있는 crew worker pool의 이름이다.

실제 target 내부 병렬도는 `targets/seoul_data_preprocess.R`의 command에 직접 적힌
`workers = 5`, `threads = 4`가 유일한 기준이다. `future::multisession` worker 5개와
worker별 native thread 상한 4개로 이론상 최대 20 logical CPUs를 사용한다. Building,
Road, POI, land-cover, DEM은 서로 다른 파일에 단독으로 쓰며 병렬 실행된다.
Boundary/buffer 생성은 병렬 구간 전에, 전체 QC/manifest/report는 이후에 직렬 실행된다.
target은 실행 전에 `workers * threads`를 available logical CPUs와 비교한다. 실행
범위에서만 OMP/OpenBLAS/MKL/Veclib/NumExpr/GDAL 환경과 `data.table` thread를
설정하며, future plan을 포함한 이전 상태는 성공 또는 오류 후 모두 복원한다.

crew pool 크기는 다음 환경변수로 덮어쓸 수 있다. 이는 target 내부의
`workers`/`threads` 값을 변경하지 않는다.

```bash
FUSE_CONTROLLER_05_WORKERS=5 \
FUSE_CONTROLLER_10_WORKERS=10 \
FUSE_CONTROLLER_20_WORKERS=20 \
FUSE_CONTROLLER_40_WORKERS=40 \
Rscript scripts/run_targets.R
```

내부 순차 디버깅은 target 선언의 command를 명시적으로 `workers = 1`로 바꾼다.
이때 multisession cluster는 생성되지 않는다. `scripts/run_targets.R`은 병렬도 관련
환경변수나 기본값을 주입하지 않는다.

향후 target도 command에 병렬도를 직접 전달하고 resources에서 pool을 선택한다.

```r
targets::tar_target(
  name = another_target,
  command = process_another_target(workers = 10, threads = 2),
  resources = targets::tar_resources(
    crew = targets::tar_resources_crew(controller = "controller_20")
  )
)
```

동일 GeoPackage나 TIFF에 여러 target/branch가 동시에 쓰지 않도록 한다. 동적
분기를 추가할 때도 shard별 임시 파일만 병렬 생성하고, 단일 파일 병합·RTree
생성·최종 publish·교차 산출물 QC는 직렬 target으로 둔다.
