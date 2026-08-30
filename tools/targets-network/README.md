# targets dependency network

이 도구는 `_targets.R`과 research targets store를 읽어 현재 dependency graph와
validity snapshot을 self-contained HTML로 저장한다. `tar_make()`나 개별 target
command는 실행하지 않는다. 최신 실행의 `queued`/`skipped` 표시 대신 공개
`targets` API인 `tar_outdated()`, `tar_progress()`, `tar_errored()`와 `tar_meta()`를
사용한다.

- node fill: 현재 status (`error`, `running`, `outdated`, `up_to_date`)
- node border와 두 번째 label line: research Phase
- node shape: stem 또는 file target
- arrow: dependency에서 dependent 방향

검색, Phase/status filter, status quick filter, pan/zoom, reset/fit, 세부 정보와
선택 target의 transitive upstream/downstream 강조를 제공한다. Phase authority는
`target_phases.yml`의 explicit mapping이며, 새 target이 mapping되지 않으면 renderer가
fail-closed한다. target dependency를 시각화를 위해 변경하거나 연결하지 않는다.

필요 패키지는 현재 환경에 설치된 `targets`, `visNetwork`, `yaml`, `jsonlite`,
`igraph`이다.
기본 store는 `config/research_paths.yml`의 `targets.research_store`다.

## 전체 graph

```bash
Rscript tools/targets-network/render_targets_network.R
```

출력: `artifacts/targets-network/targets-network.html`

## 특정 target 중심 graph

```bash
Rscript tools/targets-network/render_targets_network.R \
  --focus=spatial_scene_index \
  --degree=1
```

`--degree`는 선택 target에서 양방향으로 포함할 dependency hop 수다. 위 명령은
전체 graph와 `targets-network-focus-spatial_scene_index.html`을
함께 생성한다. 다른 출력 위치는 `--output-dir=/path/to/output`으로 지정한다.
다른 store를 검사할 때는 `--store=/absolute/store/path`를 사용한다.
다른 Phase mapping을 시험할 때는 `--phases=/absolute/target_phases.yml`을 사용한다.

HTML은 self-contained이며 deterministic node/edge/legend order를 사용한다. 동일한
graph와 store metadata를 다시 render하면 bytes가 같고 파일을 rewrite하지 않는다.
`artifacts/targets-network/`는 `.gitignore`에 포함되지만 canonical full HTML은
명시적으로 추적한다.
