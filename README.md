# fuse

`fuse`의 전국 canonical ingest와 논문 방법론 파이프라인은 분리되어 있다.
`scripts/preprocess/`는 canonical 데이터 생성 전용이며, 루트 `_targets.R`은
검증된 canonical snapshot에서 시작하는 방법론 target만 조립한다.

## 코드 구조

- `R/`: 재사용 가능한 함수. 함수 파일에는 `tar_target()`을 두지 않는다.
- `targets/seoul_data_preprocess.R`: 단일 preprocessing target 선언만 제공한다.
- `_targets.R`: 패키지, 공통 옵션과 함수/target 로딩 순서를 정의한다.
- `tools/targets-network/`: target을 계산하지 않고 dependency HTML을 생성한다.
- `artifacts/targets-network/`: 생성된 HTML. 재생성 가능한 산출물이므로 Git에서 제외한다.
- `scripts/run_targets.R`: 사용자가 실행하는 짧은 `tar_make()` 진입점이다.
- `scripts/preprocess/`: targets graph에 포함되지 않는 전국 canonical ingest 코드다.

새 공간처리 함수는 책임에 맞는 `R/process_*.R`, I/O 함수는 `R/io_*.R`,
검증 함수는 `R/validate_*.R`에 추가한다. `targets/seoul_data_preprocess.R`에는
선언만 두고 전체 orchestration은 `R/pipeline_seoul_data_preprocess.R`에서 관리한다.

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
  --focus=seoul_data_preprocess --degree=1
```

출력은 `artifacts/targets-network/targets-network.html` 및 선택 시
`targets-network-focus-*.html`이다. HTML의 target 선택 상자로 이름을 검색할
수 있고 확대·이동 및 인접 target 강조가 가능하다. 자세한 옵션은
`tools/targets-network/README.md`를 참고한다.

## 병렬 실행

target은 `seoul_data_preprocess` 하나다. `_targets.R`은 `controller_05`,
`controller_10`, `controller_20`, `controller_40`을 `crew_controller_group()`으로
등록한다. `controller_20`은 CPU 20개를 target에 직접 할당하는 설정이 아니라,
해당 target을 실행할 수 있는 crew worker pool의 이름이다.

실제 target 내부 병렬도는 `targets/seoul_data_preprocess.R`의 command에 직접 적힌
`workers = 5`, `threads = 4`가 유일한 기준이다. `future::multisession` worker 5개와
worker별 native thread 상한 4개로 이론상 최대 20 logical CPUs를 사용한다. Building,
Road, POI, land-cover, DEM은 서로 다른 파일에 단독으로 쓰며 병렬 실행된다.
Boundary/buffer 생성은 병렬 구간 전에, 전체 QC/manifest/report는 이후에 직렬 실행된다.
target은 실행 전에 `workers * threads`를 available logical CPUs와 비교한다. 실행
범위에서만 OMP/OpenBLAS/MKL/Veclib/NumExpr/GDAL 환경과 `data.table` thread를
설정하며, future plan을 포함한 이전 상태는 성공 또는 오류 후 모두 복원한다.

기본 실행:

```bash
Rscript scripts/run_targets.R
```

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
